# Quimb (`1.11.2`) & Cotengra (`0.8.3`)

## Overview
**Quimb** is a library for quantum information and tensor networks, paired with **Cotengra** for finding hyper-optimized contraction trees.

## Key Features & Competition Role
* **Benchmark III (FeMoCo Nitrogenase Chemistry Block Encodings)**:
  * Computes low-rank tensor factorizations (Double Factorization / Tensor Hypercontraction THC) for molecular Hamiltonians.
  * Optimizes Givens rotation trees and basis changes to minimize 2-qubit swap depth.
  * Analyzes tensor contraction overheads for block-encoding cost optimization ($\lambda \times T \times Q$).

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import quimb, cotengra; print('Quimb & Cotengra Tensor Networks: OK')"
```
