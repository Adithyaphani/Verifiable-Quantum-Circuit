# Cirq & Cirq-Google (`1.5.0`)

## Overview
**Cirq** is Google's open-source library for creating, editing, and invoking Noisy Intermediate Scale Quantum (NISQ) and fault-tolerant quantum circuits.

## Key Features & Competition Role
* **Circuit Representation**: Native representation of qubits, moments, gate operations, and circuit diagrams.
* **Gate Synthesis**: Reversible gate decompositions (CNOT, Toffoli, multi-controlled X, Phase, $T$, $S$).
* **Interop with Qualtran**: Seamless translation between Qualtran Bloqs and executable Cirq circuits.
* **Validation**: Used for circuit structure verification, unit testing, and circuit graph export.

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import cirq; print('Cirq Version:', cirq.__version__)"
```
