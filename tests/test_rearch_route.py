"""Tests for route realization (Phase 7).

Covers: horizontal segment expansion, vertical segment expansion, elbow
formation, dogleg (Z-shape), pass-through overlap, RouteSense invariance,
error cases, RealizedRouteSet.mergedCellMap_get, and zone-local builder.
"""
from __future__ import annotations

from signalflow.models.chip import ChipId, ChipRef
from signalflow.models.result import result_isOkCheck
from signalflow.models.zone_route import (
    RoutingZoneRoutePoint,
    routingZoneLocalSolvedRouteSetResult_build,
)
from signalflow.routing.route import (
    RealizedRoute,
    RealizedRouteSet,
    RouteSense,
    realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet,
    routePoints_realize,
)
from signalflow.routing.track import TrackDirection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_N = TrackDirection.NORTH
_S = TrackDirection.SOUTH
_E = TrackDirection.EAST
_W = TrackDirection.WEST


def _chip(module: str, func: str) -> ChipRef:
    return ChipRef(chipId=ChipId(moduleName=module, functionName=func))


def _pt(col: int, row: int) -> RoutingZoneRoutePoint:
    """Build a route point: column = horizontalIndex, row = verticalIndex."""
    return RoutingZoneRoutePoint(horizontalIndex=col, verticalIndex=row)


_SRC = _chip("M", "src")
_DST = _chip("M", "dst")


def _realize(
    points: list[tuple[int, int]],
    sense: RouteSense = RouteSense.FORWARD,
    child_idx: int = 0,
) -> RealizedRoute:
    """Convenience: realize a list of (col, row) tuples."""
    result = routePoints_realize(
        sourceChipRef=_SRC,
        destinationChipRef=_DST,
        childCallIndex=child_idx,
        routePoints=tuple(_pt(c, r) for c, r in points),
        routeSense=sense,
    )
    assert result_isOkCheck(result), "routePoints_realize unexpectedly failed"
    return result.value


def _cellMap(route: RealizedRoute) -> dict[tuple[int, int], frozenset[TrackDirection]]:
    """Return a {(row, col): directions} dict for easy assertions."""
    return {(c.worldRow, c.worldCol): c.trackCell.directions for c in route.cells}


# ---------------------------------------------------------------------------
# Horizontal segments
# ---------------------------------------------------------------------------


class TestHorizontalSegment:
    def test_two_cell_segment_right(self) -> None:
        # (col=0,row=0) → (col=1,row=0): two adjacent cells
        route = _realize([(0, 0), (1, 0)])
        m = _cellMap(route)
        assert m[(0, 0)] == frozenset({_E})
        assert m[(0, 1)] == frozenset({_W})

    def test_three_cell_segment_right(self) -> None:
        route = _realize([(0, 0), (2, 0)])
        m = _cellMap(route)
        assert m[(0, 0)] == frozenset({_E})
        assert m[(0, 1)] == frozenset({_E, _W})
        assert m[(0, 2)] == frozenset({_W})

    def test_two_cell_segment_left(self) -> None:
        route = _realize([(2, 0), (1, 0)])
        m = _cellMap(route)
        assert m[(0, 2)] == frozenset({_W})
        assert m[(0, 1)] == frozenset({_E})

    def test_three_cell_segment_left(self) -> None:
        route = _realize([(3, 0), (1, 0)])
        m = _cellMap(route)
        assert m[(0, 3)] == frozenset({_W})
        assert m[(0, 2)] == frozenset({_E, _W})
        assert m[(0, 1)] == frozenset({_E})

    def test_cell_count_equals_span(self) -> None:
        route = _realize([(0, 0), (4, 0)])
        assert len(route.cells) == 5  # cols 0..4


# ---------------------------------------------------------------------------
# Vertical segments
# ---------------------------------------------------------------------------


class TestVerticalSegment:
    def test_two_cell_segment_down(self) -> None:
        route = _realize([(0, 0), (0, 1)])
        m = _cellMap(route)
        assert m[(0, 0)] == frozenset({_S})
        assert m[(1, 0)] == frozenset({_N})

    def test_three_cell_segment_down(self) -> None:
        route = _realize([(0, 0), (0, 2)])
        m = _cellMap(route)
        assert m[(0, 0)] == frozenset({_S})
        assert m[(1, 0)] == frozenset({_N, _S})
        assert m[(2, 0)] == frozenset({_N})

    def test_two_cell_segment_up(self) -> None:
        route = _realize([(0, 2), (0, 1)])
        m = _cellMap(route)
        assert m[(2, 0)] == frozenset({_N})
        assert m[(1, 0)] == frozenset({_S})

    def test_three_cell_segment_up(self) -> None:
        route = _realize([(0, 3), (0, 1)])
        m = _cellMap(route)
        assert m[(3, 0)] == frozenset({_N})
        assert m[(2, 0)] == frozenset({_N, _S})
        assert m[(1, 0)] == frozenset({_S})


# ---------------------------------------------------------------------------
# Elbow / corner formation  (two segments meeting at one cell)
# ---------------------------------------------------------------------------


class TestElbowFormation:
    """An L-shaped route: horizontal then vertical or vice versa."""

    def test_right_then_down_elbow(self) -> None:
        # (0,0) → (2,0) → (2,2)  — go right 2, then down 2
        route = _realize([(0, 0), (2, 0), (2, 2)])
        m = _cellMap(route)
        # Horizontal start: (row=0, col=0) → EAST only
        assert m[(0, 0)] == frozenset({_E})
        # Interior horizontal: (row=0, col=1) → E+W
        assert m[(0, 1)] == frozenset({_E, _W})
        # Turn at (row=0, col=2): WEST from horizontal + SOUTH from vertical → ┐
        assert m[(0, 2)] == frozenset({_W, _S})
        # Interior vertical: (row=1, col=2)
        assert m[(1, 2)] == frozenset({_N, _S})
        # Vertical end: (row=2, col=2) → NORTH only
        assert m[(2, 2)] == frozenset({_N})

    def test_down_then_right_elbow(self) -> None:
        # (0,0) → (0,2) → (2,2) — go down 2, then right 2
        route = _realize([(0, 0), (0, 2), (2, 2)])
        m = _cellMap(route)
        assert m[(0, 0)] == frozenset({_S})
        assert m[(1, 0)] == frozenset({_N, _S})
        # Turn: NORTH from above + EAST from right → └
        assert m[(2, 0)] == frozenset({_N, _E})
        assert m[(2, 1)] == frozenset({_E, _W})
        assert m[(2, 2)] == frozenset({_W})

    def test_all_four_elbows(self) -> None:
        # All four canonical elbow shapes, verified by direction set.
        # Points are (col, row). The corner cell is where two segments meet.

        # ┐ = {S, W}: go right then down — corner at top-right
        # (col=0,row=0)→(col=2,row=0)→(col=2,row=2): corner at (row=0, col=2)
        r1 = _realize([(0, 0), (2, 0), (2, 2)])
        assert _cellMap(r1)[(0, 2)] == frozenset({_W, _S})  # ┐

        # ┘ = {N, W}: go right then up — corner at bottom-right
        # (col=0,row=2)→(col=2,row=2)→(col=2,row=0): corner at (row=2, col=2)
        r2 = _realize([(0, 2), (2, 2), (2, 0)])
        assert _cellMap(r2)[(2, 2)] == frozenset({_W, _N})  # ┘

        # ┌ = {S, E}: go left then down — corner at top-left
        # (col=2,row=0)→(col=0,row=0)→(col=0,row=2): corner at (row=0, col=0)
        r3 = _realize([(2, 0), (0, 0), (0, 2)])
        assert _cellMap(r3)[(0, 0)] == frozenset({_E, _S})  # ┌

        # └ = {N, E}: go left then up — corner at bottom-left
        # (col=2,row=2)→(col=0,row=2)→(col=0,row=0): corner at (row=2, col=0)
        r4 = _realize([(2, 2), (0, 2), (0, 0)])
        assert _cellMap(r4)[(2, 0)] == frozenset({_E, _N})  # └


# ---------------------------------------------------------------------------
# Dogleg / Z-shape  (horizontal–vertical–horizontal)
# ---------------------------------------------------------------------------


class TestDogleg:
    """A dogleg route offsets the wire vertically in a longitude region."""

    def test_z_shape_right_down_right(self) -> None:
        # (0,0)→(2,0)→(2,2)→(4,2): right 2, down 2, right 2
        route = _realize([(0, 0), (2, 0), (2, 2), (4, 2)])
        m = _cellMap(route)
        # First horizontal arm start
        assert m[(0, 0)] == frozenset({_E})
        # First turn (row=0, col=2)
        assert m[(0, 2)] == frozenset({_W, _S})
        # Vertical interior
        assert m[(1, 2)] == frozenset({_N, _S})
        # Second turn (row=2, col=2)
        assert m[(2, 2)] == frozenset({_N, _E})
        # Second horizontal arm end
        assert m[(2, 4)] == frozenset({_W})

    def test_z_shape_has_correct_total_cell_count(self) -> None:
        # (0,0)→(3,0)→(3,2)→(6,2): 4 + 3 + 4 cells, turn cells shared
        route = _realize([(0, 0), (3, 0), (3, 2), (6, 2)])
        # horizontal 0..3 = 4 cells
        # vertical 0..2 at col=3 = 3 cells; (row=0,col=3) already counted
        # horizontal 3..6 at row=2 = 4 cells; (row=2,col=3) already counted
        # unique cells = 4 + 2 + 3 = 9
        assert len(route.cells) == 9


# ---------------------------------------------------------------------------
# Pass-through overlap in RealizedRouteSet
# ---------------------------------------------------------------------------


class TestPassThroughOverlap:
    """Two routes crossing the same cell merge into a tee or cross."""

    def test_two_parallel_routes_no_overlap(self) -> None:
        r1 = _realize([(0, 0), (2, 0)], child_idx=0)
        r2 = _realize([(0, 1), (2, 1)], child_idx=1)
        rset = RealizedRouteSet(realizedRoutes=(r1, r2))
        merged = rset.mergedCellMap_get()
        # No shared cell
        assert (0, 0) in merged
        assert (1, 0) in merged
        assert (0, 2) in merged

    def test_two_perpendicular_routes_produce_cross(self) -> None:
        # Horizontal (0,1)→(4,1) and vertical (2,0)→(2,3) cross at (1, 2)
        horiz = _realize([(0, 1), (4, 1)], child_idx=0)
        vert = _realize([(2, 0), (2, 3)], child_idx=1)
        rset = RealizedRouteSet(realizedRoutes=(horiz, vert))
        merged = rset.mergedCellMap_get()
        cross_cell = merged[(1, 2)]
        assert cross_cell.glyph == "┼"
        assert cross_cell.directions == frozenset({_N, _S, _E, _W})

    def test_two_routes_sharing_horizontal_segment_merge(self) -> None:
        # Both routes have an E-W segment on the same row — overlap is ─
        r1 = _realize([(0, 0), (3, 0)], child_idx=0)
        r2 = _realize([(1, 0), (4, 0)], child_idx=1)
        rset = RealizedRouteSet(realizedRoutes=(r1, r2))
        merged = rset.mergedCellMap_get()
        # Interior overlap cell (row=0, col=2) should still be ─
        assert merged[(0, 2)].glyph == "─"


# ---------------------------------------------------------------------------
# RouteSense does not change geometry
# ---------------------------------------------------------------------------


class TestRouteSenseInvariance:
    def test_forward_and_back_same_cells(self) -> None:
        pts = [(0, 0), (3, 0), (3, 2), (5, 2)]
        fwd = _realize(pts, sense=RouteSense.FORWARD)
        bck = _realize(pts, sense=RouteSense.BACK)
        assert fwd.cells == bck.cells

    def test_forward_and_self_same_cells(self) -> None:
        pts = [(0, 0), (0, 4)]
        fwd = _realize(pts, sense=RouteSense.FORWARD)
        slf = _realize(pts, sense=RouteSense.SELF)
        assert fwd.cells == slf.cells

    def test_sense_is_stored(self) -> None:
        route = _realize([(0, 0), (2, 0)], sense=RouteSense.BACK)
        assert route.routeSense is RouteSense.BACK


# ---------------------------------------------------------------------------
# cellAt_get
# ---------------------------------------------------------------------------


class TestCellAtGet:
    def test_returns_cell_at_known_position(self) -> None:
        route = _realize([(0, 0), (2, 0)])
        cell = route.cellAt_get(worldRow=0, worldCol=1)
        assert cell is not None
        assert cell.directions == frozenset({_E, _W})

    def test_returns_none_for_absent_position(self) -> None:
        route = _realize([(0, 0), (2, 0)])
        assert route.cellAt_get(worldRow=5, worldCol=5) is None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrorCases:
    def test_single_point_fails(self) -> None:
        result = routePoints_realize(
            sourceChipRef=_SRC,
            destinationChipRef=_DST,
            childCallIndex=0,
            routePoints=(_pt(0, 0),),
        )
        assert not result_isOkCheck(result)

    def test_empty_points_fails(self) -> None:
        result = routePoints_realize(
            sourceChipRef=_SRC,
            destinationChipRef=_DST,
            childCallIndex=0,
            routePoints=(),
        )
        assert not result_isOkCheck(result)

    def test_diagonal_segment_fails(self) -> None:
        result = routePoints_realize(
            sourceChipRef=_SRC,
            destinationChipRef=_DST,
            childCallIndex=0,
            routePoints=(_pt(0, 0), _pt(1, 1)),  # diagonal
        )
        assert not result_isOkCheck(result)

    def test_coincident_waypoints_skipped(self) -> None:
        # Two coincident points do not raise but the route still spans
        # the non-degenerate segments.
        route = _realize([(0, 0), (0, 0), (2, 0)])
        m = _cellMap(route)
        # Same as a direct (0,0)→(2,0) horizontal route
        assert m[(0, 0)] == frozenset({_E})
        assert m[(0, 1)] == frozenset({_E, _W})
        assert m[(0, 2)] == frozenset({_W})


# ---------------------------------------------------------------------------
# RealizedRouteSet.routesForChip_get
# ---------------------------------------------------------------------------


class TestRealizedRouteSetLookup:
    def test_routes_for_source_chip(self) -> None:
        r1 = _realize([(0, 0), (2, 0)], child_idx=0)
        other_src = _chip("X", "other")
        result2 = routePoints_realize(
            sourceChipRef=other_src,
            destinationChipRef=_DST,
            childCallIndex=1,
            routePoints=(_pt(0, 1), _pt(2, 1)),
        )
        assert result_isOkCheck(result2)
        rset = RealizedRouteSet(realizedRoutes=(r1, result2.value))
        found = rset.routesForChip_get(_SRC)
        assert len(found) == 1
        assert found[0] is r1

    def test_empty_set_returns_empty(self) -> None:
        rset = RealizedRouteSet()
        assert rset.routesForChip_get(_SRC) == ()


# ---------------------------------------------------------------------------
# Zone-local builder
# ---------------------------------------------------------------------------


class TestZoneLocalBuilder:
    """realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet round-trip."""

    def _make_solved_route(
        self,
        src_label: str = "src0",
        dst_label: str = "dst0",
        child_idx: int = 0,
        row: int = 0,
    ) -> object:
        """Return a minimal solved zone-local route for testing."""
        from signalflow.models.routing_zone import (
            GridCoord,
            RoutingZoneId,
            RoutingZoneRegionId,
            RoutingZoneRegionKind,
            RoutingZoneRegionSide,
        )
        from signalflow.models.zone_route import (
            RoutingZoneLocalRouteSolveKind,
            routingZoneLocalSolvedRouteResult_build,
        )

        zone_id = RoutingZoneId(id=GridCoord(columnIndex=1, rowIndex=1))
        region_id = RoutingZoneRegionId(
            routingZoneId=zone_id,
            routingZoneRegionKind=RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            routingZoneRegionSide=RoutingZoneRegionSide.WEST,
        )
        result = routingZoneLocalSolvedRouteResult_build(
            owningRoutingZoneId=zone_id,
            sourceChipRef=_chip("A", src_label),
            destinationChipRef=_chip("A", dst_label),
            childCallIndex=child_idx,
            solveKind=RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD,
            routePoints=(
                RoutingZoneRoutePoint(horizontalIndex=0, verticalIndex=row),
                RoutingZoneRoutePoint(horizontalIndex=3, verticalIndex=row),
            ),
            traversedRegionIds=(region_id,),
        )
        assert result_isOkCheck(result)
        return result.value

    def test_builds_realized_set_from_one_route(self) -> None:
        solved = self._make_solved_route()
        set_result = routingZoneLocalSolvedRouteSetResult_build(
            routingZoneLocalSolvedRoutes=(solved,)
        )
        assert result_isOkCheck(set_result)
        realized_result = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
            solvedRouteSet=set_result.value,
        )
        assert result_isOkCheck(realized_result)
        rset = realized_result.value
        assert len(rset.realizedRoutes) == 1
        route = rset.realizedRoutes[0]
        # Horizontal route from col=0 to col=3 on row=0 → 4 cells
        assert len(route.cells) == 4
        assert route.routeSense is RouteSense.FORWARD

    def test_builds_realized_set_from_two_routes(self) -> None:
        s0 = self._make_solved_route(
            src_label="src0",
            dst_label="dst0",
            child_idx=0,
            row=0,
        )
        s1 = self._make_solved_route(
            src_label="src1",
            dst_label="dst1",
            child_idx=1,
            row=1,
        )
        set_result = routingZoneLocalSolvedRouteSetResult_build(
            routingZoneLocalSolvedRoutes=(s0, s1)
        )
        assert result_isOkCheck(set_result)
        realized_result = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
            solvedRouteSet=set_result.value,
            defaultRouteSense=RouteSense.BACK,
        )
        assert result_isOkCheck(realized_result)
        rset = realized_result.value
        assert len(rset.realizedRoutes) == 2
        for route in rset.realizedRoutes:
            assert route.routeSense is RouteSense.BACK

    def test_empty_set_builds_empty_realized_set(self) -> None:
        set_result = routingZoneLocalSolvedRouteSetResult_build(
            routingZoneLocalSolvedRoutes=()
        )
        assert result_isOkCheck(set_result)
        realized_result = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
            solvedRouteSet=set_result.value,
        )
        assert result_isOkCheck(realized_result)
        assert realized_result.value.realizedRoutes == ()
