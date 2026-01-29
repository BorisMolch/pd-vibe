"""
Graph Analysis for Pure Data IR.

This module provides graph analysis capabilities including:
- Strongly Connected Component (SCC) detection for feedback cycles
- Interface inference (inlet/outlet detection)
- Topological analysis
- Path finding
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from .core import (
    IRPatch,
    IRNode,
    IREdge,
    IRCanvas,
    IRSCC,
    IRInterface,
    IRInterfacePort,
    IRSymbolsAsInterface,
    IRExposedSymbol,
    IRAnalysis,
    IRSymbol,
    NodeKind,
    EdgeKind,
    Domain,
    SymbolKind,
)


class GraphAnalyzer:
    """Analyzes the graph structure of a Pure Data patch IR."""

    def __init__(self, ir_patch: IRPatch):
        self.ir = ir_patch
        self._adjacency: Dict[str, List[str]] = defaultdict(list)
        self._reverse_adjacency: Dict[str, List[str]] = defaultdict(list)
        self._build_adjacency()

    def _build_adjacency(self):
        """Build adjacency lists from edges."""
        for edge in self.ir.edges:
            if edge.kind == EdgeKind.WIRE:
                src = edge.from_endpoint.node
                dst = edge.to_endpoint.node
                self._adjacency[src].append(dst)
                self._reverse_adjacency[dst].append(src)

    def find_sccs(self) -> List[IRSCC]:
        """
        Find Strongly Connected Components using Tarjan's algorithm.

        Returns SCCs with more than one node (feedback cycles).
        """
        index_counter = [0]
        stack = []
        lowlink = {}
        index = {}
        on_stack = {}
        sccs = []

        def strongconnect(node: str):
            index[node] = index_counter[0]
            lowlink[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack[node] = True

            for successor in self._adjacency.get(node, []):
                if successor not in index:
                    strongconnect(successor)
                    lowlink[node] = min(lowlink[node], lowlink[successor])
                elif on_stack.get(successor, False):
                    lowlink[node] = min(lowlink[node], index[successor])

            if lowlink[node] == index[node]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == node:
                        break

                # Only track SCCs with multiple nodes (cycles)
                if len(scc) > 1:
                    sccs.append(scc)

        # Run on all nodes
        all_nodes = set(self._adjacency.keys()) | set(self._reverse_adjacency.keys())
        for node in all_nodes:
            if node not in index:
                strongconnect(node)

        # Convert to IRSCC objects
        result = []
        for i, scc_nodes in enumerate(sccs):
            result.append(IRSCC(
                id=f"scc{i + 1}",
                nodes=scc_nodes,
                reason="feedback_cycle",
            ))

        return result

    def find_interface_ports(self) -> IRInterface:
        """
        Find interface ports (inlet/outlet objects) in the patch.

        Returns an IRInterface with inlet and outlet specifications.
        """
        inlets = []
        outlets = []

        inlet_nodes = []
        outlet_nodes = []

        for node in self.ir.nodes:
            if node.type in ('inlet', 'inlet~'):
                inlet_nodes.append(node)
            elif node.type in ('outlet', 'outlet~'):
                outlet_nodes.append(node)

        # Sort by x position to determine index order
        inlet_nodes.sort(key=lambda n: (n.layout.x if n.layout else 0))
        outlet_nodes.sort(key=lambda n: (n.layout.x if n.layout else 0))

        for idx, node in enumerate(inlet_nodes):
            domain = Domain.SIGNAL if node.type == 'inlet~' else Domain.CONTROL
            inlets.append(IRInterfacePort(
                node=node.id,
                index=idx,
                domain=domain,
            ))

        for idx, node in enumerate(outlet_nodes):
            domain = Domain.SIGNAL if node.type == 'outlet~' else Domain.CONTROL
            outlets.append(IRInterfacePort(
                node=node.id,
                index=idx,
                domain=domain,
            ))

        return IRInterface(inlets=inlets, outlets=outlets)

    def find_symbols_as_interface(self, symbols: List[IRSymbol]) -> IRSymbolsAsInterface:
        """
        Find symbols that serve as external interface points.

        Symbols with only readers or only writers within the patch
        may represent interface points for cross-patch communication.
        """
        exposed = []

        for symbol in symbols:
            # Skip instance-local symbols
            if symbol.instance_local:
                continue

            has_writers = len(symbol.writers) > 0
            has_readers = len(symbol.readers) > 0

            # If we only have readers, this symbol receives from outside
            if has_readers and not has_writers:
                exposed.append(IRExposedSymbol(
                    kind=symbol.kind,
                    name=symbol.resolved,
                    role="reader",
                ))
            # If we only have writers, this symbol sends to outside
            elif has_writers and not has_readers:
                exposed.append(IRExposedSymbol(
                    kind=symbol.kind,
                    name=symbol.resolved,
                    role="writer",
                ))

        return IRSymbolsAsInterface(
            enabled=len(exposed) > 0,
            exposed=exposed,
        )

    def get_topological_order(self) -> List[str]:
        """
        Get nodes in topological order (for DAG portions).

        Returns a list of node IDs in topological order.
        Cycles are handled by including all cycle nodes at the first encounter.
        """
        visited = set()
        temp_marked = set()
        order = []

        def visit(node: str):
            if node in visited:
                return
            if node in temp_marked:
                return  # Cycle detected, skip

            temp_marked.add(node)

            for successor in self._adjacency.get(node, []):
                visit(successor)

            temp_marked.remove(node)
            visited.add(node)
            order.append(node)

        # Start from nodes with no predecessors
        all_nodes = set(self._adjacency.keys()) | set(self._reverse_adjacency.keys())
        roots = [n for n in all_nodes if n not in self._reverse_adjacency]

        for root in roots:
            visit(root)

        # Visit remaining nodes (may be in cycles)
        for node in all_nodes:
            if node not in visited:
                visit(node)

        order.reverse()
        return order

    def get_predecessors(self, node_id: str) -> List[str]:
        """Get immediate predecessors of a node."""
        return self._reverse_adjacency.get(node_id, [])

    def get_successors(self, node_id: str) -> List[str]:
        """Get immediate successors of a node."""
        return self._adjacency.get(node_id, [])

    def get_in_degree(self, node_id: str) -> int:
        """Get the in-degree of a node."""
        return len(self._reverse_adjacency.get(node_id, []))

    def get_out_degree(self, node_id: str) -> int:
        """Get the out-degree of a node."""
        return len(self._adjacency.get(node_id, []))

    def find_linear_chains(self, domain: Optional[Domain] = None) -> List[List[str]]:
        """
        Find linear chains of nodes (in_degree=1, out_degree=1).

        These can be collapsed in DSL output for compactness.

        Args:
            domain: If specified, only find chains in this domain

        Returns:
            List of chains, where each chain is a list of node IDs
        """
        chains = []
        visited = set()

        # Build domain-filtered adjacency if needed
        if domain:
            filtered_edges = [
                e for e in self.ir.edges
                if e.kind == EdgeKind.WIRE and e.domain == domain
            ]
            adjacency = defaultdict(list)
            reverse_adjacency = defaultdict(list)
            for edge in filtered_edges:
                adjacency[edge.from_endpoint.node].append(edge.to_endpoint.node)
                reverse_adjacency[edge.to_endpoint.node].append(edge.from_endpoint.node)
        else:
            adjacency = self._adjacency
            reverse_adjacency = self._reverse_adjacency

        def get_in_degree(n):
            return len(reverse_adjacency.get(n, []))

        def get_out_degree(n):
            return len(adjacency.get(n, []))

        # Find chain starts (nodes with out_degree=1 but in_degree!=1)
        all_nodes = set(adjacency.keys()) | set(reverse_adjacency.keys())

        for start in all_nodes:
            if start in visited:
                continue

            # Check if this could be a chain start
            out_deg = get_out_degree(start)
            in_deg = get_in_degree(start)

            if out_deg != 1:
                continue
            if in_deg == 1:
                continue  # This is mid-chain, will be found from actual start

            # Follow the chain
            chain = [start]
            current = start
            visited.add(current)

            while True:
                successors = adjacency.get(current, [])
                if len(successors) != 1:
                    break

                next_node = successors[0]
                if next_node in visited:
                    break
                if get_in_degree(next_node) != 1:
                    break

                chain.append(next_node)
                visited.add(next_node)
                current = next_node

                if get_out_degree(next_node) != 1:
                    break

            if len(chain) >= 2:
                chains.append(chain)

        return chains

    def trace_to_output(self, node_id: str, max_depth: int = 100) -> List[List[str]]:
        """
        Trace all paths from a node to output objects (dac~, outlet, outlet~).

        Returns a list of paths, where each path is a list of node IDs.
        """
        output_types = {'dac~', 'outlet', 'outlet~'}
        paths = []

        def dfs(current: str, path: List[str], depth: int):
            if depth > max_depth:
                return

            node = self.ir.get_node(current)
            if node and node.type in output_types:
                paths.append(path[:])
                return

            for successor in self._adjacency.get(current, []):
                if successor not in path:  # Avoid cycles
                    path.append(successor)
                    dfs(successor, path, depth + 1)
                    path.pop()

        dfs(node_id, [node_id], 0)
        return paths

    def trace_from_input(self, node_id: str, max_depth: int = 100) -> List[List[str]]:
        """
        Trace all paths from input objects (adc~, inlet, inlet~) to a node.

        Returns a list of paths, where each path is a list of node IDs.
        """
        input_types = {'adc~', 'inlet', 'inlet~'}
        paths = []

        def dfs(current: str, path: List[str], depth: int):
            if depth > max_depth:
                return

            node = self.ir.get_node(current)
            if node and node.type in input_types:
                paths.append(list(reversed(path)))
                return

            for predecessor in self._reverse_adjacency.get(current, []):
                if predecessor not in path:  # Avoid cycles
                    path.append(predecessor)
                    dfs(predecessor, path, depth + 1)
                    path.pop()

        dfs(node_id, [node_id], 0)
        return paths

    def analyze(self) -> IRAnalysis:
        """
        Perform full analysis of the IR.

        Returns an IRAnalysis object with SCCs and interfaces.
        """
        sccs = self.find_sccs()
        interfaces = self.find_interface_ports()
        symbols_as_interface = self.find_symbols_as_interface(self.ir.symbols)

        return IRAnalysis(
            sccs=sccs,
            interfaces=interfaces,
            symbols_as_interface=symbols_as_interface,
        )

    def get_subgraph_for_canvas(self, canvas_id: str) -> 'GraphAnalyzer':
        """
        Get a sub-analyzer for a specific canvas.

        Returns a new GraphAnalyzer with only nodes/edges from that canvas.
        """
        canvas_nodes = [n for n in self.ir.nodes if n.canvas == canvas_id]
        node_ids = {n.id for n in canvas_nodes}

        canvas_edges = [
            e for e in self.ir.edges
            if e.from_endpoint.node in node_ids and e.to_endpoint.node in node_ids
        ]

        # Create a sub-patch
        sub_ir = IRPatch(
            ir_version=self.ir.ir_version,
            nodes=canvas_nodes,
            edges=canvas_edges,
            symbols=[],
        )

        return GraphAnalyzer(sub_ir)
