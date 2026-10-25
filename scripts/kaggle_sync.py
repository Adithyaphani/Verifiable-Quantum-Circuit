#!/usr/bin/env python3
"""
Kaggle Kernel Workflow Sync Helper.

Automates exporting outputs, pulling code, and pushing notebook versions
between local workspace and Kaggle using the Kaggle API.

Usage:
    # 1. Export outputs from Kaggle to local system:
    python scripts/kaggle_sync.py output gbhanuteja23/notebook2d8aff629d -p data/kaggle_outputs

    # 2. Pull kernel code/metadata from Kaggle:
    python scripts/kaggle_sync.py pull gbhanuteja23/notebook2d8aff629d -p notebooks/

    # 3. Check status:
    python scripts/kaggle_sync.py status gbhanuteja23/notebook2d8aff629d
"""

import os
import sys
import argparse
from pathlib import Path


def configure_kaggle_environment():
    """Locates kaggle.json across common locations and sets KAGGLE_CONFIG_DIR."""
    # Possible locations for kaggle.json
    candidates = [
        Path.cwd() / ".kaggle" / "kaggle.json",
        Path("/mnt/d/1-Projects/1-Verifiable-Quantum-Circuit/.kaggle/kaggle.json"),
        Path("/mnt/c/Users/gbhan/.kaggle/kaggle.json"),
        Path(os.path.expanduser("~/.kaggle/kaggle.json")),
    ]

    for candidate in candidates:
        if candidate.exists():
            os.environ["KAGGLE_CONFIG_DIR"] = str(candidate.parent)
            print(f"[AUTH] Using Kaggle credentials from: {candidate}")
            return True

    # If environment variables already set
    if "KAGGLE_USERNAME" in os.environ and "KAGGLE_KEY" in os.environ:
        print("[AUTH] Using Kaggle credentials from environment variables.")
        return True

    # Default to local .kaggle directory in workspace
    local_kaggle = Path.cwd() / ".kaggle"
    local_kaggle.mkdir(parents=True, exist_ok=True)
    os.environ["KAGGLE_CONFIG_DIR"] = str(local_kaggle)
    return False


def main():
    parser = argparse.ArgumentParser(description="Kaggle Kernel Output & Sync Helper")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: output
    output_parser = subparsers.add_parser("output", help="Download output files from a Kaggle kernel")
    output_parser.add_argument("kernel", default="gbhanuteja23/notebook2d8aff629d", nargs="?", help="Kernel slug (user/kernel-name)")
    output_parser.add_argument("-p", "--path", default="data/kaggle_outputs", help="Destination path")

    # Command: pull
    pull_parser = subparsers.add_parser("pull", help="Pull notebook and metadata from Kaggle")
    pull_parser.add_argument("kernel", default="gbhanuteja23/notebook2d8aff629d", nargs="?", help="Kernel slug")
    pull_parser.add_argument("-p", "--path", default="notebooks", help="Destination directory")

    # Command: status
    status_parser = subparsers.add_parser("status", help="Check kernel status on Kaggle")
    status_parser.add_argument("kernel", default="gbhanuteja23/notebook2d8aff629d", nargs="?", help="Kernel slug")

    args = parser.parse_args()

    has_creds = configure_kaggle_environment()

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
    except Exception as e:
        print("\n" + "=" * 65)
        print("ERROR: Kaggle Authentication Failed")
        print("=" * 65)
        print(f"Details: {e}\n")
        print("To enable Kaggle CLI access:")
        print("1. Go to https://www.kaggle.com/settings")
        print("2. In the 'API' section, click 'Create New Token'.")
        print("3. Download kaggle.json and place it at:")
        print("     - In Windows: C:\\Users\\gbhan\\.kaggle\\kaggle.json")
        print("     - In Project: D:\\1-Projects\\1-Verifiable-Quantum-Circuit\\.kaggle\\kaggle.json")
        print("     - Or set environment variables: KAGGLE_USERNAME and KAGGLE_KEY")
        print("=" * 65)
        sys.exit(1)

    kernel_name = getattr(args, "kernel", "gbhanuteja23/notebook2d8aff629d")
    dest_path = getattr(args, "path", "data/kaggle_outputs")

    if args.command == "output":
        dest_dir = Path(dest_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"Downloading outputs for '{kernel_name}' to '{dest_dir.resolve()}'...")
        api.kernels_output_cli(kernel_name, path=str(dest_dir))
        print("✓ Outputs downloaded successfully!")
        for f in dest_dir.iterdir():
            print(f"  - {f.name} ({f.stat().st_size} bytes)")

    elif args.command == "pull":
        dest_dir = Path(dest_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"Pulling code for '{kernel_name}' to '{dest_dir.resolve()}'...")
        api.kernels_pull_cli(kernel_name, path=str(dest_dir))
        print("✓ Kernel pulled successfully!")

    elif args.command == "status":
        print(f"Checking status for '{kernel_name}'...")
        status = api.kernels_status_cli(kernel_name)
        print(f"Status: {status}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
