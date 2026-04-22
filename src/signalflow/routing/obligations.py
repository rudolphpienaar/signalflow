"""Route-obligation builders from circuit and placement state.

This module derives the first explicit routing-input layer from the validated
circuit tree and the logically placed routing-zone world.
"""

from __future__ import annotations

from signalflow.models import (
    CallingStack,
    CallRouteObligation,
    CallRouteObligationSet,
    Chip,
    ChipInternalRouteObligation,
    ChipInternalRouteObligationSet,
    ChipPortDeclaration,
    ChipRef,
    CircuitCall,
    CircuitDocument,
    Result,
    RouteObligationScope,
    RouteObligationSet,
    RoutingZone,
    RoutingZoneGrid,
    RoutingZoneId,
    RoutingZoneRegionSide,
    ZoneLocalGeometryKind,
    callingStackResult_buildFromCircuitDocument,
    callRouteObligationSetResult_build,
    chipInternalRouteObligationSetResult_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routeObligationSetResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


def routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
) -> Result[RouteObligationSet]:
    """Build explicit route obligations from circuit and placement plan."""

    callRouteObligationsMutable: list[CallRouteObligation] = []
    chipInternalRouteObligationsMutable: list[ChipInternalRouteObligation] = []
    callingStackResult: Result[CallingStack] = (
        callingStackResult_buildFromCircuitDocument(circuitDocument)
    )
    if not result_isOkCheck(callingStackResult):
        return resultErr_build()
    if not _routeObligations_collectCheck(
        circuitDocument=circuitDocument,
        callingStack=callingStackResult.value,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        callRouteObligationsMutable=callRouteObligationsMutable,
        chipInternalRouteObligationsMutable=chipInternalRouteObligationsMutable,
    ):
        return resultErr_build()

    callRouteObligationSetResult: Result[CallRouteObligationSet] = (
        callRouteObligationSetResult_build(
            callRouteObligations=tuple(callRouteObligationsMutable)
        )
    )
    if not result_isOkCheck(callRouteObligationSetResult):
        return resultErr_build()
    chipInternalRouteObligationSetResult: Result[
        ChipInternalRouteObligationSet
    ] = chipInternalRouteObligationSetResult_build(
        chipInternalRouteObligations=tuple(chipInternalRouteObligationsMutable)
    )
    if not result_isOkCheck(chipInternalRouteObligationSetResult):
        return resultErr_build()
    return routeObligationSetResult_build(
        callRouteObligationSet=callRouteObligationSetResult.value,
        chipInternalRouteObligationSet=chipInternalRouteObligationSetResult.value,
    )


def _routeObligations_collectCheck(
    circuitDocument: CircuitDocument,
    callingStack: CallingStack,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationsMutable: list[CallRouteObligation],
    chipInternalRouteObligationsMutable: list[ChipInternalRouteObligation],
) -> bool:
    """Collect call and internal obligations from the circuit graph."""

    chip: Chip
    for chip in circuitDocument.circuitChipSet.chips:
        chipInternalWiringDirective = None
        for (
            chipInternalWiringDirective
        ) in chip.internalWiringDirectiveSet.directives:
            chipInternalRouteObligationsMutable.append(
                ChipInternalRouteObligation(
                    chipRef=chip.chipRef_build(),
                    chipInternalWiringDirective=chipInternalWiringDirective,
                )
            )

    circuitCall: CircuitCall
    for circuitCall in circuitDocument.circuitCallSet.circuitCalls:
        routeObligationScopeResult: Result[RouteObligationScope] = (
            _callScopeResult_build(
                sourceChipRef=circuitCall.sourceChipRef,
                destinationChipRef=circuitCall.destinationChipRef,
                placedRoutingZoneGrid=placedRoutingZoneGrid,
            )
        )
        if not result_isOkCheck(routeObligationScopeResult):
            return False
        sourceChipResult = circuitDocument.circuitChipSet.chipResult_get(
            circuitCall.sourceChipRef.chipId
        )
        if not result_isOkCheck(sourceChipResult):
            return False
        sourcePortDeclaration: ChipPortDeclaration | None = (
            circuitCall.sourcePortDeclaration
        )
        zoneLocalGeometryKind: ZoneLocalGeometryKind | None = None
        if sourcePortDeclaration is None and circuitCall.callIndex < len(
            sourceChipResult.value.outputPortDeclarationSet.portDeclarations
        ):
            portDeclarations = (
                sourceChipResult.value.outputPortDeclarationSet.portDeclarations
            )
            sourcePortDeclaration = portDeclarations[circuitCall.callIndex]
        if routeObligationScopeResult.value is RouteObligationScope.ZONE_LOCAL:
            zoneLocalGeometryKindResult = _zoneLocalGeometryKindResult_build(
                callingStack=callingStack,
                sourceChipRef=circuitCall.sourceChipRef,
                destinationChipRef=circuitCall.destinationChipRef,
                placedRoutingZoneGrid=placedRoutingZoneGrid,
            )
            if not result_isOkCheck(zoneLocalGeometryKindResult):
                return False
            zoneLocalGeometryKind = zoneLocalGeometryKindResult.value
        callingStackDelta: int | None = callingStack.deltaOrNone_get(
            circuitCall.sourceChipRef,
            circuitCall.destinationChipRef,
        )

        callRouteObligationsMutable.append(
            CallRouteObligation(
                sourceChipRef=circuitCall.sourceChipRef,
                destinationChipRef=circuitCall.destinationChipRef,
                childCallIndex=circuitCall.callIndex,
                routeObligationScope=routeObligationScopeResult.value,
                zoneLocalGeometryKind=zoneLocalGeometryKind,
                callingStackDelta=callingStackDelta,
                sourcePortDeclaration=sourcePortDeclaration,
            )
        )
    return True


def _callScopeResult_build(
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    placedRoutingZoneGrid: RoutingZoneGrid,
) -> Result[RouteObligationScope]:
    """Build route-obligation scope for one parent-to-child call edge."""

    sourceZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
        chipRef=sourceChipRef,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
    )
    if not result_isOkCheck(sourceZoneResult):
        return resultErr_build()
    destinationZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
        chipRef=destinationChipRef,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
    )
    if not result_isOkCheck(destinationZoneResult):
        return resultErr_build()

    sourceZoneId: RoutingZoneId = sourceZoneResult.value.routingZoneId
    destinationZoneId: RoutingZoneId = (
        destinationZoneResult.value.routingZoneId
    )
    if sourceZoneId == destinationZoneId:
        return resultOk_build(RouteObligationScope.ZONE_LOCAL)

    neighboringResult = sourceZoneId.neighboringToZoneResult_build(
        destinationZoneId
    )
    if not result_isOkCheck(neighboringResult):
        return resultErr_build()
    if neighboringResult.value:
        return resultOk_build(RouteObligationScope.SEAM_CROSSING)
    return resultOk_build(RouteObligationScope.GRID_LONG_HAUL)


def _zoneOwningChipResult_build(
    chipRef: ChipRef,
    placedRoutingZoneGrid: RoutingZoneGrid,
) -> Result[RoutingZone]:
    """Build the placed routing zone that owns one chip occurrence."""

    routingZone: RoutingZone
    for routingZone in placedRoutingZoneGrid.routingZoneSet.routingZones:
        placement = routingZone.chipPlacementSet.placementForChipOrNone_get(
            chipRef
        )
        if placement is not None:
            return resultOk_build(routingZone)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.obligation.missing_chip_placement",
        message=(
            "Placed RoutingZoneGrid does not contain a placement for the "
            "requested chip"
        ),
        context=(chipRef.chipId.moduleName, chipRef.chipId.functionName),
    )
    return resultErr_build()


def _zoneLocalGeometryKindResult_build(
    callingStack: CallingStack,
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    placedRoutingZoneGrid: RoutingZoneGrid,
) -> Result[ZoneLocalGeometryKind]:
    """Build local geometry owner for one same-zone call obligation."""

    sourceZoneResult = _zoneOwningChipResult_build(
        chipRef=sourceChipRef,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
    )
    destinationZoneResult = _zoneOwningChipResult_build(
        chipRef=destinationChipRef,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
    )
    if not (
        result_isOkCheck(sourceZoneResult)
        and result_isOkCheck(destinationZoneResult)
    ):
        return resultErr_build()
    if (
        sourceZoneResult.value.routingZoneId
        != destinationZoneResult.value.routingZoneId
    ):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.obligation.zone_local_geometry.cross_zone_call",
            message=(
                "Zone-local geometry kind may only be computed for chips that "
                "share one routing zone"
            ),
        )
        return resultErr_build()

    zone: RoutingZone = sourceZoneResult.value
    sourcePlacement = zone.chipPlacementSet.placementForChipOrNone_get(
        sourceChipRef
    )
    destinationPlacement = zone.chipPlacementSet.placementForChipOrNone_get(
        destinationChipRef
    )
    if sourcePlacement is None or destinationPlacement is None:
        return resultErr_build()

    sourceDepth: int | None = callingStack.depthForChipOrNone_get(
        sourceChipRef
    )
    destinationDepth: int | None = callingStack.depthForChipOrNone_get(
        destinationChipRef
    )
    if sourceDepth is None or destinationDepth is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.obligation.calling_stack.missing_chip_depth",
            message="Calling stack could not classify one same-zone call",
            context=(
                sourceChipRef.chipId.moduleName,
                sourceChipRef.chipId.functionName,
                destinationChipRef.chipId.moduleName,
                destinationChipRef.chipId.functionName,
            ),
        )
        return resultErr_build()

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = (
        destinationPlacement.chipTerminalRegionId.routingZoneRegionSide
    )
    depthDelta: int = destinationDepth - sourceDepth
    if depthDelta > 0:
        return resultOk_build(ZoneLocalGeometryKind.INTRA_PARENT_TOCHILD)
    if depthDelta < 0:
        return resultOk_build(ZoneLocalGeometryKind.OUTER_CHILD_TOPARENT)
    if sourceSide is RoutingZoneRegionSide.WEST:
        return resultOk_build(ZoneLocalGeometryKind.OUTER_PARENT_UTURN)
    return resultOk_build(ZoneLocalGeometryKind.OUTER_CHILD_UTURN)
