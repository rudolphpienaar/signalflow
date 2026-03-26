"""Interconnect seam routing solver for the new SignalFlow engine.

This module realizes `SEAM_CROSSING` call obligations against one placed
`RoutingZoneInterconnect` plus the neighboring inter-routing fan-in/out
regions. It produces explicit planning-grid seam geometry.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from signalflow.models import (
    CallRouteObligation,
    CallRouteObligationSet,
    Chip,
    ChipPlacement,
    ChipTerminalSide,
    CircuitDocument,
    KernelObligation,
    Result,
    RouteObligationScope,
    RoutingKernel,
    RoutingZone,
    RoutingZoneFamily,
    RoutingZoneGrid,
    RoutingZoneInterconnect,
    RoutingZoneInterconnectAxis,
    RoutingZoneInterconnectRouteSolveKind,
    RoutingZoneInterconnectSolvedRoute,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneRegion,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSet,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    RoutingZoneSense,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneInterconnectSolvedRouteResult_build,
    routingZoneInterconnectSolvedRouteSetResult_build,
    routingZoneRegionResult_build,
    routingZoneResult_build,
    routingZoneRoutePointResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.routing.geometry import (
    ChipLocalGeometry,
    chipCanvasPlacementGeometry_build,
    chipLocalGeometryResult_build,
)
from signalflow.routing.kernel_solver import routingKernelSolvedRouteSetResult_build
from signalflow.routing.route import routePoints_realize


@dataclass(frozen=True)
class _PreparedSeamDemand:
    """Resolved seam-routing demand for one seam-crossing call."""

    callRouteObligation: CallRouteObligation
    sourcePlacement: ChipPlacement
    destinationPlacement: ChipPlacement
    sourceInterFanRegion: RoutingZoneRegion
    destinationInterFanRegion: RoutingZoneRegion
    sourceInterTravelRegion: RoutingZoneRegion
    destinationInterTravelRegion: RoutingZoneRegion
    interconnect: RoutingZoneInterconnect
    sourceZone: RoutingZone
    destinationZone: RoutingZone
    srcChipLines: tuple[str, ...]
    dstChipLines: tuple[str, ...]
    destinationPortIndex: int
    sourceSparseWallRows: tuple[int, int] | None
    destinationSparseWallRows: tuple[int, int] | None


def routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneInterconnectSolvedRouteSet]:
    """Build solved seam routes from placed geometry and seam obligations."""

    solvedRoutesMutable: list[RoutingZoneInterconnectSolvedRoute] = []
    seamDemandsByInterconnectMutable: dict[object, list[_PreparedSeamDemand]] = {}
    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.SEAM_CROSSING
        ):
            continue
        preparedDemandResult = _preparedSeamDemandResult_buildFromObligation(
            circuitDocument=circuitDocument,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            callRouteObligation=callRouteObligation,
        )
        if not result_isOkCheck(preparedDemandResult):
            return resultErr_build()
        interconnectId = (
            preparedDemandResult.value.interconnect.routingZoneInterconnectId
        )
        if interconnectId not in seamDemandsByInterconnectMutable:
            seamDemandsByInterconnectMutable[interconnectId] = []
        seamDemandsByInterconnectMutable[interconnectId].append(
            preparedDemandResult.value
        )

    seamDemands: list[_PreparedSeamDemand]
    for seamDemands in seamDemandsByInterconnectMutable.values():
        d0 = seamDemands[0]
        interconnect: RoutingZoneInterconnect = d0.interconnect
        sortedSeamDemands = sorted(seamDemands, key=_seamDemandSortKey_build)

        # 1. Gather the full chain of regions for the Mega-Kernel
        # (Source Wall -> Source Breakout -> Seam -> Destination Breakout -> Destination Wall)

        # Build a synthetic region for the Interconnect Seam itself
        seamRegionResult = routingZoneRegionResult_build(
            routingZoneRegionId=RoutingZoneRegionId(
                routingZoneId=interconnect.sourceZoneId, # Dummy owner
                routingZoneRegionKind=RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
                routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                routingZoneRegionTag="seam",
            ),
            routingZoneRegionFrame=RoutingZoneRegionFrame(
                horizontalStart=interconnect.routingZoneInterconnectFrame.horizontalStart,
                verticalStart=interconnect.routingZoneInterconnectFrame.verticalStart,
                horizontalSpan=interconnect.routingZoneInterconnectFrame.horizontalSpan,
                verticalSpan=interconnect.routingZoneInterconnectFrame.verticalSpan,
            )
        )
        if not result_isOkCheck(seamRegionResult):
            return resultErr_build()

        # Find the source/destination walls based on seam axis
        axisResult = interconnect.interconnectAxisResult_get()
        if not result_isOkCheck(axisResult):
            return resultErr_build()
        if axisResult.value == RoutingZoneInterconnectAxis.HORIZONTAL:
            srcWallSide = RoutingZoneRegionSide.EAST
            dstWallSide = RoutingZoneRegionSide.WEST
        else:  # VERTICAL (north-to-south)
            srcWallSide = RoutingZoneRegionSide.SOUTH
            dstWallSide = RoutingZoneRegionSide.NORTH
        srcWallResult = d0.sourceZone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.CHIP_TERMINAL, srcWallSide
        )
        dstWallResult = d0.destinationZone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.CHIP_TERMINAL, dstWallSide
        )
        if not (result_isOkCheck(srcWallResult) and result_isOkCheck(dstWallResult)):
            return resultErr_build()
        srcWall = srcWallResult.value
        dstWall = dstWallResult.value

        # Collect the mega-kernel region chain:
        # Source Wall → Source Fan → Source Travel → Seam → Dst Travel → Dst Fan → Dst Wall
        # INTRA latitude bands do NOT belong in a seam kernel.
        megaRegions = [
            srcWall,
            d0.sourceInterFanRegion,
            d0.sourceInterTravelRegion,
            seamRegionResult.value,
            d0.destinationInterTravelRegion,
            d0.destinationInterFanRegion,
            dstWall,
        ]

        # 2. Build the Mega-Kernel
        breakoutZoneResult = routingZoneResult_build(
            routingZoneId=interconnect.destinationZoneId,
            routingZoneSense=placedRoutingZoneGrid.worldSense,
            routingZoneFamily=RoutingZoneFamily.EMBEDDED,
            routingZoneRegionSet=RoutingZoneRegionSet(tuple(megaRegions)),
        )
        if not result_isOkCheck(breakoutZoneResult):
            return resultErr_build()

        kernel = RoutingKernel(
            routingZoneId=interconnect.destinationZoneId,
            routingZoneRegionSet=breakoutZoneResult.value.routingZoneRegionSet,
        )

        # Map sorted seam demands to KernelObligations
        # For converging seams, we need to know the index of this specific
        # incoming call at the destination chip to assign the correct port.
        incomingCallsByChip: dict[object, list[CallRouteObligation]] = {}
        for d in sortedSeamDemands:
            incomingCallsByChip.setdefault(d.destinationPlacement.chipRef, []).append(d.callRouteObligation)

        kernelObligations = []
        for d in sortedSeamDemands:
            # Find the port index based on the incoming call order at the destination
            portIndex = incomingCallsByChip[d.destinationPlacement.chipRef].index(d.callRouteObligation)

            kernelObligations.append(
                KernelObligation(
                    callRouteObligation=d.callRouteObligation,
                    sourcePlacement=d.sourcePlacement,
                    destinationPlacement=d.destinationPlacement,
                    destinationPortIndex=portIndex,
                )
            )


        # 4. Solve the Mega-Kernel
        kernelResult = routingKernelSolvedRouteSetResult_build(
            circuitDocument=circuitDocument,
            kernel=kernel,
            obligations=tuple(kernelObligations),
        )
        if not result_isOkCheck(kernelResult):
            return resultErr_build()

        # 5. Map back to Interconnect Solved Routes
        fwd, ret = kernelResult.value
        for i, (fwd_route, ret_route) in enumerate(zip(fwd, ret)):
            preparedDemand = sortedSeamDemands[i]

            solvedRoutesMutable.append(routingZoneInterconnectSolvedRouteResult_build(
                routingZoneInterconnectId=interconnect.routingZoneInterconnectId,
                sourceChipRef=preparedDemand.sourcePlacement.chipRef,
                destinationChipRef=preparedDemand.destinationPlacement.chipRef,
                childCallIndex=preparedDemand.callRouteObligation.childCallIndex,
                solveKind=RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM,
                routePoints=fwd_route.routePoints,
                traversedRegionIds=fwd_route.traversedRegionIds,
            ).value)

            solvedRoutesMutable.append(routingZoneInterconnectSolvedRouteResult_build(
                routingZoneInterconnectId=interconnect.routingZoneInterconnectId,
                sourceChipRef=preparedDemand.destinationPlacement.chipRef,
                destinationChipRef=preparedDemand.sourcePlacement.chipRef,
                childCallIndex=preparedDemand.callRouteObligation.childCallIndex,
                solveKind=RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM_RETURN,
                routePoints=ret_route.routePoints,
                traversedRegionIds=ret_route.traversedRegionIds,
            ).value)

    return routingZoneInterconnectSolvedRouteSetResult_build(
        routingZoneInterconnectSolvedRoutes=tuple(solvedRoutesMutable)
    )


def _preparedSeamDemandResult_buildFromObligation(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligation: CallRouteObligation,
) -> Result[_PreparedSeamDemand]:
    """Resolve one seam-crossing call into prepared seam demand."""

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

    destinationPortIndexResult = _destinationPortIndexResult_build(
        circuitDocument=circuitDocument,
        callRouteObligation=callRouteObligation,
    )
    if not result_isOkCheck(destinationPortIndexResult):
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
    sourceInterTravelRegionResult = _interRoutingTravelRegionResult_build(
        routingZone=sourceZoneResult.value,
        chipPlacement=sourcePlacementResult.value,
    )
    if not result_isOkCheck(sourceInterTravelRegionResult):
        return resultErr_build()
    destinationInterTravelRegionResult = _interRoutingTravelRegionResult_build(
        routingZone=destinationZoneResult.value,
        chipPlacement=destinationPlacementResult.value,
    )
    if not result_isOkCheck(destinationInterTravelRegionResult):
        return resultErr_build()
    sourceSparseWallRowsResult = _sparseSeamFacingWallRowsResult_build(
        routingZone=sourceZoneResult.value,
        chipPlacement=sourcePlacementResult.value,
        chip=sourceChipResult.value,
        circuitDocument=circuitDocument,
    )
    if not result_isOkCheck(sourceSparseWallRowsResult):
        return resultErr_build()
    destinationSparseWallRowsResult = _sparseSeamFacingWallRowsResult_build(
        routingZone=destinationZoneResult.value,
        chipPlacement=destinationPlacementResult.value,
        chip=destinationChipResult.value,
        circuitDocument=circuitDocument,
    )
    if not result_isOkCheck(destinationSparseWallRowsResult):
        return resultErr_build()

    return resultOk_build(
        _PreparedSeamDemand(
            callRouteObligation=callRouteObligation,
            sourcePlacement=sourcePlacementResult.value,
            destinationPlacement=destinationPlacementResult.value,
            sourceInterFanRegion=sourceInterFanRegionResult.value,
            destinationInterFanRegion=destinationInterFanRegionResult.value,
            sourceInterTravelRegion=sourceInterTravelRegionResult.value,
            destinationInterTravelRegion=destinationInterTravelRegionResult.value,
            interconnect=interconnectResult.value,
            sourceZone=sourceZoneResult.value,
            destinationZone=destinationZoneResult.value,
            srcChipLines=chipDrawLines_build(sourceChipResult.value),
            dstChipLines=chipDrawLines_build(destinationChipResult.value),
            destinationPortIndex=destinationPortIndexResult.value,
            sourceSparseWallRows=sourceSparseWallRowsResult.value,
            destinationSparseWallRows=destinationSparseWallRowsResult.value,
        )
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
        code="routing.interconnect_solver.missing_chip_zone",
        message="Placed RoutingZoneGrid does not contain the requested chip",
    )
    return resultErr_build()


def _sparseSeamFacingWallRowsResult_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
    chip: Chip,
    circuitDocument: CircuitDocument,
) -> Result[tuple[int, int] | None]:
    """Return centered seam-facing wall rows for a collapsed two-terminal wall."""

    regionSide = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    if regionSide is None:
        return resultOk_build(None)
    if routingZone.routingZoneSense is not RoutingZoneSense.WEST_TO_EAST:
        return resultOk_build(None)
    if regionSide.value not in {"west", "east"}:
        return resultOk_build(None)

    terminalSide = (
        ChipTerminalSide.WEST
        if regionSide.value == "west"
        else ChipTerminalSide.EAST
    )

    terminalRegionResult = routingZone.routingZoneRegionSet.regionResult_get(
        chipPlacement.chipTerminalRegionId
    )
    if not result_isOkCheck(terminalRegionResult):
        return resultErr_build()

    sidePlacements = sorted(
        (
            placement
            for placement in routingZone.chipPlacementSet.placements
            if placement.chipTerminalRegionId == chipPlacement.chipTerminalRegionId
        ),
        key=lambda placement: placement.orderIndex,
    )

    stackOffset: int = 0
    placement: ChipPlacement
    for placement in sidePlacements:
        if placement.chipRef == chipPlacement.chipRef:
            break
        priorChipResult = circuitDocument.circuitChipSet.chipResult_get(
            placement.chipRef.chipId
        )
        if not result_isOkCheck(priorChipResult):
            return resultErr_build()
        stackOffset += len(chipDrawLines_build(priorChipResult.value))

    chipLocalGeometryResult: Result[ChipLocalGeometry] = (
        chipLocalGeometryResult_build(chip)
    )
    if not result_isOkCheck(chipLocalGeometryResult):
        return resultErr_build()
    placementGeometry = chipCanvasPlacementGeometry_build(
        chipLocalGeometry=chipLocalGeometryResult.value,
        routingZoneSense=routingZone.routingZoneSense,
        regionSide=regionSide,
        terminalRegionVerticalStart=(
            terminalRegionResult.value.routingZoneRegionFrame.verticalStart
        ),
        terminalRegionHorizontalStart=(
            terminalRegionResult.value.routingZoneRegionFrame.horizontalStart
        ),
        stackOffset=stackOffset,
    )
    lineOffsets = sorted(
        entry.lineOffset
        for entry in chipLocalGeometryResult.value.terminalLineOffsets
        if entry.terminalSide is terminalSide
    )
    if len(lineOffsets) != 2:
        return resultOk_build(None)
    return resultOk_build(
        (
            placementGeometry.drawWorldRow + lineOffsets[0],
            placementGeometry.drawWorldRow + lineOffsets[1],
        )
    )


def _routingZoneInterconnectSolvedRouteResult_buildFromPreparedDemandAndSense(
    preparedDemand: _PreparedSeamDemand,
    seamPairIndex: int,
    seamPairCount: int,
    sourceBundleIndex: int,
    sourceBundleCount: int,
    destinationBundleIndex: int,
    destinationBundleCount: int,
    isReturn: bool,
    occupiedCells: set[tuple[int, int]],
) -> Result[RoutingZoneInterconnectSolvedRoute]:
    """Build one seam route for one prepared seam demand and sense."""

    if isReturn:
        geometryResult = _seamGeometryResult_build(
            interconnect=preparedDemand.interconnect,
            sourcePlacement=preparedDemand.destinationPlacement,
            destinationPlacement=preparedDemand.sourcePlacement,
            sourceInterFanRegion=preparedDemand.destinationInterFanRegion,
            destinationInterFanRegion=preparedDemand.sourceInterFanRegion,
            sourceInterTravelRegion=preparedDemand.destinationInterTravelRegion,
            destinationInterTravelRegion=preparedDemand.sourceInterTravelRegion,
            srcChipLines=preparedDemand.dstChipLines,
            dstChipLines=preparedDemand.srcChipLines,
            sourcePortIndex=preparedDemand.destinationPortIndex,
            destinationPortIndex=preparedDemand.callRouteObligation.childCallIndex,
            sourceSparseWallRows=preparedDemand.destinationSparseWallRows,
            destinationSparseWallRows=preparedDemand.sourceSparseWallRows,
            seamPairIndex=seamPairIndex,
            seamPairCount=seamPairCount,
            sourceBundleIndex=destinationBundleIndex,
            sourceBundleCount=destinationBundleCount,
            destinationBundleIndex=sourceBundleIndex,
            destinationBundleCount=sourceBundleCount,
            isReturn=True,
            occupiedCells=occupiedCells,
        )
    else:
        geometryResult = _seamGeometryResult_build(
            interconnect=preparedDemand.interconnect,
            sourcePlacement=preparedDemand.sourcePlacement,
            destinationPlacement=preparedDemand.destinationPlacement,
            sourceInterFanRegion=preparedDemand.sourceInterFanRegion,
            destinationInterFanRegion=preparedDemand.destinationInterFanRegion,
            sourceInterTravelRegion=preparedDemand.sourceInterTravelRegion,
            destinationInterTravelRegion=preparedDemand.destinationInterTravelRegion,
            srcChipLines=preparedDemand.srcChipLines,
            dstChipLines=preparedDemand.dstChipLines,
            sourcePortIndex=preparedDemand.callRouteObligation.childCallIndex,
            destinationPortIndex=preparedDemand.destinationPortIndex,
            sourceSparseWallRows=preparedDemand.sourceSparseWallRows,
            destinationSparseWallRows=preparedDemand.destinationSparseWallRows,
            seamPairIndex=seamPairIndex,
            seamPairCount=seamPairCount,
            sourceBundleIndex=sourceBundleIndex,
            sourceBundleCount=sourceBundleCount,
            destinationBundleIndex=destinationBundleIndex,
            destinationBundleCount=destinationBundleCount,
            isReturn=False,
            occupiedCells=occupiedCells,
        )
    if not result_isOkCheck(geometryResult):
        return resultErr_build()

    routeResult = routingZoneInterconnectSolvedRouteResult_build(
        routingZoneInterconnectId=preparedDemand.interconnect.routingZoneInterconnectId,
        sourceChipRef=(
            preparedDemand.callRouteObligation.destinationChipRef
            if isReturn
            else preparedDemand.callRouteObligation.sourceChipRef
        ),
        destinationChipRef=(
            preparedDemand.callRouteObligation.sourceChipRef
            if isReturn
            else preparedDemand.callRouteObligation.destinationChipRef
        ),
        childCallIndex=preparedDemand.callRouteObligation.childCallIndex,
        solveKind=geometryResult.value[0],
        routePoints=geometryResult.value[1],
        traversedRegionIds=geometryResult.value[2],
    )
    if not result_isOkCheck(routeResult):
        return resultErr_build()
    realizedRouteResult = routePoints_realize(
        sourceChipRef=routeResult.value.sourceChipRef,
        destinationChipRef=routeResult.value.destinationChipRef,
        childCallIndex=routeResult.value.childCallIndex,
        routePoints=routeResult.value.routePoints,
    )
    if not result_isOkCheck(realizedRouteResult):
        return resultErr_build()
    occupiedCells |= {
        (cell.worldRow, cell.worldCol) for cell in realizedRouteResult.value.cells
    }
    return resultOk_build(routeResult.value)


def _destinationPortIndexResult_build(
    circuitDocument: CircuitDocument,
    callRouteObligation: CallRouteObligation,
) -> Result[int]:
    """Build the destination input-port index for one seam-crossing call."""

    destinationChipResult = circuitDocument.circuitChipSet.chipResult_get(
        callRouteObligation.destinationChipRef.chipId
    )
    if not result_isOkCheck(destinationChipResult):
        return resultErr_build()

    inputPortDeclarations = (
        destinationChipResult.value.inputPortDeclarationSet.portDeclarations
    )
    if not inputPortDeclarations:
        return resultOk_build(0)

    if callRouteObligation.sourcePortDeclaration is not None:
        portIndex: int
        for portIndex, portDeclaration in enumerate(inputPortDeclarations):
            if portDeclaration == callRouteObligation.sourcePortDeclaration:
                return resultOk_build(portIndex)

    if len(inputPortDeclarations) == 1:
        return resultOk_build(0)

    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.interconnect_solver.ambiguous_destination_port",
        message=(
            "Seam-crossing calls into a multi-input destination must resolve to "
            "one explicit destination input port"
        ),
        context=(
            callRouteObligation.sourceChipRef.chipId.moduleName,
            callRouteObligation.sourceChipRef.chipId.functionName,
            callRouteObligation.destinationChipRef.chipId.moduleName,
            callRouteObligation.destinationChipRef.chipId.functionName,
        ),
    )
    return resultErr_build()


def _seamDemandSortKey_build(
    preparedDemand: _PreparedSeamDemand,
) -> tuple[int, int, int, str, str, int]:
    """Build deterministic lane-order key within one interconnect."""

    sourceChipId = preparedDemand.callRouteObligation.sourceChipRef.chipId
    return (
        preparedDemand.sourcePlacement.orderIndex,
        preparedDemand.destinationPlacement.orderIndex,
        preparedDemand.destinationPortIndex,
        sourceChipId.moduleName,
        sourceChipId.functionName,
        preparedDemand.callRouteObligation.childCallIndex,
    )


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


def _interRoutingTravelRegionResult_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> Result[RoutingZoneRegion]:
    """Build the seam-travel region matching one chip placement side."""

    routingZoneRegionSide = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    if routingZoneRegionSide is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.interconnect_solver.placement.missing_terminal_side",
            message="ChipPlacement terminal side is required for seam solving",
        )
        return resultErr_build()
    travelRegionKind = (
        RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE
        if routingZone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST
        else RoutingZoneRegionKind.INTER_ROUTING_LATITUDE
    )
    return routingZone.routingZoneRegionSet.regionForKindAndSideResult_get(
        travelRegionKind,
        routingZoneRegionSide,
    )


def _seamGeometryResult_build(
    interconnect: RoutingZoneInterconnect,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceInterFanRegion: RoutingZoneRegion,
    destinationInterFanRegion: RoutingZoneRegion,
    sourceInterTravelRegion: RoutingZoneRegion,
    destinationInterTravelRegion: RoutingZoneRegion,
    srcChipLines: tuple[str, ...],
    dstChipLines: tuple[str, ...],
    sourcePortIndex: int,
    destinationPortIndex: int,
    sourceSparseWallRows: tuple[int, int] | None,
    destinationSparseWallRows: tuple[int, int] | None,
    seamPairIndex: int,
    seamPairCount: int,
    sourceBundleIndex: int,
    sourceBundleCount: int,
    destinationBundleIndex: int,
    destinationBundleCount: int,
    isReturn: bool,
    occupiedCells: set[tuple[int, int]],
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
            sourceInterTravelRegion=sourceInterTravelRegion,
            destinationInterTravelRegion=destinationInterTravelRegion,
            srcChipHeight=len(srcChipLines),
            dstChipHeight=len(dstChipLines),
            sourcePortIndex=sourcePortIndex,
            destinationPortIndex=destinationPortIndex,
            sourceSparseWallRows=sourceSparseWallRows,
            destinationSparseWallRows=destinationSparseWallRows,
            seamPairIndex=seamPairIndex,
            seamPairCount=seamPairCount,
            sourceBundleIndex=sourceBundleIndex,
            sourceBundleCount=sourceBundleCount,
            destinationBundleIndex=destinationBundleIndex,
            destinationBundleCount=destinationBundleCount,
            isReturn=isReturn,
            occupiedCells=occupiedCells,
        )
    return _verticalSeamGeometryResult_build(
        interconnect=interconnect,
        sourcePlacement=sourcePlacement,
        destinationPlacement=destinationPlacement,
        sourceInterFanRegion=sourceInterFanRegion,
        destinationInterFanRegion=destinationInterFanRegion,
        sourceInterTravelRegion=sourceInterTravelRegion,
        destinationInterTravelRegion=destinationInterTravelRegion,
        srcChipWidth=max((len(line) for line in srcChipLines), default=1),
        dstChipWidth=max((len(line) for line in dstChipLines), default=1),
        sourcePortIndex=sourcePortIndex,
        destinationPortIndex=destinationPortIndex,
        seamPairIndex=seamPairIndex,
        isReturn=isReturn,
    )


def _horizontalSeamGeometryResult_build(
    interconnect: RoutingZoneInterconnect,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceInterFanRegion: RoutingZoneRegion,
    destinationInterFanRegion: RoutingZoneRegion,
    sourceInterTravelRegion: RoutingZoneRegion,
    destinationInterTravelRegion: RoutingZoneRegion,
    srcChipHeight: int,
    dstChipHeight: int,
    sourcePortIndex: int,
    destinationPortIndex: int,
    sourceSparseWallRows: tuple[int, int] | None,
    destinationSparseWallRows: tuple[int, int] | None,
    seamPairIndex: int,
    seamPairCount: int,
    sourceBundleIndex: int,
    sourceBundleCount: int,
    destinationBundleIndex: int,
    destinationBundleCount: int,
    isReturn: bool,
    occupiedCells: set[tuple[int, int]],
) -> Result[
    tuple[
        RoutingZoneInterconnectRouteSolveKind,
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
    ]
]:
    """Build explicit horizontal seam geometry."""

    # Each chip slot = chipHeight + 2 rows. The seam port row is at:
    # slotStart + 1 (corridor above) + _HEADER + 2*k (signal) / 2*k+1 (return),
    # while seam columns are allocated per directed wire.
    _HEADER: int = 3
    _RET_OFFSET: int = 1
    # Keep the seam bundle contiguous by direction: all forwards first,
    # followed by all returns. Interleaving signal/return rows forces the
    # sparse fan to self-cross before it reaches the centered vane family.
    laneIndex: int = (
        seamPairCount + seamPairIndex if isReturn else seamPairIndex
    )
    srcSignalRow: int = (
        sourceInterFanRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipHeight + 2)
        + 1 + _HEADER + 2 * sourcePortIndex
    )
    dstSignalRow: int = (
        destinationInterFanRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipHeight + 2)
        + 1 + _HEADER + 2 * destinationPortIndex
    )

    def _signalVaneOuterRow_build(
        wallRow: int,
        *,
        bundleIndex: int,
        bundleCount: int,
    ) -> int:
        return wallRow - bundleCount + bundleIndex

    def _signalSparseOuterRow_build(
        wallRow: int,
        *,
        bundleIndex: int,
        bundleCount: int,
    ) -> int:
        return wallRow - (bundleCount - 1) + 2 * bundleIndex

    def _returnVaneOuterRow_build(
        wallRow: int,
        *,
        bundleIndex: int,
    ) -> int:
        return wallRow + 1 + bundleIndex

    def _returnSparseOuterRow_build(
        wallRow: int,
        *,
        bundleIndex: int,
        bundleCount: int,
    ) -> int:
        return wallRow - bundleCount + 1 + 2 * bundleIndex

    startFanRegion = sourceInterFanRegion
    endFanRegion = destinationInterFanRegion
    if isReturn:
        startOuterRow = srcSignalRow + _RET_OFFSET
        endOuterRow = dstSignalRow + _RET_OFFSET
        startWallRow = (
            sourceSparseWallRows[1]
            if sourceSparseWallRows is not None
            else startOuterRow
        )
        endWallRow = (
            destinationSparseWallRows[1]
            if destinationSparseWallRows is not None
            else endOuterRow
        )
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM_RETURN
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM_RETURN
    else:
        startOuterRow = srcSignalRow
        endOuterRow = dstSignalRow
        startWallRow = (
            sourceSparseWallRows[0]
            if sourceSparseWallRows is not None
            else startOuterRow
        )
        endWallRow = (
            destinationSparseWallRows[0]
            if destinationSparseWallRows is not None
            else endOuterRow
        )
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM

    hasSparseSourceBundle: bool = sourceBundleCount > 1
    hasSparseDestinationBundle: bool = destinationBundleCount > 1

    # On a sparse wall, the seam must arrive/depart on the dedicated vane rows
    # themselves. Approaching on generic interconnect rows forces an extra row
    # change inside the fan zone and creates self-crossings.
    if (not isReturn) and sourceSparseWallRows is not None and hasSparseSourceBundle:
        startOuterRow = _signalSparseOuterRow_build(
            startWallRow,
            bundleIndex=sourceBundleIndex,
            bundleCount=sourceBundleCount,
        )
    if (
        (not isReturn)
        and destinationSparseWallRows is not None
        and hasSparseDestinationBundle
    ):
        endOuterRow = _signalSparseOuterRow_build(
            endWallRow,
            bundleIndex=destinationBundleIndex,
            bundleCount=destinationBundleCount,
        )
    if isReturn and destinationSparseWallRows is not None and hasSparseDestinationBundle:
        startOuterRow = _returnSparseOuterRow_build(
            startWallRow,
            bundleIndex=destinationBundleIndex,
            bundleCount=destinationBundleCount,
        )
    if isReturn and sourceSparseWallRows is not None and hasSparseSourceBundle:
        endOuterRow = _returnSparseOuterRow_build(
            endWallRow,
            bundleIndex=sourceBundleIndex,
            bundleCount=sourceBundleCount,
        )

    srcFanStart: int = sourceInterFanRegion.routingZoneRegionFrame.horizontalStart
    dstFanStart: int = destinationInterFanRegion.routingZoneRegionFrame.horizontalStart
    srcTravelStart: int = sourceInterTravelRegion.routingZoneRegionFrame.horizontalStart
    dstTravelStart: int = (
        destinationInterTravelRegion.routingZoneRegionFrame.horizontalStart
    )
    srcTravelCol: int = srcTravelStart + laneIndex
    dstTravelCol: int = dstTravelStart + laneIndex
    seamCol: int = interconnect.routingZoneInterconnectFrame.horizontalStart + laneIndex
    srcLaneCol: int = srcFanStart + 2 + laneIndex
    dstLaneCol: int = dstFanStart + laneIndex

    routePointsMutable: list[RoutingZoneRoutePoint] = []
    def _appendPoint(horizontalIndex: int, verticalIndex: int) -> Result[None]:
        pointResult = routingZoneRoutePointResult_build(
            horizontalIndex=horizontalIndex,
            verticalIndex=verticalIndex,
        )
        if not result_isOkCheck(pointResult):
            return resultErr_build()
        if routePointsMutable and routePointsMutable[-1] == pointResult.value:
            return resultOk_build(None)
        routePointsMutable.append(pointResult.value)
        return resultOk_build(None)

    def _appendHorizontalStartFan(
        fanRegion: RoutingZoneRegion,
        laneCol: int,
        travelCol: int,
        wallRow: int,
        outerRow: int,
    ) -> Result[None]:
        fanStart: int = fanRegion.routingZoneRegionFrame.horizontalStart
        fanEnd: int = fanRegion.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        if fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west":
            for col, row in (
                (fanEnd, wallRow),
                (fanEnd - 1, wallRow),
                (fanEnd - 1, outerRow),
                (laneCol, outerRow),
                (travelCol, outerRow),
            ):
                appendResult = _appendPoint(col, row)
                if not result_isOkCheck(appendResult):
                    return resultErr_build()
            return resultOk_build(None)
        for col, row in (
            (fanStart, wallRow),
            (fanStart + 1, wallRow),
            (fanStart + 1, outerRow),
            (laneCol, outerRow),
            (travelCol, outerRow),
        ):
            appendResult = _appendPoint(col, row)
            if not result_isOkCheck(appendResult):
                return resultErr_build()
        return resultOk_build(None)

    def _appendHorizontalSparseStartFan(
        fanRegion: RoutingZoneRegion,
        travelCol: int,
        outerRow: int,
        vaneRow: int,
        peelCol: int,
    ) -> Result[None]:
        if fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west":
            for col, row in (
                (peelCol, vaneRow),
                (peelCol, outerRow),
                (travelCol, outerRow),
            ):
                appendResult = _appendPoint(col, row)
                if not result_isOkCheck(appendResult):
                    return resultErr_build()
            return resultOk_build(None)
        for col, row in (
            (peelCol, vaneRow),
            (peelCol, outerRow),
            (travelCol, outerRow),
        ):
            appendResult = _appendPoint(col, row)
            if not result_isOkCheck(appendResult):
                return resultErr_build()
        return resultOk_build(None)

    def _appendHorizontalBundleStartFan(
        fanRegion: RoutingZoneRegion,
        laneCol: int,
        travelCol: int,
        wallRow: int,
        outerRow: int,
    ) -> Result[None]:
        wallCol: int = (
            fanRegion.routingZoneRegionFrame.horizontalEnd_calculate() - 1
            if fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west"
            else fanRegion.routingZoneRegionFrame.horizontalStart
        )
        for col, row in (
            (wallCol, wallRow),
            (laneCol, wallRow),
            (laneCol, outerRow),
            (travelCol, outerRow),
        ):
            appendResult = _appendPoint(col, row)
            if not result_isOkCheck(appendResult):
                return resultErr_build()
        return resultOk_build(None)

    def _appendHorizontalBundleFanPath(
        fanRegion: RoutingZoneRegion,
        *,
        startCol: int,
        startRow: int,
        endCol: int,
        endRow: int,
        extraCol: int,
    ) -> Result[None]:
        minCol = min(startCol, endCol, extraCol)
        maxCol = max(startCol, endCol, extraCol)
        minRow = fanRegion.routingZoneRegionFrame.verticalStart
        maxRow = fanRegion.routingZoneRegionFrame.verticalEnd_calculate() - 1

        start = (startCol, startRow)
        end = (endCol, endRow)
        queue: deque[tuple[int, int]] = deque([start])
        prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

        def _neighborOrder(col: int, row: int) -> tuple[tuple[int, int], ...]:
            horizontalStep = 1 if endCol > col else -1
            verticalStep = 1 if endRow > row else -1
            return (
                (col, row + verticalStep),
                (col + horizontalStep, row),
                (col - horizontalStep, row),
                (col, row - verticalStep),
            )

        while queue:
            col, row = queue.popleft()
            if (col, row) == end:
                break
            nextCol: int
            nextRow: int
            for nextCol, nextRow in _neighborOrder(col, row):
                if nextCol < minCol or nextCol > maxCol:
                    continue
                if nextRow < minRow or nextRow > maxRow:
                    continue
                nextKey = (nextCol, nextRow)
                if nextKey in prev:
                    continue
                worldKey = (nextRow, nextCol)
                if nextKey not in {start, end} and worldKey in occupiedCells:
                    continue
                prev[nextKey] = (col, row)
                queue.append(nextKey)

        if end not in prev:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.interconnect_solver.bundle_fan.no_path",
                message="Non-sparse fan manifold could not realize a collision-free path",
            )
            return resultErr_build()

        path: list[tuple[int, int]] = []
        cursor: tuple[int, int] | None = end
        while cursor is not None:
            path.append(cursor)
            cursor = prev[cursor]
        path.reverse()

        pointColsRows: list[tuple[int, int]] = [path[0]]
        if len(path) > 1:
            prevDelta = (
                path[1][0] - path[0][0],
                path[1][1] - path[0][1],
            )
            index: int
            for index in range(1, len(path) - 1):
                nextDelta = (
                    path[index + 1][0] - path[index][0],
                    path[index + 1][1] - path[index][1],
                )
                if nextDelta != prevDelta:
                    pointColsRows.append(path[index])
                prevDelta = nextDelta
            pointColsRows.append(path[-1])

        col: int
        row: int
        for col, row in pointColsRows:
            appendResult = _appendPoint(col, row)
            if not result_isOkCheck(appendResult):
                return resultErr_build()
        return resultOk_build(None)

    def _appendHorizontalEndFan(
        fanRegion: RoutingZoneRegion,
        travelCol: int,
        laneCol: int,
        outerRow: int,
        wallRow: int,
    ) -> Result[None]:
        fanStart: int = fanRegion.routingZoneRegionFrame.horizontalStart
        fanEnd: int = fanRegion.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        if fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west":
            for col, row in (
                (travelCol, outerRow),
                (laneCol, outerRow),
                (fanEnd - 1, outerRow),
                (fanEnd - 1, wallRow),
                (fanEnd, wallRow),
            ):
                appendResult = _appendPoint(col, row)
                if not result_isOkCheck(appendResult):
                    return resultErr_build()
            return resultOk_build(None)
        for col, row in (
            (travelCol, outerRow),
            (laneCol, outerRow),
            (fanStart + 1, outerRow),
            (fanStart + 1, wallRow),
            (fanStart, wallRow),
        ):
            appendResult = _appendPoint(col, row)
            if not result_isOkCheck(appendResult):
                return resultErr_build()
        return resultOk_build(None)

    def _appendHorizontalSparseEndFan(
        fanRegion: RoutingZoneRegion,
        travelCol: int,
        outerRow: int,
        vaneRow: int,
        peelCol: int,
    ) -> Result[None]:
        if fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west":
            for col, row in (
                (travelCol, outerRow),
                (peelCol, outerRow),
                (peelCol, vaneRow),
            ):
                appendResult = _appendPoint(col, row)
                if not result_isOkCheck(appendResult):
                    return resultErr_build()
            return resultOk_build(None)
        for col, row in (
            (travelCol, outerRow),
            (peelCol, outerRow),
            (peelCol, vaneRow),
        ):
            appendResult = _appendPoint(col, row)
            if not result_isOkCheck(appendResult):
                return resultErr_build()
        return resultOk_build(None)

    def _appendHorizontalBundleEndFan(
        fanRegion: RoutingZoneRegion,
        travelCol: int,
        laneCol: int,
        outerRow: int,
        wallRow: int,
    ) -> Result[None]:
        wallCol: int = (
            fanRegion.routingZoneRegionFrame.horizontalEnd_calculate() - 1
            if fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west"
            else fanRegion.routingZoneRegionFrame.horizontalStart
        )
        for col, row in (
            (travelCol, outerRow),
            (laneCol, outerRow),
            (laneCol, wallRow),
            (wallCol, wallRow),
        ):
            appendResult = _appendPoint(col, row)
            if not result_isOkCheck(appendResult):
                return resultErr_build()
        return resultOk_build(None)

    def _horizontalBundlePeelCol_build(
        fanRegion: RoutingZoneRegion,
        *,
        seamPairIndex: int,
        seamPairCount: int,
        isReturn: bool,
    ) -> int:
        fanStart: int = fanRegion.routingZoneRegionFrame.horizontalStart
        fanEnd: int = fanRegion.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        isWest: bool = (
            fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west"
        )
        if isWest:
            if isReturn:
                return fanEnd - seamPairCount + 1 + seamPairIndex
            return fanStart + 1 + seamPairIndex
        if isReturn:
            return fanStart + 1 + seamPairIndex
        return fanEnd - seamPairCount + 1 + seamPairIndex

    def _horizontalSparsePeelCol_build(
        fanRegion: RoutingZoneRegion,
        *,
        seamPairIndex: int,
        seamPairCount: int,
        isReturn: bool,
    ) -> int:
        fanStart: int = fanRegion.routingZoneRegionFrame.horizontalStart
        fanEnd: int = fanRegion.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        isWest: bool = (
            fanRegion.routingZoneRegionId.routingZoneRegionSide.value == "west"
        )
        if isWest:
            if isReturn:
                return fanEnd - (seamPairCount - 1 - seamPairIndex)
            return fanStart + seamPairIndex
        if isReturn:
            return fanStart + seamPairIndex
        return fanEnd - (seamPairCount - 1 - seamPairIndex)

    # If exactly one side is sparse, the seam row must remain the non-sparse
    # ribbon row all the way across the travel+seam corridor. The fan region,
    # not the seam, owns the row change into the sparse vane family.
    sparseOnExactlyOneSide: bool = hasSparseSourceBundle ^ hasSparseDestinationBundle
    if sparseOnExactlyOneSide:
        sourceVaneRow: int | None = None
        destinationVaneRow: int | None = None
        if hasSparseSourceBundle:
            sourceVaneRow = (
                _returnVaneOuterRow_build(
                    startWallRow,
                    bundleIndex=sourceBundleIndex,
                )
                if isReturn
                else _signalVaneOuterRow_build(
                    startWallRow,
                    bundleIndex=sourceBundleIndex,
                    bundleCount=sourceBundleCount,
                )
            )
        if hasSparseDestinationBundle:
            destinationVaneRow = (
                _returnVaneOuterRow_build(
                    endWallRow,
                    bundleIndex=destinationBundleIndex,
                )
                if isReturn
                else _signalVaneOuterRow_build(
                    endWallRow,
                    bundleIndex=destinationBundleIndex,
                    bundleCount=destinationBundleCount,
                )
            )
        seamForwardBase: int = (
            interconnect.routingZoneInterconnectFrame.verticalStart + 9
        )
        seamReturnBase: int = seamForwardBase + 2 * seamPairCount + 1
        seamRow: int = (
            seamReturnBase + 2 * seamPairIndex
            if isReturn
            else seamForwardBase + 2 * seamPairIndex
        )

        if hasSparseSourceBundle:
            startFanResult = _appendHorizontalSparseStartFan(
                fanRegion=sourceInterFanRegion,
                travelCol=srcTravelCol,
                outerRow=seamRow,
                vaneRow=sourceVaneRow,
                peelCol=_horizontalSparsePeelCol_build(
                    sourceInterFanRegion,
                    seamPairIndex=sourceBundleIndex,
                    seamPairCount=sourceBundleCount,
                    isReturn=isReturn,
                ),
            )
        else:
            startFanResult = _appendHorizontalBundleFanPath(
                fanRegion=sourceInterFanRegion,
                startCol=(
                    sourceInterFanRegion.routingZoneRegionFrame.horizontalEnd_calculate()
                    - 1
                    if sourceInterFanRegion.routingZoneRegionId.routingZoneRegionSide.value
                    == "west"
                    else sourceInterFanRegion.routingZoneRegionFrame.horizontalStart
                ),
                startRow=startWallRow,
                endCol=srcTravelCol,
                endRow=seamRow,
                extraCol=seamCol,
            )
        if not result_isOkCheck(startFanResult):
            return resultErr_build()

        seamPointResult = _appendPoint(seamCol, seamRow)
        if not result_isOkCheck(seamPointResult):
            return resultErr_build()

        if hasSparseDestinationBundle:
            endFanResult = _appendHorizontalSparseEndFan(
                fanRegion=destinationInterFanRegion,
                travelCol=dstTravelCol,
                outerRow=seamRow,
                vaneRow=destinationVaneRow,
                peelCol=_horizontalSparsePeelCol_build(
                    destinationInterFanRegion,
                    seamPairIndex=destinationBundleIndex,
                    seamPairCount=destinationBundleCount,
                    isReturn=isReturn,
                ),
            )
        else:
            endFanResult = _appendHorizontalBundleFanPath(
                fanRegion=destinationInterFanRegion,
                startCol=dstTravelCol,
                startRow=seamRow,
                endCol=(
                    destinationInterFanRegion.routingZoneRegionFrame.horizontalEnd_calculate()
                    - 1
                    if destinationInterFanRegion.routingZoneRegionId.routingZoneRegionSide.value
                    == "west"
                    else destinationInterFanRegion.routingZoneRegionFrame.horizontalStart
                ),
                endRow=endWallRow,
                extraCol=seamCol,
            )
        if not result_isOkCheck(endFanResult):
            return resultErr_build()

        return resultOk_build(
            (
                straightKind,
                tuple(routePointsMutable),
                (
                    startFanRegion.routingZoneRegionId,
                    sourceInterTravelRegion.routingZoneRegionId,
                    destinationInterTravelRegion.routingZoneRegionId,
                    endFanRegion.routingZoneRegionId,
                ),
            )
        )

    startFanResult: Result[None]
    if isReturn and sourceSparseWallRows is not None and hasSparseSourceBundle:
        startFanResult = _appendHorizontalSparseStartFan(
            fanRegion=sourceInterFanRegion,
            travelCol=srcTravelCol,
            outerRow=startOuterRow,
            vaneRow=_returnVaneOuterRow_build(
                startWallRow,
                bundleIndex=sourceBundleIndex,
            ),
            peelCol=_horizontalSparsePeelCol_build(
                sourceInterFanRegion,
                seamPairIndex=sourceBundleIndex,
                seamPairCount=sourceBundleCount,
                isReturn=True,
            ),
        )
    elif (
        (not isReturn)
        and sourceSparseWallRows is not None
        and hasSparseSourceBundle
    ):
        startFanResult = _appendHorizontalSparseStartFan(
            fanRegion=sourceInterFanRegion,
            travelCol=srcTravelCol,
            outerRow=startOuterRow,
            vaneRow=_signalVaneOuterRow_build(
                startWallRow,
                bundleIndex=sourceBundleIndex,
                bundleCount=sourceBundleCount,
            ),
            peelCol=_horizontalSparsePeelCol_build(
                sourceInterFanRegion,
                seamPairIndex=sourceBundleIndex,
                seamPairCount=sourceBundleCount,
                isReturn=False,
            ),
        )
    elif isReturn:
        startFanResult = _appendHorizontalStartFan(
            fanRegion=sourceInterFanRegion,
            laneCol=srcLaneCol,
            travelCol=srcTravelCol,
            wallRow=startWallRow,
            outerRow=startOuterRow,
        )
    else:
        startFanResult = _appendHorizontalStartFan(
            fanRegion=sourceInterFanRegion,
            laneCol=srcLaneCol,
            travelCol=srcTravelCol,
            wallRow=startWallRow,
            outerRow=startOuterRow,
        )
    if not result_isOkCheck(startFanResult):
        return resultErr_build()

    seamStartResult = _appendPoint(seamCol, startOuterRow)
    if not result_isOkCheck(seamStartResult):
        return resultErr_build()
    if startOuterRow != endOuterRow:
        seamEndResult = _appendPoint(seamCol, endOuterRow)
        if not result_isOkCheck(seamEndResult):
            return resultErr_build()

    endFanResult: Result[None]
    if isReturn and destinationSparseWallRows is not None and hasSparseDestinationBundle:
        endFanResult = _appendHorizontalSparseEndFan(
            fanRegion=destinationInterFanRegion,
            travelCol=dstTravelCol,
            outerRow=endOuterRow,
            vaneRow=_returnVaneOuterRow_build(
                endWallRow,
                bundleIndex=destinationBundleIndex,
            ),
            peelCol=_horizontalSparsePeelCol_build(
                destinationInterFanRegion,
                seamPairIndex=destinationBundleIndex,
                seamPairCount=destinationBundleCount,
                isReturn=True,
            ),
        )
    elif (
        (not isReturn)
        and destinationSparseWallRows is not None
        and hasSparseDestinationBundle
    ):
        endFanResult = _appendHorizontalSparseEndFan(
            fanRegion=destinationInterFanRegion,
            travelCol=dstTravelCol,
            outerRow=endOuterRow,
            vaneRow=_signalVaneOuterRow_build(
                endWallRow,
                bundleIndex=destinationBundleIndex,
                bundleCount=destinationBundleCount,
            ),
            peelCol=_horizontalSparsePeelCol_build(
                destinationInterFanRegion,
                seamPairIndex=destinationBundleIndex,
                seamPairCount=destinationBundleCount,
                isReturn=False,
            ),
        )
    elif isReturn:
        endFanResult = _appendHorizontalEndFan(
            fanRegion=destinationInterFanRegion,
            travelCol=dstTravelCol,
            laneCol=dstLaneCol,
            outerRow=endOuterRow,
            wallRow=endWallRow,
        )
    else:
        endFanResult = _appendHorizontalEndFan(
            fanRegion=destinationInterFanRegion,
            travelCol=dstTravelCol,
            laneCol=dstLaneCol,
            outerRow=endOuterRow,
            wallRow=endWallRow,
        )
    if not result_isOkCheck(endFanResult):
        return resultErr_build()

    solveKind = straightKind if startOuterRow == endOuterRow else offsetKind
    return resultOk_build(
        (
            solveKind,
            tuple(routePointsMutable),
            (
                startFanRegion.routingZoneRegionId,
                sourceInterTravelRegion.routingZoneRegionId,
                destinationInterTravelRegion.routingZoneRegionId,
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
    sourceInterTravelRegion: RoutingZoneRegion,
    destinationInterTravelRegion: RoutingZoneRegion,
    srcChipWidth: int,
    dstChipWidth: int,
    sourcePortIndex: int,
    destinationPortIndex: int,
    seamPairIndex: int,
    isReturn: bool,
) -> Result[
    tuple[
        RoutingZoneInterconnectRouteSolveKind,
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
    ]
]:
    """Build explicit vertical seam geometry."""

    # Each chip slot = chipWidth + 2 cols. The seam port column is at:
    # slotStart + 1 (corridor left) + _HEADER + 2*k (signal) / 2*k+1 (return),
    # while seam rows are allocated per directed wire.
    _HEADER: int = 3
    _RET_OFFSET: int = 1
    laneIndex: int = 2 * seamPairIndex + (1 if isReturn else 0)
    srcSignalCol: int = (
        sourceInterFanRegion.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex * (srcChipWidth + 2)
        + 1 + _HEADER + 2 * sourcePortIndex
    )
    dstSignalCol: int = (
        destinationInterFanRegion.routingZoneRegionFrame.horizontalStart
        + destinationPlacement.orderIndex * (dstChipWidth + 2)
        + 1 + _HEADER + 2 * destinationPortIndex
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

    srcFanStart: int = sourceInterFanRegion.routingZoneRegionFrame.verticalStart
    dstFanStart: int = destinationInterFanRegion.routingZoneRegionFrame.verticalStart
    dstFanEnd: int = (
        destinationInterFanRegion.routingZoneRegionFrame.verticalEnd_calculate()
    )
    srcTravelStart: int = sourceInterTravelRegion.routingZoneRegionFrame.verticalStart
    dstTravelStart: int = (
        destinationInterTravelRegion.routingZoneRegionFrame.verticalStart
    )
    seamRow: int = interconnect.routingZoneInterconnectFrame.verticalStart + laneIndex
    srcTravelRow: int = srcTravelStart + laneIndex
    dstTravelRow: int = dstTravelStart + laneIndex
    srcLaneRow: int = srcFanStart + 2 + laneIndex
    dstLaneRow: int = dstFanStart + laneIndex

    if isReturn:
        routeRowSeq: list[int] = [
            dstFanEnd - 1,
            dstFanEnd - 2,
            dstLaneRow,
            dstTravelRow,
            seamRow,
        ]
        endLaneRows: list[int] = [
            srcTravelRow,
            srcLaneRow,
            srcFanStart + 1,
            srcFanStart,
        ]
    else:
        routeRowSeq = [
            srcFanStart,
            srcFanStart + 1,
            srcLaneRow,
            srcTravelRow,
            seamRow,
        ]
        endLaneRows = [
            dstTravelRow,
            dstLaneRow,
            dstFanEnd - 2,
            dstFanEnd - 1,
        ]

    routePointsMutable: list[RoutingZoneRoutePoint] = []
    for row in routeRowSeq:
        ptResult = routingZoneRoutePointResult_build(
            horizontalIndex=startCol,
            verticalIndex=row,
        )
        if not result_isOkCheck(ptResult):
            return resultErr_build()
        routePointsMutable.append(ptResult.value)

    if startCol != endCol:
        seamTurnPointResult = routingZoneRoutePointResult_build(
            horizontalIndex=endCol,
            verticalIndex=seamRow,
        )
        if not result_isOkCheck(seamTurnPointResult):
            return resultErr_build()
        routePointsMutable.append(seamTurnPointResult.value)

    for row in endLaneRows:
        ptResult = routingZoneRoutePointResult_build(
            horizontalIndex=endCol,
            verticalIndex=row,
        )
        if not result_isOkCheck(ptResult):
            return resultErr_build()
        routePointsMutable.append(ptResult.value)

    solveKind = straightKind if startCol == endCol else offsetKind
    return resultOk_build(
        (
            solveKind,
            tuple(routePointsMutable),
            (
                startFanRegion.routingZoneRegionId,
                sourceInterTravelRegion.routingZoneRegionId
                if not isReturn
                else destinationInterTravelRegion.routingZoneRegionId,
                destinationInterTravelRegion.routingZoneRegionId
                if not isReturn
                else sourceInterTravelRegion.routingZoneRegionId,
                endFanRegion.routingZoneRegionId,
            ),
        )
    )
