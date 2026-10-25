#!/usr/bin/env bash
# start_jupyter.sh - Launches JupyterLab using the project venv
set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Set runtime dir to /tmp so POSIX 0600 permissions succeed on Linux ext4
# (Windows NTFS mounts under /mnt/d/ do not support POSIX 0600 permissions)
RUNTIME_DIR="/tmp/jupyter_runtime_${USER:-default}"
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR" 2>/dev/null || true

export JUPYTER_RUNTIME_DIR="$RUNTIME_DIR"
export JUPYTER_DATA_DIR="$PROJECT_ROOT/.jupyter/data"
export JUPYTER_CONFIG_DIR="$PROJECT_ROOT/.jupyter/config"
mkdir -p "$JUPYTER_DATA_DIR" "$JUPYTER_CONFIG_DIR"

echo "=========================================================="
echo "Starting JupyterLab for Verifiable Quantum Circuit..."
echo "Runtime Directory: $JUPYTER_RUNTIME_DIR"
echo "Notebook Path:     notebooks/submission_pipeline.ipynb"
echo "=========================================================="
exec "$PROJECT_ROOT/.venv/bin/jupyter" lab --ip=0.0.0.0 --port=8888 --no-browser "$@"
