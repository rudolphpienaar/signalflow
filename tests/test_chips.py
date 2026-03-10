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


def _same_name_we_pure_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="mapLookupTarget_extract()")
    c2 = Node(module="C", func="mapHandlerExpr_resolve()")
    c3 = Node(module="C", func="handlerDeclaration_resolve()")
    node = Node(module="M", func="callTargetFromStaticMap_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret=None)
    node.output_ports[(id(c1), 0)] = Port(signal="callExpr", ret="mapExpr")
    node.output_ports[(id(c2), 0)] = Port(signal="checker", ret="handlerExpr")
    node.output_ports[(id(c3), 0)] = Port(signal="checker", ret="targetDecl")
    node.internal_wiring = ["checker:checker:WE:pure"]
    node.children = [c1, c2, c3]
    return node


def _hidden_internal_label_receiver_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="classDeclarationFromNewExpr_resolve()")
    c2 = Node(module="C", func="classDeclarationFromNewExpr_resolve()")
    node = Node(module="M", func="receiverClassDecl_resolve()")
    node.showInternalLabelsOverride = False
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret="receiverDecl")
    node.output_ports[(id(c1), 0)] = Port(
        signal="checker_classDeclarationFromNewExpr_resolve",
        ret="receiverDecl",
    )
    node.output_ports[(id(c2), 0)] = Port(
        signal="checker_classDeclarationFromNewExpr_resolve_2",
        ret="classDecl",
    )
    node.internal_wiring = [
        "checker:checker_classDeclarationFromNewExpr_resolve:WE",
        "checker:checker_classDeclarationFromNewExpr_resolve_2:WE",
        "classDecl:receiverDecl:EW",
        "receiverDecl:receiverDecl:EW:pure",
    ]
    node.children = [c1, c2]
    return node


def _implicit_repeated_label_root_node() -> Node:
    c1 = Node(module="C", func="callTargetDirect_resolve()")
    c2 = Node(module="C", func="callTargetFromConstruction_resolve()")
    c3 = Node(module="C", func="callTargetFromStaticMap_resolve()")
    node = Node(module="M", func="callTarget_resolve()")
    node.output_ports[(id(c1), 0)] = Port(signal="checker", ret="directDecl")
    node.output_ports[(id(c2), 0)] = Port(signal="checker", ret="constructedDecl")
    node.output_ports[(id(c3), 0)] = Port(signal="checker", ret=None)
    node.children = [c1, c2, c3]
    return node


class TestLeafChip:
    """Leaf-chip rendering regression checks."""

    def test_chipHeight(self):
        """Leaf chips should reserve the 7-row computation-gap geometry."""
        root = Node(module="M", func="f()", children=[])
        canvas, nodes, ow = _render(root)
        assert nodes[0].chipH == 7   # leaf gap row bumps minimum to 7


class TestRootParentChip:
    """Root-parent rendering regression checks."""

    def test_right_border_first_exit(self):
        """The first root-child exit should pierce the right wall at y+3."""
        child = Node(module="M", func="c()", children=[])
        root  = Node(module="M", func="r()", children=[child])
        canvas, nodes, ow = _render(root)
        r = nodes[0]
        rx = r.x + r.ow - 1
        assert canvas.get(rx, r.y + 3) == '│'


class TestExplicitWallContinuity:
    """Regression tests for explicit same-wall and repeated-label continuity."""

    def test_explicit_output_handoff_renders_same_bracket_as_implicit(self):
        """Explicit right-wall handoff should match the implicit bracket glyphs."""
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
        """An explicit same-name NS directive should render right-wall continuity."""
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

    def test_we_pure_same_name_route_uses_corner_not_tripod(self):
        """A pure same-name WE route should end in a corner, not a tripod junction."""
        canvas, nodes, _ = _render(_same_name_we_pure_node())
        node = nodes[0]
        geo = node.geometry
        assert geo is not None

        directive = geo.wiringDirectives[0]
        srcKey, dstKey = geo.directive_endpointKeys(directive)

        # For this simple manifold there should be exactly one right-boundary
        # seam cell where the trunk meets the destination dogleg.
        seamX = geo.rightZoneInnerX
        seamY = max(max(rows) for rows in geo.allAnchorRows.values()) + 1

        assert srcKey == "L|sig|checker"
        assert dstKey == "R|sig|checker"
        assert canvas.get(seamX, seamY) == '┘'
        assert canvas.get(seamX, seamY) != '┴'

    def test_hidden_internal_labels_keep_anchor_bus_arms_connected(self):
        """Hidden internal labels should not suppress the anchor bus-arm geometry."""
        canvas, nodes, _ = _render(_hidden_internal_label_receiver_node())
        node = nodes[0]
        geo = node.geometry
        assert geo is not None
        assert geo.showInternalLabels is False

        busX = node.x + 1
        for port, rows in geo.allAnchorRows.items():
            if port in geo.unitPorts or geo.endpoint_side(port) != "L":
                continue
            for row in rows:
                assert canvas.get(busX, row) in {'┌', '└', '├'}
                assert canvas.get(busX + 1, row) == '─'

    def test_implicit_right_wall_continuity_uses_output_occurrence_not_label(self):
        """Implicit continuity should follow repeated-label output occurrence order."""
        canvas, nodes, _ = _render(_implicit_repeated_label_root_node())
        node = nodes[0]
        rx = node.x + node.ow - 1
        brkX = rx - config.uTurnWidth

        assert canvas.get(brkX, node.y + 4) == '┌'
        assert canvas.get(brkX, node.y + 5) == '█'
        assert canvas.get(brkX, node.y + 6) == '└'

        assert canvas.get(brkX, node.y + 7) == '┌'
        assert canvas.get(brkX, node.y + 8) == '█'
        assert canvas.get(brkX, node.y + 9) == '└'
