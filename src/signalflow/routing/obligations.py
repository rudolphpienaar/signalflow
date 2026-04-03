"""Route-obligation builders from circuit and placement state.

This module derives the first explicit routing-input layer from the validated
circuit tree and the logically placed routing-zone world.
"""
from __future__ import annotations

from signalflow.models import (
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
    RoutingZoneSense,
    ZoneLocalGeometryKind,
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
    if not _routeObligations_collectCheck(
        circuitDocument=circuitDocument,
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
    chipInternalRouteObligationSetResult: Result[ChipInternalRouteObligationSet] = (
        chipInternalRouteObligationSetResult_build(
            chipInternalRouteObligations=tuple(chipInternalRouteObligationsMutable)
        )
    )
    if not result_isOkCheck(chipInternalRouteObligationSetResult):
        return resultErr_build()
    return routeObligationSetResult_build(
        callRouteObligationSet=callRouteObligationSetResult.value,
        chipInternalRouteObligationSet=chipInternalRouteObligationSetResult.value,
    )


def _routeObligations_collectCheck(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationsMutable: list[CallRouteObligation],
    chipInternalRouteObligationsMutable: list[ChipInternalRouteObligation],
) -> bool:
    """Collect call and internal obligations across the canonical circuit graph."""

    chip: Chip
    for chip in circuitDocument.circuitChipSet.chips:
        chipInternalWiringDirective = None
        for chipInternalWiringDirective in chip.internalWiringDirectiveSet.directives:
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
            sourcePortDeclaration = (
                sourceChipResult.value.outputPortDeclarationSet.portDeclarations[
                    circuitCall.callIndex
                ]
            )
        if routeObligationScopeResult.value is RouteObligationScope.ZONE_LOCAL:
            zoneLocalGeometryKindResult = _zoneLocalGeometryKindResult_build(
                sourceChipRef=circuitCall.sourceChipRef,
                destinationChipRef=circuitCall.destinationChipRef,
                placedRoutingZoneGrid=placedRoutingZoneGrid,
            )
            if not result_isOkCheck(zoneLocalGeometryKindResult):
                return False
            zoneLocalGeometryKind = zoneLocalGeometryKindResult.value

        callRouteObligationsMutable.append(
            CallRouteObligation(
                sourceChipRef=circuitCall.sourceChipRef,
                destinationChipRef=circuitCall.destinationChipRef,
                childCallIndex=circuitCall.callIndex,
                routeObligationScope=routeObligationScopeResult.value,
                zoneLocalGeometryKind=zoneLocalGeometryKind,
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
    destinationZoneId: RoutingZoneId = destinationZoneResult.value.routingZoneId
    if sourceZoneId == destinationZoneId:
        return resultOk_build(RouteObligationScope.ZONE_LOCAL)

    neighboringResult = sourceZoneId.neighboringToZoneResult_build(destinationZoneId)
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
        placement = routingZone.chipPlacementSet.placementForChipOrNone_get(chipRef)
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
        result_isOkCheck(sourceZoneResult) and result_isOkCheck(destinationZoneResult)
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
    sourcePlacement = zone.chipPlacementSet.placementForChipOrNone_get(sourceChipRef)
    destinationPlacement = zone.chipPlacementSet.placementForChipOrNone_get(
        destinationChipRef
    )
    if sourcePlacement is None or destinationPlacement is None:
        return resultErr_build()

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = destinationPlacement.chipTerminalRegionId.routingZoneRegionSide
    if sourceSide == destinationSide:
        return resultOk_build(ZoneLocalGeometryKind.SAME_SIDE_LOCAL)

    if zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        if (
            sourceSide is RoutingZoneRegionSide.WEST
            and destinationSide is RoutingZoneRegionSide.EAST
        ):
            return resultOk_build(
                ZoneLocalGeometryKind.INTRA_TRANSVERSE_FORWARD
            )
        if (
            sourceSide is RoutingZoneRegionSide.EAST
            and destinationSide is RoutingZoneRegionSide.WEST
        ):
            return resultOk_build(
                ZoneLocalGeometryKind.INTER_PERIMETER_BACKEDGE
            )
    else:
        if (
            sourceSide is RoutingZoneRegionSide.NORTH
            and destinationSide is RoutingZoneRegionSide.SOUTH
        ):
            return resultOk_build(
                ZoneLocalGeometryKind.INTRA_TRANSVERSE_FORWARD
            )
        if (
            sourceSide is RoutingZoneRegionSide.SOUTH
            and destinationSide is RoutingZoneRegionSide.NORTH
        ):
            return resultOk_build(
                ZoneLocalGeometryKind.INTER_PERIMETER_BACKEDGE
            )

    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.obligation.zone_local_geometry.unsupported_side_pair",
        message=(
            "Same-zone call uses a side pair with no supported local geometry "
            "owner"
        ),
        context=(
            sourceChipRef.chipId.moduleName,
            sourceChipRef.chipId.functionName,
            destinationChipRef.chipId.moduleName,
            destinationChipRef.chipId.functionName,
            sourceSide.value if sourceSide else "none",
            destinationSide.value if destinationSide else "none",
        ),
    )
    return resultErr_build()
