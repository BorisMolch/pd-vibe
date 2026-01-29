"""
Known-Object Registry for Pure Data IR.

This module manages the registry of known Pure Data objects with their
inlet/outlet specifications, domain information, and symbol semantics.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from .core import Domain, SymbolKind


@dataclass
class IoletSpec:
    """Specification for an inlet or outlet."""
    domain: str  # "signal", "control", "signal_or_control"
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"domain": self.domain}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class ArgSpec:
    """Specification for an object argument."""
    name: str
    type: str  # "number", "symbol", "list"
    required: bool = False
    optional: bool = True
    default: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "type": self.type,
        }
        if self.required:
            d["required"] = True
        if self.default is not None:
            d["default"] = self.default
        return d


@dataclass
class SymbolSemantics:
    """Symbol semantics for send/receive type objects."""
    kind: SymbolKind
    role: str  # "writer" or "reader"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "role": self.role,
        }


@dataclass
class ObjectSpec:
    """Specification for a Pure Data object."""
    key: str
    library: str
    kind: str  # "dsp", "control", "gui", "subpatch"
    domain: Domain
    inlets: List[IoletSpec] = field(default_factory=list)
    outlets: List[IoletSpec] = field(default_factory=list)
    args: List[ArgSpec] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    symbol_semantics: Optional[SymbolSemantics] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "key": self.key,
            "library": self.library,
            "kind": self.kind,
            "domain": self.domain.value,
            "inlets": [i.to_dict() for i in self.inlets],
            "outlets": [o.to_dict() for o in self.outlets],
        }
        if self.args:
            d["args"] = [a.to_dict() for a in self.args]
        if self.aliases:
            d["aliases"] = self.aliases
        if self.symbol_semantics:
            d["symbol_semantics"] = self.symbol_semantics.to_dict()
        return d


@dataclass
class OverrideRule:
    """Rule for dynamic outlet/inlet counts based on arguments."""
    match_key: str
    rule: str  # e.g., "outlets = 1 + argc", "inlets = argc"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match": {"key": self.match_key},
            "rule": self.rule,
        }


class ObjectRegistry:
    """Registry of known Pure Data objects."""

    def __init__(self):
        self._objects: Dict[str, ObjectSpec] = {}
        self._aliases: Dict[str, str] = {}
        self._overrides: List[OverrideRule] = []
        self._sources: List[Dict[str, Any]] = []
        self.unknown_object_policy: str = "warn"

        # Load built-in objects
        self._load_builtin_objects()

    def _load_builtin_objects(self):
        """Load the built-in Pure Data vanilla objects."""
        # Control objects
        self._add_vanilla_control_objects()
        # DSP objects
        self._add_vanilla_dsp_objects()
        # Send/receive objects
        self._add_send_receive_objects()
        # Interface objects
        self._add_interface_objects()
        # Add override rules
        self._add_override_rules()

        self._sources.append({"name": "pd-vanilla", "version": "0.55"})

    def _add_vanilla_control_objects(self):
        """Add vanilla control objects."""
        control_objects = [
            # Math
            ("float", ["f"], 2, 1),
            ("int", ["i"], 2, 1),
            ("+", [], 2, 1),
            ("-", [], 2, 1),
            ("*", [], 2, 1),
            ("/", [], 2, 1),
            ("pow", [], 2, 1),
            ("log", [], 2, 1),
            ("exp", [], 1, 1),
            ("abs", [], 1, 1),
            ("sqrt", [], 1, 1),
            ("wrap", [], 1, 1),
            ("mod", ["%"], 2, 1),
            ("div", [], 2, 1),
            ("sin", [], 1, 1),
            ("cos", [], 1, 1),
            ("tan", [], 1, 1),
            ("atan", [], 1, 1),
            ("atan2", [], 2, 1),
            ("max", [], 2, 1),
            ("min", [], 2, 1),
            ("clip", [], 3, 1),
            ("random", [], 2, 1),
            # Comparison
            (">", [], 2, 1),
            ("<", [], 2, 1),
            (">=", [], 2, 1),
            ("<=", [], 2, 1),
            ("==", [], 2, 1),
            ("!=", [], 2, 1),
            # Logic
            ("&&", [], 2, 1),
            ("||", [], 2, 1),
            ("!", [], 1, 1),
            # Flow control
            ("bang", ["b"], 1, 1),
            ("trigger", ["t"], 1, -1),  # variable outlets
            ("spigot", [], 2, 1),
            ("moses", [], 2, 2),
            ("until", [], 2, 2),
            ("swap", [], 2, 2),
            ("change", [], 1, 1),
            # Lists/messages
            ("pack", [], -1, 1),  # variable inlets
            ("unpack", [], 1, -1),  # variable outlets
            ("route", [], 1, -1),  # variable outlets
            ("select", ["sel"], 1, -1),  # variable outlets
            ("list", [], 2, 1),
            ("append", [], 2, 1),
            ("prepend", [], 2, 1),
            # Time
            ("delay", ["del"], 2, 1),
            ("metro", [], 2, 1),
            ("timer", [], 2, 1),
            ("pipe", [], -1, -1),
            ("line", [], 3, 1),
            # MIDI
            ("notein", [], 1, 3),
            ("noteout", [], 3, 0),
            ("ctlin", [], 1, 3),
            ("ctlout", [], 3, 0),
            ("bendin", [], 1, 2),
            ("bendout", [], 2, 0),
            ("pgmin", [], 1, 2),
            ("pgmout", [], 2, 0),
            ("touchin", [], 1, 2),
            ("touchout", [], 2, 0),
            ("polytouchin", [], 1, 3),
            ("polytouchout", [], 3, 0),
            ("midiin", [], 1, 2),
            ("midiout", [], 1, 0),
            ("makenote", [], 3, 2),
            ("stripnote", [], 2, 2),
            # Arrays
            ("tabread", [], 2, 1),
            ("tabwrite", [], 2, 0),
            ("soundfiler", [], 1, 2),
            # GUI atoms
            ("loadbang", [], 0, 1),
            ("print", [], 1, 0),
            ("makefilename", [], 1, 1),
            ("openpanel", [], 1, 1),
            ("savepanel", [], 1, 1),
            # Misc
            ("expr", [], -1, -1),
        ]

        for item in control_objects:
            key = item[0]
            aliases = item[1]
            inlets = item[2]
            outlets = item[3]

            inlet_specs = []
            if inlets > 0:
                for i in range(inlets):
                    inlet_specs.append(IoletSpec(domain="control"))
            elif inlets == -1:
                inlet_specs.append(IoletSpec(domain="control"))

            outlet_specs = []
            if outlets > 0:
                for i in range(outlets):
                    outlet_specs.append(IoletSpec(domain="control"))
            elif outlets == -1:
                outlet_specs.append(IoletSpec(domain="control"))

            spec = ObjectSpec(
                key=key,
                library="pd-vanilla",
                kind="control",
                domain=Domain.CONTROL,
                inlets=inlet_specs,
                outlets=outlet_specs,
                aliases=aliases,
            )
            self.register(spec)

    def _add_vanilla_dsp_objects(self):
        """Add vanilla DSP objects."""
        dsp_objects = [
            # Oscillators
            ("osc~", 1, 1, "freq"),
            ("phasor~", 1, 1, "freq"),
            ("cos~", 1, 1, None),
            ("noise~", 0, 1, None),
            # Math
            ("+~", 2, 1, None),
            ("-~", 2, 1, None),
            ("*~", 2, 1, None),
            ("/~", 2, 1, None),
            ("max~", 2, 1, None),
            ("min~", 2, 1, None),
            ("clip~", 3, 1, None),
            ("wrap~", 1, 1, None),
            ("abs~", 1, 1, None),
            ("sqrt~", 1, 1, None),
            ("rsqrt~", 1, 1, None),
            ("pow~", 2, 1, None),
            ("log~", 2, 1, None),
            ("exp~", 1, 1, None),
            # Filters
            ("lop~", 2, 1, None),
            ("hip~", 2, 1, None),
            ("bp~", 3, 1, None),
            ("vcf~", 3, 2, None),
            ("biquad~", 6, 1, None),
            ("rpole~", 2, 1, None),
            ("rzero~", 2, 1, None),
            ("cpole~", 4, 2, None),
            ("czero~", 4, 2, None),
            # Delay
            ("delwrite~", 1, 0, None),
            ("delread~", 1, 1, None),
            ("delread4~", 1, 1, None),
            ("vd~", 1, 1, None),
            # Table operations
            ("tabread~", 1, 1, None),
            ("tabread4~", 1, 1, None),
            ("tabosc4~", 1, 1, None),
            ("tabwrite~", 2, 0, None),
            ("tabplay~", 1, 2, None),
            ("tabsend~", 1, 0, None),
            ("tabreceive~", 0, 1, None),
            # Conversion
            ("sig~", 1, 1, None),
            ("line~", 1, 1, None),
            ("vline~", 1, 1, None),
            ("snapshot~", 2, 1, None),
            ("samplerate~", 0, 1, None),
            ("block~", 0, 0, None),
            ("switch~", 1, 0, None),
            # Analysis
            ("env~", 1, 1, None),
            ("threshold~", 5, 2, None),
            ("bonk~", 1, 2, None),
            ("fiddle~", 1, 4, None),
            ("sigmund~", 1, -1, None),
            # I/O
            ("adc~", 0, -1, None),
            ("dac~", -1, 0, None),
            ("readsf~", 1, -1, None),
            ("writesf~", -1, 0, None),
        ]

        for item in dsp_objects:
            key = item[0]
            inlets = item[1]
            outlets = item[2]

            inlet_specs = []
            if inlets > 0:
                for i in range(inlets):
                    domain = "signal_or_control" if i == 0 else "signal"
                    inlet_specs.append(IoletSpec(domain=domain))
            elif inlets == -1:
                inlet_specs.append(IoletSpec(domain="signal"))

            outlet_specs = []
            if outlets > 0:
                for i in range(outlets):
                    outlet_specs.append(IoletSpec(domain="signal"))
            elif outlets == -1:
                outlet_specs.append(IoletSpec(domain="signal"))

            spec = ObjectSpec(
                key=key,
                library="pd-vanilla",
                kind="dsp",
                domain=Domain.SIGNAL,
                inlets=inlet_specs,
                outlets=outlet_specs,
            )
            self.register(spec)

    def _add_send_receive_objects(self):
        """Add send/receive family objects."""
        # Control send/receive
        self.register(ObjectSpec(
            key="send",
            library="pd-vanilla",
            kind="control",
            domain=Domain.CONTROL,
            inlets=[IoletSpec(domain="control", name="in")],
            outlets=[],
            args=[ArgSpec(name="symbol", type="symbol", required=True)],
            aliases=["s"],
            symbol_semantics=SymbolSemantics(kind=SymbolKind.SEND_RECEIVE, role="writer"),
        ))

        self.register(ObjectSpec(
            key="receive",
            library="pd-vanilla",
            kind="control",
            domain=Domain.CONTROL,
            inlets=[],
            outlets=[IoletSpec(domain="control", name="out")],
            args=[ArgSpec(name="symbol", type="symbol", required=True)],
            aliases=["r"],
            symbol_semantics=SymbolSemantics(kind=SymbolKind.SEND_RECEIVE, role="reader"),
        ))

        # Signal send/receive
        self.register(ObjectSpec(
            key="send~",
            library="pd-vanilla",
            kind="dsp",
            domain=Domain.SIGNAL,
            inlets=[IoletSpec(domain="signal", name="in")],
            outlets=[],
            args=[ArgSpec(name="symbol", type="symbol", required=True)],
            aliases=["s~"],
            symbol_semantics=SymbolSemantics(kind=SymbolKind.SEND_RECEIVE, role="writer"),
        ))

        self.register(ObjectSpec(
            key="receive~",
            library="pd-vanilla",
            kind="dsp",
            domain=Domain.SIGNAL,
            inlets=[],
            outlets=[IoletSpec(domain="signal", name="out")],
            args=[ArgSpec(name="symbol", type="symbol", required=True)],
            aliases=["r~"],
            symbol_semantics=SymbolSemantics(kind=SymbolKind.SEND_RECEIVE, role="reader"),
        ))

        # Throw/catch
        self.register(ObjectSpec(
            key="throw~",
            library="pd-vanilla",
            kind="dsp",
            domain=Domain.SIGNAL,
            inlets=[IoletSpec(domain="signal", name="in")],
            outlets=[],
            args=[ArgSpec(name="symbol", type="symbol", required=True)],
            symbol_semantics=SymbolSemantics(kind=SymbolKind.THROW_CATCH, role="writer"),
        ))

        self.register(ObjectSpec(
            key="catch~",
            library="pd-vanilla",
            kind="dsp",
            domain=Domain.SIGNAL,
            inlets=[],
            outlets=[IoletSpec(domain="signal", name="out")],
            args=[ArgSpec(name="symbol", type="symbol", required=True)],
            symbol_semantics=SymbolSemantics(kind=SymbolKind.THROW_CATCH, role="reader"),
        ))

        # Value
        self.register(ObjectSpec(
            key="value",
            library="pd-vanilla",
            kind="control",
            domain=Domain.CONTROL,
            inlets=[IoletSpec(domain="control")],
            outlets=[IoletSpec(domain="control")],
            args=[ArgSpec(name="symbol", type="symbol", required=True)],
            aliases=["v"],
            symbol_semantics=SymbolSemantics(kind=SymbolKind.VALUE, role="reader"),
        ))

    def _add_interface_objects(self):
        """Add interface objects (inlet/outlet)."""
        self.register(ObjectSpec(
            key="inlet",
            library="pd-vanilla",
            kind="control",
            domain=Domain.CONTROL,
            inlets=[],
            outlets=[IoletSpec(domain="control")],
        ))

        self.register(ObjectSpec(
            key="outlet",
            library="pd-vanilla",
            kind="control",
            domain=Domain.CONTROL,
            inlets=[IoletSpec(domain="control")],
            outlets=[],
        ))

        self.register(ObjectSpec(
            key="inlet~",
            library="pd-vanilla",
            kind="dsp",
            domain=Domain.SIGNAL,
            inlets=[],
            outlets=[IoletSpec(domain="signal")],
        ))

        self.register(ObjectSpec(
            key="outlet~",
            library="pd-vanilla",
            kind="dsp",
            domain=Domain.SIGNAL,
            inlets=[IoletSpec(domain="signal")],
            outlets=[],
        ))

    def _add_override_rules(self):
        """Add dynamic outlet/inlet count rules."""
        self._overrides = [
            OverrideRule("route", "outlets = 1 + argc"),
            OverrideRule("select", "outlets = 1 + argc"),
            OverrideRule("unpack", "outlets = argc"),
            OverrideRule("pack", "inlets = argc"),
            OverrideRule("trigger", "outlets = argc"),
            OverrideRule("dac~", "inlets = max(argc, 2)"),
            OverrideRule("adc~", "outlets = max(argc, 2)"),
            OverrideRule("readsf~", "outlets = arg0 + 1"),  # channels + done bang
            OverrideRule("writesf~", "inlets = arg0"),  # channels
        ]

    def register(self, spec: ObjectSpec):
        """Register an object specification."""
        self._objects[spec.key] = spec
        for alias in spec.aliases:
            self._aliases[alias] = spec.key

    def get(self, key: str) -> Optional[ObjectSpec]:
        """Get an object specification by key or alias."""
        if key in self._objects:
            return self._objects[key]
        if key in self._aliases:
            return self._objects[self._aliases[key]]
        return None

    def is_known(self, key: str) -> bool:
        """Check if an object type is known."""
        return key in self._objects or key in self._aliases

    def get_domain(self, obj_type: str) -> Domain:
        """Get the domain for an object type."""
        spec = self.get(obj_type)
        if spec:
            return spec.domain
        # Fallback: use ~ suffix heuristic
        if obj_type.endswith('~'):
            return Domain.SIGNAL
        return Domain.CONTROL

    def get_io_count(self, obj_type: str, args: List[str]) -> tuple:
        """
        Get the inlet and outlet count for an object.
        Returns (inlet_count, outlet_count).
        """
        spec = self.get(obj_type)

        # Resolve alias to canonical key for override matching
        canonical_key = obj_type
        if obj_type in self._aliases:
            canonical_key = self._aliases[obj_type]

        # Check override rules (using canonical key)
        for rule in self._overrides:
            if rule.match_key == canonical_key:
                argc = len(args)
                # Parse first argument as integer if possible (for arg0 rules)
                arg0 = 1  # default
                if args and args[0].isdigit():
                    arg0 = int(args[0])

                inlet_count = len(spec.inlets) if spec else 1
                outlet_count = len(spec.outlets) if spec else 1

                if "outlets = 1 + argc" in rule.rule:
                    outlet_count = 1 + argc
                elif "outlets = argc" in rule.rule:
                    outlet_count = max(argc, 1)
                elif "outlets = arg0 + 1" in rule.rule:
                    outlet_count = arg0 + 1
                elif "inlets = argc" in rule.rule:
                    inlet_count = max(argc, 1)
                elif "inlets = arg0" in rule.rule:
                    inlet_count = max(arg0, 1)
                elif "outlets = max(argc" in rule.rule:
                    outlet_count = max(argc, 2)
                elif "inlets = max(argc" in rule.rule:
                    inlet_count = max(argc, 2)

                return (inlet_count, outlet_count)

        if spec:
            return (len(spec.inlets), len(spec.outlets))

        # Default fallback
        return (1, 1)

    def get_symbol_semantics(self, obj_type: str) -> Optional[SymbolSemantics]:
        """Get symbol semantics for an object type."""
        spec = self.get(obj_type)
        if spec:
            return spec.symbol_semantics
        return None

    def load_json(self, filepath: str):
        """Load additional objects from a JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        if 'sources' in data:
            self._sources.extend(data['sources'])

        for obj_data in data.get('objects', []):
            domain = Domain(obj_data.get('domain', 'control'))

            inlets = []
            for inlet in obj_data.get('inlets', []):
                inlets.append(IoletSpec(
                    domain=inlet.get('domain', 'control'),
                    name=inlet.get('name'),
                ))

            outlets = []
            for outlet in obj_data.get('outlets', []):
                outlets.append(IoletSpec(
                    domain=outlet.get('domain', 'control'),
                    name=outlet.get('name'),
                ))

            args = []
            for arg in obj_data.get('args', []):
                args.append(ArgSpec(
                    name=arg.get('name', ''),
                    type=arg.get('type', 'any'),
                    required=arg.get('required', False),
                    default=arg.get('default'),
                ))

            symbol_semantics = None
            if 'symbol_semantics' in obj_data:
                sem = obj_data['symbol_semantics']
                symbol_semantics = SymbolSemantics(
                    kind=SymbolKind(sem['kind']),
                    role=sem['role'],
                )

            spec = ObjectSpec(
                key=obj_data['key'],
                library=obj_data.get('library', 'unknown'),
                kind=obj_data.get('kind', 'control'),
                domain=domain,
                inlets=inlets,
                outlets=outlets,
                args=args,
                aliases=obj_data.get('aliases', []),
                symbol_semantics=symbol_semantics,
            )
            self.register(spec)

        for override in data.get('overrides', []):
            self._overrides.append(OverrideRule(
                match_key=override['match']['key'],
                rule=override['rule'],
            ))

    def to_dict(self) -> Dict[str, Any]:
        """Export registry to a dictionary."""
        return {
            "registry_version": "0.1",
            "unknown_object_policy": self.unknown_object_policy,
            "sources": self._sources,
            "objects": [spec.to_dict() for spec in self._objects.values()],
            "overrides": [o.to_dict() for o in self._overrides],
        }


# Global registry instance
_registry: Optional[ObjectRegistry] = None


def get_registry() -> ObjectRegistry:
    """Get the global object registry."""
    global _registry
    if _registry is None:
        _registry = ObjectRegistry()
    return _registry
