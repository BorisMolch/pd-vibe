"""
Prose Explanation Generator for Pure Data Patches.

Generates natural language summaries of what a patch does,
making it easy for LLMs to understand signal and control flow.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from .core import (
    IRPatch,
    IRNode,
    IREdge,
    NodeKind,
    EdgeKind,
    Domain,
    SymbolKind,
)
from .analysis import GraphAnalyzer
from .registry import get_registry, ObjectSpec


@dataclass
class PathSegment:
    """A segment of a signal or control path."""
    node_id: str
    node_type: str
    args: List[str]
    description: str  # Human-readable description


@dataclass
class SignalPath:
    """A traced signal path from source to sink."""
    source_type: str  # "oscillator", "input", "noise", "file"
    sink_type: str    # "output", "delay", "send"
    segments: List[PathSegment]

    def to_prose(self) -> str:
        """Convert path to prose description."""
        if not self.segments:
            return ""

        parts = []
        for i, seg in enumerate(self.segments):
            if i == 0:
                parts.append(seg.description)
            else:
                parts.append(f"→ {seg.description}")

        return " ".join(parts)


@dataclass
class PatchExplanation:
    """Complete explanation of a patch."""
    name: str
    patch_type: str  # "synthesizer", "effect", "sequencer", "utility", "mixed"
    summary: str
    signal_narrative: str
    control_narrative: str
    external_deps: List[str]
    key_objects: List[str]

    def to_text(self) -> str:
        """Generate full text explanation."""
        lines = []

        lines.append(f"# {self.name}")
        lines.append("")
        lines.append(f"**Type:** {self.patch_type}")
        lines.append("")
        lines.append("## Summary")
        lines.append(self.summary)
        lines.append("")

        if self.signal_narrative:
            lines.append("## Signal Flow")
            lines.append(self.signal_narrative)
            lines.append("")

        if self.control_narrative:
            lines.append("## Control Flow")
            lines.append(self.control_narrative)
            lines.append("")

        if self.external_deps:
            lines.append("## External Dependencies")
            for dep in self.external_deps:
                lines.append(f"- {dep}")
            lines.append("")

        if self.key_objects:
            lines.append("## Key Objects")
            for obj in self.key_objects:
                lines.append(f"- {obj}")
            lines.append("")

        return "\n".join(lines)


class PatchExplainer:
    """Generates natural language explanations of Pd patches."""

    # Object categories for classification
    AUDIO_SOURCES = {'osc~', 'phasor~', 'noise~', 'adc~', 'readsf~', 'tabosc4~',
                     'tabplay~', 'inlet~'}
    AUDIO_SINKS = {'dac~', 'writesf~', 'outlet~', 'tabwrite~', 'delwrite~',
                   'throw~', 's~', 'send~'}
    OSCILLATORS = {'osc~', 'phasor~', 'tabosc4~'}
    FILTERS = {'lop~', 'hip~', 'bp~', 'vcf~', 'biquad~', 'rpole~', 'rzero~'}
    DELAYS = {'delwrite~', 'delread~', 'delread4~', 'vd~'}
    ENVELOPES = {'line~', 'vline~', 'adsr~'}
    EFFECTS = {'reverb~', 'freeverb~', 'chorus~', 'flanger~'}
    MATH_OPS = {'+~', '-~', '*~', '/~', 'clip~', 'wrap~', 'abs~', 'sqrt~'}

    CONTROL_SOURCES = {'metro', 'inlet', 'r', 'receive', 'notein', 'ctlin',
                       'bendin', 'midiin', 'loadbang'}
    CONTROL_SINKS = {'outlet', 's', 'send', 'noteout', 'ctlout', 'midiout'}
    SEQUENCER_OBJECTS = {'metro', 'counter', 'select', 'route', 'moses',
                         'spigot', 'gate', 'switch'}

    def __init__(self):
        self._registry = get_registry()

    def explain(self, ir_patch: IRPatch) -> PatchExplanation:
        """Generate a complete explanation of a patch."""
        analyzer = GraphAnalyzer(ir_patch)

        # Classify patch type
        patch_type = self._classify_patch(ir_patch)

        # Get patch name
        name = ir_patch.patch.name if ir_patch.patch else "Unknown Patch"

        # Generate narratives
        signal_narrative = self._explain_signal_flow(ir_patch, analyzer)
        control_narrative = self._explain_control_flow(ir_patch, analyzer)

        # Find external dependencies
        external_deps = self._find_external_deps(ir_patch)

        # Identify key objects
        key_objects = self._identify_key_objects(ir_patch)

        # Generate summary
        summary = self._generate_summary(
            ir_patch, patch_type, signal_narrative, control_narrative, external_deps
        )

        return PatchExplanation(
            name=name,
            patch_type=patch_type,
            summary=summary,
            signal_narrative=signal_narrative,
            control_narrative=control_narrative,
            external_deps=external_deps,
            key_objects=key_objects,
        )

    def _classify_patch(self, ir_patch: IRPatch) -> str:
        """Classify the patch type based on its contents."""
        node_types = {n.type for n in ir_patch.nodes}

        has_audio_io = bool(node_types & {'adc~', 'dac~', 'inlet~', 'outlet~'})
        has_oscillators = bool(node_types & self.OSCILLATORS)
        has_filters = bool(node_types & self.FILTERS)
        has_delays = bool(node_types & self.DELAYS)
        has_sequencer = bool(node_types & self.SEQUENCER_OBJECTS)
        has_midi = bool(node_types & {'notein', 'noteout', 'ctlin', 'ctlout'})

        # Determine type
        if has_oscillators and has_audio_io and not {'adc~'} & node_types:
            if has_sequencer or has_midi:
                return "synthesizer/sequencer"
            return "synthesizer"
        elif {'adc~', 'dac~'} <= node_types:
            if has_delays:
                return "effect (delay-based)"
            if has_filters:
                return "effect (filter-based)"
            return "effect"
        elif has_sequencer or has_midi:
            return "sequencer/controller"
        elif node_types & {'inlet', 'outlet', 'inlet~', 'outlet~'}:
            return "abstraction"
        elif has_audio_io:
            return "audio processor"
        else:
            return "utility"

    def _explain_signal_flow(self, ir_patch: IRPatch, analyzer: GraphAnalyzer) -> str:
        """Generate prose explanation of signal flow."""
        lines = []

        # First, detect delay feedback patterns
        delay_info = self._detect_delay_patterns(ir_patch)
        if delay_info:
            lines.append(delay_info)
            lines.append("")

        # Find signal sources and trace to sinks
        sources = []
        for node in ir_patch.nodes:
            if node.type in self.AUDIO_SOURCES:
                sources.append(node)

        if not sources:
            return "\n".join(lines) if lines else ""

        # Build signal path descriptions
        paths = []
        visited_paths = set()

        for source in sources:
            source_paths = analyzer.trace_to_output(source.id)
            for path in source_paths:
                path_key = tuple(path)
                if path_key not in visited_paths:
                    visited_paths.add(path_key)
                    path_desc = self._describe_signal_path(ir_patch, path)
                    if path_desc:
                        paths.append(path_desc)

        if not paths:
            # Try to describe isolated signal chains
            signal_chains = analyzer.find_linear_chains(Domain.SIGNAL)
            for chain in signal_chains[:3]:  # Limit to first 3
                path_desc = self._describe_signal_path(ir_patch, chain)
                if path_desc:
                    paths.append(path_desc)

        if paths:
            # Combine into narrative
            if len(paths) == 1:
                lines.append(paths[0])
            else:
                lines.append("Signal paths:")
                for i, path in enumerate(paths[:5], 1):  # Limit to 5 paths
                    lines.append(f"{i}. {path}")

        return "\n".join(lines) if lines else ""

    def _detect_delay_patterns(self, ir_patch: IRPatch) -> str:
        """Detect and describe delay/feedback patterns."""
        # Find delay write/read pairs
        delay_writes = {}
        delay_reads = {}

        for node in ir_patch.nodes:
            if node.type == 'delwrite~' and node.args:
                name = node.args[0]
                size = node.args[1] if len(node.args) > 1 else "?"
                delay_writes[name] = (node, size)
            elif node.type in ('delread~', 'delread4~', 'vd~') and node.args:
                name = node.args[0]
                time = node.args[1] if len(node.args) > 1 else "variable"
                delay_reads.setdefault(name, []).append((node, time))

        if not delay_writes:
            return ""

        descriptions = []
        for name, (write_node, size) in delay_writes.items():
            if name in delay_reads:
                reads = delay_reads[name]
                read_times = [t for _, t in reads]
                if len(reads) == 1:
                    time = read_times[0]
                    descriptions.append(
                        f"Delay feedback loop '{name}': {size}ms buffer, read at {time}ms"
                    )
                else:
                    descriptions.append(
                        f"Multi-tap delay '{name}': {size}ms buffer, taps at {', '.join(str(t) for t in read_times)}ms"
                    )
            else:
                descriptions.append(f"Delay line '{name}': {size}ms buffer (write only)")

        if descriptions:
            return "**Delay/feedback:** " + "; ".join(descriptions)
        return ""

    def _describe_signal_path(self, ir_patch: IRPatch, path: List[str]) -> str:
        """Describe a signal path in prose."""
        if not path:
            return ""

        descriptions = []

        for node_id in path:
            node = ir_patch.get_node(node_id)
            if not node:
                continue

            desc = self._describe_node(node)
            if desc:
                descriptions.append(desc)

        if not descriptions:
            return ""

        # Join with arrows
        return " → ".join(descriptions)

    def _describe_node(self, node: IRNode) -> str:
        """Generate a human-readable description of a node."""
        obj_type = node.type
        args = node.args

        # Get spec from registry for richer descriptions
        spec = self._registry.get(obj_type) if self._registry else None

        # Oscillators
        if obj_type == 'osc~':
            freq = args[0] if args else "variable"
            return f"sine oscillator ({freq} Hz)"
        elif obj_type == 'phasor~':
            freq = args[0] if args else "variable"
            return f"sawtooth/ramp ({freq} Hz)"
        elif obj_type == 'noise~':
            return "white noise"

        # I/O
        elif obj_type == 'adc~':
            return "audio input"
        elif obj_type == 'dac~':
            return "audio output"
        elif obj_type == 'inlet~':
            return "signal inlet"
        elif obj_type == 'outlet~':
            return "signal outlet"

        # Filters
        elif obj_type == 'lop~':
            cutoff = args[0] if args else "variable"
            return f"lowpass filter ({cutoff} Hz)"
        elif obj_type == 'hip~':
            cutoff = args[0] if args else "variable"
            return f"highpass filter ({cutoff} Hz)"
        elif obj_type == 'bp~':
            freq = args[0] if args else "variable"
            return f"bandpass filter ({freq} Hz)"
        elif obj_type == 'vcf~':
            return "resonant filter"

        # Math
        elif obj_type == '*~':
            if args:
                return f"multiply by {args[0]}"
            return "multiply"
        elif obj_type == '+~':
            if args:
                return f"add {args[0]}"
            return "add/mix"
        elif obj_type == '-~':
            return "subtract"
        elif obj_type == '/~':
            return "divide"
        elif obj_type == 'clip~':
            if len(args) >= 2:
                return f"clip to [{args[0]}, {args[1]}]"
            return "clip"

        # Delay
        elif obj_type == 'delwrite~':
            name = args[0] if args else "delay"
            size = args[1] if len(args) > 1 else "?"
            return f"write to delay '{name}' ({size}ms buffer)"
        elif obj_type == 'delread~':
            name = args[0] if args else "delay"
            time = args[1] if len(args) > 1 else "variable"
            return f"read from delay '{name}' ({time}ms)"
        elif obj_type == 'delread4~':
            name = args[0] if args else "delay"
            return f"interpolated delay read '{name}'"
        elif obj_type == 'vd~':
            name = args[0] if args else "delay"
            return f"variable delay '{name}'"

        # Envelopes
        elif obj_type == 'line~':
            return "envelope/ramp generator"
        elif obj_type == 'vline~':
            return "sample-accurate envelope"

        # Tables
        elif obj_type == 'tabread4~':
            name = args[0] if args else "table"
            return f"read table '{name}'"
        elif obj_type == 'tabosc4~':
            name = args[0] if args else "table"
            return f"wavetable oscillator '{name}'"

        # Default: use type name
        else:
            if args:
                return f"{obj_type}({', '.join(str(a) for a in args[:2])})"
            return obj_type

    def _explain_control_flow(self, ir_patch: IRPatch, analyzer: GraphAnalyzer) -> str:
        """Generate prose explanation of control flow."""
        # Find control sources
        control_sources = []
        for node in ir_patch.nodes:
            if node.type in self.CONTROL_SOURCES:
                control_sources.append(node)

        if not control_sources:
            return ""

        descriptions = []

        # Describe each control source and what it affects
        for source in control_sources[:5]:  # Limit
            desc = self._describe_control_source(ir_patch, source, analyzer)
            if desc:
                descriptions.append(desc)

        if not descriptions:
            return ""

        return "\n".join(descriptions)

    def _describe_control_source(self, ir_patch: IRPatch, source: IRNode,
                                  analyzer: GraphAnalyzer) -> str:
        """Describe what a control source does."""
        source_type = source.type

        # Get what it connects to
        successors = analyzer.get_successors(source.id)
        if not successors:
            return ""

        targets = []
        for succ_id in successors[:3]:
            succ = ir_patch.get_node(succ_id)
            if succ:
                targets.append(self._describe_node(succ))

        if not targets:
            return ""

        # Build description
        if source_type == 'metro':
            interval = source.args[0] if source.args else "variable"
            return f"- Metro ({interval}ms) triggers: {', '.join(targets)}"
        elif source_type == 'loadbang':
            return f"- On load: {', '.join(targets)}"
        elif source_type in ('r', 'receive'):
            name = source.args[0] if source.args else "?"
            return f"- Receives '{name}' → {', '.join(targets)}"
        elif source_type == 'inlet':
            return f"- Control inlet → {', '.join(targets)}"
        elif source_type == 'notein':
            return f"- MIDI note input → {', '.join(targets)}"
        elif source_type == 'ctlin':
            return f"- MIDI CC input → {', '.join(targets)}"

        return ""

    def _find_external_deps(self, ir_patch: IRPatch) -> List[str]:
        """Find external symbol dependencies."""
        deps = []

        for symbol in ir_patch.symbols:
            if symbol.instance_local:
                continue

            has_writers = len(symbol.writers) > 0
            has_readers = len(symbol.readers) > 0

            if has_readers and not has_writers:
                deps.append(f"receives: {symbol.resolved}")
            elif has_writers and not has_readers:
                deps.append(f"sends: {symbol.resolved}")

        return deps

    def _identify_key_objects(self, ir_patch: IRPatch) -> List[str]:
        """Identify the most important objects in the patch."""
        key = []

        # Count object types
        type_counts = defaultdict(int)
        for node in ir_patch.nodes:
            type_counts[node.type] += 1

        # Add notable objects
        for obj_type in ['dac~', 'adc~', 'outlet~', 'inlet~']:
            if type_counts[obj_type]:
                key.append(f"{type_counts[obj_type]}x {obj_type}")

        # Add oscillators
        osc_count = sum(type_counts[o] for o in self.OSCILLATORS)
        if osc_count:
            key.append(f"{osc_count}x oscillator(s)")

        # Add filters
        filter_count = sum(type_counts[f] for f in self.FILTERS)
        if filter_count:
            key.append(f"{filter_count}x filter(s)")

        # Add delays
        delay_count = sum(type_counts[d] for d in self.DELAYS)
        if delay_count:
            key.append(f"{delay_count}x delay line(s)")

        return key

    def _generate_summary(self, ir_patch: IRPatch, patch_type: str,
                          signal_narrative: str, control_narrative: str,
                          external_deps: List[str]) -> str:
        """Generate a one-paragraph summary."""
        node_count = len(ir_patch.nodes)

        parts = []

        # Describe what it is based on type
        type_descriptions = {
            "synthesizer": "generates audio using oscillators",
            "synthesizer/sequencer": "generates and sequences audio",
            "effect": "processes audio",
            "effect (delay-based)": "processes audio using delay lines",
            "effect (filter-based)": "processes audio using filters",
            "sequencer/controller": "sequences or controls other patches",
            "abstraction": "is a reusable component",
            "audio processor": "processes audio signals",
            "utility": "performs utility/control operations",
        }
        desc = type_descriptions.get(patch_type, f"is a {patch_type}")
        parts.append(f"This patch {desc} ({node_count} objects).")

        # Detect key features
        features = []
        node_types = {n.type for n in ir_patch.nodes}

        if node_types & {'delwrite~', 'delread~', 'vd~'}:
            features.append("delay/feedback")
        if node_types & self.FILTERS:
            features.append("filtering")
        if node_types & {'*~'} and not node_types & self.OSCILLATORS:
            features.append("amplitude control")
        if node_types & {'throw~', 'catch~'}:
            features.append("bus routing")

        if features:
            parts.append(f"Features: {', '.join(features)}.")

        # Add external deps
        if external_deps:
            receives = [d.replace('receives: ', '') for d in external_deps if d.startswith('receives:')]
            sends = [d.replace('sends: ', '') for d in external_deps if d.startswith('sends:')]
            if receives:
                parts.append(f"Receives: {', '.join(receives[:3])}.")
            if sends:
                parts.append(f"Sends: {', '.join(sends[:3])}.")

        return " ".join(parts)


def explain_patch(ir_patch: IRPatch) -> PatchExplanation:
    """Generate an explanation for a patch.

    Convenience function that creates an explainer and generates explanation.

    Args:
        ir_patch: The IR representation of the patch

    Returns:
        PatchExplanation instance
    """
    explainer = PatchExplainer()
    return explainer.explain(ir_patch)


def explain_patch_from_file(filepath: str) -> PatchExplanation:
    """Generate an explanation from a .pd file.

    Args:
        filepath: Path to the .pd file

    Returns:
        PatchExplanation instance
    """
    from .build import build_ir_from_file
    ir_patch = build_ir_from_file(filepath)
    return explain_patch(ir_patch)
