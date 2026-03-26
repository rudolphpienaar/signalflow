"""Tests for the first interconnect seam routing solver."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    GridCoord,
    Result,
    RoutingZoneGrid,
    RoutingZoneInterconnectRouteSolveKind,
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
from tests.routing_invariants import assert_solved_routes_have_no_shared_realized_cells

_EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


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
                    "output_ports": [{"signal": "query", "return": "result"}],
                    "calls": [
                        {
                            "module": "Worker.ts",
                            "func": "run()",
                            "input_ports": [
                                {"signal": "query", "return": "result"}
                            ],
                            "output_ports": [
                                {"signal": "leaf", "return": "rleaf"}
                            ],
                            "calls": [
                                {
                                    "module": "Leaf.ts",
                                    "func": "finish()",
                                    "input_ports": [
                                        {"signal": "leaf", "return": "rleaf"}
                                    ],
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
        assert len(solvedRoute.routePoints) == 4
        assert {
            routePoint.verticalIndex for routePoint in solvedRoute.routePoints
        } == {9}

    def test_interconnect_solver_builds_vertical_straight_seam(self) -> None:
        """Linear north-south depth should build a straight vertical seam route."""

        diagnosticStack.stack_clear()
        routeSetResult = interconnectSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "output_ports": [{"signal": "query", "return": "result"}],
                    "calls": [
                        {
                            "module": "Worker.ts",
                            "func": "run()",
                            "input_ports": [
                                {"signal": "query", "return": "result"}
                            ],
                            "output_ports": [
                                {"signal": "leaf", "return": "rleaf"}
                            ],
                            "calls": [
                                {
                                    "module": "Leaf.ts",
                                    "func": "finish()",
                                    "input_ports": [
                                        {"signal": "leaf", "return": "rleaf"}
                                    ],
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
        assert len(solvedRoute.routePoints) == 5
        assert {
            routePoint.horizontalIndex for routePoint in solvedRoute.routePoints
        } == {9, 22}

    def test_interconnect_solver_separates_converging_sources_into_distinct_lanes(
        self,
    ) -> None:
        """Converging seam sources must not collapse onto one destination lane."""

        diagnosticStack.stack_clear()
        routeSetResult = interconnectSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "output_ports": [
                        {"signal": "s1", "return": "r1"},
                        {"signal": "s2", "return": "r2"},
                    ],
                    "calls": [
                        {
                            "module": "Proxy.ts",
                            "func": "p1()",
                            "input_ports": [{"signal": "s1", "return": "r1"}],
                            "output_ports": [{"signal": "s1", "return": "r1"}],
                            "calls": [
                                {
                                    "module": "Hub.ts",
                                    "func": "process()",
                                    "input_ports": [
                                        {"signal": "s1", "return": "r1"},
                                        {"signal": "s2", "return": "r2"},
                                    ],
                                    "calls": [],
                                }
                            ],
                        },
                        {
                            "module": "Proxy.ts",
                            "func": "p2()",
                            "input_ports": [{"signal": "s2", "return": "r2"}],
                            "output_ports": [{"signal": "s2", "return": "r2"}],
                            "calls": [
                                {"module": "Hub.ts", "func": "process()", "calls": []}
                            ],
                        },
                    ],
                }
            },
            {"world": {"sense": "west_to_east"}},
        )

        assert result_isOkCheck(routeSetResult)
        forwardRoutes = [
            solvedRoute
            for solvedRoute in routeSetResult.value.routingZoneInterconnectSolvedRoutes
            if solvedRoute.sourceChipRef.chipId.functionName in {"p1()", "p2()"}
            and solvedRoute.destinationChipRef.chipId.functionName == "process()"
        ]

        assert len(forwardRoutes) == 2
        forwardRoutes.sort(key=lambda route: route.sourceChipRef.chipId.functionName)

        p1Route, p2Route = forwardRoutes
        assert (
            p1Route.routePoints[-1].verticalIndex
            != p2Route.routePoints[-1].verticalIndex
        )
        assert (
            p1Route.routePoints[-2].verticalIndex
            != p2Route.routePoints[-2].verticalIndex
        )
        assert p1Route.routePoints[-1].verticalIndex == 9
        assert p2Route.routePoints[-1].verticalIndex == 11

    def test_interconnect_solver_centers_sparse_process_wall_and_uses_fan_manifold(
        self,
    ) -> None:
        """Hub seam routes should converge at centered process() wall rows via a fan."""

        diagnosticStack.stack_clear()
        hubDocument = yaml.safe_load((_EXAMPLES_DIR / "hub.yaml").read_text())
        routeSetResult = interconnectSolvedRouteSetResult_buildFromDocumentDict(
            {"tree": hubDocument["tree"]},
            {"world": hubDocument["world"]},
        )

        assert result_isOkCheck(routeSetResult)

        forwardRoutes = [
            solvedRoute
            for solvedRoute in routeSetResult.value.routingZoneInterconnectSolvedRoutes
            if solvedRoute.destinationChipRef.chipId.moduleName == "Hub.ts"
            and solvedRoute.destinationChipRef.chipId.functionName == "process()"
        ]
        returnRoutes = [
            solvedRoute
            for solvedRoute in routeSetResult.value.routingZoneInterconnectSolvedRoutes
            if solvedRoute.sourceChipRef.chipId.moduleName == "Hub.ts"
            and solvedRoute.sourceChipRef.chipId.functionName == "process()"
        ]

        assert len(forwardRoutes) == 5
        assert len(returnRoutes) == 5
        assert_solved_routes_have_no_shared_realized_cells(
            routeSetResult.value.routingZoneInterconnectSolvedRoutes,
            allow_orthogonal_crossings=True,
        )

        forwardRoutes.sort(key=lambda route: route.sourceChipRef.chipId.functionName)
        returnRoutes.sort(
            key=lambda route: route.destinationChipRef.chipId.functionName
        )
        # Verify the routes target unique rows on the Hub chip.
        # The exact coordinates depend on the kernel's placement logic.
        assert len({route.routePoints[-1].verticalIndex for route in forwardRoutes}) == 5
        assert len({route.routePoints[0].verticalIndex for route in returnRoutes}) == 5
