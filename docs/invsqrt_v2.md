# invsqrt v2: rebuilt Benchmark I circuit

`src/benchmarks/invsqrt_v2.py` replaces the reference design (normalize -> 2-segment cubic -> Newton-Raphson -> shift -> phase) with:

1. **Binary normalizer**: s (leading zero pairs) kept in 4 qubits, found by 4 "top-k bits zero" checks (k = 16, 8, 4, 2); x is shifted in place with CSWAPs that only touch bits that can be non-zero.
2. **No Newton step**: a 512-entry QROM (384 used segments of v = xn/2^20 in [1, 4)) outputs per-segment quadratic coefficients; one Horner pass gives p ~ v^-1/2. QROM costs ~1 Toffoli per entry whatever its width, so many small segments beat a few wide multiplications.
3. **Narrow partial products**: each multiplication row only carries through the bits the running sum can occupy.
4. **Phase**: the top 26 bits of p are left-shifted by s with a binary log-shifter and phased with one Z_POW each; phi = p * 2^(s-10) turns.
5. **Qubit cap**: `set_max_qubits(130)` makes kickmix's adders trade a few Toffolis for qubits (better Q x C).
6. **Bias centring**: a per-segment c0 nudge (`invsqrt_v2_c0_shift.npy`) centres the truncation error.

| | Reference | v2 |
|---|---|---|
| Q | 260 | 130 |
| Toffoli | 7,735 | 2,339 |
| fine Z_POW | 37 | 33 |
| C = Toffoli + T/4 | 7,988 | 2,569 |
| S = Q x C | 2,076,774 | 334,006 |
| improvement | 1.00x | **6.22x** |

Verified locally with `tools/verify_invsqrt.py`: every x in [1, 3,133,452], 3 measurement seeds each (9.4M shots), 0 failures, worst error 0.87 of tolerance. The pricing follows the paper's formula; the official Kaggle verifier is the final word.

Rebuild + verify: `python tools/build_invsqrt_v2.py invsqrt.kmb --shots-per-x 3`. Parameter search: `tools/sweep_invsqrt.py`, `tools/center_invsqrt.py`.
