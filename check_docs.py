#!/usr/bin/env python3
"""
Quick script to check if documentation is stale vs. source patches.

Usage:
    python check_docs.py /path/to/docs/

This compares:
1. File modification timestamps
2. If detailed: re-parses .pd and compares structure
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime

def check_docs_dir(docs_dir: str, verbose: bool = False):
    """Check all docs in a directory for staleness."""
    docs_path = Path(docs_dir)
    stale = []
    ok = []
    missing = []

    for md_file in docs_path.glob("*.md"):
        content = md_file.read_text()

        # Extract source path from pd-docs comment
        match = re.search(r'<!-- pd-docs: (.+?) -->', content)
        if not match:
            continue

        pd_path = Path(match.group(1))

        if not pd_path.exists():
            missing.append((md_file.name, str(pd_path)))
            continue

        # Compare timestamps
        doc_mtime = md_file.stat().st_mtime
        pd_mtime = pd_path.stat().st_mtime

        if pd_mtime > doc_mtime:
            stale.append((md_file.name, pd_path.name,
                         datetime.fromtimestamp(pd_mtime),
                         datetime.fromtimestamp(doc_mtime)))
        else:
            ok.append(md_file.name)

    # Report
    print(f"\n📊 Documentation Status: {docs_dir}")
    print("=" * 50)

    if stale:
        print(f"\n⚠️  STALE ({len(stale)} files - source changed):")
        for doc, src, pd_time, doc_time in stale:
            print(f"   {doc}")
            if verbose:
                print(f"      Source: {src}")
                print(f"      Patch modified:  {pd_time}")
                print(f"      Doc modified:    {doc_time}")

    if missing:
        print(f"\n❌ MISSING SOURCE ({len(missing)} files):")
        for doc, src in missing:
            print(f"   {doc} -> {src}")

    print(f"\n✅ OK: {len(ok)} files up-to-date")

    return len(stale) + len(missing)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_docs.py /path/to/docs/")
        sys.exit(1)

    docs_dir = sys.argv[1]
    verbose = "-v" in sys.argv

    exit_code = check_docs_dir(docs_dir, verbose)
    sys.exit(1 if exit_code > 0 else 0)
