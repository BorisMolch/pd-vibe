"""
IR Core Schema - Data classes for the Pure Data IR representation.

This module defines the semantic intermediate representation for Pure Data patches,
following the IR Schema v0.1 specification.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import json
import hashlib


class NodeKind(Enum):
    """Types of nodes in a Pure Data patch."""
    OBJECT = "object"
    MESSAGE = "message"
    ATOM = "atom"
    GUI = "gui"
    COMMENT = "comment"
    ABSTRACTION_INSTANCE = "abstraction_instance"
    SUBPATCH = "subpatch"


class EdgeKind(Enum):
    """Types of edges (connections) in a patch."""
    WIRE = "wire"
    SYMBOL = "symbol"


class Domain(Enum):
    """Signal domain classification."""
    SIGNAL = "signal"
    CONTROL = "control"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SymbolKind(Enum):
    """Types of symbolic communication."""
    SEND_RECEIVE = "send_receive"
    THROW_CATCH = "throw_catch"
    VALUE = "value"
    ARRAY = "array"
    TABLE = "table"


class SymbolNamespace(Enum):
    """Namespace for symbol resolution."""
    GLOBAL = "global"
    INSTANCE = "instance"
    HIERARCHICAL = "hierarchical"


@dataclass
class IRIolet:
    """Inlet or outlet specification."""
    index: int
    domain: Domain = Domain.UNKNOWN
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "domain": self.domain.value,
            "name": self.name,
        }


@dataclass
class IRNodeIO:
    """Input/output specification for a node."""
    inlets: List[IRIolet] = field(default_factory=list)
    outlets: List[IRIolet] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inlets": [i.to_dict() for i in self.inlets],
            "outlets": [o.to_dict() for o in self.outlets],
        }


@dataclass
class IRLayout:
    """Layout/position information for a node."""
    x: int
    y: int
    width: Optional[int] = None
    height: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"x": self.x, "y": self.y}
        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height
        return d


@dataclass
class IRNodeMeta:
    """Metadata for a node."""
    source_line: Optional[int] = None
    original_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        if self.source_line is not None:
            d["source_line"] = self.source_line
        if self.original_id is not None:
            d["original_id"] = self.original_id
        return d


@dataclass
class IRAbstractionRef:
    """Reference to an external abstraction."""
    name: str
    path: Optional[str] = None
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "resolved": self.resolved,
        }


@dataclass
class IRExternalRef:
    """Reference to an external library object."""
    name: str
    instances: List[str] = field(default_factory=list)
    known: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "instances": self.instances,
            "known": self.known,
        }


@dataclass
class IRNode:
    """A node in the IR graph (object, message, comment, etc.)."""
    id: str
    canvas: str
    kind: NodeKind
    type: str
    args: List[str] = field(default_factory=list)
    domain: Domain = Domain.UNKNOWN
    io: Optional[IRNodeIO] = None
    layout: Optional[IRLayout] = None
    meta: Optional[IRNodeMeta] = None
    ref: Optional[IRAbstractionRef] = None
    text: Optional[str] = None  # For comments

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "canvas": self.canvas,
            "kind": self.kind.value,
            "type": self.type,
            "args": self.args,
            "domain": self.domain.value,
        }
        if self.io:
            d["io"] = self.io.to_dict()
        if self.layout:
            d["layout"] = self.layout.to_dict()
        if self.meta:
            d["meta"] = self.meta.to_dict()
        if self.ref:
            d["ref"] = self.ref.to_dict()
        if self.text:
            d["text"] = self.text
        return d


@dataclass
class IREdgeEndpoint:
    """An endpoint of an edge (connection)."""
    node: str
    outlet: Optional[int] = None
    inlet: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"node": self.node}
        if self.outlet is not None:
            d["outlet"] = self.outlet
        if self.inlet is not None:
            d["inlet"] = self.inlet
        return d


@dataclass
class IREdge:
    """An edge (connection) in the IR graph."""
    id: str
    kind: EdgeKind
    domain: Domain
    from_endpoint: IREdgeEndpoint
    to_endpoint: IREdgeEndpoint
    symbol: Optional[str] = None
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "kind": self.kind.value,
            "domain": self.domain.value,
            "from": self.from_endpoint.to_dict(),
            "to": self.to_endpoint.to_dict(),
        }
        if self.symbol:
            d["symbol"] = self.symbol
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d


@dataclass
class IRSymbolEndpoint:
    """An endpoint participating in symbol-mediated communication."""
    node: str
    port: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"node": self.node}
        if self.port is not None:
            d["port"] = self.port
        return d


@dataclass
class IRSymbol:
    """A symbol (send/receive, throw/catch, etc.) in the patch."""
    id: str
    kind: SymbolKind
    raw: str
    resolved: str
    namespace: SymbolNamespace
    instance_local: bool = False
    writers: List[IRSymbolEndpoint] = field(default_factory=list)
    readers: List[IRSymbolEndpoint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "raw": self.raw,
            "resolved": self.resolved,
            "namespace": self.namespace.value,
            "instance_local": self.instance_local,
            "writers": [w.to_dict() for w in self.writers],
            "readers": [r.to_dict() for r in self.readers],
        }


@dataclass
class IRCanvas:
    """A canvas (root or subpatch) in the IR."""
    id: str
    kind: str  # "root" or "subpatch"
    name: str
    parent_canvas: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "parent_canvas": self.parent_canvas,
        }


@dataclass
class IRSCC:
    """A strongly connected component (feedback cycle)."""
    id: str
    nodes: List[str]
    reason: str = "feedback_cycle"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nodes": self.nodes,
            "reason": self.reason,
        }


@dataclass
class IRInterfacePort:
    """An interface port (inlet or outlet of the patch)."""
    node: str
    index: int
    domain: Domain

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "index": self.index,
            "domain": self.domain.value,
        }


@dataclass
class IRExposedSymbol:
    """A symbol exposed as part of the interface."""
    kind: SymbolKind
    name: str
    role: str  # "reader" or "writer"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "role": self.role,
        }


@dataclass
class IRInterface:
    """Interface specification for a patch."""
    inlets: List[IRInterfacePort] = field(default_factory=list)
    outlets: List[IRInterfacePort] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inlets": [i.to_dict() for i in self.inlets],
            "outlets": [o.to_dict() for o in self.outlets],
        }


@dataclass
class IRSymbolsAsInterface:
    """Symbols exposed as interface."""
    enabled: bool = False
    exposed: List[IRExposedSymbol] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "exposed": [e.to_dict() for e in self.exposed],
        }


@dataclass
class IRAnalysis:
    """Analysis results for the patch."""
    sccs: List[IRSCC] = field(default_factory=list)
    interfaces: Optional[IRInterface] = None
    symbols_as_interface: Optional[IRSymbolsAsInterface] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "sccs": [s.to_dict() for s in self.sccs],
        }
        if self.interfaces:
            d["interfaces"] = self.interfaces.to_dict()
        if self.symbols_as_interface:
            d["symbols_as_interface"] = self.symbols_as_interface.to_dict()
        return d


@dataclass
class IRComment:
    """A text comment in the patch."""
    node: str
    canvas: str
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "canvas": self.canvas,
            "text": self.text,
        }


@dataclass
class IRDiagnostic:
    """A diagnostic message (error or warning)."""
    code: str
    message: str
    node: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "code": self.code,
            "message": self.message,
        }
        if self.node:
            d["node"] = self.node
        return d


@dataclass
class IRRefs:
    """References to abstractions and externals."""
    abstractions: List[Dict[str, Any]] = field(default_factory=list)
    externals: List[IRExternalRef] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "abstractions": self.abstractions,
            "externals": [e.to_dict() for e in self.externals],
        }


@dataclass
class IRText:
    """Text content (comments) in the patch."""
    comments: List[IRComment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comments": [c.to_dict() for c in self.comments],
        }


@dataclass
class IRDiagnostics:
    """Diagnostics (errors and warnings)."""
    errors: List[IRDiagnostic] = field(default_factory=list)
    warnings: List[IRDiagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


@dataclass
class IREnrichment:
    """Enrichment layer for LLM-generated content."""
    summary: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    inlet_semantics: Dict[str, str] = field(default_factory=dict)
    outlet_semantics: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "roles": self.roles,
            "inlet_semantics": self.inlet_semantics,
            "outlet_semantics": self.outlet_semantics,
            "notes": self.notes,
        }


@dataclass
class IRPatchInfo:
    """Patch metadata."""
    name: str
    path: str
    sha256: Optional[str] = None
    graph_hash: Optional[str] = None
    root_canvas: str = "c0"
    dynamic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "graph_hash": self.graph_hash,
            "root_canvas": self.root_canvas,
            "dynamic": self.dynamic,
        }


@dataclass
class IRPatch:
    """Complete IR representation of a Pure Data patch."""
    ir_version: str = "0.1"
    patch: Optional[IRPatchInfo] = None
    canvases: List[IRCanvas] = field(default_factory=list)
    nodes: List[IRNode] = field(default_factory=list)
    edges: List[IREdge] = field(default_factory=list)
    symbols: List[IRSymbol] = field(default_factory=list)
    refs: Optional[IRRefs] = None
    analysis: Optional[IRAnalysis] = None
    text: Optional[IRText] = None
    diagnostics: Optional[IRDiagnostics] = None
    enrichment: Optional[IREnrichment] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "ir_version": self.ir_version,
        }
        if self.patch:
            d["patch"] = self.patch.to_dict()
        d["canvases"] = [c.to_dict() for c in self.canvases]
        d["nodes"] = [n.to_dict() for n in self.nodes]
        d["edges"] = [e.to_dict() for e in self.edges]
        d["symbols"] = [s.to_dict() for s in self.symbols]
        if self.refs:
            d["refs"] = self.refs.to_dict()
        if self.analysis:
            d["analysis"] = self.analysis.to_dict()
        if self.text:
            d["text"] = self.text.to_dict()
        if self.diagnostics:
            d["diagnostics"] = self.diagnostics.to_dict()
        if self.enrichment:
            d["enrichment"] = self.enrichment.to_dict()
        return d

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def compute_graph_hash(self) -> str:
        """Compute a deterministic hash of the graph structure."""
        # Canonical form: sorted nodes and edges
        nodes_canonical = sorted(
            [(n.id, n.type, tuple(n.args)) for n in self.nodes],
            key=lambda x: x[0]
        )
        edges_canonical = sorted(
            [(e.from_endpoint.node, e.from_endpoint.outlet or 0,
              e.to_endpoint.node, e.to_endpoint.inlet or 0)
             for e in self.edges if e.kind == EdgeKind.WIRE],
            key=lambda x: (x[0], x[1], x[2], x[3])
        )
        content = json.dumps({"nodes": nodes_canonical, "edges": edges_canonical},
                            sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def get_node(self, node_id: str) -> Optional[IRNode]:
        """Get a node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_canvas(self, canvas_id: str) -> Optional[IRCanvas]:
        """Get a canvas by ID."""
        for canvas in self.canvases:
            if canvas.id == canvas_id:
                return canvas
        return None

    def get_nodes_by_canvas(self, canvas_id: str) -> List[IRNode]:
        """Get all nodes in a canvas."""
        return [n for n in self.nodes if n.canvas == canvas_id]

    def get_edges_from_node(self, node_id: str) -> List[IREdge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.from_endpoint.node == node_id]

    def get_edges_to_node(self, node_id: str) -> List[IREdge]:
        """Get all edges terminating at a node."""
        return [e for e in self.edges if e.to_endpoint.node == node_id]
