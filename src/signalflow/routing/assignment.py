"""Chip-to-zone assignment builders for the new routing engine.

This module bridges validated circuit input and world topology. It currently
supports the simple major-axis regime where chip assignment follows propagation
depth through a one-dimensional `RoutingZoneGrid`.
"""
from __future__ import annotations

from signalflow.models import (
    GridCoord,
    Result,
    RoutingZoneAssignment,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneId,
    RoutingZoneLayer,
    RoutingZoneLayerSet,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneAssignmentSetResult_build,
    routingZoneLayerSetResult_buildFromCircuitDocument,
)
from signalflow.models.circuit import CircuitDocument
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


def routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
    circuitDocument: CircuitDocument,
    routingZoneGrid: RoutingZoneGrid,
) -> Result[RoutingZoneAssignmentSet]:
    """Build chip-to-zone assignment plan from circuit and world topology."""

    routingZoneLayerSetResult: Result[RoutingZoneLayerSet] = (
        routingZoneLayerSetResult_buildFromCircuitDocument(circuitDocument)
    )
    if not result_isOkCheck(routingZoneLayerSetResult):
        return resultErr_build()

    if not _simpleWorldMatchesCircuitDepth_check(
        circuitDocument=circuitDocument,
        routingZoneGrid=routingZoneGrid,
    ):
        return resultErr_build()

    routingZoneAssignmentsMutable: list[RoutingZoneAssignment] = []
    routingZoneLayer: RoutingZoneLayer
    for routingZoneLayer in routingZoneLayerSetResult.value.routingZoneLayers:
        routingZoneIdResult: Result[RoutingZoneId] = _routingZoneIdForDepthResult_build(
            depthIndex=routingZoneLayer.depthIndex,
            routingZoneGrid=routingZoneGrid,
        )
        if not result_isOkCheck(routingZoneIdResult):
            return resultErr_build()
        terminalSideResult: Result[RoutingZoneRegionSide] = (
            _terminalSideForDepthResult_build(
                depthIndex=routingZoneLayer.depthIndex,
                routingZoneGrid=routingZoneGrid,
            )
        )
        if not result_isOkCheck(terminalSideResult):
            return resultErr_build()
        chipRef = None
        for chipRef in routingZoneLayer.chipRefs:
            routingZoneAssignmentsMutable.append(
                RoutingZoneAssignment(
                    chipRef=chipRef,
                    routingZoneId=routingZoneIdResult.value,
                    terminalSide=terminalSideResult.value,
                )
            )

    return routingZoneAssignmentSetResult_build(
        routingZoneAssignments=tuple(routingZoneAssignmentsMutable)
    )


def _simpleWorldMatchesCircuitDepth_check(
    circuitDocument: CircuitDocument,
    routingZoneGrid: RoutingZoneGrid,
) -> bool:
    """Return whether the current world grid matches the simple assignment regime."""

    routingZoneCountNeeded: int = max(1, circuitDocument.callingDepth_calculate() - 1)

    if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        if not (
            routingZoneGrid.gridSize.columnIndex == routingZoneCountNeeded
            and routingZoneGrid.gridSize.rowIndex == 1
        ):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.assignment.world_shape.unsupported_for_simple_regime",
                message=(
                    "Current assignment builder supports only 1 x (depth - 1) "
                    "WestToEast worlds"
                ),
            )
            return False
        return True

    if not (
        routingZoneGrid.gridSize.columnIndex == 1
        and routingZoneGrid.gridSize.rowIndex == routingZoneCountNeeded
    ):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.assignment.world_shape.unsupported_for_simple_regime",
            message=(
                "Current assignment builder supports only (depth - 1) x 1 "
                "NorthToSouth worlds"
            ),
        )
        return False
    return True


def _routingZoneIdForDepthResult_build(
    depthIndex: int,
    routingZoneGrid: RoutingZoneGrid,
) -> Result[RoutingZoneId]:
    """Build the owning routing-zone id for one call-depth layer."""

    if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        zoneColumnIndex: int = (depthIndex // 2) + 1
        gridCoord = GridCoord(columnIndex=zoneColumnIndex, rowIndex=1)
    else:
        zoneRowIndex: int = (depthIndex // 2) + 1
        gridCoord = GridCoord(columnIndex=1, rowIndex=zoneRowIndex)

    zoneResult = routingZoneGrid.zoneAtCoordResult_get(gridCoord=gridCoord)
    if not result_isOkCheck(zoneResult):
        return resultErr_build()
    return resultOk_build(zoneResult.value.routingZoneId)


def _terminalSideForDepthResult_build(
    depthIndex: int,
    routingZoneGrid: RoutingZoneGrid,
) -> Result[RoutingZoneRegionSide]:
    """Build the terminal side for one call-depth layer."""

    if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        return resultOk_build(
            RoutingZoneRegionSide.WEST
            if depthIndex % 2 == 0
            else RoutingZoneRegionSide.EAST
        )
    return resultOk_build(
        RoutingZoneRegionSide.NORTH
        if depthIndex % 2 == 0
        else RoutingZoneRegionSide.SOUTH
    )
