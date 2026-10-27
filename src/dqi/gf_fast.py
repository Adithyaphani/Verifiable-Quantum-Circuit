"""Cheaper reversible GF(2^12) arithmetic for kickmix circuits.

    ixor_mul      target ^= x * y                        54 Toffolis (kickmix: 63)
                  with a quantum control                 66          (kickmix: 75)
    init_inverse  fresh register := z^-1 (0 -> 0)        78 Toffolis (kickmix: 315)
    init_div      fresh register := x / y                132         (kickmix: 378)
    del_*         measurement-based uncomputation         0 Toffolis

How: every value is built from GF(2)-linear maps (CNOTs, free) and bilinear products.
A bilinear product is a list of terms (x-form, y-form, output set); each term costs one
AND (init_and), whose result is fanned out with CNOTs and then cleared with HMR + a
classically conditioned CZ. Multiplication uses 2-level Karatsuba over a 3-bit
6-product base (54 ANDs); inversion goes through the tower GF(((2^3)^2)^2), where
z^-1 = conj(z) / norm(z) needs 3 GF(64) products and one GF(64) inversion (24 ANDs).
A register holding linear + bilinear functions of live registers is uncomputed for
free: HMR its bits, then apply the (linear -> Z, bilinear -> CZ) phase corrections
conditioned on the measured bits.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import kickmix as km

from .gf_alg import Tower, field_mul_terms, invert_linear, tower_isomorphism

Q = list  # list of km.q


# ----------------------------------------------------------------------------- symbolic pieces
@dataclass
class Term:
    xs: list            # qubits whose parity is the x factor
    ys: list            # qubits whose parity is the y factor
    outs: list          # target qubits receiving the AND


@dataclass
class Value:
    """A register's content: XOR of linear parts and bilinear terms of other live qubits."""
    reg: list
    linear: list = field(default_factory=list)   # (source qubit, [target qubits])
    terms: list = field(default_factory=list)    # Term


def _cols_to_targets(mask: int, reg):
    return [reg[i] for i in range(len(reg)) if (mask >> i) & 1]


def _bits(mask: int, reg):
    return [reg[i] for i in range(len(reg)) if (mask >> i) & 1]


# ----------------------------------------------------------------------------- emitters
def _parity_qubit(b, qs, scratch):
    if len(qs) == 1:
        return qs[0], None
    anc = b.alloc_qubits(1)[0]
    for q in qs:
        b.cx(q, anc)
    return anc, anc


def _unparity(b, qs, anc):
    if anc is not None:
        for q in qs:
            b.cx(q, anc)
        b.free(anc)


def emit_terms(b, terms, scratch=None):
    """XOR every term's AND into its outputs (one Toffoli per term)."""
    for t in terms:
        if not t.xs or not t.ys or not t.outs:
            continue
        if set(t.xs) == set(t.ys):              # x AND x = x: a linear term, no Toffoli
            fx, ax = _parity_qubit(b, t.xs, scratch)
            b.cx(fx, km.array(t.outs))
            _unparity(b, t.xs, ax)
            continue
        fx, ax = _parity_qubit(b, t.xs, scratch)
        fy, ay = _parity_qubit(b, t.ys, scratch)
        a = b.alloc_qubits(1)[0]
        b.init_and(fx, fy, a)
        b.cx(a, km.array(t.outs))
        b.del_and(fx, fy, a)
        b.free(a)
        _unparity(b, t.ys, ay)
        _unparity(b, t.xs, ax)


def emit_linear(b, linear):
    for src, outs in linear:
        if outs:
            b.cx(src, km.array(outs))


def mbu_clear(b, val: Value):
    """Zero `val.reg` (holding linear+bilinear functions of live qubits) with no Toffolis."""
    reg = list(val.reg)
    bits = b.alloc_bits(len(reg))
    b.hmr(km.array(reg), bits)
    pos = {q: i for i, q in enumerate(reg)}
    # linear part: phase (-1)^(m . L src) -> Z(src) if parity of the m bits it feeds
    for src, outs in val.linear:
        _cond_phase(b, bits, [pos[o] for o in outs], lambda s=src: b.z(s))
    for t in val.terms:
        if not t.xs or not t.ys or not t.outs:
            continue

        def cz(t=t):
            if set(t.xs) == set(t.ys):
                fx, ax = _parity_qubit(b, t.xs, None)
                b.z(fx)
                _unparity(b, t.xs, ax)
                return
            fx, ax = _parity_qubit(b, t.xs, None)
            fy, ay = _parity_qubit(b, t.ys, None)
            b.cz(fx, fy)
            _unparity(b, t.ys, ay)
            _unparity(b, t.xs, ax)
        _cond_phase(b, bits, [pos[o] for o in t.outs], cz)
    b.free(bits)


def _cond_phase(b, bits, idx, apply):
    if not idx:
        return
    if len(idx) == 1:
        c = bits[idx[0]]
        b.push_condition(c)
        apply()
        b.pop_condition()
        return
    c = b.alloc_bits(1)[0]
    b.bit_store(c, False)
    for i in idx:
        b.cx(bits[i], c)
    b.push_condition(c)
    apply()
    b.pop_condition()
    b.free(c)


# ----------------------------------------------------------------------------- the algebra
class Arith:
    def __init__(self, field_gf: km.GF2Field):
        self.gf = field_gf
        self.n = field_gf.degree
        assert self.n == 12, "tower inversion is built for GF(2^12)"
        self.mul_terms = field_mul_terms(12, field_gf.modulus)
        T, cols = tower_isomorphism(field_gf.modulus)
        self.T = T
        self.phi = cols                       # poly -> tower (columns)
        self.phi_inv = invert_linear(cols, 12)
        self.rows_phi = [sum(((cols[k] >> i) & 1) << k for k in range(12)) for i in range(12)]
        self.t8 = field_mul_terms(3, Tower.M8)
        self.t64 = self._extend(self.t8, 3, lambda o: self._mul8_const_mask(o, T.mu))
        self.t4096 = self._extend(self.t64, 6, lambda o: self._mul64_const_mask(o, T.lam))

    # ---- tower multiplication terms as (xmask, ymask, outmask) over tower coordinates
    def _extend(self, sub, n, kappa):
        out = []
        for x, y, o in sub:
            out.append((x, y, o | (o << n)))
            out.append((x << n, y << n, kappa(o)))
            out.append((x | (x << n), y | (y << n), o << n))
        return tuple(out)

    def _linmap_mask(self, f, o, n):
        r = 0
        for i in range(n):
            if (o >> i) & 1:
                r ^= f(1 << i)
        return r

    def _mul8_const_mask(self, o, c):
        return self._linmap_mask(lambda v: self.T.mul8(v, c), o, 3)

    def _mul64_const_mask(self, o, c):
        return self._linmap_mask(lambda v: self.T.mul64(v, c), o, 6)

    # ---- helpers turning masks into qubit lists
    def _zform(self, z, tower_mask):
        """Qubits of z whose parity equals the tower-coordinate form `tower_mask`."""
        m = 0
        for i in range(12):
            if (tower_mask >> i) & 1:
                m ^= self.rows_phi[i]
        return _bits(m, z)

    # ---- multiplication -------------------------------------------------------------
    def mul_value(self, x, y, target) -> Value:
        terms = [Term(_bits(xm, x), _bits(ym, y), _bits(om, target)) for xm, ym, om in self.mul_terms]
        return Value(list(target), [], terms)

    def ixor_mul(self, b, x, y, target, control=None):
        """target ^= x*y (optionally only if control). 54 (+12) Toffolis."""
        if control is None or control is True:
            emit_terms(b, self.mul_value(x, y, target).terms)
            return
        xm = b.alloc_qubits(len(x))
        b.init_and(control, km.array(list(x)), xm)
        emit_terms(b, self.mul_value(xm, y, target).terms)
        b.del_and(control, km.array(list(x)), xm)
        b.free(xm)

    # ---- inversion ------------------------------------------------------------------
    def init_inverse(self, b, z, out=None):
        """out := z^-1 in kickmix's polynomial basis (0 -> 0). Returns (out, record)."""
        T = self.T
        if out is None:
            out = b.alloc_qubits(12)
        N = b.alloc_qubits(6)
        n8 = b.alloc_qubits(3)
        ni = b.alloc_qubits(3)
        Ni = b.alloc_qubits(6)
        vals = []
        # N = a^2 + lam b^2 + a b      (a, b = tower halves of z)
        lin = []
        for i in range(12):                      # tower coordinate i of z
            src_bits_mask = self.rows_phi[i]
            # contribution of coordinate i to N's linear part
            if i < 6:
                img = T.mul64(1 << i, 1 << i)
            else:
                e = 1 << (i - 6)
                img = T.mul64(T.lam, T.mul64(e, e))
            # coordinate i = parity of z bits in src_bits_mask -> XOR each such bit
            for k in range(12):
                if (src_bits_mask >> k) & 1 and img:
                    lin.append((z[k], _bits(img, N)))
        lin = _merge_linear(lin)
        terms = [Term(self._zform(z, xm), self._zform(z, ym << 6), _bits(om, N)) for xm, ym, om in self.t64]
        vN = Value(list(N), lin, terms)
        emit_linear(b, lin); emit_terms(b, terms); vals.append(vN)
        # n = c^2 + mu d^2 + c d   (c, d = GF(8) halves of N)
        lin = []
        for i in range(6):
            if i < 3:
                img = T.mul8(1 << i, 1 << i)
            else:
                e = 1 << (i - 3)
                img = T.mul8(T.mu, T.mul8(e, e))
            lin.append((N[i], _bits(img, n8)))
        lin = _merge_linear(lin)
        terms = [Term(_bits(xm, N[:3]), _bits(ym, N[3:]), _bits(om, n8)) for xm, ym, om in self.t8]
        vn = Value(list(n8), lin, terms)
        emit_linear(b, lin); emit_terms(b, terms); vals.append(vn)
        # ni = n^6 = n^2 * n^4
        S2 = [T.mul8(1 << i, 1 << i) for i in range(3)]          # columns of squaring
        S4 = [T.mul8(c, c) for c in S2]

        def pull(cols, m):   # mask over n such that parity(n & r) == parity((L n) & m)
            r = 0
            for i in range(3):
                if bin(cols[i] & m).count("1") & 1:
                    r |= 1 << i
            return r
        terms = [Term(_bits(pull(S2, xm), n8), _bits(pull(S4, ym), n8), _bits(om, ni)) for xm, ym, om in self.t8]
        vni = Value(list(ni), [], terms)
        emit_terms(b, terms); vals.append(vni)
        # Ni = N^-1 = ((c + d) ni, d ni)
        terms = []
        for xm, ym, om in self.t8:
            cd = [N[i] for i in range(3) if (xm >> i) & 1] + [N[3 + i] for i in range(3) if (xm >> i) & 1]
            terms.append(Term(cd, _bits(ym, ni), _bits(om, Ni[:3])))
            terms.append(Term(_bits(xm, N[3:]), _bits(ym, ni), _bits(om, Ni[3:])))
        vNi = Value(list(Ni), [], terms)
        emit_terms(b, terms); vals.append(vNi)
        # out = phi^-1( (a + b) Ni , b Ni )
        terms = []
        for xm, ym, om in self.t64:
            lo = self._poly_out(om, 0, out)
            hi = self._poly_out(om, 6, out)
            terms.append(Term(self._zform(z, xm | (xm << 6)), _bits(ym, Ni), lo))
            terms.append(Term(self._zform(z, xm << 6), _bits(ym, Ni), hi))
        vout = Value(list(out), [], terms)
        emit_terms(b, terms)
        return out, (vout, list(reversed(vals)), [N, n8, ni, Ni])

    def _poly_out(self, tower_mask_half, shift, out):
        tm = tower_mask_half << shift
        m = 0
        for i in range(12):
            if (tm >> i) & 1:
                m ^= self.phi_inv[i]
        return _bits(m, out)

    def del_inverse(self, b, record, free_out=True):
        vout, vals, regs = record
        mbu_clear(b, vout)
        for v in vals:
            mbu_clear(b, v)
        for r in regs:
            b.free(r)
        if free_out:
            b.free(vout.reg)

    def clear_scaffold(self, b, record):
        """Clear only the inversion scaffold (the output must already be cleared)."""
        _, vals, regs = record
        for v in vals:
            mbu_clear(b, v)
        for r in regs:
            b.free(r)

    # ---- division -------------------------------------------------------------------
    def init_div(self, b, num, den):
        """ratio := num / den (den = 0 -> 0). Returns (ratio, record). 132 Toffolis."""
        inv, rec = self.init_inverse(b, den)
        ratio = b.alloc_qubits(12)
        v = self.mul_value(num, inv, ratio)
        emit_terms(b, v.terms)
        return ratio, (v, inv, rec)

    def del_div(self, b, record):
        v, inv, rec = record
        mbu_clear(b, v)
        b.free(v.reg)
        self.del_inverse(b, rec)


def _merge_linear(lin):
    """Combine (src, outs) pairs with the same source (XOR of output sets)."""
    acc, order = {}, []
    for src, outs in lin:
        if src not in acc:
            acc[src] = set()
            order.append(src)
        acc[src] ^= set(outs)
    return [(s, list(acc[s])) for s in order if acc[s]]
