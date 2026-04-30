"""Chip-to-zone assignment builders for the new routing engine.

This module bridges validated circuit input and world topology. The current
policy is deterministic and conservative:

- `WestToEast` worlds consume zones in serpentine row-major order
- `NorthToSouth` worlds consume zones in serpentine column-major order

This keeps rectangular worlds usable without inventing a second placement DSL.
"""

from __future__ import annotations

from signalflow.config.world_size import worldGridSize_calculate
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
    callingStackResult_buildFromCircuitDocument,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneAssignmentSetResult_build,
    routingZoneLayerSetResult_buildFromCircuitDocument,
)
from signalflow.models.circuit import CircuitDocument
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


def routingZoneAssignmentsResult_build(
    circuitDocument: CircuitDocument,
    routingZoneGrid: RoutingZoneGrid,
) -> Result[RoutingZoneAssignmentSet]:
    """Build chip-to-zone assignments from circuit and world topology."""

    return routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
        circuitDocument,
        routingZoneGrid,
    )


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

    if not _worldHasEnoughZoneCapacityForCircuit_check(
        circuitDocument=circuitDocument,
        routingZoneGrid=routingZoneGrid,
    ):
        return resultErr_build()

    routingZoneAssignmentsMutable: list[RoutingZoneAssignment] = []
    routingZoneLayer: RoutingZoneLayer
    for routingZoneLayer in routingZoneLayerSetResult.value.routingZoneLayers:
        routingZoneIdResult: Result[RoutingZoneId] = (
            _routingZoneIdForDepthResult_build(
                depthIndex=routingZoneLayer.depthIndex,
                routingZoneGrid=routingZoneGrid,
            )
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


def _worldHasEnoughZoneCapacityForCircuit_check(
    circuitDocument: CircuitDocument,
    routingZoneGrid: RoutingZoneGrid,
) -> bool:
    """Return whether the current world grid can host the needed zone count."""

    callingStackResult = callingStackResult_buildFromCircuitDocument(
        circuitDocument
    )
    if not result_isOkCheck(callingStackResult):
        return False
    routingZoneCountNeeded: int = worldGridSize_calculate(
        callingStackResult.value.bandCount_calculate()
    )
    routingZoneCapacity: int = (
        routingZoneGrid.gridSize.columnIndex
        * routingZoneGrid.gridSize.rowIndex
    )
    if routingZoneCapacity < routingZoneCountNeeded:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.assignment.world_shape.insufficient_zone_capacity",
            message=(
                "RoutingZoneGrid does not contain enough zones "
                "for the circuit "
                "calling depth under the current assignment policy"
            ),
            context=(str(routingZoneCountNeeded), str(routingZoneCapacity)),
        )
        return False
    return True


def _routingZoneIdForDepthResult_build(
    depthIndex: int,
    routingZoneGrid: RoutingZoneGrid,
) -> Result[RoutingZoneId]:
    """Build the owning routing-zone id for one call-depth layer."""

    traversalSequence: tuple[GridCoord, ...] = _zoneTraversalSequence_build(
        routingZoneGrid=routingZoneGrid
    )
    traversalIndex: int = depthIndex // 2
    if traversalIndex >= len(traversalSequence):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.assignment.depth.layer_out_of_world_bounds",
            message=(
                "Call depth layer maps beyond the available RoutingZone path"
            ),
            context=(str(depthIndex), str(traversalIndex)),
        )
        return resultErr_build()
    gridCoord: GridCoord = traversalSequence[traversalIndex]

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


def _zoneTraversalSequence_build(
    routingZoneGrid: RoutingZoneGrid,
) -> tuple[GridCoord, ...]:
    """Build the deterministic major-axis traversal over the world grid."""

    traversalMutable: list[GridCoord] = []
    if routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST:
        rowIndex: int
        for rowIndex in range(1, routingZoneGrid.gridSize.rowIndex + 1):
            columnSequence: range
            if rowIndex % 2 == 1:
                columnSequence = range(
                    1, routingZoneGrid.gridSize.columnIndex + 1
                )
            else:
                columnSequence = range(
                    routingZoneGrid.gridSize.columnIndex,
                    0,
                    -1,
                )
            columnIndex: int
            for columnIndex in columnSequence:
                traversalMutable.append(
                    GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
                )
        return tuple(traversalMutable)

    columnIndex: int
    for columnIndex in range(1, routingZoneGrid.gridSize.columnIndex + 1):
        rowSequence: range
        if columnIndex % 2 == 1:
            rowSequence = range(1, routingZoneGrid.gridSize.rowIndex + 1)
        else:
            rowSequence = range(
                routingZoneGrid.gridSize.rowIndex,
                0,
                -1,
            )
        rowIndex: int
        for rowIndex in rowSequence:
            traversalMutable.append(
                GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            )
    return tuple(traversalMutable)
