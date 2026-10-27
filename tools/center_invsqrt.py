"""Centre the per-segment error of invsqrt_v2 by nudging its c0 table (exhaustive sims)."""
import sys

import numpy as np

sys.path.insert(0, ".")
import kickmix as km  # noqa: E402
from src.benchmarks.invsqrt_v2 import NBITS, Params, build  # noqa: E402
from tools.verify_invsqrt import MAX_X, check, price  # noqa: E402


def signed_errors(c, xs, batch=1 << 15):
    out = np.empty(len(xs))
    for st in range(0, len(xs), batch):
        ch = xs[st:st + batch]
        sim = km.Simulator(batch_size=len(ch), seed=3)
        sim.use_same_registers_as(c)
        sim.clear_for_shot()
        sim.write_across_shots("x", ((ch[None, :] >> np.arange(22)[:, None]) & 1).astype(np.bool_))
        sim.do(c)
        ph = np.array([float(sim.read_shot_phase(i)) for i in range(len(ch))]) / 2.0
        tgt = 1.0 / np.sqrt(ch.astype(np.float64))
        out[st:st + len(ch)] = ((ph - tgt) + 0.5) % 1.0 - 0.5
    return out


def segment_and_scale(xs, A):
    s = np.zeros_like(xs)
    xn = xs.copy()
    for _ in range(10):
        m = xn < (1 << (NBITS - 2))
        xn = np.where(m, xn << 2, xn)
        s += m
    return xn >> (NBITS - A), s


def centre(p: Params, rounds=3):
    xs = np.arange(1, MAX_X + 1, dtype=np.int64)
    seg, s = segment_and_scale(xs, p.A)
    scale = 2.0 ** (s.astype(np.float64) - 10)          # phi = p * scale
    shift = np.zeros(1 << p.A, dtype=np.int64)
    best = None
    for r in range(rounds + 1):
        c = build(p, c0_shift=shift)
        e = signed_errors(c, xs) / scale                 # error in units of p
        tol = 2.0**-24 * (1.0 / np.sqrt(xs)) / scale
        ratio = np.max(np.abs(e) / tol)
        res = check(c, xs, seed=11)
        res.update(price(c, res["min_margin_turns"]))
        print(f"round {r}: worst/tol={ratio:.3f} fails={res['fails']} Q={res['Q']} tof={res['toffoli']} "
              f"x{res['ratio_vs_reference']:.3f}", flush=True)
        if res["fails"] == 0 and (best is None or res["score_S"] < best[0]):
            best = (res["score_S"], shift.copy(), res)
        if r == rounds:
            break
        lo = np.full(1 << p.A, np.inf); hi = np.full(1 << p.A, -np.inf)
        np.minimum.at(lo, seg, e); np.maximum.at(hi, seg, e)
        mid = np.where(np.isfinite(lo), (lo + hi) / 2, 0.0)
        shift = shift - np.round(mid * 2.0**p.F).astype(np.int64)
    return best


if __name__ == "__main__":
    A, d, F, pb, mw = map(int, sys.argv[1:6])
    best = centre(Params(A=A, degree=d, F=F, phase_bits=pb, min_weight=mw))
    if best:
        np.save(sys.argv[6], best[1])
        print("saved", sys.argv[6], best[2])
