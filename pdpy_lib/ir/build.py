"""
IR Build Pipeline for Pure Data.

This module orchestrates the conversion from pdpy's Python objects
(PdPy, Canvas, Obj, Edge, etc.) to the semantic IR representation.
"""

import hashlib
import os
from typing import Dict, List, Optional, Any, Tuple, Set
from collections import defaultdict

from .core import (
    IRPatch,
    IRPatchInfo,
    IRCanvas,
    IRNode,
    IREdge,
    IREdgeEndpoint,
    IRSymbol,
    IRNodeIO,
    IRIolet,
    IRLayout,
    IRNodeMeta,
    IRAbstractionRef,
    IRExternalRef,
    IRRefs,
    IRText,
    IRComment,
    IRDiagnostics,
    IRDiagnostic,
    IREnrichment,
    NodeKind,
    EdgeKind,
    Domain,
)
from .ids import NodeIDGenerator, generate_canvas_path
from .symbols import SymbolExtractor
from .registry import ObjectRegistry, get_registry
from .analysis import GraphAnalyzer


class IRBuilder:
    """
    Builds IR from pdpy objects.

    This class converts pdpy's syntactic representation (PdPy, Canvas, Obj, etc.)
    into the semantic IR representation (IRPatch, IRNode, IREdge, etc.).
    """

    def __init__(self, registry: Optional[ObjectRegistry] = None):
        """
        Initialize the IR builder.

        Args:
            registry: Object registry for type information. Uses global registry if None.
        """
        self.registry = registry or get_registry()
        self._id_generator = NodeIDGenerator()
        self._symbol_extractor = SymbolExtractor()

        # Build state
        self._canvas_counter = 0
        self._edge_counter = 0
        self._node_id_map: Dict[Tuple[str, int], str] = {}  # (canvas_id, orig_id) -> ir_id
        self._subpatch_map: Dict[Tuple[str, int], str] = {}  # (canvas_id, orig_id) -> subpatch_canvas_path
        self._diagnostics = IRDiagnostics()
        self._abstractions: Dict[str, Dict[str, Any]] = {}  # name -> info
        self._externals: Dict[str, IRExternalRef] = {}

    def _reset(self):
        """Reset build state."""
        self._canvas_counter = 0
        self._edge_counter = 0
        self._node_id_map.clear()
        self._subpatch_map.clear()
        self._id_generator.reset()
        self._symbol_extractor.reset()
        self._diagnostics = IRDiagnostics()
        self._abstractions.clear()
        self._externals.clear()

    def _get_canvas_id(self) -> str:
        """Generate a unique canvas ID."""
        cid = f"c{self._canvas_counter}"
        self._canvas_counter += 1
        return cid

    def _get_edge_id(self) -> str:
        """Generate a unique edge ID."""
        self._edge_counter += 1
        return f"e{self._edge_counter}"

    def _infer_domain(self, obj_type: str, args: List[str]) -> Domain:
        """Infer the domain of an object."""
        # Check registry first
        domain = self.registry.get_domain(obj_type)
        if domain != Domain.CONTROL:
            return domain

        # Fallback: ~ suffix heuristic
        if obj_type.endswith('~'):
            return Domain.SIGNAL

        return Domain.CONTROL

    def _classify_node_kind(self, pdpy_obj: Any) -> NodeKind:
        """Classify the kind of a pdpy object."""
        class_name = pdpy_obj.__class__.__name__

        if class_name == 'Comment':
            return NodeKind.COMMENT
        elif class_name == 'Msg':
            return NodeKind.MESSAGE
        elif class_name in ('Gui', 'Toggle', 'Bng', 'Slider', 'Radio', 'Nbx', 'Vu', 'Cnv'):
            return NodeKind.GUI
        elif class_name == 'Canvas':
            return NodeKind.SUBPATCH
        elif hasattr(pdpy_obj, 'className'):
            obj_type = pdpy_obj.className or ''
            # Check if it's an abstraction instance
            if self._is_abstraction(obj_type):
                return NodeKind.ABSTRACTION_INSTANCE
            # Check for atom types
            if obj_type in ('floatatom', 'symbolatom', 'listbox'):
                return NodeKind.ATOM
            return NodeKind.OBJECT

        return NodeKind.OBJECT

    def _is_abstraction(self, obj_type: str) -> bool:
        """Check if an object type is likely an abstraction."""
        # Not in registry and not a vanilla pattern
        if self.registry.is_known(obj_type):
            return False

        # Contains path separator
        if '/' in obj_type or '\\' in obj_type:
            return True

        # Unknown object - could be abstraction or external
        return False

    def _get_object_type(self, pdpy_obj: Any) -> str:
        """Get the object type string from a pdpy object."""
        if hasattr(pdpy_obj, 'className') and pdpy_obj.className:
            class_name = pdpy_obj.className

            # Handle pdpy's special parsing where className becomes 'list' or 'float'
            # and the actual object type is in args[0] as "type arg1 arg2..."
            if class_name in ('list', 'float') and hasattr(pdpy_obj, 'args') and pdpy_obj.args:
                first_arg = str(pdpy_obj.args[0])
                # The first arg may contain "objtype arg1 arg2" - extract just the type
                parts = first_arg.split()
                if parts:
                    return parts[0]

            return class_name
        return pdpy_obj.__class__.__name__.lower()

    def _get_object_args(self, pdpy_obj: Any) -> List[str]:
        """Get arguments from a pdpy object.

        pdpy stores args with spaces joined into single strings (e.g., ['b b'] instead of ['b', 'b']).
        This method splits them back into individual arguments for proper IO counting.
        """
        if hasattr(pdpy_obj, 'args') and pdpy_obj.args:
            class_name = getattr(pdpy_obj, 'className', '')

            # Handle pdpy's special parsing where className becomes 'list' or 'float'
            # and args[0] contains "type arg1 arg2..."
            if class_name in ('list', 'float') and pdpy_obj.args:
                first_arg = str(pdpy_obj.args[0])
                parts = first_arg.split()
                if len(parts) > 1:
                    # Return the arguments after the object type
                    return parts[1:] + [str(a) for a in pdpy_obj.args[1:]]
                elif len(pdpy_obj.args) > 1:
                    # Args after the first one
                    return [str(a) for a in pdpy_obj.args[1:]]
                return []

            # Split space-joined args back into individual arguments
            # pdpy stores ['b b'] but we need ['b', 'b'] for proper IO counting
            result = []
            for arg in pdpy_obj.args:
                arg_str = str(arg)
                # Split by spaces, but preserve the arg if it doesn't contain spaces
                parts = arg_str.split()
                result.extend(parts)
            return result
        return []

    def _get_layout(self, pdpy_obj: Any) -> Optional[IRLayout]:
        """Extract layout information from a pdpy object."""
        if hasattr(pdpy_obj, 'position') and pdpy_obj.position:
            pos = pdpy_obj.position
            x = getattr(pos, 'x', 0) or 0
            y = getattr(pos, 'y', 0) or 0
            return IRLayout(x=int(x), y=int(y))
        return None

    def _get_comment_text(self, pdpy_obj: Any) -> Optional[str]:
        """Get text from a comment object."""
        if hasattr(pdpy_obj, 'text'):
            text = pdpy_obj.text
            if isinstance(text, list):
                return ' '.join(str(t) for t in text)
            return str(text) if text else None
        return None

    def _get_message_text(self, pdpy_obj: Any) -> List[str]:
        """Get text from a message object."""
        args = []
        if hasattr(pdpy_obj, 'targets') and pdpy_obj.targets:
            for target in pdpy_obj.targets:
                if hasattr(target, 'address') and target.address:
                    args.append(str(target.address))
                if hasattr(target, 'messages') and target.messages:
                    for msg in target.messages:
                        if msg:
                            args.append(str(msg))
        return args

    def _build_node_io(self, obj_type: str, args: List[str]) -> IRNodeIO:
        """Build IO specification for a node."""
        inlet_count, outlet_count = self.registry.get_io_count(obj_type, args)
        domain = self._infer_domain(obj_type, args)

        inlets = []
        for i in range(inlet_count):
            # First inlet often accepts both signal and control
            if domain == Domain.SIGNAL and i == 0:
                inlets.append(IRIolet(index=i, domain=Domain.MIXED))
            elif domain == Domain.SIGNAL:
                inlets.append(IRIolet(index=i, domain=Domain.SIGNAL))
            else:
                inlets.append(IRIolet(index=i, domain=Domain.CONTROL))

        outlets = []
        for i in range(outlet_count):
            if domain == Domain.SIGNAL:
                outlets.append(IRIolet(index=i, domain=Domain.SIGNAL))
            else:
                outlets.append(IRIolet(index=i, domain=Domain.CONTROL))

        return IRNodeIO(inlets=inlets, outlets=outlets)

    def _process_canvas(self, canvas: Any, canvas_id: str, parent_id: Optional[str],
                       canvas_path: str) -> Tuple[List[IRCanvas], List[IRNode], List[IREdge]]:
        """
        Process a canvas and its contents recursively.

        Returns:
            Tuple of (list of IRCanvases, list of IRNodes, list of IREdges)
            The first canvas in the list is the current canvas, followed by any sub-canvases.
        """
        name = getattr(canvas, 'name', None) or canvas_id
        kind = "root" if parent_id is None else "subpatch"

        ir_canvas = IRCanvas(
            id=canvas_id,
            kind=kind,
            name=str(name),
            parent_canvas=parent_id,
        )

        canvases = [ir_canvas]  # Start with current canvas
        nodes = []
        edges = []

        # Collect node data for ID generation
        node_data = []
        pdpy_nodes = []

        # Process nodes
        if hasattr(canvas, 'nodes') and canvas.nodes:
            for i, obj in enumerate(canvas.nodes):
                obj_type = self._get_object_type(obj)
                args = self._get_object_args(obj)
                kind = self._classify_node_kind(obj)
                domain = self._infer_domain(obj_type, args)

                # Handle subpatches recursively
                if obj.__class__.__name__ == 'Canvas':
                    sub_canvas_id = self._get_canvas_id()
                    sub_path = generate_canvas_path(sub_canvas_id, canvas_path)
                    sub_canvases, sub_nodes, sub_edges = self._process_canvas(
                        obj, sub_canvas_id, canvas_id, sub_path
                    )
                    # Add all sub-canvases to our canvas list
                    canvases.extend(sub_canvases)
                    nodes.extend(sub_nodes)
                    edges.extend(sub_edges)
                    # Track subpatch mapping for cross-boundary edges
                    original_id = getattr(obj, 'id', i)
                    self._subpatch_map[(canvas_id, original_id)] = sub_path

                original_id = getattr(obj, 'id', i)
                node_data.append({
                    'original_id': original_id,
                    'type': obj_type,
                    'args': args,
                    'kind': kind.value,
                    'domain': domain.value,
                })
                pdpy_nodes.append(obj)

        # Collect edge data for ID generation
        edge_tuples = []
        if hasattr(canvas, 'edges') and canvas.edges:
            for edge in canvas.edges:
                src_id = getattr(edge.source, 'id', 0) if edge.source else 0
                src_port = getattr(edge.source, 'port', 0) if edge.source else 0
                dst_id = getattr(edge.sink, 'id', 0) if edge.sink else 0
                dst_port = getattr(edge.sink, 'port', 0) if edge.sink else 0
                edge_tuples.append((src_id, src_port, dst_id, dst_port))

        # Generate deterministic IDs
        id_map = self._id_generator.generate_ids(node_data, edge_tuples, canvas_path)

        # Create IR nodes
        for i, obj in enumerate(pdpy_nodes):
            obj_type = self._get_object_type(obj)
            args = self._get_object_args(obj)
            kind = self._classify_node_kind(obj)
            domain = self._infer_domain(obj_type, args)

            original_id = node_data[i]['original_id']
            ir_id = id_map.get(original_id, f"{canvas_path}::n{i}")

            # Store mapping
            self._node_id_map[(canvas_id, original_id)] = ir_id

            # Handle special cases
            text = None
            if kind == NodeKind.COMMENT:
                text = self._get_comment_text(obj)
                obj_type = "comment"
                args = []
            elif kind == NodeKind.MESSAGE:
                args = self._get_message_text(obj)
                obj_type = "message"

            # Build IO
            io = self._build_node_io(obj_type, args)

            # Check for abstraction/external
            ref = None
            if kind == NodeKind.ABSTRACTION_INSTANCE:
                abs_name = obj_type
                ref = IRAbstractionRef(
                    name=abs_name,
                    path=None,  # Will be resolved later
                    resolved=False,
                )
                if abs_name not in self._abstractions:
                    self._abstractions[abs_name] = {
                        'name': abs_name,
                        'path': None,
                        'instances': [],
                    }
                self._abstractions[abs_name]['instances'].append(ir_id)

            # Check for unknown objects
            if kind == NodeKind.OBJECT and not self.registry.is_known(obj_type):
                if '/' in obj_type:
                    # Likely an external
                    if obj_type not in self._externals:
                        self._externals[obj_type] = IRExternalRef(
                            name=obj_type,
                            instances=[],
                            known=False,
                        )
                    self._externals[obj_type].instances.append(ir_id)

                    self._diagnostics.warnings.append(IRDiagnostic(
                        code="UNKNOWN_OBJECT",
                        message=f"{obj_type} not in registry",
                        node=ir_id,
                    ))

            # Create IR node
            ir_node = IRNode(
                id=ir_id,
                canvas=canvas_id,
                kind=kind,
                type=obj_type,
                args=args,
                domain=domain,
                io=io,
                layout=self._get_layout(obj),
                meta=IRNodeMeta(original_id=original_id),
                ref=ref,
                text=text,
            )
            nodes.append(ir_node)

            # Extract symbols
            self._symbol_extractor.extract_from_node(ir_id, obj_type, args)

        # Build a map of original_id -> (type, args) for IO count validation
        node_info_map: Dict[int, Tuple[str, List[str]]] = {}
        for i, data in enumerate(node_data):
            node_info_map[data['original_id']] = (data['type'], data['args'])

        # Create IR edges
        for edge_tuple in edge_tuples:
            src_id, src_port, dst_id, dst_port = edge_tuple

            src_ir_id = self._node_id_map.get((canvas_id, src_id))
            dst_ir_id = self._node_id_map.get((canvas_id, dst_id))

            if not src_ir_id or not dst_ir_id:
                continue

            # Validate outlet/inlet indices before creating edge
            is_src_subpatch = (canvas_id, src_id) in self._subpatch_map
            is_dst_subpatch = (canvas_id, dst_id) in self._subpatch_map

            # Check source outlet validity (skip for subpatches and unknown objects)
            if not is_src_subpatch and src_id in node_info_map:
                src_type, src_args = node_info_map[src_id]
                # Only validate if object is known in registry
                if self.registry.is_known(src_type):
                    _, outlet_count = self.registry.get_io_count(src_type, src_args)
                    if src_port >= outlet_count:
                        self._diagnostics.warnings.append(IRDiagnostic(
                            code="INVALID_CONNECTION",
                            message=f"Connection from {src_type} outlet {src_port} invalid (only has {outlet_count} outlet(s))",
                            node=src_ir_id,
                        ))
                        continue  # Skip this invalid edge

            # Check destination inlet validity (skip for subpatches and unknown objects)
            if not is_dst_subpatch and dst_id in node_info_map:
                dst_type, dst_args = node_info_map[dst_id]
                # Only validate if object is known in registry
                if self.registry.is_known(dst_type):
                    inlet_count, _ = self.registry.get_io_count(dst_type, dst_args)
                    if dst_port >= inlet_count:
                        self._diagnostics.warnings.append(IRDiagnostic(
                            code="INVALID_CONNECTION",
                            message=f"Connection to {dst_type} inlet {dst_port} invalid (only has {inlet_count} inlet(s))",
                            node=dst_ir_id,
                        ))
                        continue  # Skip this invalid edge

            # Handle cross-boundary edges: if source is a subpatch, connect from its outlet
            src_subpatch_path = self._subpatch_map.get((canvas_id, src_id))
            if src_subpatch_path:
                src_ir_id = f"{src_subpatch_path}::outlet#{src_port}"
                src_port = 0  # Outlet nodes have a single outlet (port 0)

            # If destination is a subpatch, connect to its inlet
            dst_subpatch_path = self._subpatch_map.get((canvas_id, dst_id))
            if dst_subpatch_path:
                dst_ir_id = f"{dst_subpatch_path}::inlet#{dst_port}"
                dst_port = 0  # Inlet nodes have a single inlet (port 0)

            # Determine edge domain from source node
            src_node = next((n for n in nodes if n.id == src_ir_id), None)
            edge_domain = Domain.CONTROL
            if src_node:
                edge_domain = src_node.domain

            ir_edge = IREdge(
                id=self._get_edge_id(),
                kind=EdgeKind.WIRE,
                domain=edge_domain,
                from_endpoint=IREdgeEndpoint(node=src_ir_id, outlet=src_port),
                to_endpoint=IREdgeEndpoint(node=dst_ir_id, inlet=dst_port),
            )
            edges.append(ir_edge)

        return canvases, nodes, edges

    def build(self, pdpy_obj: Any, patch_path: Optional[str] = None,
              file_content: Optional[bytes] = None) -> IRPatch:
        """
        Build IR from a pdpy object.

        Args:
            pdpy_obj: A PdPy instance or similar object with a root canvas
            patch_path: Path to the .pd file (for metadata)
            file_content: Raw file content (for SHA256 hash)

        Returns:
            IRPatch instance
        """
        self._reset()

        # Get patch name and path
        name = getattr(pdpy_obj, 'patchname', None) or 'untitled'
        if patch_path is None:
            patch_path = f"{name}.pd"

        # Compute file hash
        sha256 = None
        if file_content:
            sha256 = hashlib.sha256(file_content).hexdigest()

        # Get root canvas
        root = getattr(pdpy_obj, 'root', pdpy_obj)

        # Process root canvas (recursively processes all sub-canvases)
        root_canvas_id = self._get_canvas_id()
        canvases, nodes, edges = self._process_canvas(
            root, root_canvas_id, None, root_canvas_id
        )

        # Get symbols
        symbols = self._symbol_extractor.get_symbols()

        # Generate symbol edges
        symbol_edges = self._symbol_extractor.generate_symbol_edges()
        edges.extend(symbol_edges)

        # Build refs
        refs = IRRefs(
            abstractions=list(self._abstractions.values()),
            externals=list(self._externals.values()),
        )

        # Build text section
        comments = [
            IRComment(node=n.id, canvas=n.canvas, text=n.text)
            for n in nodes
            if n.kind == NodeKind.COMMENT and n.text
        ]
        text = IRText(comments=comments)

        # Create patch
        ir_patch = IRPatch(
            patch=IRPatchInfo(
                name=name,
                path=patch_path,
                sha256=sha256,
                root_canvas=root_canvas_id,
            ),
            canvases=canvases,
            nodes=nodes,
            edges=edges,
            symbols=symbols,
            refs=refs,
            text=text,
            diagnostics=self._diagnostics if (self._diagnostics.errors or
                                               self._diagnostics.warnings) else None,
            enrichment=IREnrichment(),  # Empty enrichment slot
        )

        # Compute graph hash
        ir_patch.patch.graph_hash = ir_patch.compute_graph_hash()

        # Run analysis
        analyzer = GraphAnalyzer(ir_patch)
        ir_patch.analysis = analyzer.analyze()

        return ir_patch

    def build_from_file(self, filepath: str) -> IRPatch:
        """
        Build IR from a .pd file.

        Args:
            filepath: Path to the .pd file

        Returns:
            IRPatch instance
        """
        # Import pdpy here to avoid circular imports
        from ..patching.pdpy import PdPy

        # Read file content
        with open(filepath, 'rb') as f:
            file_content = f.read()

        # Parse with pdpy
        pdpy_obj = PdPy(filepath)

        return self.build(pdpy_obj, filepath, file_content)


def build_ir(pdpy_obj: Any, patch_path: Optional[str] = None) -> IRPatch:
    """
    Build IR from a pdpy object.

    Convenience function that creates an IRBuilder and builds the IR.

    Args:
        pdpy_obj: A PdPy instance
        patch_path: Optional path to the .pd file

    Returns:
        IRPatch instance
    """
    builder = IRBuilder()
    return builder.build(pdpy_obj, patch_path)


def build_ir_from_file(filepath: str) -> IRPatch:
    """
    Build IR from a .pd file.

    Convenience function that creates an IRBuilder and builds from file.

    Args:
        filepath: Path to the .pd file

    Returns:
        IRPatch instance
    """
    builder = IRBuilder()
    return builder.build_from_file(filepath)
