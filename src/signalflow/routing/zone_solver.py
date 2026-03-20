"""Zone-local routing solver for the new SignalFlow engine.

This module realizes `ZONE_LOCAL` call obligations against the already planned
`RoutingZone` geometry using a clockwise concentric-rectangle lane model.

For every ZONE_LOCAL obligation two solved routes are produced:

  FORWARD  — top half of the clockwise INTRA ring rectangle (W→E or N→S).
  RETURN   — bottom half of the same rectangle (E→W or S→N).

Lane k (0-indexed, derived from the obligation's childCallIndex) occupies one
concentric rectangle in the INTRA routing ring:

  WTE lane k:
    left col  = INTRA_LONG/W.col + k
    top  row  = INTRA_LAT/N.row  + k
    right col = INTRA_LONG/E.col - k
    bottom row= INTRA_LAT/S.row  - k

  NTS lane k is the 90°-transposed equivalent.

Source port row  : sourceTerminalRegion.verticalStart   + k   (WTE forward)
Dest   port row  : destTerminalRegion.verticalStart     + dest.orderIndex
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
    RoutingZoneLocalRouteSolveKind,
    RoutingZoneLocalSolvedRoute,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneRegion,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    RoutingZoneSense,
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

    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.ZONE_LOCAL
        ):
            continue

        pairResult = _solvedRoutePairResult_buildFromObligation(
            circuitDocument=circuitDocument,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            callRouteObligation=callRouteObligation,
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


def _solvedRoutePairResult_buildFromObligation(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligation: CallRouteObligation,
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
            sourcePlacement=sourcePlacementResult.value,
            destinationPlacement=destinationPlacementResult.value,
            sourceTerminalRegion=sourceTerminalRegionResult.value,
            destinationTerminalRegion=destinationTerminalRegionResult.value,
        )
    return _ntsRoutePairResult_build(
        circuitDocument=circuitDocument,
        zone=zone,
        obligation=callRouteObligation,
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

    k: int = obligation.childCallIndex
    fanW_col: int = fanW.value.routingZoneRegionFrame.horizontalStart
    fanE_col: int = fanE.value.routingZoneRegionFrame.horizontalStart
    longW_col: int = longW.value.routingZoneRegionFrame.horizontalStart
    longE_col: int = longE.value.routingZoneRegionFrame.horizontalStart
    latN_row: int = latN.value.routingZoneRegionFrame.verticalStart
    latS_row: int = latS.value.routingZoneRegionFrame.verticalStart

    lane_left: int = longW_col + k
    lane_top: int = latN_row - k
    lane_right: int = longE_col - k
    lane_bottom: int = latS_row + k

    # r_src / r_dst: the actual port rows inside the chip body.
    # Each chip slot = chipHeight + 2 rows (1 corridor above, body, 1 corridor below).
    # Port row = slotStart + 1 (corridor) + _HEADER + portIndex.
    # East terminals are packed 1 row apart in chipDrawLines_build, so portIndex = k.
    # Source port index k = which call in the source chip's outgoing call list.
    # Destination port index = 0 (first input port of the destination chip).
    r_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipH + 2)
        + 1 + _HEADER + k
    )
    r_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipH + 2)
        + 1 + _HEADER
    )
    r_src_ret: int = r_src + 1
    r_dst_ret: int = r_dst + 1

    # Forward: top half of clockwise INTRA rectangle (W→E).
    # Route begins at fanW (just outside the source chip stub) and ends at
    # fanE (just outside the destination chip stub).  The chip body stubs
    # drawn by chipDrawLines_build bridge the visual gap to the chip wall.
    fwdPointsRaw: list[tuple[int, int]] = [
        (fanW_col,   r_src),
        (lane_left,  r_src),
        (lane_left,  lane_top),
        (lane_right, lane_top),
        (lane_right, r_dst),
        (fanE_col,   r_dst),
    ]
    fwdPtsResult = _routePoints_build(fwdPointsRaw)
    if not result_isOkCheck(fwdPtsResult):
        return resultErr_build()

    intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
        sourceTerminalRegion.routingZoneRegionId,
        fanW.value.routingZoneRegionId,
        longW.value.routingZoneRegionId,
        latN.value.routingZoneRegionId,
        longE.value.routingZoneRegionId,
        fanE.value.routingZoneRegionId,
        destinationTerminalRegion.routingZoneRegionId,
    )

    fwdRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD,
        routePoints=fwdPtsResult.value,
        traversedRegionIds=intraRegionIds,
    )
    if not result_isOkCheck(fwdRouteResult):
        return resultErr_build()

    # Return: bottom half of clockwise INTRA rectangle (E→W).
    # Uses the return-port row (r_dst_ret / r_src_ret), one below the signal.
    retPointsRaw: list[tuple[int, int]] = [
        (fanE_col,    r_dst_ret),
        (lane_right,  r_dst_ret),
        (lane_right,  lane_bottom),
        (lane_left,   lane_bottom),
        (lane_left,   r_src_ret),
        (fanW_col,    r_src_ret),
    ]
    retPtsResult = _routePoints_build(retPointsRaw)
    if not result_isOkCheck(retPtsResult):
        return resultErr_build()

    retRegionIds: tuple[RoutingZoneRegionId, ...] = (
        destinationTerminalRegion.routingZoneRegionId,
        fanE.value.routingZoneRegionId,
        longE.value.routingZoneRegionId,
        latS.value.routingZoneRegionId,
        longW.value.routingZoneRegionId,
        fanW.value.routingZoneRegionId,
        sourceTerminalRegion.routingZoneRegionId,
    )

    retRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.destinationChipRef,
        destinationChipRef=obligation.sourceChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN,
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

    k: int = obligation.childCallIndex
    fanN_row: int = fanN.value.routingZoneRegionFrame.verticalStart
    fanS_row: int = fanS.value.routingZoneRegionFrame.verticalStart
    longW_col: int = longW.value.routingZoneRegionFrame.horizontalStart
    longE_col: int = longE.value.routingZoneRegionFrame.horizontalStart
    latN_row: int = latN.value.routingZoneRegionFrame.verticalStart
    latS_row: int = latS.value.routingZoneRegionFrame.verticalStart

    lane_left: int = longW_col + k
    lane_top: int = latN_row - k
    lane_right: int = longE_col - k
    lane_bottom: int = latS_row + k

    c_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex * (srcChipW + 2)
        + 1 + _HEADER + k
    )
    c_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.horizontalStart
        + destinationPlacement.orderIndex * (dstChipW + 2)
        + 1 + _HEADER
    )
    c_src_ret: int = c_src + 1
    c_dst_ret: int = c_dst + 1

    # Forward: clockwise N→S — exit N chip going right, descend via INTRA_LONG/E,
    # cross bottom via INTRA_LAT/S, enter S chip.
    fwdPointsRaw: list[tuple[int, int]] = [
        (c_src,       fanN_row),
        (c_src,       lane_top),
        (lane_right,  lane_top),
        (lane_right,  lane_bottom),
        (c_dst,       lane_bottom),
        (c_dst,       fanS_row),
    ]
    fwdPtsResult = _routePoints_build(fwdPointsRaw)
    if not result_isOkCheck(fwdPtsResult):
        return resultErr_build()

    intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
        sourceTerminalRegion.routingZoneRegionId,
        fanN.value.routingZoneRegionId,
        latN.value.routingZoneRegionId,
        longE.value.routingZoneRegionId,
        latS.value.routingZoneRegionId,
        fanS.value.routingZoneRegionId,
        destinationTerminalRegion.routingZoneRegionId,
    )

    fwdRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD,
        routePoints=fwdPtsResult.value,
        traversedRegionIds=intraRegionIds,
    )
    if not result_isOkCheck(fwdRouteResult):
        return resultErr_build()

    # Return: bottom-half clockwise S→N — uses return-port column (one right
    # of the signal column).
    retPointsRaw: list[tuple[int, int]] = [
        (c_dst_ret,  fanS_row),
        (c_dst_ret,  lane_bottom),
        (lane_left,  lane_bottom),
        (lane_left,  lane_top),
        (c_src_ret,  lane_top),
        (c_src_ret,  fanN_row),
    ]
    retPtsResult = _routePoints_build(retPointsRaw)
    if not result_isOkCheck(retPtsResult):
        return resultErr_build()

    retRegionIds: tuple[RoutingZoneRegionId, ...] = (
        destinationTerminalRegion.routingZoneRegionId,
        fanS.value.routingZoneRegionId,
        latS.value.routingZoneRegionId,
        longW.value.routingZoneRegionId,
        latN.value.routingZoneRegionId,
        fanN.value.routingZoneRegionId,
        sourceTerminalRegion.routingZoneRegionId,
    )

    retRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.destinationChipRef,
        destinationChipRef=obligation.sourceChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN,
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
