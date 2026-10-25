import pytest
km = pytest.importorskip("kickmix")
from src.core.official_io import save_and_reload, stats, fuzz_registers


def _adder(n):
    b = km.CircuitBuilder()
    x = b.create_quantum_register(n, name="x")
    a = b.create_quantum_register(n, name="a")
    b.iadd(x, target=a)
    return b.finish_circuit()


def test_roundtrip_and_fuzz(tmp_path):
    c = save_and_reload(_adder(8), str(tmp_path / "add.kmb"))
    assert stats(c)["toffoli"] > 0
    fuzz_registers(c, lambda r: {"x": r["x"], "a": (r["a"] + r["x"]) % 256})


def test_repo_homemade_format_is_rejected(tmp_path):
    from src.benchmarks.invsqrt import generate_invsqrt_circuit
    p = tmp_path / "bad.kmx"
    generate_invsqrt_circuit().save_kmx(str(p))
    with pytest.raises(Exception):
        km.Circuit.from_file(str(p))
