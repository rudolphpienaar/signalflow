"""Logical placement planning for assigned routing-zone worlds.

This module turns a chip-to-zone assignment set into a logically placed
`RoutingZoneGrid`. The output is not final render geometry. It is an explicit
planning geometry that gives each zone:

- a stable outer frame in world coordinates
- explicit owned region geometry
- ordered chip placements in terminal regions

The current implementation now supports rectangular worlds by sizing each row
and column from the assigned zones and then placing inter-zone seams between
those row/column bands.
"""
from __future__ import annotations

from signalflow.models import (
    ChipPlacement,
    ChipPlacementSet,
    GridCoord,
    Result,
    RoutingZone,
    RoutingZoneAssignmentSet,
    RoutingZoneChannelSense,
    RoutingZoneFrame,
    RoutingZoneGrid,
    RoutingZoneId,
    RoutingZoneInterconnect,
    RoutingZoneInterconnectFrame,
    RoutingZoneInterconnectSet,
    RoutingZoneRegion,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSet,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    RoutingZoneSet,
    chipDrawLines_build,
    chipPlacementSetResult_build,
    result_isOkCheck,
    resultErr_build,
    routingZoneFrameResult_build,
    routingZoneGridResult_build,
    routingZoneInterconnectFrameResult_build,
    routingZoneInterconnectSetResult_build,
    routingZoneRegionFrameResult_build,
    routingZoneRegionResult_build,
    routingZoneRegionSetResult_build,
    routingZoneResult_build,
    routingZoneSetResult_build,
)
from signalflow.models.circuit import CircuitDocument

_TERMINAL_SPAN: int = 1
_FAN_IN_OUT_SPAN: int = 1
_CHANNEL_SPAN: int = 1
_INTERCONNECT_SPAN: int = 1
_CROSSBAR_SPAN_MIN: int = 10


def routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    routingZoneGrid: RoutingZoneGrid,
    circuitDocument: CircuitDocument,
) -> Result[RoutingZoneGrid]:
    """Build logically placed routing-zone world from assignments and topology."""

    zoneMetricsById: dict[RoutingZoneId, dict[str, int]] = _zoneMetricsById_build(
        routingZoneGrid=routingZoneGrid,
        routingZoneAssignmentSet=routingZoneAssignmentSet,
        circuitDocument=circuitDocument,
    )
    columnWidthByIndex: dict[int, int] = _columnWidthByIndex_build(
        routingZoneGrid=routingZoneGrid,
        zoneMetricsById=zoneMetricsById,
    )
    rowHeightByIndex: dict[int, int] = _rowHeightByIndex_build(
        routingZoneGrid=routingZoneGrid,
        zoneMetricsById=zoneMetricsById,
    )
    columnStartByIndex: dict[int, int] = _columnStartByIndex_build(
        routingZoneGrid=routingZoneGrid,
        columnWidthByIndex=columnWidthByIndex,
    )
    rowStartByIndex: dict[int, int] = _rowStartByIndex_build(
        routingZoneGrid=routingZoneGrid,
        rowHeightByIndex=rowHeightByIndex,
    )

    routingZonesMutable: list[RoutingZone] = []
    rowIndex: int
    columnIndex: int
    for rowIndex in range(1, routingZoneGrid.gridSize.rowIndex + 1):
        for columnIndex in range(1, routingZoneGrid.gridSize.columnIndex + 1):
            routingZoneId: RoutingZoneId = RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            )
            originalZoneResult: Result[RoutingZone] = (
                routingZoneGrid.routingZoneSet.zoneResult_get(routingZoneId)
            )
            if not result_isOkCheck(originalZoneResult):
                return resultErr_build()
            zoneMetrics: dict[str, int] = zoneMetricsById[routingZoneId]
            plannedZoneResult: Result[RoutingZone] = _plannedRoutingZoneResult_build(
                routingZoneId=routingZoneId,
                routingZoneSense=routingZoneGrid.worldSense,
                channelSenseForZone=originalZoneResult.value.channelSense,
                routingZoneAssignmentSet=routingZoneAssignmentSet,
                horizontalStart=columnStartByIndex[columnIndex],
                verticalStart=rowStartByIndex[rowIndex],
                zoneHorizontalSpan=columnWidthByIndex[columnIndex],
                zoneVerticalSpan=rowHeightByIndex[rowIndex],
                startTerminalDim=zoneMetrics["startTerminalDim"],
                endTerminalDim=zoneMetrics["endTerminalDim"],
                crossbarDim=zoneMetrics["crossbarDim"],
            )
            if not result_isOkCheck(plannedZoneResult):
                return resultErr_build()
            routingZonesMutable.append(plannedZoneResult.value)

    routingZoneSetResult: Result[RoutingZoneSet] = routingZoneSetResult_build(
        routingZones=tuple(routingZonesMutable)
    )
    if not result_isOkCheck(routingZoneSetResult):
        return resultErr_build()

    routingZoneInterconnectSetResult: Result[RoutingZoneInterconnectSet] = (
        _plannedInterconnectSetResult_build(
            originalRoutingZoneGrid=routingZoneGrid,
            plannedRoutingZoneSet=routingZoneSetResult.value,
        )
    )
    if not result_isOkCheck(routingZoneInterconnectSetResult):
        return resultErr_build()

    return routingZoneGridResult_build(
        worldSense=routingZoneGrid.worldSense,
        gridSize=routingZoneGrid.gridSize,
        routingZoneSet=routingZoneSetResult.value,
        routingZoneInterconnectSet=routingZoneInterconnectSetResult.value,
    )


def _plannedRoutingZoneResult_build(
    routingZoneId: RoutingZoneId,
    routingZoneSense: RoutingZoneSense,
    channelSenseForZone: RoutingZoneChannelSense,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    horizontalStart: int,
    verticalStart: int,
    zoneHorizontalSpan: int,
    zoneVerticalSpan: int,
    startTerminalDim: int,
    endTerminalDim: int,
    crossbarDim: int,
) -> Result[RoutingZone]:
    """Build one logically placed routing zone from assignments."""

    chipPlacementSetResult = _chipPlacementSetResult_buildForZone(
        routingZoneId=routingZoneId,
        routingZoneAssignmentSet=routingZoneAssignmentSet,
    )
    if not result_isOkCheck(chipPlacementSetResult):
        return resultErr_build()

    routingZoneFrameResult: Result[RoutingZoneFrame] = routingZoneFrameResult_build(
        horizontalStart=horizontalStart,
        verticalStart=verticalStart,
        horizontalSpan=zoneHorizontalSpan,
        verticalSpan=zoneVerticalSpan,
    )
    if not result_isOkCheck(routingZoneFrameResult):
        return resultErr_build()

    routingZoneRegionSetResult: Result[RoutingZoneRegionSet] = (
        _routingZoneRegionSetResult_buildForZone(
            routingZoneId=routingZoneId,
            routingZoneSense=routingZoneSense,
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            zoneHorizontalSpan=zoneHorizontalSpan,
            zoneVerticalSpan=zoneVerticalSpan,
            startTerminalDim=startTerminalDim,
            endTerminalDim=endTerminalDim,
            crossbarDim=crossbarDim,
        )
    )
    if not result_isOkCheck(routingZoneRegionSetResult):
        return resultErr_build()

    return routingZoneResult_build(
        routingZoneId=routingZoneId,
        routingZoneSense=routingZoneSense,
        channelSense=channelSenseForZone,
        routingZoneFrame=routingZoneFrameResult.value,
        routingZoneRegionSet=routingZoneRegionSetResult.value,
        chipPlacementSet=chipPlacementSetResult.value,
    )


def _chipPlacementSetResult_buildForZone(
    routingZoneId: RoutingZoneId,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
) -> Result[ChipPlacementSet]:
    """Build ordered chip placements for one zone."""

    placementsMutable: list[ChipPlacement] = []
    sideOrderCounters: dict[RoutingZoneRegionSide, int] = {}
    routingZoneAssignment = None
    for routingZoneAssignment in routingZoneAssignmentSet.assignmentsForZone_get(
        routingZoneId
    ):
        sideOrderIndex: int = sideOrderCounters.get(
            routingZoneAssignment.terminalSide,
            0,
        )
        sideOrderCounters[routingZoneAssignment.terminalSide] = sideOrderIndex + 1
        placementsMutable.append(
            ChipPlacement(
                chipRef=routingZoneAssignment.chipRef,
                chipTerminalRegionId=RoutingZoneRegionId(
                    routingZoneId=routingZoneId,
                    routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
                    routingZoneRegionSide=routingZoneAssignment.terminalSide,
                ),
                orderIndex=sideOrderIndex,
            )
        )
    return chipPlacementSetResult_build(placements=tuple(placementsMutable))


def _zoneMetrics_build(
    routingZoneId: RoutingZoneId,
    routingZoneSense: RoutingZoneSense,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    circuitDocument: CircuitDocument,
) -> dict[str, int]:
    """Build chip-geometry-driven sizing metrics for one zone."""

    startSide: RoutingZoneRegionSide
    endSide: RoutingZoneRegionSide
    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        startSide = RoutingZoneRegionSide.WEST
        endSide = RoutingZoneRegionSide.EAST
    else:
        startSide = RoutingZoneRegionSide.NORTH
        endSide = RoutingZoneRegionSide.SOUTH

    startAssignments = routingZoneAssignmentSet.assignmentsForZoneAndSide_get(
        routingZoneId,
        startSide,
    )
    endAssignments = routingZoneAssignmentSet.assignmentsForZoneAndSide_get(
        routingZoneId,
        endSide,
    )

    def _chipDims_get(assignments: object) -> tuple[list[int], list[int]]:
        """Return (heights, widths) lists for a sequence of assignments."""
        heights: list[int] = []
        widths: list[int] = []
        for assignment in assignments:
            chipResult = circuitDocument.circuitChipSet.chipResult_get(
                assignment.chipRef.chipId
            )
            if not result_isOkCheck(chipResult):
                continue
            lines = chipDrawLines_build(chipResult.value)
            heights.append(len(lines))
            widths.append(max((len(line) for line in lines), default=1))
        return heights, widths

    startHeights, startWidths = _chipDims_get(startAssignments)
    endHeights, endWidths = _chipDims_get(endAssignments)

    startCount: int = len(startHeights)
    endCount: int = len(endHeights)
    crossbarDim: int = max(_CROSSBAR_SPAN_MIN, startCount, endCount)

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        westTerminalWidth: int = max(startWidths, default=1)
        eastTerminalWidth: int = max(endWidths, default=1)
        chipStackHeight: int = max(sum(startHeights), sum(endHeights), 1)
        zoneVerticalSpan: int = 10 + chipStackHeight
        zoneHorizontalSpan: int = westTerminalWidth + 8 + crossbarDim + eastTerminalWidth
        return {
            "zoneHorizontalSpan": zoneHorizontalSpan,
            "zoneVerticalSpan": zoneVerticalSpan,
            "startTerminalDim": westTerminalWidth,
            "endTerminalDim": eastTerminalWidth,
            "crossbarDim": crossbarDim,
        }

    northTerminalHeight: int = max(sum(startHeights), 1)
    southTerminalHeight: int = max(sum(endHeights), 1)
    chipWidth: int = max(
        max(startWidths, default=1),
        max(endWidths, default=1),
        1,
    )
    zoneHorizontalSpanNS: int = chipWidth + 10
    zoneVerticalSpanNS: int = northTerminalHeight + 8 + crossbarDim + southTerminalHeight
    return {
        "zoneHorizontalSpan": zoneHorizontalSpanNS,
        "zoneVerticalSpan": zoneVerticalSpanNS,
        "startTerminalDim": northTerminalHeight,
        "endTerminalDim": southTerminalHeight,
        "crossbarDim": crossbarDim,
    }


def _zoneMetricsById_build(
    routingZoneGrid: RoutingZoneGrid,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    circuitDocument: CircuitDocument,
) -> dict[RoutingZoneId, dict[str, int]]:
    """Build logical sizing metrics for every zone in the world."""

    metricsById: dict[RoutingZoneId, dict[str, int]] = {}
    routingZone: RoutingZone
    for routingZone in routingZoneGrid.routingZoneSet.routingZones:
        metricsById[routingZone.routingZoneId] = _zoneMetrics_build(
            routingZoneId=routingZone.routingZoneId,
            routingZoneSense=routingZone.routingZoneSense,
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            circuitDocument=circuitDocument,
        )
    return metricsById


def _columnWidthByIndex_build(
    routingZoneGrid: RoutingZoneGrid,
    zoneMetricsById: dict[RoutingZoneId, dict[str, int]],
) -> dict[int, int]:
    """Build maximum display/planning width per grid column."""

    widthByIndex: dict[int, int] = {}
    columnIndex: int
    for columnIndex in range(1, routingZoneGrid.gridSize.columnIndex + 1):
        widthByIndex[columnIndex] = max(
            zoneMetricsById[
                RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
            ]["zoneHorizontalSpan"]
            for rowIndex in range(1, routingZoneGrid.gridSize.rowIndex + 1)
        )
    return widthByIndex


def _rowHeightByIndex_build(
    routingZoneGrid: RoutingZoneGrid,
    zoneMetricsById: dict[RoutingZoneId, dict[str, int]],
) -> dict[int, int]:
    """Build maximum display/planning height per grid row."""

    heightByIndex: dict[int, int] = {}
    rowIndex: int
    for rowIndex in range(1, routingZoneGrid.gridSize.rowIndex + 1):
        heightByIndex[rowIndex] = max(
            zoneMetricsById[
                RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
            ]["zoneVerticalSpan"]
            for columnIndex in range(1, routingZoneGrid.gridSize.columnIndex + 1)
        )
    return heightByIndex


def _columnStartByIndex_build(
    routingZoneGrid: RoutingZoneGrid,
    columnWidthByIndex: dict[int, int],
) -> dict[int, int]:
    """Build world horizontal start coordinate per grid column."""

    startByIndex: dict[int, int] = {}
    cursor: int = 0
    columnIndex: int
    for columnIndex in range(1, routingZoneGrid.gridSize.columnIndex + 1):
        startByIndex[columnIndex] = cursor
        cursor += columnWidthByIndex[columnIndex]
        if columnIndex < routingZoneGrid.gridSize.columnIndex:
            cursor += _INTERCONNECT_SPAN
    return startByIndex


def _rowStartByIndex_build(
    routingZoneGrid: RoutingZoneGrid,
    rowHeightByIndex: dict[int, int],
) -> dict[int, int]:
    """Build world vertical start coordinate per grid row."""

    startByIndex: dict[int, int] = {}
    cursor: int = 0
    rowIndex: int
    for rowIndex in range(1, routingZoneGrid.gridSize.rowIndex + 1):
        startByIndex[rowIndex] = cursor
        cursor += rowHeightByIndex[rowIndex]
        if rowIndex < routingZoneGrid.gridSize.rowIndex:
            cursor += _INTERCONNECT_SPAN
    return startByIndex


def _routingZoneRegionSetResult_buildForZone(
    routingZoneId: RoutingZoneId,
    routingZoneSense: RoutingZoneSense,
    horizontalStart: int,
    verticalStart: int,
    zoneHorizontalSpan: int,
    zoneVerticalSpan: int,
    startTerminalDim: int,
    endTerminalDim: int,
    crossbarDim: int,
) -> Result[RoutingZoneRegionSet]:
    """Build logical explicit region geometry for one planned zone."""

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return _westEastRegionSetResult_buildForZone(
            routingZoneId=routingZoneId,
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            zoneHorizontalSpan=zoneHorizontalSpan,
            zoneVerticalSpan=zoneVerticalSpan,
            westTerminalWidth=startTerminalDim,
            eastTerminalWidth=endTerminalDim,
            crossbarWidth=crossbarDim,
        )
    return _northSouthRegionSetResult_buildForZone(
        routingZoneId=routingZoneId,
        horizontalStart=horizontalStart,
        verticalStart=verticalStart,
        zoneHorizontalSpan=zoneHorizontalSpan,
        zoneVerticalSpan=zoneVerticalSpan,
        northTerminalHeight=startTerminalDim,
        southTerminalHeight=endTerminalDim,
        crossbarHeight=crossbarDim,
    )


def _westEastRegionSetResult_buildForZone(
    routingZoneId: RoutingZoneId,
    horizontalStart: int,
    verticalStart: int,
    zoneHorizontalSpan: int,
    zoneVerticalSpan: int,
    westTerminalWidth: int,
    eastTerminalWidth: int,
    crossbarWidth: int,
) -> Result[RoutingZoneRegionSet]:
    """Build logical west-to-east region set for one planned zone.

    Implements the canonical 20-band concentric zone geometry.  Bands are
    ordered outside-in on every side: inter_routing → inter_fan → chip_terminal
    → intra_fan → intra_routing.  All regions carry a cardinal side qualifier.

    Horizontal layout (left→right, W=westTerminalWidth, E=eastTerminalWidth,
                       K=crossbarWidth):
      col 0            : West/inter_routing_longitude   ← full height (inter-zone pillar)
      col 1            : West/inter_routing_fan_in_out  ┐
      cols 2..1+W      : West/chip_terminal              │ crossbar rows only
      col 2+W          : West/intra_routing_fan_in_out  │ (rows 5..4+C)
      col 3+W          : West/intra_routing_longitude   │
      cols 4+W..3+W+K  : [blank crossbar — K cols wide] │
      col 4+W+K        : East/intra_routing_longitude   │
      col 5+W+K        : East/intra_routing_fan_in_out  │
      cols 6+W+K..5+W+K+E: East/chip_terminal           │
      col 6+W+K+E      : East/inter_routing_fan_in_out  ┘
      col 7+W+K+E      : East/inter_routing_longitude   ← full height (inter-zone pillar)
    Total = W + E + 8 + K

    Vertical layout (C = zoneVerticalSpan - 10 = chip-stack height):
      row 0   : North/inter_routing_latitude
      row 1   : North/inter_routing_fan_in_out
      row 2   : North/chip_terminal  (min 1 row, no chips in WTE zones)
      row 3   : North/intra_routing_fan_in_out
      row 4   : North/intra_routing_latitude
      rows 5..4+C : crossbar / W–E chip-terminal area
      row 5+C : South/intra_routing_latitude
      row 6+C : South/intra_routing_fan_in_out
      row 7+C : South/chip_terminal  (min 1 row)
      row 8+C : South/inter_routing_fan_in_out
      row 9+C : South/inter_routing_latitude  (= H-1)
    Total H = C + 10
    """

    W: int = westTerminalWidth
    E: int = eastTerminalWidth
    K: int = crossbarWidth
    H: int = zoneVerticalSpan  # = 10 + C
    C: int = H - 10            # chip-stack height (>= 1)
    S: int = zoneHorizontalSpan  # = W + E + 8 + K
    X: int = 4 + W             # crossbar horizontal start (col after INTRA_LONG/WEST)

    regionSpecs: tuple[
        tuple[RoutingZoneRegionKind, RoutingZoneRegionSide | None, int, int, int, int],
        ...,
    ] = (
        # ── West longitude bands (vertical columns) ──
        # Only INTER_LONGITUDE spans full zone height — it is the inter-zone
        # routing pillar.  All other vertical bands are crossbar-only (rows
        # 5..4+C) so they do not bleed into the latitude band rows.
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         0, 1, _CHANNEL_SPAN, H - 2),          # pillar — skip seam rows
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         1, 5, _FAN_IN_OUT_SPAN, C),            # crossbar only
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.WEST,
         2, 5, W, C),                           # crossbar only
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         2 + W, 5, _FAN_IN_OUT_SPAN, C),        # crossbar only
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         3 + W, 5, _CHANNEL_SPAN, C),           # crossbar only
        # cols 4+W .. 3+W+K are blank crossbar space (K cols wide)
        # ── East longitude bands (vertical columns) ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         4 + W + K, 5, _CHANNEL_SPAN, C),       # crossbar only
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         5 + W + K, 5, _FAN_IN_OUT_SPAN, C),    # crossbar only
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.EAST,
         6 + W + K, 5, E, C),                   # crossbar only
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         6 + W + K + E, 5, _FAN_IN_OUT_SPAN, C), # crossbar only
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         7 + W + K + E, 1, _CHANNEL_SPAN, H - 2), # pillar — skip seam rows
        # ── North latitude bands ──
        # INTER_ROUTING_LATITUDE spans the full zone width (pillar-to-pillar) —
        # it is the inter-zone seam row.  All inner bands are confined to the
        # blank crossbar corridor (cols X..X+K) — the same K-wide transit space
        # that separates the W and E chip terminal columns.
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         1, 0, S - 2, 1),                          # seam — skip pillar cols
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         X, 1, K, 1),                              # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.NORTH,
         X, 2, K, 1),                              # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         X, 3, K, 1),                              # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         X, 4, K, 1),                              # crossbar corridor
        # ── South latitude bands ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         X, 5 + C, K, 1),                          # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         X, 6 + C, K, 1),                          # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.SOUTH,
         X, 7 + C, K, 1),                          # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         X, 8 + C, K, 1),                          # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         1, 9 + C, S - 2, 1),                      # seam — skip pillar cols
    )
    return _routingZoneRegionSetResult_buildFromSpecs(
        routingZoneId=routingZoneId,
        horizontalStart=horizontalStart,
        verticalStart=verticalStart,
        regionSpecs=regionSpecs,
    )


def _northSouthRegionSetResult_buildForZone(
    routingZoneId: RoutingZoneId,
    horizontalStart: int,
    verticalStart: int,
    zoneHorizontalSpan: int,
    zoneVerticalSpan: int,
    northTerminalHeight: int,
    southTerminalHeight: int,
    crossbarHeight: int,
) -> Result[RoutingZoneRegionSet]:
    """Build logical north-to-south region set for one planned zone.

    Implements the canonical 20-band concentric zone geometry.  All regions
    carry a cardinal side qualifier.

    Horizontal layout (W_zone = chipWidth + 10):
      col 0            : West/inter_routing_longitude  ← full height (inter-zone pillar)
      col 1            : West/inter_routing_fan_in_out ┐
      col 2            : West/chip_terminal             │ interior rows only
      col 3            : West/intra_routing_fan_in_out  │ (rows 1..T-2)
      col 4            : West/intra_routing_longitude   │
      cols 5..4+CW     : N/S chip terminal area         │  (CW = chipWidth = W_zone-10)
      col 5+CW         : East/intra_routing_longitude   │
      col 6+CW         : East/intra_routing_fan_in_out  │
      col 7+CW         : East/chip_terminal              │
      col 8+CW         : East/inter_routing_fan_in_out  ┘
      col 9+CW         : East/inter_routing_longitude  ← full height (inter-zone pillar)
    Total = CW + 10 = W_zone

    Vertical layout (N=northTerminalHeight, So=southTerminalHeight,
                     K=crossbarHeight):
      row 0          : North/inter_routing_latitude
      row 1          : North/inter_routing_fan_in_out
      rows 2..N+1    : North/chip_terminal
      row N+2        : North/intra_routing_fan_in_out
      row N+3        : North/intra_routing_latitude
      rows N+4..N+3+K: [blank crossbar — K rows tall]
      row N+4+K      : South/intra_routing_latitude
      row N+5+K      : South/intra_routing_fan_in_out
      rows N+6+K..N+5+K+So : South/chip_terminal
      row N+6+K+So   : South/inter_routing_fan_in_out
      row N+7+K+So   : South/inter_routing_latitude  (= T-1)
    Total T = N + So + 8 + K
    """

    N: int = northTerminalHeight
    So: int = southTerminalHeight
    K: int = crossbarHeight
    T: int = zoneVerticalSpan   # = N + So + 8 + K
    W_zone: int = zoneHorizontalSpan   # = chipWidth + 10
    CW: int = W_zone - 10              # chip width (>= 1)
    Y: int = N + 4             # crossbar vertical start (row after INTRA_LAT/NORTH)

    regionSpecs: tuple[
        tuple[RoutingZoneRegionKind, RoutingZoneRegionSide | None, int, int, int, int],
        ...,
    ] = (
        # ── West longitude bands (vertical columns) ──
        # Only INTER_LONGITUDE spans full zone height.  All other vertical
        # bands are confined to the blank crossbar corridor (rows Y..Y+K) —
        # the same K-tall transit space between the N and S chip terminal rows.
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         0, 1, _CHANNEL_SPAN, T - 2),       # pillar — skip seam rows
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         1, Y, _FAN_IN_OUT_SPAN, K),        # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.WEST,
         2, Y, _CHANNEL_SPAN, K),           # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         3, Y, _FAN_IN_OUT_SPAN, K),        # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         4, Y, _CHANNEL_SPAN, K),           # crossbar corridor
        # ── East longitude bands (vertical columns) ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         5 + CW, Y, _CHANNEL_SPAN, K),      # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         6 + CW, Y, _FAN_IN_OUT_SPAN, K),   # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.EAST,
         7 + CW, Y, _CHANNEL_SPAN, K),      # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         8 + CW, Y, _FAN_IN_OUT_SPAN, K),   # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         9 + CW, 1, _CHANNEL_SPAN, T - 2),  # pillar — skip seam rows
        # ── North latitude bands ──
        # INTER_ROUTING_LATITUDE spans the full zone width (pillar-to-pillar).
        # All inner bands are confined to the chip-terminal column range
        # (cols 5..5+CW) so they align with where chips sit.
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         1, 0, W_zone - 2, 1),              # seam — skip pillar cols
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         5, 1, CW, 1),                      # chip-area width
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.NORTH,
         5, 2, CW, N),                      # chip-area width (unchanged)
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         5, N + 2, CW, 1),                  # chip-area width
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         5, N + 3, CW, 1),                  # chip-area width
        # rows N+4..N+3+K are blank crossbar space (K rows tall)
        # ── South latitude bands ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         5, N + 4 + K, CW, 1),              # chip-area width
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         5, N + 5 + K, CW, 1),              # chip-area width
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.SOUTH,
         5, N + 6 + K, CW, So),             # chip-area width (unchanged)
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         5, N + 6 + K + So, CW, 1),         # chip-area width
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         1, N + 7 + K + So, W_zone - 2, 1), # seam — skip pillar cols
    )
    return _routingZoneRegionSetResult_buildFromSpecs(
        routingZoneId=routingZoneId,
        horizontalStart=horizontalStart,
        verticalStart=verticalStart,
        regionSpecs=regionSpecs,
    )


def _routingZoneRegionSetResult_buildFromSpecs(
    routingZoneId: RoutingZoneId,
    horizontalStart: int,
    verticalStart: int,
    regionSpecs: tuple[
        tuple[
            RoutingZoneRegionKind,
            RoutingZoneRegionSide | None,
            int,
            int,
            int,
            int,
        ],
        ...,
    ],
) -> Result[RoutingZoneRegionSet]:
    """Build region set from local region specs."""

    routingZoneRegionsMutable: list[RoutingZoneRegion] = []
    (
        routingZoneRegionKind,
        routingZoneRegionSide,
        localHorizontalStart,
        localVerticalStart,
        horizontalSpan,
        verticalSpan,
    ) = (None, None, 0, 0, 0, 0)
    for (
        routingZoneRegionKind,
        routingZoneRegionSide,
        localHorizontalStart,
        localVerticalStart,
        horizontalSpan,
        verticalSpan,
    ) in regionSpecs:
        routingZoneRegionFrameResult: Result[RoutingZoneRegionFrame] = (
            routingZoneRegionFrameResult_build(
                horizontalStart=horizontalStart + localHorizontalStart,
                verticalStart=verticalStart + localVerticalStart,
                horizontalSpan=horizontalSpan,
                verticalSpan=verticalSpan,
            )
        )
        if not result_isOkCheck(routingZoneRegionFrameResult):
            return resultErr_build()
        routingZoneRegionResult: Result[RoutingZoneRegion] = (
            routingZoneRegionResult_build(
                routingZoneRegionId=RoutingZoneRegionId(
                    routingZoneId=routingZoneId,
                    routingZoneRegionKind=routingZoneRegionKind,
                    routingZoneRegionSide=routingZoneRegionSide,
                ),
                routingZoneRegionFrame=routingZoneRegionFrameResult.value,
            )
        )
        if not result_isOkCheck(routingZoneRegionResult):
            return resultErr_build()
        routingZoneRegionsMutable.append(routingZoneRegionResult.value)
    return routingZoneRegionSetResult_build(
        routingZoneRegions=tuple(routingZoneRegionsMutable)
    )


def _plannedInterconnectSetResult_build(
    originalRoutingZoneGrid: RoutingZoneGrid,
    plannedRoutingZoneSet: RoutingZoneSet,
) -> Result[RoutingZoneInterconnectSet]:
    """Build interconnect set with logical world frames from planned zones."""

    plannedInterconnectsMutable: list[RoutingZoneInterconnect] = []
    originalRoutingZoneInterconnect: RoutingZoneInterconnect
    for originalRoutingZoneInterconnect in (
        originalRoutingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects
    ):
        sourceZoneResult: Result[RoutingZone] = plannedRoutingZoneSet.zoneResult_get(
            originalRoutingZoneInterconnect.sourceZoneId
        )
        if not result_isOkCheck(sourceZoneResult):
            return resultErr_build()
        destinationZoneResult: Result[RoutingZone] = (
            plannedRoutingZoneSet.zoneResult_get(
                originalRoutingZoneInterconnect.destinationZoneId
            )
        )
        if not result_isOkCheck(destinationZoneResult):
            return resultErr_build()
        interconnectFrameResult: Result[RoutingZoneInterconnectFrame] = (
            _interconnectFrameResult_buildBetweenZones(
                sourceRoutingZone=sourceZoneResult.value,
                destinationRoutingZone=destinationZoneResult.value,
            )
        )
        if not result_isOkCheck(interconnectFrameResult):
            return resultErr_build()
        plannedInterconnectsMutable.append(
            RoutingZoneInterconnect(
                routingZoneInterconnectId=(
                    originalRoutingZoneInterconnect.routingZoneInterconnectId
                ),
                sourceZoneId=originalRoutingZoneInterconnect.sourceZoneId,
                destinationZoneId=originalRoutingZoneInterconnect.destinationZoneId,
                channelSense=originalRoutingZoneInterconnect.channelSense,
                routingZoneInterconnectFrame=interconnectFrameResult.value,
            )
        )
    return routingZoneInterconnectSetResult_build(
        routingZoneInterconnects=tuple(plannedInterconnectsMutable)
    )


def _interconnectFrameResult_buildBetweenZones(
    sourceRoutingZone: RoutingZone,
    destinationRoutingZone: RoutingZone,
) -> Result[RoutingZoneInterconnectFrame]:
    """Build logical interconnect frame between two adjacent planned zones."""

    if sourceRoutingZone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        horizontalStart: int = (
            sourceRoutingZone.routingZoneFrame.horizontalEnd_calculate()
        )
        verticalStart: int = min(
            sourceRoutingZone.routingZoneFrame.verticalStart,
            destinationRoutingZone.routingZoneFrame.verticalStart,
        )
        verticalSpan: int = max(
            sourceRoutingZone.routingZoneFrame.verticalSpan,
            destinationRoutingZone.routingZoneFrame.verticalSpan,
        )
        return routingZoneInterconnectFrameResult_build(
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            horizontalSpan=_INTERCONNECT_SPAN,
            verticalSpan=verticalSpan,
        )

    verticalStart = sourceRoutingZone.routingZoneFrame.verticalEnd_calculate()
    horizontalStart = min(
        sourceRoutingZone.routingZoneFrame.horizontalStart,
        destinationRoutingZone.routingZoneFrame.horizontalStart,
    )
    horizontalSpan: int = max(
        sourceRoutingZone.routingZoneFrame.horizontalSpan,
        destinationRoutingZone.routingZoneFrame.horizontalSpan,
    )
    return routingZoneInterconnectFrameResult_build(
        horizontalStart=horizontalStart,
        verticalStart=verticalStart,
        horizontalSpan=horizontalSpan,
        verticalSpan=_INTERCONNECT_SPAN,
    )
