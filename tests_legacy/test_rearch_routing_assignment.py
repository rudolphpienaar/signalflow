"""Tests for circuit-to-world routing-zone assignment."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipId,
    GridCoord,
    Result,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneRegionSide,
    result_isOkCheck,
)
from signalflow.routing import (
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
)


def yamlFixtureDocument_build(relativePath: str) -> dict[str, object]:
    """Load one YAML fixture document from the repo."""

    fixturePath: Path = Path(__file__).parent.parent / relativePath
    with fixturePath.open(encoding="utf-8") as inputHandle:
        loadedDocument = yaml.safe_load(inputHandle.read())
    assert isinstance(loadedDocument, dict)
    return loadedDocument


class TestRoutingZoneAssignment:
    """Verification of the simple-regime chip-to-zone assignment bridge."""

    def test_assignment_build_uses_two_zone_world_for_hub_fixture(self) -> None:
        """hub.yaml implicit world should size to the two occupied depth-paired zones."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            yamlFixtureDocument_build("examples/hub.yaml")
        )
        assert result_isOkCheck(circuitDocumentResult)
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            yamlFixtureDocument_build("examples/configs/world-implicit-horizontal.yaml"),
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromSignalFlowConfig(
                signalFlowConfigResult.value
            )
        )
        assert result_isOkCheck(routingZoneGridResult)

        assert routingZoneGridResult.value.gridSize == GridCoord(
            columnIndex=2,
            rowIndex=1,
        )

    def test_assignment_build_maps_horizontal_graph_layers_into_zone_columns(
        self,
    ) -> None:
        """West-to-east simple worlds should alternate west/east by graph depth."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            yamlFixtureDocument_build("examples/explicit-hub.yaml")
        )
        assert result_isOkCheck(circuitDocumentResult)
        signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
            yamlFixtureDocument_build("examples/configs/world-implicit-horizontal.yaml"),
            callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
        )
        assert result_isOkCheck(signalFlowConfigResult)
        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromSignalFlowConfig(
                signalFlowConfigResult.value
            )
        )
        assert result_isOkCheck(routingZoneGridResult)

        assignmentSetResult: Result[RoutingZoneAssignmentSet] = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )

        assert result_isOkCheck(assignmentSetResult)
        assignmentSet = assignmentSetResult.value
        rootAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="App.ts", functionName="main()")
        )
        assert result_isOkCheck(rootAssignmentResult)
        assert rootAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=1,
            rowIndex=1,
        )
        assert rootAssignmentResult.value.terminalSide is RoutingZoneRegionSide.WEST

        proxyAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Proxy.ts", functionName="p1()")
        )
        assert result_isOkCheck(proxyAssignmentResult)
        assert proxyAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=1,
            rowIndex=1,
        )
        assert proxyAssignmentResult.value.terminalSide is RoutingZoneRegionSide.EAST

        processAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Hub.ts", functionName="process()")
        )
        assert result_isOkCheck(processAssignmentResult)
        assert processAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=2,
            rowIndex=1,
        )
        assert processAssignmentResult.value.terminalSide is RoutingZoneRegionSide.WEST

        sinkAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Sink.ts", functionName="c1()")
        )
        assert result_isOkCheck(sinkAssignmentResult)
        assert sinkAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=2,
            rowIndex=1,
        )
        assert sinkAssignmentResult.value.terminalSide is RoutingZoneRegionSide.EAST

    def test_assignment_build_maps_vertical_graph_layers_into_zone_rows(self) -> None:
        """North-to-south simple worlds should alternate north/south by depth."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "M.ts",
                    "func": "root()",
                    "output_ports": [{"signal": "s", "return": "r"}],
                    "calls": [
                        {
                            "module": "M.ts",
                            "func": "child()",
                            "input_ports": [{"signal": "s", "return": "r"}],
                            "output_ports": [{"signal": "s", "return": "r"}],
                            "calls": [
                                {
                                    "module": "M.ts",
                                    "func": "grandchild()",
                                    "input_ports": [{"signal": "s", "return": "r"}],
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
            yamlFixtureDocument_build("examples/configs/world-implicit-vertical.yaml"),
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
        rootAssignmentResult = assignmentSetResult.value.assignmentForChipResult_get(
            ChipId(moduleName="M.ts", functionName="root()")
        )
        assert result_isOkCheck(rootAssignmentResult)
        assert rootAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=1,
            rowIndex=1,
        )
        assert rootAssignmentResult.value.terminalSide is RoutingZoneRegionSide.NORTH

        childAssignmentResult = assignmentSetResult.value.assignmentForChipResult_get(
            ChipId(moduleName="M.ts", functionName="child()")
        )
        assert result_isOkCheck(childAssignmentResult)
        assert childAssignmentResult.value.terminalSide is RoutingZoneRegionSide.SOUTH

        grandchildAssignmentResult = (
            assignmentSetResult.value.assignmentForChipResult_get(
                ChipId(moduleName="M.ts", functionName="grandchild()")
            )
        )
        assert result_isOkCheck(grandchildAssignmentResult)
        assert grandchildAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=1,
            rowIndex=2,
        )
        assert (
            grandchildAssignmentResult.value.terminalSide
            is RoutingZoneRegionSide.NORTH
        )

    def test_assignment_build_assigns_single_chip_to_one_by_one_world(self) -> None:
        """A root-only circuit should still assign into a 1x1 world."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {"tree": {"module": "Hub.ts", "func": "process()", "calls": []}}
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
        rootAssignmentResult = assignmentSetResult.value.assignmentForChipResult_get(
            ChipId(moduleName="Hub.ts", functionName="process()")
        )
        assert result_isOkCheck(rootAssignmentResult)
        assert rootAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=1,
            rowIndex=1,
        )
        assert rootAssignmentResult.value.terminalSide is RoutingZoneRegionSide.WEST

    def test_assignment_build_maps_rectangular_world_in_serpentine_order(self) -> None:
        """Rectangular west-to-east worlds should consume zones in serpentine order."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "A.ts",
                    "func": "a()",
                    "output_ports": [{"signal": "s", "return": "r"}],
                    "calls": [
                        {
                            "module": "B.ts",
                            "func": "b()",
                            "input_ports": [{"signal": "s", "return": "r"}],
                            "output_ports": [{"signal": "s", "return": "r"}],
                            "calls": [
                                {
                                    "module": "C.ts",
                                    "func": "c()",
                                    "input_ports": [{"signal": "s", "return": "r"}],
                                    "output_ports": [{"signal": "s", "return": "r"}],
                                    "calls": [
                                        {
                                            "module": "D.ts",
                                            "func": "d()",
                                            "input_ports": [{"signal": "s", "return": "r"}],
                                            "output_ports": [{"signal": "s", "return": "r"}],
                                            "calls": [
                                                {
                                                    "module": "E.ts",
                                                    "func": "e()",
                                                    "input_ports": [{"signal": "s", "return": "r"}],
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

        assignmentSetResult = (
            routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
                circuitDocumentResult.value,
                routingZoneGridResult.value,
            )
        )

        assert result_isOkCheck(assignmentSetResult)
        assignmentSet = assignmentSetResult.value

        aAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="A.ts", functionName="a()")
        )
        assert result_isOkCheck(aAssignmentResult)
        assert aAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=1,
            rowIndex=1,
        )
        assert aAssignmentResult.value.terminalSide is RoutingZoneRegionSide.WEST

        cAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="C.ts", functionName="c()")
        )
        assert result_isOkCheck(cAssignmentResult)
        assert cAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=2,
            rowIndex=1,
        )
        assert cAssignmentResult.value.terminalSide is RoutingZoneRegionSide.WEST

        eAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="E.ts", functionName="e()")
        )
        assert result_isOkCheck(eAssignmentResult)
        assert eAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=2,
            rowIndex=2,
        )
        assert eAssignmentResult.value.terminalSide is RoutingZoneRegionSide.WEST

    def test_assignment_build_maps_rectangular_vertical_world_in_serpentine_order(
        self,
    ) -> None:
        """Rectangular north-to-south worlds should use serpentine traversal."""

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "A.ts",
                    "func": "a()",
                    "output_ports": [{"signal": "s", "return": "r"}],
                    "calls": [
                        {
                            "module": "B.ts",
                            "func": "b()",
                            "input_ports": [{"signal": "s", "return": "r"}],
                            "output_ports": [{"signal": "s", "return": "r"}],
                            "calls": [
                                {
                                    "module": "C.ts",
                                    "func": "c()",
                                    "input_ports": [{"signal": "s", "return": "r"}],
                                    "output_ports": [{"signal": "s", "return": "r"}],
                                    "calls": [
                                        {
                                            "module": "D.ts",
                                            "func": "d()",
                                            "input_ports": [{"signal": "s", "return": "r"}],
                                            "output_ports": [{"signal": "s", "return": "r"}],
                                            "calls": [
                                                {
                                                    "module": "E.ts",
                                                    "func": "e()",
                                                    "input_ports": [{"signal": "s", "return": "r"}],
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
            {"world": {"sense": "north_to_south", "grid": {"columns": 2, "rows": 2}}},
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
        assignmentSet = assignmentSetResult.value
        eAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="E.ts", functionName="e()")
        )
        assert result_isOkCheck(eAssignmentResult)
        assert eAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=2,
            rowIndex=2,
        )
        assert eAssignmentResult.value.terminalSide is RoutingZoneRegionSide.NORTH
