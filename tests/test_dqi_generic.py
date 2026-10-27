import os
import sys

import pytest

km = pytest.importorskip("kickmix")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifiers"))
V = pytest.importorskip("dqi.verify_submission_dqi")

from src.dqi.generic_eea2 import GenericEEADecoderLean  # noqa: E402


def test_small_instance_passes_official_checks():
    c = GenericEEADecoderLean(n=8, m=300).build()
    r = V.verify(c, V.ProblemSpecDQI.benchmark_instance(m=300, n=8, num_shots=2048), max_workers=1, seed=7)
    assert r["status"] == "PASS"
    assert r["value_errors"] == 0 and r["phase_errors"] <= 2
