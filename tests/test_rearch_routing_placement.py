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
    routingZoneRegionForKindAndSideResult_get,
    routingZoneRegionSetAll_get,
)
from signalflow.routing import (
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
)


def _frameContainsCell_check(frame, *, worldRow: int, worldCol: int) -> bool:
    return (
        frame.horizontalStart <= worldCol < frame.horizontalEnd_calculate()
        and frame.verticalStart <= worldRow < frame.verticalEnd_calculate()
    )


def _ownedRegionCountsByCell_build(zone) -> dict[tuple[int, int], int]:
    countsByCell: dict[tuple[int, int], int] = {}
    for region in routingZoneRegionSetAll_get(zone):
        frame = region.routingZoneRegionFrame
        for worldRow in range(
            frame.verticalStart,
            frame.verticalEnd_calculate(),
        ):
            for worldCol in range(
                frame.horizontalStart,
                frame.horizontalEnd_calculate(),
            ):
                key = (worldRow, worldCol)
                countsByCell[key] = countsByCell.get(key, 0) + 1
    return countsByCell


def _orderedRegionKindsAtRow_build(zone, worldRow: int) -> tuple[str, ...]:
    seen: list[str] = []
    occupiedCols: list[tuple[int, str]] = []
    for region in routingZoneRegionSetAll_get(zone):
        frame = region.routingZoneRegionFrame
        if not (frame.verticalStart <= worldRow < frame.verticalEnd_calculate()):
            continue
        side = region.routingZoneRegionId.routingZoneRegionSide
        label = (
            f"{side.value}/{region.routingZoneRegionId.routingZoneRegionKind.value}"
            if side is not None
            else region.routingZoneRegionId.routingZoneRegionKind.value
        )
        occupiedCols.append(
            (frame.horizontalStart, label)
        )
    for _, kind in sorted(occupiedCols):
        if kind not in seen:
            seen.append(kind)
    return tuple(seen)


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
        westInterLongResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        westInterFanResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
        )
        westTerminalRegionResult = (
            routingZoneRegionForKindAndSideResult_get(
            zone,
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.WEST,
            )
        )
        assert result_isOkCheck(westInterLongResult)
        assert result_isOkCheck(westInterFanResult)
        assert result_isOkCheck(westTerminalRegionResult)
        eastTerminalRegionResult = (
            routingZoneRegionForKindAndSideResult_get(
            zone,
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.EAST,
            )
        )
        eastInterLongResult = routingZoneRegionForKindAndSideResult_get(
            zone,
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

        eastInterFanResult = routingZoneRegionForKindAndSideResult_get(
            zone,
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

        westTerminalResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.WEST,
        )
        eastTerminalResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.EAST,
        )
        assert result_isOkCheck(westTerminalResult)
        assert result_isOkCheck(eastTerminalResult)
        westIntraFanResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
        )
        eastIntraFanResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
        )
        westIntraLongResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        eastIntraLongResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.EAST,
        )
        northIntraLatResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        southIntraLatResult = routingZoneRegionForKindAndSideResult_get(
            zone,
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

    def test_hub_zone_owned_regions_do_not_overlap(self) -> None:
        """hub.yaml zone (1,1) should assign at most one owner to every cell."""

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

        countsByCell = _ownedRegionCountsByCell_build(zoneResult.value)
        assert max(countsByCell.values()) == 1

    def test_hub_zone_wte_row_species_are_invariant(self) -> None:
        """Rows inside a WTE zone should show the correct long-vs-transition species."""

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

        northLatResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        southLatResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionSide.SOUTH,
        )
        assert result_isOkCheck(northLatResult)
        assert result_isOkCheck(southLatResult)

        northSpecies = _orderedRegionKindsAtRow_build(
            zone,
            northLatResult.value.routingZoneRegionFrame.verticalStart,
        )
        middleSpecies = _orderedRegionKindsAtRow_build(
            zone,
            northLatResult.value.routingZoneRegionFrame.verticalStart - 1,
        )
        southSpecies = _orderedRegionKindsAtRow_build(
            zone,
            southLatResult.value.routingZoneRegionFrame.verticalStart,
        )

        assert northSpecies == (
            "west/inter_routing_longitude",
            "west/inter_routing_fan_in_out",
            "west/chip_terminal",
            "west/intra_routing_fan_in_out",
            "west/intra_routing_transition",
            "north/intra_routing_latitude",
            "east/intra_routing_transition",
            "east/intra_routing_fan_in_out",
            "east/chip_terminal",
            "east/inter_routing_fan_in_out",
            "east/inter_routing_longitude",
        )
        assert middleSpecies == (
            "west/inter_routing_longitude",
            "west/inter_routing_fan_in_out",
            "west/chip_terminal",
            "west/intra_routing_fan_in_out",
            "west/intra_routing_longitude",
            "east/intra_routing_longitude",
            "east/intra_routing_fan_in_out",
            "east/chip_terminal",
            "east/inter_routing_fan_in_out",
            "east/inter_routing_longitude",
        )
        assert southSpecies == (
            "west/inter_routing_longitude",
            "west/inter_routing_fan_in_out",
            "west/chip_terminal",
            "west/intra_routing_fan_in_out",
            "west/intra_routing_transition",
            "south/intra_routing_latitude",
            "east/intra_routing_transition",
            "east/intra_routing_fan_in_out",
            "east/chip_terminal",
            "east/inter_routing_fan_in_out",
            "east/inter_routing_longitude",
        )

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

        northIntraLatResult = routingZoneRegionForKindAndSideResult_get(
            zone,
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

        northIntraLatResult = routingZoneRegionForKindAndSideResult_get(
            zone,
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
            routingZoneRegionForKindAndSideResult_get(
            zone,
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionSide.NORTH,
            )
        )
        southInterLatResult = routingZoneRegionForKindAndSideResult_get(
            zone,
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
            routingZoneRegionForKindAndSideResult_get(
            zoneResult.value,
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionSide.WEST,
            )
        )
        eastInterLongResult = (
            routingZoneRegionForKindAndSideResult_get(
            zoneResult.value,
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionSide.EAST,
            )
        )
        westInterFanResult = (
            routingZoneRegionForKindAndSideResult_get(
            zoneResult.value,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionSide.WEST,
            )
        )
        eastInterFanResult = (
            routingZoneRegionForKindAndSideResult_get(
            zoneResult.value,
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
            routingZoneRegionForKindAndSideResult_get(
            zone11Result.value,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionSide.EAST,
            )
        )
        zone11EastLongResult = (
            routingZoneRegionForKindAndSideResult_get(
            zone11Result.value,
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionSide.EAST,
            )
        )
        zone21WestFanResult = (
            routingZoneRegionForKindAndSideResult_get(
            zone21Result.value,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionSide.WEST,
            )
        )
        zone21WestLongResult = (
            routingZoneRegionForKindAndSideResult_get(
            zone21Result.value,
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
