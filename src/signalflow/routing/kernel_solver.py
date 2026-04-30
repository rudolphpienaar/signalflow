"""Atomic Routing Kernel solver for SignalFlow.

This module realizes call-route obligations against a single RoutingKernel.
It connects a source wall to a destination wall using monotone ribbon packing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from signalflow.models import (
    ChipPortDeclaration,
    CircuitDocument,
    KernelObligation,
    Result,
    RoutingKernel,
    RoutingZoneLocalRouteSolveKind,
    RoutingZoneLocalSolvedRoute,
    RoutingZoneRegion,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    chipDrawGeometry_build,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneLocalSolvedRouteResult_build,
    routingZoneRoutePointResult_build,
)


def _terminalBodyRow_get(
    circuitDocument: CircuitDocument,
    obligation: KernelObligation,
    sourceIsRouteOrigin: bool,
    terminalIsReturn: bool,
) -> int:
    """Return compact chip-local row offset for one route endpoint."""

    callObligation = obligation.callRouteObligation
    chipRef = (
        callObligation.sourceChipRef
        if sourceIsRouteOrigin
        else callObligation.destinationChipRef
    )
    portDeclaration = (
        callObligation.sourcePortDeclaration
        if sourceIsRouteOrigin
        else _destinationPortDeclarationOrNone_get(
            circuitDocument,
            obligation,
        )
    )
    if portDeclaration is None:
        return 2 * (
            callObligation.childCallIndex
            if sourceIsRouteOrigin
            else obligation.destinationPortIndex
        ) + (1 if terminalIsReturn else 0)
    terminalName = (
        portDeclaration.returnName
        if terminalIsReturn
        else portDeclaration.signalName
    )
    if terminalName is None:
        return 2 * (
            callObligation.childCallIndex
            if sourceIsRouteOrigin
            else obligation.destinationPortIndex
        ) + (1 if terminalIsReturn else 0)
    chipResult = circuitDocument.circuitChipSet.chipResult_get(
        chipRef.chipId
    )
    if not result_isOkCheck(chipResult):
        return 2 * (
            callObligation.childCallIndex
            if sourceIsRouteOrigin
            else obligation.destinationPortIndex
        ) + (1 if terminalIsReturn else 0)
    drawGeometry = chipDrawGeometry_build(chipResult.value)
    offsets = (
        drawGeometry.eastTerminalLineOffsets
        if sourceIsRouteOrigin
        else drawGeometry.westTerminalLineOffsets
    )
    for name, lineOffset in offsets:
        if name == terminalName:
            return lineOffset
    return 2 * (
        callObligation.childCallIndex
        if sourceIsRouteOrigin
        else obligation.destinationPortIndex
    ) + (1 if terminalIsReturn else 0)


def _obligationHasReturn_check(
    circuitDocument: CircuitDocument,
    obligation: KernelObligation,
) -> bool:
    """Return whether one call obligation has both return endpoints."""

    sourcePortDeclaration = (
        obligation.callRouteObligation.sourcePortDeclaration
    )
    destinationPortDeclaration = _destinationPortDeclarationOrNone_get(
        circuitDocument,
        obligation,
    )
    return (
        sourcePortDeclaration is not None
        and sourcePortDeclaration.returnName is not None
        and destinationPortDeclaration is not None
        and destinationPortDeclaration.returnName is not None
    )


def _destinationPortDeclarationOrNone_get(
    circuitDocument: CircuitDocument,
    obligation: KernelObligation,
) -> ChipPortDeclaration | None:
    """Return the destination input declaration for one route obligation."""

    destinationChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.callRouteObligation.destinationChipRef.chipId
    )
    if not result_isOkCheck(destinationChipResult):
        return None
    inputPortDeclarations = (
        destinationChipResult.value.inputPortDeclarationSet.portDeclarations
    )
    if not inputPortDeclarations:
        return None
    if obligation.destinationPortIndex < len(inputPortDeclarations):
        return inputPortDeclarations[obligation.destinationPortIndex]
    return None


@dataclass(frozen=True)
class KernelRouteContext:
    """Parameterizes one of the four routing substrate families.

    Attributes:
        fanKind:      Region kind for the source/destination fan areas.
        longKind:     Region kind for the longitude (peel) columns.
        latKind:      Region kind for the latitude (travel) rows.
        srcSide:      Which terminal wall is the route source.
        latFwdSide:   Which latitude band carries the forward (signal) wire.
        fwdSolveKind: RoutingZoneLocalRouteSolveKind for the forward route.
        retSolveKind: RoutingZoneLocalRouteSolveKind for the return route.
    """

    fanKind: RoutingZoneRegionKind
    longKind: RoutingZoneRegionKind
    latKind: RoutingZoneRegionKind
    srcSide: RoutingZoneRegionSide
    latFwdSide: RoutingZoneRegionSide
    fwdSolveKind: RoutingZoneLocalRouteSolveKind
    retSolveKind: RoutingZoneLocalRouteSolveKind


#: WTE intra: caller (W) → callee (E) via interior INTRA ring, N lat for fwd.
WTE_INTRA_CONTEXT: KernelRouteContext = KernelRouteContext(
    fanKind=RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
    longKind=RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
    latKind=RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
    srcSide=RoutingZoneRegionSide.WEST,
    latFwdSide=RoutingZoneRegionSide.NORTH,
    fwdSolveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD,
    retSolveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN,
)

#: WTE extra: callee (E) → caller (W) via outer INTER ring, S lat for fwd.
WTE_EXTRA_CONTEXT: KernelRouteContext = KernelRouteContext(
    fanKind=RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
    longKind=RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
    latKind=RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
    srcSide=RoutingZoneRegionSide.EAST,
    latFwdSide=RoutingZoneRegionSide.SOUTH,
    fwdSolveKind=RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD,
    retSolveKind=RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN,
)

#: NTS intra: caller (N) → callee (S) via interior INTRA ring. Future use.
NTS_INTRA_CONTEXT: KernelRouteContext = KernelRouteContext(
    fanKind=RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
    longKind=RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
    latKind=RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
    srcSide=RoutingZoneRegionSide.NORTH,
    latFwdSide=RoutingZoneRegionSide.NORTH,
    fwdSolveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD,
    retSolveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN,
)

#: NTS extra: callee (S) → caller (N) via outer INTER ring. Future use.
NTS_EXTRA_CONTEXT: KernelRouteContext = KernelRouteContext(
    fanKind=RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
    longKind=RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
    latKind=RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
    srcSide=RoutingZoneRegionSide.SOUTH,
    latFwdSide=RoutingZoneRegionSide.SOUTH,
    fwdSolveKind=RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD,
    retSolveKind=RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN,
)


def _routePoints_materialize(
    rawPoints: Sequence[tuple[int, int]],
) -> Result[tuple[RoutingZoneRoutePoint, ...]]:
    """Convert raw (col, row) tuples into RoutingZoneRoutePoint objects."""
    points = []
    for col, row in rawPoints:
        res = routingZoneRoutePointResult_build(
            horizontalIndex=col, verticalIndex=row
        )
        if not result_isOkCheck(res):
            return resultErr_build()
        points.append(res.value)
    return resultOk_build(tuple(points))


def _bandRow_clampedFromFrame(
    verticalStart: int,
    verticalEndExclusive: int,
    *,
    offset: int,
    fromStart: bool,
) -> int:
    """Pick one row within a latitude band, clamped to the band's bounds."""

    bandEndInclusive: int = verticalEndExclusive - 1
    if fromStart:
        return min(verticalStart + offset, bandEndInclusive)
    return max(bandEndInclusive - offset, verticalStart)


def routingKernelSolvedRouteSetResult_build(
    circuitDocument: CircuitDocument,
    kernel: RoutingKernel,
    obligations: Sequence[KernelObligation],
    context: KernelRouteContext = WTE_INTRA_CONTEXT,
) -> Result[
    tuple[
        tuple[RoutingZoneLocalSolvedRoute, ...],
        tuple[RoutingZoneLocalSolvedRoute, ...],
    ]
]:
    """Solve one kernel's worth of obligations as a unified bundle.

    Args:
        circuitDocument: Active circuit document.
        kernel: Routing kernel owning the region geometry.
        obligations: Ordered list of obligations to route.
        context: Routing substrate to use; defaults to WTE_INTRA_CONTEXT.
    """

    if not obligations:
        return resultOk_build(((), ()))

    def _region_get(
        kind: RoutingZoneRegionKind,
        side: RoutingZoneRegionSide,
    ) -> RoutingZoneRegion | None:
        r = kernel.routingZoneRegionSet.regionForKindAndSideResult_get(
            kind, side
        )
        return r.value if result_isOkCheck(r) else None

    # Identify terminal walls sorted by horizontal position.
    all_regions = kernel.routingZoneRegionSet.routingZoneRegions
    terminal_regions = sorted(
        [
            r
            for r in all_regions
            if r.routingZoneRegionId.routingZoneRegionKind
            == RoutingZoneRegionKind.CHIP_TERMINAL
        ],
        key=lambda r: r.routingZoneRegionFrame.horizontalStart,
    )

    if len(terminal_regions) < 2:
        return resultOk_build(((), ()))

    # Source wall: leftmost for WEST-source contexts,
    # rightmost for EAST-source.
    if context.srcSide is RoutingZoneRegionSide.WEST:
        wallSrc = terminal_regions[0]
        wallDst = terminal_regions[-1]
    else:
        wallSrc = terminal_regions[-1]
        wallDst = terminal_regions[0]

    wallSrcSide = wallSrc.routingZoneRegionId.routingZoneRegionSide
    wallDstSide = wallDst.routingZoneRegionId.routingZoneRegionSide

    fanSrc = _region_get(context.fanKind, wallSrcSide)
    fanDst = _region_get(context.fanKind, wallDstSide)

    if not (fanSrc and fanDst):
        return _straightAcrossSolve_build(
            circuitDocument, kernel, obligations, wallSrc, wallDst, context
        )

    longSrcRegion = _region_get(context.longKind, wallSrcSide)
    longDstRegion = _region_get(context.longKind, wallDstSide)

    if not (longSrcRegion and longDstRegion):
        return _straightAcrossSolve_build(
            circuitDocument, kernel, obligations, wallSrc, wallDst, context
        )

    latRetSide = (
        RoutingZoneRegionSide.SOUTH
        if context.latFwdSide is RoutingZoneRegionSide.NORTH
        else RoutingZoneRegionSide.NORTH
    )
    latFwdRegion = _region_get(context.latKind, context.latFwdSide)
    latRetRegion = _region_get(context.latKind, latRetSide)

    # Wall exit columns: left edge for WEST walls, right edge for EAST walls.
    col_wallSrc = wallSrc.routingZoneRegionFrame.horizontalStart
    if wallSrcSide is not RoutingZoneRegionSide.WEST:
        col_wallSrc = (
            wallSrc.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        )
    col_wallDst = wallDst.routingZoneRegionFrame.horizontalStart
    if wallDstSide is not RoutingZoneRegionSide.WEST:
        col_wallDst = (
            wallDst.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        )

    long_src_start = longSrcRegion.routingZoneRegionFrame.horizontalStart
    long_dst_start = longDstRegion.routingZoneRegionFrame.horizontalStart

    # Forward lat: pack from band edge inward.
    # NORTH uses bottom edge, SOUTH uses top.
    # Return lat: opposite band, offset by 1 to keep fwd/ret rows distinct.
    latFwdRow: int | None = None
    latRetRow: int | None = None
    if context.latFwdSide is RoutingZoneRegionSide.NORTH:
        latFwdRow = (
            _bandRow_clampedFromFrame(
                latFwdRegion.routingZoneRegionFrame.verticalStart,
                latFwdRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                offset=0,
                fromStart=False,
            )
            if latFwdRegion is not None
            else None
        )
        latRetRow = (
            _bandRow_clampedFromFrame(
                latRetRegion.routingZoneRegionFrame.verticalStart,
                latRetRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                offset=1,
                fromStart=True,
            )
            if latRetRegion is not None
            else None
        )
    else:
        latFwdRow = (
            _bandRow_clampedFromFrame(
                latFwdRegion.routingZoneRegionFrame.verticalStart,
                latFwdRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                offset=0,
                fromStart=True,
            )
            if latFwdRegion is not None
            else None
        )
        latRetRow = (
            _bandRow_clampedFromFrame(
                latRetRegion.routingZoneRegionFrame.verticalStart,
                latRetRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                offset=1,
                fromStart=False,
            )
            if latRetRegion is not None
            else None
        )

    allRegionIds = tuple(r.routingZoneRegionId for r in all_regions)

    fwd_m, ret_m = [], []
    for k_ob in obligations:
        ob, srcP, dstP = (
            k_ob.callRouteObligation,
            k_ob.sourcePlacement,
            k_ob.destinationPlacement,
        )
        laneIdx = k_ob.laneIndex

        srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
            ob.sourceChipRef.chipId
        )
        dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
            ob.destinationChipRef.chipId
        )
        if not (
            result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)
        ):
            return resultErr_build()
        srcChipH = len(chipDrawLines_build(srcChipResult.value))
        dstChipH = len(chipDrawLines_build(dstChipResult.value))

        sourceSignalRowOffset = _terminalBodyRow_get(
            circuitDocument=circuitDocument,
            obligation=k_ob,
            sourceIsRouteOrigin=True,
            terminalIsReturn=False,
        )
        destinationSignalRowOffset = _terminalBodyRow_get(
            circuitDocument=circuitDocument,
            obligation=k_ob,
            sourceIsRouteOrigin=False,
            terminalIsReturn=False,
        )
        r_s = (
            wallSrc.routingZoneRegionFrame.verticalStart
            + srcP.orderIndex * (srcChipH + 2)
            + 1
            + sourceSignalRowOffset
        )
        r_d = (
            wallDst.routingZoneRegionFrame.verticalStart
            + dstP.orderIndex * (dstChipH + 2)
            + 1
            + destinationSignalRowOffset
        )
        hasReturnRoute = _obligationHasReturn_check(
            circuitDocument=circuitDocument,
            obligation=k_ob,
        )
        r_s_return = r_s
        r_d_return = r_d
        if hasReturnRoute:
            sourceReturnRowOffset = _terminalBodyRow_get(
                circuitDocument=circuitDocument,
                obligation=k_ob,
                sourceIsRouteOrigin=True,
                terminalIsReturn=True,
            )
            destinationReturnRowOffset = _terminalBodyRow_get(
                circuitDocument=circuitDocument,
                obligation=k_ob,
                sourceIsRouteOrigin=False,
                terminalIsReturn=True,
            )
            r_s_return = (
                wallSrc.routingZoneRegionFrame.verticalStart
                + srcP.orderIndex * (srcChipH + 2)
                + 1
                + sourceReturnRowOffset
            )
            r_d_return = (
                wallDst.routingZoneRegionFrame.verticalStart
                + dstP.orderIndex * (dstChipH + 2)
                + 1
                + destinationReturnRowOffset
            )

        # Peel column rule: source side gets no offset,
        # destination side gets +1.
        # This prevents same-lane forward and return peels
        # from sharing a column.
        fwd_peel_src = long_src_start + 2 * laneIdx
        fwd_peel_dst = long_dst_start + 2 * laneIdx + 1
        ret_peel_src = long_dst_start + 2 * laneIdx
        ret_peel_dst = long_src_start + 2 * laneIdx + 1

        # Forward lat travel row: NORTH band approaches from bottom upward;
        # SOUTH band approaches from top downward.
        if context.latFwdSide is RoutingZoneRegionSide.NORTH:
            f_travel_row = (
                (
                    _bandRow_clampedFromFrame(
                        latFwdRegion.routingZoneRegionFrame.verticalStart,
                        latFwdRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                        offset=2 * laneIdx,
                        fromStart=False,
                    )
                    if latFwdRegion is not None
                    else latFwdRow
                )
                if latFwdRow is not None
                else r_s
            )
            r_travel_row = (
                (
                    _bandRow_clampedFromFrame(
                        latRetRegion.routingZoneRegionFrame.verticalStart,
                        latRetRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                        offset=2 * laneIdx + 1,
                        fromStart=True,
                    )
                    if latRetRegion is not None
                    else latRetRow
                )
                if latRetRow is not None
                else r_d_return
            )
        else:
            f_travel_row = (
                (
                    _bandRow_clampedFromFrame(
                        latFwdRegion.routingZoneRegionFrame.verticalStart,
                        latFwdRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                        offset=2 * laneIdx,
                        fromStart=True,
                    )
                    if latFwdRegion is not None
                    else latFwdRow
                )
                if latFwdRow is not None
                else r_s
            )
            r_travel_row = (
                (
                    _bandRow_clampedFromFrame(
                        latRetRegion.routingZoneRegionFrame.verticalStart,
                        latRetRegion.routingZoneRegionFrame.verticalEnd_calculate(),
                        offset=2 * laneIdx + 1,
                        fromStart=False,
                    )
                    if latRetRegion is not None
                    else latRetRow
                )
                if latRetRow is not None
                else r_d_return
            )

        # Forward (signal) route — 6 keypoints
        f_pts_res = _routePoints_materialize(
            [
                (col_wallSrc, r_s),
                (fwd_peel_src, r_s),
                (fwd_peel_src, f_travel_row),
                (fwd_peel_dst, f_travel_row),
                (fwd_peel_dst, r_d),
                (col_wallDst, r_d),
            ]
        )
        if not result_isOkCheck(f_pts_res):
            return resultErr_build()
        fwd_m.append(
            routingZoneLocalSolvedRouteResult_build(
                kernel.routingZoneId,
                ob.sourceChipRef,
                ob.destinationChipRef,
                ob.childCallIndex,
                context.fwdSolveKind,
                f_pts_res.value,
                allRegionIds,
            ).unwrap()
        )

        if hasReturnRoute:
            # Return route — 6 keypoints; direction is dst→src.
            r_pts_res = _routePoints_materialize(
                [
                    (col_wallDst, r_d_return),
                    (ret_peel_src, r_d_return),
                    (ret_peel_src, r_travel_row),
                    (ret_peel_dst, r_travel_row),
                    (ret_peel_dst, r_s_return),
                    (col_wallSrc, r_s_return),
                ]
            )
            if not result_isOkCheck(r_pts_res):
                return resultErr_build()
            # Return: sourceChipRef is the route's origin
            # (callee for intra, caller for extra).
            ret_m.append(
                routingZoneLocalSolvedRouteResult_build(
                    kernel.routingZoneId,
                    ob.destinationChipRef,
                    ob.sourceChipRef,
                    ob.childCallIndex,
                    context.retSolveKind,
                    r_pts_res.value,
                    allRegionIds,
                ).unwrap()
            )

    return resultOk_build((tuple(fwd_m), tuple(ret_m)))


def _straightAcrossSolve_build(
    circuitDocument: CircuitDocument,
    kernel: RoutingKernel,
    obligations: Sequence[KernelObligation],
    wallSrc: RoutingZoneRegion,
    wallDst: RoutingZoneRegion,
    context: KernelRouteContext = WTE_INTRA_CONTEXT,
) -> Result[
    tuple[
        tuple[RoutingZoneLocalSolvedRoute, ...],
        tuple[RoutingZoneLocalSolvedRoute, ...],
    ]
]:
    wallSrcSide = wallSrc.routingZoneRegionId.routingZoneRegionSide
    wallDstSide = wallDst.routingZoneRegionId.routingZoneRegionSide
    col_wallSrc = wallSrc.routingZoneRegionFrame.horizontalStart
    if wallSrcSide is not RoutingZoneRegionSide.WEST:
        col_wallSrc = (
            wallSrc.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        )
    col_wallDst = wallDst.routingZoneRegionFrame.horizontalStart
    if wallDstSide is not RoutingZoneRegionSide.WEST:
        col_wallDst = (
            wallDst.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        )

    allRegionIds = tuple(
        r.routingZoneRegionId
        for r in kernel.routingZoneRegionSet.routingZoneRegions
    )
    fwd_m, ret_m = [], []
    for k_ob in obligations:
        ob, srcP, dstP = (
            k_ob.callRouteObligation,
            k_ob.sourcePlacement,
            k_ob.destinationPlacement,
        )
        srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
            ob.sourceChipRef.chipId
        )
        dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
            ob.destinationChipRef.chipId
        )
        if not (
            result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)
        ):
            return resultErr_build()
        srcChipH = len(chipDrawLines_build(srcChipResult.value))
        dstChipH = len(chipDrawLines_build(dstChipResult.value))
        sourceSignalRowOffset = _terminalBodyRow_get(
            circuitDocument=circuitDocument,
            obligation=k_ob,
            sourceIsRouteOrigin=True,
            terminalIsReturn=False,
        )
        destinationSignalRowOffset = _terminalBodyRow_get(
            circuitDocument=circuitDocument,
            obligation=k_ob,
            sourceIsRouteOrigin=False,
            terminalIsReturn=False,
        )
        r_s = (
            wallSrc.routingZoneRegionFrame.verticalStart
            + srcP.orderIndex * (srcChipH + 2)
            + 1
            + sourceSignalRowOffset
        )
        r_d = (
            wallDst.routingZoneRegionFrame.verticalStart
            + dstP.orderIndex * (dstChipH + 2)
            + 1
            + destinationSignalRowOffset
        )

        f_pts_res = _routePoints_materialize(
            [(col_wallSrc, r_s), (col_wallDst, r_d)]
        )
        if not result_isOkCheck(f_pts_res):
            return resultErr_build()

        fwd_m.append(
            routingZoneLocalSolvedRouteResult_build(
                kernel.routingZoneId,
                ob.sourceChipRef,
                ob.destinationChipRef,
                ob.childCallIndex,
                context.fwdSolveKind,
                f_pts_res.value,
                allRegionIds,
            ).unwrap()
        )
        if _obligationHasReturn_check(
            circuitDocument=circuitDocument,
            obligation=k_ob,
        ):
            sourceReturnRowOffset = _terminalBodyRow_get(
                circuitDocument=circuitDocument,
                obligation=k_ob,
                sourceIsRouteOrigin=True,
                terminalIsReturn=True,
            )
            destinationReturnRowOffset = _terminalBodyRow_get(
                circuitDocument=circuitDocument,
                obligation=k_ob,
                sourceIsRouteOrigin=False,
                terminalIsReturn=True,
            )
            r_s_return = (
                wallSrc.routingZoneRegionFrame.verticalStart
                + srcP.orderIndex * (srcChipH + 2)
                + 1
                + sourceReturnRowOffset
            )
            r_d_return = (
                wallDst.routingZoneRegionFrame.verticalStart
                + dstP.orderIndex * (dstChipH + 2)
                + 1
                + destinationReturnRowOffset
            )
            r_pts_res = _routePoints_materialize(
                [(col_wallDst, r_d_return), (col_wallSrc, r_s_return)]
            )
            if not result_isOkCheck(r_pts_res):
                return resultErr_build()
            ret_m.append(
                routingZoneLocalSolvedRouteResult_build(
                    kernel.routingZoneId,
                    ob.sourceChipRef,
                    ob.destinationChipRef,
                    ob.childCallIndex,
                    context.retSolveKind,
                    r_pts_res.value,
                    allRegionIds,
                ).unwrap()
            )
    return resultOk_build((tuple(fwd_m), tuple(ret_m)))
