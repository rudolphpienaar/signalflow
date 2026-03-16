"""Tests for chip_render glyph positions."""

from signalflow.legacy.config import config
from signalflow.legacy.lib.boxes import moduleBox_compute
from signalflow.legacy.lib.canvas_factory import canvas_create
from signalflow.legacy.lib.chips import (
    _straightPairs_colorize,
    _threadSourceCountsAndSides_compute,
    chip_render,
)
from signalflow.legacy.lib.layout import channelWidth_compute, layout_compute
from signalflow.legacy.lib.tree import tree_flatten
from signalflow.legacy.models import Node
from signalflow.legacy.models.node import Port


def _colorAt(canvas, x: int, y: int) -> str | None:
    """Return the stored ANSI color at one rendered canvas cell."""
    return canvas.grid[y][x][1]


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


def _output_handoff_compute_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="receiverClassDecl_resolve()")
    c2 = Node(module="C", func="classMethod_find()")
    node = Node(module="M", func="callTargetFromConstruction_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret="constructedDecl")
    node.output_ports[(id(c1), 0)] = Port(signal="checker", ret="receiverDecl")
    node.output_ports[(id(c2), 0)] = Port(signal="classDecl", ret="constructedDecl")
    node.internal_wiring = [
        "checker:checker:pure",
        "receiverDecl:classDecl:compute",
        "constructedDecl:constructedDecl:pure",
    ]
    node.children = [c1, c2]
    return node


def _output_handoff_data_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="receiverClassDecl_resolve()")
    c2 = Node(module="C", func="classMethod_find()")
    node = Node(module="M", func="callTargetFromConstruction_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret="constructedDecl")
    node.output_ports[(id(c1), 0)] = Port(signal="checker", ret="receiverDecl")
    node.output_ports[(id(c2), 0)] = Port(signal="classDecl", ret="constructedDecl")
    node.internal_wiring = [
        "checker:checker:data",
        "receiverDecl:classDecl:data",
        "constructedDecl:constructedDecl:data",
    ]
    node.children = [c1, c2]
    return node


def _output_handoff_thread_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="receiverClassDecl_resolve()")
    c2 = Node(module="C", func="classMethod_find()")
    node = Node(module="M", func="callTargetFromConstruction_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret="constructedDecl")
    node.output_ports[(id(c1), 0)] = Port(signal="checker", ret="receiverDecl")
    node.output_ports[(id(c2), 0)] = Port(signal="classDecl", ret="constructedDecl")
    node.internal_wiring = [
        "checker:checker:thread:pure",
        "receiverDecl:classDecl:thread:compute",
        "constructedDecl:constructedDecl:thread:pure",
    ]
    node.children = [c1, c2]
    return node


def _proxy_data_node() -> Node:
    parent = Node(module="App", func="main()")
    child = Node(module="C", func="child()")
    node = Node(module="M", func="proxy()")
    node.input_ports[(id(parent), 0)] = Port(signal="wire", ret="ret")
    node.output_ports[(id(child), 0)] = Port(signal="wire", ret="ret")
    node.internal_wiring = ["wire:wire:WE:data", "ret:ret:EW:data"]
    node.children = [child]
    return node


def _proxy_thread_node() -> Node:
    parent = Node(module="App", func="main()")
    child = Node(module="C", func="child()")
    node = Node(module="M", func="proxy()")
    node.input_ports[(id(parent), 0)] = Port(signal="wire", ret="ret")
    node.output_ports[(id(child), 0)] = Port(signal="wire", ret="ret")
    node.internal_wiring = ["wire:wire:WE:thread", "ret:ret:EW:thread:pure"]
    node.children = [child]
    return node


def _proxy_thread_red_node() -> Node:
    parent = Node(module="App", func="main()")
    child = Node(module="C", func="child()")
    node = Node(module="M", func="proxy()")
    node.input_ports[(id(parent), 0)] = Port(signal="wire", ret="ret")
    node.output_ports[(id(child), 0)] = Port(signal="wire", ret="ret")
    node.internal_wiring = ["wire:wire:WE:thread:color(red)", "ret:ret:EW:thread:pure"]
    node.children = [child]
    return node


def _proxy_thread_nocolor_node() -> Node:
    parent = Node(module="App", func="main()")
    child = Node(module="C", func="child()")
    node = Node(module="M", func="proxy()")
    node.input_ports[(id(parent), 0)] = Port(signal="wire", ret="ret")
    node.output_ports[(id(child), 0)] = Port(signal="wire", ret="ret")
    node.internal_wiring = ["wire:wire:WE:thread:color(none)", "ret:ret:EW:thread:pure"]
    node.children = [child]
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


def _same_name_we_pure_red_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="mapLookupTarget_extract()")
    c2 = Node(module="C", func="mapHandlerExpr_resolve()")
    c3 = Node(module="C", func="handlerDeclaration_resolve()")
    node = Node(module="M", func="callTargetFromStaticMap_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret=None)
    node.output_ports[(id(c1), 0)] = Port(signal="callExpr", ret="mapExpr")
    node.output_ports[(id(c2), 0)] = Port(signal="checker", ret="handlerExpr")
    node.output_ports[(id(c3), 0)] = Port(signal="checker", ret="targetDecl")
    node.internal_wiring = ["checker:checker:WE:thread:pure:color(red)"]
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


def _east_edge_composed_continuity_node() -> Node:
    parents = [Node(module="Proxy", func=f"p{i+1}()") for i in range(5)]
    children = [Node(module="C", func=f"c{i+1}()") for i in range(5)]
    node = Node(module="Hub", func="process()")
    node.inputExplicit = False
    for i, parent in enumerate(parents):
        node.input_ports[(id(parent), 0)] = Port(
            signal=f"s{i+1}",
            ret=f"r{i+1}",
        )
    for i, child in enumerate(children):
        node.output_ports[(id(child), 0)] = Port(
            signal=f"out{i+1}",
            ret=f"ret{i+1}",
        )
    node.internal_wiring = [
        "s1:out1",
        "s1:out1",
        "s1:out2",
        "ret1:r1",
        "ret2:r1",
        "ret3:r1",
        "ret4:r1",
        "ret5:r1",
        "ret5:r1",
        "ret1:out2",
    ]
    node.children = children
    return node


def _east_edge_step_hub_node(nSteps: int) -> Node:
    """Hub-like process() node with cumulative east-edge ret->next-out steps."""
    node = _east_edge_composed_continuity_node()
    baseRoutes = [
        "s1:out1",
        "s1:out1",
        "s1:out2",
        "s1:out3",
        "s1:out4",
        "s1:out5",
        "ret1:r1",
        "ret2:r1",
        "ret3:r1",
        "ret4:r1",
        "ret5:r1",
        "ret5:r1",
    ]
    eastSteps = ["ret1:out2", "ret2:out3", "ret3:out4", "ret4:out5"]
    node.internal_wiring = baseRoutes + eastSteps[:nSteps]
    return node


def _east_edge_composed_continuity_red_node() -> Node:
    node = _east_edge_composed_continuity_node()
    node.internal_wiring[-1] = "ret1:out2:thread:compute:color(red)"
    return node


def _same_wall_thread_red_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="child1()")
    c2 = Node(module="C", func="child2()")
    node = Node(module="M", func="sameName()")
    node.input_ports[(id(parent), 0)] = Port(signal="input", ret="done")
    node.output_ports[(id(c1), 0)] = Port(signal="first", ret="color")
    node.output_ports[(id(c2), 0)] = Port(signal="color", ret="done")
    node.internal_wiring = ["color:color:NS:thread:compute:color(red)"]
    node.children = [c1, c2]
    return node


def _same_wall_thread_nocolor_node() -> Node:
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="child1()")
    c2 = Node(module="C", func="child2()")
    node = Node(module="M", func="sameName()")
    node.input_ports[(id(parent), 0)] = Port(signal="input", ret="done")
    node.output_ports[(id(c1), 0)] = Port(signal="first", ret="color")
    node.output_ports[(id(c2), 0)] = Port(signal="color", ret="done")
    node.internal_wiring = ["color:color:NS:thread:compute:color(none)"]
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

        explicitGeo = explicitNode.geometry
        assert explicitGeo is not None
        continuity = explicitGeo.wallContinuities[0]
        explicitRetRow = continuity.srcRow
        explicitGapRow = continuity.gapRow
        explicitNextRow = continuity.dstRow

        assert implicitCanvas.get(implicitBrkX, implicitRetRow) == '┌'
        assert implicitCanvas.get(implicitBrkX, implicitGapRow) == '█'
        assert implicitCanvas.get(implicitBrkX, implicitNextRow) == '└'

        assert explicitCanvas.get(explicitBrkX, explicitRetRow) == '┌'
        assert explicitCanvas.get(explicitBrkX, explicitGapRow) == '█'
        assert explicitCanvas.get(explicitBrkX, explicitNextRow) == '└'

    def test_explicit_compute_same_wall_matches_default_non_pure_block(self):
        """An explicit compute modifier should preserve the default block render."""
        defaultCanvas, defaultNodes, _ = _render(_output_handoff_node(explicit=True))
        computeCanvas, computeNodes, _ = _render(_output_handoff_compute_node())

        defaultNode = defaultNodes[0]
        computeNode = computeNodes[0]
        defaultGeo = defaultNode.geometry
        computeGeo = computeNode.geometry
        assert defaultGeo is not None
        assert computeGeo is not None

        defaultContinuity = defaultGeo.wallContinuities[0]
        computeContinuity = computeGeo.wallContinuities[0]
        defaultBrkX = defaultNode.x + defaultNode.ow - 1 - config.uTurnWidth
        computeBrkX = computeNode.x + computeNode.ow - 1 - config.uTurnWidth

        assert defaultCanvas.get(defaultBrkX, defaultContinuity.gapRow) == '█'
        assert computeCanvas.get(computeBrkX, computeContinuity.gapRow) == '█'

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

    def test_explicit_data_same_wall_uses_plain_gap_not_compute_block(self):
        """An explicit data same-wall route should not draw the compute block."""
        canvas, nodes, _ = _render(_output_handoff_data_node())
        node = nodes[0]
        geo = node.geometry
        assert geo is not None

        continuity = geo.wallContinuities[0]
        brkX = node.x + node.ow - 1 - config.uTurnWidth

        assert continuity.routeClass == "data"
        assert continuity.routeClassExplicit is True
        assert canvas.get(brkX, continuity.gapRow) == '│'

    def test_explicit_thread_same_wall_uses_thread_compute_block(self):
        """An explicit thread same-wall route should use the thread block glyph."""
        canvas, nodes, _ = _render(_output_handoff_thread_node())
        node = nodes[0]
        geo = node.geometry
        assert geo is not None

        continuity = geo.wallContinuities[0]
        brkX = node.x + node.ow - 1 - config.uTurnWidth

        assert continuity.routeClass == "thread"
        assert continuity.routeClassExplicit is True
        assert canvas.get(brkX, continuity.gapRow) == '■'

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

    def test_explicit_data_straight_route_has_no_compute_block(self):
        """An explicit data straight-through route should not get a block glyph."""
        canvas, nodes, _ = _render(_proxy_data_node())
        node = nodes[0]
        midX = (node.x + node.x + node.ow - 1) // 2

        assert canvas.get(midX, node.y + 3) != '▬'
        assert canvas.get(midX, node.y + 4) != '▬'

    def test_explicit_thread_straight_route_uses_thread_block(self):
        """An explicit thread straight-through route should use a distinct glyph."""
        _canvas, nodes, _ = _render(_proxy_thread_node())
        node = nodes[0]

        straightPairsColored, blockPositions = _straightPairs_colorize(node)
        assert straightPairsColored
        assert any(glyph == '■' for _x, _y, glyph, _color in blockPositions)

    def test_explicit_thread_straight_route_can_override_color(self):
        """A straight explicit-thread route should use its explicit route color."""
        canvas, nodes, _ = _render(_proxy_thread_red_node())
        node = nodes[0]
        midX = (node.x + node.x + node.ow - 1) // 2

        assert canvas.get(midX, node.y + 3) == '■'
        assert _colorAt(canvas, midX, node.y + 3) == "\033[31m"

    def test_explicit_thread_straight_route_can_force_monochrome(self):
        """A straight explicit-thread route may opt out of ANSI color locally."""
        canvas, nodes, _ = _render(_proxy_thread_nocolor_node())
        node = nodes[0]
        midX = (node.x + node.x + node.ow - 1) // 2

        assert canvas.get(midX, node.y + 3) == '■'
        assert _colorAt(canvas, midX, node.y + 3) is None

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
                assert canvas.get(busX, row) in {'┌', '└', '├', '┼'}
                assert canvas.get(busX + 1, row) == '─'

    def test_east_edge_same_wall_with_manifold_uses_reuse_pattern(self):
        """East ret->sig manifold reuse should form a local bridge column."""
        oldSpacing = config.portVerticalSpacing
        config.portVerticalSpacing = 10
        try:
            canvas, nodes, _ = _render(_east_edge_composed_continuity_node())
            node = nodes[0]
            geo = node.geometry
            assert geo is not None

            rx = node.x + node.ow - 1
            busX = min(
                rx - 2 - len("◄ret1"),
                rx - 2 - len("►out2"),
            ) - 2
            srcRows = geo.allAnchorRows["R|ret|ret1"]
            dstRows = geo.allAnchorRows["R|sig|out2"]
            srcRows = sorted(srcRows)
            dstRows = sorted(dstRows)
            assert len(srcRows) == 1
            assert len(dstRows) == 1

            assert canvas.get(busX, srcRows[0]) == '┐'
            assert canvas.get(busX, dstRows[0]) == '┘'
            assert canvas.get(busX + 1, srcRows[0]) == '─'
            assert canvas.get(busX + 1, dstRows[0]) == '─'
            midRows = range(srcRows[0] + 1, dstRows[0])
            assert any(canvas.get(busX, row) == '█' for row in midRows)
            for row in midRows:
                assert canvas.get(busX, row) in {'│', '█', '■'}
        finally:
            config.portVerticalSpacing = oldSpacing

    def test_explicit_thread_same_wall_can_override_color(self):
        """A same-wall explicit-thread route should honor its route color."""
        canvas, nodes, _ = _render(_same_wall_thread_red_node())
        node = nodes[0]
        geo = node.geometry
        assert geo is not None

        continuity = geo.wallContinuities[0]
        brkX = node.x + node.ow - 1 - config.uTurnWidth

        assert canvas.get(brkX, continuity.gapRow) == '■'
        assert _colorAt(canvas, brkX, continuity.gapRow) == "\033[31m"

    def test_explicit_thread_same_wall_can_force_monochrome(self):
        """A same-wall explicit-thread route may opt out of ANSI color locally."""
        canvas, nodes, _ = _render(_same_wall_thread_nocolor_node())
        node = nodes[0]
        geo = node.geometry
        assert geo is not None

        continuity = geo.wallContinuities[0]
        brkX = node.x + node.ow - 1 - config.uTurnWidth

        assert canvas.get(brkX, continuity.gapRow) == '■'
        assert _colorAt(canvas, brkX, continuity.gapRow) is None

    def test_east_edge_reuse_does_not_consume_extra_ew_lane(self):
        """East-edge manifold reuse should not inflate top-ribbon lane counts."""
        oldSpacing = config.portVerticalSpacing
        config.portVerticalSpacing = 10
        try:
            node = _east_edge_composed_continuity_node()
            canvas, nodes, _ = _render(node)
            _ = canvas
            rendered = nodes[0]
            hCounts, srcSides = _threadSourceCountsAndSides_compute(rendered)

            assert srcSides["R|ret|ret1"] == "R"
            assert hCounts["R|ret|ret1"] == 1
        finally:
            config.portVerticalSpacing = oldSpacing

    def test_east_edge_reuse_can_override_route_color(self):
        """East-edge manifold reuse should honor explicit route color."""
        oldSpacing = config.portVerticalSpacing
        config.portVerticalSpacing = 10
        try:
            canvas, nodes, _ = _render(_east_edge_composed_continuity_red_node())
            node = nodes[0]
            rx = node.x + node.ow - 1
            busX = min(
                rx - 2 - len("◄ret1"),
                rx - 2 - len("►out2"),
            ) - 2
            geo = node.geometry
            assert geo is not None
            srcRows = sorted(geo.allAnchorRows["R|ret|ret1"])
            dstRows = sorted(geo.allAnchorRows["R|sig|out2"])
            midRows = range(srcRows[0] + 1, dstRows[0])

            assert any(_colorAt(canvas, busX, row) == "\033[31m" for row in midRows)
            assert _colorAt(canvas, busX + 1, dstRows[0]) == "\033[31m"
        finally:
            config.portVerticalSpacing = oldSpacing

    def test_east_edge_steps_do_not_shift_lower_ribbon_leftward(self):
        """Extra east-edge steps must not pull lower W->E elbows leftward."""
        oldSpacing = config.portVerticalSpacing
        config.portVerticalSpacing = 10
        try:
            canvas0, _nodes0, _ = _render(_east_edge_step_hub_node(0))
            canvas1, _nodes1, _ = _render(_east_edge_step_hub_node(1))
            canvas2, _nodes2, _ = _render(_east_edge_step_hub_node(2))

            def leftJunctionX_get(canvas, rowY: int) -> int | None:
                for x in range(canvas.cols):
                    if canvas.get(x, rowY) in {"┌", "┼"}:
                        return x
                return None

            rowOut4 = 46
            rowOut5 = 56

            out4BaseX = leftJunctionX_get(canvas0, rowOut4)
            out5BaseX = leftJunctionX_get(canvas0, rowOut5)

            assert out4BaseX == leftJunctionX_get(canvas1, rowOut4)
            assert out4BaseX == leftJunctionX_get(canvas2, rowOut4)
            assert out5BaseX == leftJunctionX_get(canvas1, rowOut5)
            assert out5BaseX == leftJunctionX_get(canvas2, rowOut5)
        finally:
            config.portVerticalSpacing = oldSpacing

    def test_explicit_thread_manifold_route_can_override_color(self):
        """A general manifold explicit-thread route should honor its route color."""
        canvas, nodes, _ = _render(_same_name_we_pure_red_node())
        node = nodes[0]
        geo = node.geometry
        assert geo is not None

        seamX = geo.rightZoneInnerX
        seamY = max(max(rows) for rows in geo.allAnchorRows.values()) + 1

        assert canvas.get(seamX, seamY) == '┘'
        assert _colorAt(canvas, seamX, seamY) == "\033[31m"

    def test_implicit_right_wall_continuity_uses_output_occurrence_not_label(self):
        """Implicit continuity should follow repeated-label output occurrence order."""
        canvas, nodes, _ = _render(_implicit_repeated_label_root_node())
        node = nodes[0]
        rx = node.x + node.ow - 1
        brkX = rx - config.uTurnWidth

        assert canvas.get(brkX, node.y + 4) == '┌'
        assert canvas.get(brkX, node.y + 5) == '█'
        assert canvas.get(brkX, node.y + 6) == '└'
