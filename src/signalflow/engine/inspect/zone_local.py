"""Synthetic overlap-zone inspect context builders.

This module builds one independently solvable overlap zone from the full
circuit document and calling-stack bands. It does not depend on the older
global world-grid assumption that all overlap zones must already exist inside
one composed world.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from signalflow.config import SignalFlowConfig, configResult_build
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    CallingStack,
    CallRouteObligation,
    Chip,
    ChipInternalRouteObligation,
    ChipPortDeclaration,
    ChipRef,
    CircuitCall,
    CircuitDocument,
    GridCoord,
    Result,
    RouteObligationScope,
    RouteObligationSet,
    RoutingZone,
    RoutingZoneAssignment,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneGridSolvedRouteSet,
    RoutingZoneId,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneRegionSide,
    RoutingZoneSet,
    ZoneLocalGeometryKind,
    callingStackResult_buildFromCircuitDocument,
    callRouteObligationSetResult_build,
    chipInternalRouteObligationSetResult_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routeObligationSetResult_build,
    routingZoneAssignmentSetResult_build,
    routingZoneGridResult_build,
    routingZoneResult_build,
    routingZoneSetResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.routing import (
    chipInternalSolvedRoutesResult_build,
    placedRoutingZoneGridResult_build,
    zoneLocalSolvedRoutesResult_build,
)

from .context import InspectBoardWorld, InspectStagedWorld, SignalFlowContext


@dataclass(frozen=True)
class _ZoneLocalArtifacts:
    """Intermediate artifacts for one synthetic overlap-zone context."""

    circuitDocument: CircuitDocument
    callingStack: CallingStack
    signalFlowConfig: SignalFlowConfig
    routingZoneGrid: RoutingZoneGrid
    routingZoneAssignmentSet: RoutingZoneAssignmentSet
    placedRoutingZoneGrid: RoutingZoneGrid
    routeObligationSet: RouteObligationSet


def contextResult_buildFromDocumentAndZone(
    documentDict: dict[str, object],
    *,
    columnIndex: int,
    rowIndex: int,
) -> Result[SignalFlowContext]:
    """Build one synthetic overlap-zone inspect context.

    Args:
        documentDict: Full source document.
        columnIndex: Requested zone column.
        rowIndex: Requested zone row.

    Returns:
        Successful result containing a single-zone `SignalFlowContext` whose
        only materialized zone represents the requested overlap band pair.
    """

    diagnosticStack.stack_clear()

    artifactsResult = _zoneLocalArtifactsResult_build(
        documentDict,
        columnIndex=columnIndex,
        rowIndex=rowIndex,
    )
    if not result_isOkCheck(artifactsResult):
        return resultErr_build()
    artifacts = artifactsResult.value

    chipInternalSolvedRouteSetResult = chipInternalSolvedRoutesResult_build(
        artifacts.circuitDocument,
        artifacts.routeObligationSet.chipInternalRouteObligationSet,
    )
    if not result_isOkCheck(chipInternalSolvedRouteSetResult):
        return resultErr_build()

    routingZoneLocalSolvedRouteSetResult = zoneLocalSolvedRoutesResult_build(
        artifacts.circuitDocument,
        artifacts.placedRoutingZoneGrid,
        artifacts.routeObligationSet.callRouteObligationSet,
    )
    if not result_isOkCheck(routingZoneLocalSolvedRouteSetResult):
        return resultErr_build()

    stagedWorld = InspectStagedWorld(
        routingZoneGrid=artifacts.routingZoneGrid,
        routingZoneAssignmentSet=artifacts.routingZoneAssignmentSet,
        placedRoutingZoneGrid=artifacts.placedRoutingZoneGrid,
        routeObligationSet=artifacts.routeObligationSet,
        chipInternalSolvedRouteSet=chipInternalSolvedRouteSetResult.value,
        routingZoneLocalSolvedRouteSet=routingZoneLocalSolvedRouteSetResult.value,
        routingZoneInterconnectSolvedRouteSet=(
            RoutingZoneInterconnectSolvedRouteSet(
                routingZoneInterconnectSolvedRoutes=()
            )
        ),
        routingZoneGridSolvedRouteSet=RoutingZoneGridSolvedRouteSet(
            routingZoneGridSolvedRoutes=()
        ),
    )
    baseContext = SignalFlowContext(
        documentDict=documentDict,
        circuitDocument=artifacts.circuitDocument,
        signalFlowConfig=artifacts.signalFlowConfig,
        stagedWorld=stagedWorld,
        boardWorld=InspectBoardWorld(
            boardZonesById={},
            compatibilityPlacedGrid=artifacts.placedRoutingZoneGrid,
        ),
    )
    boardWorld = _zoneLocalBoardWorld_build(baseContext)
    return resultOk_build(
        SignalFlowContext(
            documentDict=baseContext.documentDict,
            circuitDocument=baseContext.circuitDocument,
            signalFlowConfig=baseContext.signalFlowConfig,
            stagedWorld=baseContext.stagedWorld,
            boardWorld=boardWorld,
        )
    )


def _zoneLocalArtifactsResult_build(
    documentDict: dict[str, object],
    *,
    columnIndex: int,
    rowIndex: int,
) -> Result[_ZoneLocalArtifacts]:
    """Build one synthetic overlap-zone artifact set."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
        documentDict
    )
    if not result_isOkCheck(circuitDocumentResult):
        return resultErr_build()
    circuitDocument = circuitDocumentResult.value

    callingStackResult = callingStackResult_buildFromCircuitDocument(
        circuitDocument
    )
    if not result_isOkCheck(callingStackResult):
        return resultErr_build()
    callingStack = callingStackResult.value

    overlapIndexResult = _overlapIndexResult_build(
        columnIndex=columnIndex,
        rowIndex=rowIndex,
        callingStack=callingStack,
    )
    if not result_isOkCheck(overlapIndexResult):
        return resultErr_build()
    overlapIndex = overlapIndexResult.value

    signalFlowConfigResult = configResult_build(
        documentDict,
        callingDepth=callingStack.bandCount_calculate(),
    )
    if not result_isOkCheck(signalFlowConfigResult):
        return resultErr_build()
    signalFlowConfig = signalFlowConfigResult.value

    routingZoneGridResult = _syntheticRoutingZoneGridResult_build(
        signalFlowConfig=signalFlowConfig
    )
    if not result_isOkCheck(routingZoneGridResult):
        return resultErr_build()
    routingZoneGrid = routingZoneGridResult.value

    routingZoneAssignmentSetResult = _zoneLocalAssignmentSetResult_build(
        callingStack=callingStack,
        overlapIndex=overlapIndex,
    )
    if not result_isOkCheck(routingZoneAssignmentSetResult):
        return resultErr_build()
    routingZoneAssignmentSet = routingZoneAssignmentSetResult.value

    placedRoutingZoneGridResult = placedRoutingZoneGridResult_build(
        routingZoneAssignmentSet,
        routingZoneGrid,
        circuitDocument,
    )
    if not result_isOkCheck(placedRoutingZoneGridResult):
        return resultErr_build()
    placedRoutingZoneGrid = placedRoutingZoneGridResult.value

    routeObligationSetResult = _zoneLocalRouteObligationSetResult_build(
        circuitDocument=circuitDocument,
        callingStack=callingStack,
        overlapIndex=overlapIndex,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
    )
    if not result_isOkCheck(routeObligationSetResult):
        return resultErr_build()

    return resultOk_build(
        _ZoneLocalArtifacts(
            circuitDocument=circuitDocument,
            callingStack=callingStack,
            signalFlowConfig=signalFlowConfig,
            routingZoneGrid=routingZoneGrid,
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            routeObligationSet=routeObligationSetResult.value,
        )
    )


def _overlapIndexResult_build(
    *,
    columnIndex: int,
    rowIndex: int,
    callingStack: CallingStack,
) -> Result[int]:
    """Resolve one requested overlap-zone coordinate to a 1-based band pair."""

    if columnIndex < 1 or rowIndex < 1:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="inspect.zone_local.invalid_zone_coord",
            message="Zone coordinates must be positive integers",
            context=(str(columnIndex), str(rowIndex)),
        )
        return resultErr_build()
    if columnIndex != 1 and rowIndex != 1:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="inspect.zone_local.unsupported_two_dimensional_coord",
            message=(
                "Overlap-zone inspection currently supports only one "
                "advancing axis; one coordinate must be 1"
            ),
            context=(str(columnIndex), str(rowIndex)),
        )
        return resultErr_build()
    overlapIndex: int = max(columnIndex, rowIndex)
    maxOverlapIndex: int = max(1, callingStack.bandCount_calculate() - 1)
    if overlapIndex > maxOverlapIndex:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="inspect.zone_local.absent_overlap_zone",
            message=(
                "Requested overlap zone exceeds the available adjacent "
                "calling-stack band pairs"
            ),
            context=(str(overlapIndex), str(maxOverlapIndex)),
        )
        return resultErr_build()
    return resultOk_build(overlapIndex)


def _syntheticRoutingZoneGridResult_build(
    *,
    signalFlowConfig: SignalFlowConfig,
) -> Result[RoutingZoneGrid]:
    """Build a single-zone grid carrying the full document's local policies."""

    routingZoneId = RoutingZoneId(id=GridCoord(columnIndex=1, rowIndex=1))
    routingZoneResult = routingZoneResult_build(
        routingZoneId=routingZoneId,
        routingZoneSense=signalFlowConfig.routingZoneGridConfig.worldSense,
        channelSense=signalFlowConfig.routingZoneGridConfig.channelSense,
        occupancyPolicy=signalFlowConfig.routingZoneGridConfig.occupancyPolicy,
        packingPolicy=signalFlowConfig.routingZoneGridConfig.packingPolicy,
    )
    if not result_isOkCheck(routingZoneResult):
        return resultErr_build()
    routingZoneSetResult = routingZoneSetResult_build(
        (routingZoneResult.value,)
    )
    if not result_isOkCheck(routingZoneSetResult):
        return resultErr_build()
    return routingZoneGridResult_build(
        worldSense=signalFlowConfig.routingZoneGridConfig.worldSense,
        gridSize=GridCoord(columnIndex=1, rowIndex=1),
        routingZoneSet=routingZoneSetResult.value,
        moduleBoxPadding=signalFlowConfig.routingZoneGridConfig.moduleBoxPadding,
    )


def _zoneLocalAssignmentSetResult_build(
    *,
    callingStack: CallingStack,
    overlapIndex: int,
) -> Result[RoutingZoneAssignmentSet]:
    """Assign the selected adjacent calling-stack bands into one local zone."""

    lowerDepthIndex: int = overlapIndex - 1
    upperDepthIndex: int = overlapIndex
    zoneId = RoutingZoneId(id=GridCoord(columnIndex=1, rowIndex=1))
    assignmentsMutable: list[RoutingZoneAssignment] = []
    for level in callingStack.levels:
        if level.depthIndex == lowerDepthIndex:
            for chipRef in level.chipRefs:
                assignmentsMutable.append(
                    RoutingZoneAssignment(
                        chipRef=chipRef,
                        routingZoneId=zoneId,
                        terminalSide=RoutingZoneRegionSide.WEST,
                    )
                )
        if level.depthIndex == upperDepthIndex:
            for chipRef in level.chipRefs:
                assignmentsMutable.append(
                    RoutingZoneAssignment(
                        chipRef=chipRef,
                        routingZoneId=zoneId,
                        terminalSide=RoutingZoneRegionSide.EAST,
                    )
                )
    return routingZoneAssignmentSetResult_build(tuple(assignmentsMutable))


def _zoneLocalRouteObligationSetResult_build(
    *,
    circuitDocument: CircuitDocument,
    callingStack: CallingStack,
    overlapIndex: int,
    placedRoutingZoneGrid: RoutingZoneGrid,
) -> Result[RouteObligationSet]:
    """Build route obligations for one synthetic overlap zone only."""

    lowerDepthIndex: int = overlapIndex - 1
    upperDepthIndex: int = overlapIndex
    selectedChipRefs: set[ChipRef] = {
        chipRef
        for level in callingStack.levels
        if level.depthIndex in {lowerDepthIndex, upperDepthIndex}
        for chipRef in level.chipRefs
    }

    callRouteObligationsMutable: list[CallRouteObligation] = []
    chipInternalRouteObligationsMutable: list[ChipInternalRouteObligation] = []

    chip: Chip
    for chip in circuitDocument.circuitChipSet.chips:
        chipRef = chip.chipRef_build()
        if chipRef not in selectedChipRefs:
            continue
        for directive in chip.internalWiringDirectiveSet.directives:
            chipInternalRouteObligationsMutable.append(
                ChipInternalRouteObligation(
                    chipRef=chipRef,
                    chipInternalWiringDirective=directive,
                )
            )

    circuitCall: CircuitCall
    for circuitCall in circuitDocument.circuitCallSet.circuitCalls:
        if circuitCall.sourceChipRef not in selectedChipRefs:
            continue
        if circuitCall.destinationChipRef not in selectedChipRefs:
            continue
        sourceChipResult = circuitDocument.circuitChipSet.chipResult_get(
            circuitCall.sourceChipRef.chipId
        )
        if not result_isOkCheck(sourceChipResult):
            return resultErr_build()
        sourcePortDeclaration: ChipPortDeclaration | None = (
            circuitCall.sourcePortDeclaration
        )
        if sourcePortDeclaration is None and circuitCall.callIndex < len(
            sourceChipResult.value.outputPortDeclarationSet.portDeclarations
        ):
            outputPortDeclarationSet = (
                sourceChipResult.value.outputPortDeclarationSet
            )
            sourcePortDeclarations = outputPortDeclarationSet.portDeclarations
            sourcePortDeclaration = sourcePortDeclarations[
                circuitCall.callIndex
            ]
        sourceDisplayPortDeclaration: ChipPortDeclaration | None = None
        if circuitCall.callIndex < len(
            sourceChipResult.value.outputDisplayPortDeclarationSet.portDeclarations
        ):
            outputDisplayPortDeclarationSet = (
                sourceChipResult.value.outputDisplayPortDeclarationSet
            )
            sourceDisplayPortDeclarations = (
                outputDisplayPortDeclarationSet.portDeclarations
            )
            sourceDisplayPortDeclaration = sourceDisplayPortDeclarations[
                circuitCall.callIndex
            ]
        if sourceDisplayPortDeclaration is None:
            sourceDisplayPortDeclaration = sourcePortDeclaration
        zoneLocalGeometryKindResult = _zoneLocalGeometryKindResult_build(
            callingStack=callingStack,
            sourceChipRef=circuitCall.sourceChipRef,
            destinationChipRef=circuitCall.destinationChipRef,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
        )
        if not result_isOkCheck(zoneLocalGeometryKindResult):
            return resultErr_build()
        callRouteObligationsMutable.append(
            CallRouteObligation(
                sourceChipRef=circuitCall.sourceChipRef,
                destinationChipRef=circuitCall.destinationChipRef,
                childCallIndex=circuitCall.callIndex,
                routeObligationScope=RouteObligationScope.ZONE_LOCAL,
                zoneLocalGeometryKind=zoneLocalGeometryKindResult.value,
                callingStackDelta=callingStack.deltaOrNone_get(
                    circuitCall.sourceChipRef,
                    circuitCall.destinationChipRef,
                ),
                sourcePortDeclaration=sourcePortDeclaration,
                sourceDisplayPortDeclaration=sourceDisplayPortDeclaration,
            )
        )

    callRouteObligationSetResult = callRouteObligationSetResult_build(
        tuple(callRouteObligationsMutable)
    )
    if not result_isOkCheck(callRouteObligationSetResult):
        return resultErr_build()
    chipInternalRouteObligationSetResult = (
        chipInternalRouteObligationSetResult_build(
            tuple(chipInternalRouteObligationsMutable)
        )
    )
    if not result_isOkCheck(chipInternalRouteObligationSetResult):
        return resultErr_build()
    return routeObligationSetResult_build(
        callRouteObligationSet=callRouteObligationSetResult.value,
        chipInternalRouteObligationSet=chipInternalRouteObligationSetResult.value,
    )


def _zoneLocalGeometryKindResult_build(
    *,
    callingStack: CallingStack,
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    placedRoutingZoneGrid: RoutingZoneGrid,
) -> Result[ZoneLocalGeometryKind]:
    """Classify one same-zone local obligation inside the synthetic zone."""

    zone: RoutingZone = placedRoutingZoneGrid.routingZoneSet.routingZones[0]
    sourcePlacement = zone.chipPlacementSet.placementForChipOrNone_get(
        sourceChipRef
    )
    destinationPlacement = zone.chipPlacementSet.placementForChipOrNone_get(
        destinationChipRef
    )
    if sourcePlacement is None or destinationPlacement is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="inspect.zone_local.missing_local_chip_placement",
            message=(
                "Synthetic overlap zone is missing a selected chip placement"
            ),
            context=(
                sourceChipRef.chipId.moduleName,
                sourceChipRef.chipId.functionName,
                destinationChipRef.chipId.moduleName,
                destinationChipRef.chipId.functionName,
            ),
        )
        return resultErr_build()
    sourceDepth = callingStack.depthForChipOrNone_get(sourceChipRef)
    destinationDepth = callingStack.depthForChipOrNone_get(destinationChipRef)
    if sourceDepth is None or destinationDepth is None:
        return resultErr_build()
    depthDelta: int = destinationDepth - sourceDepth
    if depthDelta > 0:
        return resultOk_build(ZoneLocalGeometryKind.INTRA_PARENT_TOCHILD)
    if depthDelta < 0:
        return resultOk_build(ZoneLocalGeometryKind.OUTER_CHILD_TOPARENT)
    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    if sourceSide is RoutingZoneRegionSide.WEST:
        return resultOk_build(ZoneLocalGeometryKind.OUTER_PARENT_UTURN)
    return resultOk_build(ZoneLocalGeometryKind.OUTER_CHILD_UTURN)


def _zoneLocalBoardWorld_build(
    debugContext: SignalFlowContext,
) -> InspectBoardWorld:
    """Build board runtime state for one synthetic overlap zone."""

    from .kernel_runtime import _boardZoneRuntime_build

    zoneResult = debugContext.placedRoutingZoneGrid.zoneAtCoordResult_get(
        GridCoord(columnIndex=1, rowIndex=1)
    )
    if not result_isOkCheck(zoneResult):
        raise RuntimeError("Could not recover synthetic overlap zone")
    boardZone = _boardZoneRuntime_build(
        debugContext=debugContext,
        routingZoneId=zoneResult.value.routingZoneId,
    )
    zoneRawResult: Result[RoutingZone] = cast(
        Result[RoutingZone], boardZone.raw_get()
    )
    compatibilityZones: tuple[RoutingZone, ...]
    if result_isOkCheck(zoneRawResult):
        compatibilityZones = (zoneRawResult.value,)
    else:
        compatibilityZones = ()
    compatibilityPlacedGrid = RoutingZoneGrid(
        worldSense=debugContext.placedRoutingZoneGrid.worldSense,
        gridSize=debugContext.placedRoutingZoneGrid.gridSize,
        routingZoneSet=RoutingZoneSet(routingZones=compatibilityZones),
        moduleBoxPadding=debugContext.moduleBoundaryPadding_get(),
    )
    return InspectBoardWorld(
        boardZonesById={zoneResult.value.routingZoneId: boardZone},
        compatibilityPlacedGrid=compatibilityPlacedGrid,
    )
