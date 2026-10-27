"""Benchmark II (DQI) decoder with a fixed, data-independent EEA schedule.

The reference (Proos-Zalka synchronized EEA) handles every degenerate case with
quantum-controlled sub-steps: 222 iterations, each sweeping all 73 slots with
controlled multiplications, plus controlled array swaps and shifts.

Here the EEA runs on x^70 and S(x) assuming the *generic* case: every quotient has
degree 1, so step i always turns (r_{i-2}, u_{i-2}) into (r_i, u_i) at classically
known positions. Shots stop being updated (a quantum "alive" flag) once the remainder
degree drops below t = 35, i.e. after k steps for k errors. Degenerate shots (a
quotient of degree >= 2; about 0.6% of the verifier's shots) decode wrongly and are
paid for through the repetition factor R(eps+).

Layout: two arrays of 71 GF(2^12) slots. Array (i mod 2) holds r_i in slots 0..69-i and
u_i reversed in slots 70-i..70 (slot 70-d = u_i[d]); the even array's slots 0..69 *are*
the syndrome registers S0..S69, so r_0 = S needs no copy and u_0 = 1 is one X gate.
Each step is in place: the two top slots freed by r shrinking are exactly the two slots
u grows into.

Step i (T = array i%2 holding (r_{i-2}, u_{i-2}), P = array (i-1)%2 holding (r_{i-1}, u_{i-1})):
    q1 = T[71-i] / P[70-i];  T_r ^= q1 x r_{i-1}
    q0 = T[70-i] / P[70-i];  T_r ^= q0 r_{i-1}
    T_u ^= (q1 x + q0) u_{i-1}
    q1, q0 are cleared by recomputing them from u_i = u_{i-2} + q u_{i-1}
    (q1 = lead(u_i)/lead(u_{i-1}), ...), with measurement-based uncomputation.

Chien search + Forney: sigma = c*u_k, omega = c*r_k (same c), so
e_j = omega(X_j^-1) / sigma'(X_j^-1) needs no normalisation. Per position: zero test of
sigma (11 Toffolis), one inversion (77), one AND (12); the MBUC phase itself is free.

Arithmetic: src/dqi/gf_fast.py (54-Toffoli multiply, 131-Toffoli divide, 77-Toffoli inverse).
"""
from __future__ import annotations

import kickmix as km

from .gf_fast import Arith, mbu_clear, Value, Term

N_SLOTS = 71


class ZeroTest:
    """flag := (reg == 0) with an AND ladder kept for free (MBU) uncomputation. 11 Toffolis."""

    def __init__(self, b, reg):
        self.b, self.reg = b, list(reg)
        b.x(km.array(self.reg))
        self.lad = []
        prev = self.reg[0]
        for q in self.reg[1:]:
            a = b.alloc_qubits(1)[0]
            b.init_and(prev, q, a)
            self.lad.append((prev, q, a))
            prev = a
        self.flag = prev

    def close(self):
        b = self.b
        for prev, q, a in reversed(self.lad):
            b.del_and(prev, q, a)
            b.free(a)
        b.x(km.array(self.reg))


class GenericEEADecoder:
    def __init__(self, n: int = 70, m: int = 4095, degree: int = 12):
        self.n, self.m, self.deg = n, m, degree
        self.t = n // 2
        self.gf = km.GF2Field(degree)
        self.ar = Arith(self.gf)
        self.N = n + 1   # slots per array

    # ------------------------------------------------------------------ helpers
    def _mul_into(self, b, x, y, target):
        self.ar.ixor_mul(b, x, y, target)

    def _ratio_and(self, b, num, den, alive, out, clear):
        """out ^= alive & (num/den); if clear, out is known to hold that value: free clear."""
        ratio, rec = self.ar.init_div(b, num, den)
        if clear:
            b.del_and(alive, ratio, out)
        else:
            b.init_and(alive, ratio, out)
        self.ar.del_div(b, rec)

    def _updates(self, b, i, T, P, q1, q0, part):
        """The XOR-multiply updates of step i (self-inverse)."""
        n = self.n
        if part == "r1":
            for j in range(1, n + 2 - i):              # T[j] ^= q1 * P[j-1]
                self._mul_into(b, q1, P[j - 1], T[j])
        elif part == "r0":
            for j in range(0, n + 1 - i):              # T[j] ^= q0 * P[j]
                self._mul_into(b, q0, P[j], T[j])
        elif part == "u":
            for j in range(n + 1 - i, n + 1):             # u part, q0: T[j] ^= q0 * P[j]
                self._mul_into(b, q0, P[j], T[j])
            for j in range(n - i, n):             # u part, q1: T[j] ^= q1 * P[j+1]
                self._mul_into(b, q1, P[j + 1], T[j])

    def _q0_numerator(self, b, i, T, P, q1):
        """tmp := T[71-i] ^ q1*P[72-i]  (= q0 * lead(u_{i-1}) after the step)."""
        n = self.n
        tmp = b.alloc_qubits(self.deg)
        b.cx(T[n + 1 - i], tmp)
        if n + 2 - i <= n:
            self._mul_into(b, q1, P[n + 2 - i], tmp)
        return tmp

    def _undo_q0_numerator(self, b, i, T, P, q1, tmp):
        n = self.n
        if n + 2 - i <= n:
            self._mul_into(b, q1, P[n + 2 - i], tmp)
        b.cx(T[n + 1 - i], tmp)
        b.free(tmp)

    def _alive_flag(self, b, P, i, prev_alive, a, clear):
        n = self.n
        zt = ZeroTest(b, P[n - i])                  # zt.flag = (lead(r_{i-1}) == 0)
        b.x(zt.flag)
        if prev_alive is None:
            b.cx(zt.flag, a)                         # first step: alive = (S69 != 0)
        elif clear:
            b.del_and(prev_alive, zt.flag, a)
        else:
            b.init_and(prev_alive, zt.flag, a)
        b.x(zt.flag)
        zt.close()

    # ------------------------------------------------------------------ one EEA step
    def step(self, b, i, arrays, alive, forward=True):
        n = self.n
        T, P = arrays[i % 2], arrays[(i - 1) % 2]
        prev = alive[i - 2] if i >= 2 else None
        a = alive[i - 1]
        d = self.deg
        if forward:
            self._alive_flag(b, P, i, prev, a, clear=False)
            q1 = b.alloc_qubits(d)
            self._ratio_and(b, T[n + 1 - i], P[n - i], a, q1, clear=False)
            self._updates(b, i, T, P, q1, None, "r1")
            q0 = b.alloc_qubits(d)
            self._ratio_and(b, T[n - i], P[n - i], a, q0, clear=False)
            self._updates(b, i, T, P, q1, q0, "r0")
            self._updates(b, i, T, P, q1, q0, "u")
            # clear q0 then q1 from the new state
            tmp = self._q0_numerator(b, i, T, P, q1)
            self._ratio_and(b, tmp, P[n + 1 - i], a, q0, clear=True)
            self._undo_q0_numerator(b, i, T, P, q1, tmp)
            b.free(q0)
            self._ratio_and(b, T[n - i], P[n + 1 - i], a, q1, clear=True)
            b.free(q1)
        else:
            q1 = b.alloc_qubits(d)
            self._ratio_and(b, T[n - i], P[n + 1 - i], a, q1, clear=False)
            q0 = b.alloc_qubits(d)
            tmp = self._q0_numerator(b, i, T, P, q1)
            self._ratio_and(b, tmp, P[n + 1 - i], a, q0, clear=False)
            self._undo_q0_numerator(b, i, T, P, q1, tmp)
            self._updates(b, i, T, P, q1, q0, "u")
            self._updates(b, i, T, P, q1, q0, "r0")
            self._ratio_and(b, T[n - i], P[n - i], a, q0, clear=True)
            b.free(q0)
            self._updates(b, i, T, P, q1, None, "r1")
            self._ratio_and(b, T[n + 1 - i], P[n - i], a, q1, clear=True)
            b.free(q1)
            self._alive_flag(b, P, i, prev, a, clear=True)

    # ------------------------------------------------------------------ Chien + Forney
    def chien_forney(self, b, A, E):
        n = self.n
        gf, d = self.gf, self.deg
        t = self.t
        alpha = gf.primitive_element
        sig = [A[n - k] for k in range(t + 1)]          # sigma_k, k = 0..35
        om = [A[k] for k in range(t)]                     # omega_k, k = 0..34
        sig_step = [gf.pow(alpha, (-k) % (2**d - 1)) for k in range(t + 1)]
        om_step = [gf.pow(alpha, (-(k + 1)) % (2**d - 1)) for k in range(t)]
        is_err = b.alloc_bits(1)
        for j in range(self.m):
            b.bit_store(is_err[0], True, control=E[j])
            b.push_condition(is_err[0])
            sv = b.alloc_qubits(d); so = b.alloc_qubits(d); wv = b.alloc_qubits(d)
            acc = [(s, sv) for s in sig] + [(sig[k], so) for k in range(1, t + 1, 2)] + [(w, wv) for w in om]
            src = km.array([q for s, _ in acc for q in s]); dst = km.array([q for _, t_ in acc for q in t_])
            b.cx(src, dst)
            zt = ZeroTest(b, sv)
            inv, rec = self.ar.init_inverse(b, so)
            loc = b.alloc_qubits(d)
            b.init_and(zt.flag, wv, loc)
            b.gf2_phase_by_product(loc, inv, mask=E[j], field=gf)
            b.del_and(zt.flag, wv, loc)
            b.free(loc)
            self.ar.del_inverse(b, rec)
            zt.close()
            b.cx(src, dst)
            b.free(sv); b.free(so); b.free(wv)
            b.pop_condition()
            b.bit_store(is_err[0], False)
            for k in range(t + 1):
                if sig_step[k] != 1:
                    b.gf2_imul(sig_step[k], target=sig[k], field=gf)
            for k in range(t):
                b.gf2_imul(om_step[k], target=om[k], field=gf)
        b.free(is_err)
        order = 2**d - 1
        if self.m % order:                       # undo the leftover evaluation-point shift
            for k in range(t + 1):
                if sig_step[k] != 1:
                    b.gf2_idiv(gf.pow(sig_step[k], self.m % order), target=sig[k], field=gf)
            for k in range(t):
                b.gf2_idiv(gf.pow(om_step[k], self.m % order), target=om[k], field=gf)

    # ------------------------------------------------------------------ full circuit
    def build(self) -> km.Circuit:
        n = self.n
        b = km.CircuitBuilder()
        d = self.deg
        S = [b.create_quantum_register(d, name=f"S{i}") for i in range(self.n)]
        E = [b.create_classical_register(d, name=f"E{j}") for j in range(self.m)]
        even = list(S) + [b.alloc_qubits(d)]
        odd = [b.alloc_qubits(d) for _ in range(self.N)]
        arrays = [even, odd]
        b.x(even[n][0])              # u_0 = 1
        b.x(odd[n][0])               # r_{-1} = x^70
        alive = [b.alloc_qubits(1)[0] for _ in range(self.t)]
        with b.mark("eea_forward"):
            for i in range(1, self.t + 1):
                self.step(b, i, arrays, alive, forward=True)
        # sigma lives in array (k mod 2); k = number of alive steps
        par = b.alloc_qubits(1)[0]
        for a in alive:
            b.cx(a, par)
        swap_src = km.array([q for s in even for q in s]); swap_dst = km.array([q for s in odd for q in s])
        b.cswap(par, swap_src, swap_dst)
        with b.mark("chien_forney"):
            self.chien_forney(b, even, E)
        b.cswap(par, swap_src, swap_dst)
        for a in alive:
            b.cx(a, par)
        b.free(par)
        with b.mark("eea_reverse"):
            for i in range(self.t, 0, -1):
                self.step(b, i, arrays, alive, forward=False)
        b.x(odd[n][0]); b.x(even[n][0])
        b.free(alive)
        b.free(even[n])
        for s in odd:
            b.free(s)
        return b.finish_circuit()


def build_circuit(**kw) -> km.Circuit:
    return GenericEEADecoder(**kw).build()
