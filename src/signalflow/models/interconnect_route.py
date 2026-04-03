"""Interconnect seam routing models for the new SignalFlow engine.

This module defines the first solved artifact for `SEAM_CROSSING` obligations.
The goal is to realize continuity across one `RoutingZoneInterconnect` using
the interconnect frame and the neighboring inter-routing fan-in/out regions.
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
from signalflow.models.zone_route import RoutingZoneRoutePoint


class RoutingZoneInterconnectRouteSolveKind(Enum):
    """Geometric class for one solved interconnect seam route."""

    STRAIGHT_SEAM = "straight_seam"
    OFFSET_SEAM = "offset_seam"
    STRAIGHT_SEAM_RETURN = "straight_seam_return"
    OFFSET_SEAM_RETURN = "offset_seam_return"


@dataclass(frozen=True)
class RoutingZoneInterconnectSolvedRoute:
    """One solved seam route across a single interconnect."""

    routingZoneInterconnectId: RoutingZoneInterconnectId
    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    childCallIndex: int
    solveKind: RoutingZoneInterconnectRouteSolveKind
    routePoints: tuple[RoutingZoneRoutePoint, ...]
    traversedRegionIds: tuple[RoutingZoneRegionId, ...]


@dataclass(frozen=True)
class RoutingZoneInterconnectSolvedRouteSet:
    """Modeled collection of solved seam routes."""

    routingZoneInterconnectSolvedRoutes: tuple[
        RoutingZoneInterconnectSolvedRoute, ...
    ] = field(default_factory=tuple)

    def routesForInterconnect_get(
        self,
        routingZoneInterconnectId: RoutingZoneInterconnectId,
    ) -> tuple[RoutingZoneInterconnectSolvedRoute, ...]:
        """Return all solved seam routes for one interconnect."""

        return tuple(
            solvedRoute
            for solvedRoute in self.routingZoneInterconnectSolvedRoutes
            if solvedRoute.routingZoneInterconnectId == routingZoneInterconnectId
        )

    def routesForZone_get(
        self,
        routingZoneId: RoutingZoneId,
    ) -> tuple[RoutingZoneInterconnectSolvedRoute, ...]:
        """Return all solved seam routes traversing one zone."""

        return tuple(
            solvedRoute
            for solvedRoute in self.routingZoneInterconnectSolvedRoutes
            if any(
                rid.routingZoneId == routingZoneId
                for rid in solvedRoute.traversedRegionIds
            )
        )

    def routesForChip_get(
        self,
        chipRef: ChipRef,
    ) -> tuple[RoutingZoneInterconnectSolvedRoute, ...]:
        """Return all solved seam routes touching one chip."""

        return tuple(
            solvedRoute
            for solvedRoute in self.routingZoneInterconnectSolvedRoutes
            if solvedRoute.sourceChipRef == chipRef
            or solvedRoute.destinationChipRef == chipRef
        )


def routingZoneInterconnectSolvedRouteResult_build(
    routingZoneInterconnectId: RoutingZoneInterconnectId,
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    solveKind: RoutingZoneInterconnectRouteSolveKind,
    routePoints: tuple[RoutingZoneRoutePoint, ...],
    traversedRegionIds: tuple[RoutingZoneRegionId, ...],
) -> Result[RoutingZoneInterconnectSolvedRoute]:
    """Build one validated solved seam route."""

    if len(routePoints) < 2:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.interconnect_solver.route.too_few_points",
            message="Solved interconnect routes must contain at least two points",
        )
        return resultErr_build()
    if not traversedRegionIds:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.interconnect_solver.route.missing_regions",
            message="Solved interconnect routes must traverse at least one region",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneInterconnectSolvedRoute(
            routingZoneInterconnectId=routingZoneInterconnectId,
            sourceChipRef=sourceChipRef,
            destinationChipRef=destinationChipRef,
            childCallIndex=childCallIndex,
            solveKind=solveKind,
            routePoints=routePoints,
            traversedRegionIds=traversedRegionIds,
        )
    )


def routingZoneInterconnectSolvedRouteSetResult_build(
    routingZoneInterconnectSolvedRoutes: tuple[RoutingZoneInterconnectSolvedRoute, ...],
) -> Result[RoutingZoneInterconnectSolvedRouteSet]:
    """Build the solved seam-route set."""

    routeKeys: tuple[tuple[ChipRef, ChipRef, int, RoutingZoneInterconnectRouteSolveKind], ...] = tuple(
        (
            solvedRoute.sourceChipRef,
            solvedRoute.destinationChipRef,
            solvedRoute.childCallIndex,
            solvedRoute.solveKind,
        )
        for solvedRoute in routingZoneInterconnectSolvedRoutes
    )
    if len(set(routeKeys)) != len(routeKeys):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.interconnect_solver.route_set.duplicate_route",
            message=(
                "Solved interconnect routes must be unique by source, "
                "destination, child index, and solve kind"
            ),
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneInterconnectSolvedRouteSet(
            routingZoneInterconnectSolvedRoutes=routingZoneInterconnectSolvedRoutes
        )
    )
