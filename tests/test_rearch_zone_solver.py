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
    TrackDirection,
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routePoints_realize,
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


def _localRoutingPipelineArtifacts_buildFromDocumentDict(
    documentDict: dict[str, object],
) -> tuple[RoutingZoneGrid, object]:
    """Build placed grid plus zone-local solved routes through the current pipeline."""

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
    routeSetResult = (
        routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocumentResult.value,
            placedGridResult.value,
            routeObligationSetResult.value.callRouteObligationSet,
        )
    )
    assert result_isOkCheck(routeSetResult)
    return placedGridResult.value, routeSetResult.value


def _routeColumnSeq(route) -> tuple[int, ...]:
    return tuple(point.horizontalIndex for point in route.routePoints)


def _routeRowSeq(route) -> tuple[int, ...]:
    return tuple(point.verticalIndex for point in route.routePoints)


def _dirsAreHorizontal(directions: frozenset[TrackDirection]) -> bool:
    return directions <= {TrackDirection.EAST, TrackDirection.WEST}


def _dirsAreVertical(directions: frozenset[TrackDirection]) -> bool:
    return directions <= {TrackDirection.NORTH, TrackDirection.SOUTH}


def _regionFrameContainsCell_check(
    regionFrame,
    *,
    worldRow: int,
    worldCol: int,
) -> bool:
    return (
        regionFrame.horizontalStart
        <= worldCol
        < regionFrame.horizontalEnd_calculate()
        and regionFrame.verticalStart
        <= worldRow
        < regionFrame.verticalEnd_calculate()
    )


def _assert_routes_have_no_illegal_cell_coincidence(routes) -> None:
    """Assert distinct routes do not illegally coincide on realized cells."""

    occupiedDirectionsByCell: dict[
        tuple[int, int],
        frozenset[TrackDirection],
    ] = {}
    routesInOrder = sorted(
        routes,
        key=lambda route: (
            0
            if route.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
            else 1,
            route.childCallIndex,
        ),
    )

    for route in routesInOrder:
        realizedRouteResult = routePoints_realize(
            sourceChipRef=route.sourceChipRef,
            destinationChipRef=route.destinationChipRef,
            childCallIndex=route.childCallIndex,
            routePoints=route.routePoints,
        )
        assert result_isOkCheck(realizedRouteResult)

        for cell in realizedRouteResult.value.cells:
            key = (cell.worldRow, cell.worldCol)
            directions = cell.trackCell.directions
            if key not in occupiedDirectionsByCell:
                occupiedDirectionsByCell[key] = directions
                continue

            existingDirections = occupiedDirectionsByCell[key]
            crossingIsLegal = (
                _dirsAreHorizontal(existingDirections)
                and _dirsAreVertical(directions)
            ) or (
                _dirsAreVertical(existingDirections)
                and _dirsAreHorizontal(directions)
            )
            assert crossingIsLegal, (
                f"illegal coincidence at {key}: "
                f"{sorted(d.value for d in existingDirections)} vs "
                f"{sorted(d.value for d in directions)}"
            )
            occupiedDirectionsByCell[key] = existingDirections | directions


def _assert_route_cells_within_traversed_regions(
    routes,
    placedGrid: RoutingZoneGrid,
) -> None:
    """Assert realized route cells remain inside the route's declared regions."""

    for route in routes:
        zoneResult = placedGrid.routingZoneSet.zoneResult_get(route.owningRoutingZoneId)
        assert result_isOkCheck(zoneResult)
        zone = zoneResult.value
        traversedFrames = []
        for regionId in route.traversedRegionIds:
            regionResult = zone.routingZoneRegionSet.regionResult_get(regionId)
            assert result_isOkCheck(regionResult)
            traversedFrames.append(regionResult.value.routingZoneRegionFrame)

        realizedRouteResult = routePoints_realize(
            sourceChipRef=route.sourceChipRef,
            destinationChipRef=route.destinationChipRef,
            childCallIndex=route.childCallIndex,
            routePoints=route.routePoints,
        )
        assert result_isOkCheck(realizedRouteResult)

        for cell in realizedRouteResult.value.cells:
            assert any(
                _regionFrameContainsCell_check(
                    frame,
                    worldRow=cell.worldRow,
                    worldCol=cell.worldCol,
                )
                for frame in traversedFrames
            ), (
                "realized route cell escapes traversed regions: "
                f"{route.sourceChipRef.chipId.functionName} -> "
                f"{route.destinationChipRef.chipId.functionName} "
                f"at ({cell.worldCol},{cell.worldRow})"
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
        """Second child uses the next lane implied by attachment-sense policy."""

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
        assert bFwdCols[1] == aFwdCols[1]
        assert bFwdCols[3] == aFwdCols[3]
        assert bFwdRows[2] > aFwdRows[2]
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
        assert bRetCols[1] > aRetCols[1]
        assert bRetCols[3] > aRetCols[3]
        assert bRetRows[2] < aRetRows[2]
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
        forwardRoute = next(
            route
            for route in routes
            if route.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        )
        backedgeRoute = next(
            route
            for route in routes
            if route.solveKind
            is RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        )
        assert (
            forwardRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        )
        assert (
            backedgeRoute.solveKind
            is RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        )
        assert any(
            route.solveKind
            is RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
            for route in routes
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

    def test_zone_solver_does_not_collapse_hub_local_forward_and_return_lanes(
        self,
    ) -> None:
        """Local hub fan-out must not reuse one INTRA lane for forward and return."""

        diagnosticStack.stack_clear()
        fixturePath = Path(__file__).parent.parent / "examples" / "hub.yaml"
        documentDict = yaml.safe_load(fixturePath.read_text(encoding="utf-8"))

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(routeSetResult)

        hubRoutes = [
            route
            for route in routeSetResult.value.routingZoneLocalSolvedRoutes
            if route.owningRoutingZoneId.id == GridCoord(columnIndex=1, rowIndex=1)
            and {
                route.sourceChipRef.chipId.moduleName,
                route.destinationChipRef.chipId.moduleName,
            }
            == {"App.ts", "Proxy.ts"}
        ]

        forwardRoutes = [
            route
            for route in hubRoutes
            if route.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        ]
        returnRoutes = [
            route
            for route in hubRoutes
            if route.solveKind
            is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        ]

        assert len(forwardRoutes) == 5
        assert len(returnRoutes) == 5

        northLaneRows = {
            route.routePoints[2].verticalIndex for route in forwardRoutes
        }
        southLaneRows = {
            route.routePoints[2].verticalIndex for route in returnRoutes
        }
        assert len(northLaneRows) == 5
        assert len(southLaneRows) == 5

    def test_zone_solver_hub_local_lane_pick_honors_west_edge_from_end(
        self,
    ) -> None:
        """Hub local WTE forwards should consume west lanes from the far end first."""

        diagnosticStack.stack_clear()
        fixturePath = Path(__file__).parent.parent / "examples" / "hub.yaml"
        documentDict = yaml.safe_load(fixturePath.read_text(encoding="utf-8"))

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(routeSetResult)

        forwardRoutes = sorted(
            (
                route
                for route in routeSetResult.value.routingZoneLocalSolvedRoutes
                if route.owningRoutingZoneId.id
                == GridCoord(columnIndex=1, rowIndex=1)
                and route.solveKind
                is RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
                and {
                    route.sourceChipRef.chipId.moduleName,
                    route.destinationChipRef.chipId.moduleName,
                }
                == {"App.ts", "Proxy.ts"}
            ),
            key=lambda route: route.childCallIndex,
        )

        westEntryColumns: list[int] = [
            route.routePoints[1].horizontalIndex for route in forwardRoutes
        ]

        assert westEntryColumns == sorted(westEntryColumns, reverse=True)

    def test_zone_solver_hub_local_routes_have_no_illegal_cell_coincidence(
        self,
    ) -> None:
        """Hub local routes may cross, but must not illegally coincide."""

        diagnosticStack.stack_clear()
        fixturePath = Path(__file__).parent.parent / "examples" / "hub.yaml"
        documentDict = yaml.safe_load(fixturePath.read_text(encoding="utf-8"))

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(routeSetResult)

        hubRoutes = [
            route
            for route in routeSetResult.value.routingZoneLocalSolvedRoutes
            if route.owningRoutingZoneId.id == GridCoord(columnIndex=1, rowIndex=1)
            and {
                route.sourceChipRef.chipId.moduleName,
                route.destinationChipRef.chipId.moduleName,
            }
            == {"App.ts", "Proxy.ts"}
        ]

        _assert_routes_have_no_illegal_cell_coincidence(hubRoutes)

    def test_zone_solver_hub_local_route_cells_stay_inside_traversed_regions(
        self,
    ) -> None:
        """Hub local route materialization must stay inside declared region families."""

        diagnosticStack.stack_clear()
        fixturePath = Path(__file__).parent.parent / "examples" / "hub.yaml"
        documentDict = yaml.safe_load(fixturePath.read_text(encoding="utf-8"))

        placedGrid, routeSet = _localRoutingPipelineArtifacts_buildFromDocumentDict(
            documentDict
        )

        hubRoutes = [
            route
            for route in routeSet.routingZoneLocalSolvedRoutes
            if route.owningRoutingZoneId.id == GridCoord(columnIndex=1, rowIndex=1)
            and {
                route.sourceChipRef.chipId.moduleName,
                route.destinationChipRef.chipId.moduleName,
            }
            == {"App.ts", "Proxy.ts"}
        ]

        _assert_route_cells_within_traversed_regions(hubRoutes, placedGrid)

    def test_zone_solver_asymmetric_fanout_routes_have_no_illegal_cell_coincidence(
        self,
    ) -> None:
        """A second asymmetric WTE local fanout should also be coincidence-free."""

        diagnosticStack.stack_clear()
        fixturePath = (
            Path(__file__).parent.parent / "examples" / "asymmetric-fanout.yaml"
        )
        documentDict = yaml.safe_load(fixturePath.read_text(encoding="utf-8"))

        routeSetResult = zoneLocalSolvedRouteSetResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(routeSetResult)
        fanoutRoutes = [
            route
            for route in routeSetResult.value.routingZoneLocalSolvedRoutes
            if route.owningRoutingZoneId.id == GridCoord(columnIndex=1, rowIndex=1)
            and route.sourceChipRef.chipId.moduleName == "App.ts"
        ]

        _assert_routes_have_no_illegal_cell_coincidence(fanoutRoutes)

    def test_zone_solver_asymmetric_fanout_route_cells_stay_inside_traversed_regions(
        self,
    ) -> None:
        """Asymmetric WTE local fanout cells must remain inside declared regions."""

        diagnosticStack.stack_clear()
        fixturePath = (
            Path(__file__).parent.parent / "examples" / "asymmetric-fanout.yaml"
        )
        documentDict = yaml.safe_load(fixturePath.read_text(encoding="utf-8"))

        placedGrid, routeSet = _localRoutingPipelineArtifacts_buildFromDocumentDict(
            documentDict
        )

        fanoutRoutes = [
            route
            for route in routeSet.routingZoneLocalSolvedRoutes
            if route.owningRoutingZoneId.id == GridCoord(columnIndex=1, rowIndex=1)
            and route.sourceChipRef.chipId.moduleName == "App.ts"
        ]

        _assert_route_cells_within_traversed_regions(fanoutRoutes, placedGrid)
