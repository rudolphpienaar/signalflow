"""Route realization for the new SignalFlow engine.

This module converts solved-route polylines (RoutingZoneRoutePoint sequences)
into modeled RealizedRoute objects.  A RealizedRoute is a collection of
per-cell TrackCell entries ready for canvas projection.

Realization is pure geometry: it operates only on world-coordinate waypoints
and emits TrackCells via the Phase 6 track algebra.  No canvas writes happen
here.

Route Sense
-----------
A RouteSense tag (FORWARD / BACK / SELF) is carried on every RealizedRoute
and controls color and presentation in the rendering layer.  It does not
change which cells the route occupies or which glyph each cell shows.  Two
routes with identical waypoints but different senses realize to the same
per-cell TrackCell set — identical topology under different semantics uses
the same path.

Lane Allocation and Sweep
--------------------------
Lane positions are determined by the upstream solvers (zone_solver,
interconnect_solver, grid_solver), which use chip orderIndex as the row or
column offset within each routing region.  This module consumes those
already-assigned positions without re-assigning them.  Sweep order (the
order in which routes contribute to a combined cell map) follows the
declaration order in the input set so that lane numbering is stable across
route variants.

Polyline Expansion
------------------
Each consecutive waypoint pair (Pi → Pi+1) contributes one axis-aligned
segment.  At each cell along a segment the wire apertures are recorded as
TrackDirection entries:

- Horizontal segment going right (c0 < c1):
    leftmost cell  → EAST only
    interior cells → EAST + WEST
    rightmost cell → WEST only

- Horizontal segment going left (c0 > c1):
    leftmost cell  → WEST only
    interior cells → EAST + WEST
    rightmost cell → EAST only

- Vertical segment going down (r0 < r1):
    topmost cell    → SOUTH only
    interior cells  → NORTH + SOUTH
    bottommost cell → NORTH only

- Vertical segment going up (r0 > r1):
    topmost cell    → NORTH only
    interior cells  → NORTH + SOUTH
    bottommost cell → SOUTH only

Turn cells (shared by two consecutive segments) accumulate contributions
from both segments.  The track merge algebra unions the direction sets, so
a right-then-down turn produces {EAST, SOUTH} → ┌ automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.chip import ChipRef
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.interconnect_route import (
    RoutingZoneInterconnectSolvedRoute,
    RoutingZoneInterconnectSolvedRouteSet,
)
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.zone_route import (
    RoutingZoneLocalSolvedRoute,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneRoutePoint,
)
from signalflow.routing.track import TrackCell, TrackDirection, trackCell_build


class RouteSense(Enum):
    """Semantic classification for one realized route.

    Attributes:
        FORWARD: Normal forward call edge (parent → child).
        BACK: Ancestor / back-edge call (child calls an ancestor).
        SELF: Self-loop call (chip calls itself).
    """

    FORWARD = "forward"
    BACK = "back"
    SELF = "self"


@dataclass(frozen=True)
class RealizedRouteCell:
    """One resolved track-cell entry in a realized route.

    Attributes:
        worldRow: World-coordinate vertical index.
        worldCol: World-coordinate horizontal index.
        trackCell: Resolved box-drawing cell for this position.
    """

    worldRow: int
    worldCol: int
    trackCell: TrackCell


@dataclass(frozen=True)
class RealizedRoute:
    """Fully realized route: metadata plus ordered per-cell geometry.

    Attributes:
        sourceChipRef: Originating chip.
        destinationChipRef: Target chip.
        childCallIndex: Call-sequence index for disambiguation.
        routeSense: Semantic classification; does not affect cell geometry.
        cells: Ordered tuple of realized track cells (sorted by row, col).
    """

    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    childCallIndex: int
    routeSense: RouteSense
    cells: tuple[RealizedRouteCell, ...]

    def cellAt_get(self, worldRow: int, worldCol: int) -> TrackCell | None:
        """Return the TrackCell at (worldRow, worldCol), or None if absent.

        Args:
            worldRow: World-coordinate vertical index to look up.
            worldCol: World-coordinate horizontal index to look up.

        Returns:
            The resolved TrackCell at the given position, or None.
        """

        for c in self.cells:
            if c.worldRow == worldRow and c.worldCol == worldCol:
                return c.trackCell
        return None


@dataclass(frozen=True)
class RealizedRouteSet:
    """Modeled collection of realized routes.

    Attributes:
        realizedRoutes: All realized routes in this set.
    """

    realizedRoutes: tuple[RealizedRoute, ...] = field(default_factory=tuple)

    def routesForChip_get(
        self,
        chipRef: ChipRef,
    ) -> tuple[RealizedRoute, ...]:
        """Return all realized routes that touch one chip.

        Args:
            chipRef: Chip reference to look up.

        Returns:
            Tuple of RealizedRoute objects where the chip is either the
            source or the destination.
        """

        return tuple(
            r
            for r in self.realizedRoutes
            if r.sourceChipRef == chipRef or r.destinationChipRef == chipRef
        )

    def mergedCellMap_get(self) -> dict[tuple[int, int], TrackCell]:
        """Merge all routes into one (worldRow, worldCol) → TrackCell map.

        Overlapping routes are combined via the track merge algebra so that
        intersecting wires produce the correct tee or cross glyphs.

        Returns:
            Dictionary mapping (worldRow, worldCol) positions to resolved
            TrackCells that represent the union of all route wires.
        """

        dirAccum: dict[tuple[int, int], set[TrackDirection]] = {}
        for route in self.realizedRoutes:
            for cell in route.cells:
                key = (cell.worldRow, cell.worldCol)
                if key not in dirAccum:
                    dirAccum[key] = set()
                dirAccum[key] |= cell.trackCell.directions
        return {
            key: trackCell_build(frozenset(dirs)) for key, dirs in dirAccum.items()
        }


def routePoints_realize(
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    routePoints: tuple[RoutingZoneRoutePoint, ...],
    routeSense: RouteSense = RouteSense.FORWARD,
) -> Result[RealizedRoute]:
    """Realize one solved route polyline into per-cell TrackCells.

    Expands each consecutive waypoint pair into one axis-aligned segment and
    records the wire apertures (TrackDirection entries) at every cell along
    the segment.  Turn cells accumulate contributions from both their
    incoming and outgoing segments, so the correct elbow or tee glyph is
    resolved automatically by the track merge algebra.

    Args:
        sourceChipRef: Originating chip reference.
        destinationChipRef: Target chip reference.
        childCallIndex: Call-sequence index for disambiguation.
        routePoints: Ordered world-coordinate waypoints (at least two).
        routeSense: Semantic tag; does not affect cell geometry.

    Returns:
        Successful result containing the RealizedRoute, or a failed result
        if the polyline contains fewer than two points or a diagonal segment.
    """

    if len(routePoints) < 2:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.route.realize.too_few_points",
            message="Route polylines must contain at least two waypoints",
        )
        return resultErr_build()

    dirMap: dict[tuple[int, int], set[TrackDirection]] = {}

    def _addDir(row: int, col: int, direction: TrackDirection) -> None:
        key = (row, col)
        if key not in dirMap:
            dirMap[key] = set()
        dirMap[key].add(direction)

    for i in range(len(routePoints) - 1):
        p0 = routePoints[i]
        p1 = routePoints[i + 1]
        r0: int = p0.verticalIndex
        c0: int = p0.horizontalIndex
        r1: int = p1.verticalIndex
        c1: int = p1.horizontalIndex

        if r0 == r1 and c0 == c1:
            # Zero-length segment between coincident waypoints — skip.
            continue

        if r0 != r1 and c0 != c1:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.route.realize.diagonal_segment",
                message=(
                    "Route polylines may only contain axis-aligned segments; "
                    "diagonal segment detected"
                ),
                context=(str(r0), str(c0), str(r1), str(c1)),
            )
            return resultErr_build()

        if r0 == r1:
            # Horizontal segment.
            if c0 < c1:
                # Going right (east).
                _addDir(r0, c0, TrackDirection.EAST)
                for c in range(c0 + 1, c1):
                    _addDir(r0, c, TrackDirection.EAST)
                    _addDir(r0, c, TrackDirection.WEST)
                _addDir(r0, c1, TrackDirection.WEST)
            else:
                # Going left (west); c0 > c1.
                _addDir(r0, c0, TrackDirection.WEST)
                for c in range(c1 + 1, c0):
                    _addDir(r0, c, TrackDirection.EAST)
                    _addDir(r0, c, TrackDirection.WEST)
                _addDir(r0, c1, TrackDirection.EAST)
        else:
            # Vertical segment; c0 == c1.
            if r0 < r1:
                # Going down (south).
                _addDir(r0, c0, TrackDirection.SOUTH)
                for r in range(r0 + 1, r1):
                    _addDir(r, c0, TrackDirection.NORTH)
                    _addDir(r, c0, TrackDirection.SOUTH)
                _addDir(r1, c0, TrackDirection.NORTH)
            else:
                # Going up (north); r0 > r1.
                _addDir(r0, c0, TrackDirection.NORTH)
                for r in range(r1 + 1, r0):
                    _addDir(r, c0, TrackDirection.NORTH)
                    _addDir(r, c0, TrackDirection.SOUTH)
                _addDir(r1, c0, TrackDirection.SOUTH)

    cells: tuple[RealizedRouteCell, ...] = tuple(
        RealizedRouteCell(
            worldRow=row,
            worldCol=col,
            trackCell=trackCell_build(frozenset(dirs)),
        )
        for (row, col), dirs in sorted(dirMap.items())
    )

    return resultOk_build(
        RealizedRoute(
            sourceChipRef=sourceChipRef,
            destinationChipRef=destinationChipRef,
            childCallIndex=childCallIndex,
            routeSense=routeSense,
            cells=cells,
        )
    )


def realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
    solvedRouteSet: RoutingZoneLocalSolvedRouteSet,
    defaultRouteSense: RouteSense = RouteSense.FORWARD,
) -> Result[RealizedRouteSet]:
    """Build a RealizedRouteSet from a set of solved zone-local routes.

    Each solved route's waypoint polyline is expanded into per-cell
    TrackCells using the polyline realization algorithm.

    Args:
        solvedRouteSet: Solved zone-local routes from the zone solver.
        defaultRouteSense: Sense tag applied to every realized route.
            Defaults to FORWARD; caller may supply BACK or SELF when the
            circuit document supplies edge-sense information.

    Returns:
        Successful result containing the RealizedRouteSet, or a failed
        result if any individual route polyline cannot be realized.
    """

    realizedRoutesMutable: list[RealizedRoute] = []
    solvedRoute: RoutingZoneLocalSolvedRoute
    for solvedRoute in solvedRouteSet.routingZoneLocalSolvedRoutes:
        realizedResult: Result[RealizedRoute] = routePoints_realize(
            sourceChipRef=solvedRoute.sourceChipRef,
            destinationChipRef=solvedRoute.destinationChipRef,
            childCallIndex=solvedRoute.childCallIndex,
            routePoints=solvedRoute.routePoints,
            routeSense=defaultRouteSense,
        )
        if not result_isOkCheck(realizedResult):
            return resultErr_build()
        realizedRoutesMutable.append(realizedResult.value)

    return resultOk_build(
        RealizedRouteSet(realizedRoutes=tuple(realizedRoutesMutable))
    )


def realizedRouteSetResult_buildFromInterconnectSolvedRouteSet(
    solvedRouteSet: RoutingZoneInterconnectSolvedRouteSet,
    defaultRouteSense: RouteSense = RouteSense.FORWARD,
) -> Result[RealizedRouteSet]:
    """Build a RealizedRouteSet from a set of solved seam-crossing routes.

    Each solved seam route's waypoint polyline is expanded into per-cell
    TrackCells using the same polyline realization algorithm used for
    zone-local routes.

    Args:
        solvedRouteSet: Solved seam-crossing routes from the interconnect solver.
        defaultRouteSense: Sense tag applied to every realized route.

    Returns:
        Successful result containing the RealizedRouteSet, or a failed
        result if any individual route polyline cannot be realized.
    """

    realizedRoutesMutable: list[RealizedRoute] = []
    solvedRoute: RoutingZoneInterconnectSolvedRoute
    for solvedRoute in solvedRouteSet.routingZoneInterconnectSolvedRoutes:
        realizedResult: Result[RealizedRoute] = routePoints_realize(
            sourceChipRef=solvedRoute.sourceChipRef,
            destinationChipRef=solvedRoute.destinationChipRef,
            childCallIndex=solvedRoute.childCallIndex,
            routePoints=solvedRoute.routePoints,
            routeSense=defaultRouteSense,
        )
        if not result_isOkCheck(realizedResult):
            return resultErr_build()
        realizedRoutesMutable.append(realizedResult.value)

    return resultOk_build(
        RealizedRouteSet(realizedRoutes=tuple(realizedRoutesMutable))
    )
