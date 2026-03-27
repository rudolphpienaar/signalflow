"""Atomic Routing Kernel solver for SignalFlow.

This module realizes call-route obligations against a single RoutingKernel.
It connects a source wall to a destination wall using monotone ribbon packing.
"""
from __future__ import annotations

from collections.abc import Sequence

from signalflow.models import (
    CircuitDocument,
    KernelObligation,
    Result,
    RoutingKernel,
    RoutingZoneLocalRouteSolveKind,
    RoutingZoneLocalSolvedRoute,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneLocalSolvedRouteResult_build,
    routingZoneRoutePointResult_build,
)


def _routePoints_materialize(
    rawPoints: Sequence[tuple[int, int]]
) -> Result[tuple[RoutingZoneRoutePoint, ...]]:
    """Convert raw (col, row) tuples into RoutingZoneRoutePoint objects."""
    points = []
    for col, row in rawPoints:
        res = routingZoneRoutePointResult_build(horizontalIndex=col, verticalIndex=row)
        if not result_isOkCheck(res):
            return resultErr_build()
        points.append(res.value)
    return resultOk_build(tuple(points))


def routingKernelSolvedRouteSetResult_build(
    circuitDocument: CircuitDocument,
    kernel: RoutingKernel,
    obligations: Sequence[KernelObligation],
) -> Result[tuple[tuple[RoutingZoneLocalSolvedRoute, ...], tuple[RoutingZoneLocalSolvedRoute, ...]]]:
    """Solve one kernel's worth of obligations as a unified bundle."""

    if not obligations:
        return resultOk_build(((), ()))

    def _region_get(kind, side):
        r = kernel.routingZoneRegionSet.regionForKindAndSideResult_get(kind, side)
        if result_isOkCheck(r):
            return r.value
        kind_map = {
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT: RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE: RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE: RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT: RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE: RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE: RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        }
        if kind in kind_map:
            r = kernel.routingZoneRegionSet.regionForKindAndSideResult_get(kind_map[kind], side)
            if result_isOkCheck(r):
                return r.value
        return None

    # Identify the full region chain
    all_regions = kernel.routingZoneRegionSet.routingZoneRegions
    terminal_regions = sorted(
        [r for r in all_regions if r.routingZoneRegionId.routingZoneRegionKind == RoutingZoneRegionKind.CHIP_TERMINAL],
        key=lambda r: r.routingZoneRegionFrame.horizontalStart
    )

    if len(terminal_regions) < 2:
        return resultOk_build(((), ()))

    wallSrc = terminal_regions[0]
    wallDst = terminal_regions[-1]
    fanSrc = _region_get(RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, wallSrc.routingZoneRegionId.routingZoneRegionSide)
    fanDst = _region_get(RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, wallDst.routingZoneRegionId.routingZoneRegionSide)
    latNRegion = _region_get(RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH)
    latSRegion = _region_get(RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH)

    if not (fanSrc and fanDst):
        return _straightAcrossSolve_build(circuitDocument, kernel, obligations, wallSrc, wallDst)

    # Longitude regions supply per-wire peel columns (span = 2*N for N obligations)
    longWRegion = _region_get(RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST)
    longERegion = _region_get(RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST)

    if not (longWRegion and longERegion):
        return _straightAcrossSolve_build(circuitDocument, kernel, obligations, wallSrc, wallDst)

    col_wallSrc = wallSrc.routingZoneRegionFrame.horizontalStart
    if wallSrc.routingZoneRegionId.routingZoneRegionSide != RoutingZoneRegionSide.WEST:
        col_wallSrc = wallSrc.routingZoneRegionFrame.horizontalEnd_calculate() - 1

    col_wallDst = wallDst.routingZoneRegionFrame.horizontalStart
    if wallDst.routingZoneRegionId.routingZoneRegionSide != RoutingZoneRegionSide.WEST:
        col_wallDst = wallDst.routingZoneRegionFrame.horizontalEnd_calculate() - 1

    longW_start = longWRegion.routingZoneRegionFrame.horizontalStart
    longE_start = longERegion.routingZoneRegionFrame.horizontalStart

    latN_end = latNRegion.routingZoneRegionFrame.verticalEnd_calculate() - 1 if latNRegion is not None else None
    latS_start = latSRegion.routingZoneRegionFrame.verticalStart if latSRegion is not None else None

    allRegionIds = tuple(r.routingZoneRegionId for r in all_regions)

    _HEADER = 3
    fwd_m, ret_m = [], []
    for k_ob in obligations:
        ob, srcP, dstP = k_ob.callRouteObligation, k_ob.sourcePlacement, k_ob.destinationPlacement
        laneIdx = k_ob.laneIndex

        srcChipResult = circuitDocument.circuitChipSet.chipResult_get(ob.sourceChipRef.chipId)
        dstChipResult = circuitDocument.circuitChipSet.chipResult_get(ob.destinationChipRef.chipId)
        if not (result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)):
            return resultErr_build()
        srcChipH = len(chipDrawLines_build(srcChipResult.value))
        dstChipH = len(chipDrawLines_build(dstChipResult.value))

        r_s = wallSrc.routingZoneRegionFrame.verticalStart + srcP.orderIndex * (srcChipH + 2) + 1 + _HEADER + 2 * ob.childCallIndex
        r_d = wallDst.routingZoneRegionFrame.verticalStart + dstP.orderIndex * (dstChipH + 2) + 1 + _HEADER + 2 * k_ob.destinationPortIndex

        # West peels: inner routes (higher laneIdx) use left-side columns, outer routes use right-side.
        # East peels: REVERSED — inner routes (higher laneIdx) use right-side columns so their
        # descent is outside outer routes' horizontal travel spans, preventing crossings.
        fwd_peel_left  = longW_start + 2 * laneIdx
        fwd_peel_right = longE_start + 2 * laneIdx + 1
        ret_peel_left  = longW_start + (2 * laneIdx + 1)
        ret_peel_right = longE_start + 2 * laneIdx

        # Latitude travel rows: forward uses south end of north band; return uses north start of south band.
        f_travel_row = (latN_end - 2 * laneIdx) if latN_end is not None else r_s
        r_travel_row = (latS_start + (2 * laneIdx + 1)) if latS_start is not None else (r_d + 1)

        # Forward (signal) route — 6 keypoints
        f_pts_res = _routePoints_materialize([
            (col_wallSrc,   r_s),
            (fwd_peel_left, r_s),
            (fwd_peel_left, f_travel_row),
            (fwd_peel_right, f_travel_row),
            (fwd_peel_right, r_d),
            (col_wallDst,   r_d),
        ])
        if not result_isOkCheck(f_pts_res):
            return resultErr_build()
        fwd_m.append(routingZoneLocalSolvedRouteResult_build(
            kernel.routingZoneId, ob.sourceChipRef, ob.destinationChipRef, ob.childCallIndex,
            RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD, f_pts_res.value, allRegionIds,
        ).value)

        # Return route — 6 keypoints; direction is callee→caller
        r_pts_res = _routePoints_materialize([
            (col_wallDst,    r_d + 1),
            (ret_peel_right, r_d + 1),
            (ret_peel_right, r_travel_row),
            (ret_peel_left,  r_travel_row),
            (ret_peel_left,  r_s + 1),
            (col_wallSrc,    r_s + 1),
        ])
        if not result_isOkCheck(r_pts_res):
            return resultErr_build()
        # Return: sourceChipRef is the callee (origin of return), destinationChipRef is the caller
        ret_m.append(routingZoneLocalSolvedRouteResult_build(
            kernel.routingZoneId, ob.destinationChipRef, ob.sourceChipRef, ob.childCallIndex,
            RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN, r_pts_res.value, allRegionIds,
        ).value)

    return resultOk_build((tuple(fwd_m), tuple(ret_m)))


def _straightAcrossSolve_build(circuitDocument, kernel, obligations, wallSrc, wallDst):
    col_wallSrc = wallSrc.routingZoneRegionFrame.horizontalStart
    if wallSrc.routingZoneRegionId.routingZoneRegionSide != RoutingZoneRegionSide.WEST:
        col_wallSrc = wallSrc.routingZoneRegionFrame.horizontalEnd_calculate() - 1
    col_wallDst = wallDst.routingZoneRegionFrame.horizontalStart
    if wallDst.routingZoneRegionId.routingZoneRegionSide != RoutingZoneRegionSide.WEST:
        col_wallDst = wallDst.routingZoneRegionFrame.horizontalEnd_calculate() - 1

    allRegionIds = tuple(r.routingZoneRegionId for r in kernel.routingZoneRegionSet.routingZoneRegions)
    fwd_m, ret_m = [], []
    _HEADER = 3
    for k_ob in obligations:
        ob, srcP, dstP = k_ob.callRouteObligation, k_ob.sourcePlacement, k_ob.destinationPlacement
        srcChipResult = circuitDocument.circuitChipSet.chipResult_get(ob.sourceChipRef.chipId)
        dstChipResult = circuitDocument.circuitChipSet.chipResult_get(ob.destinationChipRef.chipId)
        if not (result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)):
            return resultErr_build()
        srcChipH = len(chipDrawLines_build(srcChipResult.value))
        dstChipH = len(chipDrawLines_build(dstChipResult.value))
        r_s = wallSrc.routingZoneRegionFrame.verticalStart + srcP.orderIndex * (srcChipH + 2) + 1 + _HEADER + 2 * ob.childCallIndex
        r_d = wallDst.routingZoneRegionFrame.verticalStart + dstP.orderIndex * (dstChipH + 2) + 1 + _HEADER + 2 * k_ob.destinationPortIndex

        f_pts_res = _routePoints_materialize([(col_wallSrc, r_s), (col_wallDst, r_d)])
        r_pts_res = _routePoints_materialize([(col_wallDst, r_d + 1), (col_wallSrc, r_s + 1)])

        if not (result_isOkCheck(f_pts_res) and result_isOkCheck(r_pts_res)):
            return resultErr_build()

        fwd_m.append(routingZoneLocalSolvedRouteResult_build(kernel.routingZoneId, ob.sourceChipRef, ob.destinationChipRef, ob.childCallIndex, RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD, f_pts_res.value, allRegionIds).value)
        ret_m.append(routingZoneLocalSolvedRouteResult_build(kernel.routingZoneId, ob.sourceChipRef, ob.destinationChipRef, ob.childCallIndex, RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN, r_pts_res.value, allRegionIds).value)
    return resultOk_build((tuple(fwd_m), tuple(ret_m)))
