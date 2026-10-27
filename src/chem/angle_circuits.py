"""ANGLE_k circuits: per-batch XOR lookups of angle words (dfthcsos register contract).

Circuit k maps |a>|z> -> |a>|z XOR (batch_k(a) XOR batch_{k-1}(a))> with registers
"selection" (ceil(log2 L) qubits) and "word_0".."word_{J-1}" (brot qubits each).
The lookup is a unary iteration that only visits addresses whose XOR-delta is non-zero
(jumping between visited addresses costs (a ^ b).bit_length() - 1 Toffolis).
"""
from __future__ import annotations

import math

import numpy as np

import kickmix as km


def batches(words: np.ndarray, J: int) -> list[np.ndarray]:
    L, A = words.shape
    K = math.ceil(A / J)
    padded = np.zeros((L, K * J), dtype=np.int64)
    padded[:, :A] = words
    return [padded[:, k * J:(k + 1) * J] for k in range(K)]


def build_angle_circuits(words: np.ndarray, brot: int, J: int) -> list[km.Circuit]:
    words = np.asarray(words, dtype=np.int64)
    L = words.shape[0]
    sel_bits = (L - 1).bit_length()
    bs = batches(words, J)
    out = []
    for k, cur in enumerate(bs):
        prev = bs[k - 1] if k else np.zeros_like(cur)
        delta = cur ^ prev
        b = km.CircuitBuilder()
        sel = b.create_quantum_register(sel_bits, name="selection")
        regs = [b.create_quantum_register(brot, name=f"word_{j}") for j in range(J)]
        flat = [q for r in regs for q in r]
        packed = np.zeros(L, dtype=object)
        for j in range(J):
            for a in range(L):
                packed[a] = int(packed[a]) | (int(delta[a, j]) << (j * brot))
        live = [a for a in range(L) if packed[a]]
        if live:
            with b.unary_iteration(sel, range(L)) as it:
                for a in live:
                    it.move_to(a)
                    mq = it.match_qubit
                    v = int(packed[a])
                    targets = [flat[i] for i in range(len(flat)) if (v >> i) & 1]
                    b.cx(mq, km.array(targets))
        out.append(b.finish_circuit())
    return out
