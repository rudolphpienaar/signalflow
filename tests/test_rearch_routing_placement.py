"""Tests for logical routing-zone placement planning."""
from __future__ import annotations

from pathlib import Path

from yaml import safe_load

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    GridCoord,
    Result,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    result_isOkCheck,
)
from signalflow.routing import (
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
)


class TestRoutingZonePlacement:
    """Verification of logical chip-placement planning in routing zones."""

    def test_routingZoneGridPlacementPlanResult_build_populates_horizontal_zone(
        self,
    ) -> None:
        """One-zone west-to-east worlds should get placements and region frames."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {"module": "M.ts", "func": "a()", "calls": []},
                        {"module": "M.ts", "func": "b()", "calls": []},
                        {"module": "M.ts", "func": "c()", "calls": []},
                    ],
                }
            }
        )
        assert result_isOkCheck(circuitDocumentResult)
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "west_to_east"}},
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromSignalFlowConfig(
                signalFlowConfigResult.value
            )
        )
        assert result_isOkCheck(routingZoneGridResult)
        assignmentSetResult = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)

        placementPlanResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                assignmentSetResult.value,
                routingZoneGridResult.value,
                circuitDocumentResult.value,
            )
        )

        assert result_isOkCheck(placementPlanResult)
        plannedGrid = placementPlanResult.value
        zoneResult = plannedGrid.zoneAtCoordResult_get(
            GridCoord(columnIndex=1, rowIndex=1)
        )
        assert result_isOkCheck(zoneResult)
        zone = zoneResult.value

        assert zone.routingZoneFrame.horizontalSpan == 42
        assert zone.routingZoneFrame.verticalSpan == 25
        assert len(zone.chipPlacementSet.placements) == 4
        westTerminalRegionResult = (
            zone.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.WEST,
            )
        )
        assert result_isOkCheck(westTerminalRegionResult)
        eastTerminalRegionResult = (
            zone.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.EAST,
            )
        )
        assert result_isOkCheck(eastTerminalRegionResult)
        westPlacements = zone.chipPlacementSet.placementsInRegion_build(
            chipTerminalRegionId=westTerminalRegionResult.value.routingZoneRegionId
        )
        eastPlacements = zone.chipPlacementSet.placementsInRegion_build(
            chipTerminalRegionId=eastTerminalRegionResult.value.routingZoneRegionId
        )
        assert len(westPlacements.placements) == 1
        assert [placement.orderIndex for placement in eastPlacements.placements] == [
            0,
            1,
            2,
        ]

        assert (
            westTerminalRegionResult.value.routingZoneRegionFrame.horizontalStart
            == 2
        )
        assert westTerminalRegionResult.value.routingZoneRegionFrame.verticalSpan == 15

        eastInterFanResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
        )
        assert result_isOkCheck(eastInterFanResult)
        assert eastInterFanResult.value.routingZoneRegionFrame.horizontalStart == 40

    def test_routingZoneGridPlacementPlanResult_build_populates_interconnect_frame(
        self,
    ) -> None:
        """Two-zone horizontal worlds should get logical interconnect frames."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "root()",
                    "calls": [
                        {
                            "module": "M.ts",
                            "func": "child()",
                            "calls": [
                                {
                                    "module": "M.ts",
                                    "func": "grandchild()",
                                    "calls": [],
                                }
                            ],
                        }
                    ],
                }
            }
        )
        assert result_isOkCheck(circuitDocumentResult)
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "west_to_east"}},
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
            signalFlowConfigResult.value
        )
        assert result_isOkCheck(routingZoneGridResult)
        assignmentSetResult = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)

        placementPlanResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                assignmentSetResult.value,
                routingZoneGridResult.value,
                circuitDocumentResult.value,
            )
        )

        assert result_isOkCheck(placementPlanResult)
        plannedGrid = placementPlanResult.value
        sourceZoneResult = plannedGrid.zoneAtCoordResult_get(
            GridCoord(columnIndex=1, rowIndex=1)
        )
        destinationZoneResult = plannedGrid.zoneAtCoordResult_get(
            GridCoord(columnIndex=2, rowIndex=1)
        )
        assert result_isOkCheck(sourceZoneResult)
        assert result_isOkCheck(destinationZoneResult)
        interconnectResult = plannedGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=GridCoord(columnIndex=1, rowIndex=1),
            destinationGridCoord=GridCoord(columnIndex=2, rowIndex=1),
        )
        assert result_isOkCheck(interconnectResult)
        assert (
            interconnectResult.value.routingZoneInterconnectFrame.horizontalStart
            == sourceZoneResult.value.routingZoneFrame.horizontalEnd_calculate()
        )
        assert (
            interconnectResult.value.routingZoneInterconnectFrame.horizontalSpan == 2
        )
        assert (
            destinationZoneResult.value.routingZoneFrame.horizontalStart
            == interconnectResult.value.routingZoneInterconnectFrame.horizontalStart
            + interconnectResult.value.routingZoneInterconnectFrame.horizontalSpan
        )

    def test_routingZoneGridPlacementPlanResult_build_populates_vertical_zone(
        self,
    ) -> None:
        """One-zone north-to-south worlds should use north/south terminal regions."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {"module": "M.ts", "func": "child()", "calls": []}
                    ],
                }
            }
        )
        assert result_isOkCheck(circuitDocumentResult)
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "north_to_south"}},
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
            signalFlowConfigResult.value
        )
        assert result_isOkCheck(routingZoneGridResult)
        assignmentSetResult = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)

        placementPlanResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                assignmentSetResult.value,
                routingZoneGridResult.value,
                circuitDocumentResult.value,
            )
        )

        assert result_isOkCheck(placementPlanResult)
        zoneResult = placementPlanResult.value.zoneAtCoordResult_get(
            GridCoord(columnIndex=1, rowIndex=1)
        )
        assert result_isOkCheck(zoneResult)
        zone = zoneResult.value

        assert zone.routingZoneFrame.horizontalSpan == 23
        assert zone.routingZoneFrame.verticalSpan == 28
        northTerminalRegionResult = (
            zone.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.NORTH,
            )
        )
        assert result_isOkCheck(northTerminalRegionResult)
        assert northTerminalRegionResult.value.routingZoneRegionFrame.verticalStart == 2

    def test_placement_plan_places_rectangular_horizontal_world(
        self,
    ) -> None:
        """Placement planning should place zones on rectangular horizontal grids."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
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
                                                    "module": "E.ts",
                                                    "func": "e()",
                                                    "calls": [],
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
        )
        assert result_isOkCheck(circuitDocumentResult)
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "west_to_east", "grid": {"columns": 2, "rows": 2}}},
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
            signalFlowConfigResult.value
        )
        assert result_isOkCheck(routingZoneGridResult)

        assignmentSetResult: Result[RoutingZoneAssignmentSet] = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)
        placementPlanResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                routingZoneAssignmentSet=assignmentSetResult.value,
                routingZoneGrid=routingZoneGridResult.value,
                circuitDocument=circuitDocumentResult.value,
            )
        )

        assert result_isOkCheck(placementPlanResult)
        plannedGrid = placementPlanResult.value

        zone11Result = plannedGrid.zoneAtCoordResult_get(GridCoord(1, 1))
        zone21Result = plannedGrid.zoneAtCoordResult_get(GridCoord(2, 1))
        zone12Result = plannedGrid.zoneAtCoordResult_get(GridCoord(1, 2))
        zone22Result = plannedGrid.zoneAtCoordResult_get(GridCoord(2, 2))
        assert result_isOkCheck(zone11Result)
        assert result_isOkCheck(zone21Result)
        assert result_isOkCheck(zone12Result)
        assert result_isOkCheck(zone22Result)

        assert zone11Result.value.routingZoneFrame.horizontalStart == 0
        assert zone11Result.value.routingZoneFrame.verticalStart == 0
        assert (
            zone21Result.value.routingZoneFrame.horizontalStart
            == zone11Result.value.routingZoneFrame.horizontalEnd_calculate() + 2
        )
        assert zone21Result.value.routingZoneFrame.verticalStart == 0
        assert zone12Result.value.routingZoneFrame.horizontalStart == 0
        assert zone12Result.value.routingZoneFrame.verticalStart == 18
        assert (
            zone22Result.value.routingZoneFrame.horizontalStart
            == zone12Result.value.routingZoneFrame.horizontalEnd_calculate() + 2
        )
        assert zone22Result.value.routingZoneFrame.verticalStart == 18

    def test_branch_converging_placement_materializes_directed_wire_seam(
        self,
    ) -> None:
        """Branch-converging seam geometry should widen to directed-wire demand."""

        documentDict = safe_load(
            Path("examples/branch-converging.yaml").read_text()
        )
        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(circuitDocumentResult)
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "west_to_east"}},
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
            signalFlowConfigResult.value
        )
        assert result_isOkCheck(routingZoneGridResult)
        assignmentSetResult = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)
        placementPlanResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                assignmentSetResult.value,
                routingZoneGridResult.value,
                circuitDocumentResult.value,
            )
        )
        assert result_isOkCheck(placementPlanResult)

        plannedGrid = placementPlanResult.value
        zone11Result = plannedGrid.zoneAtCoordResult_get(GridCoord(1, 1))
        zone21Result = plannedGrid.zoneAtCoordResult_get(GridCoord(2, 1))
        interconnectResult = plannedGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=GridCoord(1, 1),
            destinationGridCoord=GridCoord(2, 1),
        )
        assert result_isOkCheck(zone11Result)
        assert result_isOkCheck(zone21Result)
        assert result_isOkCheck(interconnectResult)

        zone11EastFanResult = (
            zone11Result.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionSide.EAST,
            )
        )
        zone11EastLongResult = (
            zone11Result.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionSide.EAST,
            )
        )
        zone21WestFanResult = (
            zone21Result.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionSide.WEST,
            )
        )
        zone21WestLongResult = (
            zone21Result.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionSide.WEST,
            )
        )
        assert result_isOkCheck(zone11EastFanResult)
        assert result_isOkCheck(zone11EastLongResult)
        assert result_isOkCheck(zone21WestFanResult)
        assert result_isOkCheck(zone21WestLongResult)
        assert zone11EastFanResult.value.routingZoneRegionFrame.horizontalSpan == 8
        assert zone11EastLongResult.value.routingZoneRegionFrame.horizontalSpan == 6
        assert zone21WestFanResult.value.routingZoneRegionFrame.horizontalSpan == 8
        assert zone21WestLongResult.value.routingZoneRegionFrame.horizontalSpan == 6
        assert interconnectResult.value.routingZoneInterconnectFrame.horizontalSpan == 6
