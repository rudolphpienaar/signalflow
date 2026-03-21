"""Zone-local routing models for the new SignalFlow engine.

This module defines the first solved artifact above placed `RoutingZone`
geometry. The goal is to realize `ZONE_LOCAL` call obligations as explicit
world-coordinate route polylines through the already planned zone regions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.chip import ChipRef
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import Result, resultErr_build, resultOk_build
from signalflow.models.routing_zone import RoutingZoneId, RoutingZoneRegionId


class RoutingZoneLocalRouteSolveKind(Enum):
    """Geometric class for one solved zone-local route.

    Opposite-side local obligations produce a top-half FORWARD route and a
    bottom-half RETURN route through one INTRA ring rectangle. The winding
    direction depends on which side owns the source chip.
    """

    CLOCKWISE_INTRA_FORWARD = "clockwise_intra_forward"
    CLOCKWISE_INTRA_RETURN = "clockwise_intra_return"
    INTER_PERIMETER_FORWARD = "inter_perimeter_forward"
    INTER_PERIMETER_RETURN = "inter_perimeter_return"
    SAME_SIDE_LOCAL = "same_side_local"


@dataclass(frozen=True)
class RoutingZoneRoutePoint:
    """One route waypoint in world-coordinate planning geometry."""

    horizontalIndex: int
    verticalIndex: int


@dataclass(frozen=True)
class RoutingZoneLocalSolvedRoute:
    """One solved zone-local route through a placed `RoutingZone`."""

    owningRoutingZoneId: RoutingZoneId
    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    childCallIndex: int
    solveKind: RoutingZoneLocalRouteSolveKind
    routePoints: tuple[RoutingZoneRoutePoint, ...]
    traversedRegionIds: tuple[RoutingZoneRegionId, ...]


@dataclass(frozen=True)
class RoutingZoneLocalSolvedRouteSet:
    """Modeled collection of solved zone-local routes."""

    routingZoneLocalSolvedRoutes: tuple[RoutingZoneLocalSolvedRoute, ...] = field(
        default_factory=tuple
    )

    def routesForZone_get(
        self,
        routingZoneId: RoutingZoneId,
    ) -> tuple[RoutingZoneLocalSolvedRoute, ...]:
        """Return all solved local routes for one routing zone."""

        return tuple(
            routingZoneLocalSolvedRoute
            for routingZoneLocalSolvedRoute in self.routingZoneLocalSolvedRoutes
            if routingZoneLocalSolvedRoute.owningRoutingZoneId == routingZoneId
        )

    def routesForChip_get(
        self,
        chipRef: ChipRef,
    ) -> tuple[RoutingZoneLocalSolvedRoute, ...]:
        """Return all solved local routes touching one chip."""

        return tuple(
            routingZoneLocalSolvedRoute
            for routingZoneLocalSolvedRoute in self.routingZoneLocalSolvedRoutes
            if routingZoneLocalSolvedRoute.sourceChipRef == chipRef
            or routingZoneLocalSolvedRoute.destinationChipRef == chipRef
        )


def routingZoneRoutePointResult_build(
    horizontalIndex: int,
    verticalIndex: int,
) -> Result[RoutingZoneRoutePoint]:
    """Build one validated world-coordinate route point."""

    if horizontalIndex < 0 or verticalIndex < 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_solver.route_point.negative_coordinate",
            message="RoutingZoneRoutePoint coordinates must be non-negative",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneRoutePoint(
            horizontalIndex=horizontalIndex,
            verticalIndex=verticalIndex,
        )
    )


def routingZoneLocalSolvedRouteResult_build(
    owningRoutingZoneId: RoutingZoneId,
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    solveKind: RoutingZoneLocalRouteSolveKind,
    routePoints: tuple[RoutingZoneRoutePoint, ...],
    traversedRegionIds: tuple[RoutingZoneRegionId, ...],
) -> Result[RoutingZoneLocalSolvedRoute]:
    """Build one validated solved zone-local route."""

    if len(routePoints) < 2:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_solver.local_route.too_few_points",
            message="Solved zone-local routes must contain at least two points",
        )
        return resultErr_build()
    if not traversedRegionIds:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_solver.local_route.missing_regions",
            message="Solved zone-local routes must traverse at least one region",
        )
        return resultErr_build()
    routingZoneRegionId: RoutingZoneRegionId
    for routingZoneRegionId in traversedRegionIds:
        if routingZoneRegionId.routingZoneId != owningRoutingZoneId:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.cross_zone_region_reference",
                message=(
                    "Solved zone-local routes may only reference regions owned by "
                    "their routing zone"
                ),
            )
            return resultErr_build()
    return resultOk_build(
        RoutingZoneLocalSolvedRoute(
            owningRoutingZoneId=owningRoutingZoneId,
            sourceChipRef=sourceChipRef,
            destinationChipRef=destinationChipRef,
            childCallIndex=childCallIndex,
            solveKind=solveKind,
            routePoints=routePoints,
            traversedRegionIds=traversedRegionIds,
        )
    )


def routingZoneLocalSolvedRouteSetResult_build(
    routingZoneLocalSolvedRoutes: tuple[RoutingZoneLocalSolvedRoute, ...],
) -> Result[RoutingZoneLocalSolvedRouteSet]:
    """Build the solved zone-local route set."""

    routeKeys: (
        tuple[tuple[ChipRef, ChipRef, int, RoutingZoneLocalRouteSolveKind], ...]
    ) = tuple(
        (
            routingZoneLocalSolvedRoute.sourceChipRef,
            routingZoneLocalSolvedRoute.destinationChipRef,
            routingZoneLocalSolvedRoute.childCallIndex,
            routingZoneLocalSolvedRoute.solveKind,
        )
        for routingZoneLocalSolvedRoute in routingZoneLocalSolvedRoutes
    )
    if len(set(routeKeys)) != len(routeKeys):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_solver.local_route_set.duplicate_route",
            message=(
                "Solved zone-local routes must be unique by source, destination, "
                "child index, and solve kind"
            ),
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneLocalSolvedRouteSet(
            routingZoneLocalSolvedRoutes=routingZoneLocalSolvedRoutes
        )
    )
