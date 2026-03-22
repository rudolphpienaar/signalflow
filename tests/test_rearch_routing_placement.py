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
                    "output_ports": [
                        {"signal": "a", "return": "ra"},
                        {"signal": "b", "return": "rb"},
                        {"signal": "c", "return": "rc"},
                    ],
                    "calls": [
                        {
                            "module": "M.ts",
                            "func": "a()",
                            "input_ports": [{"signal": "a", "return": "ra"}],
                            "calls": [],
                        },
                        {
                            "module": "M.ts",
                            "func": "b()",
                            "input_ports": [{"signal": "b", "return": "rb"}],
                            "calls": [],
                        },
                        {
                            "module": "M.ts",
                            "func": "c()",
                            "input_ports": [{"signal": "c", "return": "rc"}],
                            "calls": [],
                        },
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

        assert len(zone.chipPlacementSet.placements) == 4
        westInterLongResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        westInterFanResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
        )
        westTerminalRegionResult = (
            zone.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.WEST,
            )
        )
        assert result_isOkCheck(westInterLongResult)
        assert result_isOkCheck(westInterFanResult)
        assert result_isOkCheck(westTerminalRegionResult)
        eastTerminalRegionResult = (
            zone.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.EAST,
            )
        )
        eastInterLongResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.EAST,
        )
        assert result_isOkCheck(eastTerminalRegionResult)
        assert result_isOkCheck(eastInterLongResult)
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

        assert westTerminalRegionResult.value.routingZoneRegionFrame.verticalSpan == 24
        assert (
            westInterLongResult.value.routingZoneRegionFrame.horizontalEnd_calculate()
            == westInterFanResult.value.routingZoneRegionFrame.horizontalStart
        )
        assert (
            westInterFanResult.value.routingZoneRegionFrame.horizontalEnd_calculate()
            == westTerminalRegionResult.value.routingZoneRegionFrame.horizontalStart
        )

        eastInterFanResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
        )
        assert result_isOkCheck(eastInterFanResult)
        assert (
            eastTerminalRegionResult.value.routingZoneRegionFrame.horizontalEnd_calculate()
            == eastInterFanResult.value.routingZoneRegionFrame.horizontalStart
        )
        assert (
            eastInterFanResult.value.routingZoneRegionFrame.horizontalEnd_calculate()
            == eastInterLongResult.value.routingZoneRegionFrame.horizontalStart
        )
        assert (
            zone.routingZoneFrame.horizontalEnd_calculate()
            == eastInterLongResult.value.routingZoneRegionFrame.horizontalEnd_calculate(
            )
        )

    def test_routingZoneGridPlacementPlanResult_build_populates_interconnect_frame(
        self,
    ) -> None:
        """Two-zone horizontal worlds should get logical interconnect frames."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "root()",
                    "output_ports": [{"signal": "sig", "return": "ret"}],
                    "calls": [
                        {
                            "module": "M.ts",
                            "func": "child()",
                            "input_ports": [{"signal": "sig", "return": "ret"}],
                            "output_ports": [{"signal": "inner", "return": "back"}],
                            "calls": [
                                {
                                    "module": "M.ts",
                                    "func": "grandchild()",
                                    "input_ports": [
                                        {"signal": "inner", "return": "back"}
                                    ],
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

    def test_hub_zone_local_crossbar_scales_to_directed_wire_demand(self) -> None:
        """hub.yaml zone (1,1) must widen its inner corridor for 10 directed wires."""

        fixturePath = Path(__file__).resolve().parents[1] / "examples" / "hub.yaml"
        documentDict = safe_load(fixturePath.read_text(encoding="utf-8"))

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
        assignmentSetResult: Result[RoutingZoneAssignmentSet] = (
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

        westTerminalResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.WEST,
        )
        eastTerminalResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.EAST,
        )
        assert result_isOkCheck(westTerminalResult)
        assert result_isOkCheck(eastTerminalResult)
        westIntraFanResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
        )
        eastIntraFanResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
        )
        westIntraLongResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        eastIntraLongResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.EAST,
        )
        northIntraLatResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        southIntraLatResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionSide.SOUTH,
        )
        assert result_isOkCheck(westIntraFanResult)
        assert result_isOkCheck(eastIntraFanResult)
        assert result_isOkCheck(westIntraLongResult)
        assert result_isOkCheck(eastIntraLongResult)
        assert result_isOkCheck(northIntraLatResult)
        assert result_isOkCheck(southIntraLatResult)

        innerCorridorWidth = (
            eastTerminalResult.value.routingZoneRegionFrame.horizontalStart
            - westTerminalResult.value.routingZoneRegionFrame.horizontalEnd_calculate()
        )

        assert innerCorridorWidth >= 24
        assert westIntraFanResult.value.routingZoneRegionFrame.horizontalSpan >= 4
        assert eastIntraFanResult.value.routingZoneRegionFrame.horizontalSpan >= 4
        assert westIntraLongResult.value.routingZoneRegionFrame.horizontalSpan == 10
        assert eastIntraLongResult.value.routingZoneRegionFrame.horizontalSpan == 10
        assert northIntraLatResult.value.routingZoneRegionFrame.verticalSpan == 10
        assert southIntraLatResult.value.routingZoneRegionFrame.verticalSpan == 10

    def test_hub_zone_buckle_aware_anchor_beats_blended_centroid(self) -> None:
        """WTE intra-lat placement should penalize buckle, not just average rows."""

        fixturePath = Path(__file__).resolve().parents[1] / "examples" / "hub.yaml"
        documentDict = safe_load(fixturePath.read_text(encoding="utf-8"))

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(circuitDocumentResult)
        circuitDocument = circuitDocumentResult.value
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "west_to_east"}},
            callingDepth=circuitDocument.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
            signalFlowConfigResult.value
        )
        assert result_isOkCheck(routingZoneGridResult)
        assignmentSetResult: Result[RoutingZoneAssignmentSet] = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocument,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)
        placementPlanResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                assignmentSetResult.value,
                routingZoneGridResult.value,
                circuitDocument,
            )
        )
        assert result_isOkCheck(placementPlanResult)

        zoneResult = placementPlanResult.value.zoneAtCoordResult_get(
            GridCoord(columnIndex=1, rowIndex=1)
        )
        assert result_isOkCheck(zoneResult)
        zone = zoneResult.value

        northIntraLatResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        assert result_isOkCheck(northIntraLatResult)
        chosenNorthFrame = northIntraLatResult.value.routingZoneRegionFrame
        chosenNorthEnd = chosenNorthFrame.verticalEnd_calculate() - 1
        chosenNorthStart = chosenNorthFrame.verticalStart

        signalRows = (9, 9, 17, 25, 33, 41)
        blendedCentroidNorthEnd = round(sum(signalRows) / len(signalRows))
        intraLaneSpan = chosenNorthFrame.verticalSpan

        def _overshoot(value: int, a: int, b: int) -> int:
            lowerBound = min(a, b)
            upperBound = max(a, b)
            if value < lowerBound:
                return lowerBound - value
            if value > upperBound:
                return value - upperBound
            return 0

        def _anchorScore(northEnd: int) -> tuple[int, int, int]:
            northStart = northEnd - intraLaneSpan + 1
            totalBuckle = 0
            totalDetour = 0
            maxDetour = 0
            for localLaneIndex, srcSignalRow in enumerate((9, 11, 13, 15, 17)):
                dstSignalRow = signalRows[localLaneIndex + 1]
                srcReturnRow = srcSignalRow + 1
                dstReturnRow = dstSignalRow + 1
                forwardLaneRow = northStart + localLaneIndex
                returnLaneRow = (
                    northEnd + 1 + (intraLaneSpan - 1 - localLaneIndex)
                )
                detours = (
                    abs(srcSignalRow - forwardLaneRow),
                    abs(dstSignalRow - forwardLaneRow),
                    abs(dstReturnRow - returnLaneRow),
                    abs(srcReturnRow - returnLaneRow),
                )
                totalDetour += sum(detours)
                maxDetour = max(maxDetour, *detours)
                totalBuckle += _overshoot(
                    forwardLaneRow,
                    srcSignalRow,
                    dstSignalRow,
                )
                totalBuckle += _overshoot(
                    returnLaneRow,
                    srcReturnRow,
                    dstReturnRow,
                )
            return (totalBuckle, totalDetour, maxDetour)

        assert _anchorScore(chosenNorthEnd) <= _anchorScore(blendedCentroidNorthEnd)
        assert chosenNorthStart >= 9

    def test_asymmetric_fanout_zone_buckle_aware_anchor_beats_blended_centroid(
        self,
    ) -> None:
        """A second asymmetric WTE fanout should also prefer the buckle-aware anchor."""

        fixturePath = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "asymmetric-fanout.yaml"
        )
        documentDict = safe_load(fixturePath.read_text(encoding="utf-8"))

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(circuitDocumentResult)
        circuitDocument = circuitDocumentResult.value
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            {"world": {"sense": "west_to_east"}},
            callingDepth=circuitDocument.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
            signalFlowConfigResult.value
        )
        assert result_isOkCheck(routingZoneGridResult)
        assignmentSetResult: Result[RoutingZoneAssignmentSet] = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocument,
                routingZoneGridResult.value,
            )
        )
        assert result_isOkCheck(assignmentSetResult)
        placementPlanResult = (
            routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
                assignmentSetResult.value,
                routingZoneGridResult.value,
                circuitDocument,
            )
        )
        assert result_isOkCheck(placementPlanResult)

        zoneResult = placementPlanResult.value.zoneAtCoordResult_get(
            GridCoord(columnIndex=1, rowIndex=1)
        )
        assert result_isOkCheck(zoneResult)
        zone = zoneResult.value

        northIntraLatResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        assert result_isOkCheck(northIntraLatResult)
        chosenNorthFrame = northIntraLatResult.value.routingZoneRegionFrame
        chosenNorthEnd = chosenNorthFrame.verticalEnd_calculate() - 1
        chosenNorthStart = chosenNorthFrame.verticalStart

        signalRows = (9, 9, 17, 25, 33, 41, 49)
        blendedCentroidNorthEnd = round(sum(signalRows) / len(signalRows))
        intraLaneSpan = chosenNorthFrame.verticalSpan

        def _overshoot(value: int, a: int, b: int) -> int:
            lowerBound = min(a, b)
            upperBound = max(a, b)
            if value < lowerBound:
                return lowerBound - value
            if value > upperBound:
                return value - upperBound
            return 0

        def _anchorScore(northEnd: int) -> tuple[int, int, int]:
            northStart = northEnd - intraLaneSpan + 1
            totalBuckle = 0
            totalDetour = 0
            maxDetour = 0
            for localLaneIndex, srcSignalRow in enumerate((9, 11, 13, 15, 17, 19)):
                dstSignalRow = signalRows[localLaneIndex + 1]
                srcReturnRow = srcSignalRow + 1
                dstReturnRow = dstSignalRow + 1
                forwardLaneRow = northStart + localLaneIndex
                returnLaneRow = (
                    northEnd + 1 + (intraLaneSpan - 1 - localLaneIndex)
                )
                detours = (
                    abs(srcSignalRow - forwardLaneRow),
                    abs(dstSignalRow - forwardLaneRow),
                    abs(dstReturnRow - returnLaneRow),
                    abs(srcReturnRow - returnLaneRow),
                )
                totalDetour += sum(detours)
                maxDetour = max(maxDetour, *detours)
                totalBuckle += _overshoot(
                    forwardLaneRow,
                    srcSignalRow,
                    dstSignalRow,
                )
                totalBuckle += _overshoot(
                    returnLaneRow,
                    srcReturnRow,
                    dstReturnRow,
                )
            return (totalBuckle, totalDetour, maxDetour)

        assert _anchorScore(chosenNorthEnd) <= _anchorScore(blendedCentroidNorthEnd)
        assert chosenNorthStart >= 9

    def test_routingZoneGridPlacementPlanResult_build_populates_vertical_zone(
        self,
    ) -> None:
        """One-zone north-to-south worlds should use north/south terminal regions."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "output_ports": [{"signal": "sig", "return": "ret"}],
                    "calls": [
                        {
                            "module": "M.ts",
                            "func": "child()",
                            "input_ports": [{"signal": "sig", "return": "ret"}],
                            "calls": [],
                        }
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

        northTerminalRegionResult = (
            zone.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.NORTH,
            )
        )
        southInterLatResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.SOUTH,
        )
        assert result_isOkCheck(northTerminalRegionResult)
        assert result_isOkCheck(southInterLatResult)
        assert northTerminalRegionResult.value.routingZoneRegionFrame.verticalStart == 2
        assert (
            zone.routingZoneFrame.verticalEnd_calculate()
            == southInterLatResult.value.routingZoneRegionFrame.verticalEnd_calculate()
        )

    def test_same_zone_backedge_widens_inter_perimeter_regions(self) -> None:
        """Same-zone perimeter backedges should contribute to INTER capacity."""

        fixturePath = (
            Path(__file__).parent.parent
            / "examples"
            / "simple-circuit"
            / "rearch-external-backedge.yaml"
        )
        documentDict = safe_load(fixturePath.read_text(encoding="utf-8"))
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
        zoneResult = placementPlanResult.value.zoneAtCoordResult_get(
            GridCoord(columnIndex=1, rowIndex=1)
        )
        assert result_isOkCheck(zoneResult)

        westInterLongResult = (
            zoneResult.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionSide.WEST,
            )
        )
        eastInterLongResult = (
            zoneResult.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionSide.EAST,
            )
        )
        westInterFanResult = (
            zoneResult.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionSide.WEST,
            )
        )
        eastInterFanResult = (
            zoneResult.value.routingZoneRegionSet.regionForKindAndSideResult_get(
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionSide.EAST,
            )
        )
        assert result_isOkCheck(westInterLongResult)
        assert result_isOkCheck(eastInterLongResult)
        assert result_isOkCheck(westInterFanResult)
        assert result_isOkCheck(eastInterFanResult)
        assert westInterLongResult.value.routingZoneRegionFrame.horizontalSpan == 2
        assert eastInterLongResult.value.routingZoneRegionFrame.horizontalSpan == 2
        assert westInterFanResult.value.routingZoneRegionFrame.horizontalSpan >= 4
        assert eastInterFanResult.value.routingZoneRegionFrame.horizontalSpan >= 4
        assert (
            westInterFanResult.value.routingZoneRegionFrame.horizontalSpan
            == eastInterFanResult.value.routingZoneRegionFrame.horizontalSpan
        )

    def test_placement_plan_places_rectangular_horizontal_world(
        self,
    ) -> None:
        """Placement planning should place zones on rectangular horizontal grids."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "A.ts",
                    "func": "a()",
                    "output_ports": [{"signal": "ab", "return": "ba"}],
                    "calls": [
                        {
                            "module": "B.ts",
                            "func": "b()",
                            "input_ports": [{"signal": "ab", "return": "ba"}],
                            "output_ports": [{"signal": "bc", "return": "cb"}],
                            "calls": [
                                {
                                    "module": "C.ts",
                                    "func": "c()",
                                    "input_ports": [
                                        {"signal": "bc", "return": "cb"}
                                    ],
                                    "output_ports": [
                                        {"signal": "cd", "return": "dc"}
                                    ],
                                    "calls": [
                                        {
                                            "module": "D.ts",
                                            "func": "d()",
                                            "input_ports": [
                                                {"signal": "cd", "return": "dc"}
                                            ],
                                            "output_ports": [
                                                {"signal": "de", "return": "ed"}
                                            ],
                                            "calls": [
                                                {
                                                    "module": "E.ts",
                                                    "func": "e()",
                                                    "input_ports": [
                                                        {
                                                            "signal": "de",
                                                            "return": "ed",
                                                        }
                                                    ],
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
        assert zone12Result.value.routingZoneFrame.verticalStart == 19
        assert (
            zone22Result.value.routingZoneFrame.horizontalStart
            == zone12Result.value.routingZoneFrame.horizontalEnd_calculate() + 2
        )
        assert zone22Result.value.routingZoneFrame.verticalStart == 19

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
        assert zone11EastFanResult.value.routingZoneRegionFrame.horizontalSpan >= 8
        assert zone11EastLongResult.value.routingZoneRegionFrame.horizontalSpan == 6
        assert zone21WestFanResult.value.routingZoneRegionFrame.horizontalSpan >= 8
        assert zone21WestLongResult.value.routingZoneRegionFrame.horizontalSpan == 6
        assert (
            zone11EastFanResult.value.routingZoneRegionFrame.horizontalSpan
            == zone21WestFanResult.value.routingZoneRegionFrame.horizontalSpan
        )
        assert interconnectResult.value.routingZoneInterconnectFrame.horizontalSpan == 6
