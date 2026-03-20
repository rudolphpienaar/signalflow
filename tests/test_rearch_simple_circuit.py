"""Structural verification for the simple-circuit fixture family."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipId,
    GridCoord,
    Result,
    RouteObligationScope,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneRegionSide,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
)


def simpleCircuitFixtureDocument_build(fixtureName: str) -> dict[str, object]:
    """Load one simple-circuit YAML fixture."""

    fixturePath: Path = (
        Path(__file__).parent.parent / "examples" / "simple-circuit" / fixtureName
    )
    with fixturePath.open(encoding="utf-8") as inputHandle:
        loadedDocument = yaml.safe_load(inputHandle.read())
    assert isinstance(loadedDocument, dict)
    return loadedDocument


def placedGridAndAssignment_build(
    fixtureName: str,
) -> tuple[object, RoutingZoneGrid, RoutingZoneAssignmentSet]:
    """Build circuit, assignment, and placed grid for one simple-circuit fixture."""

    documentDict = simpleCircuitFixtureDocument_build(fixtureName)
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

    assignmentSetResult: Result[RoutingZoneAssignmentSet] = (
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
    return (
        circuitDocumentResult.value,
        placedGridResult.value,
        assignmentSetResult.value,
    )


def callObligationScopes_getAll(
    routeObligationSet: object,
) -> tuple[RouteObligationScope, ...]:
    """Return call-obligation scopes in stable order."""

    return tuple(
        obligation.routeObligationScope
        for obligation in (
            routeObligationSet.callRouteObligationSet.callRouteObligations
        )
    )


class TestSimpleCircuitFixtures:
    """Structural verification for the simple-circuit corpus."""

    def test_root_recursive_models_one_chip_and_one_self_edge(self) -> None:
        """Root-only recursion should stay one canonical chip with one self edge."""

        diagnosticStack.stack_clear()
        circuitDocument, placedGrid, assignmentSet = placedGridAndAssignment_build(
            "root-recursive.yaml"
        )

        assert len(circuitDocument.circuitChipSet.chips) == 1
        assert len(circuitDocument.circuitCallSet.circuitCalls) == 1
        assert circuitDocument.callingDepth_calculate() == 1
        rootAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Loop.ts", functionName="loop()")
        )
        assert result_isOkCheck(rootAssignmentResult)
        assert rootAssignmentResult.value.routingZoneId.id == GridCoord(
            columnIndex=1,
            rowIndex=1,
        )
        assert rootAssignmentResult.value.terminalSide is RoutingZoneRegionSide.WEST

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocument,
                placedGrid,
            )
        )
        assert result_isOkCheck(routeObligationSetResult)
        assert set(callObligationScopes_getAll(routeObligationSetResult.value)) == {
            RouteObligationScope.ZONE_LOCAL
        }

    def test_three_deep_linear_assigns_forward_layers_without_back_edges(self) -> None:
        """Three-deep linear fixtures should map root/mid/leaf to simple layers."""

        diagnosticStack.stack_clear()
        circuitDocument, placedGrid, assignmentSet = placedGridAndAssignment_build(
            "three-deep-linear.yaml"
        )

        assert len(circuitDocument.circuitChipSet.chips) == 3
        assert circuitDocument.callingDepth_calculate() == 3
        rootAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Root.ts", functionName="root()")
        )
        midAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Mid.ts", functionName="mid()")
        )
        leafAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Leaf.ts", functionName="leaf()")
        )
        assert result_isOkCheck(rootAssignmentResult)
        assert result_isOkCheck(midAssignmentResult)
        assert result_isOkCheck(leafAssignmentResult)
        assert rootAssignmentResult.value.routingZoneId.id == GridCoord(1, 1)
        assert midAssignmentResult.value.routingZoneId.id == GridCoord(1, 1)
        assert leafAssignmentResult.value.routingZoneId.id == GridCoord(2, 1)

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocument,
                placedGrid,
            )
        )
        assert result_isOkCheck(routeObligationSetResult)
        assert callObligationScopes_getAll(routeObligationSetResult.value) == (
            RouteObligationScope.ZONE_LOCAL,
            RouteObligationScope.SEAM_CROSSING,
        )

    def test_recursive_each_layer_does_not_inflate_forward_depth_assignment(
        self,
    ) -> None:
        """Self edges should not move canonical chips out of their forward layers."""

        diagnosticStack.stack_clear()
        circuitDocument, placedGrid, assignmentSet = placedGridAndAssignment_build(
            "three-deep-recursive-each-layer.yaml"
        )

        assert len(circuitDocument.circuitChipSet.chips) == 3
        assert circuitDocument.callingDepth_calculate() == 3
        assert result_isOkCheck(
            assignmentSet.assignmentForChipResult_get(
                ChipId(moduleName="Root.ts", functionName="root()")
            )
        )
        midAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Mid.ts", functionName="mid()")
        )
        leafAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Leaf.ts", functionName="leaf()")
        )
        assert result_isOkCheck(midAssignmentResult)
        assert result_isOkCheck(leafAssignmentResult)
        assert midAssignmentResult.value.routingZoneId.id == GridCoord(1, 1)
        assert leafAssignmentResult.value.routingZoneId.id == GridCoord(2, 1)

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocument,
                placedGrid,
            )
        )
        assert result_isOkCheck(routeObligationSetResult)
        scopes = set(callObligationScopes_getAll(routeObligationSetResult.value))
        assert RouteObligationScope.ZONE_LOCAL in scopes
        assert RouteObligationScope.SEAM_CROSSING in scopes

    def test_ancestor_calls_target_existing_chips_without_cloning(self) -> None:
        """Ancestor references should target canonical chips and preserve layers."""

        diagnosticStack.stack_clear()
        circuitDocument, placedGrid, assignmentSet = placedGridAndAssignment_build(
            "three-deep-ancestor-call-each-layer.yaml"
        )

        assert len(circuitDocument.circuitChipSet.chips) == 3
        assert len(circuitDocument.circuitCallSet.circuitCalls) == 5
        assert circuitDocument.callingDepth_calculate() == 3
        assert result_isOkCheck(
            assignmentSet.assignmentForChipResult_get(
                ChipId(moduleName="Root.ts", functionName="root()")
            )
        )
        assert result_isOkCheck(
            assignmentSet.assignmentForChipResult_get(
                ChipId(moduleName="Mid.ts", functionName="mid()")
            )
        )
        assert result_isOkCheck(
            assignmentSet.assignmentForChipResult_get(
                ChipId(moduleName="Leaf.ts", functionName="leaf()")
            )
        )

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocument,
                placedGrid,
            )
        )
        assert result_isOkCheck(routeObligationSetResult)
        scopes = callObligationScopes_getAll(routeObligationSetResult.value)
        assert scopes.count(RouteObligationScope.ZONE_LOCAL) >= 2
        assert scopes.count(RouteObligationScope.SEAM_CROSSING) >= 2

    def test_ancestor_calls_with_recursion_preserve_canonical_depth_and_scope(
        self,
    ) -> None:
        """Combined backedges and self edges should not clone chips or inflate depth."""

        diagnosticStack.stack_clear()
        circuitDocument, placedGrid, assignmentSet = placedGridAndAssignment_build(
            "three-deep-ancestor-call-and-recursion.yaml"
        )

        assert len(circuitDocument.circuitChipSet.chips) == 3
        assert circuitDocument.callingDepth_calculate() == 3
        rootAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Root.ts", functionName="root()")
        )
        midAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Mid.ts", functionName="mid()")
        )
        leafAssignmentResult = assignmentSet.assignmentForChipResult_get(
            ChipId(moduleName="Leaf.ts", functionName="leaf()")
        )
        assert result_isOkCheck(rootAssignmentResult)
        assert result_isOkCheck(midAssignmentResult)
        assert result_isOkCheck(leafAssignmentResult)
        assert rootAssignmentResult.value.routingZoneId.id == GridCoord(1, 1)
        assert midAssignmentResult.value.routingZoneId.id == GridCoord(1, 1)
        assert leafAssignmentResult.value.routingZoneId.id == GridCoord(2, 1)

        routeObligationSetResult = (
            routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
                circuitDocument,
                placedGrid,
            )
        )
        assert result_isOkCheck(routeObligationSetResult)
        scopes = set(callObligationScopes_getAll(routeObligationSetResult.value))
        assert scopes == {
            RouteObligationScope.ZONE_LOCAL,
            RouteObligationScope.SEAM_CROSSING,
        }
