# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Offline documentation through ordinary pytest discovery."""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    docs = commands.add_parser("docs", help="Collect Python declarations without connecting to a slave")
    docs.add_argument("paths", nargs="*", help="Pytest test paths or node IDs")
    docs.add_argument("--output", type=Path, required=True)
    args, pytest_args = parser.parse_known_args()
    # A fresh pytest process preserves its ordinary assertion-rewriting startup.
    return subprocess.call([sys.executable, "-m", "pytest", *args.paths, *pytest_args,
                            "--collect-only", "--tzen-offline", f"--tzen-docs={args.output}"])


if __name__ == "__main__":
    raise SystemExit(main())
