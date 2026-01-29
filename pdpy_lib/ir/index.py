"""
SQLite Indexing for Pure Data IR.

This module provides SQLite-based indexing for IR patches, enabling
efficient querying across multiple patches in a repository.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from .core import (
    IRPatch,
    IRNode,
    IREdge,
    IRSymbol,
    EdgeKind,
)


class IRIndex:
    """
    SQLite-based index for Pure Data IR.

    Provides persistent storage and querying capabilities for IR data
    across multiple patches.
    """

    SCHEMA_VERSION = "0.1"

    def __init__(self, db_path: str):
        """
        Initialize the IR index.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Get the database connection, creating if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_schema(self):
        """Create database schema if it doesn't exist."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Patches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patches (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                sha256 TEXT,
                graph_hash TEXT,
                ir_version TEXT,
                parsed_at DATETIME
            )
        ''')

        # Nodes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY,
                patch_id INTEGER REFERENCES patches(id) ON DELETE CASCADE,
                node_id TEXT NOT NULL,
                canvas_id TEXT,
                type TEXT,
                kind TEXT,
                domain TEXT,
                args_json TEXT,
                UNIQUE(patch_id, node_id)
            )
        ''')

        # Edges table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY,
                patch_id INTEGER REFERENCES patches(id) ON DELETE CASCADE,
                edge_id TEXT,
                kind TEXT,
                domain TEXT,
                from_node TEXT,
                from_port INTEGER,
                to_node TEXT,
                to_port INTEGER,
                symbol TEXT
            )
        ''')

        # Symbols table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY,
                resolved TEXT NOT NULL,
                kind TEXT,
                namespace TEXT,
                UNIQUE(resolved, kind, namespace)
            )
        ''')

        # Symbol endpoints table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS symbol_endpoints (
                id INTEGER PRIMARY KEY,
                symbol_id INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
                patch_id INTEGER REFERENCES patches(id) ON DELETE CASCADE,
                node_id TEXT,
                role TEXT
            )
        ''')

        # Comments FTS table
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS comments_fts USING fts5(
                patch_path, node_id, text
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_domain ON nodes(domain)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbols_resolved ON symbols(resolved)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_endpoints_symbol ON symbol_endpoints(symbol_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_endpoints_patch ON symbol_endpoints(patch_id)')

        conn.commit()

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def index_patch(self, ir_patch: IRPatch):
        """
        Index an IR patch into the database.

        Args:
            ir_patch: The IR patch to index
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        patch_path = ir_patch.patch.path if ir_patch.patch else "unknown"
        sha256 = ir_patch.patch.sha256 if ir_patch.patch else None
        graph_hash = ir_patch.patch.graph_hash if ir_patch.patch else None

        # Insert or update patch
        cursor.execute('''
            INSERT OR REPLACE INTO patches (path, sha256, graph_hash, ir_version, parsed_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (patch_path, sha256, graph_hash, ir_patch.ir_version, datetime.now().isoformat()))

        patch_id = cursor.lastrowid

        # Delete existing data for this patch
        cursor.execute('DELETE FROM nodes WHERE patch_id = ?', (patch_id,))
        cursor.execute('DELETE FROM edges WHERE patch_id = ?', (patch_id,))
        cursor.execute('DELETE FROM symbol_endpoints WHERE patch_id = ?', (patch_id,))
        cursor.execute('DELETE FROM comments_fts WHERE patch_path = ?', (patch_path,))

        # Insert nodes
        for node in ir_patch.nodes:
            cursor.execute('''
                INSERT INTO nodes (patch_id, node_id, canvas_id, type, kind, domain, args_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                patch_id,
                node.id,
                node.canvas,
                node.type,
                node.kind.value,
                node.domain.value,
                json.dumps(node.args),
            ))

        # Insert edges
        for edge in ir_patch.edges:
            cursor.execute('''
                INSERT INTO edges (patch_id, edge_id, kind, domain, from_node, from_port, to_node, to_port, symbol)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                patch_id,
                edge.id,
                edge.kind.value,
                edge.domain.value,
                edge.from_endpoint.node,
                edge.from_endpoint.outlet,
                edge.to_endpoint.node,
                edge.to_endpoint.inlet,
                edge.symbol,
            ))

        # Insert symbols and endpoints
        for symbol in ir_patch.symbols:
            # Insert or get symbol
            cursor.execute('''
                INSERT OR IGNORE INTO symbols (resolved, kind, namespace)
                VALUES (?, ?, ?)
            ''', (symbol.resolved, symbol.kind.value, symbol.namespace.value))

            cursor.execute('''
                SELECT id FROM symbols WHERE resolved = ? AND kind = ? AND namespace = ?
            ''', (symbol.resolved, symbol.kind.value, symbol.namespace.value))
            symbol_id = cursor.fetchone()[0]

            # Insert endpoints
            for writer in symbol.writers:
                cursor.execute('''
                    INSERT INTO symbol_endpoints (symbol_id, patch_id, node_id, role)
                    VALUES (?, ?, ?, ?)
                ''', (symbol_id, patch_id, writer.node, 'writer'))

            for reader in symbol.readers:
                cursor.execute('''
                    INSERT INTO symbol_endpoints (symbol_id, patch_id, node_id, role)
                    VALUES (?, ?, ?, ?)
                ''', (symbol_id, patch_id, reader.node, 'reader'))

        # Insert comments into FTS
        if ir_patch.text:
            for comment in ir_patch.text.comments:
                cursor.execute('''
                    INSERT INTO comments_fts (patch_path, node_id, text)
                    VALUES (?, ?, ?)
                ''', (patch_path, comment.node, comment.text))

        conn.commit()

    def remove_patch(self, patch_path: str):
        """Remove a patch from the index."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM patches WHERE path = ?', (patch_path,))
        row = cursor.fetchone()
        if row:
            patch_id = row[0]
            cursor.execute('DELETE FROM patches WHERE id = ?', (patch_id,))
            cursor.execute('DELETE FROM comments_fts WHERE patch_path = ?', (patch_path,))

        conn.commit()

    def get_patch_info(self, patch_path: str) -> Optional[Dict[str, Any]]:
        """Get stored information about a patch."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM patches WHERE path = ?', (patch_path,))
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def find_nodes_by_type(self, obj_type: str) -> List[Dict[str, Any]]:
        """Find all nodes of a given type across all patches."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT n.*, p.path as patch_path
            FROM nodes n
            JOIN patches p ON n.patch_id = p.id
            WHERE n.type = ?
        ''', (obj_type,))

        return [dict(row) for row in cursor.fetchall()]

    def find_nodes_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """Find all nodes of a given domain."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT n.*, p.path as patch_path
            FROM nodes n
            JOIN patches p ON n.patch_id = p.id
            WHERE n.domain = ?
        ''', (domain,))

        return [dict(row) for row in cursor.fetchall()]

    def find_symbol_endpoints(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Find all endpoints for a symbol."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT se.*, s.resolved, s.kind, s.namespace, p.path as patch_path
            FROM symbol_endpoints se
            JOIN symbols s ON se.symbol_id = s.id
            JOIN patches p ON se.patch_id = p.id
            WHERE s.resolved = ?
        ''', (symbol_name,))

        return [dict(row) for row in cursor.fetchall()]

    def find_cross_patch_symbols(self) -> List[Dict[str, Any]]:
        """Find symbols that connect multiple patches."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT s.resolved, s.kind, s.namespace,
                   GROUP_CONCAT(DISTINCT p.path) as patches,
                   COUNT(DISTINCT p.id) as patch_count
            FROM symbols s
            JOIN symbol_endpoints se ON s.id = se.symbol_id
            JOIN patches p ON se.patch_id = p.id
            GROUP BY s.id
            HAVING patch_count > 1
        ''')

        return [dict(row) for row in cursor.fetchall()]

    def search_comments(self, query: str) -> List[Dict[str, Any]]:
        """Search comments using FTS."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT patch_path, node_id, text
            FROM comments_fts
            WHERE text MATCH ?
        ''', (query,))

        return [dict(row) for row in cursor.fetchall()]

    def get_signal_path(self, from_node: str, to_node: str,
                        patch_path: str) -> List[List[str]]:
        """
        Find all signal paths between two nodes in a patch.

        Returns a list of paths, where each path is a list of node IDs.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Get patch ID
        cursor.execute('SELECT id FROM patches WHERE path = ?', (patch_path,))
        row = cursor.fetchone()
        if not row:
            return []
        patch_id = row[0]

        # Build adjacency list
        cursor.execute('''
            SELECT from_node, to_node
            FROM edges
            WHERE patch_id = ? AND kind = 'wire' AND domain = 'signal'
        ''', (patch_id,))

        adjacency = {}
        for row in cursor.fetchall():
            src, dst = row['from_node'], row['to_node']
            if src not in adjacency:
                adjacency[src] = []
            adjacency[src].append(dst)

        # DFS to find all paths
        paths = []

        def dfs(current: str, path: List[str]):
            if current == to_node:
                paths.append(path[:])
                return

            for neighbor in adjacency.get(current, []):
                if neighbor not in path:
                    path.append(neighbor)
                    dfs(neighbor, path)
                    path.pop()

        dfs(from_node, [from_node])
        return paths

    def get_symbol_flow(self, symbol_name: str) -> Dict[str, Any]:
        """
        Get the complete flow for a symbol across patches.

        Returns writers and readers organized by patch.
        """
        endpoints = self.find_symbol_endpoints(symbol_name)

        flow = {
            'symbol': symbol_name,
            'patches': {},
        }

        for ep in endpoints:
            patch = ep['patch_path']
            if patch not in flow['patches']:
                flow['patches'][patch] = {'writers': [], 'readers': []}

            if ep['role'] == 'writer':
                flow['patches'][patch]['writers'].append(ep['node_id'])
            else:
                flow['patches'][patch]['readers'].append(ep['node_id'])

        return flow

    def get_dependency_tree(self, patch_path: str) -> Dict[str, Any]:
        """
        Build a dependency tree for a patch.

        Shows what abstractions/externals the patch uses.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM patches WHERE path = ?', (patch_path,))
        row = cursor.fetchone()
        if not row:
            return {'patch': patch_path, 'dependencies': []}

        patch_id = row[0]

        # Find abstraction instances
        cursor.execute('''
            SELECT DISTINCT type
            FROM nodes
            WHERE patch_id = ? AND kind = 'abstraction_instance'
        ''', (patch_id,))

        abstractions = [row['type'] for row in cursor.fetchall()]

        # Find externals (objects with / in name)
        cursor.execute('''
            SELECT DISTINCT type
            FROM nodes
            WHERE patch_id = ? AND type LIKE '%/%'
        ''', (patch_id,))

        externals = [row['type'] for row in cursor.fetchall()]

        return {
            'patch': patch_path,
            'abstractions': abstractions,
            'externals': externals,
        }

    def get_reverse_deps(self, patch_path: str) -> List[str]:
        """
        Find patches that depend on a given patch (as abstraction).

        Returns list of patch paths that use this patch as an abstraction.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Extract the abstraction name from path
        abs_name = os.path.splitext(os.path.basename(patch_path))[0]

        cursor.execute('''
            SELECT DISTINCT p.path
            FROM nodes n
            JOIN patches p ON n.patch_id = p.id
            WHERE n.kind = 'abstraction_instance' AND n.type = ?
        ''', (abs_name,))

        return [row['path'] for row in cursor.fetchall()]

    def get_statistics(self) -> Dict[str, Any]:
        """Get index statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()

        stats = {}

        cursor.execute('SELECT COUNT(*) as count FROM patches')
        stats['patch_count'] = cursor.fetchone()['count']

        cursor.execute('SELECT COUNT(*) as count FROM nodes')
        stats['node_count'] = cursor.fetchone()['count']

        cursor.execute('SELECT COUNT(*) as count FROM edges')
        stats['edge_count'] = cursor.fetchone()['count']

        cursor.execute('SELECT COUNT(*) as count FROM symbols')
        stats['symbol_count'] = cursor.fetchone()['count']

        cursor.execute('''
            SELECT type, COUNT(*) as count
            FROM nodes
            GROUP BY type
            ORDER BY count DESC
            LIMIT 10
        ''')
        stats['top_object_types'] = [
            {'type': row['type'], 'count': row['count']}
            for row in cursor.fetchall()
        ]

        return stats


def create_index(db_path: str) -> IRIndex:
    """Create a new IR index."""
    return IRIndex(db_path)


def index_directory(directory: str, db_path: str,
                    pattern: str = "**/*.pd") -> IRIndex:
    """
    Index all .pd files in a directory.

    Args:
        directory: Directory to scan
        db_path: Path for the SQLite database
        pattern: Glob pattern for finding .pd files

    Returns:
        IRIndex instance
    """
    import glob
    from .build import build_ir_from_file

    index = IRIndex(db_path)

    pd_files = glob.glob(os.path.join(directory, pattern), recursive=True)

    for filepath in pd_files:
        try:
            ir = build_ir_from_file(filepath)
            index.index_patch(ir)
        except Exception as e:
            print(f"Error indexing {filepath}: {e}")

    return index
