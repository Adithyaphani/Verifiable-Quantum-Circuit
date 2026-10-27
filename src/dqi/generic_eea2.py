"""Generic-schedule DQI decoder, qubit-lean version (see generic_eea.py for the algorithm).

Changes vs GenericEEADecoder:
  * the 35 per-step "alive" flags are replaced by a 6-bit counter K of executed steps
    (alive at step i  <=>  K == i-1 and lead(r_{i-1}) != 0); K's low bit is the parity
    used to pick sigma's array;
  * the q0-recovery numerator is formed in place in T[n+1-i];
  * Chien/Forney accumulate sigma(x), sigma_odd(x), omega(x) in place into
    sigma_0, sigma_1, omega_0 instead of three fresh registers.
"""
from __future__ import annotations

import kickmix as km

from .generic_eea import GenericEEADecoder, ZeroTest


from .gf_fast import emit_terms, mbu_clear


class GenericEEADecoderLean(GenericEEADecoder):
    KBITS = 6

    def _ratio_and_inv(self, b, num, inv, alive, out, clear):
        """out ^= alive & (num * inv), with inv = 1/den already computed (54 + 12 Toffolis)."""
        ratio = b.alloc_qubits(self.deg)
        v = self.ar.mul_value(num, inv, ratio)
        emit_terms(b, v.terms)
        if clear:
            b.del_and(alive, ratio, out)
        else:
            b.init_and(alive, ratio, out)
        mbu_clear(b, v)
        b.free(ratio)

    # -- in-place numerator for clearing q0
    def _q0_num_inplace(self, b, i, T, P, q1):
        n = self.n
        if n + 2 - i <= n:
            self._mul_into(b, q1, P[n + 2 - i], T[n + 1 - i])
        return T[n + 1 - i]

    def _q0_num_undo(self, b, i, T, P, q1):
        n = self.n
        if n + 2 - i <= n:
            self._mul_into(b, q1, P[n + 2 - i], T[n + 1 - i])

    def _alive_compute(self, b, i, P, K, a, clear):
        """a ^= (K == i-1) & (lead(r_{i-1}) != 0)   (MBU-cleared when clear=True)."""
        n = self.n
        eq = b.alloc_qubits(1)[0]
        b.flip_if_equal(K, i - 1, target=eq)
        zt = ZeroTest(b, P[n - i])
        b.x(zt.flag)
        if clear:
            b.del_and(eq, zt.flag, a)
        else:
            b.init_and(eq, zt.flag, a)
        b.x(zt.flag)
        zt.close()
        b.flip_if_equal(K, i - 1, target=eq)
        b.free(eq)

    def step_lean(self, b, i, arrays, K, forward=True):
        n, d = self.n, self.deg
        T, P = arrays[i % 2], arrays[(i - 1) % 2]
        a = b.alloc_qubits(1)[0]
        if forward:
            self._alive_compute(b, i, P, K, a, clear=False)
            inv_r, rec_r = self.ar.init_inverse(b, P[n - i])        # 1 / lead(r_{i-1})
            q1 = b.alloc_qubits(d)
            self._ratio_and_inv(b, T[n + 1 - i], inv_r, a, q1, clear=False)
            self._updates(b, i, T, P, q1, None, "r1")
            q0 = b.alloc_qubits(d)
            self._ratio_and_inv(b, T[n - i], inv_r, a, q0, clear=False)
            self.ar.del_inverse(b, rec_r)
            self._updates(b, i, T, P, q1, q0, "r0")
            self._updates(b, i, T, P, q1, q0, "u")
            inv_u, rec_u = self.ar.init_inverse(b, P[n + 1 - i])    # 1 / lead(u_{i-1})
            num = self._q0_num_inplace(b, i, T, P, q1)
            self._ratio_and_inv(b, num, inv_u, a, q0, clear=True)
            self._q0_num_undo(b, i, T, P, q1)
            b.free(q0)
            self._ratio_and_inv(b, T[n - i], inv_u, a, q1, clear=True)
            b.free(q1)
            self.ar.del_inverse(b, rec_u)
            b.iadd(1, target=K, control=a)
            b.flip_if_equal(K, i, target=a)          # a == (K == i) now: clears it
        else:
            b.flip_if_equal(K, i, target=a)          # a := (K == i)
            b.isub(1, target=K, control=a)
            inv_u, rec_u = self.ar.init_inverse(b, P[n + 1 - i])
            q1 = b.alloc_qubits(d)
            self._ratio_and_inv(b, T[n - i], inv_u, a, q1, clear=False)
            q0 = b.alloc_qubits(d)
            num = self._q0_num_inplace(b, i, T, P, q1)
            self._ratio_and_inv(b, num, inv_u, a, q0, clear=False)
            self._q0_num_undo(b, i, T, P, q1)
            self.ar.del_inverse(b, rec_u)
            self._updates(b, i, T, P, q1, q0, "u")
            self._updates(b, i, T, P, q1, q0, "r0")
            inv_r, rec_r = self.ar.init_inverse(b, P[n - i])
            self._ratio_and_inv(b, T[n - i], inv_r, a, q0, clear=True)
            b.free(q0)
            self._updates(b, i, T, P, q1, None, "r1")
            self._ratio_and_inv(b, T[n + 1 - i], inv_r, a, q1, clear=True)
            b.free(q1)
            self.ar.del_inverse(b, rec_r)
            self._alive_compute(b, i, P, K, a, clear=True)
        b.free(a)

    def chien_forney(self, b, A, E):
        n = self.n
        gf, d = self.gf, self.deg
        t = self.t
        alpha = gf.primitive_element
        order = 2**d - 1
        sig = [A[n - k] for k in range(t + 1)]
        om = [A[k] for k in range(t)]
        sig_step = [gf.pow(alpha, (-k) % order) for k in range(t + 1)]
        om_step = [gf.pow(alpha, (-(k + 1)) % order) for k in range(t)]
        # in-place sums: sig[0] := sigma(x), then sig[1] := odd part, om[0] := omega(x)
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

    def build(self) -> km.Circuit:
        n, d = self.n, self.deg
        b = km.CircuitBuilder()
        S = [b.create_quantum_register(d, name=f"S{i}") for i in range(n)]
        E = [b.create_classical_register(d, name=f"E{j}") for j in range(self.m)]
        even = list(S) + [b.alloc_qubits(d)]
        odd = [b.alloc_qubits(d) for _ in range(self.N)]
        arrays = [even, odd]
        b.x(even[n][0])
        b.x(odd[n][0])
        K = b.alloc_qubits(self.KBITS)
        with b.mark("eea_forward"):
            for i in range(1, self.t + 1):
                self.step_lean(b, i, arrays, K, forward=True)
        par = K[0]
        swap_src = km.array([q for s in even for q in s])
        swap_dst = km.array([q for s in odd for q in s])
        b.cswap(par, swap_src, swap_dst)
        with b.mark("chien_forney"):
            self.chien_forney(b, even, E)
        b.cswap(par, swap_src, swap_dst)
        with b.mark("eea_reverse"):
            for i in range(self.t, 0, -1):
                self.step_lean(b, i, arrays, K, forward=False)
        b.x(odd[n][0])
        b.x(even[n][0])
        b.free(K)
        b.free(even[n])
        for s in odd:
            b.free(s)
        return b.finish_circuit()
