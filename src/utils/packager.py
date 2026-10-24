"""
Submission Packager & Validator for Google Quantum AI Kaggle Competition.

Validates that all three benchmarks are present, compliant with structural constraints,
and packages them into a submission.zip archive ready for the Kaggle evaluation workers.
"""

import os
import zipfile
import numpy as np
from pathlib import Path
from typing import Tuple, List, Dict, Any


REQUIRED_NPZ_KEYS = {"U", "W", "H2_I", "H1_I", "Hsym_lower", "tree_edges"}
MAX_ALLOWED_QUBITS = 128


def validate_submission_directory(staging_dir: str) -> Tuple[bool, List[str]]:
    """
    Validates a staging directory against all official competition requirements.
    
    Returns:
        (is_valid, list_of_errors_or_warnings)
    """
    staging_path = Path(staging_dir)
    errors = []

    # 1. Check Benchmark I: invsqrt
    has_invsqrt = (staging_path / "invsqrt.kmx").exists() or (staging_path / "invsqrt.kmb").exists()
    if not has_invsqrt:
        errors.append("Missing Benchmark I circuit: 'invsqrt.kmx' or 'invsqrt.kmb'.")

    # 2. Check Benchmark II: dqi
    has_dqi = (staging_path / "dqi.kmx").exists() or (staging_path / "dqi.kmb").exists()
    if not has_dqi:
        errors.append("Missing Benchmark II circuit: 'dqi.kmx' or 'dqi.kmb'.")

    # 3. Check Benchmark III: dfthcsos folder
    dfthcsos_dir = staging_path / "dfthcsos"
    if not dfthcsos_dir.is_dir():
        errors.append("Missing Benchmark III folder: 'dfthcsos/'.")
    else:
        # Check submission.npz
        npz_file = dfthcsos_dir / "submission.npz"
        if not npz_file.exists():
            errors.append("Missing 'dfthcsos/submission.npz'.")
        else:
            try:
                data = np.load(npz_file)
                missing_keys = REQUIRED_NPZ_KEYS - set(data.files)
                if missing_keys:
                    errors.append(f"'dfthcsos/submission.npz' is missing required keys: {missing_keys}")
            except Exception as e:
                errors.append(f"Failed to load 'dfthcsos/submission.npz': {str(e)}")

        # Check sequential angle_k_i files
        angle_files = sorted(list(dfthcsos_dir.glob("angle_k_*")))
        if not angle_files:
            errors.append("No 'angle_k_*' circuits found in 'dfthcsos/'.")
        else:
            indices = []
            for f in angle_files:
                stem = f.stem  # e.g. angle_k_0
                parts = stem.split("_")
                if len(parts) >= 3 and parts[-1].isdigit():
                    indices.append(int(parts[-1]))
            indices.sort()
            # Check numbered from 0 with no gaps
            if indices and (indices[0] != 0 or indices != list(range(len(indices)))):
                errors.append(f"Angle circuits in 'dfthcsos/' must be numbered from 0 with no gaps. Found: {indices[:10]}...")

    is_valid = len(errors) == 0
    return is_valid, errors


def create_submission_zip(staging_dir: str, output_zip_path: str) -> str:
    """
    Packages the staging directory contents into a compliant submission.zip archive.
    """
    is_valid, errors = validate_submission_directory(staging_dir)
    if not is_valid:
        error_msg = "\n  - ".join(errors)
        raise ValueError(f"Submission directory validation failed with {len(errors)} error(s):\n  - {error_msg}")

    staging_path = Path(staging_dir)
    output_path = Path(output_zip_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(staging_path):
            for file in files:
                full_path = Path(root) / file
                # Relative path inside zip
                rel_path = full_path.relative_to(staging_path)
                zipf.write(full_path, arcname=str(rel_path))

    return str(output_path.resolve())
