"""Build a cheaper Benchmark III (dfthcsos) submission from the baseline factorization.

    python tools/build_dfthcsos.py BASELINE.npz OUT_DIR [--brot 10] [--rounds 3] [--joint-iters 140]
        [--verify]

BASELINE.npz is the competition's sample_submission/dfthcsos/submission.npz. OUT_DIR gets
submission.npz plus angle_k_0.kmb ... (copy the folder into the zip as dfthcsos/).
Runtime on 2 cores: about 10 min for the joint refit, about 12 min per word-selection round.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "verifiers"))

from dfthcsos.scoreinfra.dfthc_math import evaluate_dfthc_vectors, reconstruct_x  # noqa: E402
from dfthcsos.verify import load_inputs  # noqa: E402
from src.chem import requant as rq  # noqa: E402
from src.chem.angle_circuits import build_angle_circuits  # noqa: E402

REF_SCORE = 3355599588.3155365


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("out")
    ap.add_argument("--brot", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--joint-iters", type=int, default=140)
    ap.add_argument("--offset-iters", type=int, default=150)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    log = lambda m: print(f"[{time.time() - t0:6.0f}s] {m}", flush=True)  # noqa: E731

    base = dict(np.load(a.baseline, allow_pickle=False))
    inp = load_inputs(a.baseline)
    edges = base["tree_edges"]
    Ts = rq.packed_target(inp.ref["tei"], inp.S)
    U = base["U"].astype(np.float64)
    U /= np.linalg.norm(U, axis=2, keepdims=True)
    w = base["W"].astype(np.float64)
    W = base["H2_I"].astype(np.float64) - w.sum(1)
    R, B, C = w.shape

    if a.joint_iters:
        U, w = rq.joint_fit(U, w, Ts, iters=a.joint_iters)
        log(f"joint refit done: error_2 (unquantized) = {np.sqrt(rq.joint_loss_grad(U, w, Ts)[0]):.6f}")
    words2, w = rq.QOpt(U, w, Ts, edges, a.brot).run(a.rounds, log=log)

    U2 = rq.decode(words2.reshape(-1, 75), edges, a.brot).reshape(R, B, rq.N)
    X = reconstruct_x(U2, w)
    X = np.tril(X) + np.swapaxes(np.tril(X, k=-1), -1, -2)
    h1 = inp.ref["oei"] - 0.5 * np.einsum("prrq->pq", inp.ref["tei"])
    h1p0 = h1 - 0.5 * inp.ref["electrons"] * inp.S + inp.beta_1 * np.eye(rq.N)
    c0 = inp.energy_upper - inp.ref["ecore"] + inp.ref["electrons"] * inp.beta_1
    Xs, aa, ss = X.reshape(R * C, rq.N, rq.N), np.abs(w).sum(1).ravel(), w.sum(1).ravel()
    Wn = rq.opt_offsets(Xs, h1p0, c0, aa, ss, W.ravel(), iters=a.offset_iters)

    def le(Wv):
        eg, La, _, _ = rq.sos_metrics(Wv, Xs, h1p0, c0, aa, ss)
        return np.sqrt(eg * (2 * La - eg)) if eg > rq.E_GAP_FLOOR + 1e-4 else np.inf
    if le(Wn) < le(W.ravel()):
        W = Wn.reshape(R, C)
    lam, V = np.linalg.eigh(h1p0 - np.einsum("rc,rcpq->pq", W, X))
    words = np.vstack([rq.words_of(V.T, edges, a.brot), words2.reshape(-1, 75)]).astype(np.int64)
    m = evaluate_dfthc_vectors(rq.decode(words, edges, a.brot), w, W, inp.S, inp.beta_1, inp.ref,
                               energy_upper=inp.energy_upper)
    log("metrics " + json.dumps({k: float(m[k]) for k in ("error_1", "error_2", "Lambda", "E_gap", "lambda_eff")}))

    os.makedirs(a.out, exist_ok=True)
    np.savez(os.path.join(a.out, "submission.npz"), U=U2.astype(np.float32), W=w.astype(np.float32),
             H2_I=(W + w.sum(1)).astype(np.float32), H1_I=base["H1_I"], Hsym_lower=base["Hsym_lower"],
             tree_edges=edges, angle_words=words)
    sel = (words.shape[0] - 1).bit_length()
    J = (128 - 2 * sel) // a.brot
    K = -(-75 // J)
    J = -(-75 // K)
    for k, c in enumerate(build_angle_circuits(words, a.brot, J)):
        c.to_file(os.path.join(a.out, f"angle_k_{k}.kmb"), format="kmb")
    log(f"wrote {K} circuits (J = {J}) and submission.npz to {a.out}")
    if a.verify:
        from dfthcsos.verify import verify
        r = verify(a.out)
        log(f"official verify: {r['status']} score {r['score']:.6g} ratio {REF_SCORE / r['score']:.4f}")


if __name__ == "__main__":
    main()
