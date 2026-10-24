# Galois (`0.4.11`)

## Overview
**Galois** is an efficient C++/Numba-accelerated Python library for arithmetic over Galois Fields ($\text{GF}(p^m)$) and polynomial rings.

## Key Features & Competition Role
* **Benchmark II (Reed-Solomon Decoders for DQI)**:
  * Computes syndromes over finite fields $\text{GF}(2^m)$.
  * Implements the **Extended Euclidean Algorithm (EEA)** and Berlekamp-Massey algorithm for finding error locator polynomials.
  * Serves as the high-speed classical reference oracle to fuzz-test and verify quantum reversible Reed-Solomon systolic arrays and Chien search circuits.

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import galois; GF = galois.GF(2**8); print('Galois Finite Fields: OK', GF)"
```
