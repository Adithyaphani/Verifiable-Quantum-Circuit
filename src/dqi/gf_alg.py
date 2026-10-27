"""Classical algebra for cheap reversible GF(2^12) arithmetic (no kickmix needed).

* Bilinear multiplication algorithms: Karatsuba over GF(2) polynomials. A product
  is a list of terms (xmask, ymask, outmask): z ^= outmask whenever
  parity(x & xmask) and parity(y & ymask). One AND (Toffoli) per term.
  12x12 bits -> 54 terms (vs 63 in kickmix's ixor_gf2_mul).
* A tower representation GF(((2^3)^2)^2) with an explicit GF(2)-linear isomorphism
  to kickmix's polynomial basis, used for a 78-AND inversion (vs 315).
"""
from __future__ import annotations

from functools import lru_cache


def parity(v: int) -> int:
    return bin(v).count("1") & 1


# ----------------------------------------------------------------------------- Karatsuba
@lru_cache(None)
def karatsuba_terms(n: int) -> tuple:
    """Bilinear algorithm for the product of two degree-(n-1) GF(2) polynomials.

    Returns terms (xmask, ymask, outmask) with masks over n input bits and 2n-1 output bits.
    """
    if n == 1:
        return ((1, 1, 1),)
    if n == 2:
        # a0b0, a1b1, (a0+a1)(b0+b1): z0=p0, z2=p1, z1=p0+p1+p2
        return ((1, 1, 0b011), (2, 2, 0b110), (3, 3, 0b010))
    if n == 3:
        # 6-multiplication formula
        t = []
        t.append((1, 1, None))   # a0b0
        t.append((2, 2, None))   # a1b1
        t.append((4, 4, None))   # a2b2
        t.append((3, 3, None))   # (a0+a1)(b0+b1)
        t.append((5, 5, None))   # (a0+a2)(b0+b2)
        t.append((6, 6, None))   # (a1+a2)(b1+b2)
        # z0 = p00 ; z1 = p01 + p00 + p11 ; z2 = p02 + p00 + p22 + p11 ; z3 = p12 + p11 + p22 ; z4 = p22
        out = [0] * 6
        def add(term, k): out[term] ^= 1 << k
        add(0, 0)
        for tm in (3, 0, 1): add(tm, 1)
        for tm in (4, 0, 2, 1): add(tm, 2)
        for tm in (5, 1, 2): add(tm, 3)
        add(2, 4)
        return tuple((x, y, o) for (x, y, _), o in zip(t, out))
    # split
    h = (n + 1) // 2 if n % 2 else n // 2
    lo, hi = h, n - h
    assert hi <= lo
    inner = karatsuba_terms(lo)
    inner_hi = karatsuba_terms(hi)
    terms = []
    mlo = (1 << lo) - 1

    def shift_out(o, s):
        return o << s

    # P0 = X0*Y0 (deg 2lo-2) at shift 0 ; P2 = X1*Y1 at shift 2h ; P1=(X0+X1)(Y0+Y1) at shift h
    # Z = P0 + (P1 + P0 + P2) z^h + P2 z^2h
    for x, y, o in inner:
        terms.append((x, y, shift_out(o, 0) ^ shift_out(o, h)))
    for x, y, o in inner_hi:
        terms.append((x << h, y << h, shift_out(o, 2 * h) ^ shift_out(o, h)))
    for x, y, o in inner:
        # (X0 + X1): bit i of the sum is x0_i + x1_i (x1_i absent if i >= hi)
        def lift(m):
            v = 0
            for i in range(lo):
                if (m >> i) & 1:
                    v |= 1 << i
                    if i < hi:
                        v |= 1 << (i + h)
            return v
        terms.append((lift(x), lift(y), shift_out(o, h)))
    return tuple(terms)


def poly_mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        b >>= 1
    return r


def poly_mod(a: int, mod: int) -> int:
    d = mod.bit_length() - 1
    while a.bit_length() - 1 >= d:
        a ^= mod << (a.bit_length() - 1 - d)
    return a


def field_mul_terms(nbits: int, modulus: int) -> tuple:
    """Bilinear algorithm for multiplication in GF(2)[x]/modulus (poly basis)."""
    red = [poly_mod(1 << k, modulus) for k in range(2 * nbits - 1)]
    out = []
    for x, y, o in karatsuba_terms(nbits):
        v = 0
        for k in range(2 * nbits - 1):
            if (o >> k) & 1:
                v ^= red[k]
        if v:
            out.append((x, y, v))
    return tuple(out)


def apply_terms(terms, x: int, y: int) -> int:
    z = 0
    for xm, ym, om in terms:
        if parity(x & xm) and parity(y & ym):
            z ^= om
    return z


# ----------------------------------------------------------------------------- tower field
class Tower:
    """GF(8) = GF(2)[y]/(y^3+y+1); GF(64) = GF(8)[z]/(z^2+z+mu); GF(4096) = GF(64)[w]/(w^2+w+lam).

    Element encodings (ints): GF(8): 3 bits; GF(64): c | d<<3 means c + d z;
    GF(4096): a | b<<6 means a + b w.
    """
    M8 = 0b1011

    def __init__(self):
        self.mu = next(m for m in range(1, 8) if all(self.mul8(r, r) ^ r ^ m for r in range(8)))
        self.lam = next(l for l in range(1, 64) if all(self.mul64(r, r) ^ r ^ l for r in range(64)))

    def mul8(self, a, b):
        return poly_mod(poly_mul(a, b), self.M8)

    def mul64(self, u, v):
        c, d, e, f = u & 7, u >> 3, v & 7, v >> 3
        ce, df = self.mul8(c, e), self.mul8(d, f)
        lo = ce ^ self.mul8(self.mu, df)
        hi = self.mul8(c ^ d, e ^ f) ^ ce
        return lo | (hi << 3)

    def mul4096(self, u, v):
        a, b, c, d = u & 63, u >> 6, v & 63, v >> 6
        ac, bd = self.mul64(a, c), self.mul64(b, d)
        lo = ac ^ self.mul64(self.lam, bd)
        hi = self.mul64(a ^ b, c ^ d) ^ ac
        return lo | (hi << 6)


def gf_pow(mul, x, e, one=1):
    r = one
    while e:
        if e & 1:
            r = mul(r, x)
        x = mul(x, x)
        e >>= 1
    return r


def tower_isomorphism(modulus: int):
    """Linear map (list of 12 column ints) sending poly-basis alpha^k to tower root^k."""
    T = Tower()
    deg = modulus.bit_length() - 1
    for r in range(2, 4096):
        acc, ok = 0, True
        # evaluate modulus at r
        val, p = 0, 1
        for k in range(deg + 1):
            if (modulus >> k) & 1:
                val ^= p
            p = T.mul4096(p, r)
        if val == 0:
            cols = []
            p = 1
            for k in range(deg):
                cols.append(p)
                p = T.mul4096(p, r)
            return T, cols
    raise ValueError("no root")


def apply_linear(cols, v: int) -> int:
    out = 0
    for k, c in enumerate(cols):
        if (v >> k) & 1:
            out ^= c
    return out


def invert_linear(cols, n: int):
    """Columns of the inverse GF(2) matrix."""
    # rows-as-ints gaussian elimination on augmented [A | I]
    rows = []
    for i in range(n):
        r = 0
        for k, c in enumerate(cols):
            if (c >> i) & 1:
                r |= 1 << k
        rows.append(r | (1 << (n + i)))
    for col in range(n):
        piv = next(i for i in range(col, n) if (rows[i] >> col) & 1)
        rows[col], rows[piv] = rows[piv], rows[col]
        for i in range(n):
            if i != col and (rows[i] >> col) & 1:
                rows[i] ^= rows[col]
    inv_rows = [r >> n for r in rows]       # row i of the inverse
    return [sum(((inv_rows[i] >> k) & 1) << i for i in range(n)) for k in range(n)]
