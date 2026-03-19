"""Tests for the first zone-local routing solver."""
from __future__ import annotations

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipId,
    GridCoord,
    Result,
    RoutingZoneGrid,
    RoutingZoneLocalRouteSolveKind,
    RoutingZoneRoutePoint,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
    routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)


def zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
    documentDict: dict[str, object],
):
    """Build zone-local solved routes through the current pipeline."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(documentDict)
    assert result_isOkCheck(circuitDocumentResult)
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
        routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocumentResult.value,
            placedGridResult.value,
            routeObligationSetResult.value.callRouteObligationSet,
        )
    )


class TestZoneSolver:
    """Verification of the first zone-local solved-route layer."""

    def test_zone_solver_builds_straight_transverse_route(self) -> None:
        """Root-to-child within one zone should build a straight transverse path."""

        diagnosticStack.stack_clear()

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {
                            "module": "Worker.ts",
                            "func": "run()",
                            "calls": [],
                        }
                    ],
                }
            }
        )

        assert result_isOkCheck(routeSetResult)
        solvedRoute = routeSetResult.value.routingZoneLocalSolvedRoutes[0]
        assert (
            solvedRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.STRAIGHT_TRANSVERSE
        )
        assert solvedRoute.owningRoutingZoneId.id == GridCoord(1, 1)
        assert solvedRoute.routePoints == (
            RoutingZoneRoutePoint(2, 5),
            RoutingZoneRoutePoint(14, 5),
            RoutingZoneRoutePoint(15, 5),
            RoutingZoneRoutePoint(26, 5),
            RoutingZoneRoutePoint(27, 5),
            RoutingZoneRoutePoint(28, 5),
        )

    def test_zone_solver_builds_offset_transverse_route_for_lower_child(self) -> None:
        """Second child in the east band should force a row-offset local path."""

        diagnosticStack.stack_clear()

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {
                            "module": "A.ts",
                            "func": "a()",
                            "calls": [],
                        },
                        {
                            "module": "B.ts",
                            "func": "b()",
                            "calls": [],
                        },
                    ],
                }
            }
        )

        assert result_isOkCheck(routeSetResult)
        solvedRoute = routeSetResult.value.routingZoneLocalSolvedRoutes[1]
        assert solvedRoute.destinationChipRef.chipId == ChipId(
            moduleName="B.ts",
            functionName="b()",
        )
        assert solvedRoute.solveKind is RoutingZoneLocalRouteSolveKind.OFFSET_TRANSVERSE
        assert solvedRoute.routePoints == (
            RoutingZoneRoutePoint(2, 5),
            RoutingZoneRoutePoint(14, 5),
            RoutingZoneRoutePoint(15, 5),
            RoutingZoneRoutePoint(15, 6),
            RoutingZoneRoutePoint(26, 6),
            RoutingZoneRoutePoint(27, 6),
            RoutingZoneRoutePoint(28, 6),
        )

    def test_zone_solver_builds_same_side_local_self_route(self) -> None:
        """Recursive self-calls should solve to a same-side local loop."""

        diagnosticStack.stack_clear()

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "Loop.ts",
                    "func": "loop()",
                    "calls": [{"module": "Loop.ts", "func": "loop()"}],
                }
            }
        )

        assert result_isOkCheck(routeSetResult)
        solvedRoute = routeSetResult.value.routingZoneLocalSolvedRoutes[0]
        assert solvedRoute.sourceChipRef == solvedRoute.destinationChipRef
        assert solvedRoute.solveKind is RoutingZoneLocalRouteSolveKind.SAME_SIDE_LOCAL
        assert solvedRoute.routePoints == (
            RoutingZoneRoutePoint(2, 5),
            RoutingZoneRoutePoint(14, 5),
            RoutingZoneRoutePoint(15, 5),
            RoutingZoneRoutePoint(14, 5),
            RoutingZoneRoutePoint(2, 5),
        )
