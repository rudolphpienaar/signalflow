"""Inspect-context/build entry points and staged pipeline assembly."""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.config import SignalFlowConfig, configResult_build
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipInternalSolvedRouteSet,
    CircuitDocument,
    Result,
    RouteObligationSet,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneGridSolvedRouteSet,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneLocalSolvedRouteSet,
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

from .context import SignalFlowContext


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


def context_buildFromDocument(
    documentDict: dict[str, object],
) -> Result[SignalFlowContext]:
    """Build the full current inspect context for one source document."""

    diagnosticStack.stack_clear()

    artifactsResult = _debugBuildArtifactsResult_build(documentDict)
    if not result_isOkCheck(artifactsResult):
        return resultErr_build()
    artifacts = artifactsResult.value

    return resultOk_build(
        SignalFlowContext(
            documentDict=documentDict,
            circuitDocument=artifacts.circuitDocument,
            signalFlowConfig=artifacts.signalFlowConfig,
            routingZoneGrid=artifacts.routingZoneGrid,
            routingZoneAssignmentSet=artifacts.routingZoneAssignmentSet,
            placedRoutingZoneGrid=artifacts.placedRoutingZoneGrid,
            routeObligationSet=artifacts.routeObligationSet,
            chipInternalSolvedRouteSet=artifacts.chipInternalSolvedRouteSet,
            routingZoneLocalSolvedRouteSet=artifacts.routingZoneLocalSolvedRouteSet,
            routingZoneInterconnectSolvedRouteSet=(
                artifacts.routingZoneInterconnectSolvedRouteSet
            ),
            routingZoneGridSolvedRouteSet=artifacts.routingZoneGridSolvedRouteSet,
        )
    )


def _documentWithDefaultWorld_build(
    documentDict: dict[str, object],
) -> dict[str, object]:
    """Build effective debug document with default world config when absent."""

    if "world" in documentDict:
        return documentDict
    return {
        **documentDict,
        "world": {"sense": "west_to_east"},
    }


def _debugBuildArtifactsResult_build(
    documentDict: dict[str, object],
) -> Result[_InspectBuildArtifacts]:
    """Build the staged engine artifacts consumed by the inspect context."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
        documentDict
    )
    if not result_isOkCheck(circuitDocumentResult):
        return resultErr_build()
    circuitDocument = circuitDocumentResult.value

    signalFlowConfigResult = configResult_build(
        _documentWithDefaultWorld_build(documentDict),
        callingDepth=circuitDocument.callingDepth_calculate(),
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

    solvedRouteSetsResult = _debugSolvedRouteSetsResult_build(
        circuitDocument=circuitDocument,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        routeObligationSet=routeObligationSet,
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
            circuitDocument=circuitDocument,
            signalFlowConfig=signalFlowConfig,
            routingZoneGrid=routingZoneGrid,
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            routeObligationSet=routeObligationSet,
            chipInternalSolvedRouteSet=chipInternalSolvedRouteSet,
            routingZoneLocalSolvedRouteSet=routingZoneLocalSolvedRouteSet,
            routingZoneInterconnectSolvedRouteSet=(
                routingZoneInterconnectSolvedRouteSet
            ),
            routingZoneGridSolvedRouteSet=routingZoneGridSolvedRouteSet,
        )
    )


def _debugSolvedRouteSetsResult_build(
    *,
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    routeObligationSet: RouteObligationSet,
) -> Result[
    tuple[
        ChipInternalSolvedRouteSet,
        RoutingZoneLocalSolvedRouteSet,
        RoutingZoneInterconnectSolvedRouteSet,
        RoutingZoneGridSolvedRouteSet,
    ]
]:
    """Build the solved route layers used by the debugger."""

    chipInternalSolvedRouteSetResult = (
        chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet(
            circuitDocument,
            routeObligationSet.chipInternalRouteObligationSet,
        )
    )
    if not result_isOkCheck(chipInternalSolvedRouteSetResult):
        return resultErr_build()

    routingZoneLocalSolvedRouteSetResult = (
        routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocument,
            placedRoutingZoneGrid,
            routeObligationSet.callRouteObligationSet,
        )
    )
    if not result_isOkCheck(routingZoneLocalSolvedRouteSetResult):
        return resultErr_build()

    routingZoneInterconnectSolvedRouteSetResult = (
        routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocument,
            placedRoutingZoneGrid,
            routeObligationSet.callRouteObligationSet,
        )
    )
    if not result_isOkCheck(routingZoneInterconnectSolvedRouteSetResult):
        return resultErr_build()

    routingZoneGridSolvedRouteSetResult = (
        routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocument,
            placedRoutingZoneGrid,
            routeObligationSet.callRouteObligationSet,
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
