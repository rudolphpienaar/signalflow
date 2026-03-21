"""Tests for the first zone-local routing solver."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipId,
    GridCoord,
    Result,
    RoutingZoneGrid,
    RoutingZoneLocalRouteSolveKind,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
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


def _routeColumnSeq(route) -> tuple[int, ...]:
    return tuple(point.horizontalIndex for point in route.routePoints)


def _routeRowSeq(route) -> tuple[int, ...]:
    return tuple(point.verticalIndex for point in route.routePoints)


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
                    "output_ports": [{"signal": "query", "return": "result"}],
                    "calls": [
                        {
                            "module": "Worker.ts",
                            "func": "run()",
                            "input_ports": [
                                {"signal": "query", "return": "result"}
                            ],
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
        fwdCols = _routeColumnSeq(fwdRoute)
        fwdRows = _routeRowSeq(fwdRoute)
        assert len(fwdRoute.routePoints) == 6
        assert fwdCols[0] < fwdCols[1] == fwdCols[2]
        assert fwdCols[2] < fwdCols[3] == fwdCols[4] < fwdCols[5]
        assert fwdRows[0] == fwdRows[1]
        assert fwdRows[4] == fwdRows[5]
        assert fwdRows[2] == fwdRows[3]
        assert fwdRows[2] <= fwdRows[0]
        retRoute = routes[1]
        assert (
            retRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        )
        retCols = _routeColumnSeq(retRoute)
        retRows = _routeRowSeq(retRoute)
        assert len(retRoute.routePoints) == 6
        assert retCols[0] > retCols[1] == retCols[2]
        assert retCols[2] > retCols[3] == retCols[4] > retCols[5]
        assert retRows[0] == retRows[1]
        assert retRows[4] == retRows[5]
        assert retRows[2] == retRows[3]
        assert retRows[2] >= retRows[0]

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
                    "output_ports": [
                        {"signal": "a", "return": "ra"},
                        {"signal": "b", "return": "rb"},
                    ],
                    "calls": [
                        {
                            "module": "A.ts",
                            "func": "a()",
                            "input_ports": [{"signal": "a", "return": "ra"}],
                            "calls": [],
                        },
                        {
                            "module": "B.ts",
                            "func": "b()",
                            "input_ports": [{"signal": "b", "return": "rb"}],
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
        aFwdRoute = routes[0]
        aFwdCols = _routeColumnSeq(aFwdRoute)
        aFwdRows = _routeRowSeq(aFwdRoute)
        bFwdCols = _routeColumnSeq(bFwdRoute)
        bFwdRows = _routeRowSeq(bFwdRoute)
        assert len(bFwdRoute.routePoints) == 6
        assert bFwdCols[1] > aFwdCols[1]
        assert bFwdCols[3] < aFwdCols[3]
        assert bFwdRows[2] < aFwdRows[2]
        assert bFwdRows[4] > aFwdRows[4]
        bRetRoute = routes[3]
        assert bRetRoute.sourceChipRef.chipId == ChipId(
            moduleName="B.ts",
            functionName="b()",
        )
        assert (
            bRetRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        )
        aRetRoute = routes[2]
        aRetCols = _routeColumnSeq(aRetRoute)
        aRetRows = _routeRowSeq(aRetRoute)
        bRetCols = _routeColumnSeq(bRetRoute)
        bRetRows = _routeRowSeq(bRetRoute)
        assert len(bRetRoute.routePoints) == 6
        assert bRetCols[1] < aRetCols[1]
        assert bRetCols[3] > aRetCols[3]
        assert bRetRows[2] > aRetRows[2]
        assert bRetRows[4] >= aRetRows[4]

    def test_zone_solver_builds_same_side_local_self_route(self) -> None:
        """Recursive self-calls should solve to a same-side local loop."""

        diagnosticStack.stack_clear()

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "Loop.ts",
                    "func": "loop()",
                    "input_ports": [{"signal": "tick", "return": "tock"}],
                    "output_ports": [{"signal": "tick", "return": "tock"}],
                    "calls": [{"module": "Loop.ts", "func": "loop()"}],
                }
            }
        )

        assert result_isOkCheck(routeSetResult)
        solvedRoute = routeSetResult.value.routingZoneLocalSolvedRoutes[0]
        assert solvedRoute.sourceChipRef == solvedRoute.destinationChipRef
        assert solvedRoute.solveKind is RoutingZoneLocalRouteSolveKind.SAME_SIDE_LOCAL
        loopCols = _routeColumnSeq(solvedRoute)
        loopRows = _routeRowSeq(solvedRoute)
        assert len(solvedRoute.routePoints) == 5
        assert loopRows.count(loopRows[0]) == len(loopRows)
        assert loopCols[0] == loopCols[-1]
        assert loopCols[1] == loopCols[3]
        assert loopCols[2] > loopCols[1] > loopCols[0]

    def test_zone_solver_builds_inter_perimeter_backedge_route(
        self,
    ) -> None:
        """Ancestor backedges should use INTER perimeter regions, not INTRA."""

        diagnosticStack.stack_clear()
        fixturePath = (
            Path(__file__).parent.parent
            / "examples"
            / "simple-circuit"
            / "rearch-external-backedge.yaml"
        )
        documentDict = yaml.safe_load(fixturePath.read_text(encoding="utf-8"))

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(routeSetResult)
        routes = routeSetResult.value.routingZoneLocalSolvedRoutes
        forwardRoute = routes[0]
        backedgeRoute = routes[1]
        assert (
            forwardRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        )
        assert (
            backedgeRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        )
        assert (
            routes[3].solveKind
            is RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
        )
        assert forwardRoute.routePoints != backedgeRoute.routePoints
        assert min(point.verticalIndex for point in backedgeRoute.routePoints) == 0
        assert (
            max(point.verticalIndex for point in routes[3].routePoints)
            > max(point.verticalIndex for point in forwardRoute.routePoints)
        )
        assert tuple(
            regionId.routingZoneRegionKind
            for regionId in backedgeRoute.traversedRegionIds
        ) == (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.CHIP_TERMINAL,
        )
        assert tuple(
            regionId.routingZoneRegionSide
            for regionId in backedgeRoute.traversedRegionIds
        ) == (
            RoutingZoneRegionSide.EAST,
            RoutingZoneRegionSide.EAST,
            RoutingZoneRegionSide.EAST,
            RoutingZoneRegionSide.NORTH,
            RoutingZoneRegionSide.WEST,
            RoutingZoneRegionSide.WEST,
            RoutingZoneRegionSide.WEST,
        )
