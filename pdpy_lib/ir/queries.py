"""
Graph Query Functions for Pure Data IR.

This module provides high-level query functions for analyzing IR patches
and cross-patch relationships.
"""

from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

from .core import (
    IRPatch,
    IRNode,
    IREdge,
    IRSymbol,
    EdgeKind,
    Domain,
    NodeKind,
    SymbolKind,
)
from .analysis import GraphAnalyzer
from .index import IRIndex


def trace_to_dac(ir_patch: IRPatch, node_id: str,
                 include_symbol_edges: bool = True) -> List[List[str]]:
    """
    Trace all paths from a node to dac~ outputs.

    Args:
        ir_patch: The IR patch to analyze
        node_id: Starting node ID
        include_symbol_edges: Whether to follow symbol-mediated edges

    Returns:
        List of paths, where each path is a list of node IDs ending at dac~
    """
    analyzer = GraphAnalyzer(ir_patch)
    output_types = {'dac~', 'outlet~', 'outlet'}

    paths = []
    visited_in_path: Set[str] = set()

    # Build adjacency including symbol edges if requested
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in ir_patch.edges:
        if edge.kind == EdgeKind.WIRE:
            adjacency[edge.from_endpoint.node].append(edge.to_endpoint.node)
        elif include_symbol_edges and edge.kind == EdgeKind.SYMBOL:
            adjacency[edge.from_endpoint.node].append(edge.to_endpoint.node)

    def dfs(current: str, path: List[str]):
        node = ir_patch.get_node(current)
        if node and node.type in output_types:
            paths.append(path[:])
            return

        if current in visited_in_path:
            return
        visited_in_path.add(current)

        for successor in adjacency.get(current, []):
            path.append(successor)
            dfs(successor, path)
            path.pop()

        visited_in_path.remove(current)

    dfs(node_id, [node_id])
    return paths


def trace_from_adc(ir_patch: IRPatch, node_id: str,
                   include_symbol_edges: bool = True) -> List[List[str]]:
    """
    Trace all paths from adc~ inputs to a node.

    Args:
        ir_patch: The IR patch to analyze
        node_id: Target node ID
        include_symbol_edges: Whether to follow symbol-mediated edges

    Returns:
        List of paths from input to the node
    """
    input_types = {'adc~', 'inlet~', 'inlet'}

    paths = []
    visited_in_path: Set[str] = set()

    # Build reverse adjacency
    reverse_adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in ir_patch.edges:
        if edge.kind == EdgeKind.WIRE:
            reverse_adjacency[edge.to_endpoint.node].append(edge.from_endpoint.node)
        elif include_symbol_edges and edge.kind == EdgeKind.SYMBOL:
            reverse_adjacency[edge.to_endpoint.node].append(edge.from_endpoint.node)

    def dfs(current: str, path: List[str]):
        node = ir_patch.get_node(current)
        if node and node.type in input_types:
            paths.append(list(reversed(path)))
            return

        if current in visited_in_path:
            return
        visited_in_path.add(current)

        for predecessor in reverse_adjacency.get(current, []):
            path.append(predecessor)
            dfs(predecessor, path)
            path.pop()

        visited_in_path.remove(current)

    dfs(node_id, [node_id])
    return paths


def symbol_flow(ir_patch: IRPatch, symbol_name: str) -> Dict[str, Any]:
    """
    Analyze the flow of a symbol through a patch.

    Args:
        ir_patch: The IR patch to analyze
        symbol_name: The symbol to trace

    Returns:
        Dictionary with writers, readers, and edge information
    """
    symbol = next(
        (s for s in ir_patch.symbols if s.resolved == symbol_name),
        None
    )

    if not symbol:
        return {
            'symbol': symbol_name,
            'found': False,
            'writers': [],
            'readers': [],
            'edges': [],
        }

    # Find symbol edges
    symbol_edges = [
        e for e in ir_patch.edges
        if e.kind == EdgeKind.SYMBOL and e.symbol == symbol_name
    ]

    return {
        'symbol': symbol_name,
        'found': True,
        'kind': symbol.kind.value,
        'namespace': symbol.namespace.value,
        'instance_local': symbol.instance_local,
        'writers': [w.node for w in symbol.writers],
        'readers': [r.node for r in symbol.readers],
        'edges': [
            {
                'from': e.from_endpoint.node,
                'to': e.to_endpoint.node,
                'confidence': e.confidence,
            }
            for e in symbol_edges
        ],
    }


def find_feedback_paths(ir_patch: IRPatch) -> List[Dict[str, Any]]:
    """
    Find all feedback paths (cycles) in the patch.

    Args:
        ir_patch: The IR patch to analyze

    Returns:
        List of feedback path information
    """
    analyzer = GraphAnalyzer(ir_patch)
    sccs = analyzer.find_sccs()

    result = []
    for scc in sccs:
        # Find the edges that form the cycle
        cycle_nodes = set(scc.nodes)
        cycle_edges = [
            e for e in ir_patch.edges
            if e.from_endpoint.node in cycle_nodes
            and e.to_endpoint.node in cycle_nodes
            and e.kind == EdgeKind.WIRE
        ]

        result.append({
            'id': scc.id,
            'nodes': scc.nodes,
            'edges': [
                {
                    'from': e.from_endpoint.node,
                    'to': e.to_endpoint.node,
                    'domain': e.domain.value,
                }
                for e in cycle_edges
            ],
            'reason': scc.reason,
        })

    return result


def get_signal_chain(ir_patch: IRPatch, start_node: str) -> List[str]:
    """
    Get the linear signal chain starting from a node.

    Follows the signal path as long as nodes have single in/out connections.

    Args:
        ir_patch: The IR patch to analyze
        start_node: Starting node ID

    Returns:
        List of node IDs in the chain
    """
    analyzer = GraphAnalyzer(ir_patch)

    chain = [start_node]
    current = start_node
    visited = {start_node}

    while True:
        successors = [
            e.to_endpoint.node for e in ir_patch.edges
            if e.from_endpoint.node == current
            and e.kind == EdgeKind.WIRE
            and e.domain == Domain.SIGNAL
        ]

        if len(successors) != 1:
            break

        next_node = successors[0]
        if next_node in visited:
            break

        # Check if next node has single predecessor
        predecessors = [
            e.from_endpoint.node for e in ir_patch.edges
            if e.to_endpoint.node == next_node
            and e.kind == EdgeKind.WIRE
            and e.domain == Domain.SIGNAL
        ]

        if len(predecessors) != 1:
            break

        chain.append(next_node)
        visited.add(next_node)
        current = next_node

    return chain


def find_orphaned_connections(ir_patch: IRPatch) -> Dict[str, List[str]]:
    """
    Find nodes with unconnected inlets or outlets.

    Args:
        ir_patch: The IR patch to analyze

    Returns:
        Dictionary with 'unconnected_inlets' and 'unconnected_outlets'
    """
    # Track which ports are connected
    connected_outlets: Set[Tuple[str, int]] = set()
    connected_inlets: Set[Tuple[str, int]] = set()

    for edge in ir_patch.edges:
        if edge.kind == EdgeKind.WIRE:
            connected_outlets.add(
                (edge.from_endpoint.node, edge.from_endpoint.outlet or 0)
            )
            connected_inlets.add(
                (edge.to_endpoint.node, edge.to_endpoint.inlet or 0)
            )

    unconnected_inlets = []
    unconnected_outlets = []

    for node in ir_patch.nodes:
        if node.io:
            for inlet in node.io.inlets:
                if (node.id, inlet.index) not in connected_inlets:
                    # Check if it's an interface node (these are expected to be "unconnected")
                    if node.type not in ('inlet', 'inlet~', 'adc~', 'r', 'receive', 'r~', 'receive~', 'catch~'):
                        unconnected_inlets.append(f"{node.id}:{inlet.index}")

            for outlet in node.io.outlets:
                if (node.id, outlet.index) not in connected_outlets:
                    if node.type not in ('outlet', 'outlet~', 'dac~', 's', 'send', 's~', 'send~', 'throw~'):
                        unconnected_outlets.append(f"{node.id}:{outlet.index}")

    return {
        'unconnected_inlets': unconnected_inlets,
        'unconnected_outlets': unconnected_outlets,
    }


def dependency_tree(ir_patch: IRPatch) -> Dict[str, Any]:
    """
    Build a dependency tree showing abstractions and externals used.

    Args:
        ir_patch: The IR patch to analyze

    Returns:
        Dependency tree structure
    """
    abstractions = []
    externals = []

    if ir_patch.refs:
        abstractions = [
            {
                'name': a['name'],
                'path': a.get('path'),
                'instances': a.get('instances', []),
            }
            for a in ir_patch.refs.abstractions
        ]

        externals = [
            {
                'name': e.name,
                'instances': e.instances,
                'known': e.known,
            }
            for e in ir_patch.refs.externals
        ]

    return {
        'patch': ir_patch.patch.path if ir_patch.patch else 'unknown',
        'abstractions': abstractions,
        'externals': externals,
    }


def find_similar_patterns(ir_patch: IRPatch, pattern: List[str]) -> List[List[str]]:
    """
    Find node sequences matching a type pattern.

    Args:
        ir_patch: The IR patch to search
        pattern: List of object types to match (e.g., ['osc~', '*~', 'dac~'])

    Returns:
        List of matching node ID sequences
    """
    if not pattern:
        return []

    # Build adjacency for path following
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in ir_patch.edges:
        if edge.kind == EdgeKind.WIRE:
            adjacency[edge.from_endpoint.node].append(edge.to_endpoint.node)

    # Find starting nodes matching first pattern element
    start_nodes = [
        n for n in ir_patch.nodes
        if n.type == pattern[0]
    ]

    matches = []

    for start in start_nodes:
        # DFS to find matching sequences
        def find_pattern(current: str, pattern_idx: int, path: List[str]):
            if pattern_idx >= len(pattern):
                matches.append(path[:])
                return

            node = ir_patch.get_node(current)
            if not node or node.type != pattern[pattern_idx]:
                return

            path.append(current)

            if pattern_idx == len(pattern) - 1:
                matches.append(path[:])
            else:
                for successor in adjacency.get(current, []):
                    find_pattern(successor, pattern_idx + 1, path)

            path.pop()

        find_pattern(start.id, 0, [])

    return matches


def get_patch_summary(ir_patch: IRPatch) -> Dict[str, Any]:
    """
    Get a summary of patch statistics and characteristics.

    Args:
        ir_patch: The IR patch to summarize

    Returns:
        Summary dictionary
    """
    analyzer = GraphAnalyzer(ir_patch)

    # Count by kind
    kind_counts: Dict[str, int] = defaultdict(int)
    for node in ir_patch.nodes:
        kind_counts[node.kind.value] += 1

    # Count by domain
    domain_counts: Dict[str, int] = defaultdict(int)
    for node in ir_patch.nodes:
        domain_counts[node.domain.value] += 1

    # Count edges
    wire_count = sum(1 for e in ir_patch.edges if e.kind == EdgeKind.WIRE)
    symbol_count = sum(1 for e in ir_patch.edges if e.kind == EdgeKind.SYMBOL)

    # Get interface
    interface = analyzer.find_interface_ports()

    return {
        'patch': ir_patch.patch.path if ir_patch.patch else 'unknown',
        'total_nodes': len(ir_patch.nodes),
        'total_edges': len(ir_patch.edges),
        'wire_edges': wire_count,
        'symbol_edges': symbol_count,
        'by_kind': dict(kind_counts),
        'by_domain': dict(domain_counts),
        'symbols': len(ir_patch.symbols),
        'canvases': len(ir_patch.canvases),
        'interface': {
            'inlets': len(interface.inlets),
            'outlets': len(interface.outlets),
        },
        'has_feedback': bool(ir_patch.analysis and ir_patch.analysis.sccs),
        'diagnostics': {
            'errors': len(ir_patch.diagnostics.errors) if ir_patch.diagnostics else 0,
            'warnings': len(ir_patch.diagnostics.warnings) if ir_patch.diagnostics else 0,
        },
    }


# Cross-patch queries (require IRIndex)

def cross_patch_symbol_flow(index: IRIndex, symbol_name: str) -> Dict[str, Any]:
    """
    Analyze symbol flow across multiple patches.

    Args:
        index: IRIndex instance
        symbol_name: Symbol to trace

    Returns:
        Cross-patch flow analysis
    """
    return index.get_symbol_flow(symbol_name)


def find_all_abstractions(index: IRIndex) -> List[Dict[str, Any]]:
    """
    Find all abstraction usages across indexed patches.

    Args:
        index: IRIndex instance

    Returns:
        List of abstraction usage information
    """
    nodes = index.find_nodes_by_type('abstraction_instance')
    return nodes


def find_patches_using(index: IRIndex, abstraction_name: str) -> List[str]:
    """
    Find all patches that use a specific abstraction.

    Args:
        index: IRIndex instance
        abstraction_name: Name of the abstraction

    Returns:
        List of patch paths
    """
    return index.get_reverse_deps(abstraction_name)
