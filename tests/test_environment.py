"""
Automated Environment Verification Test Suite
Confirms that all core dependencies, quantum frameworks, arithmetic engines,
and tensor network libraries are correctly installed and operational in .venv.
"""

import sys
import os

# Ensure headless matplotlib backend
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")


def test_qualtran():
    import qualtran
    assert hasattr(qualtran, "Bloq"), "Qualtran missing Bloq abstraction"
    assert hasattr(qualtran, "CompositeBloq"), "Qualtran missing CompositeBloq"
    print("✓ [TEST] Qualtran Bloq framework operational")


def test_cirq():
    import cirq
    assert hasattr(cirq, "Circuit"), "Cirq missing Circuit class"
    q = cirq.LineQubit(0)
    c = cirq.Circuit(cirq.X(q))
    assert len(c) == 1, "Cirq circuit construction failed"
    print(f"✓ [TEST] Cirq {cirq.__version__} operational")


def test_pyzx():
    import pyzx as zx
    g = zx.Graph()
    assert g is not None, "PyZX graph initialization failed"
    print("✓ [TEST] PyZX ZX-calculus rewriter operational")


def test_galois():
    import galois
    gf = galois.GF(2**4)
    assert gf.order == 16, "Galois field order mismatch"
    print("✓ [TEST] Galois finite-field arithmetic engine operational")


def test_fxpmath():
    from fxpmath import Fxp
    x = Fxp(0.5, signed=False, n_word=8, n_frac=7)
    assert float(x) == 0.5, "Fxpmath value evaluation failed"
    print("✓ [TEST] Fxpmath fixed-point arithmetic engine operational")


def test_quimb_and_cotengra():
    import quimb
    import cotengra
    assert quimb is not None and cotengra is not None
    print("✓ [TEST] Quimb & Cotengra tensor network compilers operational")


def test_scientific_stack():
    import numpy as np
    import scipy
    import sympy as sp
    import networkx as nx
    import rustworkx as rx
    
    assert np.__version__ is not None
    assert scipy.__version__ is not None
    assert sp.__version__ is not None
    assert nx.__version__ is not None
    assert rx.__version__ is not None
    print("✓ [TEST] Scientific & Graph toolchain (NumPy, SciPy, SymPy, NetworkX, RustworkX) operational")


def test_telemetry_stack():
    import matplotlib
    import plotly
    import pydantic
    assert matplotlib.__version__ is not None
    assert plotly.__version__ is not None
    assert pydantic.__version__ is not None
    print("✓ [TEST] Telemetry & validation stack (Matplotlib, Plotly, Pydantic) operational")


if __name__ == "__main__":
    print("=" * 65)
    print("RUNNING QUANTUM COMPILATION ENVIRONMENT VERIFICATION")
    print("=" * 65)
    test_qualtran()
    test_cirq()
    test_pyzx()
    test_galois()
    test_fxpmath()
    test_quimb_and_cotengra()
    test_scientific_stack()
    test_telemetry_stack()
    print("=" * 65)
    print("ALL ENVIRONMENT INVARIANTS VERIFIED SUCCESSFULLY!")
    print("=" * 65)
