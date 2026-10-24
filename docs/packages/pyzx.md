# PyZX (`0.10.7`)

## Overview
**PyZX** is an open-source Python library for quantum circuit compilation and verification using the **ZX-calculus** graph rewrite formalism.

## Key Features & Competition Role
* **Clifford+T Optimization**: Transforms quantum circuits into ZX-diagrams, performs graph-theoretic rewrites (spider fusion, phase teleportation, pivoting), and extracts simplified circuits.
* **Toffoli / T-Count Reduction**: Powerful rewrite heuristics for minimizing non-Clifford gate count.
* **Equivalence Verification**: Fast graph-theoretic check of circuit equivalence for candidate optimizations.

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import pyzx; print('PyZX Graph Rewriter: OK')"
```
