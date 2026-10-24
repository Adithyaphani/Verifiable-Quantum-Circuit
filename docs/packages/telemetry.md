# Telemetry & Analysis Stack

## Core Libraries
* **`matplotlib`** (`3.10.9`) & **`plotly`** (`7.1.0`): Multi-panel scientific diagnostic plots, Pareto frontier curves ($Q$ vs $T$), and resource convergence profiles.
* **`dash`** (`4.4.1`): Local live dashboard for monitoring compilation agent exploration.
* **`pydantic`** (`2.14.1`): Strict typing and schema validation for compiler configuration files and submission manifests.

## Verification
```bash
/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.venv/bin/python -c "import matplotlib, plotly, pydantic; print('Telemetry & Validation: OK')"
```
