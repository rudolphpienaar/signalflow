"""Inspect-context/build entry points and staged pipeline assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from signalflow.config import SignalFlowConfig, configResult_build
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipInternalSolvedRouteSet,
    CircuitDocument,
    Result,
    RouteObligationSet,
    RoutingZone,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneGridSolvedRouteSet,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneSet,
    callingStackResult_buildFromCircuitDocument,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.diagnostics import diagnosticStack
from signalflow.routing import (
    chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet,
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
    routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations,
    routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations,
    routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)

from .context import (
    InspectBoardWorld,
    InspectStagedWorld,
    SignalFlowContext,
)


@dataclass(frozen=True)
class _InspectBuildArtifacts:
    """Intermediate inspect-pipeline artifacts before the context wrapper."""

    circuitDocument: CircuitDocument
    signalFlowConfig: SignalFlowConfig
    routingZoneGrid: RoutingZoneGrid
    routingZoneAssignmentSet: RoutingZoneAssignmentSet
    placedRoutingZoneGrid: RoutingZoneGrid
    routeObligationSet: RouteObligationSet
    chipInternalSolvedRouteSet: ChipInternalSolvedRouteSet
    routingZoneLocalSolvedRouteSet: RoutingZoneLocalSolvedRouteSet
    routingZoneInterconnectSolvedRouteSet: (
        RoutingZoneInterconnectSolvedRouteSet
    )
    routingZoneGridSolvedRouteSet: RoutingZoneGridSolvedRouteSet

    def chipInternalRouteObligationSet_get(self):
        return self.routeObligationSet.chipInternalRouteObligationSet

    def callRouteObligationSet_get(self):
        return self.routeObligationSet.callRouteObligationSet

    def placedGrid_get(self) -> RoutingZoneGrid:
        return self.placedRoutingZoneGrid


def context_buildFromDocument(
    documentDict: dict[str, object],
) -> Result[SignalFlowContext]:
    """Build the full current inspect context for one source document."""

    diagnosticStack.stack_clear()

    artifactsResult = _inspectBuildArtifactsResult_build(documentDict)
    if not result_isOkCheck(artifactsResult):
        return resultErr_build()
    artifacts = artifactsResult.value

    return resultOk_build(
        _inspectContext_build(
            documentDict=documentDict,
            circuitDocument=artifacts.circuitDocument,
            signalFlowConfig=artifacts.signalFlowConfig,
            artifacts=artifacts,
        )
    )


def _inspectContext_build(
    *,
    documentDict: dict[str, object],
    circuitDocument: CircuitDocument,
    signalFlowConfig: SignalFlowConfig,
    artifacts: _InspectBuildArtifacts,
) -> SignalFlowContext:
    stagedWorld = InspectStagedWorld(
        routingZoneGrid=artifacts.routingZoneGrid,
        routingZoneAssignmentSet=artifacts.routingZoneAssignmentSet,
        placedRoutingZoneGrid=artifacts.placedRoutingZoneGrid,
        routeObligationSet=artifacts.routeObligationSet,
        chipInternalSolvedRouteSet=artifacts.chipInternalSolvedRouteSet,
        routingZoneLocalSolvedRouteSet=(
            artifacts.routingZoneLocalSolvedRouteSet
        ),
        routingZoneInterconnectSolvedRouteSet=(
            artifacts.routingZoneInterconnectSolvedRouteSet
        ),
        routingZoneGridSolvedRouteSet=artifacts.routingZoneGridSolvedRouteSet,
    )
    baseContext = SignalFlowContext(
        documentDict=documentDict,
        circuitDocument=circuitDocument,
        signalFlowConfig=signalFlowConfig,
        stagedWorld=stagedWorld,
        boardWorld=InspectBoardWorld(
            boardZonesById={},
            compatibilityPlacedGrid=artifacts.placedRoutingZoneGrid,
        ),
    )
    return SignalFlowContext(
        documentDict=baseContext.documentDict,
        circuitDocument=baseContext.circuitDocument,
        signalFlowConfig=baseContext.signalFlowConfig,
        stagedWorld=baseContext.stagedWorld,
        boardWorld=_inspectBoardWorld_build(baseContext),
    )


def _inspectBoardWorld_build(
    debugContext: SignalFlowContext,
) -> InspectBoardWorld:
    from .kernel_runtime import _boardZoneRuntime_build

    compatibilityZonesMutable = []
    boardZonesById = {
        routingZone.routingZoneId: _boardZoneRuntime_build(
            debugContext=debugContext,
            routingZoneId=routingZone.routingZoneId,
        )
        for routingZone in (
            debugContext.routingZoneGrid.routingZoneSet.routingZones
        )
    }
    for boardZone in boardZonesById.values():
        zoneResult = cast(Result[RoutingZone], boardZone.raw_get())
        if result_isOkCheck(zoneResult):
            compatibilityZonesMutable.append(zoneResult.value)
    compatibilityPlacedGrid = RoutingZoneGrid(
        worldSense=debugContext.routingZoneGrid.worldSense,
        gridSize=debugContext.routingZoneGrid.gridSize,
        routingZoneSet=RoutingZoneSet(
            routingZones=tuple(compatibilityZonesMutable)
        ),
        moduleBoxPadding=debugContext.moduleBoundaryPadding_get(),
    )
    return InspectBoardWorld(
        boardZonesById=boardZonesById,
        compatibilityPlacedGrid=compatibilityPlacedGrid,
    )


def _documentWithDefaultWorld_build(
    documentDict: dict[str, object],
) -> dict[str, object]:
    """Return document unchanged; raise if world: block is absent."""

    if "world" not in documentDict:
        raise ValueError(
            "Document missing required 'world:' block. "
            "tree:-only circuits use the deprecated engine "
            "and are not supported."
        )
    return documentDict


def _inspectBuildArtifactsResult_build(
    documentDict: dict[str, object],
) -> Result[_InspectBuildArtifacts]:
    """Build the staged engine artifacts consumed by the inspect context."""

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

    signalFlowConfigResult = configResult_build(
        _documentWithDefaultWorld_build(documentDict),
        callingDepth=callingStackResult.value.bandCount_calculate(),
    )
    if not result_isOkCheck(signalFlowConfigResult):
        return resultErr_build()
    signalFlowConfig = signalFlowConfigResult.value

    routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
        signalFlowConfig
    )
    if not result_isOkCheck(routingZoneGridResult):
        return resultErr_build()
    routingZoneGrid = routingZoneGridResult.value

    routingZoneAssignmentSetResult = (
        routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
            circuitDocument,
            routingZoneGrid,
        )
    )
    if not result_isOkCheck(routingZoneAssignmentSetResult):
        return resultErr_build()
    routingZoneAssignmentSet = routingZoneAssignmentSetResult.value

    placedRoutingZoneGridResult = (
        routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
            routingZoneAssignmentSet,
            routingZoneGrid,
            circuitDocument,
        )
    )
    if not result_isOkCheck(placedRoutingZoneGridResult):
        return resultErr_build()
    placedRoutingZoneGrid = placedRoutingZoneGridResult.value

    routeObligationSetResult = (
        routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
            circuitDocument,
            placedRoutingZoneGrid,
        )
    )
    if not result_isOkCheck(routeObligationSetResult):
        return resultErr_build()
    routeObligationSet = routeObligationSetResult.value

    artifacts = _InspectBuildArtifacts(
        circuitDocument=circuitDocument,
        signalFlowConfig=signalFlowConfig,
        routingZoneGrid=routingZoneGrid,
        routingZoneAssignmentSet=routingZoneAssignmentSet,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        routeObligationSet=routeObligationSet,
        chipInternalSolvedRouteSet=ChipInternalSolvedRouteSet(
            chipInternalSolvedRoutes=()
        ),
        routingZoneLocalSolvedRouteSet=RoutingZoneLocalSolvedRouteSet(
            routingZoneLocalSolvedRoutes=()
        ),
        routingZoneInterconnectSolvedRouteSet=(
            RoutingZoneInterconnectSolvedRouteSet(
                routingZoneInterconnectSolvedRoutes=()
            )
        ),
        routingZoneGridSolvedRouteSet=RoutingZoneGridSolvedRouteSet(
            routingZoneGridSolvedRoutes=()
        ),
    )

    solvedRouteSetsResult = _inspectSolvedRouteSetsResult_build(
        artifacts=artifacts
    )
    if not result_isOkCheck(solvedRouteSetsResult):
        return resultErr_build()
    (
        chipInternalSolvedRouteSet,
        routingZoneLocalSolvedRouteSet,
        routingZoneInterconnectSolvedRouteSet,
        routingZoneGridSolvedRouteSet,
    ) = solvedRouteSetsResult.value

    return resultOk_build(
        _InspectBuildArtifacts(
            circuitDocument=artifacts.circuitDocument,
            signalFlowConfig=artifacts.signalFlowConfig,
            routingZoneGrid=artifacts.routingZoneGrid,
            routingZoneAssignmentSet=artifacts.routingZoneAssignmentSet,
            placedRoutingZoneGrid=artifacts.placedRoutingZoneGrid,
            routeObligationSet=artifacts.routeObligationSet,
            chipInternalSolvedRouteSet=chipInternalSolvedRouteSet,
            routingZoneLocalSolvedRouteSet=routingZoneLocalSolvedRouteSet,
            routingZoneInterconnectSolvedRouteSet=(
                routingZoneInterconnectSolvedRouteSet
            ),
            routingZoneGridSolvedRouteSet=routingZoneGridSolvedRouteSet,
        )
    )


def _inspectSolvedRouteSetsResult_build(
    *,
    artifacts: _InspectBuildArtifacts,
) -> Result[
    tuple[
        ChipInternalSolvedRouteSet,
        RoutingZoneLocalSolvedRouteSet,
        RoutingZoneInterconnectSolvedRouteSet,
        RoutingZoneGridSolvedRouteSet,
    ]
]:
    """Build the solved route layers used by the inspect surface."""

    chipInternalSolvedRouteSetResult = (
        chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet(
            artifacts.circuitDocument,
            artifacts.chipInternalRouteObligationSet_get(),
        )
    )
    if not result_isOkCheck(chipInternalSolvedRouteSetResult):
        return resultErr_build()

    routingZoneLocalSolvedRouteSetResult = (
        routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            artifacts.circuitDocument,
            artifacts.placedGrid_get(),
            artifacts.callRouteObligationSet_get(),
        )
    )
    if not result_isOkCheck(routingZoneLocalSolvedRouteSetResult):
        return resultErr_build()

    routingZoneInterconnectSolvedRouteSetResult = (
        routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            artifacts.circuitDocument,
            artifacts.placedGrid_get(),
            artifacts.callRouteObligationSet_get(),
        )
    )
    if not result_isOkCheck(routingZoneInterconnectSolvedRouteSetResult):
        return resultErr_build()

    routingZoneGridSolvedRouteSetResult = (
        routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            artifacts.circuitDocument,
            artifacts.placedGrid_get(),
            artifacts.callRouteObligationSet_get(),
        )
    )
    if not result_isOkCheck(routingZoneGridSolvedRouteSetResult):
        return resultErr_build()

    return resultOk_build(
        (
            chipInternalSolvedRouteSetResult.value,
            routingZoneLocalSolvedRouteSetResult.value,
            routingZoneInterconnectSolvedRouteSetResult.value,
            routingZoneGridSolvedRouteSetResult.value,
        )
    )


__all__: list[str] = [
    "SignalFlowContext",
    "context_buildFromDocument",
]
