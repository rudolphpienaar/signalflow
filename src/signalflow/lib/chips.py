"""Chip rendering: function boxes, centered labels, in-band ► / ◄ markers."""
from __future__ import annotations

# Standard library
from typing import TYPE_CHECKING

# Local
from signalflow.config import Wire, config
from signalflow.engine.router.models import Location, Terminal
from signalflow.engine.router.router import VLSIRouter
from signalflow.models import Canvas, Node
from signalflow.models.chip_geometry import WallContinuity

if TYPE_CHECKING:
    from signalflow.engine.router.models import Track


def wallContinuitiesFromImplicit_build(node: Node) -> list[WallContinuity]:
    """Build the legacy implicit right-wall continuities for a non-manifold chip."""

    geo = node.geometry
    if geo is None:
        return []

    continuities: list[WallContinuity] = []
    portItems: list = list(node.output_ports.values())
    i: int
    for i in range(len(portItems) - 1):
        portCurr = portItems[i]
        portNext = portItems[i + 1]
        if not portCurr.ret or not portNext.signal:
            continue
        # Implicit continuity is defined by adjacent output-port occurrences,
        # not by display labels. Repeated labels on the right wall are valid,
        # so row identity must come from concrete output order.
        retRow: int = node.y + 4 + 3 * i
        nextRow: int = node.y + 3 + 3 * (i + 1)
        if nextRow != retRow + 2:
            continue
        continuities.append(
            WallContinuity(
                side="R",
                src=portCurr.ret,
                dst=portNext.signal,
                srcRow=retRow,
                dstRow=nextRow,
            )
        )
    return continuities


def wallContinuities_render(
    canvas: Canvas, node: Node, continuities: list[WallContinuity]
) -> None:
    """Render same-wall output continuity with the legacy bracket/block glyphs."""

    if config.implicitThread != "block":
        return

    rx: int = node.x + node.ow - 1
    brkX: int = rx - config.uTurnWidth
    continuity: WallContinuity
    for continuity in continuities:
        if continuity.side != "R":
            continue
        gapChar: str = "│" if continuity.isPure else "█"
        canvas.set(brkX, continuity.srcRow, "┌")
        canvas.hline_force(continuity.srcRow, brkX + 1, rx, "─")
        canvas.set(brkX, continuity.gapRow, gapChar)
        canvas.set(brkX, continuity.dstRow, "└")
        canvas.hline_force(continuity.dstRow, brkX + 1, rx, "─")


def _frame_render(canvas: Canvas, node: Node) -> None:
    """Draw the chip border and header separator."""
    x0: int = node.x
    y0: int = node.y
    rx: int = x0 + node.ow - 1
    by: int = y0 + node.chipH - 1

    canvas.set(x0, y0, "┌")
    canvas.hline_force(y0, x0 + 1, rx, "─")
    canvas.set(rx, y0, "┐")
    canvas.set(x0, by, "└")
    canvas.hline_force(by, x0 + 1, rx, "─")
    canvas.set(rx, by, "┘")

    row: int
    for row in range(1, node.chipH - 1):
        ry: int = y0 + row
        canvas.set(x0, ry, "│")
        canvas.set(rx, ry, "│")

    canvas.set(x0, y0 + 2, "├")
    canvas.hline_force(y0 + 2, x0 + 1, rx, "─")
    canvas.set(rx, y0 + 2, "┤")


def _contentLabel_render(canvas: Canvas, node: Node) -> None:
    """Draw the centered function label and root input labels when applicable."""
    x0: int = node.x
    y0: int = node.y
    iw: int = node.ow - 2
    content: str = node.func.center(iw)[:iw]
    canvas.text(x0 + 1, y0 + 1, content)

    if node.isRoot and 0 in node.input_ports and not node.children:
        port = node.input_ports[0]
        entryY: int
        returnY: int
        if node.internal_wiring:
            entryY, returnY = node.y + 3, node.y + 4
        else:
            entryY, returnY = node.y + 3, node.y + 5
        canvas.set(x0 - 1, entryY, Wire.RA)
        if port.signal:
            canvas.text(2, entryY, port.signal[: x0 - 4])
        if port.ret:
            canvas.text(2, returnY, port.ret[: x0 - 4])


def _leafUturn_render(canvas: Canvas, node: Node) -> None:
    """Render the non-manifold leaf U-turn geometry."""
    from signalflow.models.node import PortKey as _PortKey

    x0: int = node.x
    _pkey: _PortKey
    for _pkey in node.input_ports:
        entryY: int = node.entryRows[_pkey]
        returnY: int = node.returnRows[_pkey]
        gapY: int = entryY + 1
        canvas.hline_force(entryY, x0 + 1, x0 + config.uTurnWidth, "─")
        canvas.set(x0 + config.uTurnWidth, entryY, "┐")
        gapChar: str = "█" if config.implicitThread == "block" else "│"
        canvas.set(x0 + config.uTurnWidth, gapY, gapChar)
        canvas.hline_force(returnY, x0 + 1, x0 + config.uTurnWidth, "─")
        canvas.set(x0 + config.uTurnWidth, returnY, "┘")


def _nonManifold_render(canvas: Canvas, node: Node) -> None:
    """Render leaf or implicit fallback internals for chips without internal wiring."""
    if not node.children:
        _leafUturn_render(canvas, node)
    elif config.implicitThread == "block":
        wallContinuities_render(
            canvas, node, wallContinuitiesFromImplicit_build(node)
        )


def _palette_get() -> list[str]:
    """Return the internal manifold color palette."""
    return [
        "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
        "\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m",
    ]


def _straightPairs_colorize(
    node: Node,
) -> tuple[list[tuple[object, str | None]], list[tuple[int, int]]]:
    """Assign colors to straight pairs and collect opaque block positions."""
    geo = node.geometry
    assert geo is not None

    straightPairsColored: list[tuple[object, str | None]] = []
    blockPositions: list[tuple[int, int]] = []
    palette: list[str] = _palette_get()
    midX: int = (node.x + node.x + node.ow - 1) // 2

    idx: int
    directive: object
    for idx, directive in enumerate(geo.straightDirectives):
        color: str | None = (
            palette[idx % len(palette)] if geo.internalWireColorize else None
        )
        straightPairsColored.append((directive, color))
        src: str = directive.src
        dst: str = directive.dst
        _srcSide: str
        _dstSide: str
        rowY: int
        _srcSide, _dstSide, rowY, _dstRow = geo.directive_endpoints(directive)
        if config.implicitThread == "block" and (src, dst) not in geo.purePairs:
            blockPositions.append((midX, rowY))

    return straightPairsColored, blockPositions


def _straightPairs_render(
    canvas: Canvas,
    node: Node,
    straightPairsColored: list[tuple[object, str | None]],
) -> None:
    """Render straight-through internal directives."""
    x0: int = node.x
    rx: int = x0 + node.ow - 1

    directive: object
    color: str | None
    for directive, color in straightPairsColored:
        _srcSide: str
        _dstSide: str
        rowY: int
        _srcSide, _dstSide, rowY, _dstRow = node.geometry.directive_endpoints(directive)
        canvas.hline_pierce(rowY, x0, rx + 1, color)


def _threadSourceCountsAndSides_compute(
    node: Node,
) -> tuple[dict[str, int], dict[str, str]]:
    """Collect source density and originating wall side for manifold trunks."""
    geo = node.geometry
    assert geo is not None

    hCounts: dict[str, int] = {}
    srcSides: dict[str, str] = {}
    directive: object
    for directive in geo.wiringDirectives:
        srcKey, _ = geo.directive_endpointKeys(directive)
        srcSide, _dstSide, _srcRow, _dstRow = geo.directive_endpoints(directive)
        hCounts[srcKey] = hCounts.get(srcKey, 0) + 1
        srcSides.setdefault(srcKey, srcSide)
    return hCounts, srcSides


def _threadUsedRows_seed(node: Node) -> set[int]:
    """Seed reserved rows from straight-through and pass-through endpoints."""
    geo = node.geometry
    assert geo is not None

    usedRows: set[int] = set()
    directive: object
    for directive in geo.straightDirectives:
        straightSrcKey, _ = geo.directive_endpointKeys(directive)
        usedRows.add(geo.endpoint_wallRow(straightSrcKey))
    port: str
    for port in geo.unitPorts:
        usedRows.add(geo.endpoint_wallRow(port))
    return usedRows


def _eastWestThreadRows_assign(
    node: Node,
    threadToY: dict[str, int],
    usedRows: set[int],
    eastWestCounts: dict[str, int],
) -> None:
    """Assign top-zone rows for east-to-west trunks."""
    ewNext: int = node.y + 3
    srcKey: str
    for srcKey in sorted(eastWestCounts):
        laneCount: int = eastWestCounts[srcKey]
        while any(row in usedRows for row in range(ewNext, ewNext + laneCount)):
            ewNext += 1
        threadToY[srcKey] = ewNext
        usedRows.update(range(ewNext, ewNext + laneCount))
        ewNext += laneCount


def _westEastThreadRows_assign(
    node: Node,
    threadToY: dict[str, int],
    usedRows: set[int],
    westEastCounts: dict[str, int],
) -> None:
    """Assign lower-zone rows for west-to-east trunks."""
    geo = node.geometry
    assert geo is not None

    lastAnchorRow: int = (
        max(max(rows) for rows in geo.allAnchorRows.values())
        if geo.allAnchorRows
        else node.y + 2
    )
    weNextRow: int = lastAnchorRow + 1
    srcKey: str
    for srcKey in sorted(westEastCounts):
        laneCount: int = westEastCounts[srcKey]
        threadToY[srcKey] = weNextRow
        usedRows.update(range(weNextRow, weNextRow + laneCount))
        weNextRow += laneCount


def _threadRows_compute(node: Node) -> dict[str, int]:
    """Allocate trunk rows for manifold source endpoints."""
    hCounts: dict[str, int]
    srcSides: dict[str, str]
    hCounts, srcSides = _threadSourceCountsAndSides_compute(node)

    ewHCounts: dict[str, int] = {
        srcKey: cnt for srcKey, cnt in hCounts.items() if srcSides.get(srcKey) == "R"
    }
    weHCounts: dict[str, int] = {
        srcKey: cnt for srcKey, cnt in hCounts.items() if srcSides.get(srcKey) != "R"
    }

    threadToY: dict[str, int] = {}
    usedRows: set[int] = _threadUsedRows_seed(node)
    _eastWestThreadRows_assign(node, threadToY, usedRows, ewHCounts)
    _westEastThreadRows_assign(node, threadToY, usedRows, weHCounts)

    return threadToY


def _terminal_build(
    x0: int,
    rx: int,
    side: str,
    endpointKey: str,
    rowY: int,
) -> Terminal:
    """Build one router terminal from a manifold endpoint key and anchor row."""
    return Terminal(
        endpointKey,
        Location.WESTSIDE if side == "L" else Location.EASTSIDE,
        x=x0 + 1 if side == "L" else rx - 1,
        y=rowY,
    )


def _routerSignals_get(node: Node) -> list[tuple[str, str]]:
    """Build the router netlist from classified manifold directives."""
    geo = node.geometry
    assert geo is not None
    return [
        geo.directive_endpointKeys(directive)
        for directive in geo.wiringDirectives
    ]


def _routerThreadId_build(directive: object, directiveIdx: int) -> str:
    """Build a stable router track id for one directive occurrence."""
    token: str = directive.orientation or "infer"
    return f"{directive.src}:{directive.dst}:{token}:{directiveIdx}"


def _directiveTerminals_build(
    node: Node,
    directive: object,
    x0: int,
    rx: int,
    srcCounters: dict[str, int],
    dstCounters: dict[str, int],
) -> tuple[str, str, str, str, Terminal, Terminal]:
    """Resolve endpoint keys, sides, and anchor terminals for one directive."""
    geo = node.geometry
    assert geo is not None

    srcKey: str
    dstKey: str
    srcKey, dstKey = geo.directive_endpointKeys(directive)
    srcSide: str
    dstSide: str
    _srcRow: int
    _dstRow: int
    srcSide, dstSide, _srcRow, _dstRow = geo.directive_endpoints(directive)

    srcIdx: int = srcCounters.get(srcKey, 0)
    srcCounters[srcKey] = srcIdx + 1
    dstIdx: int = dstCounters.get(dstKey, 0)
    dstCounters[dstKey] = dstIdx + 1

    tSrc: Terminal = _terminal_build(
        x0,
        rx,
        srcSide,
        srcKey,
        geo.allAnchorRows[srcKey][srcIdx],
    )
    tDst: Terminal = _terminal_build(
        x0,
        rx,
        dstSide,
        dstKey,
        geo.allAnchorRows[dstKey][dstIdx],
    )
    return srcKey, dstKey, srcSide, dstSide, tSrc, tDst


def _routeEntry_render(
    canvas: Canvas,
    points: list[tuple[int, int]],
    color: str | None,
) -> None:
    """Render the source wall exit and initial vertical dogleg."""
    canvas.hline_pierce(
        points[0][1],
        min(points[0][0], points[1][0]),
        max(points[0][0], points[1][0]) + 1,
        color,
    )
    if points[1][1] != points[2][1]:
        canvas.vline(
            points[1][0],
            min(points[1][1], points[2][1]),
            max(points[1][1], points[2][1]) + 1,
            color=color,
        )


def _routeSourceExtension_render(
    canvas: Canvas,
    geo: object,
    trunkY: int,
    srcSide: str,
    srcTrackX: int,
    color: str | None,
) -> None:
    """Render the source-side extension from dogleg to trunk zone."""
    if srcSide == "L" and srcTrackX < geo.leftZoneInnerX:
        canvas.hline_pierce(trunkY, srcTrackX, geo.leftZoneInnerX, color)
    elif srcSide == "R" and srcTrackX > geo.rightZoneInnerX:
        canvas.hline_pierce(trunkY, geo.rightZoneInnerX, srcTrackX + 1, color)


def _routeTrunkEnd_compute(
    geo: object,
    srcSide: str,
    dstSide: str,
    srcTrackX: int,
    dstTrackX: int,
) -> int:
    """Return the inclusive W3 endpoint after seam ownership adjustment."""
    return geo.rightZoneInnerX + (
        1
        if (
            (srcSide == "R" and srcTrackX == geo.rightZoneInnerX)
            or (dstSide == "R" and dstTrackX == geo.rightZoneInnerX)
        )
        else 0
    )


def _routeDestinationExtension_render(
    canvas: Canvas,
    geo: object,
    trunkY: int,
    dstSide: str,
    dstTrackX: int,
    color: str | None,
) -> None:
    """Render the destination-side extension from trunk zone to dogleg."""
    if dstSide == "R" and dstTrackX > geo.rightZoneInnerX:
        canvas.hline_pierce(trunkY, geo.rightZoneInnerX, dstTrackX + 1, color)
    elif dstSide == "L" and dstTrackX < geo.leftZoneInnerX:
        canvas.hline_pierce(trunkY, dstTrackX, geo.leftZoneInnerX, color)


def _routeExit_render(
    canvas: Canvas,
    points: list[tuple[int, int]],
    color: str | None,
) -> None:
    """Render the destination dogleg and final wall entry."""
    if points[3][1] != points[4][1]:
        canvas.vline(
            points[3][0],
            min(points[3][1], points[4][1]),
            max(points[3][1], points[4][1]) + 1,
            color=color,
        )
    canvas.hline_pierce(
        points[4][1],
        min(points[4][0], points[5][0]),
        max(points[4][0], points[5][0]) + 1,
        color,
    )


def _junctionBus_render(canvas: Canvas, node: Node) -> None:
    """Render neutral wall-to-anchor connector buses."""
    geo = node.geometry
    assert geo is not None

    rx: int = node.x + node.ow - 1
    port: str
    rows: list[int]
    for port, rows in geo.allAnchorRows.items():
        if port in geo.unitPorts:
            continue
        side: str = geo.endpoint_side(port)
        wallRow: int = geo.endpoint_wallRow(port)
        busX: int = node.x + 1 if side == "L" else rx - 1
        if geo.endpoint_isSignal(port):
            canvas.vline(busX, min(rows), wallRow, None)
            canvas.set(busX, wallRow, "┘" if side == "L" else "└")
        else:
            canvas.vline(busX, wallRow + 1, max(rows) + 1, None)
            canvas.set(busX, wallRow, "┐" if side == "L" else "┌")


def _sourceColors_map(
    node: Node,
    straightPairsColored: list[tuple[object, str | None]],
) -> dict[str, str | None]:
    """Assign stable colors to manifold source endpoints."""
    geo = node.geometry
    assert geo is not None

    srcColorMap: dict[str, str | None] = {}
    if not geo.internalWireColorize:
        return srcColorMap

    palette: list[str] = _palette_get()
    srcSlot: int = len(straightPairsColored)
    directive: object
    for directive in geo.wiringDirectives:
        srcKey, _ = geo.directive_endpointKeys(directive)
        if srcKey not in srcColorMap:
            srcColorMap[srcKey] = palette[srcSlot % len(palette)]
            srcSlot += 1
    return srcColorMap


def _router_render(
    canvas: Canvas,
    node: Node,
    threadToY: dict[str, int],
    srcColorMap: dict[str, str | None],
) -> None:
    """Render routed manifold paths using the VLSI router."""
    geo = node.geometry
    assert geo is not None

    x0: int = node.x
    rx: int = x0 + node.ow - 1
    routerSignals: list[tuple[str, str]] = _routerSignals_get(node)
    router: VLSIRouter = VLSIRouter(routerSignals)
    srcCounters: dict[str, int] = {}
    dstCounters: dict[str, int] = {}

    directiveIdx: int
    directive: object
    for directiveIdx, directive in enumerate(geo.wiringDirectives):
        srcKey: str
        _dstKey: str
        srcSide: str
        dstSide: str
        tSrc: Terminal
        tDst: Terminal
        srcKey, _dstKey, srcSide, dstSide, tSrc, tDst = _directiveTerminals_build(
            node,
            directive,
            x0,
            rx,
            srcCounters,
            dstCounters,
        )
        color: str | None = srcColorMap.get(srcKey)
        threadId: str = _routerThreadId_build(directive, directiveIdx)
        track: Track = router.route_lay(threadId, tSrc, tDst)
        points: list[tuple[int, int]] = router.canvasCoords_resolve(
            track, geo.portToX, threadToY
        )
        _routeSegments_render(canvas, node, geo, points, srcSide, dstSide, color)


def _routeSegments_render(
    canvas: Canvas,
    node: Node,
    geo: object,
    points: list[tuple[int, int]],
    srcSide: str,
    dstSide: str,
    color: str | None,
) -> None:
    """Render the routed W1-W5 segment sequence for one manifold trace."""
    trunkY: int = points[2][1]
    vXSrcPt: int = points[2][0]
    vXDstPt: int = points[3][0]

    _routeEntry_render(canvas, points, color)
    _routeSourceExtension_render(canvas, geo, trunkY, srcSide, vXSrcPt, color)
    w3End: int = _routeTrunkEnd_compute(geo, srcSide, dstSide, vXSrcPt, vXDstPt)
    if geo.leftZoneInnerX < w3End:
        canvas.hline_pierce(trunkY, geo.leftZoneInnerX, w3End, color)
    _routeDestinationExtension_render(
        canvas,
        geo,
        trunkY,
        dstSide,
        vXDstPt,
        color,
    )
    _routeExit_render(canvas, points, color)


def _anchorOverlay_render(
    canvas: Canvas,
    node: Node,
    srcColorMap: dict[str, str | None],
) -> None:
    """Draw anchor arms and optional internal label text."""
    geo = node.geometry
    assert geo is not None

    rx: int = node.x + node.ow - 1
    port: str
    rows: list[int]
    for port, rows in geo.allAnchorRows.items():
        if port in geo.unitPorts:
            continue
        side: str = geo.endpoint_side(port)
        isSig: bool = geo.endpoint_isSignal(port)
        arrow: str = "►" if isSig else "◄"
        color: str | None = srcColorMap.get(port)
        busX: int = node.x + 1 if side == "L" else rx - 1
        display: str = geo.endpoint_internalDisplay(port)
        label: str = f"{display}{arrow}" if side == "L" else f"{arrow}{display}"

        i: int
        row: int
        for i, row in enumerate(rows):
            isEnd: bool = i == len(rows) - 1
            if side == "L":
                junctionGlyph: str = ("┌" if isSig else "└") if isEnd else "├"
                canvas.set(busX, row, junctionGlyph, color)
                canvas.set(busX + 1, row, "─", color)
                if geo.showInternalLabels:
                    canvas.text(node.x + 3, row, label, color=color)
            else:
                junctionGlyph = ("┐" if isSig else "┘") if isEnd else "┤"
                canvas.set(busX - 1, row, "─", color)
                canvas.set(busX, row, junctionGlyph, color)
                if geo.showInternalLabels:
                    canvas.text(rx - 2 - len(label), row, label, color=color)


def _anchorAudit_validate(node: Node) -> None:
    """Assert that the realized anchor rows match the resolved manifold counts."""
    geo = node.geometry
    assert geo is not None

    port: str
    expectedCount: int
    for port, expectedCount in geo.lCounts.items():
        if port in geo.unitPorts:
            continue
        wallRow: int = geo.endpoint_wallRow(port)
        actualRows: list[int] = geo.allAnchorRows.get(port, [])
        assert len(actualRows) == expectedCount, (
            f"PORT {port}: expected {expectedCount} internal anchors, "
            f"got {len(actualRows)}"
        )
        row: int
        for row in actualRows:
            assert row != wallRow, (
                f"PORT {port}: anchor row {row} coincides with wall port row {wallRow}"
            )
        assert len(set(actualRows)) == len(actualRows), (
            f"PORT {port}: duplicate anchor rows: {actualRows}"
        )


def chip_render(canvas: Canvas, node: Node) -> None:
    """Draw the function chip for *node* onto *canvas*.

    Args:
        canvas: The canvas to draw on.
        node: The node representing the function chip.
    """

    _frame_render(canvas, node)

    # 2. Internal Wiring Manifold — guard BEFORE modeMerge
    if not node.internal_wiring:
        _nonManifold_render(canvas, node)
        _contentLabel_render(canvas, node)
        return

    # Geometry is fully resolved by layout_compute — read from node.geometry.
    geo = node.geometry
    assert geo is not None and geo.resolved, (
        f"chip_render({node.func}): geometry not resolved — "
        "layout_compute must run before chip_render"
    )

    straightPairsColored: list[tuple[object, str | None]]
    blockPositions: list[tuple[int, int]]
    straightPairsColored, blockPositions = _straightPairs_colorize(node)

    canvas.modeMerge = True
    try:
        _straightPairs_render(canvas, node, straightPairsColored)

        if geo.wiringPairs:
            threadToY: dict[str, int] = _threadRows_compute(node)
            _junctionBus_render(canvas, node)
            srcColorMap: dict[str, str | None] = _sourceColors_map(
                node, straightPairsColored
            )
            _router_render(canvas, node, threadToY, srcColorMap)
            _anchorOverlay_render(canvas, node, srcColorMap)
            _anchorAudit_validate(node)

    finally:
        canvas.modeMerge = False

    # 2.3 Straight-through computation blocks (overwrite mode — must follow hlines)
    # ▬ (U+25AC BLACK RECTANGLE) has horizontal emphasis matching the wire direction,
    # visually evoking the IEC resistor symbol on a horizontal line.
    bx: int
    by: int
    for bx, by in blockPositions:
        canvas.set(bx, by, "▬")

    wallContinuities_render(canvas, node, geo.wallContinuities)
    _contentLabel_render(canvas, node)
