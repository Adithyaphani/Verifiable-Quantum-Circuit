"""Parameter sweep for invsqrt_v2: builds each variant, preview-checks it, prints the best."""
import itertools
import sys

import numpy as np

sys.path.insert(0, ".")
from src.benchmarks.invsqrt_v2 import Params, build  # noqa: E402
from tools.verify_invsqrt import MAX_X, check, price  # noqa: E402


def preview_xs(stride):
    xs = np.arange(1, MAX_X + 1, stride, dtype=np.int64)
    return np.unique(np.concatenate([xs, np.arange(1, 3000), np.arange(MAX_X - 3000, MAX_X + 1)]))


def evaluate(p: Params, stride=389):
    try:
        c = build(p)
    except AssertionError as e:
        return None
    r = check(c, preview_xs(stride), seed=5)
    if r["fails"] or r["worst_err_over_tol"] > 0.85:   # keep a safety margin for unchecked x
        return None
    r.update(price(c, r["min_margin_turns"]))
    return r


if __name__ == "__main__":
    grid = dict(A=[7, 8, 9, 10], degree=[2, 3], F=[26, 27, 28, 29, 30], drop=[0, 1, 2, 3], mw=[34, 35, 36, 37])
    results = []
    for A, d, F, drop, mw in itertools.product(*grid.values()):
        if d == 2 and A < 8:
            continue
        if d == 3 and A > 8:
            continue
        p = Params(A=A, degree=d, F=F, phase_bits=F + 1 - drop, min_weight=mw)
        r = evaluate(p)
        if r:
            results.append((r["score_S"], p, r))
            print(f"{r['score_S']:>10.0f} x{r['ratio_vs_reference']:.3f} Q={r['Q']} tof={r['toffoli']} "
                  f"err={r['worst_err_over_tol']:.2f} {p}", flush=True)
    results.sort(key=lambda z: z[0])
    print("BEST:")
    for s, p, r in results[:5]:
        print(f"{s:.0f} x{r['ratio_vs_reference']:.3f} {p} Q={r['Q']} tof={r['toffoli']} err={r['worst_err_over_tol']:.3f}")
