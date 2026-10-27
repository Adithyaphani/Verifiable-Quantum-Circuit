"""Benchmark II (DQI) decoder: generic-schedule EEA with the syndrome as a shrinking window.

GenericEEADecoder keeps both remainder/cofactor pairs (r_{i-1}, u_{i-1}) and (r_i, u_i)
explicitly: 142 GF(2^12) slots. Here the remainders are never stored. With
r_i = u_i * S mod x^70 every coefficient the schedule needs is a dot product of a
cofactor with a window of the syndrome, and the syndrome itself is consumed from the
top:

  * step i needs only r_{i-1}[70-i], r_{i-1}[69-i] (computed, carried to step i+1 as
    r_{(i+1)-2}'s top pair) and S_0..S_{70-i};
  * after step i the coefficient S_{71-i} is no longer read. The known zero
    (u S)_{71-i} = 0 (deg r_i, r_{i-1} < 71-i) gives S_{71-i} = D / u[0] for u = u_i, or
    for u = u_{i-1} when u_i[0] = 0 (they never vanish together), so it is XORed to 0
    and its slot hosts the next cofactor coefficient.

Live data: S_0..S_{70-i} plus u_{i-1}, u_i plus 2 carried coefficients, i.e. about
74 + i slots instead of 142. Dead steps (after the last error) still eliminate, using
sigma = u_k ((sigma S)_q = 0 for k <= q <= 69), which sits in the array of parity k.
omega = sigma S mod x^35 is then formed in place from S_0..S_34, and Chien/Forney runs
on (sigma, omega). Degenerate shots (a quotient of degree 2, ~0.9%) decode wrongly, as
in GenericEEADecoder; about half of them still get the right phase.

Measured: Q = 1408, T = 952k (GenericEEADecoderLean: Q = 1780, T = 985k).

Everything is mirrored by an explicit reverse pass, so S and all workspace are restored.
"""
from __future__ import annotations

import kickmix as km

from .generic_eea import ZeroTest
from .gf_fast import Arith, Term, Value, emit_linear, emit_terms, mbu_clear, _bits

N_SYN = 70


class WindowEEADecoder:
    KBITS = 6

    def __init__(self, n: int = 70, m: int = 4095, degree: int = 12):
        self.n, self.m, self.d = n, m, degree
        self.t = n // 2
        self.gf = km.GF2Field(degree)
        self.ar = Arith(self.gf)

    # ------------------------------------------------------------------ arithmetic helpers
    def dot_value(self, b, pairs, target):
        """Value for target ^= sum x*y over pairs (x, y): each x, y a list of 12 per-bit forms."""
        terms = []
        for xf, yf in pairs:
            for xm, ym, om in self.ar.mul_terms:
                xs = [q for i in range(self.d) if (xm >> i) & 1 for q in xf[i]]
                ys = [q for i in range(self.d) if (ym >> i) & 1 for q in yf[i]]
                terms.append(Term(xs, ys, _bits(om, target)))
        return Value(list(target), [], terms)

    @staticmethod
    def F(reg):
        """Per-bit forms of a plain register."""
        return [[q] for q in reg]

    @staticmethod
    def F2(r1, r2):
        return [[a, c] for a, c in zip(r1, r2)]

    def emit(self, b, v):
        emit_linear(b, v.linear)
        emit_terms(b, v.terms)

    # ------------------------------------------------------------------ layout
    def _layout(self, b):
        """Static slot map. X[p][j] = slot of cofactor coefficient j in array p."""
        n = self.n
        self.X = [[None] * (self.t + 1) for _ in range(2)]
        fresh = lambda: b.alloc_qubits(self.d)  # noqa: E731
        self.X[0][0] = fresh()
        self.spare_after = {}
        for i in range(1, self.t + 1):
            p = i % 2
            self.X[p][i - 1] = fresh()
            if i <= 2:
                self.X[p][i] = fresh()
            else:
                self.X[p][i] = self.S[72 - i]        # S_{72-i}, eliminated at step i-1
        self.X[0][self.t] = self.S[36]               # 0 after the loop (eliminated at step t)

    # ------------------------------------------------------------------ one step
    def _cd_value(self, i, P, c, d):
        """c := r_{i-1}[70-i], d := r_{i-1}[69-i] with r_{i-1} = u_{i-1} S (P = u_{i-1})."""
        S = self.S
        if i == 1:
            vc = Value(list(c), [(S[69][k], [c[k]]) for k in range(self.d)], [])
            vd = Value(list(d), [(S[68][k], [d[k]]) for k in range(self.d)], [])
            return vc, vd
        vc = self.dot_value(None, [(self.F(P[l]), self.F(S[70 - i - l])) for l in range(i)], c)
        vd = self.dot_value(None, [(self.F(P[l]), self.F(S[69 - i - l])) for l in range(i)], d)
        return vc, vd

    def _alive(self, b, i, K, c, a, clear):
        eq = b.alloc_qubits(1)[0]
        b.flip_if_equal(K, i - 1, target=eq)
        zt = ZeroTest(b, c)
        b.x(zt.flag)
        if clear:
            b.del_and(eq, zt.flag, a)
        else:
            b.init_and(eq, zt.flag, a)
        b.x(zt.flag)
        zt.close()
        b.flip_if_equal(K, i - 1, target=eq)
        b.free(eq)

    def _ratio_into(self, b, num_forms, inv, ctrl, out, clear):
        """out ^= ctrl & (num * inv); clear=True when out already holds it (MBU)."""
        ratio = b.alloc_qubits(self.d)
        v = self.dot_value(b, [(num_forms, self.F(inv))], ratio)
        emit_terms(b, v.terms)
        if clear:
            b.del_and(ctrl, ratio, out)
        else:
            b.init_and(ctrl, ratio, out)
        mbu_clear(b, v)
        b.free(ratio)

    def _q(self, b, i, a, c, d, carry, q1, q0, clear, vd=None):
        """q1 = ca / c, q0 = (cb + q1 d) / c, ANDed with a.

        Forward (clear=False): computes q1, q0 and consumes the old carry (ca, cb are
        MBU-cleared; they are still functions of u_{i-2} and S). Reverse (clear=True):
        MBU-clears q0, q1 and leaves the recomputed carry in place.
        """
        ca, cb, vca, vcb = carry
        inv, rec = self.ar.init_inverse(b, c)

        def top(clr):
            if i == 1:      # ca = 1
                (b.del_and if clr else b.init_and)(a, inv, q1)
            else:
                self._ratio_into(b, self.F(ca), inv, a, q1, clr)

        def low(clr):
            if i == 1:      # cb = 0: numerator q1 d in a fresh register
                nm = b.alloc_qubits(self.d)
                vn = self.dot_value(b, [(self.F(q1), self.F(d))], nm)
                emit_terms(b, vn.terms)
                self._ratio_into(b, self.F(nm), inv, a, q0, clr)
                mbu_clear(b, vn)
                b.free(nm)
                return
            vn = self.dot_value(b, [(self.F(q1), self.F(d))], cb)
            emit_terms(b, vn.terms)                   # cb := cb + q1 d
            self._ratio_into(b, self.F(cb), inv, a, q0, clr)
            if clear:
                emit_terms(b, vn.terms)               # restore cb (it is the next carry)
            else:
                mbu_clear(b, Value(list(cb), list(vcb.linear), list(vcb.terms) + list(vn.terms)))
                b.free(cb)

        if clear:
            low(True)
            b.free(q0)
            if i >= 2:                                # ca only now: lower qubit peak
                ca = b.alloc_qubits(self.d)
                vca, _ = self._cd_value(i - 1, self.X[i % 2], ca, cb)
                self.emit(b, vca)
                carry[0] = ca
                carry[2] = vca
            top(True)
        else:
            top(False)
            if i >= 2:
                mbu_clear(b, vca)
                b.free(ca)
            self.emit(b, vd)                          # d only now: lower qubit peak
            q0.extend(b.alloc_qubits(self.d))
            low(False)
        self.ar.del_inverse(b, rec)

    def _u_update(self, b, i, T, P, q1, q0):
        """T := u_{i-2} + (q1 x + q0) u_{i-1} (self-inverse)."""
        if i == 1:     # u_{-1} = 0, u_0 = 1
            b.cx(q1, T[1])
            b.cx(q0, T[0])
            return
        for j in range(i):
            self.ar.ixor_mul(b, q1, P[j], T[j + 1])
            self.ar.ixor_mul(b, q0, P[j], T[j])

    def _q_from_u(self, b, i, a, T, P, q1, q0, clear):
        """Recompute (clear=False) or MBU-clear (clear=True) q1, q0 from u_i = T, u_{i-1} = P."""
        if i == 1:
            b.cx(T[1], q1)
            b.cx(T[0], q0)
            return
        inv, rec = self.ar.init_inverse(b, P[i - 1])
        order = ("q0", "q1") if clear else ("q1", "q0")
        for which in order:
            if which == "q1":
                self._ratio_into(b, self.F(T[i]), inv, a, q1, clear)
            else:
                if i >= 2:
                    self.ar.ixor_mul(b, q1, P[i - 2], T[i - 1])
                self._ratio_into(b, self.F(T[i - 1]), inv, a, q0, clear)
                if i >= 2:
                    self.ar.ixor_mul(b, q1, P[i - 2], T[i - 1])
        self.ar.del_inverse(b, rec)

    def _elim_gates(self, b, i, a, T, h0, h1):
        """h0 ^= use u_i (T), h1 ^= use u_{i-1} (P) for eliminating S_{71-i} (self-inverse).

        Alive step: T unless T[0] == 0. Dead step: whichever array holds sigma = u_k,
        i.e. T iff K = i mod 2 (K = k is frozen); (sigma S)_q = 0 for k <= q <= 69.
        """
        K = self.K
        zt = ZeroTest(b, T[0])             # flag = (u_i[0] == 0); T[0] is flipped while open
        b.ccx(a, zt.flag, h1)
        b.x(zt.flag)
        b.ccx(a, zt.flag, h0)
        b.x(zt.flag)
        zt.close()
        b.x(a)
        if i % 2 == 0:
            b.x(K[0])
        b.ccx(a, K[0], h0)                 # dead and K = i mod 2
        b.x(K[0])
        b.ccx(a, K[0], h1)                 # dead and K != i mod 2
        if i % 2 == 1:
            b.x(K[0])
        b.x(a)

    def _eliminate(self, b, i, a, T, P):
        """S_{71-i} ^= a & (D/u[0]) with u = u_i, or u_{i-1} when u_i[0] == 0 (self-inverse)."""
        S, d = self.S, self.d
        tgt = S[71 - i]
        h0 = b.alloc_qubits(1)[0]
        h1 = b.alloc_qubits(1)[0]
        self._elim_gates(b, i, a, T, h0, h1)
        for U, deg, h in ((T, i, h0), (P, i - 1, h1)):
            D = b.alloc_qubits(d)
            vD = self.dot_value(b, [(self.F(U[l]), self.F(S[71 - i - l])) for l in range(1, deg + 1)], D)
            emit_terms(b, vD.terms)
            inv, rec = self.ar.init_inverse(b, U[0])
            ratio = b.alloc_qubits(d)
            vr = self.dot_value(b, [(self.F(D), self.F(inv))], ratio)
            emit_terms(b, vr.terms)
            b.ccx(h, ratio, tgt)
            mbu_clear(b, vr)
            b.free(ratio)
            self.ar.del_inverse(b, rec)
            mbu_clear(b, vD)
            b.free(D)
        self._elim_gates(b, i, a, T, h0, h1)
        b.free(h0)
        b.free(h1)

    def step_forward(self, b, i, K, carry):
        """carry = (ca, cb, vca, vcb) = r_{i-2}'s top pair; returns the new carry."""
        d = self.d
        p = i % 2
        T, P = self.X[p], self.X[1 - p]
        ca, cb, vca, vcb = carry
        c = b.alloc_qubits(d)
        dd = b.alloc_qubits(d)
        vc, vd = self._cd_value(i, P, c, dd)
        self.emit(b, vc)
        a = b.alloc_qubits(1)[0]
        self._alive(b, i, K, c, a, clear=False)
        q1 = b.alloc_qubits(d)
        q0 = []                               # allocated inside _q, after ca is cleared
        self._q(b, i, a, c, dd, carry, q1, q0, clear=False, vd=vd)
        q0 = km.array(q0)
        self._u_update(b, i, T, P, q1, q0)
        self._q_from_u(b, i, a, T, P, q1, q0, clear=True)
        b.free(q1)
        b.free(q0)
        if i >= 2:
            self._eliminate(b, i, a, T, P)
        b.iadd(1, target=K, control=a)
        b.flip_if_equal(K, i, target=a)
        b.free(a)
        return (c, dd, vc, vd)

    def step_reverse(self, b, i, K, carry):
        """Inverse of step_forward; carry = this step's (c, d, vc, vd); returns step i-1's."""
        d = self.d
        p = i % 2
        T, P = self.X[p], self.X[1 - p]
        c, dd, vc, vd = carry
        a = b.alloc_qubits(1)[0]
        b.flip_if_equal(K, i, target=a)
        b.isub(1, target=K, control=a)
        if i >= 2:
            self._eliminate(b, i, a, T, P)
        q1 = b.alloc_qubits(d)
        q0 = b.alloc_qubits(d)
        self._q_from_u(b, i, a, T, P, q1, q0, clear=False)
        self._u_update(b, i, T, P, q1, q0)
        if i >= 2:                           # recompute r_{i-2}'s top pair (ca inside _q)
            cb = b.alloc_qubits(d)
            _, vcb = self._cd_value(i - 1, T, cb, cb)
            self.emit(b, vcb)
            prev = [None, cb, None, vcb]
        else:
            ca = cb = None
            prev = (None, None, None, None)
        self._q(b, i, a, c, dd, prev, q1, q0, clear=True)
        b.free(q1)
        self._alive(b, i, K, c, a, clear=True)
        b.free(a)
        mbu_clear(b, vc)
        mbu_clear(b, vd)
        b.free(c)
        b.free(dd)
        return tuple(prev)

    # ------------------------------------------------------------------ after the loop
    def omega_forward(self, b, inv0):
        """omega_p = (sigma S)_p for p = 34..0, built in place; returns omega's slots."""
        d = self.d
        A, S = self.X[0], self.S
        om = [None] * self.t
        w = b.alloc_qubits(d)
        for p in range(self.t - 1, -1, -1):
            D = b.alloc_qubits(d)
            vD = self.dot_value(b, [(self.F(A[l]), self.F(S[p - l])) for l in range(1, p + 1)], D)
            emit_terms(b, vD.terms)
            vw = self.dot_value(b, [(self.F(A[0]), self.F(S[p]))], w)
            emit_terms(b, vw.terms)
            b.cx(D, w)
            self.ar.ixor_mul(b, inv0, w, S[p])
            self.ar.ixor_mul(b, inv0, D, S[p])
            mbu_clear(b, vD)
            b.free(D)
            om[p] = w
            w = S[p]                          # now 0: hosts the next coefficient
        self.om_spare = w
        return om

    def omega_reverse(self, b, inv0, om):
        A, S, d = self.X[0], self.S, self.d
        for p in range(self.t):
            w = om[p]
            D = b.alloc_qubits(d)
            vD = self.dot_value(b, [(self.F(A[l]), self.F(S[p - l])) for l in range(1, p + 1)], D)
            emit_terms(b, vD.terms)
            self.ar.ixor_mul(b, inv0, D, S[p])
            self.ar.ixor_mul(b, inv0, w, S[p])
            b.cx(D, w)
            vw = self.dot_value(b, [(self.F(A[0]), self.F(S[p]))], w)
            mbu_clear(b, vw)
            mbu_clear(b, vD)
            b.free(D)
        b.free(om[self.t - 1])

    # ------------------------------------------------------------------ Chien + Forney
    def chien_forney(self, b, sig, om, E):
        gf, d, t = self.gf, self.d, self.t
        alpha = gf.primitive_element
        order = 2**d - 1
        sig_step = [gf.pow(alpha, (-k) % order) for k in range(t + 1)]
        om_step = [gf.pow(alpha, (-(k + 1)) % order) for k in range(t)]
        s0_src = km.array([q for k in range(1, t + 1) for q in sig[k]])
        s0_dst = km.array([q for k in range(1, t + 1) for q in sig[0]])
        s1_src = km.array([q for k in range(3, t + 1, 2) for q in sig[k]])
        s1_dst = km.array([q for k in range(3, t + 1, 2) for q in sig[1]])
        w_src = km.array([q for k in range(1, t) for q in om[k]])
        w_dst = km.array([q for k in range(1, t) for q in om[0]])
        is_err = b.alloc_bits(1)
        for j in range(self.m):
            b.bit_store(is_err[0], True, control=E[j])
            b.push_condition(is_err[0])
            b.cx(s0_src, s0_dst)
            b.cx(s1_src, s1_dst)
            b.cx(w_src, w_dst)
            zt = ZeroTest(b, sig[0])
            inv, rec = self.ar.init_inverse(b, sig[1])
            loc = b.alloc_qubits(d)
            b.init_and(zt.flag, om[0], loc)
            b.gf2_phase_by_product(loc, inv, mask=E[j], field=gf)
            b.del_and(zt.flag, om[0], loc)
            b.free(loc)
            self.ar.del_inverse(b, rec)
            zt.close()
            b.cx(w_src, w_dst)
            b.cx(s1_src, s1_dst)
            b.cx(s0_src, s0_dst)
            b.pop_condition()
            b.bit_store(is_err[0], False)
            for k in range(t + 1):
                if sig_step[k] != 1:
                    b.gf2_imul(sig_step[k], target=sig[k], field=gf)
            for k in range(t):
                b.gf2_imul(om_step[k], target=om[k], field=gf)
        b.free(is_err)
        if self.m % order:
            for k in range(t + 1):
                if sig_step[k] != 1:
                    b.gf2_idiv(gf.pow(sig_step[k], self.m % order), target=sig[k], field=gf)
            for k in range(t):
                b.gf2_idiv(gf.pow(om_step[k], self.m % order), target=om[k], field=gf)

    # ------------------------------------------------------------------ full circuit
    def build(self, chien=True) -> km.Circuit:
        d = self.d
        b = km.CircuitBuilder()
        self.S = [b.create_quantum_register(d, name=f"S{i}") for i in range(self.n)]
        E = [b.create_classical_register(d, name=f"E{j}") for j in range(self.m)]
        self._layout(b)
        X = self.X
        b.x(X[0][0][0])                      # u_0 = 1
        K = b.alloc_qubits(self.KBITS)
        self.K = K
        carry = (None, None, None, None)
        with b.mark("eea_forward"):
            for i in range(1, self.t + 1):
                carry = self.step_forward(b, i, K, carry)
            c, dd, vc, vd = carry
            mbu_clear(b, vc)
            mbu_clear(b, vd)
            b.free(c)
            b.free(dd)
        src = km.array([q for s in X[0] for q in s])
        dst = km.array([q for s in X[1] for q in s])
        b.cswap(K[0], src, dst)              # X[0] := sigma = u_k
        inv0, rec0 = self.ar.init_inverse(b, X[0][0])
        with b.mark("post"):
            om = self.omega_forward(b, inv0)
        if chien:
            with b.mark("chien_forney"):
                self.chien_forney(b, X[0], om, E)
        with b.mark("post_reverse"):
            self.omega_reverse(b, inv0, om)
        self.ar.del_inverse(b, rec0)
        b.cswap(K[0], src, dst)
        with b.mark("eea_reverse"):
            c = b.alloc_qubits(d)
            dd = b.alloc_qubits(d)
            vc, vd = self._cd_value(self.t, X[(self.t - 1) % 2], c, dd)
            self.emit(b, vc)
            self.emit(b, vd)
            carry = (c, dd, vc, vd)
            for i in range(self.t, 0, -1):
                carry = self.step_reverse(b, i, K, carry)
        b.x(X[0][0][0])
        b.free(K)
        seen = {id(s) for s in self.S}
        for p in range(2):
            for s in X[p]:
                if id(s) not in seen:
                    seen.add(id(s))
                    b.free(s)
        return b.finish_circuit()
