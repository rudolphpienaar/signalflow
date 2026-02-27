"""Tests for wire_forward_render and wire_return_render."""

from signalflow.lib.boxes import moduleBox_compute
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, innerWidth_get, layout_compute
from signalflow.lib.tree import col_assign, tree_flatten
from signalflow.lib.wires import thread_render
from signalflow.models import Node


def _full_render(root: Node):
    nodes = tree_flatten(root)
    col_assign(root)
    iw = innerWidth_get(nodes)
    ow = iw + 2
    cw = channelWidth_compute(root)
    layout_compute(root, ow, cw)
    boxes  = moduleBox_compute(nodes, ow)
    canvas = canvas_create(nodes, ow, cw, boxes)
    for n in nodes:
        chip_render(canvas, n, ow)
    thread_render(canvas, root, ow)
    return canvas, nodes, ow


class TestForwardWire:
    def test_forward_wire_places_entry_glyph(self):
        child = Node(module="M", func="child()", input_signal=None, children=[])
        root  = Node(module="M", func="root()", input_signal=None, children=[child])
        canvas, nodes, ow = _full_render(root)
        c = nodes[1]
        # ► is placed one column before the child left wall; wall itself keeps ┼
        assert canvas.get(c.x - 1, c.entry_row) == '►'
        assert canvas.get(c.x, c.entry_row) == '┼'

    def test_signal_label_present(self):
        child = Node(module="M", func="child()", input_signal="mySignal", children=[])
        root  = Node(module="M", func="root()", input_signal=None, children=[child])
        canvas, nodes, ow = _full_render(root)
        lines = canvas.lines_get()
        assert any('mySignal' in line for line in lines)


class TestReturnWire:
    def test_return_wire_connects(self):
        child = Node(module="M", func="child()", input_signal=None, children=[])
        root  = Node(module="M", func="root()", input_signal=None, children=[child])
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        rx = r.x + ow - 1
        # Root right wall return row (y+4) uses ├ (single-wall connection)
        assert canvas.get(rx, r.y + 4) == '├'
