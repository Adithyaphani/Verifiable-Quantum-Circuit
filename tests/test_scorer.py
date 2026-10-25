import math
from src.scoring.scorer import bench1_score, bench2_score, failure_upper_bound, repetition_factor


def test_bench1_reference():
    s = bench1_score(260, 7735, 1, [2 ** -25] * 37)
    assert s == pytest_approx(2.08e6, 0.02)


def test_bench2_exact_penalty():
    eps = failure_upper_bound(102400)
    assert 1.1 < repetition_factor(eps) < 1.3
    assert bench2_score(1893, 5725461, eps) > 0
    assert math.isinf(repetition_factor(0.1))


def pytest_approx(v, rel):
    class A:
        def __eq__(self, o): return abs(o - v) <= rel * v
    return A()
