"""Interconnect seam routing solver for the new SignalFlow engine.

This module realizes `SEAM_CROSSING` call obligations against one placed
`RoutingZoneInterconnect` plus the neighboring inter-routing fan-in/out
regions. It produces explicit planning-grid seam geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    RoutingZoneInterconnect,
    RoutingZoneInterconnectAxis,
    RoutingZoneInterconnectRouteSolveKind,
    RoutingZoneInterconnectSolvedRoute,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneRegion,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRoutePoint,
    RoutingZoneSense,
    chipDrawGeometry_build,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneInterconnectSolvedRouteResult_build,
    routingZoneInterconnectSolvedRouteSetResult_build,
    routingZoneRegionForKindAndSideResult_get,
    routingZoneRoutePointResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


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
    srcChipLines: tuple[str, ...]
    dstChipLines: tuple[str, ...]
    destinationPortIndex: int
    sourceSignalLineOffset: int
    destinationSignalLineOffset: int
    sourceReturnLineOffset: int | None
    destinationReturnLineOffset: int | None


def interconnectSolvedRoutesResult_build(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneInterconnectSolvedRouteSet]:
    """Build solved seam routes from placed interconnect geometry."""

    routeSetResultBuild = routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations  # noqa: E501 - RPN compatibility name exceeds line limit
    return routeSetResultBuild(
        circuitDocument,
        placedRoutingZoneGrid,
        callRouteObligationSet,
    )


def routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations(  # noqa: E501 - RPN compatibility name exceeds line limit
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneInterconnectSolvedRouteSet]:
    """Build solved seam routes from placed geometry and seam obligations."""

    solvedRoutesMutable: list[RoutingZoneInterconnectSolvedRoute] = []
    seamDemandsByInterconnectMutable: dict[
        object, list[_PreparedSeamDemand]
    ] = {}
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
        seamPairIndex: int
        preparedDemand: _PreparedSeamDemand
        for seamPairIndex, preparedDemand in enumerate(
            sorted(seamDemands, key=_seamDemandSortKey_build)
        ):
            routePairResultBuild = _routingZoneInterconnectSolvedRoutePairResult_buildFromPreparedDemand  # noqa: E501 - RPN helper name exceeds line limit
            routePairResult = routePairResultBuild(
                preparedDemand=preparedDemand,
                seamPairIndex=seamPairIndex,
            )
            if not result_isOkCheck(routePairResult):
                return resultErr_build()
            solvedRoutesMutable.extend(routePairResult.value)

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

    interconnectSet = placedRoutingZoneGrid.routingZoneInterconnectSet
    interconnectResult = interconnectSet.interconnectBetweenZonesResult_get(
        sourceZoneResult.value.routingZoneId,
        destinationZoneResult.value.routingZoneId,
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

    sourceDrawGeometry = chipDrawGeometry_build(sourceChipResult.value)
    destinationDrawGeometry = chipDrawGeometry_build(
        destinationChipResult.value
    )
    sourceSignalLineOffset = _terminalLineOffset_get(
        sourceDrawGeometry.eastTerminalLineOffsets,
        callRouteObligation.sourcePortDeclaration.signalName
        if callRouteObligation.sourcePortDeclaration is not None
        else None,
        fallback=3 + callRouteObligation.childCallIndex,
    )
    sourceReturnLineOffset = _terminalLineOffsetOrNone_get(
        sourceDrawGeometry.eastTerminalLineOffsets,
        callRouteObligation.sourcePortDeclaration.returnName
        if callRouteObligation.sourcePortDeclaration is not None
        else None,
    )
    destinationPortDeclaration = (
        destinationChipResult.value.inputPortDeclarationSet.portDeclarations[
            destinationPortIndexResult.value
        ]
        if destinationPortIndexResult.value
        < len(
            destinationChipResult.value.inputPortDeclarationSet.portDeclarations
        )
        else None
    )
    destinationSignalLineOffset = _terminalLineOffset_get(
        destinationDrawGeometry.westTerminalLineOffsets,
        destinationPortDeclaration.signalName
        if destinationPortDeclaration is not None
        else None,
        fallback=3 + destinationPortIndexResult.value,
    )
    destinationReturnLineOffset = _terminalLineOffsetOrNone_get(
        destinationDrawGeometry.westTerminalLineOffsets,
        destinationPortDeclaration.returnName
        if destinationPortDeclaration is not None
        else None,
    )

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
            srcChipLines=chipDrawLines_build(sourceChipResult.value),
            dstChipLines=chipDrawLines_build(destinationChipResult.value),
            destinationPortIndex=destinationPortIndexResult.value,
            sourceSignalLineOffset=sourceSignalLineOffset,
            destinationSignalLineOffset=destinationSignalLineOffset,
            sourceReturnLineOffset=sourceReturnLineOffset,
            destinationReturnLineOffset=destinationReturnLineOffset,
        )
    )


def _terminalLineOffset_get(
    terminalLineOffsets: tuple[tuple[str, int], ...],
    terminalName: str | None,
    fallback: int,
) -> int:
    """Return a semantic terminal line offset, falling back if unresolved."""

    if terminalName is None:
        return fallback
    terminalLineOffset: tuple[str, int]
    for terminalLineOffset in terminalLineOffsets:
        if terminalLineOffset[0] == terminalName:
            return terminalLineOffset[1]
    return fallback


def _terminalLineOffsetOrNone_get(
    terminalLineOffsets: tuple[tuple[str, int], ...],
    terminalName: str | None,
) -> int | None:
    """Return a semantic terminal line offset when the terminal exists."""

    if terminalName is None:
        return None
    terminalLineOffset: tuple[str, int]
    for terminalLineOffset in terminalLineOffsets:
        if terminalLineOffset[0] == terminalName:
            return terminalLineOffset[1]
    return None


def _zoneOwningChipResult_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    chipRef: ChipRef,
) -> Result[RoutingZone]:
    """Build the placed routing zone that owns one chip."""

    routingZone: RoutingZone
    for routingZone in placedRoutingZoneGrid.routingZoneSet.routingZones:
        placement = routingZone.chipPlacementSet.placementForChipOrNone_get(
            chipRef
        )
        if placement is not None:
            return resultOk_build(routingZone)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.interconnect_solver.missing_chip_zone",
        message="Placed RoutingZoneGrid does not contain the requested chip",
    )
    return resultErr_build()


def _routingZoneInterconnectSolvedRoutePairResult_buildFromPreparedDemand(
    preparedDemand: _PreparedSeamDemand,
    seamPairIndex: int,
) -> Result[
    tuple[RoutingZoneInterconnectSolvedRoute, ...]
]:
    """Build solved seam route(s) for one prepared seam demand."""

    fwdGeometryResult = _seamGeometryResult_build(
        interconnect=preparedDemand.interconnect,
        sourcePlacement=preparedDemand.sourcePlacement,
        destinationPlacement=preparedDemand.destinationPlacement,
        sourceInterFanRegion=preparedDemand.sourceInterFanRegion,
        destinationInterFanRegion=preparedDemand.destinationInterFanRegion,
        sourceInterTravelRegion=preparedDemand.sourceInterTravelRegion,
        destinationInterTravelRegion=preparedDemand.destinationInterTravelRegion,
        srcChipLines=preparedDemand.srcChipLines,
        dstChipLines=preparedDemand.dstChipLines,
        sourceSignalLineOffset=preparedDemand.sourceSignalLineOffset,
        destinationSignalLineOffset=preparedDemand.destinationSignalLineOffset,
        sourceReturnLineOffset=preparedDemand.sourceReturnLineOffset,
        destinationReturnLineOffset=preparedDemand.destinationReturnLineOffset,
        seamPairIndex=seamPairIndex,
        isReturn=False,
    )
    if not result_isOkCheck(fwdGeometryResult):
        return resultErr_build()

    fwdRouteResult = routingZoneInterconnectSolvedRouteResult_build(
        routingZoneInterconnectId=preparedDemand.interconnect.routingZoneInterconnectId,
        sourceChipRef=preparedDemand.callRouteObligation.sourceChipRef,
        destinationChipRef=preparedDemand.callRouteObligation.destinationChipRef,
        childCallIndex=preparedDemand.callRouteObligation.childCallIndex,
        solveKind=fwdGeometryResult.value[0],
        routePoints=fwdGeometryResult.value[1],
        traversedRegionIds=fwdGeometryResult.value[2],
    )
    if not result_isOkCheck(fwdRouteResult):
        return resultErr_build()

    if (
        preparedDemand.sourceReturnLineOffset is None
        or preparedDemand.destinationReturnLineOffset is None
    ):
        return resultOk_build((fwdRouteResult.value,))

    retGeometryResult = _seamGeometryResult_build(
        interconnect=preparedDemand.interconnect,
        sourcePlacement=preparedDemand.sourcePlacement,
        destinationPlacement=preparedDemand.destinationPlacement,
        sourceInterFanRegion=preparedDemand.sourceInterFanRegion,
        destinationInterFanRegion=preparedDemand.destinationInterFanRegion,
        sourceInterTravelRegion=preparedDemand.sourceInterTravelRegion,
        destinationInterTravelRegion=preparedDemand.destinationInterTravelRegion,
        srcChipLines=preparedDemand.srcChipLines,
        dstChipLines=preparedDemand.dstChipLines,
        sourceSignalLineOffset=preparedDemand.sourceSignalLineOffset,
        destinationSignalLineOffset=preparedDemand.destinationSignalLineOffset,
        sourceReturnLineOffset=preparedDemand.sourceReturnLineOffset,
        destinationReturnLineOffset=preparedDemand.destinationReturnLineOffset,
        seamPairIndex=seamPairIndex,
        isReturn=True,
    )
    if not result_isOkCheck(retGeometryResult):
        return resultErr_build()
    retRouteResult = routingZoneInterconnectSolvedRouteResult_build(
        routingZoneInterconnectId=preparedDemand.interconnect.routingZoneInterconnectId,
        sourceChipRef=preparedDemand.callRouteObligation.destinationChipRef,
        destinationChipRef=preparedDemand.callRouteObligation.sourceChipRef,
        childCallIndex=preparedDemand.callRouteObligation.childCallIndex,
        solveKind=retGeometryResult.value[0],
        routePoints=retGeometryResult.value[1],
        traversedRegionIds=retGeometryResult.value[2],
    )
    if not result_isOkCheck(retRouteResult):
        return resultErr_build()
    return resultOk_build((fwdRouteResult.value, retRouteResult.value))


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
            "Seam-crossing calls into multi-input destinations must resolve "
            "to one explicit input port"
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
    """Build inter-routing fan-in/out region for one chip side."""

    routingZoneRegionSide = (
        chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    )
    if routingZoneRegionSide is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.interconnect_solver.placement.missing_terminal_side",
            message="ChipPlacement terminal side is required for seam solving",
        )
        return resultErr_build()
    return routingZoneRegionForKindAndSideResult_get(
        routingZone,
        RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
        routingZoneRegionSide,
    )


def _interRoutingTravelRegionResult_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> Result[RoutingZoneRegion]:
    """Build the seam-travel region matching one chip placement side."""

    routingZoneRegionSide = (
        chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    )
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
    return routingZoneRegionForKindAndSideResult_get(
        routingZone,
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
    sourceSignalLineOffset: int,
    destinationSignalLineOffset: int,
    sourceReturnLineOffset: int | None,
    destinationReturnLineOffset: int | None,
    seamPairIndex: int,
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
            sourceInterTravelRegion=sourceInterTravelRegion,
            destinationInterTravelRegion=destinationInterTravelRegion,
            srcChipHeight=len(srcChipLines),
            dstChipHeight=len(dstChipLines),
            sourceSignalLineOffset=sourceSignalLineOffset,
            destinationSignalLineOffset=destinationSignalLineOffset,
            sourceReturnLineOffset=sourceReturnLineOffset,
            destinationReturnLineOffset=destinationReturnLineOffset,
            seamPairIndex=seamPairIndex,
            isReturn=isReturn,
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
        sourceSignalLineOffset=sourceSignalLineOffset,
        destinationSignalLineOffset=destinationSignalLineOffset,
        sourceReturnLineOffset=sourceReturnLineOffset,
        destinationReturnLineOffset=destinationReturnLineOffset,
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
    sourceSignalLineOffset: int,
    destinationSignalLineOffset: int,
    sourceReturnLineOffset: int | None,
    destinationReturnLineOffset: int | None,
    seamPairIndex: int,
    isReturn: bool,
) -> Result[
    tuple[
        RoutingZoneInterconnectRouteSolveKind,
        tuple[RoutingZoneRoutePoint, ...],
        tuple[RoutingZoneRegionId, ...],
    ]
]:
    """Build explicit horizontal seam geometry."""

    laneIndex: int = 2 * seamPairIndex + (1 if isReturn else 0)
    srcSignalRow: int = (
        sourceInterFanRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipHeight + 2)
        + 1
        + sourceSignalLineOffset
    )
    dstSignalRow: int = (
        destinationInterFanRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipHeight + 2)
        + 1
        + destinationSignalLineOffset
    )

    if isReturn:
        # Return: leaf (dst) → mid (src), using return port rows (+1).
        if (
            sourceReturnLineOffset is None
            or destinationReturnLineOffset is None
        ):
            return resultErr_build()
        startFanRegion = destinationInterFanRegion
        endFanRegion = sourceInterFanRegion
        startRow = (
            destinationInterFanRegion.routingZoneRegionFrame.verticalStart
            + destinationPlacement.orderIndex * (dstChipHeight + 2)
            + 1
            + destinationReturnLineOffset
        )
        endRow = (
            sourceInterFanRegion.routingZoneRegionFrame.verticalStart
            + sourcePlacement.orderIndex * (srcChipHeight + 2)
            + 1
            + sourceReturnLineOffset
        )
        straightKind = (
            RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM_RETURN
        )
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM_RETURN
    else:
        startFanRegion = sourceInterFanRegion
        endFanRegion = destinationInterFanRegion
        startRow = srcSignalRow
        endRow = dstSignalRow
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM

    srcFanStart: int = (
        sourceInterFanRegion.routingZoneRegionFrame.horizontalStart
    )
    dstFanStart: int = (
        destinationInterFanRegion.routingZoneRegionFrame.horizontalStart
    )
    dstFanEnd: int = (
        destinationInterFanRegion.routingZoneRegionFrame.horizontalEnd_calculate()
        - 1
    )
    srcTravelStart: int = (
        sourceInterTravelRegion.routingZoneRegionFrame.horizontalStart
    )
    dstTravelStart: int = (
        destinationInterTravelRegion.routingZoneRegionFrame.horizontalStart
    )
    seamCol: int = (
        interconnect.routingZoneInterconnectFrame.horizontalStart + laneIndex
    )
    srcTravelCol: int = srcTravelStart + laneIndex
    dstTravelCol: int = dstTravelStart + laneIndex
    srcLaneCol: int = srcFanStart + 2 + laneIndex
    dstLaneCol: int = dstFanStart + laneIndex

    if isReturn:
        routeColSeq: list[int] = [
            dstFanEnd,
            dstFanEnd - 1,
            dstLaneCol,
            dstTravelCol,
            seamCol,
        ]
        endLaneCols: list[int] = [
            srcTravelCol,
            srcLaneCol,
            srcFanStart + 1,
            srcFanStart,
        ]
    else:
        routeColSeq = [
            srcFanStart,
            srcFanStart + 1,
            srcLaneCol,
            srcTravelCol,
            seamCol,
        ]
        endLaneCols = [
            dstTravelCol,
            dstLaneCol,
            dstFanEnd - 1,
            dstFanEnd,
        ]

    routePointsMutable: list[RoutingZoneRoutePoint] = []
    for col in routeColSeq:
        ptResult = routingZoneRoutePointResult_build(
            horizontalIndex=col,
            verticalIndex=startRow,
        )
        if not result_isOkCheck(ptResult):
            return resultErr_build()
        routePointsMutable.append(ptResult.value)

    if startRow != endRow:
        turnResult = routingZoneRoutePointResult_build(
            horizontalIndex=seamCol,
            verticalIndex=endRow,
        )
        if not result_isOkCheck(turnResult):
            return resultErr_build()
        routePointsMutable.append(turnResult.value)

    for col in endLaneCols:
        ptResult = routingZoneRoutePointResult_build(
            horizontalIndex=col,
            verticalIndex=endRow,
        )
        if not result_isOkCheck(ptResult):
            return resultErr_build()
        routePointsMutable.append(ptResult.value)

    solveKind = straightKind if startRow == endRow else offsetKind
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
    sourceSignalLineOffset: int,
    destinationSignalLineOffset: int,
    sourceReturnLineOffset: int | None,
    destinationReturnLineOffset: int | None,
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

    laneIndex: int = 2 * seamPairIndex + (1 if isReturn else 0)
    srcSignalCol: int = (
        sourceInterFanRegion.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex * (srcChipWidth + 2)
        + 1
        + sourceSignalLineOffset
    )
    dstSignalCol: int = (
        destinationInterFanRegion.routingZoneRegionFrame.horizontalStart
        + destinationPlacement.orderIndex * (dstChipWidth + 2)
        + 1
        + destinationSignalLineOffset
    )

    if isReturn:
        # Return: leaf (dst) → mid (src), using return port columns (+1).
        if (
            sourceReturnLineOffset is None
            or destinationReturnLineOffset is None
        ):
            return resultErr_build()
        startFanRegion = destinationInterFanRegion
        endFanRegion = sourceInterFanRegion
        startCol = (
            destinationInterFanRegion.routingZoneRegionFrame.horizontalStart
            + destinationPlacement.orderIndex * (dstChipWidth + 2)
            + 1
            + destinationReturnLineOffset
        )
        endCol = (
            sourceInterFanRegion.routingZoneRegionFrame.horizontalStart
            + sourcePlacement.orderIndex * (srcChipWidth + 2)
            + 1
            + sourceReturnLineOffset
        )
        straightKind = (
            RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM_RETURN
        )
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM_RETURN
    else:
        startFanRegion = sourceInterFanRegion
        endFanRegion = destinationInterFanRegion
        startCol = srcSignalCol
        endCol = dstSignalCol
        straightKind = RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM
        offsetKind = RoutingZoneInterconnectRouteSolveKind.OFFSET_SEAM

    srcFanStart: int = (
        sourceInterFanRegion.routingZoneRegionFrame.verticalStart
    )
    dstFanStart: int = (
        destinationInterFanRegion.routingZoneRegionFrame.verticalStart
    )
    destinationFrame = destinationInterFanRegion.routingZoneRegionFrame
    dstFanEnd: int = destinationFrame.verticalEnd_calculate()
    srcTravelStart: int = (
        sourceInterTravelRegion.routingZoneRegionFrame.verticalStart
    )
    dstTravelStart: int = (
        destinationInterTravelRegion.routingZoneRegionFrame.verticalStart
    )
    seamRow: int = (
        interconnect.routingZoneInterconnectFrame.verticalStart + laneIndex
    )
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
