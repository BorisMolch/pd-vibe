"""
Symbol Extraction and Global Symbol Table for Pure Data IR.

This module handles extraction of send/receive, throw/catch, value, and other
symbol-mediated communication from Pure Data patches, and builds a global
symbol table for cross-file resolution.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict
import json
import re

from .core import (
    IRSymbol,
    IRSymbolEndpoint,
    IREdge,
    IREdgeEndpoint,
    EdgeKind,
    Domain,
    SymbolKind,
    SymbolNamespace,
)
from .registry import get_registry


@dataclass
class SymbolEndpointInfo:
    """Information about a symbol endpoint."""
    node_id: str
    patch_path: str
    role: str  # "writer" or "reader"
    domain: Domain
    port: Optional[int] = None


@dataclass
class GlobalSymbolEntry:
    """Entry in the global symbol table."""
    kind: SymbolKind
    resolved: str
    namespace: SymbolNamespace
    instance_local: bool
    endpoints: List[SymbolEndpointInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "resolved": self.resolved,
            "namespace": self.namespace.value,
            "instance_local": self.instance_local,
            "endpoints": [
                {
                    "role": e.role,
                    "patch": e.patch_path,
                    "node": e.node_id,
                    "domain": e.domain.value,
                }
                for e in self.endpoints
            ],
        }


class SymbolExtractor:
    """Extracts symbols from Pure Data objects."""

    # Object types that participate in symbol communication
    SEND_RECEIVE_WRITERS = {'send', 's', 'send~', 's~'}
    SEND_RECEIVE_READERS = {'receive', 'r', 'receive~', 'r~'}
    THROW_CATCH_WRITERS = {'throw~'}
    THROW_CATCH_READERS = {'catch~'}
    VALUE_OBJECTS = {'value', 'v'}
    ARRAY_OBJECTS = {'array', 'table', 'tabread', 'tabwrite', 'tabread~',
                     'tabwrite~', 'tabread4~', 'tabosc4~', 'tabplay~',
                     'soundfiler', 'tabsend~', 'tabreceive~'}
    DELAY_OBJECTS = {'delwrite~', 'delread~', 'delread4~', 'vd~'}

    # Pattern for instance-local symbols
    INSTANCE_LOCAL_PATTERN = re.compile(r'^\$0[-_]')

    def __init__(self):
        self._symbols: Dict[str, IRSymbol] = {}
        self._symbol_counter = 0

    def reset(self):
        """Reset extractor state."""
        self._symbols.clear()
        self._symbol_counter = 0

    def _get_symbol_id(self) -> str:
        """Generate a unique symbol ID."""
        self._symbol_counter += 1
        return f"sym{self._symbol_counter}"

    def _parse_namespace(self, raw_symbol: str) -> Tuple[str, SymbolNamespace, bool]:
        """
        Parse a symbol to determine its namespace and resolved form.

        Returns:
            (resolved_symbol, namespace, instance_local)
        """
        if self.INSTANCE_LOCAL_PATTERN.match(raw_symbol):
            return (raw_symbol, SymbolNamespace.INSTANCE, True)

        # Check for hierarchical convention (path/symbol)
        if '/' in raw_symbol and not raw_symbol.startswith('/'):
            return (raw_symbol, SymbolNamespace.HIERARCHICAL, False)

        return (raw_symbol, SymbolNamespace.GLOBAL, False)

    def _get_symbol_kind(self, obj_type: str) -> Optional[SymbolKind]:
        """Determine the symbol kind for an object type."""
        base_type = obj_type.split('/')[-1]  # Handle library prefixes

        if base_type in self.SEND_RECEIVE_WRITERS or base_type in self.SEND_RECEIVE_READERS:
            return SymbolKind.SEND_RECEIVE
        if base_type in self.THROW_CATCH_WRITERS or base_type in self.THROW_CATCH_READERS:
            return SymbolKind.THROW_CATCH
        if base_type in self.VALUE_OBJECTS:
            return SymbolKind.VALUE
        if base_type in self.ARRAY_OBJECTS:
            return SymbolKind.ARRAY
        if base_type in self.DELAY_OBJECTS:
            return SymbolKind.TABLE  # Delay lines use named tables

        return None

    def _get_role(self, obj_type: str) -> Optional[str]:
        """Determine if an object is a writer or reader."""
        base_type = obj_type.split('/')[-1]

        if base_type in self.SEND_RECEIVE_WRITERS:
            return "writer"
        if base_type in self.SEND_RECEIVE_READERS:
            return "reader"
        if base_type in self.THROW_CATCH_WRITERS:
            return "writer"
        if base_type in self.THROW_CATCH_READERS:
            return "reader"
        if base_type in {'delwrite~', 'tabwrite', 'tabwrite~'}:
            return "writer"
        if base_type in {'delread~', 'delread4~', 'vd~', 'tabread', 'tabread~',
                         'tabread4~', 'tabosc4~', 'tabplay~', 'tabreceive~'}:
            return "reader"
        if base_type == 'tabsend~':
            return "writer"
        if base_type in self.VALUE_OBJECTS:
            return "reader"  # value can both read and write

        return None

    def _get_domain_for_type(self, obj_type: str) -> Domain:
        """Get the domain for an object type."""
        if obj_type.endswith('~'):
            return Domain.SIGNAL
        return Domain.CONTROL

    def extract_from_node(self, node_id: str, obj_type: str,
                         args: List[str]) -> Optional[IRSymbol]:
        """
        Extract symbol information from a node.

        Returns an IRSymbol if the node participates in symbol communication,
        None otherwise.
        """
        symbol_kind = self._get_symbol_kind(obj_type)
        if symbol_kind is None:
            return None

        if not args:
            return None  # Symbol required but not provided

        raw_symbol = str(args[0])
        resolved, namespace, instance_local = self._parse_namespace(raw_symbol)
        role = self._get_role(obj_type)
        domain = self._get_domain_for_type(obj_type)

        if role is None:
            return None

        # Check if we already have this symbol
        symbol_key = (symbol_kind.value, resolved, namespace.value)
        key_str = f"{symbol_key[0]}:{symbol_key[1]}:{symbol_key[2]}"

        if key_str in self._symbols:
            symbol = self._symbols[key_str]
            endpoint = IRSymbolEndpoint(node=node_id)
            if role == "writer":
                symbol.writers.append(endpoint)
            else:
                symbol.readers.append(endpoint)
            return symbol

        # Create new symbol
        symbol = IRSymbol(
            id=self._get_symbol_id(),
            kind=symbol_kind,
            raw=raw_symbol,
            resolved=resolved,
            namespace=namespace,
            instance_local=instance_local,
            writers=[],
            readers=[],
        )

        endpoint = IRSymbolEndpoint(node=node_id)
        if role == "writer":
            symbol.writers.append(endpoint)
        else:
            symbol.readers.append(endpoint)

        self._symbols[key_str] = symbol
        return symbol

    def get_symbols(self) -> List[IRSymbol]:
        """Get all extracted symbols."""
        return list(self._symbols.values())

    def generate_symbol_edges(self) -> List[IREdge]:
        """
        Generate virtual edges for symbol-mediated connections.

        Returns a list of IREdge objects representing symbol connections.
        """
        edges = []
        edge_counter = 0

        for symbol in self._symbols.values():
            # Create edges from each writer to each reader
            for writer in symbol.writers:
                for reader in symbol.readers:
                    edge_counter += 1

                    # Determine domain
                    if symbol.kind in {SymbolKind.THROW_CATCH, SymbolKind.SEND_RECEIVE}:
                        if '~' in symbol.raw or symbol.kind == SymbolKind.THROW_CATCH:
                            domain = Domain.SIGNAL
                        else:
                            domain = Domain.CONTROL
                    else:
                        domain = Domain.CONTROL

                    # Confidence based on namespace
                    confidence = 1.0
                    if symbol.instance_local:
                        confidence = 0.7  # Lower confidence for $0- symbols
                    elif symbol.namespace == SymbolNamespace.GLOBAL:
                        confidence = 0.9

                    edge = IREdge(
                        id=f"e_sym{edge_counter}",
                        kind=EdgeKind.SYMBOL,
                        domain=domain,
                        from_endpoint=IREdgeEndpoint(node=writer.node, outlet=0),
                        to_endpoint=IREdgeEndpoint(node=reader.node, inlet=0),
                        symbol=symbol.resolved,
                        confidence=confidence,
                    )
                    edges.append(edge)

        return edges


class GlobalSymbolTable:
    """
    Global Symbol Table for cross-file symbol resolution.

    Aggregates symbols from multiple patches and provides query capabilities.
    """

    def __init__(self):
        self._entries: Dict[str, GlobalSymbolEntry] = {}
        self._patches: Set[str] = set()

    def _make_key(self, kind: SymbolKind, resolved: str,
                  namespace: SymbolNamespace) -> str:
        """Generate a unique key for a symbol entry."""
        return f"{kind.value}:{resolved}:{namespace.value}"

    def add_symbol(self, symbol: IRSymbol, patch_path: str,
                   node_id_map: Optional[Dict[str, str]] = None):
        """
        Add a symbol from a patch to the global table.

        Args:
            symbol: The symbol to add
            patch_path: Path of the patch containing the symbol
            node_id_map: Optional mapping from local node IDs to global IDs
        """
        key = self._make_key(symbol.kind, symbol.resolved, symbol.namespace)
        self._patches.add(patch_path)

        if key not in self._entries:
            self._entries[key] = GlobalSymbolEntry(
                kind=symbol.kind,
                resolved=symbol.resolved,
                namespace=symbol.namespace,
                instance_local=symbol.instance_local,
            )

        entry = self._entries[key]

        # Determine domain
        domain = Domain.SIGNAL if symbol.kind == SymbolKind.THROW_CATCH else Domain.CONTROL
        if symbol.kind == SymbolKind.SEND_RECEIVE and '~' in symbol.raw:
            domain = Domain.SIGNAL

        for writer in symbol.writers:
            node_id = writer.node
            if node_id_map and node_id in node_id_map:
                node_id = node_id_map[node_id]

            endpoint = SymbolEndpointInfo(
                node_id=node_id,
                patch_path=patch_path,
                role="writer",
                domain=domain,
                port=writer.port,
            )
            entry.endpoints.append(endpoint)

        for reader in symbol.readers:
            node_id = reader.node
            if node_id_map and node_id in node_id_map:
                node_id = node_id_map[node_id]

            endpoint = SymbolEndpointInfo(
                node_id=node_id,
                patch_path=patch_path,
                role="reader",
                domain=domain,
                port=reader.port,
            )
            entry.endpoints.append(endpoint)

    def add_patch_symbols(self, symbols: List[IRSymbol], patch_path: str,
                          node_id_map: Optional[Dict[str, str]] = None):
        """Add all symbols from a patch."""
        for symbol in symbols:
            self.add_symbol(symbol, patch_path, node_id_map)

    def get_symbol(self, kind: SymbolKind, resolved: str,
                   namespace: SymbolNamespace = SymbolNamespace.GLOBAL
                   ) -> Optional[GlobalSymbolEntry]:
        """Get a symbol entry by its identifying properties."""
        key = self._make_key(kind, resolved, namespace)
        return self._entries.get(key)

    def find_by_name(self, name: str) -> List[GlobalSymbolEntry]:
        """Find all symbols matching a name (across all kinds/namespaces)."""
        return [
            entry for entry in self._entries.values()
            if entry.resolved == name
        ]

    def get_writers(self, kind: SymbolKind, resolved: str,
                    namespace: SymbolNamespace = SymbolNamespace.GLOBAL
                    ) -> List[SymbolEndpointInfo]:
        """Get all writers for a symbol."""
        entry = self.get_symbol(kind, resolved, namespace)
        if entry is None:
            return []
        return [e for e in entry.endpoints if e.role == "writer"]

    def get_readers(self, kind: SymbolKind, resolved: str,
                    namespace: SymbolNamespace = SymbolNamespace.GLOBAL
                    ) -> List[SymbolEndpointInfo]:
        """Get all readers for a symbol."""
        entry = self.get_symbol(kind, resolved, namespace)
        if entry is None:
            return []
        return [e for e in entry.endpoints if e.role == "reader"]

    def get_cross_patch_connections(self) -> List[Dict[str, Any]]:
        """
        Find symbols that connect multiple patches.

        Returns a list of cross-patch symbol connections.
        """
        connections = []

        for entry in self._entries.values():
            patches_with_writers = set(
                e.patch_path for e in entry.endpoints if e.role == "writer"
            )
            patches_with_readers = set(
                e.patch_path for e in entry.endpoints if e.role == "reader"
            )

            cross_patch_readers = patches_with_readers - patches_with_writers

            if cross_patch_readers:
                connections.append({
                    "symbol": entry.resolved,
                    "kind": entry.kind.value,
                    "writer_patches": list(patches_with_writers),
                    "reader_patches": list(cross_patch_readers),
                })

        return connections

    def get_orphaned_symbols(self) -> Dict[str, List[GlobalSymbolEntry]]:
        """
        Find symbols with only writers or only readers.

        Returns dict with 'writers_only' and 'readers_only' lists.
        """
        writers_only = []
        readers_only = []

        for entry in self._entries.values():
            has_writers = any(e.role == "writer" for e in entry.endpoints)
            has_readers = any(e.role == "reader" for e in entry.endpoints)

            if has_writers and not has_readers:
                writers_only.append(entry)
            elif has_readers and not has_writers:
                readers_only.append(entry)

        return {
            "writers_only": writers_only,
            "readers_only": readers_only,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Export the global symbol table to a dictionary."""
        return {
            "index_version": "0.1",
            "symbols": [entry.to_dict() for entry in self._entries.values()],
        }

    def to_json(self, indent: int = 2) -> str:
        """Export the global symbol table to JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, filepath: str):
        """Save the global symbol table to a file."""
        with open(filepath, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, filepath: str) -> 'GlobalSymbolTable':
        """Load a global symbol table from a file."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        gst = cls()

        for sym_data in data.get('symbols', []):
            key = gst._make_key(
                SymbolKind(sym_data['kind']),
                sym_data['resolved'],
                SymbolNamespace(sym_data['namespace']),
            )

            entry = GlobalSymbolEntry(
                kind=SymbolKind(sym_data['kind']),
                resolved=sym_data['resolved'],
                namespace=SymbolNamespace(sym_data['namespace']),
                instance_local=sym_data.get('instance_local', False),
            )

            for ep_data in sym_data.get('endpoints', []):
                endpoint = SymbolEndpointInfo(
                    node_id=ep_data['node'],
                    patch_path=ep_data['patch'],
                    role=ep_data['role'],
                    domain=Domain(ep_data.get('domain', 'control')),
                )
                entry.endpoints.append(endpoint)

            gst._entries[key] = entry

        return gst
