"""Tests for route-obligation derivation from circuit and placement."""
from __future__ import annotations

from pathlib import Path

from yaml import safe_load

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipId,
    ChipPlacementSet,
    ChipRef,
    Result,
    RouteObligationScope,
    RoutingZoneGrid,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
)


def placedGridResult_buildFromDocumentDict(
    documentDict: dict[str, object],
    worldDocumentDict: dict[str, object],
) -> Result[RoutingZoneGrid]:
    """Build placed routing-zone world from document and world config."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(documentDict)
    assert result_isOkCheck(circuitDocumentResult)
    signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
        worldDocumentDict,
        callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
    )
    assert result_isOkCheck(signalFlowConfigResult)
    routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
        signalFlowConfigResult.value
    )
    assert result_isOkCheck(routingZoneGridResult)
    if circuitDocumentResult.value.callingDepth_calculate() < 2:
        return routingZoneGridResult
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
    return placedGridResult


class TestRoutingObligations:
    """Verification of the first route-obligation layer."""

    def test_zoneOwnershipScan_does_not_emit_false_missing_chip_diagnostics(
        self,
    ) -> None:
        """Scanning zones to find ownership should not log per-zone miss noise."""

        diagnosticStack.stack_clear()
        documentDict = safe_load(Path("examples/branch-converging.yaml").read_text())
        placedGridResult = placedGridResult_buildFromDocumentDict(
            documentDict,
            {"world": {"sense": "west_to_east"}},
        )
        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(placedGridResult)
        assert result_isOkCheck(circuitDocumentResult)

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocumentResult.value,
                placedGridResult.value,
            )
        )

        assert result_isOkCheck(routeObligationSetResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert [
            diagnostic.code for diagnostic in diagnostics
        ] == []

    def test_placementForChipResult_get_reports_missing_chip_context(self) -> None:
        """A real placement miss should include the missing chip identity."""

        diagnosticStack.stack_clear()
        missingChipRef = ChipRef(
            ChipId(moduleName="Missing.ts", functionName="ghost()")
        )

        placementResult = ChipPlacementSet().placementForChipResult_get(missingChipRef)

        assert not result_isOkCheck(placementResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "routing.zone.placement.missing_chip"
        assert diagnostics[0].context == ("Missing.ts", "ghost()")

    def test_routeObligationSet_build_marks_same_zone_calls_as_local(self) -> None:
        """Root-to-child calls in one zone should be local obligations."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "calls": [
                    {"module": "A.ts", "func": "a()", "calls": []},
                    {"module": "B.ts", "func": "b()", "calls": []},
                ],
            }
        }
        placedGridResult = placedGridResult_buildFromDocumentDict(
            documentDict,
            {"world": {"sense": "west_to_east"}},
        )
        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(circuitDocumentResult)

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocumentResult.value,
                placedGridResult.value,
            )
        )

        assert result_isOkCheck(routeObligationSetResult)
        callRouteObligations = (
            routeObligationSetResult.value.callRouteObligationSet.callRouteObligations
        )
        assert len(callRouteObligations) == 2
        assert {
            callRouteObligation.routeObligationScope
            for callRouteObligation in callRouteObligations
        } == {RouteObligationScope.ZONE_LOCAL}

    def test_routeObligationSet_build_marks_cross_zone_calls_as_seam_crossing(
        self,
    ) -> None:
        """Child-to-grandchild calls across adjacent zones should be seam crossings."""

        documentDict = {
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
        }
        placedGridResult = placedGridResult_buildFromDocumentDict(
            documentDict,
            {"world": {"sense": "west_to_east"}},
        )
        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(circuitDocumentResult)

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocumentResult.value,
                placedGridResult.value,
            )
        )

        assert result_isOkCheck(routeObligationSetResult)
        callRouteObligations = (
            routeObligationSetResult.value.callRouteObligationSet.callRouteObligations
        )
        assert [
            obligation.routeObligationScope for obligation in callRouteObligations
        ] == [RouteObligationScope.ZONE_LOCAL, RouteObligationScope.SEAM_CROSSING]

    def test_routeObligationSet_build_collects_chip_internal_wiring(self) -> None:
        """Declared internal wiring should become chip-internal obligations."""

        documentDict = {
            "tree": {
                "module": "Hub.ts",
                "func": "process()",
                "input_ports": [{"signal": "a"}],
                "output_ports": [{"signal": "b"}],
                "internal_wiring": ["a:b", "b:b:data"],
                "calls": [],
            }
        }
        placedGridResult = placedGridResult_buildFromDocumentDict(
            documentDict,
            {
                "world": {
                    "sense": "west_to_east",
                    "grid": {"columns": 1, "rows": 1},
                }
            },
        )
        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(circuitDocumentResult)

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocumentResult.value,
                placedGridResult.value,
            )
        )

        assert result_isOkCheck(routeObligationSetResult)
        internalObligations = (
            routeObligationSetResult.value
            .chipInternalRouteObligationSet.chipInternalRouteObligations
        )
        assert len(internalObligations) == 2
        assert {
            obligation.routeObligationScope for obligation in internalObligations
        } == {RouteObligationScope.CHIP_INTERNAL}
