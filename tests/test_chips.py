"""Tests for chip_render glyph positions."""

from signalflow.config import config
from signalflow.lib.boxes import moduleBox_compute
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.models import Node


def _render(root: Node):
    cw = channelWidth_compute(root)
    layout_compute(root, cw)
    nodes = tree_flatten(root)
    boxes  = moduleBox_compute(nodes)
    canvas = canvas_create(nodes, cw, boxes)
    for n in nodes:
        chip_render(canvas, n)
    return canvas, nodes, root.ow


class TestLeafChip:
    def test_chip_height(self):
        root = Node(module="M", func="f()", children=[])
        canvas, nodes, ow = _render(root)
        assert nodes[0].chip_h == config.baseLeafHeight


class TestRootParentChip:
    def test_right_border_first_exit(self):
        child = Node(module="M", func="c()", children=[])
        root  = Node(module="M", func="r()", children=[child])
        canvas, nodes, ow = _render(root)
        r = nodes[0]
        rx = r.x + r.ow - 1
        assert canvas.get(rx, r.y + 3) == '├'
