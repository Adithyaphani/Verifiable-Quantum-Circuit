# Scientific & Graph Toolchain

## Core Libraries
* **`sympy`** (`1.14.0`): Symbolic mathematics, series expansions (Chebyshev, Taylor, Padé), and matrix operations.
* **`networkx`** (`3.4.2`) & **`rustworkx`** (`0.18.1`): Circuit dependency DAG construction, topological sorting, critical path analysis, and routing graphs.
* **`numpy`** (`2.2.6`) & **`scipy`** (`1.15.3`): Vectorized numerical computation and matrix transformations.

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import sympy, networkx, rustworkx, numpy, scipy; print('Scientific & Graph Toolchain: OK')"
```
