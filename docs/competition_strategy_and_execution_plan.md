> **Status:** the invsqrt/DQI/chemistry generators in this repo are placeholders. They do not yet compute the required functions and would fail verification. Earlier 'verified' claims are unsupported.

# Google Quantum AI: Competition Analysis, Technical Strategy & Execution Plan

This document details the technical analysis of the **Google Quantum AI - Verifiable Quantum Circuit Compilation** Kaggle competition, the algorithmic foundations of each benchmark, the submission architecture, and our end-to-end execution roadmap.

---

## 1. Executive Summary & Strategic Positioning

* **Competition**: [Google Quantum AI - Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation)
* **Prize Pool**: $150,000 (Leaderboard prizes, Mid-Competition Milestone Prize ($10,000 per Kaggle; confirm) on Nov 20, 2026, and Longest Leader Prize on Jan 4, 2027)
* **Timeline**: October 22, 2026 – January 20, 2027
* **Core Paradigm**: Closed-loop agentic optimization of fault-tolerant quantum circuits using classical verification (Kickmix).

### Why the "No Starter Kit" Reality is an Advantage
Traditional machine learning challenges provide large static datasets and turnkey starter notebooks, resulting in rapid leaderboard saturation. Google Quantum AI has provided **no starter kit dataset** because this is an algorithmic synthesis and compiler engineering challenge.

Success depends on:
1. Understanding the mathematical structure of the three scientific bottlenecks.
2. Generating valid, verified Kickmix circuits (`.kmx` / `.kmb`).
3. Exploiting approximation tolerances ("asking the quantum computer to do less").
4. Developing autonomous search heuristics that optimize qubit count ($Q$) and Toffoli count ($T$).

---

## 2. Deep-Dive: The Three Scientific Benchmarks

Per the paper (arXiv:2610.23832v2) each benchmark has its own score S (lower is better). The paper defines no combined geometric-mean score; check the Kaggle Evaluation tab for how the leaderboard combines them.

```
                                  EVALUATION ENGINE
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
    [Benchmark I: Fusion]        [Benchmark II: DQI]       [Benchmark III: Chemistry]
     Fixed-point 1/√x Phasing     Reed-Solomon Decoders      FeMoCo Block Encodings
     S = Q × C  (C = Toffolis + T/4; Z_POW costs 0.56·log2(1/ε)+5.3 T each)                S = R(ε⁺) × Q² × T,  R = ln2 / −ln(1/2 + 2√ε⁺)       Cost = λ_eff × Q_tot × T_tot
```

---

### Benchmark I: Fusion Energy (`1/√x` Phasing)

* **Physical Context**: Modeling alpha-particle stopping power in warm dense plasmas for inertial confinement fusion (PNAS 2024). Requires applying diagonal phase angles proportional to the Coulomb interaction potential $V(r) \propto 1/r = 1/\sqrt{x}$, where $x = \Delta x^2 + \Delta y^2 + \Delta z^2$.
* **Cost Metric**: 
  $$S = Q \times C,\quad C = \text{Toffolis} + T/4$$
  * $Q$: Physical qubit count per shot.
  * $T$: Toffoli gate count per shot.
* **Key Optimization Insights**:
  * **Qubit penalty**: Benchmark I is linear in Q (S = Q × C); the Q² term belongs to Benchmark II. Official reference: Q=260, 7,735 Toffolis, S≈2.08×10⁶ in the benchmark score.
  * **Ancilla Recycling (Pebble Game)**: Intermediate scratch registers must be immediately uncomputed and reused in-place rather than allocating fresh ancillae.
  * **Approximation Bounds**: The phase does not require exact floating-point division. Fixed-point polynomial approximations (Chebyshev economization or 1–2 Goldschmidt iterations) can achieve the required physical stopping-power accuracy with dramatically fewer Toffoli gates.

---

### Benchmark II: Combinatorial Optimization (Decoded Quantum Interferometry / DQI)

* **Physical Context**: Solving the Optimal Polynomial Intersection problem over finite fields using Decoded Quantum Interferometry (Nature 2025, arXiv:2510.10967). The bottleneck subroutine is a reversible Reed-Solomon syndrome decoder.
* **Cost Metric**:
  $$S = R(\epsilon^+)\, Q^2\, T,\quad R=\frac{\ln 2}{-\ln(1/2+2\sqrt{\epsilon^+})}$$
  * $\epsilon^+$: Upper confidence bound on decoder failure rate.
  * $R(\epsilon^+)$: Repetition factor compensating for decoder failures.
  * $Q$: Qubit count; $T$: Toffoli count per shot.
* **Key Optimization Insights**:
  * **Failure-Rate vs. Gate Count Trade-Off**: Traditional decoders implement full Extended Euclidean Algorithm (EEA) systolic arrays to achieve $\epsilon^+ \to 0$. However, if an approximated decoder cuts $T$ by 60% while only slightly increasing $\epsilon^+$, the repetition overhead $R(\epsilon^+)$ will be outweighed by the gate savings.
  * **Galois Field ($\text{GF}(2^m)$) Synthesis**: Synthesizing finite-field multiplication and inversion with minimal scratch ancillae.

---

### Benchmark III: Quantum Chemistry & Clean Energy (FeMoCo Block Encodings)

* **Physical Context**: Simulating the electronic structure of the Iron-Molybdenum cofactor (FeMoCo)—the catalytic active site of nitrogenase responsible for biological nitrogen fixation (PNAS 2017, PRX 2025). Industrial Haber-Bosch fertilizer synthesis consumes ~2% of global energy.
* **Cost Metric**:
  $$\text{Cost} = \lambda_{\text{eff}} \times Q_{\text{total}} \times T_{\text{total}}$$
  * $\lambda_{\text{eff}}$: 1-norm of the Hamiltonian block encoding (dictates simulation time).
  * **Hard Constraint**: Any submitted ANGLE circuit wider than **128 qubits is rejected**.
* **Key Optimization Insights**:
  * **Classical/Quantum Co-Optimization**: Competitors submit both classical factorizations (`submission.npz`) and quantum Givens trees (`angle_k_*.kmb`/`.kmx`).
  * **Tensor Rank Truncation**: Truncating small eigenvalues in the Double Factorization (DF-THC) tensor tensors $U, W$ directly reduces the number of Givens rotation circuits $n$ without exceeding chemical accuracy (the paper's 0.020 Ha residual limits).
  * **QROM Table Lookups**: Packing rotation angles into unary iteration QROMs with dirty ancilla borrowing.

---

## 3. The Kickmix Circuit Architecture (`.kmx` & `.kmb`)

Kickmix circuits circumvent the exponential scaling of quantum state simulation by restricting operations to basis-preserving gates:

1. **Reversible Classical Logic**:
   * Bit flips: `X(target)`
   * Controlled bit flips: `CX(control, target)`, `CCX(c1, c2, target)` (Toffoli), multi-controlled `MCX`.
   * Swaps: `SWAP(q1, q2)`.
2. **Diagonal Phase Operations**:
   * Phase gates: $Z$, $S$, $T$, and arbitrary diagonal rotations $R_z(\theta)$ applied conditionally to basis states.
3. **Clean Measurement & Uncomputation**:
   * Scratch qubits must be returned to $|0\rangle$ so they can be reused without entangling garbage into the computation.

### File Format Differences:
* **`.kmx` (Human-Readable Text Format)**:
  * Plain text instruction lists specifying gate opcodes, control qubits, target qubits, and angle parameters.
  * **Advantage**: Can be directly generated and manipulated via pure Python scripts.
* **`.kmb` (Binary Serialization)**:
  * Packed struct-of-arrays representation for fast C++ memory-mapped I/O.
  * Qualtran and Kickmix support both formats interchangeably.

---

## 4. Submission Package Specification

Every valid submission to Kaggle must be a single `.zip` file with the exact following structure:

```text
submission.zip
├── invsqrt.kmb (or invsqrt.kmx)
├── dqi.kmb (or dqi.kmx)
└── dfthcsos/
    ├── angle_k_0.kmb (or angle_k_0.kmx)
    ├── angle_k_1.kmb (or angle_k_1.kmx)
    ├── ...
    ├── angle_k_<n-1>.kmb (or angle_k_<n-1>.kmx)
    └── submission.npz
```

* **Constraints**:
  * In `dfthcsos/`, files must be numbered sequentially from `0` to `n-1` with no gaps.
  * `submission.npz` must contain keys: `U`, `W`, `H2_I`, `H1_I`, `Hsym_lower`, and `tree_edges`.
  * Every ANGLE circuit must have width $\le 128$ qubits.
  * Scoring execution takes approximately 45 minutes on Kaggle's evaluation workers.

---

## 5. Step 2 & Beyond: Architecture & Execution Roadmap

```
Phase 1: Foundation (Current Step 2)
├── Build Kickmix Circuit AST & .kmx Serializer (src/core/kickmix_ast.py)
├── Implement Reversible Arithmetic Primitives (Adders, Multipliers, In-place Subtraction)
└── Create Automated Submission Packager & Format Validator

Phase 2: Benchmark I Attack (invsqrt)
├── Fixed-Point Error Simulator & Precision Allocator (using fxpmath)
├── Synthesize Goldschmidt & Chebyshev 1/√x Reversible Circuits
├── Implement Pebble Game Ancilla Scheduler (Minimizing Q²)
└── Generate & Validate First Competitive invsqrt.kmx

Phase 3: Benchmark II Attack (dqi)
├── Galois Field GF(2^m) Arithmetic Synthesizer (using galois)
├── Reversible Reed-Solomon Extended Euclidean Algorithm (EEA)
└── Optimize Failure Rate ε⁺ vs. Toffoli Trade-off

Phase 4: Benchmark III Attack (dfthcsos)
├── Classical Tensor Rank Truncation & Chemistry Hamiltonian Parsing
├── Givens Rotation Tree Scheduler (width ≤ 128 qubits)
└── Generate submission.npz and angle_k_*.kmx sub-circuits

Phase 5: Agentic Search Loop
├── Multi-operator Peephole Optimizer (Toffoli cancellation, phase merging)
└── Monte Carlo Tree Search (MCTS) exploring the Pareto frontier
```

---

## 6. Verification Checklist for Submissions

Before producing any `.zip` artifact for submission, verify:
- [ ] `invsqrt.kmx` compiles, runs on classical inputs, and scratch qubits are fully uncomputed.
- [ ] `dqi.kmx` passes finite-field syndrome decoding tests with error rate $\le \epsilon^+$.
- [ ] All `angle_k_*.kmx` circuits have width $\le 128$ qubits.
- [ ] `dfthcsos/submission.npz` contains all 6 required array keys.
- [ ] `submission.zip` root directory contains no extraneous parent folders.
