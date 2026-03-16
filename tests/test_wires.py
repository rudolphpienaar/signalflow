"""Tests for wireForward_render and wireReturn_render."""

from pathlib import Path

import yaml

from signalflow.legacy.lib.boxes import moduleBox_compute
from signalflow.legacy.lib.canvas_factory import canvas_create
from signalflow.legacy.lib.chips import chip_render
from signalflow.legacy.lib.layout import channelWidth_compute, layout_compute
from signalflow.legacy.lib.tree import tree_flatten
from signalflow.legacy.lib.wires import thread_render
from signalflow.legacy.models import Node, PortKey
from signalflow.legacy.models.node import Port


def _bind(
    parent: Node,
    child: Node,
    port: Port | None = None,
) -> tuple[PortKey, PortKey]:
    """Bind a single parent→child port pair and register in call_sequence."""
    p = port if port is not None else Port()
    call_idx = sum(1 for c, *_ in parent.call_sequence if c is child)
    out_key: PortKey = (id(child), call_idx)
    in_key:  PortKey = (id(parent), call_idx)
    parent.output_ports[out_key] = p
    child.input_ports[in_key] = p
    parent.call_sequence.append((child, out_key, in_key))
    return out_key, in_key


def _full_render(root: Node):
    cw = channelWidth_compute(root)
    layout_compute(root, cw)
    nodes = tree_flatten(root)
    boxes  = moduleBox_compute(nodes)
    canvas = canvas_create(nodes, cw, boxes)
    for n in nodes:
        chip_render(canvas, n)
    thread_render(canvas, root)
    return canvas, nodes, root.ow


def _hub_root_render():
    """Render examples/hub.yaml and return the root and process nodes."""
    path = Path(__file__).parent.parent / "examples" / "hub.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    from signalflow.legacy.config import config

    config.config_update(data.get("config", {}))
    root = Node.node_fromDict(data.get("tree", data))
    cw = channelWidth_compute(root)
    layout_compute(root, cw)
    nodes = tree_flatten(root)
    boxes = moduleBox_compute(nodes)
    canvas = canvas_create(nodes, cw, boxes)
    for node in nodes:
        chip_render(canvas, node)
    thread_render(canvas, root)
    process = next(node for node in nodes if node.func == "process()")
    return canvas, root, process


class TestForwardWire:
    """Forward-wire rendering smoke tests."""

    def test_forward_wire_places_entry_glyph(self):
        """A forward wire should place a right arrow just before the child wall."""
        child = Node(module="M", func="child()", children=[])
        root  = Node(module="M", func="root()", children=[child])
        _, in_key = _bind(root, child, Port("sig", "ret"))
        canvas, nodes, ow = _full_render(root)
        c = nodes[1]
        entryRow = c.entryRows.get(in_key, c.y + 3)
        # ► is placed one column before the child left wall; wall itself keeps │
        assert canvas.get(c.x - 1, entryRow) == '►'
        assert canvas.get(c.x, entryRow) == '│'

    def test_signal_label_present(self):
        """Forward wire rendering should include the signal label text."""
        child = Node(module="M", func="child()", children=[])
        root  = Node(module="M", func="root()", children=[child])
        _bind(root, child, Port("mySignal", None))
        canvas, nodes, ow = _full_render(root)
        lines = canvas.lines_get()
        assert any('mySignal' in line for line in lines)


class TestReturnWire:
    """Return-wire rendering smoke tests."""

    def test_return_wire_connects(self):
        """A return wire should reconnect to the parent's right wall."""
        child = Node(module="M", func="child()", children=[])
        root  = Node(module="M", func="root()", children=[child])
        _bind(root, child, Port(None, None))
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        rx = r.x + r.ow - 1
        # Root right wall return row (y+4) uses │ (arrow is at rx+1)
        assert canvas.get(rx, r.y + 4) == '│'


class TestRoutingInvariants:
    """Topological rules for wire routing."""

    def test_double_helix_invariant(self):
        """For staggered wires, the forward channel stays right of the return."""
        c1 = Node(module="M", func="c1()", children=[])
        c2 = Node(module="M", func="c2()", children=[])
        root = Node(module="M", func="root()", children=[c1, c2])
        _bind(root, c1, Port(None, None))
        _bind(root, c2, Port(None, None))

        canvas, nodes, ow = _full_render(root)

        r = nodes[0]
        rx = r.x + r.ow - 1

        def find_vchan(y, start_x):
            for x in range(start_x, start_x + 100):
                if canvas.get(x, y) in ('┐', '┘'):
                    return x
            return -1

        chan_f = find_vchan(r.y + 6, rx + 2)
        chan_r = find_vchan(r.y + 7, rx + 2)

        assert chan_f != -1, "Forward channel not found for staggered child 1"
        assert chan_r != -1, "Return channel not found for staggered child 1"
        # Argument (Forward) Right of Return
        assert chan_f > chan_r, (
            "Violation: Forward channel "
            f"{chan_f} is not to the right of Return channel {chan_r}"
        )


class TestParentEastWallRows:
    """Regressions for parent east-wall rows in manifold chips."""

    def test_hub_process_output_exit_matches_resolved_signal_row(self):
        """The first hub output wire should leave on process()'s resolved signal row."""
        canvas, _root, process = _hub_root_render()
        rx = process.x + process.ow - 1
        out1Row = process.geometry.rightSignalRows["out1"][0]

        assert canvas.get(rx, out1Row) == "│"

    def test_hub_process_output_return_matches_resolved_return_row(self):
        """The first hub return wire should use process()'s resolved return row."""
        canvas, _root, process = _hub_root_render()
        rx = process.x + process.ow - 1
        ret1Row = process.geometry.rightReturnRows["ret1"][0]

        assert canvas.get(rx, ret1Row) == "│"
