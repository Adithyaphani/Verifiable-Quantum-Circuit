import os
import sys

import pytest

km = pytest.importorskip("kickmix")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifiers"))
V = pytest.importorskip("dqi.verify_submission_dqi")

from src.dqi.window_eea import WindowEEADecoder  # noqa: E402


@pytest.mark.slow
def test_benchmark_instance_sample():
    """Full-size decoder (the slot map is written for n = 70) on a 512-shot sample."""
    c = WindowEEADecoder().build()
    assert c.num_qubits <= 1408
    r = V.verify(c, V.ProblemSpecDQI.benchmark_instance(num_shots=512), max_workers=2, seed=3, log2_delta=-1)
    assert r["value_errors"] == 0
    assert r["phase_errors"] <= 8          # ~0.4% degenerate shots expected
