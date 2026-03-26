"""Grid-level long-haul routing solver for the new SignalFlow engine.

This module realizes `GRID_LONG_HAUL` call obligations against the placed
world topology. The current implementation now supports both the simple
one-dimensional regimes and rectangular Manhattan paths across the placed
`RoutingZoneGrid`.
"""
from __future__ import annotations

from signalflow.models import (
    CallRouteObligation,
    CallRouteObligationSet,
    ChipPlacement,
    CircuitDocument,
    Result,
    RouteObligationScope,
    RoutingZone,
    RoutingZoneGrid,
    RoutingZoneGridPathPolicy,
    RoutingZoneGridRouteSolveKind,
    RoutingZoneGridSolvedRoute,
    RoutingZoneGridSolvedRouteSet,
    RoutingZoneInterconnect,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    RoutingZoneSense,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneGridSolvedRouteResult_build,
    routingZoneGridSolvedRouteSetResult_build,
    routingZoneRegionByIdResult_get,
    routingZoneRegionForKindAndSideResult_get,
    routingZoneRoutePointResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


def routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
    pathPolicy: RoutingZoneGridPathPolicy = RoutingZoneGridPathPolicy.HORIZONTAL_FIRST,
) -> Result[RoutingZoneGridSolvedRouteSet]:
    """Build solved long-haul routes from placed geometry and grid obligations."""

    solvedRoutesMutable: list[RoutingZoneGridSolvedRoute] = []
    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.GRID_LONG_HAUL
        ):
            continue
        solvedRouteResult: Result[RoutingZoneGridSolvedRoute] = (
            _routingZoneGridSolvedRouteResult_buildFromObligation(
                circuitDocument=circuitDocument,
                placedRoutingZoneGrid=placedRoutingZoneGrid,
                callRouteObligation=callRouteObligation,
                pathPolicy=pathPolicy,
            )
        )
        if not result_isOkCheck(solvedRouteResult):
            return resultErr_build()
        solvedRoutesMutable.append(solvedRouteResult.value)
    return routingZoneGridSolvedRouteSetResult_build(
        routingZoneGridSolvedRoutes=tuple(solvedRoutesMutable)
    )


def _routingZoneGridSolvedRouteResult_buildFromObligation(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligation: CallRouteObligation,
    pathPolicy: RoutingZoneGridPathPolicy,
) -> Result[RoutingZoneGridSolvedRoute]:
    """Build one solved long-haul route from one world-scale obligation."""

    sourceChipResult = circuitDocument.circuitChipSet.chipResult_get(
        callRouteObligation.sourceChipRef.chipId
    )
    if not result_isOkCheck(sourceChipResult):
        return resultErr_build()
    destinationChipResult = circuitDocument.circuitChipSet.chipResult_get(
        callRouteObligation.destinationChipRef.chipId
    )
    if not result_isOkCheck(destinationChipResult):
        return resultErr_build()

    sourceZoneResult = _zoneOwningChipResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        chipRef=callRouteObligation.sourceChipRef,
    )
    if not result_isOkCheck(sourceZoneResult):
        return resultErr_build()
    destinationZoneResult = _zoneOwningChipResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        chipRef=callRouteObligation.destinationChipRef,
    )
    if not result_isOkCheck(destinationZoneResult):
        return resultErr_build()

    routingZonePathResult = placedRoutingZoneGrid.pathBetweenZonesResult_build(
        sourceZoneResult.value.routingZoneId,
        destinationZoneResult.value.routingZoneId,
        pathPolicy=pathPolicy,
    )
    if not result_isOkCheck(routingZonePathResult):
        return resultErr_build()
    interconnectSequenceResult = (
        placedRoutingZoneGrid.interconnectSequenceForPathResult_build(
            routingZonePathResult.value
        )
    )
    if not result_isOkCheck(interconnectSequenceResult):
        return resultErr_build()

    sourcePlacementResult = (
        sourceZoneResult.value.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.sourceChipRef
        )
    )
    if not result_isOkCheck(sourcePlacementResult):
        return resultErr_build()
    destinationPlacementResult = (
        destinationZoneResult.value.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.destinationChipRef
        )
    )
    if not result_isOkCheck(destinationPlacementResult):
        return resultErr_build()
    geometryResult = _gridGeometryResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        routingZonePath=routingZonePathResult.value,
        interconnectSequence=interconnectSequenceResult.value.routingZoneInterconnects,
        sourcePlacement=sourcePlacementResult.value,
        destinationPlacement=destinationPlacementResult.value,
    )
    if not result_isOkCheck(geometryResult):
        return resultErr_build()

    return routingZoneGridSolvedRouteResult_build(
        sourceChipRef=callRouteObligation.sourceChipRef,
        destinationChipRef=callRouteObligation.destinationChipRef,
        childCallIndex=callRouteObligation.childCallIndex,
        routingZonePath=routingZonePathResult.value,
        traversedInterconnectIds=tuple(
            interconnect.routingZoneInterconnectId
            for interconnect in (
                interconnectSequenceResult.value.routingZoneInterconnects
            )
        ),
        traversedRegionIds=geometryResult.value[1],
        routePoints=geometryResult.value[0],
        solveKind=geometryResult.value[2],
    )


def _zoneOwningChipResult_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    chipRef,
) -> Result[RoutingZone]:
    """Build the placed routing zone that owns one chip."""

    routingZone: RoutingZone
    for routingZone in placedRoutingZoneGrid.routingZoneSet.routingZones:
        placement = routingZone.chipPlacementSet.placementForChipOrNone_get(chipRef)
        if placement is not None:
            return resultOk_build(routingZone)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.grid_solver.missing_chip_zone",
        message="Placed RoutingZoneGrid does not contain the requested chip",
    )
    return resultErr_build()


def _gridGeometryResult_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    routingZonePath,
    interconnectSequence: tuple[RoutingZoneInterconnect, ...],
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
) -> Result[
    tuple[
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
        RoutingZoneGridRouteSolveKind,
    ]
]:
    """Build route points, traversed regions, and solve kind for one route."""

    if (
        placedRoutingZoneGrid.gridSize.rowIndex != 1
        and placedRoutingZoneGrid.gridSize.columnIndex != 1
    ):
        return _rectangularGridGeometryResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            routingZonePath=routingZonePath,
            interconnectSequence=interconnectSequence,
            sourcePlacement=sourcePlacement,
            destinationPlacement=destinationPlacement,
        )
    if placedRoutingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        return _horizontalGridGeometryResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            routingZonePath=routingZonePath,
            interconnectSequence=interconnectSequence,
            sourcePlacement=sourcePlacement,
        )
    return _verticalGridGeometryResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        routingZonePath=routingZonePath,
        interconnectSequence=interconnectSequence,
        sourcePlacement=sourcePlacement,
    )


def _horizontalGridGeometryResult_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    routingZonePath,
    interconnectSequence: tuple[RoutingZoneInterconnect, ...],
    sourcePlacement: ChipPlacement,
) -> Result[
    tuple[
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
        RoutingZoneGridRouteSolveKind,
    ]
]:
    """Build explicit long-haul geometry for current west-east worlds."""

    sourceZoneResult = placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZonePath.zoneIds[0]
    )
    if not result_isOkCheck(sourceZoneResult):
        return resultErr_build()
    pathDirectionSideResult = _horizontalDirectionSideResult_build(
        routingZonePath.zoneIds[0],
        routingZonePath.zoneIds[-1],
    )
    if not result_isOkCheck(pathDirectionSideResult):
        return resultErr_build()
    pathDirectionSide = pathDirectionSideResult.value
    entrySide = (
        RoutingZoneRegionSide.WEST
        if pathDirectionSide is RoutingZoneRegionSide.EAST
        else RoutingZoneRegionSide.EAST
    )
    sourceFanRegionResult = (
        routingZoneRegionForKindAndSideResult_get(
            sourceZoneResult.value,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            pathDirectionSide,
        )
    )
    if not result_isOkCheck(sourceFanRegionResult):
        return resultErr_build()
    sourceRow: int = (
        sourceFanRegionResult.value.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex
    )
    routePointsMutable: list[RoutingZoneRoutePoint] = []
    traversedRegionIdsMutable: list[RoutingZoneRegionId] = [
        sourceFanRegionResult.value.routingZoneRegionId
    ]
    startPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=sourceFanRegionResult.value.routingZoneRegionFrame.horizontalStart,
        verticalIndex=sourceRow,
    )
    if not result_isOkCheck(startPointResult):
        return resultErr_build()
    routePointsMutable.append(startPointResult.value)

    currentRow: int = sourceRow
    interconnectIndex: int
    for interconnectIndex, interconnect in enumerate(interconnectSequence):
        interconnectPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=interconnect.routingZoneInterconnectFrame.horizontalStart,
            verticalIndex=currentRow,
        )
        if not result_isOkCheck(interconnectPointResult):
            return resultErr_build()
        routePointsMutable.append(interconnectPointResult.value)

        nextZoneId = routingZonePath.zoneIds[interconnectIndex + 1]
        nextZoneResult = placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            nextZoneId
        )
        if not result_isOkCheck(nextZoneResult):
            return resultErr_build()
        isFinalZone: bool = interconnectIndex + 1 == len(routingZonePath.zoneIds) - 1

        nextEntryFanRegionResult = (
            routingZoneRegionForKindAndSideResult_get(
                nextZoneResult.value,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                entrySide,
            )
        )
        if not result_isOkCheck(nextEntryFanRegionResult):
            return resultErr_build()
        nextEntryFanPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=nextEntryFanRegionResult.value.routingZoneRegionFrame.horizontalStart,
            verticalIndex=currentRow,
        )
        if not result_isOkCheck(nextEntryFanPointResult):
            return resultErr_build()
        routePointsMutable.append(nextEntryFanPointResult.value)
        traversedRegionIdsMutable.append(
            nextEntryFanRegionResult.value.routingZoneRegionId
        )

        if isFinalZone:
            break
        else:
            passThroughRegionResult = (
                routingZoneRegionForKindAndSideResult_get(
                    nextZoneResult.value,
                    RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                    RoutingZoneRegionSide.WEST,
                )
            )
            if not result_isOkCheck(passThroughRegionResult):
                return resultErr_build()
            passThroughPointResult = routingZoneRoutePointResult_build(
                horizontalIndex=passThroughRegionResult.value.routingZoneRegionFrame.horizontalStart,
                verticalIndex=currentRow,
            )
            if not result_isOkCheck(passThroughPointResult):
                return resultErr_build()
            routePointsMutable.append(passThroughPointResult.value)
            traversedRegionIdsMutable.append(
                passThroughRegionResult.value.routingZoneRegionId
            )

    return resultOk_build(
        (
            tuple(routePointsMutable),
            tuple(traversedRegionIdsMutable),
            RoutingZoneGridRouteSolveKind.LINEAR_HORIZONTAL,
        )
    )


def _verticalGridGeometryResult_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    routingZonePath,
    interconnectSequence: tuple[RoutingZoneInterconnect, ...],
    sourcePlacement: ChipPlacement,
) -> Result[
    tuple[
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
        RoutingZoneGridRouteSolveKind,
    ]
]:
    """Build explicit long-haul geometry for current north-south worlds."""

    sourceZoneResult = placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZonePath.zoneIds[0]
    )
    if not result_isOkCheck(sourceZoneResult):
        return resultErr_build()
    pathDirectionSideResult = _verticalDirectionSideResult_build(
        routingZonePath.zoneIds[0],
        routingZonePath.zoneIds[-1],
    )
    if not result_isOkCheck(pathDirectionSideResult):
        return resultErr_build()
    pathDirectionSide = pathDirectionSideResult.value
    entrySide = (
        RoutingZoneRegionSide.NORTH
        if pathDirectionSide is RoutingZoneRegionSide.SOUTH
        else RoutingZoneRegionSide.SOUTH
    )
    sourceFanRegionResult = (
        routingZoneRegionForKindAndSideResult_get(
            sourceZoneResult.value,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            pathDirectionSide,
        )
    )
    if not result_isOkCheck(sourceFanRegionResult):
        return resultErr_build()
    sourceColumn: int = (
        sourceFanRegionResult.value.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex
    )
    routePointsMutable: list[RoutingZoneRoutePoint] = []
    traversedRegionIdsMutable: list[RoutingZoneRegionId] = [
        sourceFanRegionResult.value.routingZoneRegionId
    ]
    startPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=sourceColumn,
        verticalIndex=sourceFanRegionResult.value.routingZoneRegionFrame.verticalStart,
    )
    if not result_isOkCheck(startPointResult):
        return resultErr_build()
    routePointsMutable.append(startPointResult.value)

    currentColumn: int = sourceColumn
    interconnectIndex: int
    for interconnectIndex, interconnect in enumerate(interconnectSequence):
        interconnectPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=currentColumn,
            verticalIndex=interconnect.routingZoneInterconnectFrame.verticalStart,
        )
        if not result_isOkCheck(interconnectPointResult):
            return resultErr_build()
        routePointsMutable.append(interconnectPointResult.value)

        nextZoneId = routingZonePath.zoneIds[interconnectIndex + 1]
        nextZoneResult = placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            nextZoneId
        )
        if not result_isOkCheck(nextZoneResult):
            return resultErr_build()
        isFinalZone: bool = interconnectIndex + 1 == len(routingZonePath.zoneIds) - 1

        nextEntryFanRegionResult = (
            routingZoneRegionForKindAndSideResult_get(
                nextZoneResult.value,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                entrySide,
            )
        )
        if not result_isOkCheck(nextEntryFanRegionResult):
            return resultErr_build()
        nextEntryFanPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=currentColumn,
            verticalIndex=nextEntryFanRegionResult.value.routingZoneRegionFrame.verticalStart,
        )
        if not result_isOkCheck(nextEntryFanPointResult):
            return resultErr_build()
        routePointsMutable.append(nextEntryFanPointResult.value)
        traversedRegionIdsMutable.append(
            nextEntryFanRegionResult.value.routingZoneRegionId
        )

        if isFinalZone:
            break
        else:
            passThroughRegionResult = (
                routingZoneRegionForKindAndSideResult_get(
                    nextZoneResult.value,
                    RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
                    RoutingZoneRegionSide.NORTH,
                )
            )
            if not result_isOkCheck(passThroughRegionResult):
                return resultErr_build()
            passThroughPointResult = routingZoneRoutePointResult_build(
                horizontalIndex=currentColumn,
                verticalIndex=passThroughRegionResult.value.routingZoneRegionFrame.verticalStart,
            )
            if not result_isOkCheck(passThroughPointResult):
                return resultErr_build()
            routePointsMutable.append(passThroughPointResult.value)
            traversedRegionIdsMutable.append(
                passThroughRegionResult.value.routingZoneRegionId
            )

    return resultOk_build(
        (
            tuple(routePointsMutable),
            tuple(traversedRegionIdsMutable),
            RoutingZoneGridRouteSolveKind.LINEAR_VERTICAL,
        )
    )


def _rectangularGridGeometryResult_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    routingZonePath,
    interconnectSequence: tuple[RoutingZoneInterconnect, ...],
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
) -> Result[
    tuple[
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
        RoutingZoneGridRouteSolveKind,
    ]
]:
    """Build explicit Manhattan geometry for rectangular placed worlds."""

    sourceZoneResult = placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZonePath.zoneIds[0]
    )
    if not result_isOkCheck(sourceZoneResult):
        return resultErr_build()
    destinationZoneResult = placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZonePath.zoneIds[-1]
    )
    if not result_isOkCheck(destinationZoneResult):
        return resultErr_build()

    sourcePoint: RoutingZoneRoutePoint = _routePointForChipPlacement_build(
        routingZone=sourceZoneResult.value,
        chipPlacement=sourcePlacement,
    )
    destinationPoint: RoutingZoneRoutePoint = _routePointForChipPlacement_build(
        routingZone=destinationZoneResult.value,
        chipPlacement=destinationPlacement,
    )

    currentPoint: RoutingZoneRoutePoint = sourcePoint
    routePointsMutable: list[RoutingZoneRoutePoint] = [currentPoint]

    interconnect: RoutingZoneInterconnect
    for interconnect in interconnectSequence:
        interconnectPointResult = _pointAtInterconnectResult_build(
            interconnect=interconnect,
            currentPoint=currentPoint,
        )
        if not result_isOkCheck(interconnectPointResult):
            return resultErr_build()
        currentPoint = interconnectPointResult.value
        routePointsMutable.append(currentPoint)

    if currentPoint.horizontalIndex != destinationPoint.horizontalIndex:
        horizontalAlignPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=destinationPoint.horizontalIndex,
            verticalIndex=currentPoint.verticalIndex,
        )
        if not result_isOkCheck(horizontalAlignPointResult):
            return resultErr_build()
        currentPoint = horizontalAlignPointResult.value
        routePointsMutable.append(currentPoint)
    if currentPoint.verticalIndex != destinationPoint.verticalIndex:
        verticalAlignPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=currentPoint.horizontalIndex,
            verticalIndex=destinationPoint.verticalIndex,
        )
        if not result_isOkCheck(verticalAlignPointResult):
            return resultErr_build()
        currentPoint = verticalAlignPointResult.value
        routePointsMutable.append(currentPoint)
    if currentPoint != destinationPoint:
        routePointsMutable.append(destinationPoint)

    return resultOk_build(
        (
            tuple(routePointsMutable),
            (),
            RoutingZoneGridRouteSolveKind.MANHATTAN_TURNING,
        )
    )


def _horizontalDirectionSideResult_build(
    sourceZoneId,
    destinationZoneId,
) -> Result[RoutingZoneRegionSide]:
    """Build east/west direction from one world-zone id pair."""

    sourceGridCoordResult = sourceZoneId.worldGridCoordResult_get()
    if not result_isOkCheck(sourceGridCoordResult):
        return resultErr_build()
    destinationGridCoordResult = destinationZoneId.worldGridCoordResult_get()
    if not result_isOkCheck(destinationGridCoordResult):
        return resultErr_build()
    if (
        sourceGridCoordResult.value.columnIndex
        < destinationGridCoordResult.value.columnIndex
    ):
        return resultOk_build(RoutingZoneRegionSide.EAST)
    return resultOk_build(RoutingZoneRegionSide.WEST)


def _verticalDirectionSideResult_build(
    sourceZoneId,
    destinationZoneId,
) -> Result[RoutingZoneRegionSide]:
    """Build north/south direction from one world-zone id pair."""

    sourceGridCoordResult = sourceZoneId.worldGridCoordResult_get()
    if not result_isOkCheck(sourceGridCoordResult):
        return resultErr_build()
    destinationGridCoordResult = destinationZoneId.worldGridCoordResult_get()
    if not result_isOkCheck(destinationGridCoordResult):
        return resultErr_build()
    if sourceGridCoordResult.value.rowIndex < destinationGridCoordResult.value.rowIndex:
        return resultOk_build(RoutingZoneRegionSide.SOUTH)
    return resultOk_build(RoutingZoneRegionSide.NORTH)


def _pointAtInterconnectResult_build(
    interconnect: RoutingZoneInterconnect,
    currentPoint: RoutingZoneRoutePoint,
) -> Result[RoutingZoneRoutePoint]:
    """Build the route point at one interconnect seam."""

    interconnectAxisResult = interconnect.interconnectAxisResult_get()
    if not result_isOkCheck(interconnectAxisResult):
        return resultErr_build()
    if interconnectAxisResult.value.value == "horizontal":
        return routingZoneRoutePointResult_build(
            horizontalIndex=interconnect.routingZoneInterconnectFrame.horizontalStart,
            verticalIndex=currentPoint.verticalIndex,
        )
    return routingZoneRoutePointResult_build(
        horizontalIndex=currentPoint.horizontalIndex,
        verticalIndex=interconnect.routingZoneInterconnectFrame.verticalStart,
    )


def _routePointForChipPlacement_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> RoutingZoneRoutePoint:
    """Build the planning-world point for one placed chip."""

    regionResult = routingZoneRegionByIdResult_get(
        routingZone,
        chipPlacement.chipTerminalRegionId,
    )
    assert result_isOkCheck(regionResult)
    regionFrame = regionResult.value.routingZoneRegionFrame
    side = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    assert side is not None
    if side in {RoutingZoneRegionSide.WEST, RoutingZoneRegionSide.EAST}:
        return RoutingZoneRoutePoint(
            horizontalIndex=regionFrame.horizontalStart,
            verticalIndex=regionFrame.verticalStart + chipPlacement.orderIndex,
        )
    return RoutingZoneRoutePoint(
        horizontalIndex=regionFrame.horizontalStart + chipPlacement.orderIndex,
        verticalIndex=regionFrame.verticalStart,
    )
