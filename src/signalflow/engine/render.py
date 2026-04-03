"""Engine-dispatched document rendering for SignalFlow.

This module owns the runtime boundary between the top-level engine path and the
quarantined legacy engine path. The public entry point is `diagram_render`,
which delegates to the selected engine and returns printable output lines.

The current new-engine renderer projects the solved planning-world state into a
readable box-drawing artifact. It now exposes one primary diagram block rather
than requiring the user to mentally fuse separate topology and presentation
sections.
"""
from __future__ import annotations

from signalflow.engine.debug import context_buildFromDocument
from signalflow.legacy.engine.render import diagram_render as diagramLegacy_render
from signalflow.models import (
    ChipId,
    ChipPlacement,
    Diagnostic,
    RoutingZone,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    RoutingZoneSense,
    result_isOkCheck,
    routingZoneRegionByIdResult_get,
)
from signalflow.models.diagnostics import diagnosticStack
from signalflow.models.engine import EngineName
from signalflow.render.world import worldCanvas_render
from signalflow.routing import (
    RealizedRouteSet,
    realizedRouteSetResult_buildFromChipInternalSolvedRouteSet,
    realizedRouteSetResult_buildFromInterconnectSolvedRouteSet,
    realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet,
)

_MASK_N: int = 1
_MASK_E: int = 2
_MASK_S: int = 4
_MASK_W: int = 8

_GLYPH_BY_MASK: dict[int, str] = {
    0: " ",
    _MASK_E: "─",
    _MASK_W: "─",
    _MASK_E | _MASK_W: "─",
    _MASK_N: "│",
    _MASK_S: "│",
    _MASK_N | _MASK_S: "│",
    _MASK_E | _MASK_S: "┌",
    _MASK_W | _MASK_S: "┐",
    _MASK_N | _MASK_E: "└",
    _MASK_N | _MASK_W: "┘",
    _MASK_N | _MASK_E | _MASK_S: "├",
    _MASK_N | _MASK_W | _MASK_S: "┤",
    _MASK_E | _MASK_S | _MASK_W: "┬",
    _MASK_N | _MASK_E | _MASK_W: "┴",
    _MASK_N | _MASK_E | _MASK_S | _MASK_W: "┼",
}

_CHIP_MARKER_POOL: str = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


def _diagnosticLine_build(diagnostic: Diagnostic) -> str:
    """Build one readable diagnostic output line."""

    contextSuffix: str = ""
    if diagnostic.context:
        contextSuffix = f" context={diagnostic.context}"
    return (
        f"{diagnostic.level.value}:{diagnostic.phase.value}:{diagnostic.code}: "
        f"{diagnostic.message}{contextSuffix}"
    )


def worldDiagram_lprint(
    title: str,
    documentDict: dict[str, object],
) -> list[str]:
    """Render one document via the new engine pipeline.

    Runs the full staged pipeline then renders the world canvas using
    ``worldCanvas_render``.  Falls back to error lines when the pipeline fails.
    """

    contextResult = context_buildFromDocument(documentDict)
    if not result_isOkCheck(contextResult):
        return _worldFailureLines_build(title)

    debugContext = contextResult.value
    chipInternalResult = realizedRouteSetResult_buildFromChipInternalSolvedRouteSet(
        debugContext.circuitDocument,
        debugContext.placedRoutingZoneGrid,
        debugContext.chipInternalSolvedRouteSet,
    )
    zoneLocalResult = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
        debugContext.routingZoneLocalSolvedRouteSet
    )
    interconnectResult = realizedRouteSetResult_buildFromInterconnectSolvedRouteSet(
        debugContext.routingZoneInterconnectSolvedRouteSet
    )
    if (
        result_isOkCheck(chipInternalResult)
        and result_isOkCheck(zoneLocalResult)
        and result_isOkCheck(interconnectResult)
    ):
        combinedRoutes = RealizedRouteSet(
            realizedRoutes=(
                chipInternalResult.value.realizedRoutes
                + zoneLocalResult.value.realizedRoutes
                + interconnectResult.value.realizedRoutes
            )
        )
    else:
        combinedRoutes = RealizedRouteSet()

    canvasLines = worldCanvas_render(
        placedGrid=debugContext.placedRoutingZoneGrid,
        circuitDocument=debugContext.circuitDocument,
        realizedRouteSet=combinedRoutes,
    )

    lines: list[str] = []
    if title:
        lines.append(f"== {title} ==")
        lines.append("")
    lines.extend(canvasLines)
    return lines


def _worldFailureLines_build(title: str) -> list[str]:
    """Build readable error lines when the new-engine pipeline fails."""

    lines: list[str] = []
    if title:
        lines.append(f"== {title} ==")
        lines.append("")
    lines.append("engine: new")
    lines.append("status: error")
    diagnostics: tuple[Diagnostic, ...] = (
        diagnosticStack.diagnosticSet_build().diagnostics_getAll()
    )
    if not diagnostics:
        lines.append("diagnostics: <none>")
        return lines
    lines.append("diagnostics:")
    diagnostic: Diagnostic
    for diagnostic in diagnostics:
        lines.append(f"  {_diagnosticLine_build(diagnostic)}")
    return lines


def _worldProjectionLines_build(
    title: str,
    debugContext,
) -> list[str]:
    """Build readable projection lines from the current solved pipeline."""

    chipMarkerMap: dict[ChipId, str] = _chipMarkerMap_build(debugContext)
    chipInternalCount: int = len(
        debugContext.chipInternalSolvedRouteSet.chipInternalSolvedRoutes
    )
    zoneLocalCount: int = len(
        debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
    )
    seamCount: int = len(
        debugContext.routingZoneInterconnectSolvedRouteSet
        .routingZoneInterconnectSolvedRoutes
    )
    gridCount: int = len(
        debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
    )
    lines: list[str] = []
    if title:
        lines.append(f"== {title} ==")
        lines.append("")
    lines.extend(
        [
            "engine: new",
            "artifact: planning_projection",
            (
                "world: "
                f"{debugContext.placedRoutingZoneGrid.gridSize.columnIndex}x"
                f"{debugContext.placedRoutingZoneGrid.gridSize.rowIndex} "
                f"{debugContext.placedRoutingZoneGrid.worldSense.value}"
            ),
            (
                "routeCounts: "
                f"chip_internal={chipInternalCount} "
                f"zone_local={zoneLocalCount} "
                f"seam={seamCount} "
                f"grid={gridCount}"
            ),
            "",
            "legend:",
        ]
    )
    chipId: ChipId
    for chipId in debugContext.chipIds_getAll():
        marker: str = chipMarkerMap[chipId]
        lines.append(f"  {marker} = {chipId.moduleName}:{chipId.functionName}")

    lines.append("")
    lines.append("diagram:")
    lines.extend(
        _diagramLines_build(
            debugContext=debugContext,
            chipMarkerMap=chipMarkerMap,
        )
    )

    lines.append("")
    lines.append("canvas:")
    lines.extend(
        _canvasLines_build(
            debugContext=debugContext,
            chipMarkerMap=chipMarkerMap,
        )
    )

    lines.append("")
    lines.append("world-routes:")
    lines.extend(_worldRouteLines_build(debugContext))

    lines.append("")
    lines.append("chip-internal:")
    chipInternalLines: list[str] = _chipInternalLines_build(debugContext)
    lines.extend(chipInternalLines)
    return lines


def _chipMarkerMap_build(debugContext) -> dict[ChipId, str]:
    """Build stable single-character markers for canonical chips."""

    markerMap: dict[ChipId, str] = {}
    chipIndex: int
    chipId: ChipId
    for chipIndex, chipId in enumerate(debugContext.chipIds_getAll()):
        if chipIndex < len(_CHIP_MARKER_POOL):
            markerMap[chipId] = _CHIP_MARKER_POOL[chipIndex]
        else:
            markerMap[chipId] = "*"
    return markerMap


def _canvasLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
) -> list[str]:
    """Build world-canvas lines from solved routes and chip placements."""

    routeMaskByPoint: dict[tuple[int, int], int] = {}
    routePointSequence: tuple[tuple[RoutingZoneRoutePoint, ...], ...] = (
        tuple(
            solvedRoute.routePoints
            for solvedRoute in (
                debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
            )
        )
        + tuple(
            solvedRoute.routePoints
            for solvedRoute in (
                debugContext.routingZoneInterconnectSolvedRouteSet
                .routingZoneInterconnectSolvedRoutes
            )
        )
        + tuple(
            solvedRoute.routePoints
            for solvedRoute in (
                debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
            )
        )
    )

    routePoints: tuple[RoutingZoneRoutePoint, ...]
    for routePoints in routePointSequence:
        _routeMaskByPoint_mutateForRoute(
            routeMaskByPoint=routeMaskByPoint,
            routePoints=routePoints,
        )

    markerByPoint: dict[tuple[int, int], str] = {}
    routingZone: RoutingZone
    for routingZone in debugContext.zones_getAll():
        chipPlacement: ChipPlacement
        for chipPlacement in routingZone.chipPlacementSet.placements:
            markerPoint = _chipPlacementPoint_build(
                routingZone=routingZone,
                chipPlacement=chipPlacement,
            )
            markerByPoint[markerPoint] = chipMarkerMap[chipPlacement.chipRef.chipId]

    maxHorizontalIndex: int = 0
    maxVerticalIndex: int = 0
    point: tuple[int, int]
    for point in tuple(routeMaskByPoint) + tuple(markerByPoint):
        maxHorizontalIndex = max(maxHorizontalIndex, point[0])
        maxVerticalIndex = max(maxVerticalIndex, point[1])
    maxHorizontalIndex = max(
        maxHorizontalIndex,
        max(
            routingZone.routingZoneFrame.horizontalEnd_calculate() - 1
            for routingZone in debugContext.zones_getAll()
        ),
    )
    maxVerticalIndex = max(
        maxVerticalIndex,
        max(
            routingZone.routingZoneFrame.verticalEnd_calculate() - 1
            for routingZone in debugContext.zones_getAll()
        ),
    )
    if debugContext.interconnects_getAll():
        maxHorizontalIndex = max(
            maxHorizontalIndex,
            max(
                (
                    interconnect.routingZoneInterconnectFrame.horizontalStart
                    + interconnect.routingZoneInterconnectFrame.horizontalSpan
                    - 1
                )
                for interconnect in debugContext.interconnects_getAll()
            ),
        )
        maxVerticalIndex = max(
            maxVerticalIndex,
            max(
                (
                    interconnect.routingZoneInterconnectFrame.verticalStart
                    + interconnect.routingZoneInterconnectFrame.verticalSpan
                    - 1
                )
                for interconnect in debugContext.interconnects_getAll()
            ),
        )

    lines: list[str] = []
    rulerDigits: str = "".join(
        str(index % 10) for index in range(maxHorizontalIndex + 1)
    )
    lines.append(f"    {rulerDigits}")
    verticalIndex: int
    for verticalIndex in range(maxVerticalIndex + 1):
        rowCharacters: list[str] = []
        horizontalIndex: int
        for horizontalIndex in range(maxHorizontalIndex + 1):
            pointKey: tuple[int, int] = (horizontalIndex, verticalIndex)
            if pointKey in markerByPoint:
                rowCharacters.append(markerByPoint[pointKey])
                continue
            rowCharacters.append(
                _GLYPH_BY_MASK.get(routeMaskByPoint.get(pointKey, 0), " ")
            )
        lines.append(f"{verticalIndex:>3} {''.join(rowCharacters)}")
    return lines


def _diagramLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
) -> list[str]:
    """Build the primary rendered diagram block."""

    if debugContext.placedRoutingZoneGrid.gridSize.rowIndex > 1:
        return _rectangularDiagramLines_build(
            debugContext=debugContext,
            chipMarkerMap=chipMarkerMap,
        )

    topologyLines: list[str] = _worldTopologyLines_build(
        debugContext=debugContext,
        chipMarkerMap=chipMarkerMap,
    )
    presentationLines: list[str] = _presentationLines_build(
        debugContext=debugContext,
        chipMarkerMap=chipMarkerMap,
    )
    connectorLines: list[str] = _flowConnectorLines_build(debugContext=debugContext)
    labeledLines: list[str] = _topologyLabeledLines_build(
        debugContext=debugContext,
        topologyLines=topologyLines,
    )
    if not presentationLines:
        return labeledLines
    for rowKind, rowText in _compactDiagramFlowRows_build(
        connectorLines=connectorLines,
        presentationLines=presentationLines,
    ):
        labeledLines.append(f"  {rowKind}  {rowText}")
    return labeledLines


def _rectangularDiagramLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
) -> list[str]:
    """Build a row-grouped diagram for rectangular worlds."""

    rowLabels: tuple[str, ...] = (
        "zone ",
        "coord",
        "chip ",
        "chip ",
        "face ",
        "zone ",
        "seam ",
    )
    lines: list[str] = []
    rowIndex: int
    for rowIndex in range(1, debugContext.placedRoutingZoneGrid.gridSize.rowIndex + 1):
        topologyBlockLines: list[str] = _rectangularTopologyBlockLines_build(
            debugContext=debugContext,
            chipMarkerMap=chipMarkerMap,
            rowIndex=rowIndex,
        )
        lineIndex: int
        topologyLine: str
        for lineIndex, topologyLine in enumerate(topologyBlockLines):
            lines.append(f"  {rowLabels[lineIndex]} {topologyLine.strip()}")

        verticalBand = _diagramVerticalBandForGridRow_build(
            debugContext=debugContext,
            rowIndex=rowIndex,
        )
        flowRows = _diagramFlowRowsForVerticalBand_build(
            debugContext=debugContext,
            chipMarkerMap=chipMarkerMap,
            gridRowIndex=rowIndex,
            verticalStartIndex=verticalBand[0],
            verticalEndIndex=verticalBand[1],
        )
        for rowKind, rowText in flowRows:
            lines.append(f"  {rowKind}  {rowText}")
        if rowIndex < debugContext.placedRoutingZoneGrid.gridSize.rowIndex:
            lines.append(
                f"  seam  {_rectangularSeamLine_build(debugContext, rowIndex).strip()}"
            )
    return lines


def _compactDiagramFlowRows_build(
    connectorLines: list[str],
    presentationLines: list[str],
) -> list[tuple[str, str]]:
    """Build compact labeled flow rows for the main diagram."""

    rowPairs: list[tuple[str, str]] = []
    rowIndex: int
    for rowIndex, flowLine in enumerate(presentationLines):
        connectorLine: str = (
            connectorLines[rowIndex] if rowIndex < len(connectorLines) else ""
        )
        if _diagramFlowRowIsEmpty_isPresentCheck(
            connectorLine=connectorLine,
            flowLine=flowLine,
        ):
            continue
        rowPairs.append((connectorLine, flowLine))

    compactRows: list[tuple[str, str]] = []
    index: int = 0
    while index < len(rowPairs):
        connectorLine, flowLine = rowPairs[index]
        if not _verticalPassThroughFlowRow_isPresentCheck(flowLine):
            if connectorLine and _flowRowHasChipBody_isPresentCheck(flowLine):
                compactRows.append(("link", connectorLine))
            compactRows.append(("flow", flowLine))
            index += 1
            continue

        runEndIndex: int = index
        while (
            runEndIndex + 1 < len(rowPairs)
            and _verticalPassThroughFlowRow_isPresentCheck(rowPairs[runEndIndex + 1][1])
        ):
            runEndIndex += 1

        if runEndIndex > index:
            compactRows.append(
                ("flow", _ellipsisFlowLine_build(rowPairs[index][1]))
            )
        else:
            runIndex: int
            for runIndex in range(index, runEndIndex + 1):
                runConnectorLine, runFlowLine = rowPairs[runIndex]
                if (
                    runConnectorLine
                    and _flowRowHasChipBody_isPresentCheck(runFlowLine)
                ):
                    compactRows.append(("link", runConnectorLine))
                compactRows.append(("flow", runFlowLine))

        index = runEndIndex + 1
    return compactRows


def _diagramFlowRowIsEmpty_isPresentCheck(
    connectorLine: str,
    flowLine: str,
) -> bool:
    """Return whether one diagram flow row pair is visually empty."""

    connectorBody: str = connectorLine[4:] if len(connectorLine) >= 4 else ""
    flowBody: str = flowLine[4:] if len(flowLine) >= 4 else ""
    return not connectorBody.strip() and not flowBody.strip()


def _verticalPassThroughFlowRow_isPresentCheck(flowLine: str) -> bool:
    """Return whether one flow row is only vertical pass-through content."""

    if len(flowLine) < 4:
        return False
    flowBody: str = flowLine[4:]
    strippedBody: str = flowBody.strip()
    if not strippedBody:
        return False
    return all(character in {" ", "│"} for character in strippedBody)


def _flowRowHasChipBody_isPresentCheck(flowLine: str) -> bool:
    """Return whether one flow row contains rendered chip bodies/endpoints."""

    flowBody: str = flowLine[4:] if len(flowLine) >= 4 else flowLine
    return any(character.isalnum() or character == "*" for character in flowBody)


def _ellipsisFlowLine_build(flowLine: str) -> str:
    """Build one compact ellipsis row for collapsed flow runs."""

    rowPrefix: str = flowLine[:4]
    flowBody: str = flowLine[4:]
    bodyCharacters: list[str] = list(flowBody)
    nonSpaceIndices: list[int] = [
        index for index, character in enumerate(bodyCharacters) if character != " "
    ]
    if not nonSpaceIndices:
        return rowPrefix + flowBody
    midpointIndex: int = nonSpaceIndices[len(nonSpaceIndices) // 2]
    bodyCharacters[midpointIndex] = "⋮"
    return rowPrefix + "".join(
        " " if character == "│" else character for character in bodyCharacters
    )


def _topologyLabeledLines_build(
    debugContext,
    topologyLines: list[str],
) -> list[str]:
    """Build labeled diagram rows for the topology block."""

    if (
        debugContext.placedRoutingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST
        and debugContext.placedRoutingZoneGrid.gridSize.rowIndex == 1
    ):
        topologyLabels: tuple[str, ...] = (
            "zone ",
            "coord",
            "chip ",
            "chip ",
            "face ",
            "zone ",
        )
        labeledLines: list[str] = []
        lineIndex: int
        topologyLine: str
        for lineIndex, topologyLine in enumerate(topologyLines):
            label: str = (
                topologyLabels[lineIndex]
                if lineIndex < len(topologyLabels)
                else "diag "
            )
            labeledLines.append(f"  {label} {topologyLine.strip()}")
        return labeledLines

    stackedLabels: tuple[str, ...] = (
        "zone ",
        "coord",
        "chip ",
        "chip ",
        "face ",
        "zone ",
        "seam ",
    )
    labeledLines = []
    lineIndex = 0
    for topologyLine in topologyLines:
        label = stackedLabels[lineIndex % len(stackedLabels)]
        labeledLines.append(f"  {label} {topologyLine.strip()}")
        lineIndex += 1
    return labeledLines


def _flowConnectorLines_build(
    debugContext,
) -> list[str]:
    """Build connector rows between zone boxes and flow rows."""

    _, chipIdByPoint, maxHorizontalIndex, maxVerticalIndex = _worldPointState_build(
        debugContext=debugContext,
    )
    lines: list[str] = []
    verticalIndex: int
    for verticalIndex in range(maxVerticalIndex + 1):
        rowCharacters: list[str] = [" "] * (4 + ((maxHorizontalIndex + 1) * 3))
        rowPrefix: str = f"{verticalIndex:>3} "
        prefixIndex: int
        for prefixIndex, character in enumerate(rowPrefix):
            rowCharacters[prefixIndex] = character
        horizontalIndex: int
        for horizontalIndex in range(maxHorizontalIndex + 1):
            if (horizontalIndex, verticalIndex) not in chipIdByPoint:
                continue
            stemIndex: int = 4 + (horizontalIndex * 3) + 1
            rowCharacters[stemIndex] = "│"
        lines.append("".join(rowCharacters).rstrip())
    return lines


def _presentationLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
) -> list[str]:
    """Build expanded presentation rows with chip-face bodies and route cells."""

    routeMaskByPoint, chipIdByPoint, maxHorizontalIndex, maxVerticalIndex = (
        _worldPointState_build(
            debugContext=debugContext,
        )
    )
    lines: list[str] = []
    verticalIndex: int
    for verticalIndex in range(maxVerticalIndex + 1):
        rowSegments: list[str] = []
        horizontalIndex: int
        for horizontalIndex in range(maxHorizontalIndex + 1):
            pointKey: tuple[int, int] = (horizontalIndex, verticalIndex)
            chipId = chipIdByPoint.get(pointKey)
            if chipId is not None:
                rowSegments.append(
                    _chipContactBodyText_build(
                        chipMarker=chipMarkerMap[chipId],
                        routeMask=routeMaskByPoint.get(pointKey, 0),
                    )
                )
                continue
            rowSegments.append(
                _routeCellText_build(routeMaskByPoint.get(pointKey, 0))
            )
        lines.append(f"{verticalIndex:>3} {''.join(rowSegments)}")
    return lines


def _worldTopologyLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
) -> list[str]:
    """Build readable zone-topology lines above the route canvas."""

    if debugContext.placedRoutingZoneGrid.gridSize.rowIndex > 1:
        return _rectangularTopologyLines_build(
            debugContext=debugContext,
            chipMarkerMap=chipMarkerMap,
        )

    worldSense = debugContext.placedRoutingZoneGrid.worldSense
    routingZones = debugContext.zones_getAll()
    if worldSense is RoutingZoneSense.WEST_TO_EAST:
        width: int = max(
            routingZone.routingZoneFrame.horizontalEnd_calculate()
            for routingZone in routingZones
        )
        topRow: list[str] = [" "] * width
        coordRow: list[str] = [" "] * width
        chipTopRow: list[str] = [" "] * width
        chipBottomRow: list[str] = [" "] * width
        chipPortRow: list[str] = [" "] * width
        bottomRow: list[str] = [" "] * width
        routingZone: RoutingZone
        for routingZone in routingZones:
            _zoneBoxRows_mutate(
                topRow=topRow,
                coordRow=coordRow,
                chipTopRow=chipTopRow,
                chipBottomRow=chipBottomRow,
                chipPortRow=chipPortRow,
                bottomRow=bottomRow,
                routingZone=routingZone,
                chipRows=_zoneChipRows_build(
                    debugContext=debugContext,
                    routingZone=routingZone,
                    chipMarkerMap=chipMarkerMap,
                ),
            )
        _interconnectRows_mutate(
            debugContext=debugContext,
            row=chipPortRow,
        )
        return [
            f"    {''.join(topRow)}",
            f"    {''.join(coordRow)}",
            f"    {''.join(chipTopRow)}",
            f"    {''.join(chipBottomRow)}",
            f"    {''.join(chipPortRow)}",
            f"    {''.join(bottomRow)}",
        ]

    lines: list[str] = []
    routingZoneIndex: int
    for routingZoneIndex, routingZone in enumerate(routingZones):
        lines.extend(
            _verticalZoneBoxLines_build(
                debugContext=debugContext,
                routingZone=routingZone,
                chipMarkerMap=chipMarkerMap,
            )
        )
        if routingZoneIndex < len(routingZones) - 1:
            lines.append("   ↓")
    return lines


def _rectangularTopologyLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
) -> list[str]:
    """Build row-grouped topology blocks for rectangular placed worlds."""

    lines: list[str] = []
    rowIndex: int
    for rowIndex in range(1, debugContext.placedRoutingZoneGrid.gridSize.rowIndex + 1):
        lines.extend(
            _rectangularTopologyBlockLines_build(
                debugContext=debugContext,
                chipMarkerMap=chipMarkerMap,
                rowIndex=rowIndex,
            )
        )
        if rowIndex < debugContext.placedRoutingZoneGrid.gridSize.rowIndex:
            lines.append(
                _rectangularSeamLine_build(
                    debugContext=debugContext,
                    rowIndex=rowIndex,
                )
            )
    return lines


def _rectangularTopologyBlockLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
    rowIndex: int,
) -> list[str]:
    """Build one topology block for one rectangular world row."""

    if debugContext.placedRoutingZoneGrid.worldSense is RoutingZoneSense.NORTH_TO_SOUTH:
        return _verticalRectangularTopologyBlockLines_build(
            debugContext=debugContext,
            chipMarkerMap=chipMarkerMap,
            rowIndex=rowIndex,
        )

    rowZones: list[RoutingZone] = _routingZonesForGridRow_build(
        debugContext=debugContext,
        rowIndex=rowIndex,
    )
    width: int = max(
        routingZone.routingZoneFrame.horizontalEnd_calculate()
        for routingZone in rowZones
    )
    topRow: list[str] = [" "] * width
    coordRow: list[str] = [" "] * width
    chipTopRow: list[str] = [" "] * width
    chipBottomRow: list[str] = [" "] * width
    chipPortRow: list[str] = [" "] * width
    bottomRow: list[str] = [" "] * width
    routingZone: RoutingZone
    for routingZone in rowZones:
        _zoneBoxRows_mutate(
            topRow=topRow,
            coordRow=coordRow,
            chipTopRow=chipTopRow,
            chipBottomRow=chipBottomRow,
            chipPortRow=chipPortRow,
            bottomRow=bottomRow,
            routingZone=routingZone,
            chipRows=_zoneChipRows_build(
                debugContext=debugContext,
                routingZone=routingZone,
                chipMarkerMap=chipMarkerMap,
            ),
        )
    _interconnectRows_mutate(
        debugContext=debugContext,
        row=chipPortRow,
    )
    lines: list[str] = [
        f"    {''.join(topRow)}",
        f"    {''.join(coordRow)}",
        f"    {''.join(chipTopRow)}",
        f"    {''.join(chipBottomRow)}",
        f"    {''.join(chipPortRow)}",
        f"    {''.join(bottomRow)}",
    ]
    return lines


def _verticalRectangularTopologyBlockLines_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
    rowIndex: int,
) -> list[str]:
    """Build one row-grouped topology block for north-south rectangular worlds."""

    rowZones: list[RoutingZone] = _routingZonesForGridRow_build(
        debugContext=debugContext,
        rowIndex=rowIndex,
    )
    zoneLineSets: list[list[str]] = [
        _verticalZoneBoxLines_build(
            debugContext=debugContext,
            routingZone=routingZone,
            chipMarkerMap=chipMarkerMap,
        )
        for routingZone in rowZones
    ]
    lines: list[str] = []
    lineOffset: int
    for lineOffset in range(6):
        lines.append(
            "    " + " ".join(zoneLineSet[lineOffset] for zoneLineSet in zoneLineSets)
        )
    return lines


def _rectangularSeamLine_build(
    debugContext,
    rowIndex: int,
) -> str:
    """Build one seam line between adjacent rectangular grid rows."""

    rowZones: list[RoutingZone] = _routingZonesForGridRow_build(
        debugContext=debugContext,
        rowIndex=rowIndex,
    )
    if debugContext.placedRoutingZoneGrid.worldSense is RoutingZoneSense.NORTH_TO_SOUTH:
        seamSegments: list[str] = ["   ↓    " for _ in rowZones]
        return "    " + " ".join(seamSegments)

    width: int = max(
        routingZone.routingZoneFrame.horizontalEnd_calculate()
        for routingZone in rowZones
    )
    seamRow: list[str] = [" "] * max(width, 1)
    routingZone: RoutingZone
    for routingZone in rowZones:
        seamColumn: int = (
            routingZone.routingZoneFrame.horizontalStart
            + (routingZone.routingZoneFrame.horizontalSpan // 2)
        )
        if seamColumn < len(seamRow):
            seamRow[seamColumn] = "↓"
    handoffColumnIndex: int
    handoffGlyphByColumn = _routeHandoffGlyphByColumnForRowBoundary_build(
        debugContext=debugContext,
        rowIndex=rowIndex,
    )
    for handoffColumnIndex, handoffGlyph in handoffGlyphByColumn.items():
        if (
            0 <= handoffColumnIndex < len(seamRow)
        ):
            seamRow[handoffColumnIndex] = handoffGlyph
    return "    " + "".join(seamRow)


def _routingZonesForGridRow_build(
    debugContext,
    rowIndex: int,
) -> list[RoutingZone]:
    """Build the placed routing zones that live in one grid row."""

    rowZones: list[RoutingZone] = []
    routingZone: RoutingZone
    for routingZone in debugContext.zones_getAll():
        coordResult = routingZone.routingZoneId.worldGridCoordResult_get()
        assert result_isOkCheck(coordResult)
        if coordResult.value.rowIndex == rowIndex:
            rowZones.append(routingZone)
    rowZones.sort(
        key=lambda zone: zone.routingZoneId.worldGridCoordResult_get().unwrap().columnIndex
    )
    return rowZones


def _diagramVerticalBandForGridRow_build(
    debugContext,
    rowIndex: int,
) -> tuple[int, int]:
    """Build the vertical route band associated with one grid row."""

    rowZones: list[RoutingZone] = _routingZonesForGridRow_build(
        debugContext=debugContext,
        rowIndex=rowIndex,
    )
    bandStart: int = min(
        routingZone.routingZoneFrame.verticalStart for routingZone in rowZones
    )
    if rowIndex < debugContext.placedRoutingZoneGrid.gridSize.rowIndex:
        nextRowZones: list[RoutingZone] = _routingZonesForGridRow_build(
            debugContext=debugContext,
            rowIndex=rowIndex + 1,
        )
        nextBandStart: int = min(
            routingZone.routingZoneFrame.verticalStart
            for routingZone in nextRowZones
        )
        return (
            bandStart,
            nextBandStart - 1,
        )

    _, _, _, maxVerticalIndex = _worldPointState_build(debugContext=debugContext)
    return (bandStart, maxVerticalIndex)


def _routeHandoffGlyphByColumnForRowBoundary_build(
    debugContext,
    rowIndex: int,
) -> dict[int, str]:
    """Build seam-row glyphs for routes that continue across one row boundary."""

    routeMaskByPoint, _, maxHorizontalIndex, _ = _worldPointState_build(
        debugContext=debugContext,
    )
    currentBandStart, currentBandEnd = _diagramVerticalBandForGridRow_build(
        debugContext=debugContext,
        rowIndex=rowIndex,
    )
    nextBandStart, _ = _diagramVerticalBandForGridRow_build(
        debugContext=debugContext,
        rowIndex=rowIndex + 1,
    )
    handoffGlyphByColumn: dict[int, str] = {}
    horizontalIndex: int
    for horizontalIndex in range(maxHorizontalIndex + 1):
        upperMask: int = routeMaskByPoint.get((horizontalIndex, currentBandEnd), 0)
        lowerMask: int = routeMaskByPoint.get((horizontalIndex, nextBandStart), 0)
        if upperMask & _MASK_S or lowerMask & _MASK_N:
            upperPreviousMask: int = (
                routeMaskByPoint.get((horizontalIndex, currentBandEnd - 1), 0)
                if currentBandEnd > currentBandStart
                else 0
            )
            lowerNextMask: int = routeMaskByPoint.get(
                (horizontalIndex, nextBandStart + 1),
                0,
            )
            handoffMask: int = _routeHandoffMaskForBoundary_build(
                upperMask=upperMask,
                lowerMask=lowerMask,
                upperPreviousMask=upperPreviousMask,
                lowerNextMask=lowerNextMask,
            )
            handoffGlyphByColumn[horizontalIndex] = _GLYPH_BY_MASK.get(
                handoffMask,
                "│",
            )
    return handoffGlyphByColumn


def _routeHandoffMaskForBoundary_build(
    upperMask: int,
    lowerMask: int,
    upperPreviousMask: int,
    lowerNextMask: int,
) -> int:
    """Build the seam-row connection mask for one boundary handoff column."""

    horizontalMask: int = _MASK_E | _MASK_W
    upperHorizontalMask: int = upperPreviousMask & horizontalMask
    lowerHorizontalMask: int = (lowerMask | lowerNextMask) & horizontalMask
    if upperHorizontalMask and lowerHorizontalMask:
        return upperHorizontalMask | lowerHorizontalMask | _MASK_N | _MASK_S
    if upperHorizontalMask:
        return upperHorizontalMask | _MASK_S
    if lowerHorizontalMask:
        return lowerHorizontalMask | _MASK_N
    if upperMask & _MASK_S and lowerMask & _MASK_N:
        return _MASK_N | _MASK_S
    if upperMask & _MASK_S:
        return _MASK_N
    return _MASK_S


def _diagramFlowRowsForVerticalBand_build(
    debugContext,
    chipMarkerMap: dict[ChipId, str],
    gridRowIndex: int,
    verticalStartIndex: int,
    verticalEndIndex: int,
) -> list[tuple[str, str]]:
    """Build compact diagram flow rows for one vertical band."""

    connectorLines: list[str] = _flowConnectorLines_build(debugContext=debugContext)
    presentationLines: list[str] = _presentationLines_build(
        debugContext=debugContext,
        chipMarkerMap=chipMarkerMap,
    )
    compactRows = _compactDiagramFlowRows_build(
        connectorLines=connectorLines[verticalStartIndex : verticalEndIndex + 1],
        presentationLines=presentationLines[verticalStartIndex : verticalEndIndex + 1],
    )
    if gridRowIndex > 1:
        return _diagramFlowRowsWithIncomingHandoff_build(
            compactRows=compactRows,
            handoffColumns=tuple(
                _routeHandoffGlyphByColumnForRowBoundary_build(
                    debugContext=debugContext,
                    rowIndex=gridRowIndex - 1,
                ).keys()
            ),
        )
    return compactRows


def _diagramFlowRowsWithIncomingHandoff_build(
    compactRows: list[tuple[str, str]],
    handoffColumns: tuple[int, ...],
) -> list[tuple[str, str]]:
    """Build compact rows with incoming seam handoff stems on the first band row."""

    if not compactRows or not handoffColumns:
        return compactRows

    firstRowKind, firstRowText = compactRows[0]
    handoffLinkText: str = _rowTextWithVerticalColumns_build(
        rowText=firstRowText,
        columns=handoffColumns,
    )

    if firstRowKind == "link":
        updatedRows: list[tuple[str, str]] = list(compactRows)
        updatedRows[0] = ("link", _rowsMerged_build(firstRowText, handoffLinkText))
        return updatedRows

    return compactRows


def _rowTextWithVerticalColumns_build(
    rowText: str,
    columns: tuple[int, ...],
) -> str:
    """Build one row text populated with vertical stems at given world columns."""

    rowCharacters: list[str] = list(rowText)
    rowLength: int = len(rowCharacters)
    columnIndex: int
    for columnIndex in columns:
        characterIndex: int = 4 + (columnIndex * 3) + 1
        if characterIndex >= rowLength:
            rowCharacters.extend([" "] * (characterIndex - rowLength + 1))
            rowLength = len(rowCharacters)
        rowCharacters[characterIndex] = "│"
    return "".join(rowCharacters).rstrip()


def _rowsMerged_build(
    baseRowText: str,
    overlayRowText: str,
) -> str:
    """Build one row text by overlaying non-space characters from a second row."""

    rowLength: int = max(len(baseRowText), len(overlayRowText))
    mergedCharacters: list[str] = []
    index: int
    for index in range(rowLength):
        overlayCharacter: str = (
            overlayRowText[index] if index < len(overlayRowText) else " "
        )
        if overlayCharacter != " ":
            mergedCharacters.append(overlayCharacter)
            continue
        mergedCharacters.append(
            baseRowText[index] if index < len(baseRowText) else " "
        )
    return "".join(mergedCharacters).rstrip()


def _verticalZoneBoxLines_build(
    debugContext,
    routingZone: RoutingZone,
    chipMarkerMap: dict[ChipId, str],
) -> list[str]:
    """Build one readable vertical-world zone box with stable presentation width."""

    interiorWidth: int = 6
    label: str = _zoneLabel_build(routingZone).center(interiorWidth)[:interiorWidth]
    chipRows: tuple[str, str, str] = _zoneChipRows_build(
        debugContext=debugContext,
        routingZone=routingZone,
        chipMarkerMap=chipMarkerMap,
    )
    return [
        f"╔{'═' * interiorWidth}╗",
        f"║{label}║",
        f"║{chipRows[0].ljust(interiorWidth)[:interiorWidth]}║",
        f"║{chipRows[1].ljust(interiorWidth)[:interiorWidth]}║",
        f"║{chipRows[2].ljust(interiorWidth)[:interiorWidth]}║",
        f"╚{'═' * interiorWidth}╝",
    ]


def _zoneBoxRows_mutate(
    topRow: list[str],
    coordRow: list[str],
    chipTopRow: list[str],
    chipBottomRow: list[str],
    chipPortRow: list[str],
    bottomRow: list[str],
    routingZone: RoutingZone,
    chipRows: tuple[str, str, str],
) -> None:
    """Mutate topology rows with one rendered routing-zone box."""

    startIndex: int = routingZone.routingZoneFrame.horizontalStart
    endIndex: int = routingZone.routingZoneFrame.horizontalEnd_calculate() - 1
    interiorStartIndex: int = startIndex + 1
    interiorEndIndex: int = endIndex - 1
    horizontalIndex: int
    for horizontalIndex in range(startIndex + 1, endIndex):
        topRow[horizontalIndex] = "═"
        bottomRow[horizontalIndex] = "═"
    topRow[startIndex] = "╔"
    topRow[endIndex] = "╗"
    bottomRow[startIndex] = "╚"
    bottomRow[endIndex] = "╝"
    coordRow[startIndex] = "║"
    coordRow[endIndex] = "║"
    chipTopRow[startIndex] = "║"
    chipTopRow[endIndex] = "║"
    chipBottomRow[startIndex] = "║"
    chipBottomRow[endIndex] = "║"
    chipPortRow[startIndex] = "║"
    chipPortRow[endIndex] = "║"
    label: str = _zoneLabel_build(routingZone)
    labelWidth: int = max(interiorEndIndex - interiorStartIndex + 1, 0)
    labelText: str = label.center(labelWidth)[:labelWidth]
    labelIndex: int
    for labelIndex, character in enumerate(labelText):
        coordRow[interiorStartIndex + labelIndex] = character
    chipTopText: str = chipRows[0].ljust(labelWidth)[:labelWidth]
    chipBottomText: str = chipRows[1].ljust(labelWidth)[:labelWidth]
    chipPortText: str = chipRows[2].ljust(labelWidth)[:labelWidth]
    for labelIndex, character in enumerate(chipTopText):
        chipTopRow[interiorStartIndex + labelIndex] = character
    for labelIndex, character in enumerate(chipBottomText):
        chipBottomRow[interiorStartIndex + labelIndex] = character
    for labelIndex, character in enumerate(chipPortText):
        chipPortRow[interiorStartIndex + labelIndex] = character


def _zoneLabel_build(routingZone: RoutingZone) -> str:
    """Build a compact label for one routing zone."""

    worldGridCoordResult = routingZone.routingZoneId.worldGridCoordResult_get()
    assert result_isOkCheck(worldGridCoordResult)
    return (
        f"[{worldGridCoordResult.value.columnIndex},"
        f"{worldGridCoordResult.value.rowIndex}]"
    )


def _zoneChipRows_build(
    debugContext,
    routingZone: RoutingZone,
    chipMarkerMap: dict[ChipId, str],
) -> tuple[str, str, str]:
    """Build compact chip-body and port rows for one routing zone."""

    slotCount: int = 2
    topSlots: list[str] = ["   "] * slotCount
    bottomSlots: list[str] = ["   "] * slotCount
    portSlots: list[str] = ["   "] * slotCount
    westMarkers: list[str] = []
    eastMarkers: list[str] = []
    northMarkers: list[str] = []
    southMarkers: list[str] = []
    portTextByMarker: dict[str, str] = {}
    chipPlacement: ChipPlacement
    for chipPlacement in routingZone.chipPlacementSet.placements:
        marker = chipMarkerMap[chipPlacement.chipRef.chipId]
        chipResult = debugContext.circuitDocument.circuitChipSet.chipResult_get(
            chipPlacement.chipRef.chipId
        )
        assert result_isOkCheck(chipResult)
        portTextByMarker[marker] = _chipPortFaceText_build(chipResult.value)
        side = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
        if side is RoutingZoneRegionSide.WEST:
            westMarkers.append(marker)
        elif side is RoutingZoneRegionSide.EAST:
            eastMarkers.append(marker)
        elif side is RoutingZoneRegionSide.NORTH:
            northMarkers.append(marker)
        elif side is RoutingZoneRegionSide.SOUTH:
            southMarkers.append(marker)
    if routingZone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        _chipSlots_mutate(
            slots=topSlots,
            markers=tuple(westMarkers),
            leftToRight=True,
            slotTextByMarker=portTextByMarker,
            portSlots=portSlots,
        )
        _chipSlots_mutate(
            slots=topSlots,
            markers=tuple(eastMarkers),
            leftToRight=False,
            slotTextByMarker=portTextByMarker,
            portSlots=portSlots,
        )
    else:
        _chipSlots_mutate(
            slots=topSlots,
            markers=tuple(northMarkers),
            leftToRight=True,
            slotTextByMarker=portTextByMarker,
            portSlots=portSlots,
        )
        _chipSlots_mutate(
            slots=topSlots,
            markers=tuple(southMarkers),
            leftToRight=False,
            slotTextByMarker=portTextByMarker,
            portSlots=portSlots,
        )
    slotIndex: int
    for slotIndex, slot in enumerate(topSlots):
        if slot != "   ":
            bottomSlots[slotIndex] = "└─┘"
    return ("".join(topSlots), "".join(bottomSlots), "".join(portSlots))


def _chipSlots_mutate(
    slots: list[str],
    markers: tuple[str, ...],
    leftToRight: bool,
    slotTextByMarker: dict[str, str],
    portSlots: list[str],
) -> None:
    """Mutate slot list with compact chip bodies."""

    if not markers:
        return
    availableIndices: list[int]
    if leftToRight:
        availableIndices = [
            index for index, slot in enumerate(slots)
            if slot == "   "
        ]
    else:
        availableIndices = [
            index for index, slot in reversed(tuple(enumerate(slots)))
            if slot == "   "
        ]
    markerIndex: int
    for markerIndex, marker in enumerate(markers[: len(availableIndices)]):
        slotIndex = availableIndices[markerIndex]
        slots[slotIndex] = f"┌{marker}┐"
        portSlots[slotIndex] = slotTextByMarker[marker]
    if len(markers) > len(availableIndices):
        overflowIndex: int = (
            availableIndices[-1]
            if availableIndices
            else (len(slots) - 1 if leftToRight else 0)
        )
        slots[overflowIndex] = "┌+┐"
        portSlots[overflowIndex] = "···"


def _chipPortFaceText_build(chip) -> str:
    """Build compact face/port text for one chip body."""

    hasInputs: bool = bool(chip.inputPortDeclarationSet.portDeclarations)
    hasOutputs: bool = bool(chip.outputPortDeclarationSet.portDeclarations)
    leftText: str = "◄" if hasInputs else " "
    rightText: str = "►" if hasOutputs else " "
    return f"{leftText}•{rightText}"


def _interconnectRows_mutate(
    debugContext,
    row: list[str],
) -> None:
    """Mutate topology placement row with directional interconnect arrows."""

    interconnect = None
    for interconnect in debugContext.interconnects_getAll():
        axisResult = interconnect.interconnectAxisResult_get()
        if not result_isOkCheck(axisResult):
            continue
        if axisResult.value.value == "horizontal":
            sourceCoordResult = interconnect.sourceZoneId.worldGridCoordResult_get()
            destinationCoordResult = (
                interconnect.destinationZoneId.worldGridCoordResult_get()
            )
            if not (
                result_isOkCheck(sourceCoordResult)
                and result_isOkCheck(destinationCoordResult)
            ):
                continue
            arrowCharacter: str = (
                "→"
                if sourceCoordResult.value.columnIndex
                < destinationCoordResult.value.columnIndex
                else "←"
            )
            row[interconnect.routingZoneInterconnectFrame.horizontalStart] = (
                arrowCharacter
            )


def _routeMaskByPoint_mutateForRoute(
    routeMaskByPoint: dict[tuple[int, int], int],
    routePoints: tuple[RoutingZoneRoutePoint, ...],
) -> None:
    """Mutate route-mask table for one solved polyline."""

    pointIndex: int
    for pointIndex in range(len(routePoints) - 1):
        startPoint = routePoints[pointIndex]
        endPoint = routePoints[pointIndex + 1]
        segmentPoints: tuple[tuple[int, int], ...] = _segmentPoints_build(
            startPoint=startPoint,
            endPoint=endPoint,
        )
        segmentIndex: int
        for segmentIndex in range(len(segmentPoints) - 1):
            startKey = segmentPoints[segmentIndex]
            endKey = segmentPoints[segmentIndex + 1]
            startMask, endMask = _segmentMasks_build(startKey=startKey, endKey=endKey)
            routeMaskByPoint[startKey] = routeMaskByPoint.get(startKey, 0) | startMask
            routeMaskByPoint[endKey] = routeMaskByPoint.get(endKey, 0) | endMask


def _segmentPoints_build(
    startPoint: RoutingZoneRoutePoint,
    endPoint: RoutingZoneRoutePoint,
) -> tuple[tuple[int, int], ...]:
    """Build discrete cell sequence for one orthogonal segment."""

    if startPoint.horizontalIndex == endPoint.horizontalIndex:
        step: int = 1 if endPoint.verticalIndex >= startPoint.verticalIndex else -1
        return tuple(
            (startPoint.horizontalIndex, verticalIndex)
            for verticalIndex in range(
                startPoint.verticalIndex,
                endPoint.verticalIndex + step,
                step,
            )
        )
    step = 1 if endPoint.horizontalIndex >= startPoint.horizontalIndex else -1
    return tuple(
        (horizontalIndex, startPoint.verticalIndex)
        for horizontalIndex in range(
            startPoint.horizontalIndex,
            endPoint.horizontalIndex + step,
            step,
        )
    )


def _segmentMasks_build(
    startKey: tuple[int, int],
    endKey: tuple[int, int],
) -> tuple[int, int]:
    """Build direction masks for one adjacent segment step."""

    horizontalDelta: int = endKey[0] - startKey[0]
    verticalDelta: int = endKey[1] - startKey[1]
    if horizontalDelta == 1:
        return (_MASK_E, _MASK_W)
    if horizontalDelta == -1:
        return (_MASK_W, _MASK_E)
    if verticalDelta == 1:
        return (_MASK_S, _MASK_N)
    return (_MASK_N, _MASK_S)


def _chipPlacementPoint_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> tuple[int, int]:
    """Build world-coordinate marker point for one placed chip."""

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


def _worldPointState_build(
    debugContext,
) -> tuple[
    dict[tuple[int, int], int],
    dict[tuple[int, int], ChipId],
    int,
    int,
]:
    """Build combined route and chip-point state for world projection."""

    routeMaskByPoint: dict[tuple[int, int], int] = {}
    routePointSequence: tuple[tuple[RoutingZoneRoutePoint, ...], ...] = (
        tuple(
            solvedRoute.routePoints
            for solvedRoute in (
                debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
            )
        )
        + tuple(
            solvedRoute.routePoints
            for solvedRoute in (
                debugContext.routingZoneInterconnectSolvedRouteSet
                .routingZoneInterconnectSolvedRoutes
            )
        )
        + tuple(
            solvedRoute.routePoints
            for solvedRoute in (
                debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
            )
        )
    )
    routePoints: tuple[RoutingZoneRoutePoint, ...]
    for routePoints in routePointSequence:
        _routeMaskByPoint_mutateForRoute(
            routeMaskByPoint=routeMaskByPoint,
            routePoints=routePoints,
        )

    chipIdByPoint: dict[tuple[int, int], ChipId] = {}
    routingZone: RoutingZone
    for routingZone in debugContext.zones_getAll():
        chipPlacement: ChipPlacement
        for chipPlacement in routingZone.chipPlacementSet.placements:
            markerPoint = _chipPlacementPoint_build(
                routingZone=routingZone,
                chipPlacement=chipPlacement,
            )
            chipIdByPoint[markerPoint] = chipPlacement.chipRef.chipId

    maxHorizontalIndex: int = 0
    maxVerticalIndex: int = 0
    point: tuple[int, int]
    for point in tuple(routeMaskByPoint) + tuple(chipIdByPoint):
        maxHorizontalIndex = max(maxHorizontalIndex, point[0])
        maxVerticalIndex = max(maxVerticalIndex, point[1])
    maxHorizontalIndex = max(
        maxHorizontalIndex,
        max(
            routingZone.routingZoneFrame.horizontalEnd_calculate() - 1
            for routingZone in debugContext.zones_getAll()
        ),
    )
    maxVerticalIndex = max(
        maxVerticalIndex,
        max(
            routingZone.routingZoneFrame.verticalEnd_calculate() - 1
            for routingZone in debugContext.zones_getAll()
        ),
    )
    if debugContext.interconnects_getAll():
        maxHorizontalIndex = max(
            maxHorizontalIndex,
            max(
                (
                    interconnect.routingZoneInterconnectFrame.horizontalStart
                    + interconnect.routingZoneInterconnectFrame.horizontalSpan
                    - 1
                )
                for interconnect in debugContext.interconnects_getAll()
            ),
        )
        maxVerticalIndex = max(
            maxVerticalIndex,
            max(
                (
                    interconnect.routingZoneInterconnectFrame.verticalStart
                    + interconnect.routingZoneInterconnectFrame.verticalSpan
                    - 1
                )
                for interconnect in debugContext.interconnects_getAll()
            ),
        )
    return (routeMaskByPoint, chipIdByPoint, maxHorizontalIndex, maxVerticalIndex)


def _chipFaceBodyText_build(
    debugContext,
    chipId: ChipId,
    chipMarker: str,
) -> str:
    """Build one three-character chip body for the presentation canvas."""

    chipResult = debugContext.circuitDocument.circuitChipSet.chipResult_get(chipId)
    assert result_isOkCheck(chipResult)
    hasInputs: bool = bool(chipResult.value.inputPortDeclarationSet.portDeclarations)
    hasOutputs: bool = bool(chipResult.value.outputPortDeclarationSet.portDeclarations)
    leftText: str = "◄" if hasInputs else " "
    rightText: str = "►" if hasOutputs else " "
    return f"{leftText}{chipMarker}{rightText}"


def _chipContactBodyText_build(
    chipMarker: str,
    routeMask: int,
) -> str:
    """Build one three-character chip body from solved route contact."""

    if routeMask & (_MASK_W | _MASK_E):
        leftText: str = "◄" if routeMask & _MASK_W else " "
        rightText: str = "►" if routeMask & _MASK_E else " "
        return f"{leftText}{chipMarker}{rightText}"

    if routeMask & (_MASK_N | _MASK_S):
        leftText = "▲" if routeMask & _MASK_N else " "
        rightText = "▼" if routeMask & _MASK_S else " "
        return f"{leftText}{chipMarker}{rightText}"

    return f" {chipMarker} "


def _routeCellText_build(routeMask: int) -> str:
    """Build one expanded route cell for the presentation canvas."""

    if routeMask == 0:
        return "   "
    horizontalPresent: bool = bool(routeMask & (_MASK_E | _MASK_W))
    verticalPresent: bool = bool(routeMask & (_MASK_N | _MASK_S))
    if horizontalPresent and not verticalPresent:
        return "───"
    if verticalPresent and not horizontalPresent:
        return " │ "
    return f"─{_GLYPH_BY_MASK.get(routeMask, '┼')}─"


def _worldRouteLines_build(debugContext) -> list[str]:
    """Build readable summary lines for solved world routes."""

    lines: list[str] = []

    localLines: tuple[str, ...] = tuple(
        _routeSummaryLine_build(
            prefix="local",
            sourceFunctionName=solvedRoute.sourceChipRef.chipId.functionName,
            destinationFunctionName=(
                solvedRoute.destinationChipRef.chipId.functionName
            ),
            solveKindValue=solvedRoute.solveKind.value,
        )
        for solvedRoute in (
            debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        )
    )
    seamLines: tuple[str, ...] = tuple(
        _routeSummaryLine_build(
            prefix="seam",
            sourceFunctionName=solvedRoute.sourceChipRef.chipId.functionName,
            destinationFunctionName=(
                solvedRoute.destinationChipRef.chipId.functionName
            ),
            solveKindValue=solvedRoute.solveKind.value,
        )
        for solvedRoute in (
            debugContext.routingZoneInterconnectSolvedRouteSet
            .routingZoneInterconnectSolvedRoutes
        )
    )
    gridLines: tuple[str, ...] = tuple(
        _routeSummaryLine_build(
            prefix="grid",
            sourceFunctionName=solvedRoute.sourceChipRef.chipId.functionName,
            destinationFunctionName=(
                solvedRoute.destinationChipRef.chipId.functionName
            ),
            solveKindValue=solvedRoute.solveKind.value,
        )
        for solvedRoute in (
            debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
        )
    )

    combinedLines: tuple[str, ...] = localLines + seamLines + gridLines
    if not combinedLines:
        return ["  <none>"]
    lines.extend(f"  {line}" for line in combinedLines)
    return lines


def _routeSummaryLine_build(
    prefix: str,
    sourceFunctionName: str,
    destinationFunctionName: str,
    solveKindValue: str,
) -> str:
    """Build one compact route-summary line."""

    return (
        f"{prefix} "
        f"{sourceFunctionName}->{destinationFunctionName} "
        f"[{solveKindValue}]"
    )


def _chipInternalLines_build(debugContext) -> list[str]:
    """Build readable chip-internal route summary lines."""

    lines: list[str] = []
    chipId: ChipId
    for chipId in debugContext.chipIds_getAll():
        solvedRoutes = debugContext.chipRoutesForChip_get(chipId)
        if not solvedRoutes:
            lines.append(f"  {chipId.moduleName}:{chipId.functionName}: <none>")
            continue
        routeSummary: str = ", ".join(
            (
                f"{solvedRoute.chipInternalRouteDirectiveSpec.sourceTerminalName}->"
                f"{solvedRoute.chipInternalRouteDirectiveSpec.destinationTerminalName}"
                f"[{solvedRoute.solveKind.value}]"
            )
            for solvedRoute in solvedRoutes
        )
        lines.append(
            f"  {chipId.moduleName}:{chipId.functionName}: {routeSummary}"
        )
    return lines


def diagram_render(
    title: str,
    treeDict: dict[str, object],
    engineName: EngineName = EngineName.NEW,
) -> list[str]:
    """Render one document through the selected engine path."""

    if engineName is EngineName.LEGACY:
        return diagramLegacy_render(title, treeDict)
    return worldDiagram_lprint(title, treeDict)
