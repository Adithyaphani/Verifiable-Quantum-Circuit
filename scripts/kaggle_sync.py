#!/usr/bin/env python3
"""
Kaggle Kernel Workflow Sync Helper.

Automates exporting outputs, pulling code, and checking status
using either the modern Kaggle Access Token (KGAT_...) or traditional credentials.

Usage:
    python scripts/kaggle_sync.py output gbhanuteja23/notebook2d8aff629d -p data/kaggle_outputs
    python scripts/kaggle_sync.py status gbhanuteja23/notebook2d8aff629d
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path


def get_access_token() -> str:
    """Finds the Kaggle Access Token (KGAT_...) from environment or files."""
    # 1. Environment variable
    if "KAGGLE_API_TOKEN" in os.environ:
        return os.environ["KAGGLE_API_TOKEN"].strip()
    if "KAGGLE_KEY" in os.environ and os.environ["KAGGLE_KEY"].startswith("KGAT_"):
        return os.environ["KAGGLE_KEY"].strip()

    # 2. Project local credential directory only (strictly confined to project)
    project_root = Path(__file__).resolve().parent.parent
    token_files = [
        project_root / ".kaggle" / "access_token",
        project_root / ".kaggle" / "kaggle.json",
    ]


    for p in token_files:
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8").strip()
                if content.startswith("KGAT_"):
                    return content
                # Check if it's a JSON with key
                data = json.loads(content)
                key = data.get("key", "")
                if key.startswith("KGAT_"):
                    return key
            except Exception:
                pass

    return ""


def download_kernel_outputs(kernel_slug: str, dest_dir: Path, token: str):
    """Downloads all output files for a kernel using Kaggle's Bearer auth API."""
    if "/" not in kernel_slug:
        raise ValueError(f"Kernel slug must be in format 'username/kernel-name', got: '{kernel_slug}'")

    username, kernelslug = kernel_slug.split("/", 1)
    url = f"https://www.kaggle.com/api/v1/kernels/output?username={username}&kernelslug={kernelslug}"

    headers = {"Authorization": f"Bearer {token}"}
    print(f"Connecting to Kaggle API for kernel '{kernel_slug}'...")
    res = requests.get(url, headers=headers)

    if res.status_code == 401:
        raise PermissionError("401 Unauthorized: The Kaggle Access Token was rejected. Check your token.")
    elif res.status_code == 403:
        raise PermissionError(f"403 Forbidden: No access to outputs for '{kernel_slug}'.")
    elif res.status_code != 200:
        raise RuntimeError(f"API Error ({res.status_code}): {res.text}")

    data = res.json()
    files = data.get("files", [])
    if not files:
        print(f"No output files found yet for '{kernel_slug}'. (Has the kernel finished running?)")
        if data.get("log"):
            print("Recent Kernel Logs:")
            print(data["log"][-500:])
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nFound {len(files)} output file(s). Downloading to '{dest_dir.resolve()}':")

    for f_info in files:
        filename = f_info.get("fileName")
        file_url = f_info.get("url")
        if not filename or not file_url:
            continue

        out_path = dest_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"  ⬇ Downloading {filename}...", end="", flush=True)
        r = requests.get(file_url, stream=True)
        if r.status_code == 200:
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f" Done ({out_path.stat().st_size} bytes)")
        else:
            print(f" Failed (HTTP {r.status_code})")

    print("\n✓ All output artifacts exported successfully!")


def main():
    parser = argparse.ArgumentParser(description="Kaggle Output Exporter")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    out_p = subparsers.add_parser("output", help="Download kernel output files")
    out_p.add_argument("kernel", default="gbhanuteja23/notebook2d8aff629d", nargs="?", help="Kernel slug")
    out_p.add_argument("-p", "--path", default="data/kaggle_outputs", help="Output path")

    args = parser.parse_args()

    token = get_access_token()
    if not token:
        print("ERROR: Kaggle Access Token not found.")
        print("Place your token in ~/.kaggle/access_token or set KAGGLE_API_TOKEN.")
        sys.exit(1)

    if args.command == "output":
        download_kernel_outputs(args.kernel, Path(args.path), token)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
