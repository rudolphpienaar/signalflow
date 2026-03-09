"""Tests for chip_render glyph positions."""

from signalflow.config import config
from signalflow.lib.boxes import moduleBox_compute
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.models import Node
from signalflow.models.node import Port


def _render(root: Node):
    cw = channelWidth_compute(root)
    layout_compute(root, cw)
    nodes = tree_flatten(root)
    boxes  = moduleBox_compute(nodes)
    canvas = canvas_create(nodes, cw, boxes)
    for n in nodes:
        chip_render(canvas, n)
    return canvas, nodes, root.ow


def _output_handoff_node(explicit: bool) -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="receiverClassDecl_resolve()")
    c2 = Node(module="C", func="classMethod_find()")
    node = Node(module="M", func="callTargetFromConstruction_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret="constructedDecl")
    node.output_ports[(id(c1), 0)] = Port(signal="checker", ret="receiverDecl")
    node.output_ports[(id(c2), 0)] = Port(signal="classDecl", ret="constructedDecl")
    if explicit:
        node.internal_wiring = [
            "checker:checker:pure",
            "receiverDecl:classDecl",
            "constructedDecl:constructedDecl:pure",
        ]
    node.children = [c1, c2]
    return node


def _same_name_right_wall_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="child1()")
    c2 = Node(module="C", func="child2()")
    node = Node(module="M", func="sameName()")
    node.input_ports[(id(parent), 0)] = Port(signal="input", ret="done")
    node.output_ports[(id(c1), 0)] = Port(signal="first", ret="color")
    node.output_ports[(id(c2), 0)] = Port(signal="color", ret="done")
    node.internal_wiring = ["color:color:NS"]
    node.children = [c1, c2]
    return node


class TestLeafChip:
    def test_chipHeight(self):
        root = Node(module="M", func="f()", children=[])
        canvas, nodes, ow = _render(root)
        assert nodes[0].chipH == 7   # leaf gap row bumps minimum to 7


class TestRootParentChip:
    def test_right_border_first_exit(self):
        child = Node(module="M", func="c()", children=[])
        root  = Node(module="M", func="r()", children=[child])
        canvas, nodes, ow = _render(root)
        r = nodes[0]
        rx = r.x + r.ow - 1
        assert canvas.get(rx, r.y + 3) == '│'


class TestExplicitWallContinuity:
    def test_explicit_output_handoff_renders_same_bracket_as_implicit(self):
        implicitCanvas, implicitNodes, _ = _render(_output_handoff_node(explicit=False))
        explicitCanvas, explicitNodes, _ = _render(_output_handoff_node(explicit=True))

        implicitNode = implicitNodes[0]
        explicitNode = explicitNodes[0]
        implicitRx = implicitNode.x + implicitNode.ow - 1
        explicitRx = explicitNode.x + explicitNode.ow - 1
        implicitBrkX = implicitRx - config.uTurnWidth
        explicitBrkX = explicitRx - config.uTurnWidth

        implicitRetRow = implicitNode.y + 4
        implicitGapRow = implicitRetRow + 1
        implicitNextRow = implicitRetRow + 2

        explicitRetRow = explicitNode.y + 4
        explicitGapRow = explicitRetRow + 1
        explicitNextRow = explicitRetRow + 2

        assert implicitCanvas.get(implicitBrkX, implicitRetRow) == '┌'
        assert implicitCanvas.get(implicitBrkX, implicitGapRow) == '█'
        assert implicitCanvas.get(implicitBrkX, implicitNextRow) == '└'

        assert explicitCanvas.get(explicitBrkX, explicitRetRow) == '┌'
        assert explicitCanvas.get(explicitBrkX, explicitGapRow) == '█'
        assert explicitCanvas.get(explicitBrkX, explicitNextRow) == '└'

    def test_same_name_ns_renders_right_wall_continuity(self):
        canvas, nodes, _ = _render(_same_name_right_wall_node())
        node = nodes[0]
        rx = node.x + node.ow - 1
        brkX = rx - config.uTurnWidth
        retRow = node.y + 4
        gapRow = retRow + 1
        nextRow = retRow + 2

        assert canvas.get(brkX, retRow) == '┌'
        assert canvas.get(brkX, gapRow) == '█'
        assert canvas.get(brkX, nextRow) == '└'
