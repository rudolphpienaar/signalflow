"""Geometry/render helper functions for debug surfaces."""

from __future__ import annotations

from signalflow.models import (
    ChipPlacement,
    GridCoord,
    RoutingZone,
    RoutingZoneId,
    RoutingZoneInterconnectAxis,
    RoutingZoneRegionSide,
    result_isOkCheck,
    routingZoneDrawLines_build,
    routingZoneRegionByIdResult_get,
    routingZoneRegionSetAll_get,
)
from signalflow.notation import sfN
from signalflow.render.world import worldCanvas_render
from signalflow.routing import (
    RealizedRouteSet,
    chipLocalGeometrySetResult_buildFromChips,
    realizedRouteSetResult_buildFromChipInternalSolvedRouteSet,
    realizedRouteSetResult_buildFromInterconnectSolvedRouteSet,
    realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet,
)
from signalflow.routing.geometry import chipPlacementStackOffsetResult_build

from .context import SignalFlowContext


def regionSymbol_get(regionKey: str) -> str:
    """Return the canonical display glyph for one named region."""

    symbol = sfN.symbolFromRegionKey_get(regionKey)
    if symbol is not None:
        return symbol
    if regionKey.endswith("/inter_routing_transition"):
        return "X"
    if regionKey.endswith("/intra_routing_transition"):
        return "x"
    if regionKey.endswith("/inter_routing_longitude"):
        side = regionKey.split("/", 1)[0]
        return {"west": "▌", "east": "▐"}.get(side, "?")
    if regionKey.endswith("/inter_routing_latitude"):
        side = regionKey.split("/", 1)[0]
        return {"north": "🭶", "south": "🭻"}.get(side, "?")
    return "?"


def _regionDisplaySpans_build(
    *,
    visibleColBreaks: list[int],
    rowBreaks: list[int],
    mode: str,
) -> tuple[list[int], list[int]]:
    """Build display-space column widths and row heights for a region grid."""

    if mode == "schematic":
        minWidth, maxWidth, minHeight = 3, 8, 1
        colWidths = [
            max(
                minWidth,
                min(
                    maxWidth,
                    visibleColBreaks[index + 1] - visibleColBreaks[index],
                ),
            )
            for index in range(len(visibleColBreaks) - 1)
        ]
        rowHeights = [
            max(minHeight, rowBreaks[index + 1] - rowBreaks[index])
            for index in range(len(rowBreaks) - 1)
        ]
        return (colWidths, rowHeights)

    colWidths = [
        visibleColBreaks[index + 1] - visibleColBreaks[index]
        for index in range(len(visibleColBreaks) - 1)
    ]
    rowHeights = [
        rowBreaks[index + 1] - rowBreaks[index]
        for index in range(len(rowBreaks) - 1)
    ]
    return (colWidths, rowHeights)


def _regionRuler_build(
    *,
    visibleColBreaks: list[int],
    colStarts: list[int],
    totalCols: int,
) -> list[str]:
    """Build the top column ruler for a region grid."""

    rulerTop: list[str] = [" "] * totalCols
    for index, worldCol in enumerate(visibleColBreaks[:-1]):
        marker = str(worldCol % 100)
        displayColStart = colStarts[index]
        for markerIndex, char in enumerate(marker):
            if displayColStart + markerIndex < totalCols:
                rulerTop[displayColStart + markerIndex] = char
    return rulerTop


def regionDrawGrid_build(
    regions: tuple,
    labels: list[str],
    mode: str,
    columnOffset: int | None = None,
) -> list[str]:
    """Build a filled ASCII grid showing each region as a labeled band."""

    if not regions:
        return []

    colBreaks: list[int] = sorted(
        {
            value
            for region in regions
            for value in (
                region.routingZoneRegionFrame.horizontalStart,
                region.routingZoneRegionFrame.horizontalEnd_calculate(),
            )
        }
    )
    rowBreaks: list[int] = sorted(
        {
            value
            for region in regions
            for value in (
                region.routingZoneRegionFrame.verticalStart,
                region.routingZoneRegionFrame.verticalEnd_calculate(),
            )
        }
    )

    displayStartColumn = (
        colBreaks[0] if columnOffset is None else max(0, columnOffset)
    )
    displayEndColumn = colBreaks[-1]
    if displayStartColumn >= displayEndColumn:
        return []

    visibleColBreaks: list[int] = sorted(
        {
            displayStartColumn,
            displayEndColumn,
            *(
                worldColumn
                for worldColumn in colBreaks
                if displayStartColumn <= worldColumn <= displayEndColumn
            ),
        }
    )

    colWidths, rowHeights = _regionDisplaySpans_build(
        visibleColBreaks=visibleColBreaks,
        rowBreaks=rowBreaks,
        mode=mode,
    )

    colStarts: list[int] = [0]
    for width in colWidths:
        colStarts.append(colStarts[-1] + width)
    rowStarts: list[int] = [0]
    for height in rowHeights:
        rowStarts.append(rowStarts[-1] + height)

    totalCols = colStarts[-1]
    totalRows = rowStarts[-1]
    grid: list[list[str]] = [[" "] * totalCols for _ in range(totalRows)]

    sortedIndexed = sorted(
        enumerate(regions),
        key=lambda indexedRegion: -(
            indexedRegion[1].routingZoneRegionFrame.horizontalSpan
            * indexedRegion[1].routingZoneRegionFrame.verticalSpan
        ),
    )
    for index, region in sortedIndexed:
        frame = region.routingZoneRegionFrame
        label = labels[index]
        clippedHorizontalStart = max(frame.horizontalStart, displayStartColumn)
        clippedHorizontalEnd = min(
            frame.horizontalEnd_calculate(), displayEndColumn
        )
        if clippedHorizontalStart >= clippedHorizontalEnd:
            continue
        colBegin = visibleColBreaks.index(clippedHorizontalStart)
        colEnd = visibleColBreaks.index(clippedHorizontalEnd)
        rowBegin = rowBreaks.index(frame.verticalStart)
        rowEnd = rowBreaks.index(frame.verticalEnd_calculate())
        for rowIndex in range(rowBegin, rowEnd):
            for colIndex in range(colBegin, colEnd):
                for displayRow in range(
                    rowStarts[rowIndex], rowStarts[rowIndex + 1]
                ):
                    for displayCol in range(
                        colStarts[colIndex], colStarts[colIndex + 1]
                    ):
                        grid[displayRow][displayCol] = label

    rulerTop = _regionRuler_build(
        visibleColBreaks=visibleColBreaks,
        colStarts=colStarts,
        totalCols=totalCols,
    )

    firstWorldRow = rowBreaks[0]
    rowLabelWidth = max(len(str(rowBreaks[-1] - 1)), 2)
    lines: list[str] = [f"{0:>{rowLabelWidth}}: {''.join(rulerTop)}"]
    for rowIndex, row in enumerate(grid):
        lines.append(
            f"{firstWorldRow + rowIndex:>{rowLabelWidth}}: {''.join(row)}"
        )
    return lines


def _chipStackOffsetOrNone_build(
    debugContext: SignalFlowContext,
    zone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> int | None:
    """Build the cumulative stack offset for one placed chip."""

    regionSide = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    if regionSide is None:
        return None

    sidePlacements: list[ChipPlacement] = sorted(
        (
            placement
            for placement in zone.chipPlacementSet.placements
            if placement.chipTerminalRegionId.routingZoneRegionSide
            is regionSide
        ),
        key=lambda placement: placement.orderIndex,
    )

    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        debugContext.circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(chipLocalGeometrySetResult):
        return None

    stackOffsetResult = chipPlacementStackOffsetResult_build(
        sidePlacements=sidePlacements,
        targetPlacement=chipPlacement,
        chipLocalGeometrySet=chipLocalGeometrySetResult.value,
        routingZoneSense=zone.routingZoneSense,
        regionSide=regionSide,
    )
    if not result_isOkCheck(stackOffsetResult):
        return None
    return stackOffsetResult.value


def _zoneDrawingLines_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Resolve a zone and delegate to the canonical drawer."""

    zoneResult = (
        debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
    )
    if not result_isOkCheck(zoneResult):
        return f"zone {routingZoneId.id}\n  status: missing"
    return "\n".join(routingZoneDrawLines_build(zoneResult.value))


def _textBlockSize_build(
    lines: tuple[str, ...] | list[str],
) -> tuple[int, int]:
    """Build width and height for one text block."""

    if not lines:
        return (0, 0)
    return (max(len(line) for line in lines), len(lines))


def _chipPlacementPointForZone_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> tuple[int, int]:
    """Build the world-coordinate point used for the placed chip marker."""

    regionResult = routingZoneRegionByIdResult_get(
        routingZone,
        chipPlacement.chipTerminalRegionId,
    )
    assert result_isOkCheck(regionResult)
    regionFrame = regionResult.value.routingZoneRegionFrame
    side = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    assert side is not None
    if side in {RoutingZoneRegionSide.WEST, RoutingZoneRegionSide.EAST}:
        return (
            regionFrame.horizontalStart,
            regionFrame.verticalStart + chipPlacement.orderIndex,
        )
    return (
        regionFrame.horizontalStart + chipPlacement.orderIndex,
        regionFrame.verticalStart,
    )


def _zoneSummaryText_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Build a readable debug summary for one placed routing zone."""

    routingZoneResult = (
        debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
    )
    if not result_isOkCheck(routingZoneResult):
        return f"zone {routingZoneId.id}\n  status: missing"
    routingZone = routingZoneResult.value
    placements = debugContext.placementsForZone_get(routingZoneId)
    localRoutes = debugContext.zoneLocalRoutesForZone_get(routingZoneId)
    lines: list[str] = [
        f"zone {routingZone.routingZoneId.id}",
        f"  sense: {routingZone.routingZoneSense.value}",
        (
            "  frame: "
            f"({routingZone.routingZoneFrame.horizontalStart},"
            f"{routingZone.routingZoneFrame.verticalStart}) + "
            f"{routingZone.routingZoneFrame.horizontalSpan}x"
            f"{routingZone.routingZoneFrame.verticalSpan}"
        ),
        f"  regions: {len(routingZoneRegionSetAll_get(routingZone))}",
        f"  placements: {len(placements)}",
        f"  zone-local routes: {len(localRoutes)}",
        "  grid routes: "
        f"{len(debugContext.gridRoutesForZone_get(routingZoneId))}",
    ]
    for chipPlacement in placements:
        lines.append(
            "  - "
            f"{chipPlacement.chipRef.chipId.moduleName}:"
            f"{chipPlacement.chipRef.chipId.functionName} "
            f"{chipPlacement.chipTerminalRegionId.routingZoneRegionSide.value}"  # type: ignore[union-attr]
            f"#{chipPlacement.orderIndex}"
        )
    return "\n".join(lines)


def _zoneRoutesText_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Build readable solved-route text for one placed routing zone."""

    localRoutes = debugContext.zoneLocalRoutesForZone_get(routingZoneId)
    lines: list[str] = [
        f"zone routes {routingZoneId.id}",
        f"  count: {len(localRoutes)}",
    ]
    for localRoute in localRoutes:
        lines.append(
            "  - "
            f"{localRoute.sourceChipRef.chipId.functionName} -> "
            f"{localRoute.destinationChipRef.chipId.functionName} "
            f"[{localRoute.solveKind.value}]"
        )
        lines.append(f"    points: {localRoute.routePoints}")
    return "\n".join(lines)


def _interconnectSummaryText_build(
    debugContext: SignalFlowContext,
    routingZoneInterconnectId,
) -> str:
    """Build readable solved-route text for one placed interconnect."""

    solvedRoutes = debugContext.interconnectRoutesForInterconnect_get(
        routingZoneInterconnectId
    )
    lines: list[str] = [
        (
            "interconnect "
            f"{routingZoneInterconnectId.sourceZoneId.id} -> "
            f"{routingZoneInterconnectId.destinationZoneId.id}"
        ),
        f"  seam routes: {len(solvedRoutes)}",
    ]
    for solvedRoute in solvedRoutes:
        lines.append(
            "  - "
            f"{solvedRoute.sourceChipRef.chipId.functionName} -> "
            f"{solvedRoute.destinationChipRef.chipId.functionName} "
            f"[{solvedRoute.solveKind.value}]"
        )
        lines.append(f"    points: {solvedRoute.routePoints}")
    return "\n".join(lines)


def _interconnectDrawingText_build(
    debugContext: SignalFlowContext,
    sourceGridCoord: GridCoord,
    destinationGridCoord: GridCoord,
    mode: str = "pixel",
) -> str:
    """Build a compact pixel draw for one placed interconnect frame."""

    interconnectResult = (
        debugContext.placedRoutingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=sourceGridCoord,
            destinationGridCoord=destinationGridCoord,
        )
    )
    if not result_isOkCheck(interconnectResult):
        return "interconnect draw\n  status: missing"

    interconnect = interconnectResult.value
    frame = interconnect.routingZoneInterconnectFrame
    axisResult = interconnect.interconnectAxisResult_get()
    if not result_isOkCheck(axisResult):
        return "interconnect draw\n  error: missing axis"

    if mode != "pixel":
        return "interconnect draw\n  expected mode: pixel"

    if axisResult.value is RoutingZoneInterconnectAxis.HORIZONTAL:
        header = (
            " ".join(
                str(frame.horizontalStart + index)
                for index in range(frame.horizontalSpan)
            )
            if frame.horizontalSpan > 0
            else ""
        )
        rows = ["▓" * frame.horizontalSpan for _ in range(frame.verticalSpan)]
        legend = [
            "",
            "legend:",
            (
                "  ▓   seam/interconnect  "
                f"[col={frame.horizontalStart}.."
                f"{frame.horizontalStart + frame.horizontalSpan}  "
                f"row={frame.verticalStart}.."
                f"{frame.verticalStart + frame.verticalSpan}]"
            ),
        ]
        return "\n".join(([header] if header else []) + rows + legend)

    rows = [("▓" * frame.horizontalSpan) for _ in range(frame.verticalSpan)]
    legend = [
        "legend:",
        (
            "  ▓   seam/interconnect  "
            f"[col={frame.horizontalStart}.."
            f"{frame.horizontalStart + frame.horizontalSpan}  "
            f"row={frame.verticalStart}.."
            f"{frame.verticalStart + frame.verticalSpan}]"
        ),
    ]
    return "\n".join(rows + [""] + legend)


def _interconnectWorldCanvasText_build(
    debugContext: SignalFlowContext,
    sourceGridCoord: GridCoord,
    destinationGridCoord: GridCoord,
) -> str:
    """Build one placed-interconnect crop from the composed world canvas."""

    interconnectResult = (
        debugContext.placedRoutingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=sourceGridCoord,
            destinationGridCoord=destinationGridCoord,
        )
    )
    if not result_isOkCheck(interconnectResult):
        return "interconnect world canvas\n  status: missing"

    worldCanvasLines = _worldCanvasLines_build(debugContext)
    if worldCanvasLines is None:
        return "interconnect world canvas\n  error: route realization failed"
    if not worldCanvasLines:
        return "interconnect world canvas\n  <empty>"

    frame = interconnectResult.value.routingZoneInterconnectFrame
    horizontalStart: int = frame.horizontalStart
    horizontalEnd: int = horizontalStart + frame.horizontalSpan
    verticalStart: int = frame.verticalStart
    verticalEnd: int = verticalStart + frame.verticalSpan

    croppedLines: list[str] = []
    for rowIndex in range(verticalStart, verticalEnd):
        if rowIndex >= len(worldCanvasLines):
            break
        croppedLines.append(
            worldCanvasLines[rowIndex][horizontalStart:horizontalEnd]
        )

    if not croppedLines:
        return "interconnect world canvas\n  <empty>"
    return "\n".join(croppedLines)


def _gridText_build(
    debugContext: SignalFlowContext,
    style: str,
) -> str:
    """Build one readable placed-world text view for the named style."""

    if style == "zones":
        return _gridZonesText_build(debugContext)
    if style == "placements":
        return _gridPlacementsText_build(debugContext)
    if style == "routes":
        return _gridRoutesText_build(debugContext)
    return (
        "unknown world print style\n"
        "  expected one of: zones, placements, routes"
    )


def _gridZonesText_build(
    debugContext: SignalFlowContext,
) -> str:
    """Build grid text showing zone coordinates."""

    size = debugContext.placedRoutingZoneGrid.gridSize
    rows: list[str] = [f"world {size.columnIndex}x{size.rowIndex}"]
    for rowIndex in range(1, size.rowIndex + 1):
        cells: list[str] = []
        for columnIndex in range(1, size.columnIndex + 1):
            cells.append(f"[{columnIndex},{rowIndex}]")
        rows.append(" ".join(cells))
    return "\n".join(rows)


def _gridPlacementsText_build(
    debugContext: SignalFlowContext,
) -> str:
    """Build grid text showing chip placement ownership by zone."""

    lines: list[str] = ["world placements"]
    for routingZone in debugContext.zones_getAll():
        placements = debugContext.placementsForZone_get(
            routingZone.routingZoneId
        )
        placementText: str = (
            ", ".join(
                (
                    f"{chipPlacement.chipRef.chipId.functionName}"
                    f"@{chipPlacement.chipTerminalRegionId.routingZoneRegionSide.value}"  # type: ignore[union-attr]
                    f"#{chipPlacement.orderIndex}"
                )
                for chipPlacement in placements
            )
            or "<empty>"
        )
        lines.append(f"  {routingZone.routingZoneId.id}: {placementText}")
    return "\n".join(lines)


def _gridRoutesText_build(
    debugContext: SignalFlowContext,
) -> str:
    """Build grid text showing zone-local route ownership by zone."""

    lines: list[str] = ["world routes"]
    for routingZone in debugContext.zones_getAll():
        localRoutes = debugContext.zoneLocalRoutesForZone_get(
            routingZone.routingZoneId
        )
        routeText: str = (
            ", ".join(
                (
                    f"{localRoute.sourceChipRef.chipId.functionName}->"
                    f"{localRoute.destinationChipRef.chipId.functionName}"
                )
                for localRoute in localRoutes
            )
            or "<none>"
        )
        lines.append(f"  {routingZone.routingZoneId.id}: local={routeText}")
    if debugContext.interconnects_getAll():
        lines.append("  seams:")
        for interconnect in debugContext.interconnects_getAll():
            seamRoutes = debugContext.interconnectRoutesForInterconnect_get(
                interconnect.routingZoneInterconnectId
            )
            seamText: str = (
                ", ".join(
                    (
                        f"{solvedRoute.sourceChipRef.chipId.functionName}->"
                        f"{solvedRoute.destinationChipRef.chipId.functionName}"
                    )
                    for solvedRoute in seamRoutes
                )
                or "<none>"
            )
            lines.append(
                "    "
                f"{interconnect.sourceZoneId.id}->"
                f"{interconnect.destinationZoneId.id}: "
                f"{seamText}"
            )
    lines.append("  grid:")
    for routingZone in debugContext.zones_getAll():
        gridText: str = (
            ", ".join(
                (
                    f"{solvedRoute.sourceChipRef.chipId.functionName}->"
                    f"{solvedRoute.destinationChipRef.chipId.functionName}"
                )
                for solvedRoute in debugContext.gridRoutesForZone_get(
                    routingZone.routingZoneId
                )
            )
            or "<none>"
        )
        lines.append(f"    {routingZone.routingZoneId.id}: {gridText}")
    return "\n".join(lines)


def _worldDrawText_build(
    debugContext: SignalFlowContext,
) -> str:
    """Build a spatial ASCII schematic of the full placed world grid."""

    grid = debugContext.placedRoutingZoneGrid
    size = grid.gridSize

    def _zone_block(col: int, row: int) -> list[str]:
        r = grid.routingZoneSet.zoneResult_get(
            RoutingZoneId(id=GridCoord(columnIndex=col, rowIndex=row))
        )
        if result_isOkCheck(r):
            return list(routingZoneDrawLines_build(r.value))
        return [f"[{col},{row}]", " (missing) "]

    def _has_h_seam(col: int, row: int) -> bool:
        return result_isOkCheck(
            grid.interconnectAtCoordsResult_get(
                GridCoord(columnIndex=col, rowIndex=row),
                GridCoord(columnIndex=col + 1, rowIndex=row),
            )
        )

    def _has_v_seam(col: int, row: int) -> bool:
        return result_isOkCheck(
            grid.interconnectAtCoordsResult_get(
                GridCoord(columnIndex=col, rowIndex=row),
                GridCoord(columnIndex=col, rowIndex=row + 1),
            )
        )

    def _block_w(block: list[str]) -> int:
        return max(len(line) for line in block) if block else 0

    def _pad(block: list[str], height: int, width: int) -> list[str]:
        padded = [line.ljust(width) for line in block]
        while len(padded) < height:
            padded.append(" " * width)
        return padded

    def _compose_h_row(
        blocks: list[list[str]], seams: list[bool]
    ) -> list[str]:
        height = max(len(b) for b in blocks)
        widths = [_block_w(b) for b in blocks]
        padded = [
            _pad(b, height, w) for b, w in zip(blocks, widths, strict=True)
        ]
        mid = height // 2
        lines: list[str] = []
        for i in range(height):
            parts = [padded[0][i]]
            for j, seam in enumerate(seams):
                parts.append(" ─ " if (seam and i == mid) else "   ")
                parts.append(padded[j + 1][i])
            lines.append("".join(parts))
        return lines

    def _compose_v_connector(
        blocks: list[list[str]], seams: list[bool]
    ) -> list[str]:
        widths = [_block_w(b) for b in blocks]
        parts: list[str] = []
        for idx, (w, seam) in enumerate(zip(widths, seams, strict=True)):
            center = w // 2
            ch = "│" if seam else " "
            parts.append(" " * center + ch + " " * (w - center - 1))
            if idx < len(widths) - 1:
                parts.append("   ")
        return ["".join(parts)]

    all_lines: list[str] = [f"world {size.columnIndex}×{size.rowIndex}"]
    prev_blocks: list[list[str]] | None = None
    for rowIndex in range(1, size.rowIndex + 1):
        blocks = [
            _zone_block(col, rowIndex)
            for col in range(1, size.columnIndex + 1)
        ]
        h_seams = [
            _has_h_seam(col, rowIndex) for col in range(1, size.columnIndex)
        ]
        if prev_blocks is not None:
            v_seams = [
                _has_v_seam(col, rowIndex - 1)
                for col in range(1, size.columnIndex + 1)
            ]
            all_lines.extend(_compose_v_connector(prev_blocks, v_seams))
        all_lines.extend(_compose_h_row(blocks, h_seams))
        prev_blocks = blocks

    return "\n".join(all_lines)


def _worldCanvasText_build(
    debugContext: SignalFlowContext,
) -> str:
    """Build the full world canvas as one string."""

    worldCanvasLines = _worldCanvasLines_build(debugContext)
    if worldCanvasLines is None:
        return "world canvas\n  error: route realization failed"
    if not worldCanvasLines:
        return "world canvas\n  <empty>"
    return "\n".join(worldCanvasLines)


def _worldCanvasLines_build(
    debugContext: SignalFlowContext,
) -> tuple[str, ...] | None:
    """Build authoritative world canvas lines, or ``None`` on failure."""

    chipInternalResult = (
        realizedRouteSetResult_buildFromChipInternalSolvedRouteSet(
            debugContext.circuitDocument,
            debugContext.placedRoutingZoneGrid,
            debugContext.chipInternalSolvedRouteSet,
        )
    )
    if not result_isOkCheck(chipInternalResult):
        return None

    zoneLocalResult = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
        debugContext.routingZoneLocalSolvedRouteSet
    )
    if not result_isOkCheck(zoneLocalResult):
        return None

    interconnectResult = (
        realizedRouteSetResult_buildFromInterconnectSolvedRouteSet(
            debugContext.routingZoneInterconnectSolvedRouteSet
        )
    )
    if not result_isOkCheck(interconnectResult):
        return None

    combinedRoutes = RealizedRouteSet(
        realizedRoutes=(
            chipInternalResult.value.realizedRoutes
            + zoneLocalResult.value.realizedRoutes
            + interconnectResult.value.realizedRoutes
        )
    )
    return worldCanvas_render(
        placedGrid=debugContext.placedRoutingZoneGrid,
        circuitDocument=debugContext.circuitDocument,
        realizedRouteSet=combinedRoutes,
    )


def _zoneWorldCanvasText_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Build one placed-zone crop from the composed world canvas."""

    zoneResult = (
        debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
    )
    if not result_isOkCheck(zoneResult):
        return f"zone world canvas {routingZoneId.id}\n  status: missing"

    worldCanvasLines = _worldCanvasLines_build(debugContext)
    if worldCanvasLines is None:
        return (
            f"zone world canvas {routingZoneId.id}"
            "\n  error: route realization failed"
        )
    if not worldCanvasLines:
        return f"zone world canvas {routingZoneId.id}\n  <empty>"

    zoneFrame = zoneResult.value.routingZoneFrame
    horizontalStart: int = zoneFrame.horizontalStart
    horizontalEnd: int = zoneFrame.horizontalEnd_calculate()
    verticalStart: int = zoneFrame.verticalStart
    verticalEnd: int = zoneFrame.verticalEnd_calculate()

    croppedLines: list[str] = []
    for rowIndex in range(verticalStart, verticalEnd):
        if rowIndex >= len(worldCanvasLines):
            break
        croppedLines.append(
            worldCanvasLines[rowIndex][horizontalStart:horizontalEnd]
        )

    if not croppedLines:
        return f"zone world canvas {routingZoneId.id}\n  <empty>"
    return "\n".join(croppedLines)


__all__ = ["regionDrawGrid_build", "regionSymbol_get"]
