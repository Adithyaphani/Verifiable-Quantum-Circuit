"""Tests for peephole and commutation-aware cancellation."""
from src.optimization.peephole import optimize_kmx_lines, KmxInstruction


def test_adjacent_cancellation():
    circuit = [
        "REGISTER r0 \"x\"",
        "APPEND_TO_REGISTER q0 r0",
        "X q1",
        "X q1",
        "CX q1 q2",
        "CX q1 q2",
        "CCX q0 q1 q3",
        "CCX q1 q0 q3",  # Controls reversed: should cancel
        "Z_POW q0 0.5",
        "Z_POW q0 1.5",  # Sums to 2.0 (mod 2 = 0): should cancel
    ]
    opt = optimize_kmx_lines(circuit)
    # Only the register metadata should remain
    assert len(opt) == 2
    assert "X q1" not in opt
    assert "CX q1 q2" not in opt
    assert "CCX" not in opt
    assert "Z_POW" not in opt


def test_commutation_sliding_cancellation():
    circuit = [
        "REGISTER r0 \"x\"",
        "APPEND_TO_REGISTER q0 r0",
        "CCX q1 q2 q3",
        "CX q4 q5",       # Disjoint qubits {q4, q5}
        "CCX q2 q1 q3",  # Cancels with first CCX across CX q4 q5
        "CX q4 q5",       # Cancels with earlier CX q4 q5
    ]
    opt = optimize_kmx_lines(circuit)
    assert len(opt) == 2


def test_zpow_merging():
    circuit = [
        "REGISTER r0 \"x\"",
        "APPEND_TO_REGISTER q0 r0",
        "Z_POW q0 0.125",
        "CX q1 q2",       # Disjoint
        "Z_POW q0 0.125",
    ]
    opt = optimize_kmx_lines(circuit)
    assert any("Z_POW q0 0.25" in line for line in opt)
    assert any("CX q1 q2" in line for line in opt)


if __name__ == "__main__":
    test_adjacent_cancellation()
    test_commutation_sliding_cancellation()
    test_zpow_merging()
    print("All peephole unit tests passed successfully!")
