"""
DSL Serialization for Pure Data IR.

This module provides DSL (Domain-Specific Language) output for the IR,
in both FULL (explicit, tooling-friendly) and COMPACT (token-efficient) modes.
"""

from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from .core import (
    IRPatch,
    IRNode,
    IREdge,
    IRCanvas,
    IRSymbol,
    IRSCC,
    NodeKind,
    EdgeKind,
    Domain,
    SymbolKind,
)
from .analysis import GraphAnalyzer


class DSLMode(Enum):
    """DSL output mode."""
    FULL = "full"
    COMPACT = "compact"


class DSLSerializer:
    """Serializes IR to DSL format."""

    def __init__(self, ir_patch: IRPatch, mode: DSLMode = DSLMode.COMPACT):
        self.ir = ir_patch
        self.mode = mode
        self._analyzer: Optional[GraphAnalyzer] = None

    def _get_analyzer(self) -> GraphAnalyzer:
        """Get or create a graph analyzer."""
        if self._analyzer is None:
            self._analyzer = GraphAnalyzer(self.ir)
        return self._analyzer

    def _format_args(self, args: List[str]) -> str:
        """Format arguments for DSL output."""
        if not args:
            return ""
        # Quote args with spaces
        formatted = []
        for arg in args:
            if ' ' in str(arg) or ',' in str(arg):
                formatted.append(f'"{arg}"')
            else:
                formatted.append(str(arg))
        return " ".join(formatted)

    def _format_domain(self, domain: Domain) -> str:
        """Format domain annotation."""
        if domain == Domain.SIGNAL:
            return "[signal]"
        elif domain == Domain.CONTROL:
            return "[control]"
        elif domain == Domain.MIXED:
            return "[mixed]"
        return ""

    def _node_shorthand(self, node: IRNode) -> str:
        """Generate shorthand representation for a node."""
        args = self._format_args(node.args)
        if args:
            return f"{node.type} {args}"
        return node.type

    def serialize_full(self) -> str:
        """Serialize to FULL mode DSL."""
        lines = []

        # Patch header
        if self.ir.patch:
            lines.append(f"patch {self.ir.patch.path}")
            lines.append("")

        # Canvases
        for canvas in self.ir.canvases:
            parent = f" parent={canvas.parent_canvas}" if canvas.parent_canvas else ""
            lines.append(f'canvas {canvas.id} "{canvas.name}"{parent}')
        lines.append("")

        # Nodes by canvas
        for canvas in self.ir.canvases:
            canvas_nodes = [n for n in self.ir.nodes if n.canvas == canvas.id]
            if not canvas_nodes:
                continue

            lines.append(f"# Canvas: {canvas.name}")
            for node in canvas_nodes:
                kind_map = {
                    NodeKind.OBJECT: "obj",
                    NodeKind.MESSAGE: "msg",
                    NodeKind.ATOM: "atom",
                    NodeKind.GUI: "gui",
                    NodeKind.COMMENT: "text",
                    NodeKind.ABSTRACTION_INSTANCE: "abs",
                    NodeKind.SUBPATCH: "sub",
                }
                kind_str = kind_map.get(node.kind, "obj")

                if node.kind == NodeKind.COMMENT:
                    text = node.text or ""
                    lines.append(f'node {node.id} {kind_str} "{text}"')
                elif node.kind == NodeKind.ABSTRACTION_INSTANCE and node.ref:
                    args = self._format_args(node.args)
                    domain_str = self._format_domain(node.domain)
                    lines.append(
                        f"node {node.id} {kind_str} {node.type} {args} -> {node.ref.path} {domain_str}"
                    )
                else:
                    args = self._format_args(node.args)
                    domain_str = self._format_domain(node.domain)
                    if args:
                        lines.append(f"node {node.id} {kind_str} {node.type} {args} {domain_str}")
                    else:
                        lines.append(f"node {node.id} {kind_str} {node.type} {domain_str}")

            lines.append("")

        # Wires
        wire_edges = [e for e in self.ir.edges if e.kind == EdgeKind.WIRE]
        if wire_edges:
            lines.append("# Wires")
            for edge in wire_edges:
                domain_str = self._format_domain(edge.domain)
                src = f"{edge.from_endpoint.node}:{edge.from_endpoint.outlet or 0}"
                dst = f"{edge.to_endpoint.node}:{edge.to_endpoint.inlet or 0}"
                lines.append(f"wire {src} -> {dst} {domain_str}")
            lines.append("")

        # Symbols
        if self.ir.symbols:
            lines.append("# Symbols")
            for symbol in self.ir.symbols:
                ns = f"namespace={symbol.namespace.value}"
                lines.append(f"sym {symbol.kind.value} {symbol.resolved} {ns}")
                for writer in symbol.writers:
                    lines.append(f"  writer {writer.node}")
                for reader in symbol.readers:
                    lines.append(f"  reader {reader.node}")
            lines.append("")

        # Analysis: SCCs
        if self.ir.analysis and self.ir.analysis.sccs:
            lines.append("# Feedback Cycles")
            for scc in self.ir.analysis.sccs:
                nodes_str = ",".join(scc.nodes)
                lines.append(f"scc {scc.id} nodes=[{nodes_str}] reason={scc.reason}")
            lines.append("")

        return "\n".join(lines)

    def serialize_compact(self) -> str:
        """Serialize to COMPACT mode DSL."""
        lines = []

        # Patch header
        if self.ir.patch:
            lines.append(f"patch {self.ir.patch.path}")
            lines.append("")

        # Find linear chains for chain~ optimization
        analyzer = self._get_analyzer()
        signal_chains = analyzer.find_linear_chains(Domain.SIGNAL)

        # Build set of nodes in chains
        chained_nodes: Set[str] = set()
        for chain in signal_chains:
            chained_nodes.update(chain)

        # Nodes (excluding chained nodes, shown separately)
        for canvas in self.ir.canvases:
            canvas_nodes = [
                n for n in self.ir.nodes
                if n.canvas == canvas.id and n.id not in chained_nodes
            ]

            if canvas.kind != "root":
                lines.append(f"# {canvas.name}")

            for node in canvas_nodes:
                if node.kind == NodeKind.COMMENT:
                    text = node.text or ""
                    lines.append(f'{node.id}: # "{text}"')
                elif node.kind == NodeKind.ABSTRACTION_INSTANCE and node.ref:
                    args_str = ",".join(str(a) for a in node.args) if node.args else ""
                    if args_str:
                        lines.append(f"{node.id}: {node.type}({args_str}) @{node.ref.path}")
                    else:
                        lines.append(f"{node.id}: {node.type} @{node.ref.path}")
                elif node.kind == NodeKind.MESSAGE:
                    args = self._format_args(node.args)
                    lines.append(f"{node.id}: msg {args}")
                else:
                    args = self._format_args(node.args)
                    if args:
                        lines.append(f"{node.id}: {node.type} {args}")
                    else:
                        lines.append(f"{node.id}: {node.type}")

        if lines and lines[-1]:
            lines.append("")

        # Signal chains
        if signal_chains:
            lines.append("chains~:")
            for chain in signal_chains:
                chain_parts = []
                for node_id in chain:
                    node = self.ir.get_node(node_id)
                    if node:
                        args_str = ""
                        if node.args:
                            args_str = f"({','.join(str(a) for a in node.args)})"
                        chain_parts.append(f"{node_id}:{node.type}{args_str}")
                lines.append(f"  {' -> '.join(chain_parts)}")
            lines.append("")

        # Wires (grouped and simplified)
        wire_edges = [
            e for e in self.ir.edges
            if e.kind == EdgeKind.WIRE
            # Exclude edges between chained nodes
            and not (e.from_endpoint.node in chained_nodes
                    and e.to_endpoint.node in chained_nodes)
        ]

        if wire_edges:
            lines.append("wires:")
            # Group by (source node, outlet) to properly handle fan-out
            by_source_outlet: Dict[Tuple[str, int], List[IREdge]] = defaultdict(list)
            for edge in wire_edges:
                key = (edge.from_endpoint.node, edge.from_endpoint.outlet or 0)
                by_source_outlet[key].append(edge)

            # Track which edges have been processed (by edge id)
            processed_edges: Set[str] = set()

            # Process each (source, outlet) pair
            for (src_node, src_outlet), edges in by_source_outlet.items():
                # Process ALL edges from this source/outlet (handles fan-out)
                for edge in edges:
                    if edge.id in processed_edges:
                        continue

                    # Start a wire chain from this edge
                    wire_chain = [f"{src_node}:{src_outlet}"]
                    current = edge.to_endpoint.node
                    current_inlet = edge.to_endpoint.inlet or 0
                    wire_chain.append(f"{current}:{current_inlet}")
                    processed_edges.add(edge.id)

                    # Follow the chain (with cycle detection)
                    # Only continue if the next node has exactly one outgoing edge
                    chain_visited: Set[str] = {src_node, current}
                    while True:
                        # Find edges from current node
                        current_edges = []
                        for (n, o), e_list in by_source_outlet.items():
                            if n == current:
                                current_edges.extend(e_list)

                        # Only continue chain if exactly one unprocessed outgoing edge
                        unprocessed = [e for e in current_edges if e.id not in processed_edges]
                        if len(unprocessed) != 1:
                            break

                        next_edge = unprocessed[0]
                        next_node = next_edge.to_endpoint.node
                        # Stop if we'd create a cycle
                        if next_node in chain_visited:
                            break

                        current = next_node
                        current_inlet = next_edge.to_endpoint.inlet or 0
                        wire_chain.append(f"{current}:{current_inlet}")
                        processed_edges.add(next_edge.id)
                        chain_visited.add(current)

                    lines.append(f"  {' -> '.join(wire_chain)}")

            lines.append("")

        # Symbols (compact)
        if self.ir.symbols:
            lines.append("symbols:")
            for symbol in self.ir.symbols:
                writers = ",".join(w.node for w in symbol.writers)
                readers = ",".join(r.node for r in symbol.readers)
                ns = f"({symbol.namespace.value})" if symbol.namespace.value != "global" else "(global)"
                lines.append(f"  {symbol.resolved} {ns}: w[{writers}] r[{readers}]")
            lines.append("")

        # Cycles (compact)
        if self.ir.analysis and self.ir.analysis.sccs:
            cycles_str = "; ".join(
                f"[{','.join(scc.nodes)}]"
                for scc in self.ir.analysis.sccs
            )
            lines.append(f"cycles: {cycles_str}")
            lines.append("")

        # Diagnostics (warnings and errors)
        if self.ir.diagnostics:
            if self.ir.diagnostics.warnings:
                lines.append("warnings:")
                for diag in self.ir.diagnostics.warnings:
                    node_str = f" @ {diag.node}" if diag.node else ""
                    lines.append(f"  [{diag.code}] {diag.message}{node_str}")
                lines.append("")
            if self.ir.diagnostics.errors:
                lines.append("errors:")
                for diag in self.ir.diagnostics.errors:
                    node_str = f" @ {diag.node}" if diag.node else ""
                    lines.append(f"  [{diag.code}] {diag.message}{node_str}")
                lines.append("")

        return "\n".join(lines)

    def serialize(self) -> str:
        """Serialize to DSL based on current mode."""
        if self.mode == DSLMode.FULL:
            return self.serialize_full()
        return self.serialize_compact()

    def to_string(self) -> str:
        """Alias for serialize()."""
        return self.serialize()


def ir_to_dsl(ir_patch: IRPatch, mode: DSLMode = DSLMode.COMPACT) -> str:
    """
    Convert an IR patch to DSL string.

    Args:
        ir_patch: The IR patch to convert
        mode: DSL mode (FULL or COMPACT)

    Returns:
        DSL string representation
    """
    serializer = DSLSerializer(ir_patch, mode)
    return serializer.serialize()
