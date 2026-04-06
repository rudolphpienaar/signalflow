"""Routing-zone grid models for SignalFlow.

This module defines the world-topology vocabulary that places routing zones in
2D grid coordinates and supports deterministic macro path selection.

Key components:
    - RoutingZoneGridPathPolicy: Deterministic macro path policy
    - RoutingZoneSet: Modeled collection of routing zones
    - RoutingZoneInterconnectSet: Modeled collection of interconnects
    - RoutingZonePath: Modeled zone-to-zone path
    - RoutingZoneGrid: World topology of routing zones and interconnects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.routing_zone import (
    GridCoord,
    RoutingZone,
    RoutingZoneId,
    RoutingZoneInterconnect,
    RoutingZoneInterconnectId,
    RoutingZoneSense,
)


class RoutingZoneGridPathPolicy(Enum):
    """Deterministic macro path policy for the routing-zone grid."""

    HORIZONTAL_FIRST = "horizontal_first"
    VERTICAL_FIRST = "vertical_first"


@dataclass(frozen=True)
class RoutingZoneSet:
    """Modeled collection of routing zones."""

    routingZones: tuple[RoutingZone, ...] = field(default_factory=tuple)

    def zoneResult_get(
        self, routingZoneId: RoutingZoneId
    ) -> Result[RoutingZone]:
        """Build one routing zone by id."""

        routingZone: RoutingZone
        for routingZone in self.routingZones:
            if routingZone.routingZoneId == routingZoneId:
                return resultOk_build(routingZone)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_grid.zone_set.missing_zone",
            message="Requested RoutingZone is absent from the world grid",
        )
        return resultErr_build()


@dataclass(frozen=True)
class RoutingZoneInterconnectSet:
    """Modeled collection of zone-to-zone interconnects."""

    routingZoneInterconnects: tuple[RoutingZoneInterconnect, ...] = field(
        default_factory=tuple
    )

    def interconnectBetweenZonesResult_get(
        self,
        sourceZoneId: RoutingZoneId,
        destinationZoneId: RoutingZoneId,
    ) -> Result[RoutingZoneInterconnect]:
        """Build the interconnect joining two neighboring zones."""

        routingZoneInterconnect: RoutingZoneInterconnect
        for routingZoneInterconnect in self.routingZoneInterconnects:
            if (
                routingZoneInterconnect.sourceZoneId == sourceZoneId
                and routingZoneInterconnect.destinationZoneId
                == destinationZoneId
            ) or (
                routingZoneInterconnect.sourceZoneId == destinationZoneId
                and routingZoneInterconnect.destinationZoneId == sourceZoneId
            ):
                return resultOk_build(routingZoneInterconnect)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_grid.interconnect_set.missing_interconnect",
            message="Requested RoutingZoneInterconnect is absent from the world grid",
        )
        return resultErr_build()


@dataclass(frozen=True)
class RoutingZonePath:
    """Modeled macro path across the routing-zone grid."""

    zoneIds: tuple[RoutingZoneId, ...]


@dataclass(frozen=True)
class RoutingZoneGrid:
    """World topology of routing zones and interconnects."""

    worldSense: RoutingZoneSense
    gridSize: GridCoord
    routingZoneSet: RoutingZoneSet
    moduleBoxPadding: int = 3
    routingZoneInterconnectSet: RoutingZoneInterconnectSet = field(
        default_factory=RoutingZoneInterconnectSet
    )

    def coordInBounds_isPresentCheck(self, gridCoord: GridCoord) -> bool:
        """Return whether one coordinate lies inside this world grid."""

        return (
            1 <= gridCoord.columnIndex <= self.gridSize.columnIndex
            and 1 <= gridCoord.rowIndex <= self.gridSize.rowIndex
        )

    def zoneAtCoordResult_get(
        self, gridCoord: GridCoord
    ) -> Result[RoutingZone]:
        """Build one routing zone directly from a grid coordinate."""

        if not self.coordInBounds_isPresentCheck(gridCoord):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.coord.out_of_bounds",
                message="Requested GridCoord lies outside the RoutingZoneGrid",
            )
            return resultErr_build()
        return self.routingZoneSet.zoneResult_get(RoutingZoneId(id=gridCoord))

    def interconnectAtCoordsResult_get(
        self,
        sourceGridCoord: GridCoord,
        destinationGridCoord: GridCoord,
    ) -> Result[RoutingZoneInterconnect]:
        """Build one interconnect directly from two neighboring coordinates."""

        if not self.coordInBounds_isPresentCheck(sourceGridCoord):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.interconnect.source_coord.out_of_bounds",
                message="Requested interconnect source GridCoord is outside the grid",
            )
            return resultErr_build()
        if not self.coordInBounds_isPresentCheck(destinationGridCoord):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code=(
                    "routing.zone_grid.interconnect.destination_coord.out_of_bounds"
                ),
                message=(
                    "Requested interconnect destination GridCoord is outside the "
                    "grid"
                ),
            )
            return resultErr_build()
        return (
            self.routingZoneInterconnectSet.interconnectBetweenZonesResult_get(
                RoutingZoneId(id=sourceGridCoord),
                RoutingZoneId(id=destinationGridCoord),
            )
        )

    def pathBetweenZonesResult_build(
        self,
        sourceZoneId: RoutingZoneId,
        destinationZoneId: RoutingZoneId,
        pathPolicy: RoutingZoneGridPathPolicy = (
            RoutingZoneGridPathPolicy.HORIZONTAL_FIRST
        ),
    ) -> Result[RoutingZonePath]:
        """Build a deterministic Manhattan path between two zones."""

        sourceZoneResult: Result[RoutingZone] = (
            self.routingZoneSet.zoneResult_get(sourceZoneId)
        )
        if not result_isOkCheck(sourceZoneResult):
            return resultErr_build()
        destinationZoneResult: Result[RoutingZone] = (
            self.routingZoneSet.zoneResult_get(destinationZoneId)
        )
        if not result_isOkCheck(destinationZoneResult):
            return resultErr_build()

        zoneIdsMutable: list[RoutingZoneId] = [sourceZoneId]
        currentZoneId: RoutingZoneId = sourceZoneId

        if pathPolicy is RoutingZoneGridPathPolicy.HORIZONTAL_FIRST:
            pathStepColumnsResult: Result[RoutingZoneId] = (
                self._pathStepColumnsResult_build(
                    currentZoneId,
                    destinationZoneId,
                    zoneIdsMutable,
                )
            )
            if not result_isOkCheck(pathStepColumnsResult):
                return resultErr_build()
            pathStepRowsResult: Result[RoutingZoneId] = (
                self._pathStepRowsResult_build(
                    pathStepColumnsResult.value,
                    destinationZoneId,
                    zoneIdsMutable,
                )
            )
            if not result_isOkCheck(pathStepRowsResult):
                return resultErr_build()
        else:
            pathStepRowsResult = self._pathStepRowsResult_build(
                currentZoneId,
                destinationZoneId,
                zoneIdsMutable,
            )
            if not result_isOkCheck(pathStepRowsResult):
                return resultErr_build()
            pathStepColumnsResult = self._pathStepColumnsResult_build(
                pathStepRowsResult.value,
                destinationZoneId,
                zoneIdsMutable,
            )
            if not result_isOkCheck(pathStepColumnsResult):
                return resultErr_build()

        return routingZonePathResult_build(zoneIds=tuple(zoneIdsMutable))

    def interconnectSequenceForPathResult_build(
        self,
        routingZonePath: RoutingZonePath,
    ) -> Result[RoutingZoneInterconnectSet]:
        """Build the interconnect sequence used by one routing-zone path."""

        routingZoneInterconnectsMutable: list[RoutingZoneInterconnect] = []
        currentZoneId: RoutingZoneId
        nextZoneId: RoutingZoneId
        for currentZoneId, nextZoneId in zip(
            routingZonePath.zoneIds,
            routingZonePath.zoneIds[1:],
            strict=False,
        ):
            interconnectResult: Result[RoutingZoneInterconnect] = (
                self.routingZoneInterconnectSet.interconnectBetweenZonesResult_get(
                    currentZoneId,
                    nextZoneId,
                )
            )
            if not result_isOkCheck(interconnectResult):
                return resultErr_build()
            routingZoneInterconnectsMutable.append(interconnectResult.value)

        return routingZoneInterconnectSetResult_build(
            routingZoneInterconnects=tuple(routingZoneInterconnectsMutable)
        )

    def _pathStepColumnsResult_build(
        self,
        sourceZoneId: RoutingZoneId,
        destinationZoneId: RoutingZoneId,
        zoneIdsMutable: list[RoutingZoneId],
    ) -> Result[RoutingZoneId]:
        """Append horizontal steps from source toward destination."""

        sourceGridCoordResult: Result[GridCoord] = (
            sourceZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(sourceGridCoordResult):
            return resultErr_build()
        destinationGridCoordResult: Result[GridCoord] = (
            destinationZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(destinationGridCoordResult):
            return resultErr_build()

        currentZoneId: RoutingZoneId = sourceZoneId
        currentGridCoord: GridCoord = sourceGridCoordResult.value
        destinationGridCoord: GridCoord = destinationGridCoordResult.value
        columnStep: int = (
            1
            if destinationGridCoord.columnIndex > currentGridCoord.columnIndex
            else -1
        )
        while currentGridCoord.columnIndex != destinationGridCoord.columnIndex:
            currentGridCoord = GridCoord(
                columnIndex=currentGridCoord.columnIndex + columnStep,
                rowIndex=currentGridCoord.rowIndex,
            )
            currentZoneId = RoutingZoneId(id=currentGridCoord)
            zoneResult: Result[RoutingZone] = (
                self.routingZoneSet.zoneResult_get(currentZoneId)
            )
            if not result_isOkCheck(zoneResult):
                return resultErr_build()
            zoneIdsMutable.append(currentZoneId)
        return resultOk_build(currentZoneId)

    def _pathStepRowsResult_build(
        self,
        sourceZoneId: RoutingZoneId,
        destinationZoneId: RoutingZoneId,
        zoneIdsMutable: list[RoutingZoneId],
    ) -> Result[RoutingZoneId]:
        """Append vertical steps from source toward destination."""

        sourceGridCoordResult: Result[GridCoord] = (
            sourceZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(sourceGridCoordResult):
            return resultErr_build()
        destinationGridCoordResult: Result[GridCoord] = (
            destinationZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(destinationGridCoordResult):
            return resultErr_build()

        currentZoneId: RoutingZoneId = sourceZoneId
        currentGridCoord: GridCoord = sourceGridCoordResult.value
        destinationGridCoord: GridCoord = destinationGridCoordResult.value
        rowStep: int = (
            1
            if destinationGridCoord.rowIndex > currentGridCoord.rowIndex
            else -1
        )
        while currentGridCoord.rowIndex != destinationGridCoord.rowIndex:
            currentGridCoord = GridCoord(
                columnIndex=currentGridCoord.columnIndex,
                rowIndex=currentGridCoord.rowIndex + rowStep,
            )
            currentZoneId = RoutingZoneId(id=currentGridCoord)
            zoneResult: Result[RoutingZone] = (
                self.routingZoneSet.zoneResult_get(currentZoneId)
            )
            if not result_isOkCheck(zoneResult):
                return resultErr_build()
            zoneIdsMutable.append(currentZoneId)
        return resultOk_build(currentZoneId)


def routingZoneSetResult_build(
    routingZones: tuple[RoutingZone, ...],
) -> Result[RoutingZoneSet]:
    """Build a validated routing-zone set."""

    routingZoneIds: tuple[RoutingZoneId, ...] = tuple(
        routingZone.routingZoneId for routingZone in routingZones
    )
    if len(set(routingZoneIds)) != len(routingZoneIds):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_grid.zone_set.duplicate_zone_id",
            message="RoutingZone ids must be unique in one grid",
        )
        return resultErr_build()
    routingZoneId: RoutingZoneId
    for routingZoneId in routingZoneIds:
        if not routingZoneId.worldGridAddress_isPresentCheck():
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.zone_set.invalid_address_type",
                message=(
                    "RoutingZoneGrid may contain only world-grid-addressed zones"
                ),
            )
            return resultErr_build()
    return resultOk_build(RoutingZoneSet(routingZones=routingZones))


def routingZoneInterconnectSetResult_build(
    routingZoneInterconnects: tuple[RoutingZoneInterconnect, ...],
) -> Result[RoutingZoneInterconnectSet]:
    """Build a validated routing-zone interconnect set."""

    interconnectIds: tuple[RoutingZoneInterconnectId, ...] = tuple(
        routingZoneInterconnect.routingZoneInterconnectId
        for routingZoneInterconnect in routingZoneInterconnects
    )
    if len(set(interconnectIds)) != len(interconnectIds):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_grid.interconnect_set.duplicate_interconnect_id",
            message="RoutingZoneInterconnect ids must be unique",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneInterconnectSet(
            routingZoneInterconnects=routingZoneInterconnects
        )
    )


def routingZonePathResult_build(
    zoneIds: tuple[RoutingZoneId, ...],
) -> Result[RoutingZonePath]:
    """Build a validated routing-zone path."""

    if not zoneIds:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_grid.path.empty",
            message="RoutingZonePath must contain at least one zone",
        )
        return resultErr_build()

    currentZoneId: RoutingZoneId
    nextZoneId: RoutingZoneId
    for currentZoneId, nextZoneId in zip(
        zoneIds,
        zoneIds[1:],
        strict=False,
    ):
        neighboringResult: Result[bool] = (
            currentZoneId.neighboringToZoneResult_build(nextZoneId)
        )
        if not result_isOkCheck(neighboringResult):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.path.invalid_address_type",
                message="RoutingZonePath must use world-grid-addressed zones",
            )
            return resultErr_build()
        if not neighboringResult.value:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.path.non_neighbor_step",
                message="RoutingZonePath must move by neighboring zones",
            )
            return resultErr_build()
    return resultOk_build(RoutingZonePath(zoneIds=zoneIds))


def routingZoneGridResult_build(
    worldSense: RoutingZoneSense,
    routingZoneSet: RoutingZoneSet,
    gridSize: GridCoord | None = None,
    moduleBoxPadding: int = 3,
    routingZoneInterconnectSet: RoutingZoneInterconnectSet | None = None,
) -> Result[RoutingZoneGrid]:
    """Build a validated routing-zone grid."""

    resolvedGridSize: GridCoord
    if gridSize is None:
        if not routingZoneSet.routingZones:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.missing_grid_size",
                message=(
                    "RoutingZoneGrid requires gridSize when routingZoneSet is empty"
                ),
            )
            return resultErr_build()
        resolvedGridSize = GridCoord(
            columnIndex=max(
                routingZone.routingZoneId.id.columnIndex
                for routingZone in routingZoneSet.routingZones
                if isinstance(routingZone.routingZoneId.id, GridCoord)
            ),
            rowIndex=max(
                routingZone.routingZoneId.id.rowIndex
                for routingZone in routingZoneSet.routingZones
                if isinstance(routingZone.routingZoneId.id, GridCoord)
            ),
        )
    else:
        resolvedGridSize = gridSize

    if resolvedGridSize.columnIndex <= 0 or resolvedGridSize.rowIndex <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_grid.invalid_grid_size",
            message="RoutingZoneGrid gridSize must be positive on both axes",
        )
        return resultErr_build()
    if moduleBoxPadding <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_grid.invalid_module_box_padding",
            message="RoutingZoneGrid moduleBoxPadding must be positive",
        )
        return resultErr_build()

    routingZone: RoutingZone
    for routingZone in routingZoneSet.routingZones:
        gridCoordResult: Result[GridCoord] = (
            routingZone.routingZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(gridCoordResult):
            return resultErr_build()
        if (
            gridCoordResult.value.columnIndex > resolvedGridSize.columnIndex
            or gridCoordResult.value.rowIndex > resolvedGridSize.rowIndex
        ):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.zone_out_of_bounds",
                message="RoutingZone lies outside the declared RoutingZoneGrid size",
            )
            return resultErr_build()

    routingZoneInterconnectSetValue: RoutingZoneInterconnectSet = (
        routingZoneInterconnectSet or RoutingZoneInterconnectSet()
    )
    routingZoneInterconnect: RoutingZoneInterconnect
    for (
        routingZoneInterconnect
    ) in routingZoneInterconnectSetValue.routingZoneInterconnects:
        sourceZoneResult: Result[RoutingZone] = routingZoneSet.zoneResult_get(
            routingZoneInterconnect.sourceZoneId
        )
        if not result_isOkCheck(sourceZoneResult):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.missing_interconnect_source_zone",
                message="RoutingZoneGrid interconnect source zone is absent",
            )
            return resultErr_build()
        destinationZoneResult: Result[RoutingZone] = (
            routingZoneSet.zoneResult_get(
                routingZoneInterconnect.destinationZoneId
            )
        )
        if not result_isOkCheck(destinationZoneResult):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_grid.missing_interconnect_destination_zone",
                message="RoutingZoneGrid interconnect destination zone is absent",
            )
            return resultErr_build()
    return resultOk_build(
        RoutingZoneGrid(
            worldSense=worldSense,
            gridSize=resolvedGridSize,
            routingZoneSet=routingZoneSet,
            moduleBoxPadding=moduleBoxPadding,
            routingZoneInterconnectSet=routingZoneInterconnectSetValue,
        )
    )
