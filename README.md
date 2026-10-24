# Google Quantum AI: Verifiable Quantum Circuit Compilation
### Automated Agentic Synthesis & Optimization of Fault-Tolerant Quantum Subroutines

This repository contains the codebase, optimization agents, arithmetic synthesizers, and verification pipeline for the **Google Quantum AI - Verifiable Quantum Circuit Compilation** hackathon hosted on Kaggle.

* **Competition**: [Google Quantum AI - Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation)
* **Goal**: Minimize physical qubit count ($Q$), Toffoli gate count ($T$), and space-time volume ($Q^2 \cdot T$ or $\lambda \cdot T \cdot Q$) across fault-tolerant quantum algorithms using closed-loop verification (Kickmix).

---

## 1. Environment & Setup Details

A dedicated Python 3.10 virtual environment has been created and configured directly within this project directory to ensure consistency across both Linux (WSL) and Windows environments.

| Property | Details |
| :--- | :--- |
| **Virtual Environment Path** | `/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv` (`D:\1-Projects\1-Verifiable-Quantum-Circuit\.venv`) |
| **Python Version** | Python `3.10.12` (x86_64 Linux / WSL) |
| **Package Installer** | `pip 26.2.2` bootstrapped via user-space `virtualenv` |
| **Sandbox Compatibility** | Fully accessible inside sandboxed tooling and native shell |

### Activation Instructions

* **Linux / WSL (Recommended)**:
  ```bash
  source /mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/activate
  ```
  Or invoke the interpreter directly:
  ```bash
  /mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python <script.py>
  ```

* **Matplotlib Cache Environment Variable**:
  When running headless in restricted environments, set:
  ```bash
  export MPLCONFIGDIR=/tmp/matplotlib
  ```

---

## 2. Installed Packages & System Stack

The environment is pre-loaded with the full suite of fault-tolerant quantum algorithm libraries, reversible logic tools, finite-field math engines, and tensor network optimizers:

### A. Google Quantum AI Core Frameworks
* **`qualtran`** (`0.7.0`): Google Quantum AI's flagship library for expressing, analyzing, and resource-estimating fault-tolerant quantum algorithms (Bloqs, Soquets, composite bloqs, and cost models).
* **`cirq`** (`1.5.0`) & **`cirq-core`**: Core circuit data structures, gates, and simulation primitives.
* **`cirq-google`** (`1.5.0`): Hardware specifications, Sycamore gate sets, and device targets.
* **`cirq-aqt`**, **`cirq-ionq`**, **`cirq-pasqal`**, **`cirq-web`**: Cross-platform transpilation tools.

### B. High-Performance Quantum & Circuit Compilers
* **`pyzx`** (`0.10.7`): Fast quantum circuit optimization and Clifford+T simplification using ZX-calculus graph rewrites.
* **`bartiq`** (`0.12.1`): High-level quantum resource estimation and symbolic cost tracking.
* **`pennylane`** (`0.42.3`) & **`pennylane-lightning`**: Differentiable quantum programming and circuit gradients.
* **`qsharp`** (`1.31.0`) & **`qdk`** (`1.33.1`): Quantum Development Kit integration.

### C. Mathematics, Fixed-Point & Finite-Field Arithmetic
*(Critical for Benchmark I $1/\sqrt{x}$ and Benchmark II Reed-Solomon decoders)*
* **`galois`** (`0.4.11`): Performant Galois Field ($\text{GF}(2^m)$) arithmetic, polynomial rings, and Extended Euclidean Algorithm (EEA) routines for Reed-Solomon syndrome decoding.
* **`fxpmath`** (`0.4.10`): Arbitrary-precision fixed-point arithmetic for precision modeling of $1/\sqrt{x}$ Coulomb interaction phase angles.
* **`sympy`** (`1.14.0`): Symbolic mathematics, series expansions (Chebyshev, Taylor, Padé), and matrix operations.
* **`numpy`** (`2.2.6`) & **`scipy`** (`1.15.3`): Vectorized numerical analysis and linear algebra.

### D. Graph Theory & Tensor Networks
*(Critical for Benchmark III FeMoCo Givens trees and Double Factorization)*
* **`quimb`** (`1.11.2`): Tensor network algorithms, DMRG, and MPS quantum state decompositions.
* **`cotengra`** (`0.8.3`): Hyper-optimized contraction trees for large tensor networks.
* **`networkx`** (`3.4.2`) & **`rustworkx`** (`0.18.1`): Fast graph algorithms for circuit dependency DAGs and Givens tree routing.

### E. Telemetry, Analysis & Visual Dashboards
* **`matplotlib`** (`3.10.9`), **`plotly`** (`7.1.0`), **`dash`** (`4.4.1`): Multi-panel Pareto frontier plots ($Q$ vs $T$ vs volume).
* **`ipython`** (`8.39.0`), **`jupyterlab`** (`4.6.4`), **`notebook`** (`7.6.3`): Interactive prototyping.
* **`pydantic`** (`2.14.1`): Strict schema validation for compiler configurations and submission artifacts.

---

## 3. The `kickmix` Verification Engine & Starter Kit

### What is `kickmix`?
Verifying general quantum circuits classically requires simulating arbitrary superposition states, which is exponentially hard ($\mathcal{O}(2^n)$). 

To overcome this, Google Quantum AI designed **kickmix circuits**—a structured subclass composed of:
1. **Reversible classical logic** (X, CNOT, Toffoli, multi-controlled gates).
2. **Diagonal phase gates** ($Z$, $S$, $T$, arbitrary $R_z(\theta)$).
3. **Measurement-based uncomputation** (clean ancilla reset).

Because kickmix circuits map each computational basis state directly to a single output bitstring plus a phase, they can be classically fuzzed and verified at **tens of billions of operations per second** on a single CPU core.

### How `kickmix` is Integrated
* Google provides **`kickmix.so`** (precompiled C++20 shared library for Linux x86_64) inside the Kaggle competition dataset.
* In Step 2, the starter kit archive downloaded from Kaggle will be extracted into this project directory, allowing Python scripts to import `kickmix` directly.

---

## 4. Project Directory Layout (Planned)

```text
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/
├── .venv/                            # Python 3.10 virtual environment
├── README.md                         # This environment & setup documentation
├── config/                           # Compiler budgets, precision tolerances, fuzz shot counts
├── data/                             # Starter kit assets, baseline .kmb files, kickmix.so
│   ├── kickmix.so                    # Fast C++20 verification engine
│   ├── baseline_invsqrt.kmb          # Benchmark I reference circuit
│   ├── baseline_dqi.kmb              # Benchmark II reference circuit
│   └── dfthcsos/                     # Benchmark III chemistry Hamiltonians
├── src/
│   ├── core/                         # Circuit representations, .kmb parsers & serializers
│   ├── verifier/                     # Automated Kickmix fuzz-testing interface
│   ├── schedulers/                   # Pebble game & ancilla uncomputation reuse
│   ├── optimizers/                   # Reversible arithmetic synthesis & peephole rewrites
│   └── agent/                        # Closed-loop MCTS / Pareto optimization engine
├── tests/                            # Automated regression tests & verification invariants
└── run_compiler.py                   # Main CLI execution launcher
```

---

## 5. Verification Check

To confirm that the environment is working properly, run:
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "
import qualtran, cirq, galois, fxpmath, pyzx, quimb
print('Qualtran Bloq Framework: OK')
print('Cirq Version:', cirq.__version__)
print('Galois Finite Fields: OK')
print('Fxpmath Fixed-Point: OK')
print('PyZX Graph Rewriter: OK')
print('Quimb Tensor Networks: OK')
"
```
