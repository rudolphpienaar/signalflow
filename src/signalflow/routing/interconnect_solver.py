"""Interconnect seam routing solver for the new SignalFlow engine.

This module realizes `SEAM_CROSSING` call obligations against one placed
`RoutingZoneInterconnect` plus the neighboring inter-routing fan-in/out
regions. It produces explicit planning-grid seam geometry.
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
    RoutingZoneInterconnect,
    RoutingZoneInterconnectAxis,
    RoutingZoneInterconnectRouteSolveKind,
    RoutingZoneInterconnectSolvedRoute,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneRegion,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRoutePoint,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneInterconnectSolvedRouteResult_build,
    routingZoneInterconnectSolvedRouteSetResult_build,
    routingZoneRoutePointResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


def routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneInterconnectSolvedRouteSet]:
    """Build solved seam routes from placed geometry and seam obligations."""

    solvedRoutesMutable: list[RoutingZoneInterconnectSolvedRoute] = []
    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.SEAM_CROSSING
        ):
            continue
        routePairResult = (
            _routingZoneInterconnectSolvedRoutePairResult_buildFromObligation(
                circuitDocument=circuitDocument,
                placedRoutingZoneGrid=placedRoutingZoneGrid,
                callRouteObligation=callRouteObligation,
            )
        )
        if not result_isOkCheck(routePairResult):
            return resultErr_build()
        forwardRoute, returnRoute = routePairResult.value
        solvedRoutesMutable.append(forwardRoute)
        solvedRoutesMutable.append(returnRoute)

    return routingZoneInterconnectSolvedRouteSetResult_build(
        routingZoneInterconnectSolvedRoutes=tuple(solvedRoutesMutable)
    )


def _routingZoneInterconnectSolvedRoutePairResult_buildFromObligation(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligation: CallRouteObligation,
) -> Result[tuple[RoutingZoneInterconnectSolvedRoute, RoutingZoneInterconnectSolvedRoute]]:
    """Build forward + return solved seam route pair from one seam-crossing obligation."""

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

    interconnectResult = (
        placedRoutingZoneGrid.routingZoneInterconnectSet.interconnectBetweenZonesResult_get(
            sourceZoneResult.value.routingZoneId,
            destinationZoneResult.value.routingZoneId,
        )
    )
    if not result_isOkCheck(interconnectResult):
        return resultErr_build()

    sourcePlacementResult: Result[ChipPlacement] = (
        sourceZoneResult.value.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.sourceChipRef
        )
    )
    if not result_isOkCheck(sourcePlacementResult):
        return resultErr_build()
    destinationPlacementResult: Result[ChipPlacement] = (
        destinationZoneResult.value.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.destinationChipRef
        )
    )
    if not result_isOkCheck(destinationPlacementResult):
        return resultErr_build()

    sourceInterFanRegionResult = _interRoutingFanRegionResult_build(
        routingZone=sourceZoneResult.value,
        chipPlacement=sourcePlacementResult.value,
    )
    if not result_isOkCheck(sourceInterFanRegionResult):
        return resultErr_build()
    destinationInterFanRegionResult = _interRoutingFanRegionResult_build(
        routingZone=destinationZoneResult.value,
        chipPlacement=destinationPlacementResult.value,
    )
    if not result_isOkCheck(destinationInterFanRegionResult):
        return resultErr_build()

    srcChipLines = chipDrawLines_build(sourceChipResult.value)
    dstChipLines = chipDrawLines_build(destinationChipResult.value)
    fwdGeometryResult = _seamGeometryResult_build(
        interconnect=interconnectResult.value,
        sourcePlacement=sourcePlacementResult.value,
        destinationPlacement=destinationPlacementResult.value,
        sourceInterFanRegion=sourceInterFanRegionResult.value,
        destinationInterFanRegion=destinationInterFanRegionResult.value,
        srcChipLines=srcChipLines,
        dstChipLines=dstChipLines,
        childCallIndex=callRouteObligation.childCallIndex,
        isReturn=False,
    )
    retGeometryResult = _seamGeometryResult_build(
        interconnect=interconnectResult.value,
        sourcePlacement=sourcePlacementResult.value,
        destinationPlacement=destinationPlacementResult.value,
        sourceInterFanRegion=sourceInterFanRegionResult.value,
        destinationInterFanRegion=destinationInterFanRegionResult.value,
        srcChipLines=srcChipLines,
        dstChipLines=dstChipLines,
        childCallIndex=callRouteObligation.childCallIndex,
        isReturn=True,
    )
    if not result_isOkCheck(fwdGeometryResult) or not result_isOkCheck(retGeometryResult):
        return resultErr_build()

    fwdRouteResult = routingZoneInterconnectSolvedRouteResult_build(
        routingZoneInterconnectId=interconnectResult.value.routingZoneInterconnectId,
        sourceChipRef=callRouteObligation.sourceChipRef,
        destinationChipRef=callRouteObligation.destinationChipRef,
        childCallIndex=callRouteObligation.childCallIndex,
        solveKind=fwdGeometryResult.value[0],
        routePoints=fwdGeometryResult.value[1],
        traversedRegionIds=fwdGeometryResult.value[2],
    )
    # Return route: leaf → mid (source/dest swapped).
    retRouteResult = routingZoneInterconnectSolvedRouteResult_build(
        routingZoneInterconnectId=interconnectResult.value.routingZoneInterconnectId,
        sourceChipRef=callRouteObligation.destinationChipRef,
        destinationChipRef=callRouteObligation.sourceChipRef,
        childCallIndex=callRouteObligation.childCallIndex,
        solveKind=retGeometryResult.value[0],
        routePoints=retGeometryResult.value[1],
        traversedRegionIds=retGeometryResult.value[2],
    )
    if not result_isOkCheck(fwdRouteResult) or not result_isOkCheck(retRouteResult):
        return resultErr_build()
    return resultOk_build((fwdRouteResult.value, retRouteResult.value))


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
        code="routing.interconnect_solver.missing_chip_zone",
        message="Placed RoutingZoneGrid does not contain the requested chip",
    )
    return resultErr_build()


def _interRoutingFanRegionResult_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> Result[RoutingZoneRegion]:
    """Build the inter-routing fan-in/out region matching one chip placement side."""

    routingZoneRegionSide = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    if routingZoneRegionSide is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.interconnect_solver.placement.missing_terminal_side",
            message="ChipPlacement terminal side is required for seam solving",
        )
        return resultErr_build()
    return routingZone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
        routingZoneRegionSide,
    )


def _seamGeometryResult_build(
    interconnect: RoutingZoneInterconnect,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceInterFanRegion: RoutingZoneRegion,
    destinationInterFanRegion: RoutingZoneRegion,
    srcChipLines: tuple[str, ...],
    dstChipLines: tuple[str, ...],
    childCallIndex: int,
    isReturn: bool,
) -> Result[
    tuple[
        RoutingZoneInterconnectRouteSolveKind,
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
    ]
]:
    """Build solved seam polyline and traversed region ids."""

    interconnectAxisResult = interconnect.interconnectAxisResult_get()
    if not result_isOkCheck(interconnectAxisResult):
        return resultErr_build()

    if interconnectAxisResult.value is RoutingZoneInterconnectAxis.HORIZONTAL:
        return _horizontalSeamGeometryResult_build(
            interconnect=interconnect,
            sourcePlacement=sourcePlacement,
            destinationPlacement=destinationPlacement,
            sourceInterFanRegion=sourceInterFanRegion,
            destinationInterFanRegion=destinationInterFanRegion,
            srcChipHeight=len(srcChipLines),
            dstChipHeight=len(dstChipLines),
            childCallIndex=childCallIndex,
            isReturn=isReturn,
        )
    return _verticalSeamGeometryResult_build(
        interconnect=interconnect,
        sourcePlacement=sourcePlacement,
        destinationPlacement=destinationPlacement,
        sourceInterFanRegion=sourceInterFanRegion,
        destinationInterFanRegion=destinationInterFanRegion,
        srcChipWidth=max((len(line) for line in srcChipLines), default=1),
        dstChipWidth=max((len(line) for line in dstChipLines), default=1),
        childCallIndex=childCallIndex,
        isReturn=isReturn,
    )


def _horizontalSeamGeometryResult_build(
    interconnect: RoutingZoneInterconnect,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceInterFanRegion: RoutingZoneRegion,
    destinationInterFanRegion: RoutingZoneRegion,
    srcChipHeight: int,
    dstChipHeight: int,
    childCallIndex: int,
    isReturn: bool,
) -> Result[
    tuple[
        RoutingZoneInterconnectRouteSolveKind,
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
    ]
]:
    """Build explicit horizontal seam geometry."""

    # Each chip slot = chipHeight + 2 rows.  The seam port row is at:
    # slotStart + 1 (corridor above) + _HEADER (chip header rows) + k
    # where k = childCallIndex (which output port within the source chip).
    # East terminals are packed 1 row apart in chipDrawLines_build, so offset = k.
    # The return port is one row below the signal port.
    _HEADER: int = 3
    _RET_OFFSET: int = 1
    k: int = childCallIndex
    srcSignalRow: int = (
        sourceInterFanRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipHeight + 2)
        + 1 + _HEADER + k
    )
    dstSignalRow: int = (
        destinationInterFanRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipHeight + 2)
        + 1 + _HEADER
    )

    if isReturn:
        # Return: leaf (dst) → mid (src), using return port rows (+1).
        startFanRegion = destinationInterFanRegion
        endFanRegion = sourceInterFanRegion
        startRow = dstSignalRow + _RET_OFFSET
        endRow = srcSignalRow + _RET_OFFSET
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM_RETURN
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM_RETURN
    else:
        startFanRegion = sourceInterFanRegion
        endFanRegion = destinationInterFanRegion
        startRow = srcSignalRow
        endRow = dstSignalRow
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM

    startPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=startFanRegion.routingZoneRegionFrame.horizontalStart,
        verticalIndex=startRow,
    )
    seamEntryPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=interconnect.routingZoneInterconnectFrame.horizontalStart,
        verticalIndex=startRow,
    )
    if not (
        result_isOkCheck(startPointResult)
        and result_isOkCheck(seamEntryPointResult)
    ):
        return resultErr_build()

    routePointsMutable: list[RoutingZoneRoutePoint] = [
        startPointResult.value,
        seamEntryPointResult.value,
    ]
    if startRow != endRow:
        seamTurnPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=interconnect.routingZoneInterconnectFrame.horizontalStart,
            verticalIndex=endRow,
        )
        if not result_isOkCheck(seamTurnPointResult):
            return resultErr_build()
        routePointsMutable.append(seamTurnPointResult.value)

    endPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=endFanRegion.routingZoneRegionFrame.horizontalStart,
        verticalIndex=endRow,
    )
    if not result_isOkCheck(endPointResult):
        return resultErr_build()
    routePointsMutable.append(endPointResult.value)

    solveKind = straightKind if startRow == endRow else offsetKind
    return resultOk_build(
        (
            solveKind,
            tuple(routePointsMutable),
            (
                startFanRegion.routingZoneRegionId,
                endFanRegion.routingZoneRegionId,
            ),
        )
    )


def _verticalSeamGeometryResult_build(
    interconnect: RoutingZoneInterconnect,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceInterFanRegion: RoutingZoneRegion,
    destinationInterFanRegion: RoutingZoneRegion,
    srcChipWidth: int,
    dstChipWidth: int,
    childCallIndex: int,
    isReturn: bool,
) -> Result[
    tuple[
        RoutingZoneInterconnectRouteSolveKind,
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
    ]
]:
    """Build explicit vertical seam geometry."""

    # Each chip slot = chipWidth + 2 cols.  The seam port column is at:
    # slotStart + 1 (corridor left) + _HEADER (chip header cols) + k
    # where k = childCallIndex (which output port within the source chip).
    # East terminals are packed 1 col apart in chipDrawLines_build, so offset = k.
    # The return port is one column to the right of the signal port.
    _HEADER: int = 3
    _RET_OFFSET: int = 1
    k: int = childCallIndex
    srcSignalCol: int = (
        sourceInterFanRegion.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex * (srcChipWidth + 2)
        + 1 + _HEADER + k
    )
    dstSignalCol: int = (
        destinationInterFanRegion.routingZoneRegionFrame.horizontalStart
        + destinationPlacement.orderIndex * (dstChipWidth + 2)
        + 1 + _HEADER
    )

    if isReturn:
        # Return: leaf (dst) → mid (src), using return port columns (+1).
        startFanRegion = destinationInterFanRegion
        endFanRegion = sourceInterFanRegion
        startCol = dstSignalCol + _RET_OFFSET
        endCol = srcSignalCol + _RET_OFFSET
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM_RETURN
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM_RETURN
    else:
        startFanRegion = sourceInterFanRegion
        endFanRegion = destinationInterFanRegion
        startCol = srcSignalCol
        endCol = dstSignalCol
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM

    startPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=startCol,
        verticalIndex=startFanRegion.routingZoneRegionFrame.verticalStart,
    )
    seamEntryPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=startCol,
        verticalIndex=interconnect.routingZoneInterconnectFrame.verticalStart,
    )
    if not (
        result_isOkCheck(startPointResult)
        and result_isOkCheck(seamEntryPointResult)
    ):
        return resultErr_build()

    routePointsMutable: list[RoutingZoneRoutePoint] = [
        startPointResult.value,
        seamEntryPointResult.value,
    ]
    if startCol != endCol:
        seamTurnPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=endCol,
            verticalIndex=interconnect.routingZoneInterconnectFrame.verticalStart,
        )
        if not result_isOkCheck(seamTurnPointResult):
            return resultErr_build()
        routePointsMutable.append(seamTurnPointResult.value)

    endPointResult = routingZoneRoutePointResult_build(
        horizontalIndex=endCol,
        verticalIndex=endFanRegion.routingZoneRegionFrame.verticalStart,
    )
    if not result_isOkCheck(endPointResult):
        return resultErr_build()
    routePointsMutable.append(endPointResult.value)

    solveKind = straightKind if startCol == endCol else offsetKind
    return resultOk_build(
        (
            solveKind,
            tuple(routePointsMutable),
            (
                startFanRegion.routingZoneRegionId,
                endFanRegion.routingZoneRegionId,
            ),
        )
    )
