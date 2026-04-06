"""Grid-level long-haul routing models for the new SignalFlow engine.

This module defines the first solved artifact for `GRID_LONG_HAUL`
obligations. The goal is to realize world-scale path selection and explicit
planning-grid route geometry across multiple zones and interconnects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.chip import ChipRef
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import Result, resultErr_build, resultOk_build
from signalflow.models.routing_zone import (
    RoutingZoneId,
    RoutingZoneInterconnectId,
    RoutingZoneRegionId,
)
from signalflow.models.routing_zone_grid import RoutingZonePath
from signalflow.models.zone_route import RoutingZoneRoutePoint


class RoutingZoneGridRouteSolveKind(Enum):
    """Geometric class for one solved grid-level route."""

    LINEAR_HORIZONTAL = "linear_horizontal"
    LINEAR_VERTICAL = "linear_vertical"
    MANHATTAN_TURNING = "manhattan_turning"


@dataclass(frozen=True)
class RoutingZoneGridSolvedRoute:
    """One solved long-haul route across the routing-zone grid."""

    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    childCallIndex: int
    routingZonePath: RoutingZonePath
    traversedInterconnectIds: tuple[RoutingZoneInterconnectId, ...]
    traversedRegionIds: tuple[RoutingZoneRegionId, ...]
    routePoints: tuple[RoutingZoneRoutePoint, ...]
    solveKind: RoutingZoneGridRouteSolveKind


@dataclass(frozen=True)
class RoutingZoneGridSolvedRouteSet:
    """Modeled collection of solved grid-level routes."""

    routingZoneGridSolvedRoutes: tuple[RoutingZoneGridSolvedRoute, ...] = (
        field(default_factory=tuple)
    )

    def routesForChip_get(
        self,
        chipRef: ChipRef,
    ) -> tuple[RoutingZoneGridSolvedRoute, ...]:
        """Return all solved long-haul routes touching one chip."""

        return tuple(
            solvedRoute
            for solvedRoute in self.routingZoneGridSolvedRoutes
            if solvedRoute.sourceChipRef == chipRef
            or solvedRoute.destinationChipRef == chipRef
        )

    def routesForZone_get(
        self,
        routingZoneId: RoutingZoneId,
    ) -> tuple[RoutingZoneGridSolvedRoute, ...]:
        """Return all solved long-haul routes traversing one zone."""

        return tuple(
            solvedRoute
            for solvedRoute in self.routingZoneGridSolvedRoutes
            if routingZoneId in solvedRoute.routingZonePath.zoneIds
        )


def routingZoneGridSolvedRouteResult_build(
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    routingZonePath: RoutingZonePath,
    traversedInterconnectIds: tuple[RoutingZoneInterconnectId, ...],
    traversedRegionIds: tuple[RoutingZoneRegionId, ...],
    routePoints: tuple[RoutingZoneRoutePoint, ...],
    solveKind: RoutingZoneGridRouteSolveKind,
) -> Result[RoutingZoneGridSolvedRoute]:
    """Build one validated solved grid-level route."""

    if len(routingZonePath.zoneIds) < 2:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.grid_solver.route.path_too_short",
            message="Grid-level solved routes must traverse at least two zones",
        )
        return resultErr_build()
    if len(routePoints) < 2:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.grid_solver.route.too_few_points",
            message="Grid-level solved routes must contain at least two points",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneGridSolvedRoute(
            sourceChipRef=sourceChipRef,
            destinationChipRef=destinationChipRef,
            childCallIndex=childCallIndex,
            routingZonePath=routingZonePath,
            traversedInterconnectIds=traversedInterconnectIds,
            traversedRegionIds=traversedRegionIds,
            routePoints=routePoints,
            solveKind=solveKind,
        )
    )


def routingZoneGridSolvedRouteSetResult_build(
    routingZoneGridSolvedRoutes: tuple[RoutingZoneGridSolvedRoute, ...],
) -> Result[RoutingZoneGridSolvedRouteSet]:
    """Build the solved grid-level route set."""

    routeKeys: tuple[tuple[ChipRef, ChipRef, int], ...] = tuple(
        (
            solvedRoute.sourceChipRef,
            solvedRoute.destinationChipRef,
            solvedRoute.childCallIndex,
        )
        for solvedRoute in routingZoneGridSolvedRoutes
    )
    if len(set(routeKeys)) != len(routeKeys):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.grid_solver.route_set.duplicate_route",
            message=(
                "Solved grid-level routes must be unique by source, "
                "destination, and child index"
            ),
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneGridSolvedRouteSet(
            routingZoneGridSolvedRoutes=routingZoneGridSolvedRoutes
        )
    )
