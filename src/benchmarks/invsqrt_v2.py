"""Benchmark I (invsqrt) rebuilt on the official kickmix builder.

Implements |x>|0> -> exp(2*pi*i / sqrt(x)) |x>|0> for x in [1, 3*(2**10-2)**2]
(np = 10, beta = 1, register "x" of 22 qubits), as specified in arXiv:2610.23832v2 sec. II.A.

Design (no Newton-Raphson step):
  1. normalize in place: s = number of leading zero bit-pairs, stored in BINARY (4 qubits),
     found with 4 "top-k bits are zero" checks (k = 16, 8, 4, 2) and shifted with CSWAPs
     that only touch bits that can be non-zero.  xn = x * 4**s, v = xn / 2**20 in [1, 4).
  2. initial guess *is* the answer: the top A bits of xn select one of 3*2**(A-2) segments,
     a QROM (cheap: ~1 Toffoli per entry, independent of width) outputs per-segment
     coefficients, and a low-degree Horner step in t = (remaining bits) / 2**(22-A)
     evaluates p ~= v**-0.5 to ~2**-27 relative error.
  3. phase: phi = p * 2**(s-10) turns.  The top bits of p are left-shifted by s (binary
     log-shifter, CSWAPs only on possibly-non-zero bits) and every bit gets one Z_POW.
  4. everything except the phase is uncomputed in reverse; QROM via measurement-based
     del_lookup.

All parameters are explicit so they can be swept (see tools/sweep_invsqrt.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

import kickmix as km

NBITS = 22
MAX_X = 3 * (2**10 - 2) ** 2  # 3,133,452


@dataclass(frozen=True)
class Params:
    A: int = 9            # address bits of the coefficient table
    degree: int = 2       # polynomial degree per segment
    F: int = 28           # fractional bits of all polynomial registers
    phase_bits: int = 26  # top bits of p that are phased (p has F+1 bits)
    min_weight: int = 36  # drop rotations whose weight is below 2**-min_weight turns
    max_qubits: int = 130 # >0: cap the builder's width; adders then trade Toffolis for qubits


BEST = Params()
# per-segment c0 nudges found by tools/center_invsqrt.py for BEST (centres the truncation error)
BEST_C0_SHIFT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "invsqrt_v2_c0_shift.npy")


def build_best() -> "km.Circuit":
    """The submitted configuration: exhaustively verified (all x, 3 seeds), Q=130, 2,339 Toffolis."""
    return build(BEST, c0_shift=np.load(BEST_C0_SHIFT))


# --------------------------------------------------------------------------- coefficients
def fit_tables(p: Params):
    """Per segment a: q(t) = c0 - C1 t + C2 t^2 - ...  ~  ((a + t) * 2**(2-A)) ** -0.5."""
    nseg = 1 << p.A
    lo = 1 << (p.A - 2)
    k = np.arange(4 * (p.degree + 1))
    nodes = 0.5 - 0.5 * np.cos(np.pi * (k + 0.5) / len(k))          # Chebyshev nodes in [0,1]
    coeffs = np.zeros((nseg, p.degree + 1))
    for a in range(lo, nseg):
        v = (a + nodes) * 2.0 ** (2 - p.A)
        f = v ** -0.5
        # weighted least squares on Chebyshev nodes ~ minimax relative error
        c = np.polynomial.polynomial.polyfit(nodes, f, p.degree, w=1 / f)
        coeffs[a] = c
    mags = np.abs(coeffs)
    ints = np.round(mags * 2.0**p.F).astype(object)
    for a in range(lo):
        ints[a] = [0] * (p.degree + 1)
    for d in range(1, p.degree + 1):  # sign pattern sanity: + - + - ...
        sgn = np.sign(coeffs[lo:, d])
        assert np.all(sgn == (-1) ** d), f"unexpected sign in coefficient {d}"
    widths = [max(int(v).bit_length() for v in ints[:, d]) for d in range(p.degree + 1)]
    return ints, widths


# --------------------------------------------------------------------------- building blocks
def _norm_stages():
    # (s bit, shift in bits). Applied in this order; s = 8*s3 + 4*s2 + 2*s1 + s0.
    return [(3, 16), (2, 8), (1, 4), (0, 2)]


def _flag_top_zero(b, x, k, flag):
    top = x[NBITS - k:]
    b.x(top)
    b.multi_controlled_x(top, flag)
    b.x(top)


def _shift_left_known_zero(b, ctrl, reg, k, width):
    """reg <<= k if ctrl, given only reg[0:width] can be non-zero. Returns CSWAP list."""
    ops = [(reg[i], reg[i + k]) for i in range(width - 1, -1, -1)]
    for a, c in ops:
        b.cswap(ctrl, a, c)
    return ops


def _mul_rows(b, t_bits, src, dst, sign):
    """dst (+/-)= floor(src * t) with t = sum t_j 2**(j-n), row by row (exact floors)."""
    n = len(t_bits)
    rows = []
    for j in range(n):
        drop = n - j
        if drop >= len(src):
            continue
        # after rows 0..j the partial sum is < src * 2**(j+1-n): it fits in this many bits,
        # so the carry chain never needs to run past them
        width = min(len(dst), len(src) - drop + 1)
        rows.append((t_bits[j], src[drop:], dst[:width]))
    for ctrl, off, tgt in rows:
        (b.iadd if sign > 0 else b.isub)(off, target=tgt, control=ctrl)
    return rows


def _unmul_rows(b, rows, dst, sign):
    for ctrl, off, tgt in reversed(rows):
        (b.isub if sign > 0 else b.iadd)(off, target=tgt, control=ctrl)


# --------------------------------------------------------------------------- circuit
def build(p: Params = Params(), c0_shift=None) -> km.Circuit:
    """c0_shift: optional per-segment integer added to the c0 table (bias centring)."""
    ints, widths = fit_tables(p)
    if c0_shift is not None:
        for a in range(1 << (p.A - 2), 1 << p.A):
            ints[a][0] = int(ints[a][0]) + int(c0_shift[a])
        widths[0] = max(int(v).bit_length() for v in ints[:, 0])
    b = km.CircuitBuilder()
    if p.max_qubits:
        b.set_max_qubits(p.max_qubits)
    x = b.create_quantum_register(NBITS, name="x")
    s = b.alloc_qubits(4)

    # 1. normalize ------------------------------------------------------------
    norm_log = []
    width = NBITS
    for bit, k in _norm_stages():
        _flag_top_zero(b, x, k, s[bit])
        nz = NBITS - k                     # bits that can be non-zero when the flag is set
        norm_log.append((bit, k, _shift_left_known_zero(b, s[bit], x, k, nz)))

    # 2. coefficient lookup + Horner ----------------------------------------------------
    addr = x[NBITS - p.A:]
    t_bits = x[: NBITS - p.A]
    regs = [b.alloc_qubits(w) for w in widths]          # c0, C1, C2, ...
    target = km.array([q for r in regs for q in r])
    table = []
    for a in range(1 << p.A):
        val, off = 0, 0
        for d in range(p.degree + 1):
            val |= int(ints[a][d]) << off
            off += widths[d]
        table.append(val)
    b.init_lookup(table=table, address=addr, target=target)

    horner = []                                         # (k, product register, rows)
    for k in range(p.degree - 1, -1, -1):
        src = regs[k + 1]                               # holds B_{k+1}
        prod = b.alloc_qubits(len(src))
        rows = _mul_rows(b, t_bits, src, prod, +1)
        b.isub(prod, target=regs[k])                    # regs[k] becomes B_k (B_0 = p)
        horner.append((k, prod, rows))

    # 3. phase ---------------------------------------------------------------------------
    pr = regs[0]                                        # p * 2**F, width F+1
    lo_bit = max(0, len(pr) - p.phase_bits)
    nph = len(pr) - lo_bit
    pad = b.alloc_qubits(10)
    win = km.array(list(pr[lo_bit:]) + list(pad))
    shift_log = []
    stages = ((0, 1), (1, 2), (2, 4), (3, 8))
    for n, (bit, k) in enumerate(stages):
        # widest the data can be when this stage fires (s <= 10 limits earlier shifts)
        prior = max(sum(kk for bb, kk in stages[:n] if (sv >> bb) & 1)
                    for sv in range(11) if (sv >> bit) & 1)
        shift_log.append(_shift_left_known_zero(b, s[bit], win, k, nph + prior))
    for m in range(len(win)):
        e = 2 ** (lo_bit + m - p.F - 10)               # weight in turns
        if e >= 1 or e < 2.0 ** -p.min_weight:
            continue
        b.z_pow(win[m], 2 * e)                         # Z_POW exponent is in half turns
    # unshift: replay each stage's CSWAPs in reverse order
    for (bit, _), ops in zip(reversed(((0, 1), (1, 2), (2, 4), (3, 8))), reversed(shift_log)):
        for a, c in reversed(ops):
            b.cswap(s[bit], a, c)
    b.free(pad)

    # 4. uncompute ----------------------------------------------------------------------
    for k, prod, rows in reversed(horner):
        b.iadd(prod, target=regs[k])
        _unmul_rows(b, rows, prod, +1)
        b.free(prod)
    b.del_lookup(table=table, address=addr, target=target)
    for r in regs:
        b.free(r)
    for bit, k, ops in reversed(norm_log):
        for a, c in reversed(ops):
            b.cswap(s[bit], a, c)
        _flag_top_zero(b, x, k, s[bit])
    b.free(s)
    return b.finish_circuit()
