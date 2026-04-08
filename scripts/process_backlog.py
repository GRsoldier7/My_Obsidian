#!/usr/bin/env python3
"""
scripts/process_backlog.py
One-shot backlog processor — runs the brain dump pipeline immediately against
all files with real content. Use to clear the backlog accumulated since Mar 25.

Usage:
    python3 scripts/process_backlog.py
    python3 scripts/process_backlog.py --dry-run
"""
import os
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

def main():
    dry_run = "--dry-run" in sys.argv
    cmd = [sys.executable, str(REPO_ROOT / "tools" / "process_brain_dump.py")]
    if dry_run:
        cmd.append("--dry-run")
    cmd.append("--verbose")

    print("=== Backlog Processor ===")
    print(f"Running: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
