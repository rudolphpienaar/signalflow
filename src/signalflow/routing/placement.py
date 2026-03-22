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
from signalflow.routing.geometry import chipLocalGeometryResult_build

_TERMINAL_SPAN: int = 1
_FAN_IN_OUT_SPAN: int = 1
_CHANNEL_SPAN: int = 1
_INTERCONNECT_SPAN: int = 1
_CROSSBAR_SPAN_MIN: int = 10
_INTER_FAN_STRUCTURE_SPAN: int = 2


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
    globalInterLaneSpan: int = max(
        (m.get("interLaneSpan", 1) for m in zoneMetricsById.values()),
        default=1,
    )
    globalInterFanSpan: int = max(
        (m.get("interFanSpan", 1) for m in zoneMetricsById.values()),
        default=1,
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
        interLaneSpan=globalInterLaneSpan,
    )
    rowStartByIndex: dict[int, int] = _rowStartByIndex_build(
        routingZoneGrid=routingZoneGrid,
        rowHeightByIndex=rowHeightByIndex,
        interLaneSpan=globalInterLaneSpan,
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
                intraLaneSpan=zoneMetrics.get("intraLaneSpan", 1),
                latNOffset=zoneMetrics.get("latNOffset", 4),
                latSOffset=zoneMetrics.get("latSOffset"),
                interLaneSpan=globalInterLaneSpan,
                interFanSpan=globalInterFanSpan,
                westInterFanDim=zoneMetrics.get("westInterFanDim"),
                eastInterFanDim=zoneMetrics.get("eastInterFanDim"),
                westIntraFanDim=zoneMetrics.get("westIntraFanDim"),
                eastIntraFanDim=zoneMetrics.get("eastIntraFanDim"),
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
            interLaneSpan=globalInterLaneSpan,
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
    intraLaneSpan: int = 1,
    latNOffset: int = 4,
    latSOffset: int | None = None,
    interLaneSpan: int = 1,
    interFanSpan: int = 1,
    westInterFanDim: int | None = None,
    eastInterFanDim: int | None = None,
    westIntraFanDim: int | None = None,
    eastIntraFanDim: int | None = None,
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

    C: int = zoneVerticalSpan - 10
    resolvedLatS: int = latSOffset if latSOffset is not None else 5 + C
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
            intraLaneSpan=intraLaneSpan,
            latNOffset=latNOffset,
            latSOffset=resolvedLatS,
            interLaneSpan=interLaneSpan,
            interFanSpan=interFanSpan,
            westInterFanDim=westInterFanDim,
            eastInterFanDim=eastInterFanDim,
            westIntraFanDim=westIntraFanDim,
            eastIntraFanDim=eastIntraFanDim,
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
    interLaneSpan: int = 1,
    interFanSpan: int = 1,
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

    def _chipDims_get(
        assignments: object,
    ) -> tuple[list[int], list[int], list[int], list[int], list[int], list[int]]:
        """Return box dims and materialized label extents for assignments."""
        heights: list[int] = []
        widths: list[int] = []
        westMargins: list[int] = []
        eastMargins: list[int] = []
        northMargins: list[int] = []
        southMargins: list[int] = []
        for assignment in assignments:
            chipResult = circuitDocument.circuitChipSet.chipResult_get(
                assignment.chipRef.chipId
            )
            if not result_isOkCheck(chipResult):
                continue
            geometryResult = chipLocalGeometryResult_build(chipResult.value)
            if not result_isOkCheck(geometryResult):
                continue
            heights.append(geometryResult.value.boxHeight)
            widths.append(geometryResult.value.boxWidth)
            westMargins.append(geometryResult.value.westMarginWidth)
            eastMargins.append(geometryResult.value.eastMarginWidth)
            northMargins.append(geometryResult.value.northMarginHeight)
            southMargins.append(geometryResult.value.southMarginHeight)
        return (
            heights,
            widths,
            westMargins,
            eastMargins,
            northMargins,
            southMargins,
        )

    (
        startHeights,
        startWidths,
        startWestMargins,
        startEastMargins,
        _startNorthMargins,
        _startSouthMargins,
    ) = _chipDims_get(startAssignments)
    (
        endHeights,
        endWidths,
        endWestMargins,
        endEastMargins,
        _endNorthMargins,
        _endSouthMargins,
    ) = _chipDims_get(endAssignments)

    startCount: int = len(startHeights)
    endCount: int = len(endHeights)
    localIntraDirectedWireDemand: int = _localIntraDirectedWireDemandForZone_compute(
        routingZoneId=routingZoneId,
        routingZoneSense=routingZoneSense,
        routingZoneAssignmentSet=routingZoneAssignmentSet,
        circuitDocument=circuitDocument,
    )
    intraLaneSpan: int = max(localIntraDirectedWireDemand, 1)
    crossbarDim: int = max(
        2,
        startCount,
        endCount,
    )

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        westTerminalWidth: int = max(startWidths, default=1)
        eastTerminalWidth: int = max(endWidths, default=1)
        westInterFanDim: int = max(interFanSpan, max(startWestMargins, default=0))
        eastInterFanDim: int = max(interFanSpan, max(endEastMargins, default=0))
        westIntraFanDim: int = max(
            _FAN_IN_OUT_SPAN,
            max(startEastMargins, default=0),
        )
        eastIntraFanDim: int = max(
            _FAN_IN_OUT_SPAN,
            max(endWestMargins, default=0),
        )
        startSlotHeight: int = sum(h + 2 for h in startHeights) if startHeights else 1
        endSlotHeight: int = sum(h + 2 for h in endHeights) if endHeights else 1
        chipStackHeight: int = max(startSlotHeight, endSlotHeight, 1)
        # Choose the WTE north/south intra-lat placement that minimizes total
        # detour cost over the actual same-zone obligation set.
        # The solver consumes real lane fields, not one-cell anchors. Choose
        # the WTE north/south intra-lat placement that minimizes total detour
        # cost across the zone-local obligation set.
        (
            chipStackHeightAdjusted,
            latNOffset,
            latSOffset,
        ) = _wteIntraLatOffsets_buildMinDetour(
            routingZoneId=routingZoneId,
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            circuitDocument=circuitDocument,
            startAssignments=tuple(startAssignments),
            endAssignments=tuple(endAssignments),
            startHeights=tuple(startHeights),
            endHeights=tuple(endHeights),
            startSide=startSide,
            endSide=endSide,
            intraLaneSpan=intraLaneSpan,
            chipStackHeight=chipStackHeight,
        )
        zoneVerticalSpan: int = 10 + chipStackHeightAdjusted
        zoneHorizontalSpan: int = (
            westTerminalWidth
            + eastTerminalWidth
            + crossbarDim
            + westInterFanDim
            + eastInterFanDim
            + 2 * interLaneSpan
            + westIntraFanDim
            + eastIntraFanDim
            + 2 * intraLaneSpan
        )
        return {
            "zoneHorizontalSpan": zoneHorizontalSpan,
            "zoneVerticalSpan": zoneVerticalSpan,
            "startTerminalDim": westTerminalWidth,
            "endTerminalDim": eastTerminalWidth,
            "crossbarDim": crossbarDim,
            "intraLaneSpan": intraLaneSpan,
            "latNOffset": latNOffset,
            "latSOffset": latSOffset,
            "interLaneSpan": interLaneSpan,
            "interFanSpan": interFanSpan,
            "westInterFanDim": westInterFanDim,
            "eastInterFanDim": eastInterFanDim,
            "westIntraFanDim": westIntraFanDim,
            "eastIntraFanDim": eastIntraFanDim,
        }

    northTerminalHeight: int = max(
        sum(h + 2 for h in startHeights) if startHeights else 1, 1
    )
    southTerminalHeight: int = max(
        sum(h + 2 for h in endHeights) if endHeights else 1, 1
    )
    chipWidth: int = max(
        max(startWidths, default=1),
        max(endWidths, default=1),
        2 * localIntraDirectedWireDemand,
        1,
    )
    zoneHorizontalSpanNS: int = chipWidth + 10
    zoneHorizontalSpanNS = (
        chipWidth
        + 2 * interFanSpan
        + 2 * interLaneSpan
        + 6
    )
    zoneVerticalSpanNS: int = (
        northTerminalHeight
        + southTerminalHeight
        + crossbarDim
        + 2 * interFanSpan
        + 2 * interLaneSpan
        + 4
    )
    return {
        "zoneHorizontalSpan": zoneHorizontalSpanNS,
        "zoneVerticalSpan": zoneVerticalSpanNS,
        "startTerminalDim": northTerminalHeight,
        "endTerminalDim": southTerminalHeight,
        "crossbarDim": crossbarDim,
        "intraLaneSpan": intraLaneSpan,
        "interLaneSpan": interLaneSpan,
        "interFanSpan": interFanSpan,
    }


def _localIntraDirectedWireDemandForZone_compute(
    routingZoneId: RoutingZoneId,
    routingZoneSense: RoutingZoneSense,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    circuitDocument: CircuitDocument,
) -> int:
    """Return directed-wire demand for same-zone transverse INTRA routing."""

    startSide: RoutingZoneRegionSide
    endSide: RoutingZoneRegionSide
    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        startSide = RoutingZoneRegionSide.WEST
        endSide = RoutingZoneRegionSide.EAST
    else:
        startSide = RoutingZoneRegionSide.NORTH
        endSide = RoutingZoneRegionSide.SOUTH

    directedWireDemand: int = 0
    for circuitCall in circuitDocument.circuitCallSet.circuitCalls:
        sourceAssignment = _assignmentForChipOrNone_get(
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            chipId=circuitCall.sourceChipRef.chipId,
        )
        destinationAssignment = _assignmentForChipOrNone_get(
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            chipId=circuitCall.destinationChipRef.chipId,
        )
        if sourceAssignment is None or destinationAssignment is None:
            continue
        if (
            sourceAssignment.routingZoneId != routingZoneId
            or destinationAssignment.routingZoneId != routingZoneId
        ):
            continue
        if (
            sourceAssignment.terminalSide is startSide
            and destinationAssignment.terminalSide is endSide
        ):
            directedWireDemand += 2
    return directedWireDemand


def _assignmentForChipOrNone_get(
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    chipId,
):
    """Return the assignment for one chip, or `None` when absent."""

    for routingZoneAssignment in routingZoneAssignmentSet.routingZoneAssignments:
        if routingZoneAssignment.chipRef.chipId == chipId:
            return routingZoneAssignment
    return None


def _wteIntraLatOffsets_buildMinDetour(
    routingZoneId: RoutingZoneId,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    circuitDocument: CircuitDocument,
    startAssignments: tuple,
    endAssignments: tuple,
    startHeights: tuple[int, ...],
    endHeights: tuple[int, ...],
    startSide: RoutingZoneRegionSide,
    endSide: RoutingZoneRegionSide,
    intraLaneSpan: int,
    chipStackHeight: int,
) -> tuple[int, int, int]:
    """Choose WTE intra-lat anchors that minimize buckle-aware detour cost.

    Returns:
        `(chipStackHeightAdjusted, latNOffset, latSOffset)` where `latNOffset`
        is the north-band end row and `latSOffset` is the south-band start row.
    """

    _TERM_ROW: int = 5
    _HEADER_AND_CORRIDOR: int = 4

    startOrderByChipId = {
        assignment.chipRef.chipId: orderIndex
        for orderIndex, assignment in enumerate(startAssignments)
    }
    endOrderByChipId = {
        assignment.chipRef.chipId: orderIndex
        for orderIndex, assignment in enumerate(endAssignments)
    }
    startHeightByChipId = {
        assignment.chipRef.chipId: startHeights[orderIndex]
        for orderIndex, assignment in enumerate(startAssignments)
    }
    endHeightByChipId = {
        assignment.chipRef.chipId: endHeights[orderIndex]
        for orderIndex, assignment in enumerate(endAssignments)
    }

    localCalls = [
        circuitCall
        for circuitCall in circuitDocument.circuitCallSet.circuitCalls
        if (
            (sourceAssignment := _assignmentForChipOrNone_get(
                routingZoneAssignmentSet=routingZoneAssignmentSet,
                chipId=circuitCall.sourceChipRef.chipId,
            ))
            is not None
            and (destinationAssignment := _assignmentForChipOrNone_get(
                routingZoneAssignmentSet=routingZoneAssignmentSet,
                chipId=circuitCall.destinationChipRef.chipId,
            ))
            is not None
            and sourceAssignment.routingZoneId == routingZoneId
            and destinationAssignment.routingZoneId == routingZoneId
            and sourceAssignment.terminalSide is startSide
            and destinationAssignment.terminalSide is endSide
        )
    ]

    if not localCalls:
        defaultNorthEnd: int = _TERM_ROW + intraLaneSpan - 1
        return (
            max(chipStackHeight, 2 * intraLaneSpan),
            defaultNorthEnd,
            defaultNorthEnd + 1,
        )

    preferredNorthEnd: int = round(
        sum(
            (
                _TERM_ROW
                + startOrderByChipId[circuitCall.sourceChipRef.chipId]
                * (
                    startHeightByChipId[circuitCall.sourceChipRef.chipId] + 2
                )
                + _HEADER_AND_CORRIDOR
                + 2 * circuitCall.callIndex
            )
            + (
                _TERM_ROW
                + endOrderByChipId[circuitCall.destinationChipRef.chipId]
                * (
                    endHeightByChipId[circuitCall.destinationChipRef.chipId] + 2
                )
                + _HEADER_AND_CORRIDOR
            )
            for circuitCall in localCalls
        ) / (2 * len(localCalls))
    )

    chipStackHeightAdjusted: int = max(chipStackHeight, 2 * intraLaneSpan)
    bestNorthEnd: int | None = None
    bestCost: int | None = None
    bestBucklePenalty: int | None = None
    bestMaxDetour: int | None = None

    while bestNorthEnd is None:
        minNorthEnd: int = _TERM_ROW + intraLaneSpan - 1
        maxNorthEnd: int = (_TERM_ROW - 1) + chipStackHeightAdjusted - intraLaneSpan
        if minNorthEnd > maxNorthEnd:
            chipStackHeightAdjusted += 1
            continue

        northEnd: int
        for northEnd in range(minNorthEnd, maxNorthEnd + 1):
            northStart: int = northEnd - intraLaneSpan + 1
            southStart: int = northEnd + 1
            totalCost: int = 0
            totalBucklePenalty: int = 0
            maxDetour: int = 0

            localLaneIndex: int
            circuitCall = None
            for localLaneIndex, circuitCall in enumerate(localCalls):
                srcSignalRow: int = (
                    _TERM_ROW
                    + startOrderByChipId[circuitCall.sourceChipRef.chipId]
                    * (
                        startHeightByChipId[circuitCall.sourceChipRef.chipId] + 2
                    )
                    + _HEADER_AND_CORRIDOR
                    + 2 * circuitCall.callIndex
                )
                dstSignalRow: int = (
                    _TERM_ROW
                    + endOrderByChipId[circuitCall.destinationChipRef.chipId]
                    * (
                        endHeightByChipId[
                            circuitCall.destinationChipRef.chipId
                        ] + 2
                    )
                    + _HEADER_AND_CORRIDOR
                )
                srcReturnRow: int = srcSignalRow + 1
                dstReturnRow: int = dstSignalRow + 1

                # Match the current WTE occupancy solver's packed lane family:
                # forward lanes consume the north band from its start downward
                # in pick order; returns consume the south band from its end.
                forwardLaneRow: int = northStart + localLaneIndex
                returnLaneRow: int = (
                    southStart + (intraLaneSpan - 1 - localLaneIndex)
                )

                detours = (
                    abs(srcSignalRow - forwardLaneRow),
                    abs(dstSignalRow - forwardLaneRow),
                    abs(dstReturnRow - returnLaneRow),
                    abs(srcReturnRow - returnLaneRow),
                )
                bucklePenalty = (
                    _intervalOvershootPenalty_compute(
                        value=forwardLaneRow,
                        firstRow=srcSignalRow,
                        secondRow=dstSignalRow,
                    )
                    + _intervalOvershootPenalty_compute(
                        value=returnLaneRow,
                        firstRow=srcReturnRow,
                        secondRow=dstReturnRow,
                    )
                )
                totalCost += sum(detours)
                totalBucklePenalty += bucklePenalty
                maxDetour = max(maxDetour, *detours)

            candidateDistance: int = abs(northEnd - preferredNorthEnd)
            bestDistance: int = (
                abs(bestNorthEnd - preferredNorthEnd)
                if bestNorthEnd is not None
                else 0
            )
            if (
                bestBucklePenalty is None
                or totalBucklePenalty < bestBucklePenalty
                or (
                    totalBucklePenalty == bestBucklePenalty
                    and totalCost < bestCost
                )
                or (
                    totalBucklePenalty == bestBucklePenalty
                    and totalCost == bestCost
                    and maxDetour < bestMaxDetour
                )
                or (
                    totalBucklePenalty == bestBucklePenalty
                    and totalCost == bestCost
                    and maxDetour == bestMaxDetour
                    and candidateDistance < bestDistance
                )
                or (
                    totalBucklePenalty == bestBucklePenalty
                    and totalCost == bestCost
                    and maxDetour == bestMaxDetour
                    and candidateDistance == bestDistance
                    and northEnd < bestNorthEnd
                )
            ):
                bestNorthEnd = northEnd
                bestCost = totalCost
                bestBucklePenalty = totalBucklePenalty
                bestMaxDetour = maxDetour

    return chipStackHeightAdjusted, bestNorthEnd, bestNorthEnd + 1


def _intervalOvershootPenalty_compute(
    value: int,
    firstRow: int,
    secondRow: int,
) -> int:
    """Return how far `value` lies outside the closed interval of two rows."""

    lowerBound: int = min(firstRow, secondRow)
    upperBound: int = max(firstRow, secondRow)
    if value < lowerBound:
        return lowerBound - value
    if value > upperBound:
        return value - upperBound
    return 0


def _zonePairKey_build(
    sourceZoneId: RoutingZoneId,
    destinationZoneId: RoutingZoneId,
) -> tuple[RoutingZoneId, RoutingZoneId]:
    """Return one stable adjacent-zone pair key."""

    sourceCoord = sourceZoneId.id
    destinationCoord = destinationZoneId.id
    if (
        sourceCoord.columnIndex,
        sourceCoord.rowIndex,
    ) <= (
        destinationCoord.columnIndex,
        destinationCoord.rowIndex,
    ):
        return sourceZoneId, destinationZoneId
    return destinationZoneId, sourceZoneId


def _zonesAdjacentCheck(
    sourceZoneId: RoutingZoneId,
    destinationZoneId: RoutingZoneId,
) -> bool:
    """Return whether two routing zones share one seam."""

    sourceCoord = sourceZoneId.id
    destinationCoord = destinationZoneId.id
    return (
        abs(sourceCoord.columnIndex - destinationCoord.columnIndex)
        + abs(sourceCoord.rowIndex - destinationCoord.rowIndex)
        == 1
    )


def _globalInterLaneSpan_compute(
    routingZoneGrid: RoutingZoneGrid,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    circuitDocument: CircuitDocument,
) -> int:
    """Return global max directed-wire demand over all INTER-owned corridors."""

    seamLaneCountByZonePair: dict[tuple[RoutingZoneId, RoutingZoneId], int] = {}
    perimeterLaneCountByZoneId: dict[RoutingZoneId, int] = {}
    startSide: RoutingZoneRegionSide
    endSide: RoutingZoneRegionSide
    if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        startSide = RoutingZoneRegionSide.WEST
        endSide = RoutingZoneRegionSide.EAST
    else:
        startSide = RoutingZoneRegionSide.NORTH
        endSide = RoutingZoneRegionSide.SOUTH

    for circuitCall in circuitDocument.circuitCallSet.circuitCalls:
        sourceAssignment = _assignmentForChipOrNone_get(
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            chipId=circuitCall.sourceChipRef.chipId,
        )
        destinationAssignment = _assignmentForChipOrNone_get(
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            chipId=circuitCall.destinationChipRef.chipId,
        )
        if sourceAssignment is None or destinationAssignment is None:
            continue
        if sourceAssignment.routingZoneId == destinationAssignment.routingZoneId:
            if (
                sourceAssignment.terminalSide is endSide
                and destinationAssignment.terminalSide is startSide
            ):
                perimeterLaneCountByZoneId[sourceAssignment.routingZoneId] = (
                    perimeterLaneCountByZoneId.get(
                        sourceAssignment.routingZoneId,
                        0,
                    )
                    + 2
                )
            continue
        if not _zonesAdjacentCheck(
            sourceZoneId=sourceAssignment.routingZoneId,
            destinationZoneId=destinationAssignment.routingZoneId,
        ):
            continue
        zonePairKey = _zonePairKey_build(
            sourceZoneId=sourceAssignment.routingZoneId,
            destinationZoneId=destinationAssignment.routingZoneId,
        )
        seamLaneCountByZonePair[zonePairKey] = (
            seamLaneCountByZonePair.get(zonePairKey, 0) + 2
        )
    return max(
        tuple(seamLaneCountByZonePair.values())
        + tuple(perimeterLaneCountByZoneId.values()),
        default=1,
    )


def _globalInterFanSpan_build(interLaneSpan: int) -> int:
    """Return seam-side fan width/height from directed-wire lane demand."""

    if interLaneSpan <= 1:
        return 1
    return interLaneSpan + _INTER_FAN_STRUCTURE_SPAN


def _zoneMetricsById_build(
    routingZoneGrid: RoutingZoneGrid,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    circuitDocument: CircuitDocument,
) -> dict[RoutingZoneId, dict[str, int]]:
    """Build logical sizing metrics for every zone in the world."""

    # Compute global seam demand first so every zone uses a consistent seam
    # corridor width on the world major axis.
    globalInterLaneSpan: int = _globalInterLaneSpan_compute(
        routingZoneGrid=routingZoneGrid,
        routingZoneAssignmentSet=routingZoneAssignmentSet,
        circuitDocument=circuitDocument,
    )
    globalInterFanSpan: int = _globalInterFanSpan_build(
        interLaneSpan=globalInterLaneSpan
    )

    metricsById: dict[RoutingZoneId, dict[str, int]] = {}
    routingZone: RoutingZone
    for routingZone in routingZoneGrid.routingZoneSet.routingZones:
        metricsById[routingZone.routingZoneId] = _zoneMetrics_build(
            routingZoneId=routingZone.routingZoneId,
            routingZoneSense=routingZone.routingZoneSense,
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            circuitDocument=circuitDocument,
            interLaneSpan=globalInterLaneSpan,
            interFanSpan=globalInterFanSpan,
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
    interLaneSpan: int = 1,
) -> dict[int, int]:
    """Build world horizontal start coordinate per grid column."""

    startByIndex: dict[int, int] = {}
    cursor: int = 0
    columnIndex: int
    for columnIndex in range(1, routingZoneGrid.gridSize.columnIndex + 1):
        startByIndex[columnIndex] = cursor
        cursor += columnWidthByIndex[columnIndex]
        if columnIndex < routingZoneGrid.gridSize.columnIndex:
            gapSpan: int = (
                interLaneSpan
                if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST
                else _INTERCONNECT_SPAN
            )
            cursor += gapSpan
    return startByIndex


def _rowStartByIndex_build(
    routingZoneGrid: RoutingZoneGrid,
    rowHeightByIndex: dict[int, int],
    interLaneSpan: int = 1,
) -> dict[int, int]:
    """Build world vertical start coordinate per grid row."""

    startByIndex: dict[int, int] = {}
    cursor: int = 0
    rowIndex: int
    for rowIndex in range(1, routingZoneGrid.gridSize.rowIndex + 1):
        startByIndex[rowIndex] = cursor
        cursor += rowHeightByIndex[rowIndex]
        if rowIndex < routingZoneGrid.gridSize.rowIndex:
            gapSpan: int = (
                interLaneSpan
                if routingZoneGrid.worldSense is RoutingZoneSense.NORTH_TO_SOUTH
                else _INTERCONNECT_SPAN
            )
            cursor += gapSpan
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
    intraLaneSpan: int = 1,
    latNOffset: int = 4,
    latSOffset: int | None = None,
    interLaneSpan: int = 1,
    interFanSpan: int = 1,
    westInterFanDim: int | None = None,
    eastInterFanDim: int | None = None,
    westIntraFanDim: int | None = None,
    eastIntraFanDim: int | None = None,
) -> Result[RoutingZoneRegionSet]:
    """Build logical explicit region geometry for one planned zone."""

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        C: int = zoneVerticalSpan - 10
        return _westEastRegionSetResult_buildForZone(
            routingZoneId=routingZoneId,
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            zoneHorizontalSpan=zoneHorizontalSpan,
            zoneVerticalSpan=zoneVerticalSpan,
            westTerminalWidth=startTerminalDim,
            eastTerminalWidth=endTerminalDim,
            crossbarWidth=crossbarDim,
            intraLaneSpan=intraLaneSpan,
            latNOffset=latNOffset,
            latSOffset=latSOffset if latSOffset is not None else 5 + C,
            interLaneSpan=interLaneSpan,
            interFanSpan=interFanSpan,
            westInterFanWidth=(
                westInterFanDim if westInterFanDim is not None else interFanSpan
            ),
            eastInterFanWidth=(
                eastInterFanDim if eastInterFanDim is not None else interFanSpan
            ),
            westIntraFanWidth=(
                westIntraFanDim
                if westIntraFanDim is not None
                else _FAN_IN_OUT_SPAN
            ),
            eastIntraFanWidth=(
                eastIntraFanDim
                if eastIntraFanDim is not None
                else _FAN_IN_OUT_SPAN
            ),
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
        interLaneSpan=interLaneSpan,
        interFanSpan=interFanSpan,
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
    intraLaneSpan: int = 1,
    latNOffset: int = 4,
    latSOffset: int | None = None,
    interLaneSpan: int = 1,
    interFanSpan: int = 1,
    westInterFanWidth: int | None = None,
    eastInterFanWidth: int | None = None,
    westIntraFanWidth: int | None = None,
    eastIntraFanWidth: int | None = None,
) -> Result[RoutingZoneRegionSet]:
    """Build logical west-to-east region set for one planned zone.

    Implements the canonical 20-band concentric zone geometry.  Bands are
    ordered outside-in on every side: inter_routing → inter_fan → chip_terminal
    → intra_fan → intra_routing.  All regions carry a cardinal side qualifier.

    Horizontal layout (left→right, W=westTerminalWidth, E=eastTerminalWidth,
                       K=crossbarWidth):
      col 0            : West/inter_routing_longitude
                         ← full height (inter-zone pillar)
      col 1            : West/inter_routing_fan_in_out  ┐
      cols 2..1+W      : West/chip_terminal              │ crossbar rows only
      col 2+W          : West/intra_routing_fan_in_out  │ (rows 5..4+C)
      col 3+W          : West/intra_routing_longitude   │
      cols 4+W..3+W+K  : [blank crossbar — K cols wide] │
      col 4+W+K        : East/intra_routing_longitude   │
      col 5+W+K        : East/intra_routing_fan_in_out  │
      cols 6+W+K..5+W+K+E: East/chip_terminal           │
      col 6+W+K+E      : East/inter_routing_fan_in_out  ┘
      col 7+W+K+E      : East/inter_routing_longitude
                         ← full height (inter-zone pillar)
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
    intraSpan: int = intraLaneSpan
    L: int = interLaneSpan     # seam-side INTER_ROUTING_LONGITUDE width
    FWI: int = (
        westInterFanWidth
        if westInterFanWidth is not None
        else interFanSpan
    )
    FEI: int = (
        eastInterFanWidth
        if eastInterFanWidth is not None
        else interFanSpan
    )
    FWI_INTRA: int = (
        westIntraFanWidth
        if westIntraFanWidth is not None
        else _FAN_IN_OUT_SPAN
    )
    FEI_INTRA: int = (
        eastIntraFanWidth
        if eastIntraFanWidth is not None
        else _FAN_IN_OUT_SPAN
    )
    H: int = zoneVerticalSpan  # = 10 + C
    C: int = H - 10            # chip-stack height (>= 1)
    S: int = zoneHorizontalSpan
    X: int = L + FWI + W + FWI_INTRA
    innerCorridorWidth: int = 2 * intraSpan + K
    LN: int = latNOffset
    LS: int = latSOffset if latSOffset is not None else 5 + C
    northLatStart: int = LN - intraSpan + 1
    southLatStart: int = LS

    regionSpecs: tuple[
        tuple[RoutingZoneRegionKind, RoutingZoneRegionSide | None, int, int, int, int],
        ...,
    ] = (
        # ── West longitude bands (vertical columns) ──
        # INTER_LONGITUDE now carries the seam lane field itself, while
        # INTER_FAN_IN_OUT includes both lane capacity and two structural
        # columns used to materialize breakout/tee/elbow geometry near the chip.
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         0, 1, L, H - 2),                      # seam lane corridor
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         L, 5, FWI, C),                        # crossbar only
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.WEST,
         L + FWI, 5, W, C),                    # crossbar only
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         L + FWI + W, 5, FWI_INTRA, C),        # crossbar only
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         X, 5, intraSpan, C),                  # crossbar only
        # cols X .. X+K-1 are blank crossbar space (K cols wide)
        # ── East longitude bands (vertical columns) ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         X + intraSpan + K, 5, intraSpan, C),  # crossbar only
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         X + intraSpan + K + intraSpan, 5, FEI_INTRA, C),      # crossbar only
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.EAST,
         X + intraSpan + K + intraSpan + FEI_INTRA, 5, E, C),  # crossbar only
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         X + intraSpan + K + intraSpan + FEI_INTRA + E, 5, FEI, C), # crossbar only
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         X + intraSpan + K + intraSpan + FEI_INTRA + E + FEI,
         1, L, H - 2),                               # seam lane corridor
        # ── North latitude bands ──
        # INTER_ROUTING_LATITUDE spans the full zone width (pillar-to-pillar) —
        # it is the inter-zone seam row.  All inner bands are confined to the
        # blank crossbar corridor (cols X..X+K) — the same K-wide transit space
        # that separates the W and E chip terminal columns.
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         L, 0, S - 2 * L, 1),                      # seam — skip pillar cols
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         X, 1, innerCorridorWidth, 1),            # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.NORTH,
         X, 2, innerCorridorWidth, 1),            # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         X, 3, innerCorridorWidth, 1),            # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         X, northLatStart, innerCorridorWidth, intraSpan),
                                                     # centroid-anchored lane field
        # ── South latitude bands ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         X, southLatStart, innerCorridorWidth, intraSpan),
                                                     # centroid-anchored lane field
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         X, 6 + C, innerCorridorWidth, 1),        # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.SOUTH,
         X, 7 + C, innerCorridorWidth, 1),        # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         X, 8 + C, innerCorridorWidth, 1),        # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         L, 9 + C, S - 2 * L, 1),                  # seam — skip pillar cols
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
    interLaneSpan: int = 1,
    interFanSpan: int = 1,
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
    L: int = interLaneSpan      # seam-side INTER_ROUTING_LATITUDE height
    F: int = interFanSpan       # seam-side INTER_ROUTING_FAN_IN_OUT height
    T: int = zoneVerticalSpan   # = N + So + K + 2*F + 2*L + 4
    W_zone: int = zoneHorizontalSpan
    CW: int = W_zone - (2 * L + 2 * F + 6)
    Y: int = L + F + N + 2
    X: int = L + F + 3

    regionSpecs: tuple[
        tuple[RoutingZoneRegionKind, RoutingZoneRegionSide | None, int, int, int, int],
        ...,
    ] = (
        # ── West longitude bands (vertical columns) ──
        # Only INTER_LONGITUDE spans full zone height.  All other vertical
        # bands are confined to the blank crossbar corridor (rows Y..Y+K) —
        # the same K-tall transit space between the N and S chip terminal rows.
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         0, 1, L, T - 2),                   # pillar — skip seam rows
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         L, Y, F, K),                       # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.WEST,
         L + F, Y, _CHANNEL_SPAN, K),       # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST,
         L + F + 1, Y, _FAN_IN_OUT_SPAN, K),# crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST,
         L + F + 2, Y, _CHANNEL_SPAN, K),   # crossbar corridor
        # ── East longitude bands (vertical columns) ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         X + CW, Y, _CHANNEL_SPAN, K),      # crossbar corridor
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         X + CW + 1, Y, _FAN_IN_OUT_SPAN, K),   # crossbar corridor
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.EAST,
         X + CW + 2, Y, _CHANNEL_SPAN, K),  # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST,
         X + CW + 3, Y, F, K),              # crossbar corridor
        (RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST,
         X + CW + 3 + F, 1, L, T - 2),      # pillar — skip seam rows
        # ── North latitude bands ──
        # INTER_ROUTING_LATITUDE spans the full zone width (pillar-to-pillar).
        # All inner bands are confined to the chip-terminal column range
        # (cols 5..5+CW) so they align with where chips sit.
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         L, 0, W_zone - 2 * L, L),          # seam — skip pillar cols
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         X, L, CW, F),                      # chip-area width
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.NORTH,
         X, L + F, CW, N),                  # chip-area width (unchanged)
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH,
         X, L + F + N, CW, 1),              # chip-area width
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH,
         X, L + F + N + 1, CW, 1),          # chip-area width
        # rows N+4..N+3+K are blank crossbar space (K rows tall)
        # ── South latitude bands ──
        (RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         X, Y + K, CW, 1),                  # chip-area width
        (RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         X, Y + K + 1, CW, 1),              # chip-area width
        (RoutingZoneRegionKind.CHIP_TERMINAL, RoutingZoneRegionSide.SOUTH,
         X, Y + K + 2, CW, So),             # chip-area width (unchanged)
        (RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH,
         X, Y + K + 2 + So, CW, F),         # chip-area width
        (RoutingZoneRegionKind.INTER_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH,
         L, Y + K + 2 + So + F, W_zone - 2 * L, L), # seam — skip pillar cols
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
    interLaneSpan: int = 1,
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
                interLaneSpan=interLaneSpan,
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
    interLaneSpan: int = 1,
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
            horizontalSpan=interLaneSpan,
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
        verticalSpan=interLaneSpan,
    )
