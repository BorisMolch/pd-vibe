#!/usr/bin/env python3
"""
Backward-compatible wrapper for documentation drift checks.

Deprecated: use `pd-docs drift` directly.

Examples:
    python check_docs.py /path/to/project/      # hash mode
    python check_docs.py /path/to/docs/ -t      # timestamp mode
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    local_pd_docs = Path(__file__).resolve().parent / 'pd-docs'
    cmd = [str(local_pd_docs), 'drift', *sys.argv[1:]]
    return subprocess.call(cmd)


if __name__ == '__main__':
    sys.exit(main())
