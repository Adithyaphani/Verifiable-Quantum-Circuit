import numpy as np
import pytest

km = pytest.importorskip("kickmix")

from src.benchmarks.invsqrt_v2 import build_best  # noqa: E402
from tools.verify_invsqrt import MAX_X, check, price  # noqa: E402


def test_invsqrt_v2_sample_passes_and_beats_reference():
    c = build_best()
    xs = np.unique(np.concatenate([np.arange(1, 2000), np.arange(1, MAX_X + 1, 997),
                                   np.arange(MAX_X - 2000, MAX_X + 1), [936319, 234463, 2588411]]))
    r = check(c, xs, seed=7)
    assert r["fails"] == 0 and r["worst_err_over_tol"] < 1
    cost = price(c, r["min_margin_turns"])
    assert cost["Q"] <= 130 and cost["toffoli"] <= 2400
    assert cost["ratio_vs_reference"] > 6
