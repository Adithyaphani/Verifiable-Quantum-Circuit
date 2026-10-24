# Fxpmath (`0.4.10`)

## Overview
**Fxpmath** is a high-performance Python library for fractional fixed-point arithmetic with configurable bit widths, signedness, overflow handling, and rounding modes.

## Key Features & Competition Role
* **Benchmark I ($1/\sqrt{x}$ Phasing for Fusion Energy)**:
  * Precisely simulates register bit widths ($Q$) and precision errors ($\epsilon^+$) in fixed-point inverse square root computation.
  * Evaluates Goldschmidt iterations, Newton-Raphson steps, and Chebyshev polynomial approximations.
  * Tracks quantization noise to ensure candidate circuits satisfy the 102,400-shot verification test without exceeding acceptable error thresholds.

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import fxpmath; val = fxpmath.Fxp(1.25, signed=False, n_word=16, n_frac=14); print('Fxpmath Fixed-Point: OK', val)"
```
