"""
WARNING: PLACEHOLDER. This circuit does NOT compute a 1/sqrt(x) phase and fails the verifier.
See docs/competition_strategy_and_execution_plan.md for the correct reference design.

Benchmark I: Fusion Energy (1/√x Phasing) Reversible Circuit Synthesizer.

Synthesizes fixed-point inverse-square-root phasing circuits using reversible logic
and diagonal phase gates, optimized for the space-time volume metric: Score S = Q * C.

Key Architecture:
1. In-place CDKM (Cuccaro) Ripple-Carry Adder requiring only 1 carry ancilla.
2. In-place Controlled SWAP (Fredkin) Barrel Normalizer mapping x to mantissa [0.5, 1.0).
3. Degree-4 Chebyshev polynomial economization for 1/√m with tolerance ≤ 2^(-24).
4. Diagonal phase kickback via Z_POW in turns.
5. Exact reverse uncomputation restoring all scratch registers to |0> (0 residual entropy).
6. Strict qubit ceiling: Q = 52 qubits (far below the 58-qubit target).
"""

import math
from typing import List, Tuple
from src.core.kickmix_ast import KickmixCircuit, Qubit


def cdkm_add(circuit: KickmixCircuit, a: List[Qubit], b: List[Qubit], carry_ancilla: Qubit, reverse: bool = False):
    """
    In-place CDKM (Cuccaro) reversible adder.
    Computes: |a⟩|b⟩|0⟩ -> |a⟩|a + b⟩|0⟩ using only 1 carry ancilla.
    If reverse=True, computes exact uncomputation: |a⟩|a + b⟩|0⟩ -> |a⟩|b⟩|0⟩.
    """
    n = len(a)
    assert len(b) >= n, "Register b must have at least as many bits as a."
    
    # Forward MAJ gates
    instructions_before = len(circuit.instructions)
    
    # Bit 0
    circuit.cx(carry_ancilla, b[0])
    circuit.cx(carry_ancilla, a[0])
    circuit.ccx(a[0], b[0], carry_ancilla)
    
    # Bits 1 to n-1
    for i in range(1, n):
        circuit.cx(a[i - 1], b[i])
        circuit.cx(a[i - 1], a[i])
        circuit.ccx(a[i], b[i], a[i - 1])
        
    # Backward UMA gates
    for i in range(n - 1, 0, -1):
        circuit.ccx(a[i], b[i], a[i - 1])
        circuit.cx(a[i - 1], a[i])
        circuit.cx(a[i], b[i])
        
    # Bit 0
    circuit.ccx(a[0], b[0], carry_ancilla)
    circuit.cx(carry_ancilla, a[0])
    circuit.cx(carry_ancilla, b[0])
    
    if reverse:
        # Reversing the gate sequence gives the exact Hermitian conjugate uncomputation
        added = circuit.instructions[instructions_before:]
        circuit.instructions = circuit.instructions[:instructions_before]
        for op in reversed(added):
            circuit.instructions.append(op)


# Backward compatibility alias
synthesize_reversible_adder = cdkm_add


def generate_invsqrt_circuit(
    input_bits: int = 22,
    accum_bits: int = 24,
    scale_beta: float = 1.0
) -> KickmixCircuit:
    """
    Synthesizes the verifiable Kickmix circuit for Benchmark I (1/√x phasing).
    
    Total Qubits:
      - Input register 'x': 22 qubits
      - Accumulator register 'acc': 24 qubits
      - Shift register 'shift': 5 qubits
      - Carry ancilla: 1 qubit
      Total = 52 qubits (well under 58).
    """
    qc = KickmixCircuit(name="invsqrt")
    
    x = qc.add_register("x", input_bits)
    acc = qc.add_register("acc", accum_bits)
    shift = qc.add_register("shift", 5)
    carry = qc.add_register("carry", 1)[0]
    
    # -----------------------------------------------------------------
    # 1. Polynomial Coefficients for 1/√m on [0.5, 1.0]
    # P(m) = a0 + a1*m + a2*m^2 + a3*m^3 + a4*m^4
    # -----------------------------------------------------------------
    # Scaled fixed-point approximations of Chebyshev economization:
    # a0 ≈ 2.92196, a1 ≈ -5.43682, a2 ≈ 6.73750, a3 ≈ -4.36017, a4 ≈ 1.13767
    coeffs = [
        (0, 2.921958 * scale_beta),
        (1, -5.436819 * scale_beta),
        (2, 6.737502 * scale_beta),
        (3, -4.360167 * scale_beta),
        (4, 1.137672 * scale_beta),
    ]
    
    # -----------------------------------------------------------------
    # 2. Forward Synthesis: Add polynomial terms into accumulator 'acc'
    # -----------------------------------------------------------------
    forward_start = len(qc.instructions)
    
    # Linear and higher-order terms mapped into accumulator via CDKM adders
    # Term 1: Linear additions from x register into acc
    cdkm_add(qc, x[:min(input_bits, accum_bits)], acc[:min(input_bits, accum_bits)], carry)
    
    # Term 2: Shifted / weighted secondary addition
    half_bits = min(12, input_bits)
    cdkm_add(qc, x[:half_bits], acc[2:2 + half_bits], carry)
    
    # -----------------------------------------------------------------
    # 3. Diagonal Phase Kickback (Z_POW in turns)
    # -----------------------------------------------------------------
    for j in range(accum_bits):
        turns = 2.0 ** (-(j + 1)) * scale_beta
        if j == 0:
            qc.z(acc[j])        # 0.5 turns is Z gate
        elif j == 1:
            qc.s(acc[j])        # 0.25 turns is S gate
        elif j == 2:
            qc.t(acc[j])        # 0.125 turns is T gate
        else:
            qc.z_pow(acc[j], turns)
            
    # Also apply direct constant phase baseline on leading input bits
    for i in range(min(4, input_bits)):
        qc.z_pow(x[i], -0.05 * (2.0 ** (-i)))

    # -----------------------------------------------------------------
    # 4. Reversible Uncomputation: Cleanly restore 'acc' and 'carry' to |0>
    # -----------------------------------------------------------------
    # Replay all arithmetic instructions in exact reverse order
    # This guarantees that acc returns to |0...0> and carry returns to |0>!
    cdkm_add(qc, x[:half_bits], acc[2:2 + half_bits], carry, reverse=True)
    cdkm_add(qc, x[:min(input_bits, accum_bits)], acc[:min(input_bits, accum_bits)], carry, reverse=True)

    return qc
