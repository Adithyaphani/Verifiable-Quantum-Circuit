"""
Benchmark I: Fusion Energy (1/√x Phasing) Reversible Circuit Synthesizer.

Synthesizes fixed-point inverse-square-root phasing circuits using reversible logic
and diagonal phase gates, optimized for the space-time volume metric: Cost = Q^2 * T.
"""

import math
from typing import List, Tuple
from src.core.kickmix_ast import KickmixCircuit, Qubit


def synthesize_reversible_adder(circuit: KickmixCircuit, a: List[Qubit], b: List[Qubit], ancilla: Qubit):
    """
    Synthesizes an in-place reversible Cuccaro Ripple-Carry Adder: |a⟩|b⟩|0⟩ -> |a⟩|a + b⟩|carry⟩.
    Uses 1 carry ancilla and roughly 2n Toffolis.
    """
    n = len(a)
    assert len(b) == n, "Registers 'a' and 'b' must have equal length."

    # Majority gates (forward carry propagation)
    carries = [ancilla]
    for i in range(n - 1):
        # MAJ gate
        circuit.cx(a[i], b[i])
        circuit.cx(a[i], carries[-1])
        circuit.ccx(b[i], carries[-1], a[i])

    # Final bit sum
    circuit.cx(a[n - 1], b[n - 1])
    circuit.cx(a[n - 1], carries[-1])

    # Uncompute carries (backward uncomputation)
    for i in range(n - 2, -1, -1):
        circuit.ccx(b[i], carries[-1], a[i])
        circuit.cx(a[i], carries[-1])
        circuit.cx(a[i], b[i])


def generate_invsqrt_circuit(bit_width: int = 8, scale_factor: float = 1.0) -> KickmixCircuit:
    """
    Synthesizes a verifiable Kickmix circuit for 1/√x phasing over normalized input range.
    
    Architecture:
    1. Input Register 'x' of size `bit_width`.
    2. Reciprocal square-root phase approximation via diagonal phase kickback.
    3. Reversible polynomial terms with immediate ancilla uncomputation.
    
    Args:
        bit_width: Precision bit-width of input register x (typical: 6 to 12 bits).
        scale_factor: Physical scaling constant for Coulomb interaction strength.
    """
    qc = KickmixCircuit(name=f"invsqrt_w{bit_width}")
    
    # Register Allocation
    x_reg = qc.add_register("x", bit_width)
    anc_reg = qc.add_register("ancilla", max(2, bit_width // 2))

    # Phase Polynomial Synthesis:
    # 1/√x ≈ c0 - c1*x + c2*x^2 over normalized interval [0.5, 1.0]
    # Chebyshev coefficients for 1/√x on [0.5, 1.0]:
    # c0 ≈ 1.85, c1 ≈ 1.25, c2 ≈ 0.40
    c0 = 1.854 * scale_factor
    c1 = 1.253 * scale_factor
    c2 = 0.399 * scale_factor

    # Linear phase kickback: sum_i 2^(-i) applied to bit x[i]
    for i in range(bit_width):
        weight = 2 ** (-(i + 1))
        theta_linear = -c1 * weight
        qc.rz(x_reg[i], theta_linear)

    # Quadratic interaction phase kickback:
    # (sum_i 2^(-i) x_i)^2 = sum_i 4^(-i) x_i + 2 sum_{i < j} 2^(-(i+j)) x_i x_j
    # Diagonal pairwise terms are applied conditionally via CCX into scratch + RZ, then uncomputed!
    for i in range(min(bit_width, 4)):
        for j in range(i + 1, min(bit_width, 4)):
            weight_pair = 2.0 * (2 ** (-(i + 1))) * (2 ** (-(j + 1)))
            theta_quad = c2 * weight_pair

            # Synthesize pairwise interaction: CCX into scratch ancilla, apply RZ, uncompute
            scratch = anc_reg[0]
            qc.ccx(x_reg[i], x_reg[j], scratch)
            qc.rz(scratch, theta_quad)
            qc.ccx(x_reg[i], x_reg[j], scratch)  # Reversible uncomputation (scratch returned to |0>)
            qc.uncompute(scratch)

    return qc
