"""Tests for the first grid-level long-haul routing solver."""
from __future__ import annotations

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    GridCoord,
    Result,
    RouteObligationScope,
    RoutingZoneGrid,
    RoutingZoneGridRouteSolveKind,
    RoutingZoneRoutePoint,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
    routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)


def gridSolvedRouteSetResult_buildFromDocumentDict(
    documentDict: dict[str, object],
    worldDocumentDict: dict[str, object],
):
    """Build grid-level solved routes through the current pipeline."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(documentDict)
    assert result_isOkCheck(circuitDocumentResult)
    signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
        worldDocumentDict,
        callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
    )
    assert result_isOkCheck(signalFlowConfigResult)
    routingZoneGridResult: Result[RoutingZoneGrid] = (
        routingZoneGridResult_buildFromSignalFlowConfig(signalFlowConfigResult.value)
    )
    assert result_isOkCheck(routingZoneGridResult)
    assignmentSetResult = (
        routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
            circuitDocumentResult.value,
            routingZoneGridResult.value,
        )
    )
    assert result_isOkCheck(assignmentSetResult)
    placedGridResult = routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
        assignmentSetResult.value,
        routingZoneGridResult.value,
        circuitDocumentResult.value,
    )
    assert result_isOkCheck(placedGridResult)
    routeObligationSetResult = (
        routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
            circuitDocumentResult.value,
            placedGridResult.value,
        )
    )
    assert result_isOkCheck(routeObligationSetResult)
    return routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations(
        circuitDocumentResult.value,
        placedGridResult.value,
        routeObligationSetResult.value.callRouteObligationSet,
    )


class TestGridSolver:
    """Verification of the first world-scale long-haul solver."""

    def test_grid_solver_builds_horizontal_linear_long_haul_route(self) -> None:
        """Five-layer depth with a root backedge should build one long-haul path."""

        diagnosticStack.stack_clear()
        documentDict = {
            "tree": {
                "module": "Root.ts",
                "func": "root()",
                "calls": [
                    {
                        "module": "A.ts",
                        "func": "a()",
                        "calls": [
                            {
                                "module": "B.ts",
                                "func": "b()",
                                "calls": [
                                    {
                                        "module": "C.ts",
                                        "func": "c()",
                                        "calls": [
                                            {
                                                "module": "D.ts",
                                                "func": "d()",
                                                "calls": [
                                                    {
                                                        "module": "Root.ts",
                                                        "func": "root()",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        }

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(circuitDocumentResult)
        assert circuitDocumentResult.value.callingDepth_calculate() == 5

        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "west_to_east"}},
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromSignalFlowConfig(signalFlowConfigResult.value)
        )
        assert result_isOkCheck(routingZoneGridResult)
        assignmentSetResult = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)
        placedGridResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                assignmentSetResult.value,
                routingZoneGridResult.value,
                circuitDocumentResult.value,
            )
        )
        assert result_isOkCheck(placedGridResult)
        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocumentResult.value,
                placedGridResult.value,
            )
        )
        assert result_isOkCheck(routeObligationSetResult)
        scopes = tuple(
            obligation.routeObligationScope
            for obligation in (
                routeObligationSetResult.value.callRouteObligationSet
                .callRouteObligations
            )
        )
        assert RouteObligationScope.GRID_LONG_HAUL in scopes

        solvedRouteSetResult = (
            routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations(
                circuitDocumentResult.value,
                placedGridResult.value,
                routeObligationSetResult.value.callRouteObligationSet,
            )
        )

        assert result_isOkCheck(solvedRouteSetResult)
        solvedRoute = solvedRouteSetResult.value.routingZoneGridSolvedRoutes[0]
        assert (
            solvedRoute.solveKind
            is RoutingZoneGridRouteSolveKind.LINEAR_HORIZONTAL
        )
        zone31Result = routingZoneGridResult.value.zoneAtCoordResult_get(
            GridCoord(3, 1)
        )
        zone21Result = routingZoneGridResult.value.zoneAtCoordResult_get(
            GridCoord(2, 1)
        )
        zone11Result = routingZoneGridResult.value.zoneAtCoordResult_get(
            GridCoord(1, 1)
        )
        assert result_isOkCheck(zone31Result)
        assert result_isOkCheck(zone21Result)
        assert result_isOkCheck(zone11Result)
        assert solvedRoute.routingZonePath.zoneIds == (
            zone31Result.value.routingZoneId,
            zone21Result.value.routingZoneId,
            zone11Result.value.routingZoneId,
        )
        assert solvedRoute.routePoints == (
            RoutingZoneRoutePoint(87, 5),
            RoutingZoneRoutePoint(85, 5),
            RoutingZoneRoutePoint(83, 5),
            RoutingZoneRoutePoint(43, 5),
            RoutingZoneRoutePoint(42, 5),
            RoutingZoneRoutePoint(40, 5),
        )
