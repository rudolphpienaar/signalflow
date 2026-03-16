"""Tests for route-obligation derivation from circuit and placement."""
from __future__ import annotations

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    Result,
    RouteObligationScope,
    RoutingZoneGrid,
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
    )
    assert result_isOkCheck(placedGridResult)
    return placedGridResult


class TestRoutingObligations:
    """Verification of the first route-obligation layer."""

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
