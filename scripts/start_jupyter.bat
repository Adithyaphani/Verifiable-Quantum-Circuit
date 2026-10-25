@echo off
REM start_jupyter.bat - Launches JupyterLab inside WSL from Windows CMD
echo ==========================================================
echo Starting JupyterLab in WSL virtual environment...
echo Notebook: notebooks/submission_pipeline.ipynb
echo ==========================================================

wsl -e bash -c "cd /mnt/d/1-Projects/1-Verifiable-Quantum-Circuit && ./scripts/start_jupyter.sh"
pause
