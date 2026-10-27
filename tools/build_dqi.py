"""Build the window-EEA DQI decoder (Benchmark II) and optionally verify it.

    python tools/build_dqi.py dqi.kmb                # build (~30 s, ~500 MB file)
    python tools/build_dqi.py dqi.kmb --verify 2     # + official verifier, 2 workers (~4 min)
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "verifiers"))

from src.dqi.window_eea import WindowEEADecoder  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--verify", type=int, default=0, metavar="WORKERS")
    a = ap.parse_args()
    t = time.time()
    c = WindowEEADecoder().build()
    c.to_file(a.out, format="kmb")
    print(f"wrote {a.out}: Q={c.num_qubits} toffoli={c.operation_statistics().num_toffoli_like} ({time.time() - t:.0f}s)")
    if a.verify:
        import kickmix as km
        from dqi import verify_submission_dqi as V
        r = V.verify(km.Circuit.from_file(a.out, format="kmb"), V.ProblemSpecDQI.benchmark_instance(),
                     max_workers=a.verify)
        print(json.dumps({k: r[k] for k in ("status", "score", "num_qubits", "toffoli_count", "value_errors",
                                            "phase_errors", "repetition_factor")}, indent=1))
        print("ratio vs reference:", 24_439_473_914_136.67 / r["score"])
