"""Tests for the first interconnect seam routing solver."""
from __future__ import annotations

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    GridCoord,
    Result,
    RoutingZoneGrid,
    RoutingZoneInterconnectRouteSolveKind,
    RoutingZoneRoutePoint,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
    routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)


def interconnectSolvedRouteSetResult_buildFromDocumentDict(
    documentDict: dict[str, object],
    worldDocumentDict: dict[str, object],
):
    """Build seam solved routes through the current pipeline."""

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
    return (
        routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocumentResult.value,
            placedGridResult.value,
            routeObligationSetResult.value.callRouteObligationSet,
        )
    )


class TestInterconnectSolver:
    """Verification of the first seam-solving layer."""

    def test_interconnect_solver_builds_horizontal_straight_seam(self) -> None:
        """Linear west-east depth should build a straight seam route."""

        diagnosticStack.stack_clear()
        routeSetResult = interconnectSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {
                            "module": "Worker.ts",
                            "func": "run()",
                            "calls": [
                                {
                                    "module": "Leaf.ts",
                                    "func": "finish()",
                                    "calls": [],
                                }
                            ],
                        }
                    ],
                }
            },
            {"world": {"sense": "west_to_east"}},
        )

        assert result_isOkCheck(routeSetResult)
        solvedRoute = routeSetResult.value.routingZoneInterconnectSolvedRoutes[0]
        assert (
            solvedRoute.solveKind
            is RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM
        )
        assert solvedRoute.routingZoneInterconnectId.sourceZoneId.id == GridCoord(1, 1)
        assert solvedRoute.routingZoneInterconnectId.destinationZoneId.id == GridCoord(
            2,
            1,
        )
        assert solvedRoute.routePoints == (
            RoutingZoneRoutePoint(40, 5),
            RoutingZoneRoutePoint(42, 5),
            RoutingZoneRoutePoint(44, 5),
        )

    def test_interconnect_solver_builds_vertical_straight_seam(self) -> None:
        """Linear north-south depth should build a straight vertical seam route."""

        diagnosticStack.stack_clear()
        routeSetResult = interconnectSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {
                            "module": "Worker.ts",
                            "func": "run()",
                            "calls": [
                                {
                                    "module": "Leaf.ts",
                                    "func": "finish()",
                                    "calls": [],
                                }
                            ],
                        }
                    ],
                }
            },
            {"world": {"sense": "north_to_south"}},
        )

        assert result_isOkCheck(routeSetResult)
        solvedRoute = routeSetResult.value.routingZoneInterconnectSolvedRoutes[0]
        assert (
            solvedRoute.solveKind
            is RoutingZoneInterconnectRouteSolveKind.STRAIGHT_SEAM
        )
        assert solvedRoute.routingZoneInterconnectId.sourceZoneId.id == GridCoord(1, 1)
        assert solvedRoute.routingZoneInterconnectId.destinationZoneId.id == GridCoord(
            1,
            2,
        )
        assert solvedRoute.routePoints == (
            RoutingZoneRoutePoint(5, 22),
            RoutingZoneRoutePoint(5, 24),
            RoutingZoneRoutePoint(5, 26),
        )
