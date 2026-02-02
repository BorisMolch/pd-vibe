#!/usr/bin/env python3
"""
Check if documentation is stale vs. source patches using content hashes.

Usage:
    python check_docs.py /path/to/project/    # Project with .pd-docs/refs.json
    python check_docs.py /path/to/docs/ -t    # Timestamp-only mode (no refs.json)

Compares content hashes from refs.json against current .pd file state.
"""

import sys
import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add pdpy_lib to path for IR parsing
sys.path.insert(0, str(Path(__file__).parent))

def compute_node_hash(node: dict, edges_out: list) -> str:
    """Compute content hash for a node (type + args + connections)."""
    # Handle both old (source/target) and new (from/to) edge formats
    connections = []
    for e in edges_out:
        if 'from' in e and 'to' in e:
            # New format: {from: {node, outlet}, to: {node, inlet}}
            connections.append((e['from']['outlet'], e['to']['node'], e['to']['inlet']))
        elif 'source_port' in e:
            # Old format
            connections.append((e['source_port'], e['target'], e['target_port']))

    content = {
        'type': node.get('type', ''),
        'args': node.get('args', []),
        'connections': sorted(connections)
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:12]


def load_refs(project_dir: Path) -> dict:
    """Load refs.json from .pd-docs directory."""
    refs_path = project_dir / '.pd-docs' / 'refs.json'
    if not refs_path.exists():
        return {}
    with open(refs_path) as f:
        return json.load(f)


def parse_patch_for_hashes(pd_path: Path) -> dict:
    """Parse a .pd file and compute hashes for all nodes."""
    try:
        from pdpy_lib.patching.pdpy import PdPy
        from pdpy_lib.utilities.utils import loadPdFile, parsePdFileLines

        # Load and parse with PdPy
        raw = loadPdFile(str(pd_path))
        pd_lines = parsePdFileLines(raw)
        pdpy = PdPy(name=pd_path.stem, pd_lines=pd_lines)
        ir = pdpy.to_ir(patch_path=str(pd_path))
        ir_data = ir.to_dict()

        # Build node hash map keyed by position
        node_hashes = {}
        patch_name = pd_path.stem

        # Build edge lookup - handle both formats
        edges_by_source = defaultdict(list)
        for edge in ir_data.get('edges', []):
            if 'from' in edge:
                # New format
                source_id = edge['from']['node']
            else:
                # Old format
                source_id = edge.get('source', '')
            edges_by_source[source_id].append(edge)

        for node in ir_data.get('nodes', []):
            node_id = node.get('id', '')
            obj_type = node.get('type', '')
            args = node.get('args', [])
            x = node.get('x', 0)
            y = node.get('y', 0)
            canvas = node.get('canvas', 'c0')

            # Compute hash like pd-docs does
            edges_out = edges_by_source.get(node_id, [])
            h = compute_node_hash(node, edges_out)

            key = f"{patch_name}::{canvas}@{x},{y}"
            node_hashes[key] = {
                'hash': h,
                'type': obj_type,
                'node_id': node_id
            }

        return node_hashes
    except Exception as e:
        return {'_error': str(e)}


def check_with_hashes(project_dir: Path, verbose: bool = False):
    """Check docs using refs.json hash comparison."""
    refs = load_refs(project_dir)
    if not refs:
        print(f"No .pd-docs/refs.json found in {project_dir}")
        print("Run: pd-docs init <project> first, or use -t for timestamp mode")
        return 1

    # Group refs by patch file
    patches = defaultdict(list)
    for ref_key, ref_data in refs.items():
        patches[ref_data['patch']].append((ref_key, ref_data))

    stale_patches = {}
    ok_count = 0
    missing_patches = []

    for patch_path, ref_list in patches.items():
        pd_path = Path(patch_path)
        if not pd_path.exists():
            doc_file = ref_list[0][1].get('doc_file', 'unknown')
            missing_patches.append((doc_file, patch_path))
            continue

        # Parse current state
        current_hashes = parse_patch_for_hashes(pd_path)
        if '_error' in current_hashes:
            if verbose:
                print(f"  Error parsing {pd_path.name}: {current_hashes['_error']}")
            continue

        # Compare hashes
        changed_nodes = []
        for ref_key, ref_data in ref_list:
            if ref_key in current_hashes:
                if current_hashes[ref_key]['hash'] != ref_data['hash']:
                    changed_nodes.append({
                        'ref_key': ref_key,
                        'type': ref_data['obj_type'],
                        'old_hash': ref_data['hash'],
                        'new_hash': current_hashes[ref_key]['hash']
                    })

        if changed_nodes:
            doc_file = ref_list[0][1].get('doc_file', 'unknown')
            stale_patches[doc_file] = {
                'patch': pd_path.name,
                'changed': changed_nodes
            }
        else:
            ok_count += 1

    # Report
    print(f"\n📊 Documentation Status (hash-based): {project_dir}")
    print("=" * 60)

    if stale_patches:
        print(f"\n⚠️  STALE ({len(stale_patches)} docs - content changed):")
        for doc_file, info in stale_patches.items():
            print(f"   {doc_file} ({info['patch']})")
            if verbose:
                for node in info['changed'][:5]:  # Show first 5
                    print(f"      - {node['type']}: {node['old_hash']} → {node['new_hash']}")
                if len(info['changed']) > 5:
                    print(f"      ... and {len(info['changed']) - 5} more")

    if missing_patches:
        print(f"\n❌ MISSING SOURCE ({len(missing_patches)} patches):")
        for doc_file, patch_path in missing_patches:
            print(f"   {doc_file} -> {patch_path}")

    print(f"\n✅ OK: {ok_count} docs up-to-date")

    return len(stale_patches) + len(missing_patches)


def check_with_timestamps(docs_dir: Path, verbose: bool = False):
    """Fallback: check using file timestamps only."""
    stale = []
    ok = []
    missing = []

    for md_file in docs_dir.glob("*.md"):
        content = md_file.read_text()
        match = re.search(r'<!-- pd-docs: (.+?) -->', content)
        if not match:
            continue

        pd_path = Path(match.group(1))
        if not pd_path.exists():
            missing.append((md_file.name, str(pd_path)))
            continue

        doc_mtime = md_file.stat().st_mtime
        pd_mtime = pd_path.stat().st_mtime

        if pd_mtime > doc_mtime:
            stale.append((md_file.name, pd_path.name,
                         datetime.fromtimestamp(pd_mtime),
                         datetime.fromtimestamp(doc_mtime)))
        else:
            ok.append(md_file.name)

    print(f"\n📊 Documentation Status (timestamp-based): {docs_dir}")
    print("=" * 60)

    if stale:
        print(f"\n⚠️  STALE ({len(stale)} files - source newer):")
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
        print("Usage: python check_docs.py /path/to/project/")
        print("       python check_docs.py /path/to/docs/ -t  (timestamp mode)")
        sys.exit(1)

    target = Path(sys.argv[1])
    verbose = "-v" in sys.argv
    timestamp_mode = "-t" in sys.argv

    if timestamp_mode:
        # Timestamp mode - target is docs directory
        exit_code = check_with_timestamps(target, verbose)
    else:
        # Hash mode - target is project directory with .pd-docs/
        exit_code = check_with_hashes(target, verbose)

    sys.exit(1 if exit_code > 0 else 0)
