"""Logical placement planning for assigned routing-zone worlds.

This module turns a chip-to-zone assignment set into a logically placed
`RoutingZoneGrid`. The output is not final render geometry. It is an explicit
planning geometry that gives each zone:

- a stable outer frame in world coordinates
- explicit owned region geometry
- ordered chip placements in terminal regions

The current implementation supports only the simple one-dimensional regime that
already underlies the assignment builder.
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
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack

_TERMINAL_SPAN: int = 1
_FAN_IN_OUT_SPAN: int = 1
_CHANNEL_SPAN: int = 1
_INTERCONNECT_SPAN: int = 1


def routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    routingZoneGrid: RoutingZoneGrid,
) -> Result[RoutingZoneGrid]:
    """Build logically placed routing-zone world from assignments and topology."""

    if not _simpleGridShape_isSupportedCheck(routingZoneGrid):
        return resultErr_build()

    routingZonesMutable: list[RoutingZone] = []
    if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        horizontalCursor: int = 0
        columnIndex: int
        for columnIndex in range(1, routingZoneGrid.gridSize.columnIndex + 1):
            routingZoneId: RoutingZoneId = RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=1)
            )
            originalZoneResult: Result[RoutingZone] = (
                routingZoneGrid.routingZoneSet.zoneResult_get(routingZoneId)
            )
            if not result_isOkCheck(originalZoneResult):
                return resultErr_build()
            plannedZoneResult: Result[RoutingZone] = (
                _plannedRoutingZoneResult_build(
                    routingZoneId=routingZoneId,
                    routingZoneSense=routingZoneGrid.worldSense,
                    channelSenseForZone=originalZoneResult.value.channelSense,
                    routingZoneAssignmentSet=routingZoneAssignmentSet,
                    horizontalStart=horizontalCursor,
                    verticalStart=0,
                )
            )
            if not result_isOkCheck(plannedZoneResult):
                return resultErr_build()
            routingZonesMutable.append(plannedZoneResult.value)
            horizontalCursor = (
                plannedZoneResult.value.routingZoneFrame.horizontalEnd_calculate()
                + _INTERCONNECT_SPAN
            )
    else:
        verticalCursor: int = 0
        rowIndex: int
        for rowIndex in range(1, routingZoneGrid.gridSize.rowIndex + 1):
            routingZoneId = RoutingZoneId(
                id=GridCoord(columnIndex=1, rowIndex=rowIndex)
            )
            originalZoneResult = routingZoneGrid.routingZoneSet.zoneResult_get(
                routingZoneId
            )
            if not result_isOkCheck(originalZoneResult):
                return resultErr_build()
            plannedZoneResult = _plannedRoutingZoneResult_build(
                routingZoneId=routingZoneId,
                routingZoneSense=routingZoneGrid.worldSense,
                channelSenseForZone=originalZoneResult.value.channelSense,
                routingZoneAssignmentSet=routingZoneAssignmentSet,
                horizontalStart=0,
                verticalStart=verticalCursor,
            )
            if not result_isOkCheck(plannedZoneResult):
                return resultErr_build()
            routingZonesMutable.append(plannedZoneResult.value)
            verticalCursor = (
                plannedZoneResult.value.routingZoneFrame.verticalEnd_calculate()
                + _INTERCONNECT_SPAN
            )

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


def _simpleGridShape_isSupportedCheck(routingZoneGrid: RoutingZoneGrid) -> bool:
    """Return whether logical placement planning supports this grid shape."""

    if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        if routingZoneGrid.gridSize.rowIndex != 1:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.placement.world_shape.unsupported",
                message=(
                    "Current placement planning supports only one-row "
                    "WestToEast worlds"
                ),
            )
            return False
        return True

    if routingZoneGrid.gridSize.columnIndex != 1:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.placement.world_shape.unsupported",
            message=(
                "Current placement planning supports only one-column "
                "NorthToSouth worlds"
            ),
        )
        return False
    return True


def _plannedRoutingZoneResult_build(
    routingZoneId: RoutingZoneId,
    routingZoneSense: RoutingZoneSense,
    channelSenseForZone: RoutingZoneChannelSense,
    routingZoneAssignmentSet: RoutingZoneAssignmentSet,
    horizontalStart: int,
    verticalStart: int,
) -> Result[RoutingZone]:
    """Build one logically placed routing zone from assignments."""

    chipPlacementSetResult = _chipPlacementSetResult_buildForZone(
        routingZoneId=routingZoneId,
        routingZoneAssignmentSet=routingZoneAssignmentSet,
    )
    if not result_isOkCheck(chipPlacementSetResult):
        return resultErr_build()

    regionMetrics = _zoneMetrics_build(
        routingZoneId=routingZoneId,
        routingZoneSense=routingZoneSense,
        routingZoneAssignmentSet=routingZoneAssignmentSet,
    )

    routingZoneFrameResult: Result[RoutingZoneFrame] = routingZoneFrameResult_build(
        horizontalStart=horizontalStart,
        verticalStart=verticalStart,
        horizontalSpan=regionMetrics["zoneHorizontalSpan"],
        verticalSpan=regionMetrics["zoneVerticalSpan"],
    )
    if not result_isOkCheck(routingZoneFrameResult):
        return resultErr_build()

    routingZoneRegionSetResult: Result[RoutingZoneRegionSet] = (
        _routingZoneRegionSetResult_buildForZone(
            routingZoneId=routingZoneId,
            routingZoneSense=routingZoneSense,
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            zoneHorizontalSpan=regionMetrics["zoneHorizontalSpan"],
            zoneVerticalSpan=regionMetrics["zoneVerticalSpan"],
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
) -> dict[str, int]:
    """Build simple logical sizing metrics from assignment counts."""

    startSide: RoutingZoneRegionSide
    endSide: RoutingZoneRegionSide
    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        startSide = RoutingZoneRegionSide.WEST
        endSide = RoutingZoneRegionSide.EAST
    else:
        startSide = RoutingZoneRegionSide.NORTH
        endSide = RoutingZoneRegionSide.SOUTH

    startCount: int = len(
        routingZoneAssignmentSet.assignmentsForZoneAndSide_get(
            routingZoneId,
            startSide,
        )
    )
    endCount: int = len(
        routingZoneAssignmentSet.assignmentsForZoneAndSide_get(
            routingZoneId,
            endSide,
        )
    )
    maxTerminalCount: int = max(startCount, endCount, 1)

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return {
            "zoneHorizontalSpan": 8,
            "zoneVerticalSpan": maxTerminalCount,
        }
    return {
        "zoneHorizontalSpan": maxTerminalCount,
        "zoneVerticalSpan": 8,
    }


def _routingZoneRegionSetResult_buildForZone(
    routingZoneId: RoutingZoneId,
    routingZoneSense: RoutingZoneSense,
    horizontalStart: int,
    verticalStart: int,
    zoneHorizontalSpan: int,
    zoneVerticalSpan: int,
) -> Result[RoutingZoneRegionSet]:
    """Build logical explicit region geometry for one planned zone."""

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return _westEastRegionSetResult_buildForZone(
            routingZoneId=routingZoneId,
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            zoneVerticalSpan=zoneVerticalSpan,
        )
    return _northSouthRegionSetResult_buildForZone(
        routingZoneId=routingZoneId,
        horizontalStart=horizontalStart,
        verticalStart=verticalStart,
        zoneHorizontalSpan=zoneHorizontalSpan,
    )


def _westEastRegionSetResult_buildForZone(
    routingZoneId: RoutingZoneId,
    horizontalStart: int,
    verticalStart: int,
    zoneVerticalSpan: int,
) -> Result[RoutingZoneRegionSet]:
    """Build logical west-to-east region set for one planned zone."""

    regionSpecs: tuple[
        tuple[RoutingZoneRegionKind, RoutingZoneRegionSide | None, int, int, int, int],
        ...,
    ] = (
        (
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
            0,
            0,
            _FAN_IN_OUT_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.WEST,
            1,
            0,
            _TERMINAL_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
            2,
            0,
            _FAN_IN_OUT_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            None,
            3,
            0,
            _CHANNEL_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            None,
            4,
            0,
            _CHANNEL_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
            5,
            0,
            _FAN_IN_OUT_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.EAST,
            6,
            0,
            _TERMINAL_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
            7,
            0,
            _FAN_IN_OUT_SPAN,
            zoneVerticalSpan,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            None,
            3,
            max((zoneVerticalSpan - 1) // 2, 0),
            _CHANNEL_SPAN,
            1,
        ),
        (
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            None,
            4,
            max((zoneVerticalSpan - 1) // 2, 0),
            _CHANNEL_SPAN,
            1,
        ),
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
) -> Result[RoutingZoneRegionSet]:
    """Build logical north-to-south region set for one planned zone."""

    centerColumnIndex: int = max((zoneHorizontalSpan - 1) // 2, 0)
    regionSpecs: tuple[
        tuple[RoutingZoneRegionKind, RoutingZoneRegionSide | None, int, int, int, int],
        ...,
    ] = (
        (
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.NORTH,
            0,
            0,
            zoneHorizontalSpan,
            _FAN_IN_OUT_SPAN,
        ),
        (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.NORTH,
            0,
            1,
            zoneHorizontalSpan,
            _TERMINAL_SPAN,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.NORTH,
            0,
            2,
            zoneHorizontalSpan,
            _FAN_IN_OUT_SPAN,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            None,
            0,
            3,
            zoneHorizontalSpan,
            _CHANNEL_SPAN,
        ),
        (
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            None,
            0,
            4,
            zoneHorizontalSpan,
            _CHANNEL_SPAN,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.SOUTH,
            0,
            5,
            zoneHorizontalSpan,
            _FAN_IN_OUT_SPAN,
        ),
        (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.SOUTH,
            0,
            6,
            zoneHorizontalSpan,
            _TERMINAL_SPAN,
        ),
        (
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.SOUTH,
            0,
            7,
            zoneHorizontalSpan,
            _FAN_IN_OUT_SPAN,
        ),
        (
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            None,
            centerColumnIndex,
            3,
            1,
            2,
        ),
        (
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            None,
            centerColumnIndex,
            4,
            1,
            2,
        ),
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
