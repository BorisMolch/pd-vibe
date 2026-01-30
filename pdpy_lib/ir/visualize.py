"""
SVG Visualization for Pure Data Patches.

Generates SVG diagrams from IR, showing objects and connections
with color-coded signal vs control paths.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from .core import IRPatch, IRNode, IREdge, EdgeKind, Domain, NodeKind


@dataclass
class Box:
    """A rendered object box."""
    id: str
    x: float
    y: float
    width: float
    height: float
    text: str
    domain: Domain
    kind: NodeKind


@dataclass
class Wire:
    """A rendered connection wire."""
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    domain: Domain


class SVGRenderer:
    """Renders IR patches as SVG diagrams."""

    # Colors
    SIGNAL_COLOR = "#3498db"      # Blue for signal
    CONTROL_COLOR = "#2c3e50"     # Dark gray for control
    SIGNAL_FILL = "#ebf5fb"       # Light blue fill
    CONTROL_FILL = "#f8f9fa"      # Light gray fill
    MESSAGE_FILL = "#fff9c4"      # Yellow for messages
    COMMENT_COLOR = "#7f8c8d"     # Gray for comments
    BACKGROUND = "#ffffff"

    # Sizing
    CHAR_WIDTH = 7                # Approximate character width
    BOX_HEIGHT = 20
    BOX_PADDING = 8
    INLET_OUTLET_SIZE = 8
    MIN_BOX_WIDTH = 30

    def __init__(self, ir_patch: IRPatch):
        self.ir = ir_patch
        self.boxes: Dict[str, Box] = {}
        self.wires: List[Wire] = []
        self._build()

    def _build(self):
        """Build boxes and wires from IR."""
        # Create boxes for all nodes
        for node in self.ir.nodes:
            if not node.layout:
                continue

            # Calculate text and width
            text = self._node_text(node)
            width = max(
                len(text) * self.CHAR_WIDTH + self.BOX_PADDING * 2,
                self.MIN_BOX_WIDTH
            )

            self.boxes[node.id] = Box(
                id=node.id,
                x=node.layout.x,
                y=node.layout.y,
                width=width,
                height=self.BOX_HEIGHT,
                text=text,
                domain=node.domain or Domain.CONTROL,
                kind=node.kind,
            )

        # Create wires for all edges
        for edge in self.ir.edges:
            if edge.kind != EdgeKind.WIRE:
                continue

            from_box = self.boxes.get(edge.from_endpoint.node)
            to_box = self.boxes.get(edge.to_endpoint.node)

            if not from_box or not to_box:
                continue

            # Calculate outlet position (bottom of source box)
            num_outlets = self._get_outlet_count(edge.from_endpoint.node)
            outlet_idx = edge.from_endpoint.outlet or 0
            from_x = self._port_x(from_box, outlet_idx, num_outlets)
            from_y = from_box.y + from_box.height

            # Calculate inlet position (top of dest box)
            num_inlets = self._get_inlet_count(edge.to_endpoint.node)
            inlet_idx = edge.to_endpoint.inlet or 0
            to_x = self._port_x(to_box, inlet_idx, num_inlets)
            to_y = to_box.y

            self.wires.append(Wire(
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                domain=edge.domain or Domain.CONTROL,
            ))

    def _node_text(self, node: IRNode) -> str:
        """Get display text for a node."""
        if node.kind == NodeKind.COMMENT:
            return node.text or ""
        elif node.kind == NodeKind.MESSAGE:
            return " ".join(str(a) for a in node.args) if node.args else "bang"

        # Object: type + args
        parts = [node.type]
        if node.args:
            parts.extend(str(a) for a in node.args[:3])  # Limit args shown
            if len(node.args) > 3:
                parts.append("...")
        return " ".join(parts)

    def _get_inlet_count(self, node_id: str) -> int:
        """Get number of inlets for a node."""
        node = self.ir.get_node(node_id)
        if node and node.io and node.io.inlets:
            return len(node.io.inlets)
        return 1

    def _get_outlet_count(self, node_id: str) -> int:
        """Get number of outlets for a node."""
        node = self.ir.get_node(node_id)
        if node and node.io and node.io.outlets:
            return len(node.io.outlets)
        return 1

    def _port_x(self, box: Box, port_idx: int, num_ports: int) -> float:
        """Calculate x position of a port (inlet/outlet)."""
        if num_ports <= 1:
            return box.x + box.width / 2

        # Distribute ports evenly
        margin = self.BOX_PADDING
        usable_width = box.width - margin * 2
        spacing = usable_width / (num_ports - 1) if num_ports > 1 else 0
        return box.x + margin + port_idx * spacing

    def render(self, canvas_id: str = "c0") -> str:
        """Render the patch as SVG."""
        # Filter to canvas
        canvas_boxes = {k: v for k, v in self.boxes.items()
                        if k.startswith(canvas_id + "::")}
        canvas_wires = [w for w in self.wires]  # TODO: filter by canvas

        if not canvas_boxes:
            canvas_boxes = self.boxes  # Fallback to all

        # Calculate bounds
        if not canvas_boxes:
            return self._empty_svg()

        min_x = min(b.x for b in canvas_boxes.values()) - 20
        min_y = min(b.y for b in canvas_boxes.values()) - 20
        max_x = max(b.x + b.width for b in canvas_boxes.values()) + 20
        max_y = max(b.y + b.height for b in canvas_boxes.values()) + 40

        width = max_x - min_x
        height = max_y - min_y

        # Create SVG
        svg = ET.Element("svg", {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"{min_x} {min_y} {width} {height}",
            "width": str(width),
            "height": str(height),
        })

        # Add styles
        style = ET.SubElement(svg, "style")
        style.text = self._css()

        # Add background
        ET.SubElement(svg, "rect", {
            "x": str(min_x),
            "y": str(min_y),
            "width": str(width),
            "height": str(height),
            "fill": self.BACKGROUND,
        })

        # Draw wires first (behind boxes)
        wires_group = ET.SubElement(svg, "g", {"class": "wires"})
        for wire in canvas_wires:
            self._draw_wire(wires_group, wire)

        # Draw boxes
        boxes_group = ET.SubElement(svg, "g", {"class": "boxes"})
        for box in canvas_boxes.values():
            self._draw_box(boxes_group, box)

        return ET.tostring(svg, encoding="unicode")

    def _css(self) -> str:
        """Generate CSS styles."""
        return f"""
            .box {{ stroke-width: 1.5; }}
            .box-signal {{ stroke: {self.SIGNAL_COLOR}; fill: {self.SIGNAL_FILL}; }}
            .box-control {{ stroke: {self.CONTROL_COLOR}; fill: {self.CONTROL_FILL}; }}
            .box-message {{ stroke: {self.CONTROL_COLOR}; fill: {self.MESSAGE_FILL}; }}
            .box-comment {{ stroke: none; fill: none; }}
            .wire-signal {{ stroke: {self.SIGNAL_COLOR}; stroke-width: 2; fill: none; }}
            .wire-control {{ stroke: {self.CONTROL_COLOR}; stroke-width: 1.5; fill: none; }}
            .text {{ font-family: Monaco, 'Courier New', monospace; font-size: 11px; }}
            .text-signal {{ fill: {self.SIGNAL_COLOR}; }}
            .text-control {{ fill: {self.CONTROL_COLOR}; }}
            .text-comment {{ fill: {self.COMMENT_COLOR}; font-style: italic; }}
        """

    def _draw_box(self, parent: ET.Element, box: Box):
        """Draw a single box."""
        g = ET.SubElement(parent, "g")

        # Determine class based on kind and domain
        if box.kind == NodeKind.COMMENT:
            box_class = "box box-comment"
            text_class = "text text-comment"
        elif box.kind == NodeKind.MESSAGE:
            box_class = "box box-message"
            text_class = "text text-control"
        elif box.domain == Domain.SIGNAL:
            box_class = "box box-signal"
            text_class = "text text-signal"
        else:
            box_class = "box box-control"
            text_class = "text text-control"

        # Draw rectangle (skip for comments)
        if box.kind != NodeKind.COMMENT:
            if box.kind == NodeKind.MESSAGE:
                # Message box: flag shape
                points = self._message_points(box)
                ET.SubElement(g, "polygon", {
                    "points": points,
                    "class": box_class,
                })
            else:
                # Regular object box
                ET.SubElement(g, "rect", {
                    "x": str(box.x),
                    "y": str(box.y),
                    "width": str(box.width),
                    "height": str(box.height),
                    "class": box_class,
                })

        # Draw text
        text = ET.SubElement(g, "text", {
            "x": str(box.x + self.BOX_PADDING),
            "y": str(box.y + box.height - 6),
            "class": text_class,
        })
        text.text = box.text

    def _message_points(self, box: Box) -> str:
        """Generate polygon points for message box (flag shape)."""
        x, y, w, h = box.x, box.y, box.width, box.height
        notch = 4
        return f"{x},{y} {x+w},{y} {x+w+notch},{y+h/2} {x+w},{y+h} {x},{y+h} {x+notch},{y+h/2}"

    def _draw_wire(self, parent: ET.Element, wire: Wire):
        """Draw a connection wire."""
        wire_class = "wire-signal" if wire.domain == Domain.SIGNAL else "wire-control"

        # Simple straight line for now
        # Could use bezier curves for more complex routing
        if abs(wire.to_y - wire.from_y) < 30:
            # Short connection: straight line
            ET.SubElement(parent, "line", {
                "x1": str(wire.from_x),
                "y1": str(wire.from_y),
                "x2": str(wire.to_x),
                "y2": str(wire.to_y),
                "class": wire_class,
            })
        else:
            # Longer connection: curved path
            mid_y = (wire.from_y + wire.to_y) / 2
            d = f"M {wire.from_x} {wire.from_y} C {wire.from_x} {mid_y}, {wire.to_x} {mid_y}, {wire.to_x} {wire.to_y}"
            ET.SubElement(parent, "path", {
                "d": d,
                "class": wire_class,
            })

    def _empty_svg(self) -> str:
        """Return an empty SVG."""
        svg = ET.Element("svg", {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": "0 0 200 100",
            "width": "200",
            "height": "100",
        })
        text = ET.SubElement(svg, "text", {"x": "50", "y": "50"})
        text.text = "Empty patch"
        return ET.tostring(svg, encoding="unicode")


def render_svg(ir_patch: IRPatch, canvas_id: str = "c0") -> str:
    """Render a patch as SVG.

    Args:
        ir_patch: The IR representation of the patch
        canvas_id: Which canvas to render (default: main canvas)

    Returns:
        SVG string
    """
    renderer = SVGRenderer(ir_patch)
    return renderer.render(canvas_id)


def render_svg_from_file(filepath: str, canvas_id: str = "c0") -> str:
    """Render a .pd file as SVG.

    Args:
        filepath: Path to the .pd file
        canvas_id: Which canvas to render

    Returns:
        SVG string
    """
    from .build import build_ir_from_file
    ir_patch = build_ir_from_file(filepath)
    return render_svg(ir_patch, canvas_id)
