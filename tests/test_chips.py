"""Tests for chip_render glyph positions."""

from signalflow.config import BASE_LEAF
from signalflow.lib.boxes import moduleBox_compute
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, innerWidth_get, layout_compute
from signalflow.lib.tree import col_assign, tree_flatten
from signalflow.models import Node


def _render(root: Node):
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
    return canvas, nodes, ow


class TestLeafChip:
    def test_entry_glyph(self):
        root = Node(module="M", func="f()", input_signal=None, children=[])
        canvas, nodes, ow = _render(root)
        n = nodes[0]
        assert canvas.get(n.x, n.entry_row) == '┼'

    def test_return_glyph(self):
        root = Node(module="M", func="f()", input_signal=None, children=[])
        canvas, nodes, ow = _render(root)
        n = nodes[0]
        assert canvas.get(n.x, n.return_row) == '┼'

    def test_chip_height(self):
        root = Node(module="M", func="f()", input_signal=None, children=[])
        canvas, nodes, ow = _render(root)
        assert nodes[0].chip_h == BASE_LEAF


class TestRootParentChip:
    def test_right_border_first_exit(self):
        child = Node(module="M", func="c()", input_signal=None, children=[])
        root  = Node(module="M", func="r()", input_signal=None, children=[child])
        canvas, nodes, ow = _render(root)
        r = nodes[0]
        rx = r.x + ow - 1
        assert canvas.get(rx, r.y + 3) == '├'
