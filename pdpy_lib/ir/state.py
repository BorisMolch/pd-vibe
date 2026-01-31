"""
State Analysis for Pure Data Patches.

Identifies stateful elements (delay buffers, feedback loops, tables)
and how to silence them. Useful for debugging audio bleed issues.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from .core import IRPatch, IRNode, IREdge, Domain, EdgeKind
from .analysis import GraphAnalyzer


@dataclass
class DelayBuffer:
    """A delay buffer (delwrite~) and its readers."""
    name: str
    size_ms: str
    writer_node: str
    reader_nodes: List[Tuple[str, str]]  # (node_id, read_time)
    feedback_multiplier: Optional[Tuple[str, str]] = None  # (node_id, value)


@dataclass
class FeedbackLoop:
    """A feedback loop with gain information."""
    nodes: List[str]
    gain_node: Optional[str] = None
    gain_value: Optional[str] = None
    delay_name: Optional[str] = None


@dataclass
class TableBuffer:
    """A table/array that stores samples."""
    name: str
    node_id: str
    size: Optional[str] = None


@dataclass
class StateAnalysis:
    """Complete state analysis of a patch."""
    delay_buffers: List[DelayBuffer]
    feedback_loops: List[FeedbackLoop]
    tables: List[TableBuffer]

    def to_text(self) -> str:
        """Generate human-readable state report."""
        lines = []

        if not self.delay_buffers and not self.feedback_loops and not self.tables:
            return "No stateful elements found (stateless patch)."

        lines.append("# Stateful Elements")
        lines.append("")

        if self.delay_buffers:
            lines.append("## Delay Buffers")
            for buf in self.delay_buffers:
                readers = ", ".join(f"{t}ms" for _, t in buf.reader_nodes) if buf.reader_nodes else "none"
                lines.append(f"- **{buf.name}** ({buf.size_ms}ms)")
                lines.append(f"  - Writer: `{buf.writer_node}`")
                lines.append(f"  - Read taps: {readers}")
                if buf.feedback_multiplier:
                    node, val = buf.feedback_multiplier
                    lines.append(f"  - Feedback: `{node}` (gain: {val})")
                    lines.append(f"  - **To silence:** Set `{node}` to 0, then `; {buf.name} const 0`")
                else:
                    lines.append(f"  - **To clear:** `; {buf.name} const 0`")
            lines.append("")

        if self.feedback_loops:
            lines.append("## Feedback Loops")
            for loop in self.feedback_loops:
                nodes_str = " → ".join(loop.nodes)
                lines.append(f"- {nodes_str}")
                if loop.gain_node:
                    lines.append(f"  - Gain control: `{loop.gain_node}` = {loop.gain_value or '?'}")
                    lines.append(f"  - **To kill:** Set `{loop.gain_node}` to 0")
            lines.append("")

        if self.tables:
            lines.append("## Tables/Arrays")
            for tbl in self.tables:
                size_str = f" ({tbl.size} samples)" if tbl.size else ""
                lines.append(f"- **{tbl.name}**{size_str}")
                lines.append(f"  - **To clear:** `; {tbl.name} const 0`")
            lines.append("")

        # Summary
        lines.append("## Silence Sequence")
        lines.append("To fully silence this patch:")
        step = 1

        # First kill feedback
        for loop in self.feedback_loops:
            if loop.gain_node:
                lines.append(f"{step}. Set `{loop.gain_node}` to 0 (kill feedback)")
                step += 1

        for buf in self.delay_buffers:
            if buf.feedback_multiplier:
                node, _ = buf.feedback_multiplier
                lines.append(f"{step}. Set `{node}` to 0 (kill {buf.name} feedback)")
                step += 1

        if step > 1:
            lines.append(f"{step}. Wait ~10ms for buffers to drain")
            step += 1

        # Then clear buffers
        for buf in self.delay_buffers:
            lines.append(f"{step}. `; {buf.name} const 0`")
            step += 1

        for tbl in self.tables:
            lines.append(f"{step}. `; {tbl.name} const 0`")
            step += 1

        return "\n".join(lines)


class StateAnalyzer:
    """Analyzes stateful elements in a Pd patch."""

    def __init__(self, ir_patch: IRPatch):
        self.ir = ir_patch
        self._analyzer = GraphAnalyzer(ir_patch)
        self._node_map: Dict[str, IRNode] = {n.id: n for n in ir_patch.nodes}

    def analyze(self) -> StateAnalysis:
        """Perform complete state analysis."""
        delay_buffers = self._find_delay_buffers()
        feedback_loops = self._find_feedback_loops()
        tables = self._find_tables()

        return StateAnalysis(
            delay_buffers=delay_buffers,
            feedback_loops=feedback_loops,
            tables=tables,
        )

    def _find_delay_buffers(self) -> List[DelayBuffer]:
        """Find all delay buffers and their properties."""
        buffers = []

        # Find delwrite~ nodes
        writers: Dict[str, Tuple[str, str]] = {}  # name -> (node_id, size)
        for node in self.ir.nodes:
            if node.type == 'delwrite~' and node.args:
                name = str(node.args[0])
                size = str(node.args[1]) if len(node.args) > 1 else "?"
                writers[name] = (node.id, size)

        # Find corresponding readers
        readers: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for node in self.ir.nodes:
            if node.type in ('delread~', 'delread4~', 'vd~') and node.args:
                name = str(node.args[0])
                time = str(node.args[1]) if len(node.args) > 1 else "variable"
                readers[name].append((node.id, time))

        # Build buffer objects
        for name, (writer_id, size) in writers.items():
            # Look for feedback multiplier
            feedback = self._find_feedback_multiplier(writer_id, name)

            buffers.append(DelayBuffer(
                name=name,
                size_ms=size,
                writer_node=writer_id,
                reader_nodes=readers.get(name, []),
                feedback_multiplier=feedback,
            ))

        return buffers

    def _find_feedback_multiplier(self, writer_id: str, delay_name: str) -> Optional[Tuple[str, str]]:
        """Find the *~ node that controls feedback into a delay writer."""
        # Get predecessors of the writer
        preds = self._analyzer.get_predecessors(writer_id)

        for pred_id in preds:
            pred = self._node_map.get(pred_id)
            if not pred:
                continue

            # Direct *~ predecessor
            if pred.type == '*~':
                val = str(pred.args[0]) if pred.args else "?"
                return (pred_id, val)

            # Check one level deeper
            pred_preds = self._analyzer.get_predecessors(pred_id)
            for pp_id in pred_preds:
                pp = self._node_map.get(pp_id)
                if pp and pp.type == '*~':
                    val = str(pp.args[0]) if pp.args else "?"
                    return (pp_id, val)

        return None

    def _find_feedback_loops(self) -> List[FeedbackLoop]:
        """Find feedback loops from SCC analysis."""
        loops = []

        if not self.ir.analysis or not self.ir.analysis.sccs:
            return loops

        for scc in self.ir.analysis.sccs:
            if len(scc.nodes) < 2:
                continue

            # Find gain control node in the loop
            gain_node = None
            gain_value = None
            delay_name = None

            for node_id in scc.nodes:
                node = self._node_map.get(node_id)
                if not node:
                    continue

                if node.type == '*~':
                    gain_node = node_id
                    gain_value = str(node.args[0]) if node.args else "?"
                elif node.type == 'delwrite~' and node.args:
                    delay_name = str(node.args[0])

            loops.append(FeedbackLoop(
                nodes=list(scc.nodes),
                gain_node=gain_node,
                gain_value=gain_value,
                delay_name=delay_name,
            ))

        return loops

    def _find_tables(self) -> List[TableBuffer]:
        """Find all tables/arrays."""
        tables = []

        for node in self.ir.nodes:
            if node.type == 'table' and node.args:
                name = str(node.args[0])
                size = str(node.args[1]) if len(node.args) > 1 else None
                tables.append(TableBuffer(name=name, node_id=node.id, size=size))
            elif node.type == 'array' and node.args:
                # Arrays defined via #X array
                name = str(node.args[0])
                size = str(node.args[1]) if len(node.args) > 1 else None
                tables.append(TableBuffer(name=name, node_id=node.id, size=size))

        # Also check for tabwrite~/tabread~ to find named tables
        table_names: Set[str] = set()
        for node in self.ir.nodes:
            if node.type in ('tabwrite~', 'tabread~', 'tabread4~', 'tabplay~', 'tabosc4~'):
                if node.args:
                    table_names.add(str(node.args[0]))

        # Add any tables we found via usage but not definition
        existing_names = {t.name for t in tables}
        for name in table_names - existing_names:
            tables.append(TableBuffer(name=name, node_id="(external)", size=None))

        return tables


def analyze_state(ir_patch: IRPatch) -> StateAnalysis:
    """Analyze stateful elements in a patch."""
    analyzer = StateAnalyzer(ir_patch)
    return analyzer.analyze()


def analyze_state_from_file(filepath: str) -> StateAnalysis:
    """Analyze stateful elements from a .pd file."""
    from .build import build_ir_from_file
    ir_patch = build_ir_from_file(filepath)
    return analyze_state(ir_patch)
