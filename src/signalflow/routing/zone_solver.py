"""Zone-local routing solver for the new SignalFlow engine.

This module realizes `ZONE_LOCAL` call obligations against already planned
`RoutingZone` geometry.

Same-zone obligations do not all use the same substrate:

- west->east / north->south forward edges use the interior `INTRA` route family
- east->west / south->north backedges use the outer `INTER` perimeter family
- same-side self calls use a short local loop

Port identity and lane identity are intentionally separate. Multiple chips in
one zone can each have `childCallIndex == 0`, but they must still occupy
distinct route lanes inside the chosen geometry family.
"""
from __future__ import annotations

from signalflow.models import (
    CallRouteObligation,
    CallRouteObligationSet,
    ChipPlacement,
    ChipRef,
    CircuitDocument,
    Result,
    RouteObligationScope,
    RoutingZone,
    RoutingZoneGrid,
    RoutingZoneId,
    RoutingZoneLocalRouteSolveKind,
    RoutingZoneLocalSolvedRoute,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneRegion,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    RoutingZoneSense,
    ZoneLocalGeometryKind,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneLocalSolvedRouteResult_build,
    routingZoneLocalSolvedRouteSetResult_build,
    routingZoneRoutePointResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


def routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneLocalSolvedRouteSet]:
    """Build solved zone-local routes from placed geometry and local obligations."""

    forwardRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    returnRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    laneIndexByObligationKey: dict[
        tuple[ChipRef, ChipRef, int],
        int,
    ] = _zoneLocalLaneIndexByObligationKey_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        callRouteObligationSet=callRouteObligationSet,
    )

    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.ZONE_LOCAL
        ):
            continue

        obligationKey: tuple[ChipRef, ChipRef, int] = (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        )
        pairResult = _solvedRoutePairResult_buildFromObligation(
            circuitDocument=circuitDocument,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            callRouteObligation=callRouteObligation,
            localLaneIndex=laneIndexByObligationKey[obligationKey],
        )
        if not result_isOkCheck(pairResult):
            return resultErr_build()

        forwardRoute, returnRoute = pairResult.value
        forwardRoutesMutable.append(forwardRoute)
        if returnRoute is not None:
            returnRoutesMutable.append(returnRoute)

    return routingZoneLocalSolvedRouteSetResult_build(
        routingZoneLocalSolvedRoutes=tuple(
            forwardRoutesMutable + returnRoutesMutable
        )
    )


def _zoneLocalLaneIndexByObligationKey_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> dict[tuple[ChipRef, ChipRef, int], int]:
    """Return stable per-zone lane indices for local obligations."""

    laneIndexByObligationKey: dict[tuple[ChipRef, ChipRef, int], int] = {}
    nextIntraLaneIndexByZoneId: dict[RoutingZoneId, int] = {}
    nextInterLaneIndexByZoneId: dict[RoutingZoneId, int] = {}

    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.ZONE_LOCAL
        ):
            continue

        sourceZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            chipRef=callRouteObligation.sourceChipRef,
        )
        destinationZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            chipRef=callRouteObligation.destinationChipRef,
        )
        if not (
            result_isOkCheck(sourceZoneResult)
            and result_isOkCheck(destinationZoneResult)
        ):
            continue

        zone = sourceZoneResult.value
        sourcePlacement = zone.chipPlacementSet.placementForChipOrNone_get(
            callRouteObligation.sourceChipRef
        )
        destinationPlacement = zone.chipPlacementSet.placementForChipOrNone_get(
            callRouteObligation.destinationChipRef
        )
        if sourcePlacement is None or destinationPlacement is None:
            continue

        obligationKey: tuple[ChipRef, ChipRef, int] = (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        )
        if (
            callRouteObligation.zoneLocalGeometryKind
            is ZoneLocalGeometryKind.SAME_SIDE_LOCAL
        ):
            laneIndexByObligationKey[obligationKey] = (
                callRouteObligation.childCallIndex
            )
            continue

        if (
            callRouteObligation.zoneLocalGeometryKind
            is ZoneLocalGeometryKind.INTER_PERIMETER_BACKEDGE
        ):
            nextLaneIndex: int = nextInterLaneIndexByZoneId.get(
                zone.routingZoneId,
                0,
            )
            laneIndexByObligationKey[obligationKey] = nextLaneIndex
            nextInterLaneIndexByZoneId[zone.routingZoneId] = nextLaneIndex + 1
            continue

        nextLaneIndex = nextIntraLaneIndexByZoneId.get(zone.routingZoneId, 0)
        laneIndexByObligationKey[obligationKey] = nextLaneIndex
        nextIntraLaneIndexByZoneId[zone.routingZoneId] = nextLaneIndex + 1

    return laneIndexByObligationKey


def _solvedRoutePairResult_buildFromObligation(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligation: CallRouteObligation,
    localLaneIndex: int,
) -> Result[tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]]:
    """Build (forward, return) solved route pair for one local obligation."""

    sourceZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        chipRef=callRouteObligation.sourceChipRef,
    )
    if not result_isOkCheck(sourceZoneResult):
        return resultErr_build()
    destinationZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        chipRef=callRouteObligation.destinationChipRef,
    )
    if not result_isOkCheck(destinationZoneResult):
        return resultErr_build()
    if (
        sourceZoneResult.value.routingZoneId
        != destinationZoneResult.value.routingZoneId
    ):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_solver.local_route.cross_zone_obligation",
            message="Zone-local route obligations must stay inside one routing zone",
        )
        return resultErr_build()

    zone = sourceZoneResult.value

    sourcePlacementResult: Result[ChipPlacement] = (
        zone.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.sourceChipRef
        )
    )
    if not result_isOkCheck(sourcePlacementResult):
        return resultErr_build()
    destinationPlacementResult: Result[ChipPlacement] = (
        zone.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.destinationChipRef
        )
    )
    if not result_isOkCheck(destinationPlacementResult):
        return resultErr_build()

    sourceTerminalRegionResult: Result[RoutingZoneRegion] = (
        zone.routingZoneRegionSet.regionResult_get(
            sourcePlacementResult.value.chipTerminalRegionId
        )
    )
    if not result_isOkCheck(sourceTerminalRegionResult):
        return resultErr_build()
    destinationTerminalRegionResult: Result[RoutingZoneRegion] = (
        zone.routingZoneRegionSet.regionResult_get(
            destinationPlacementResult.value.chipTerminalRegionId
        )
    )
    if not result_isOkCheck(destinationTerminalRegionResult):
        return resultErr_build()

    sourceSide = sourcePlacementResult.value.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = (
        destinationPlacementResult.value.chipTerminalRegionId.routingZoneRegionSide
    )

    # Self-call: same chip on the same side — single same-side local route, no return.
    if sourceSide == destinationSide:
        sameResult = _sameSideLocalRouteResult_build(
            circuitDocument=circuitDocument,
            zone=zone,
            obligation=callRouteObligation,
            sourcePlacement=sourcePlacementResult.value,
            destinationPlacement=destinationPlacementResult.value,
            sourceTerminalRegion=sourceTerminalRegionResult.value,
            destinationTerminalRegion=destinationTerminalRegionResult.value,
        )
        if not result_isOkCheck(sameResult):
            return resultErr_build()
        return resultOk_build((sameResult.value, None))

    if zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return _wteRoutePairResult_build(
            circuitDocument=circuitDocument,
            zone=zone,
            obligation=callRouteObligation,
            localLaneIndex=localLaneIndex,
            sourcePlacement=sourcePlacementResult.value,
            destinationPlacement=destinationPlacementResult.value,
            sourceTerminalRegion=sourceTerminalRegionResult.value,
            destinationTerminalRegion=destinationTerminalRegionResult.value,
        )
    return _ntsRoutePairResult_build(
        circuitDocument=circuitDocument,
        zone=zone,
        obligation=callRouteObligation,
        localLaneIndex=localLaneIndex,
        sourcePlacement=sourcePlacementResult.value,
        destinationPlacement=destinationPlacementResult.value,
        sourceTerminalRegion=sourceTerminalRegionResult.value,
        destinationTerminalRegion=destinationTerminalRegionResult.value,
    )


# ---------------------------------------------------------------------------
# WTE solver
# ---------------------------------------------------------------------------


def _wteRoutePairResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligation: CallRouteObligation,
    localLaneIndex: int,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceTerminalRegion: RoutingZoneRegion,
    destinationTerminalRegion: RoutingZoneRegion,
) -> Result[tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]]:
    """Build forward + return solved route pair for one WTE ZONE_LOCAL obligation."""

    fanW = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST
    )
    fanE = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST
    )
    longW = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST
    )
    longE = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST
    )
    latN = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH
    )
    latS = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH
    )
    if not all(
        result_isOkCheck(r) for r in [fanW, fanE, longW, longE, latN, latS]
    ):
        return resultErr_build()

    # Look up chip heights so port rows can be computed from slot boundaries.
    srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.destinationChipRef.chipId
    )
    if not (result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)):
        return resultErr_build()
    srcChipH: int = len(chipDrawLines_build(srcChipResult.value))
    dstChipH: int = len(chipDrawLines_build(dstChipResult.value))

    # Chip body layout: top-border + title + separator = 3 header rows before ports.
    _HEADER: int = 3

    portIndex: int = obligation.childCallIndex
    laneIndex: int = localLaneIndex
    fanW_col: int = fanW.value.routingZoneRegionFrame.horizontalStart
    fanE_col: int = fanE.value.routingZoneRegionFrame.horizontalStart
    longW_col: int = longW.value.routingZoneRegionFrame.horizontalStart
    longE_col: int = longE.value.routingZoneRegionFrame.horizontalStart
    latN_row: int = latN.value.routingZoneRegionFrame.verticalStart
    latS_row: int = latS.value.routingZoneRegionFrame.verticalStart

    lane_left: int = longW_col + laneIndex
    lane_top: int = latN_row - laneIndex
    lane_right: int = longE_col - laneIndex
    lane_bottom: int = latS_row + laneIndex

    # r_src / r_dst: the actual port rows inside the chip body.
    # Each chip slot = chipHeight + 2 rows (1 corridor above, body, 1 corridor below).
    # Port row = slotStart + 1 (corridor) + _HEADER + 2*k (signal) or 2*k+1 (return).
    # Each east terminal occupies 2 body rows: signal at 2k, return at 2k+1.
    # Source port index k = which call in the source chip's outgoing call list.
    # Destination port index = 0 (first input port of the destination chip).
    r_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipH + 2)
        + 1 + _HEADER + 2 * portIndex
    )
    r_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipH + 2)
        + 1 + _HEADER
    )
    r_src_ret: int = r_src + 1
    r_dst_ret: int = r_dst + 1

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = destinationPlacement.chipTerminalRegionId.routingZoneRegionSide

    if (
        sourceSide is RoutingZoneRegionSide.WEST
        and destinationSide is RoutingZoneRegionSide.EAST
    ):
        solveKindForward = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        # Forward: top half of clockwise INTRA rectangle (W→E).
        fwdPointsRaw: list[tuple[int, int]] = [
            (fanW_col,   r_src),
            (lane_left,  r_src),
            (lane_left,  lane_top),
            (lane_right, lane_top),
            (lane_right, r_dst),
            (fanE_col,   r_dst),
        ]
        retPointsRaw: list[tuple[int, int]] = [
            (fanE_col,    r_dst_ret),
            (lane_right,  r_dst_ret),
            (lane_right,  lane_bottom),
            (lane_left,   lane_bottom),
            (lane_left,   r_src_ret),
            (fanW_col,    r_src_ret),
        ]
        intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanW.value.routingZoneRegionId,
            longW.value.routingZoneRegionId,
            latN.value.routingZoneRegionId,
            longE.value.routingZoneRegionId,
            fanE.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds: tuple[RoutingZoneRegionId, ...] = (
            destinationTerminalRegion.routingZoneRegionId,
            fanE.value.routingZoneRegionId,
            longE.value.routingZoneRegionId,
            latS.value.routingZoneRegionId,
            longW.value.routingZoneRegionId,
            fanW.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )
    else:
        interFanW = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
        )
        interFanE = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
        )
        interLongW = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        interLongE = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.EAST,
        )
        interLatN = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        interLatS = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.SOUTH,
        )
        if not all(
            result_isOkCheck(r)
            for r in [
                interFanW,
                interFanE,
                interLongW,
                interLongE,
                interLatN,
                interLatS,
            ]
        ):
            return resultErr_build()

        solveKindForward = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
        srcInterFanStart: int = (
            interFanE.value.routingZoneRegionFrame.horizontalStart
        )
        dstInterFanStart: int = (
            interFanW.value.routingZoneRegionFrame.horizontalStart
        )
        dstInterFanEnd: int = (
            interFanW.value.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        )
        srcInterTravelCol: int = (
            interLongE.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        dstInterTravelCol: int = (
            interLongW.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        srcInterLaneCol: int = srcInterFanStart + 2 + laneIndex
        dstInterLaneCol: int = dstInterFanStart + laneIndex
        northPerimeterRow: int = (
            interLatN.value.routingZoneRegionFrame.verticalStart
        )
        southPerimeterRow: int = (
            interLatS.value.routingZoneRegionFrame.verticalStart
        )

        fwdPointsRaw = [
            (srcInterFanStart, r_src),
            (srcInterFanStart + 1, r_src),
            (srcInterLaneCol, r_src),
            (srcInterTravelCol, r_src),
            (srcInterTravelCol, northPerimeterRow),
            (dstInterTravelCol, northPerimeterRow),
            (dstInterTravelCol, r_dst),
            (dstInterLaneCol, r_dst),
            (dstInterFanEnd - 1, r_dst),
            (dstInterFanEnd, r_dst),
        ]
        retPointsRaw = [
            (dstInterFanEnd, r_dst_ret),
            (dstInterFanEnd - 1, r_dst_ret),
            (dstInterLaneCol, r_dst_ret),
            (dstInterTravelCol, r_dst_ret),
            (dstInterTravelCol, southPerimeterRow),
            (srcInterTravelCol, southPerimeterRow),
            (srcInterTravelCol, r_src_ret),
            (srcInterLaneCol, r_src_ret),
            (srcInterFanStart + 1, r_src_ret),
            (srcInterFanStart, r_src_ret),
        ]
        intraRegionIds = (
            sourceTerminalRegion.routingZoneRegionId,
            interFanE.value.routingZoneRegionId,
            interLongE.value.routingZoneRegionId,
            interLatN.value.routingZoneRegionId,
            interLongW.value.routingZoneRegionId,
            interFanW.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds = (
            destinationTerminalRegion.routingZoneRegionId,
            interFanW.value.routingZoneRegionId,
            interLongW.value.routingZoneRegionId,
            interLatS.value.routingZoneRegionId,
            interLongE.value.routingZoneRegionId,
            interFanE.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )

    fwdPtsResult = _routePoints_build(fwdPointsRaw)
    if not result_isOkCheck(fwdPtsResult):
        return resultErr_build()

    fwdRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindForward,
        routePoints=fwdPtsResult.value,
        traversedRegionIds=intraRegionIds,
    )
    if not result_isOkCheck(fwdRouteResult):
        return resultErr_build()

    retPtsResult = _routePoints_build(retPointsRaw)
    if not result_isOkCheck(retPtsResult):
        return resultErr_build()

    retRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.destinationChipRef,
        destinationChipRef=obligation.sourceChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindReturn,
        routePoints=retPtsResult.value,
        traversedRegionIds=retRegionIds,
    )
    if not result_isOkCheck(retRouteResult):
        return resultErr_build()

    return resultOk_build((fwdRouteResult.value, retRouteResult.value))


# ---------------------------------------------------------------------------
# NTS solver
# ---------------------------------------------------------------------------


def _ntsRoutePairResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligation: CallRouteObligation,
    localLaneIndex: int,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceTerminalRegion: RoutingZoneRegion,
    destinationTerminalRegion: RoutingZoneRegion,
) -> Result[tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]]:
    """Build forward + return solved route pair for one NTS ZONE_LOCAL obligation."""

    fanN = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH
    )
    fanS = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH
    )
    longW = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST
    )
    longE = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST
    )
    latN = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH
    )
    latS = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH
    )
    if not all(
        result_isOkCheck(r) for r in [fanN, fanS, longW, longE, latN, latS]
    ):
        return resultErr_build()

    # Look up chip widths so port columns can be computed from slot boundaries.
    srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.destinationChipRef.chipId
    )
    if not (result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)):
        return resultErr_build()
    srcLines = chipDrawLines_build(srcChipResult.value)
    dstLines = chipDrawLines_build(dstChipResult.value)
    srcChipW: int = max((len(line) for line in srcLines), default=1)
    dstChipW: int = max((len(line) for line in dstLines), default=1)

    # For NTS chips stacked horizontally each slot = chipWidth + 2 cols
    # (1 corridor col left, chip body, 1 corridor col right).
    # Port col = slotStart + 1 + _HEADER + 2*portIndex.
    _HEADER: int = 3

    portIndex: int = obligation.childCallIndex
    laneIndex: int = localLaneIndex
    fanN_row: int = fanN.value.routingZoneRegionFrame.verticalStart
    fanS_row: int = fanS.value.routingZoneRegionFrame.verticalStart
    longW_col: int = longW.value.routingZoneRegionFrame.horizontalStart
    longE_col: int = longE.value.routingZoneRegionFrame.horizontalStart
    latN_row: int = latN.value.routingZoneRegionFrame.verticalStart
    latS_row: int = latS.value.routingZoneRegionFrame.verticalStart

    lane_left: int = longW_col + laneIndex
    lane_top: int = latN_row - laneIndex
    lane_right: int = longE_col - laneIndex
    lane_bottom: int = latS_row + laneIndex

    c_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex * (srcChipW + 2)
        + 1 + _HEADER + 2 * portIndex
    )
    c_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.horizontalStart
        + destinationPlacement.orderIndex * (dstChipW + 2)
        + 1 + _HEADER
    )
    c_src_ret: int = c_src + 1
    c_dst_ret: int = c_dst + 1

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = destinationPlacement.chipTerminalRegionId.routingZoneRegionSide

    if (
        sourceSide is RoutingZoneRegionSide.NORTH
        and destinationSide is RoutingZoneRegionSide.SOUTH
    ):
        solveKindForward = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        fwdPointsRaw: list[tuple[int, int]] = [
            (c_src,       fanN_row),
            (c_src,       lane_top),
            (lane_right,  lane_top),
            (lane_right,  lane_bottom),
            (c_dst,       lane_bottom),
            (c_dst,       fanS_row),
        ]
        retPointsRaw: list[tuple[int, int]] = [
            (c_dst_ret,  fanS_row),
            (c_dst_ret,  lane_bottom),
            (lane_left,  lane_bottom),
            (lane_left,  lane_top),
            (c_src_ret,  lane_top),
            (c_src_ret,  fanN_row),
        ]
        intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanN.value.routingZoneRegionId,
            latN.value.routingZoneRegionId,
            longE.value.routingZoneRegionId,
            latS.value.routingZoneRegionId,
            fanS.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds: tuple[RoutingZoneRegionId, ...] = (
            destinationTerminalRegion.routingZoneRegionId,
            fanS.value.routingZoneRegionId,
            latS.value.routingZoneRegionId,
            longW.value.routingZoneRegionId,
            latN.value.routingZoneRegionId,
            fanN.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )
    else:
        interFanN = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.NORTH,
        )
        interFanS = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.SOUTH,
        )
        interLongW = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        interLongE = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.EAST,
        )
        interLatN = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        interLatS = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.SOUTH,
        )
        if not all(
            result_isOkCheck(r)
            for r in [
                interFanN,
                interFanS,
                interLongW,
                interLongE,
                interLatN,
                interLatS,
            ]
        ):
            return resultErr_build()

        solveKindForward = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
        srcInterFanStart: int = (
            interFanS.value.routingZoneRegionFrame.verticalStart
        )
        dstInterFanStart: int = (
            interFanN.value.routingZoneRegionFrame.verticalStart
        )
        dstInterFanEnd: int = (
            interFanN.value.routingZoneRegionFrame.verticalEnd_calculate() - 1
        )
        southTravelRow: int = (
            interLatS.value.routingZoneRegionFrame.verticalStart + laneIndex
        )
        northTravelRow: int = (
            interLatN.value.routingZoneRegionFrame.verticalStart + laneIndex
        )
        westPerimeterCol: int = (
            interLongW.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        eastPerimeterCol: int = (
            interLongE.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        srcInterLaneRow: int = srcInterFanStart + 2 + laneIndex
        dstInterLaneRow: int = dstInterFanStart + laneIndex

        fwdPointsRaw = [
            (c_src, srcInterFanStart),
            (c_src, srcInterFanStart + 1),
            (c_src, srcInterLaneRow),
            (c_src, southTravelRow),
            (westPerimeterCol, southTravelRow),
            (westPerimeterCol, northTravelRow),
            (c_dst, northTravelRow),
            (c_dst, dstInterLaneRow),
            (c_dst, dstInterFanEnd - 1),
            (c_dst, dstInterFanEnd),
        ]
        retPointsRaw = [
            (c_dst_ret, dstInterFanEnd),
            (c_dst_ret, dstInterFanEnd - 1),
            (c_dst_ret, dstInterLaneRow),
            (c_dst_ret, northTravelRow),
            (eastPerimeterCol, northTravelRow),
            (eastPerimeterCol, southTravelRow),
            (c_src_ret, southTravelRow),
            (c_src_ret, srcInterLaneRow),
            (c_src_ret, srcInterFanStart + 1),
            (c_src_ret, srcInterFanStart),
        ]
        intraRegionIds = (
            sourceTerminalRegion.routingZoneRegionId,
            interFanS.value.routingZoneRegionId,
            interLatS.value.routingZoneRegionId,
            interLongW.value.routingZoneRegionId,
            interLatN.value.routingZoneRegionId,
            interFanN.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds = (
            destinationTerminalRegion.routingZoneRegionId,
            interFanN.value.routingZoneRegionId,
            interLatN.value.routingZoneRegionId,
            interLongE.value.routingZoneRegionId,
            interLatS.value.routingZoneRegionId,
            interFanS.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )

    fwdPtsResult = _routePoints_build(fwdPointsRaw)
    if not result_isOkCheck(fwdPtsResult):
        return resultErr_build()

    fwdRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindForward,
        routePoints=fwdPtsResult.value,
        traversedRegionIds=intraRegionIds,
    )
    if not result_isOkCheck(fwdRouteResult):
        return resultErr_build()

    retPtsResult = _routePoints_build(retPointsRaw)
    if not result_isOkCheck(retPtsResult):
        return resultErr_build()

    retRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.destinationChipRef,
        destinationChipRef=obligation.sourceChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindReturn,
        routePoints=retPtsResult.value,
        traversedRegionIds=retRegionIds,
    )
    if not result_isOkCheck(retRouteResult):
        return resultErr_build()

    return resultOk_build((fwdRouteResult.value, retRouteResult.value))


# ---------------------------------------------------------------------------
# Same-side local (self-call)
# ---------------------------------------------------------------------------


def _sameSideLocalRouteResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligation: CallRouteObligation,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceTerminalRegion: RoutingZoneRegion,
    destinationTerminalRegion: RoutingZoneRegion,
) -> Result[RoutingZoneLocalSolvedRoute]:
    """Build a same-side local loop for a self-call obligation."""

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    assert sourceSide is not None

    # Look up the chip so port offset can be computed from slot boundaries.
    chipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    if not result_isOkCheck(chipResult):
        return resultErr_build()
    chipLines = chipDrawLines_build(chipResult.value)
    _HEADER: int = 3

    if zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        fanResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, sourceSide
        )
        longResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, sourceSide
        )
        if not result_isOkCheck(fanResult) or not result_isOkCheck(longResult):
            return resultErr_build()

        chipH: int = len(chipLines)
        r = (
            sourceTerminalRegion.routingZoneRegionFrame.verticalStart
            + sourcePlacement.orderIndex * (chipH + 2)
            + 1 + _HEADER
        )
        chipCol = sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
        fanCol = fanResult.value.routingZoneRegionFrame.horizontalStart
        longCol = longResult.value.routingZoneRegionFrame.horizontalStart

        pointsRaw: list[tuple[int, int]] = [
            (chipCol, r),
            (fanCol,  r),
            (longCol, r),
            (fanCol,  r),
            (chipCol, r),
        ]
        traversedIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            longResult.value.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
    else:
        fanResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, sourceSide
        )
        latResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, sourceSide
        )
        if not result_isOkCheck(fanResult) or not result_isOkCheck(latResult):
            return resultErr_build()

        chipW: int = max((len(line) for line in chipLines), default=1)
        c = (
            sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
            + sourcePlacement.orderIndex * (chipW + 2)
            + 1 + _HEADER
        )
        chipRow = sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        fanRow = fanResult.value.routingZoneRegionFrame.verticalStart
        latRow = latResult.value.routingZoneRegionFrame.verticalStart

        pointsRaw = [
            (c, chipRow),
            (c, fanRow),
            (c, latRow),
            (c, fanRow),
            (c, chipRow),
        ]
        traversedIds = (
            sourceTerminalRegion.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            latResult.value.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )

    ptsResult = _routePoints_build(pointsRaw)
    if not result_isOkCheck(ptsResult):
        return resultErr_build()

    return routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=RoutingZoneLocalRouteSolveKind.SAME_SIDE_LOCAL,
        routePoints=ptsResult.value,
        traversedRegionIds=traversedIds,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _routePoints_build(
    raw: list[tuple[int, int]],
) -> Result[tuple[RoutingZoneRoutePoint, ...]]:
    """Build a validated tuple of route points from (h, v) pairs."""

    pointsMutable: list[RoutingZoneRoutePoint] = []
    for h, v in raw:
        ptResult = routingZoneRoutePointResult_build(
            horizontalIndex=h, verticalIndex=v
        )
        if not result_isOkCheck(ptResult):
            return resultErr_build()
        pointsMutable.append(ptResult.value)
    return resultOk_build(tuple(pointsMutable))


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
        code="routing.zone_solver.missing_chip_zone",
        message="Placed RoutingZoneGrid does not contain the requested chip",
    )
    return resultErr_build()
