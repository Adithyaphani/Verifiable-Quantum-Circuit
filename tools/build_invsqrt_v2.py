"""Write the optimized invsqrt.kmb and verify it exhaustively.

    python tools/build_invsqrt_v2.py out/invsqrt.kmb [--shots-per-x 3]
"""
import sys

sys.path.insert(0, ".")
from src.benchmarks.invsqrt_v2 import build_best  # noqa: E402
from tools import verify_invsqrt  # noqa: E402

if __name__ == "__main__":
    out = sys.argv[1]
    build_best().to_file(out, format="kmb")
    print("wrote", out)
    sys.exit(verify_invsqrt.main([out] + sys.argv[2:]))
