# Qualtran (`0.7.0`)

## Overview
**Qualtran** is Google Quantum AI's open-source Python framework for expressing, analyzing, and resource-estimating fault-tolerant quantum algorithms.

## Key Features & Competition Role
* **Bloq Abstraction**: Represents quantum operations with well-defined signatures, classical registers, and quantum registers (`QBit`, `QUInt`, `QFxp`).
* **Resource Estimation**: Provides automated gate counts ($T$-count, Toffoli count, Clifford volume, rotation synthesis costs).
* **Bloq Decompositions**: Enables recursive decomposition from high-level algorithms down to fault-tolerant basis gates.
* **Kickmix Synergy**: Serves as the high-level representation layer from which Kickmix verifiable circuits are constructed and compiled.

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import qualtran; print('Qualtran Bloq Framework: OK')"
```
