"""Exhaustive local check + score for Benchmark I, following arXiv:2610.23832v2 sec. II.A.3.

Every x in [1, 3,133,452] is simulated (optionally several shots per x with different
measurement seeds). Checks: phase within tol(x) = 2**-24 / sqrt(x) turns, x restored,
scratch qubits back to 0. Then prices the circuit: S = Q * (Toffoli + T/4), where each
fine Z_POW costs 0.56*log2(1/eps) + 5.3 T and eps = pi * min_x(tol - |err|) / n_rot.

    python tools/verify_invsqrt.py circuit.kmb [--shots-per-x 1] [--stride 1]
"""
from __future__ import annotations

import argparse
import math
import sys
import time

import numpy as np

import kickmix as km

MAX_X = 3 * (2**10 - 2) ** 2
REF_SCORE = 2_076_774.233715282


def check(circuit, xs: np.ndarray, seed: int, batch: int = 1 << 15):
    regs = circuit.register_data
    assert list(regs) == ["x"] and len(regs["x"]) == 22, f"registers must be exactly x[22], got {list(regs)}"
    used = set(regs["x"])
    scratch = km.array(sorted(set(km.q(i) for i in range(circuit.num_qubits)) - used))
    worst_ratio, min_margin, worst_x = 0.0, math.inf, None
    fails = 0
    for start in range(0, len(xs), batch):
        chunk = xs[start:start + batch]
        n = len(chunk)
        sim = km.Simulator(batch_size=n, seed=seed + start)
        sim.use_same_registers_as(circuit)
        sim.clear_for_shot()
        bits = ((chunk[None, :] >> np.arange(22)[:, None]) & 1).astype(np.bool_)
        sim.write_across_shots("x", bits)
        sim.do(circuit)
        out = sim.read_across_shots("x")
        assert np.array_equal(out, bits), "x not restored"
        if len(scratch):
            assert not sim.read_across_shots(scratch).any(), "scratch qubits not clean"
        ph = np.array([float(sim.read_shot_phase(i)) for i in range(n)]) / 2.0  # turns
        target = 1.0 / np.sqrt(chunk.astype(np.float64))
        err = np.abs(((ph - target) + 0.5) % 1.0 - 0.5)
        tol = 2.0**-24 * target
        ratio = err / tol
        i = int(np.argmax(ratio))
        if ratio[i] > worst_ratio:
            worst_ratio, worst_x = float(ratio[i]), int(chunk[i])
        min_margin = min(min_margin, float(np.min(tol - err)))
        fails += int(np.sum(err > tol))
    return {"fails": fails, "worst_err_over_tol": worst_ratio, "worst_x": worst_x, "min_margin_turns": min_margin}


def price(circuit, min_margin: float) -> dict:
    st = circuit.operation_statistics()
    q = circuit.num_qubits
    tof = st.num_toffoli_like
    t = st.num_t_like
    nrot = st.num_z_pow(4, None)
    rot_t = 0.0
    if nrot:
        eps = math.pi * min_margin / nrot
        rot_t = 0.56 * math.log2(1 / eps) + 5.3 if eps > 0 else math.inf
    c = tof + (t + nrot * rot_t) / 4
    return {"Q": q, "toffoli": tof, "T": t, "n_rot": nrot, "rot_T_each": rot_t, "C": c,
            "score_S": q * c, "ratio_vs_reference": REF_SCORE / (q * c)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("circuit")
    ap.add_argument("--shots-per-x", type=int, default=1)
    ap.add_argument("--stride", type=int, default=1, help="check every k-th x (fast preview)")
    a = ap.parse_args(argv)
    c = km.Circuit.from_file(a.circuit)
    xs = np.arange(1, MAX_X + 1, a.stride, dtype=np.int64)
    if a.stride > 1:   # always include the edges
        xs = np.unique(np.concatenate([xs, np.arange(1, 5000), np.arange(MAX_X - 5000, MAX_X + 1)]))
    t0 = time.time()
    res = None
    for shot in range(a.shots_per_x):
        r = check(c, xs, seed=1000003 * shot + 17)
        if res is None:
            res = r
        else:
            res["fails"] += r["fails"]
            if r["worst_err_over_tol"] > res["worst_err_over_tol"]:
                res.update(worst_err_over_tol=r["worst_err_over_tol"], worst_x=r["worst_x"])
            res["min_margin_turns"] = min(res["min_margin_turns"], r["min_margin_turns"])
    res.update(price(c, res["min_margin_turns"]))
    res["inputs_checked"] = len(xs) * a.shots_per_x
    res["seconds"] = round(time.time() - t0, 1)
    for k, v in res.items():
        print(f"{k:>20}: {v}")
    return 0 if res["fails"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
