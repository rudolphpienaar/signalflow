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

    def test_zone_solver_builds_clockwise_intra_forward_route(self) -> None:
        """Root-to-child produces a clockwise INTRA forward route (top half)."""

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
        routes = routeSetResult.value.routingZoneLocalSolvedRoutes
        fwdRoute = routes[0]
        assert fwdRoute.owningRoutingZoneId.id == GridCoord(1, 1)
        assert (
            fwdRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        )
        assert fwdRoute.routePoints == (
            RoutingZoneRoutePoint(14, 9),
            RoutingZoneRoutePoint(15, 9),
            RoutingZoneRoutePoint(15, 9),
            RoutingZoneRoutePoint(26, 9),
            RoutingZoneRoutePoint(26, 9),
            RoutingZoneRoutePoint(27, 9),
        )
        retRoute = routes[1]
        assert (
            retRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        )
        assert retRoute.routePoints == (
            RoutingZoneRoutePoint(27, 10),
            RoutingZoneRoutePoint(26, 10),
            RoutingZoneRoutePoint(26, 10),
            RoutingZoneRoutePoint(15, 10),
            RoutingZoneRoutePoint(15, 10),
            RoutingZoneRoutePoint(14, 10),
        )

    def test_zone_solver_builds_clockwise_intra_forward_route_for_second_child(
        self,
    ) -> None:
        """Second child uses lane 1 — one step inward in the concentric rectangle."""

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
        routes = routeSetResult.value.routingZoneLocalSolvedRoutes
        # Forwards first (indices 0 and 1), then returns (indices 2 and 3).
        bFwdRoute = routes[1]
        assert bFwdRoute.destinationChipRef.chipId == ChipId(
            moduleName="B.ts",
            functionName="b()",
        )
        assert (
            bFwdRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        )
        assert bFwdRoute.routePoints == (
            RoutingZoneRoutePoint(14, 11),
            RoutingZoneRoutePoint(16, 11),
            RoutingZoneRoutePoint(16, 10),
            RoutingZoneRoutePoint(25, 10),
            RoutingZoneRoutePoint(25, 14),
            RoutingZoneRoutePoint(27, 14),
        )
        bRetRoute = routes[3]
        assert bRetRoute.sourceChipRef.chipId == ChipId(
            moduleName="B.ts",
            functionName="b()",
        )
        assert (
            bRetRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        )
        assert bRetRoute.routePoints == (
            RoutingZoneRoutePoint(27, 15),
            RoutingZoneRoutePoint(25, 15),
            RoutingZoneRoutePoint(25, 13),
            RoutingZoneRoutePoint(16, 13),
            RoutingZoneRoutePoint(16, 12),
            RoutingZoneRoutePoint(14, 12),
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
            RoutingZoneRoutePoint(2, 9),
            RoutingZoneRoutePoint(14, 9),
            RoutingZoneRoutePoint(15, 9),
            RoutingZoneRoutePoint(14, 9),
            RoutingZoneRoutePoint(2, 9),
        )
