"""
Deterministic Node ID Generation for Pure Data IR.

This module implements a tiered system for generating stable node IDs that
are resilient to cosmetic changes (position, line order) while remaining
sensitive to structural changes.

Tier 0: Explicit IDs (future - @id=name annotations)
Tier 1: Strong Semantic Anchors (send/receive symbols, array names)
Tier 2: Interface Nodes (inlet~/outlet~ by port index)
Tier 3: Graph-Structure Signature (topology-based hash)
Tier 4: Fallback (stable sort by properties)
"""

import hashlib
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict


class NodeIDGenerator:
    """Generates deterministic IDs for nodes in a Pure Data patch."""

    # Objects with unique symbol arguments (Tier 1)
    SYMBOL_ANCHORS = {
        # Send/receive family
        's', 'send', 'r', 'receive',
        's~', 'send~', 'r~', 'receive~',
        'throw~', 'catch~',
        # Value/table/array
        'value', 'v',
        'table', 'array',
        'soundfiler',
        'text',
        # Named objects
        'delwrite~', 'delread~', 'delread4~',
        'tabread~', 'tabread4~', 'tabosc4~', 'tabwrite~',
        'tabread', 'tabwrite', 'tabread4',
    }

    # Interface objects (Tier 2)
    INTERFACE_OBJECTS = {'inlet', 'inlet~', 'outlet', 'outlet~'}

    def __init__(self):
        self._counter: Dict[str, int] = defaultdict(int)
        self._node_map: Dict[int, str] = {}  # original_id -> generated_id
        self._id_set: Set[str] = set()

    def reset(self):
        """Reset the generator state."""
        self._counter.clear()
        self._node_map.clear()
        self._id_set.clear()

    def _make_unique(self, base_id: str) -> str:
        """Ensure an ID is unique by adding a suffix if needed."""
        if base_id not in self._id_set:
            self._id_set.add(base_id)
            return base_id
        k = 1
        while f"{base_id}#{k}" in self._id_set:
            k += 1
        unique_id = f"{base_id}#{k}"
        self._id_set.add(unique_id)
        return unique_id

    def _sanitize_symbol(self, symbol: str) -> str:
        """Sanitize a symbol for use in an ID."""
        # Replace problematic characters
        sanitized = symbol.replace('/', '_').replace('\\', '_')
        sanitized = sanitized.replace(' ', '_').replace('\t', '_')
        # Limit length
        if len(sanitized) > 32:
            sanitized = sanitized[:32]
        return sanitized

    def _get_tier1_id(self, canvas_path: str, obj_type: str,
                      args: List[str], domain: str) -> Optional[str]:
        """
        Tier 1: Strong Semantic Anchors.
        Objects with unique symbols get IDs based on their symbol argument.
        """
        base_type = obj_type.split('/')[-1]  # Handle library prefixes

        if base_type not in self.SYMBOL_ANCHORS:
            return None

        if not args:
            return None

        symbol = args[0]
        sanitized = self._sanitize_symbol(symbol)

        # Format: canvas_path::type:symbol:domain
        base_id = f"{canvas_path}::{base_type}:{sanitized}"
        if domain and domain != "unknown":
            base_id += f":{domain}"

        return self._make_unique(base_id)

    def _get_tier2_id(self, canvas_path: str, obj_type: str,
                      interface_index: int) -> Optional[str]:
        """
        Tier 2: Interface Nodes.
        inlet/outlet objects get IDs based on their port index.
        """
        if obj_type not in self.INTERFACE_OBJECTS:
            return None

        base_id = f"{canvas_path}::{obj_type}#{interface_index}"
        return self._make_unique(base_id)

    def _compute_node_signature(self, obj_type: str, args: List[str]) -> str:
        """Compute a local signature for a node (type + args)."""
        content = f"{obj_type}|{','.join(str(a) for a in args)}"
        return hashlib.sha256(content.encode()).hexdigest()[:8]

    def _get_tier3_id(self, canvas_path: str, obj_type: str, args: List[str],
                      predecessors: List[str], successors: List[str]) -> str:
        """
        Tier 3: Graph-Structure Signature.
        Generate ID based on local topology (node + neighbors).
        """
        self_sig = self._compute_node_signature(obj_type, args)
        pred_sigs = sorted(predecessors)
        succ_sigs = sorted(successors)

        combined = f"{self_sig}|{','.join(pred_sigs)}|{','.join(succ_sigs)}"
        fp = hashlib.sha256(combined.encode()).hexdigest()[:8]

        base_id = f"{canvas_path}::h{fp}"
        return self._make_unique(base_id)

    def _get_tier4_id(self, canvas_path: str, obj_type: str,
                      kind: str, original_order: int) -> str:
        """
        Tier 4: Fallback.
        Generate ID based on stable sort order.
        """
        # Simple sequential ID as last resort
        key = f"{canvas_path}:{kind}"
        self._counter[key] += 1
        base_id = f"{canvas_path}::n{self._counter[key]}"
        return self._make_unique(base_id)

    def generate_ids(self, nodes: List[Dict[str, Any]],
                     edges: List[Tuple[int, int, int, int]],
                     canvas_path: str = "c0") -> Dict[int, str]:
        """
        Generate deterministic IDs for a list of nodes.

        Args:
            nodes: List of node dicts with 'original_id', 'type', 'args', 'kind', 'domain'
            edges: List of (src_id, src_port, dst_id, dst_port) tuples
            canvas_path: Canvas identifier for namespacing

        Returns:
            Dict mapping original_id to generated_id
        """
        self.reset()

        # Build adjacency information
        predecessors: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        successors: Dict[int, List[Tuple[int, int]]] = defaultdict(list)

        for src_id, src_port, dst_id, dst_port in edges:
            successors[src_id].append((dst_id, src_port))
            predecessors[dst_id].append((src_id, dst_port))

        # Track interface objects for Tier 2 ordering
        interface_counts: Dict[str, int] = defaultdict(int)

        # First pass: identify interface objects and assign indices
        interface_indices: Dict[int, int] = {}
        for node in nodes:
            obj_type = node.get('type', '')
            if obj_type in self.INTERFACE_OBJECTS:
                idx = interface_counts[obj_type]
                interface_indices[node['original_id']] = idx
                interface_counts[obj_type] += 1

        # Generate IDs for each node
        result: Dict[int, str] = {}

        for i, node in enumerate(nodes):
            original_id = node['original_id']
            obj_type = node.get('type', '')
            args = node.get('args', [])
            kind = node.get('kind', 'object')
            domain = node.get('domain', 'unknown')

            generated_id = None

            # Try Tier 1: Semantic anchors
            generated_id = self._get_tier1_id(canvas_path, obj_type, args, domain)

            # Try Tier 2: Interface nodes
            if generated_id is None and original_id in interface_indices:
                generated_id = self._get_tier2_id(
                    canvas_path, obj_type, interface_indices[original_id]
                )

            # Try Tier 3: Graph structure
            if generated_id is None:
                # Get neighbor signatures
                pred_sigs = []
                for pred_id, _ in predecessors.get(original_id, []):
                    pred_node = next((n for n in nodes if n['original_id'] == pred_id), None)
                    if pred_node:
                        pred_sigs.append(self._compute_node_signature(
                            pred_node.get('type', ''),
                            pred_node.get('args', [])
                        ))

                succ_sigs = []
                for succ_id, _ in successors.get(original_id, []):
                    succ_node = next((n for n in nodes if n['original_id'] == succ_id), None)
                    if succ_node:
                        succ_sigs.append(self._compute_node_signature(
                            succ_node.get('type', ''),
                            succ_node.get('args', [])
                        ))

                # Only use Tier 3 if we have meaningful topology
                if pred_sigs or succ_sigs:
                    generated_id = self._get_tier3_id(
                        canvas_path, obj_type, args, pred_sigs, succ_sigs
                    )

            # Tier 4: Fallback
            if generated_id is None:
                generated_id = self._get_tier4_id(canvas_path, obj_type, kind, i)

            result[original_id] = generated_id
            self._node_map[original_id] = generated_id

        return result

    def get_id(self, original_id: int) -> Optional[str]:
        """Get the generated ID for an original ID."""
        return self._node_map.get(original_id)


def generate_canvas_path(canvas_id: str, parent_path: Optional[str] = None) -> str:
    """Generate a canvas path for ID namespacing."""
    if parent_path:
        return f"{parent_path}/{canvas_id}"
    return canvas_id
