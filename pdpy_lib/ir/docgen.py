"""
Documentation Generator for Pure Data Abstractions.

This module auto-generates documentation for Pd abstractions by analyzing
$N argument usage patterns and extracting manual documentation from comments.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict
from pathlib import Path
import json

from .core import IRPatch, IRNode, NodeKind, Domain


@dataclass
class ArgUsage:
    """A single usage of a $N argument in the patch."""
    arg_index: int           # e.g., 1 for $1
    context: str             # "symbol_name", "object_arg", "message", "arithmetic"
    object_type: str         # The Pd object type where it's used
    usage_pattern: str       # e.g., "r $1Touch" or "mod $5"


@dataclass
class ArgDocumentation:
    """Documentation for a single argument."""
    index: int
    usages: List[ArgUsage] = field(default_factory=list)
    inferred_type: str = "unknown"       # "symbol", "number", "patch_name"
    inferred_purpose: str = ""           # "track identifier", "buffer count"
    manual_description: Optional[str] = None
    suggested_name: str = ""             # "track_name", "buffer_count"


@dataclass
class AbstractionDoc:
    """Complete documentation for an abstraction."""
    name: str
    path: str
    arg_count: int
    arguments: List[ArgDocumentation] = field(default_factory=list)
    inlets: List[Dict[str, Any]] = field(default_factory=list)
    outlets: List[Dict[str, Any]] = field(default_factory=list)
    exposed_symbols: List[str] = field(default_factory=list)
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "path": self.path,
            "arg_count": self.arg_count,
            "arguments": [
                {
                    "index": arg.index,
                    "name": arg.suggested_name or f"arg{arg.index}",
                    "type": arg.inferred_type,
                    "description": arg.manual_description or arg.inferred_purpose,
                    "usages": [
                        {
                            "context": u.context,
                            "object_type": u.object_type,
                            "pattern": u.usage_pattern,
                        }
                        for u in arg.usages
                    ],
                }
                for arg in self.arguments
            ],
            "inlets": self.inlets,
            "outlets": self.outlets,
            "exposed_symbols": self.exposed_symbols,
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Generate markdown documentation."""
        lines = []
        lines.append(f"# {self.name}")
        lines.append("")

        if self.summary:
            lines.append(self.summary)
            lines.append("")

        # Arguments table
        if self.arguments:
            lines.append("## Arguments")
            lines.append("")
            lines.append("| # | Name | Type | Description |")
            lines.append("|---|------|------|-------------|")
            for arg in self.arguments:
                name = arg.suggested_name or f"arg{arg.index}"
                desc = arg.manual_description or arg.inferred_purpose or "-"
                lines.append(f"| ${arg.index} | {name} | {arg.inferred_type} | {desc} |")
            lines.append("")

        # Interface section
        if self.inlets or self.outlets:
            lines.append("## Interface")
            lines.append("")
            for inlet in self.inlets:
                domain_str = f" ({inlet.get('domain', 'control')})" if inlet.get('domain') else ""
                lines.append(f"- inlet {inlet['index']}{domain_str}: {inlet.get('description', 'input')}")
            for outlet in self.outlets:
                domain_str = f" ({outlet.get('domain', 'control')})" if outlet.get('domain') else ""
                lines.append(f"- outlet {outlet['index']}{domain_str}: {outlet.get('description', 'output')}")
            lines.append("")

        # Exposed symbols
        if self.exposed_symbols:
            lines.append("## Symbols")
            lines.append("")
            sends = [s for s in self.exposed_symbols if s.startswith("s:")]
            receives = [s for s in self.exposed_symbols if s.startswith("r:")]
            if sends:
                lines.append(f"Sends: {', '.join(s[2:] for s in sends)}")
            if receives:
                lines.append(f"Receives: {', '.join(s[2:] for s in receives)}")
            lines.append("")

        return "\n".join(lines)


class ArgExtractor:
    """Extracts $N argument usages from IR patches."""

    # Pattern to find $N references (both escaped \$N and raw $N)
    ARG_PATTERN = re.compile(r'\\?\$(\d+)')

    # Object types that use $1 as a symbol/name
    SYMBOL_OBJECTS = {'r', 's', 'receive', 'send', 'r~', 's~', 'receive~', 'send~',
                      'throw~', 'catch~', 'value', 'v', 'table', 'array',
                      'soundfiler', 'tabread', 'tabread~', 'tabwrite', 'tabwrite~',
                      'tabread4~', 'tabplay~', 'tabosc4~'}

    # Objects where numeric arguments have specific meanings
    NUMERIC_CONTEXTS = {
        'clone': {1: 'instance_count'},
        'mod': {0: 'modulo_divisor'},
        '%': {0: 'modulo_divisor'},
        'del': {0: 'delay_ms'},
        'delay': {0: 'delay_ms'},
        'metro': {0: 'interval_ms'},
        'pipe': {-1: 'delay_ms'},  # -1 means last arg
        'line': {0: 'target_value', 1: 'ramp_time'},
        'line~': {0: 'target_value', 1: 'ramp_time'},
        'vline~': {0: 'target_value', 1: 'ramp_time'},
        'pack': {-1: 'pack_element'},
        'unpack': {-1: 'unpack_element'},
        'route': {-1: 'selector'},
        'select': {-1: 'match_value'},
        'sel': {-1: 'match_value'},
        'moses': {0: 'split_value'},
        'random': {0: 'range'},
        'expr': {-1: 'expression_var'},
        'osc~': {0: 'frequency'},
        'phasor~': {0: 'frequency'},
        'noise~': {},
        'hip~': {0: 'cutoff_hz'},
        'lop~': {0: 'cutoff_hz'},
        'bp~': {0: 'center_freq', 1: 'q'},
        'vcf~': {0: 'center_freq', 1: 'q'},
        'delread~': {0: 'delay_name', 1: 'delay_ms'},
        'delwrite~': {0: 'delay_name', 1: 'max_delay_ms'},
        'vd~': {0: 'delay_name'},
    }

    def __init__(self):
        self._usages: Dict[int, List[ArgUsage]] = defaultdict(list)

    def extract_from_ir(self, ir_patch: IRPatch) -> Dict[int, List[ArgUsage]]:
        """Find all $N references and their contexts."""
        self._usages = defaultdict(list)

        for node in ir_patch.nodes:
            self._extract_from_node(node)

        return dict(self._usages)

    def _extract_from_node(self, node: IRNode) -> None:
        """Extract argument usages from a single node."""
        # Skip comments for argument extraction (but we'll use them for manual docs)
        if node.kind == NodeKind.COMMENT:
            return

        obj_type = node.type

        # Check each argument
        for i, arg in enumerate(node.args):
            arg_str = str(arg)
            for match in self.ARG_PATTERN.finditer(arg_str):
                arg_num = int(match.group(1))
                if arg_num == 0:
                    # $0 is instance ID, not a creation argument
                    continue

                context = self._classify_context(obj_type, i, arg_str, match)
                usage_pattern = self._build_usage_pattern(obj_type, node.args, i, arg_str)

                self._usages[arg_num].append(ArgUsage(
                    arg_index=arg_num,
                    context=context,
                    object_type=obj_type,
                    usage_pattern=usage_pattern,
                ))

        # Also check message nodes for $N in message content
        if node.kind == NodeKind.MESSAGE:
            for i, arg in enumerate(node.args):
                arg_str = str(arg)
                for match in self.ARG_PATTERN.finditer(arg_str):
                    arg_num = int(match.group(1))
                    if arg_num == 0:
                        continue

                    context = "message"
                    usage_pattern = f"msg: {' '.join(str(a) for a in node.args)}"

                    self._usages[arg_num].append(ArgUsage(
                        arg_index=arg_num,
                        context=context,
                        object_type="message",
                        usage_pattern=usage_pattern,
                    ))

    def _classify_context(self, obj_type: str, arg_index: int, arg_str: str,
                          match: re.Match) -> str:
        """Classify the context in which an argument is used."""
        # Check if it's part of a symbol name (e.g., "$1Touch", "track-$1")
        match_start = match.start()
        match_end = match.end()

        # If there's text directly adjacent to the $N, it's a symbol construction
        has_prefix = match_start > 0 and arg_str[match_start - 1] not in ' \t,'
        has_suffix = match_end < len(arg_str) and arg_str[match_end] not in ' \t,'

        if has_prefix or has_suffix:
            return "symbol_name"

        # Check if used in arithmetic context
        if any(op in arg_str for op in ['*', '/', '+', '-', '%', 'expr']):
            return "arithmetic"

        # Check if it's the first argument of a symbol object
        if obj_type in self.SYMBOL_OBJECTS and arg_index == 0:
            return "symbol_name"

        # Default: object argument
        return "object_arg"

    def _build_usage_pattern(self, obj_type: str, args: List[str], arg_index: int,
                             arg_str: str) -> str:
        """Build a readable usage pattern string."""
        if len(args) <= 3:
            return f"{obj_type} {' '.join(str(a) for a in args)}"
        else:
            # Truncate for readability
            return f"{obj_type} ... {arg_str} ..."


class DocGenerator:
    """Generates documentation for abstractions."""

    # Pattern to extract manual documentation from comments
    # Matches patterns like "$1: description" or "\$1: description"
    MANUAL_DOC_PATTERN = re.compile(r'\\?\$(\d+)\s*:\s*([^,$\\;]+)')

    def __init__(self):
        self._extractor = ArgExtractor()

    def generate(self, ir_patch: IRPatch, path: str = "") -> AbstractionDoc:
        """Generate documentation for an abstraction from its IR."""
        name = ir_patch.patch.name if ir_patch.patch else "unknown"
        path = path or (ir_patch.patch.path if ir_patch.patch else "")

        # Extract argument usages
        usages = self._extractor.extract_from_ir(ir_patch)

        # Extract manual documentation from comments
        manual_docs = self._extract_manual_docs(ir_patch)

        # Determine argument count (highest $N found)
        arg_count = max(usages.keys()) if usages else 0

        # Build argument documentation
        arguments = []
        for i in range(1, arg_count + 1):
            arg_usages = usages.get(i, [])
            inferred_type, inferred_purpose = self._infer_type_and_purpose(i, arg_usages)
            suggested_name = self._suggest_name(i, arg_usages, inferred_type, inferred_purpose)

            arguments.append(ArgDocumentation(
                index=i,
                usages=arg_usages,
                inferred_type=inferred_type,
                inferred_purpose=inferred_purpose,
                manual_description=manual_docs.get(i),
                suggested_name=suggested_name,
            ))

        # Extract interface (inlets/outlets)
        inlets, outlets = self._extract_interface(ir_patch)

        # Extract exposed symbols
        exposed_symbols = self._extract_exposed_symbols(ir_patch)

        # Extract summary from comments
        summary = self._extract_summary(ir_patch)

        return AbstractionDoc(
            name=name,
            path=path,
            arg_count=arg_count,
            arguments=arguments,
            inlets=inlets,
            outlets=outlets,
            exposed_symbols=exposed_symbols,
            summary=summary,
        )

    def _extract_manual_docs(self, ir_patch: IRPatch) -> Dict[int, str]:
        """Extract manual documentation from comments."""
        docs = {}

        # Check comment nodes
        for node in ir_patch.nodes:
            if node.kind == NodeKind.COMMENT and node.text:
                for match in self.MANUAL_DOC_PATTERN.finditer(node.text):
                    arg_num = int(match.group(1))
                    description = match.group(2).strip()
                    if arg_num > 0:  # Skip $0
                        docs[arg_num] = description

        # Also check text.comments section
        if ir_patch.text and ir_patch.text.comments:
            for comment in ir_patch.text.comments:
                if comment.text:
                    for match in self.MANUAL_DOC_PATTERN.finditer(comment.text):
                        arg_num = int(match.group(1))
                        description = match.group(2).strip()
                        if arg_num > 0:  # Skip $0
                            docs[arg_num] = description

        return docs

    def _infer_type_and_purpose(self, arg_index: int,
                                 usages: List[ArgUsage]) -> tuple[str, str]:
        """Infer the type and purpose of an argument from its usages."""
        if not usages:
            return "unknown", ""

        # Count context types
        context_counts = defaultdict(int)
        object_types = set()
        for usage in usages:
            context_counts[usage.context] += 1
            object_types.add(usage.object_type)

        # Determine type based on context
        if context_counts["symbol_name"] > 0:
            inferred_type = "symbol"
        elif context_counts["arithmetic"] > 0:
            inferred_type = "number"
        elif any(ot in ArgExtractor.SYMBOL_OBJECTS for ot in object_types):
            inferred_type = "symbol"
        else:
            # Check specific object contexts
            for usage in usages:
                if usage.object_type in ArgExtractor.NUMERIC_CONTEXTS:
                    inferred_type = "number"
                    break
            else:
                # Default based on first usage
                inferred_type = "symbol" if context_counts["symbol_name"] else "unknown"

        # Infer purpose
        purpose = self._infer_purpose(usages, inferred_type)

        return inferred_type, purpose

    def _infer_purpose(self, usages: List[ArgUsage], inferred_type: str) -> str:
        """Infer the purpose of an argument from its usages."""
        if not usages:
            return ""

        # Check for specific patterns
        for usage in usages:
            obj_type = usage.object_type

            # Send/receive patterns -> identifier
            if obj_type in {'r', 's', 'receive', 'send', 'r~', 's~'}:
                if usage.context == "symbol_name":
                    return "identifier prefix for send/receive"
                return "send/receive name"

            # Clone -> instance count
            if obj_type == 'clone':
                return "instance count"

            # Timing objects
            if obj_type in {'del', 'delay', 'metro', 'pipe'}:
                return "time interval (ms)"

            # Data structures
            if obj_type in {'getsize', 'element', 'get', 'set'}:
                # Check arg position from usage pattern
                if 'getsize' in usage.usage_pattern or 'element' in usage.usage_pattern:
                    return "template or array name"
                return "data structure field"

            # Arithmetic
            if obj_type in {'mod', '%'}:
                return "modulo divisor"

            # Route/select
            if obj_type in {'route', 'select', 'sel'}:
                return "selector value"

        # Generic purposes based on type
        if inferred_type == "symbol":
            return "identifier/name"
        elif inferred_type == "number":
            return "numeric parameter"

        return ""

    def _suggest_name(self, arg_index: int, usages: List[ArgUsage],
                      inferred_type: str, inferred_purpose: str) -> str:
        """Suggest a name for an argument."""
        if not usages:
            return f"arg{arg_index}"

        # Try to extract a meaningful name from usage patterns
        for usage in usages:
            pattern = usage.usage_pattern

            # Look for patterns like "r $1-something" or "r something$1"
            if usage.context == "symbol_name":
                # Try to extract the base name
                match = re.search(r'\$\d+[-_]?(\w+)', pattern)
                if match:
                    suffix = match.group(1)
                    if suffix and len(suffix) > 1:
                        return f"{suffix}_prefix"

                match = re.search(r'(\w+)[-_]?\$\d+', pattern)
                if match:
                    prefix = match.group(1)
                    if prefix and len(prefix) > 1:
                        return f"{prefix}_suffix"

        # Fall back to purpose-based names
        purpose_to_name = {
            "instance count": "count",
            "time interval (ms)": "time_ms",
            "identifier prefix for send/receive": "name",
            "send/receive name": "symbol",
            "template or array name": "template",
            "data structure field": "field",
            "modulo divisor": "divisor",
            "selector value": "selector",
            "identifier/name": "name",
            "numeric parameter": "value",
        }

        if inferred_purpose in purpose_to_name:
            base_name = purpose_to_name[inferred_purpose]
            return f"{base_name}{arg_index}" if arg_index > 1 else base_name

        return f"arg{arg_index}"

    def _extract_interface(self, ir_patch: IRPatch) -> tuple[List[Dict], List[Dict]]:
        """Extract inlet/outlet information from the patch."""
        inlets = []
        outlets = []

        for node in ir_patch.nodes:
            if node.type == 'inlet':
                inlets.append({
                    "index": len(inlets),
                    "domain": "control",
                    "description": "control input",
                })
            elif node.type == 'inlet~':
                inlets.append({
                    "index": len(inlets),
                    "domain": "signal",
                    "description": "signal input",
                })
            elif node.type == 'outlet':
                outlets.append({
                    "index": len(outlets),
                    "domain": "control",
                    "description": "control output",
                })
            elif node.type == 'outlet~':
                outlets.append({
                    "index": len(outlets),
                    "domain": "signal",
                    "description": "signal output",
                })

        return inlets, outlets

    def _extract_exposed_symbols(self, ir_patch: IRPatch) -> List[str]:
        """Extract send/receive symbols that contain $N references."""
        exposed = []

        for symbol in ir_patch.symbols:
            # Check if the symbol contains $N (but not $0)
            if re.search(r'\\?\$[1-9]', symbol.raw):
                if symbol.writers:
                    exposed.append(f"s:{symbol.raw}")
                if symbol.readers:
                    exposed.append(f"r:{symbol.raw}")

        return list(set(exposed))

    def _extract_summary(self, ir_patch: IRPatch) -> Optional[str]:
        """Extract a summary from the first substantial comment."""
        # Collect all comment texts
        comment_texts = []

        # Check comment nodes
        for node in ir_patch.nodes:
            if node.kind == NodeKind.COMMENT and node.text:
                comment_texts.append(node.text)

        # Also check text.comments section
        if ir_patch.text and ir_patch.text.comments:
            for comment in ir_patch.text.comments:
                if comment.text:
                    comment_texts.append(comment.text)

        # Find the first substantial comment
        for text in comment_texts:
            text = text.strip()
            # Skip short comments or those that look like argument docs
            if len(text) > 20 and not text.startswith('$') and not text.startswith('\\$'):
                # Clean up the text
                text = re.sub(r'\s+', ' ', text)
                # Truncate if too long
                if len(text) > 200:
                    text = text[:197] + "..."
                return text

        return None


def generate_doc(ir_patch: IRPatch, path: str = "") -> AbstractionDoc:
    """Generate documentation for an abstraction.

    Convenience function that creates a DocGenerator and generates docs.

    Args:
        ir_patch: The IR representation of the patch
        path: Optional path to the .pd file

    Returns:
        AbstractionDoc instance
    """
    generator = DocGenerator()
    return generator.generate(ir_patch, path)


def generate_doc_from_file(filepath: str) -> AbstractionDoc:
    """Generate documentation from a .pd file.

    Args:
        filepath: Path to the .pd file

    Returns:
        AbstractionDoc instance
    """
    from .build import build_ir_from_file
    ir_patch = build_ir_from_file(filepath)
    return generate_doc(ir_patch, filepath)
