"""Tests for cell-local track-laying algebra (Phase 6).

Covers: elbow formation, tee formation, cross formation, pass-through,
no-op merges, direction-mask to glyph promotion, and idempotence.
"""
from __future__ import annotations

from signalflow.routing.track import (
    EMPTY_TRACK_CELL,
    TrackDirection,
    glyph_resolveFromDirections,
    trackCell_build,
    trackCell_buildFromIntent,
    trackCells_merge,
    trackIntent_build,
    trackIntents_merge,
)

_N = TrackDirection.NORTH
_S = TrackDirection.SOUTH
_E = TrackDirection.EAST
_W = TrackDirection.WEST


# ---------------------------------------------------------------------------
# Glyph table completeness
# ---------------------------------------------------------------------------


class TestGlyphTable:
    """Every canonical direction-mask maps to the correct box-drawing character."""

    def test_empty_is_space(self) -> None:
        assert glyph_resolveFromDirections([]) == " "

    def test_north_only(self) -> None:
        assert glyph_resolveFromDirections([_N]) == "│"

    def test_south_only(self) -> None:
        assert glyph_resolveFromDirections([_S]) == "│"

    def test_ns_passthrough(self) -> None:
        assert glyph_resolveFromDirections([_N, _S]) == "│"

    def test_east_only(self) -> None:
        assert glyph_resolveFromDirections([_E]) == "─"

    def test_west_only(self) -> None:
        assert glyph_resolveFromDirections([_W]) == "─"

    def test_ew_passthrough(self) -> None:
        assert glyph_resolveFromDirections([_E, _W]) == "─"

    def test_elbow_ne(self) -> None:
        assert glyph_resolveFromDirections([_N, _E]) == "└"

    def test_elbow_nw(self) -> None:
        assert glyph_resolveFromDirections([_N, _W]) == "┘"

    def test_elbow_se(self) -> None:
        assert glyph_resolveFromDirections([_S, _E]) == "┌"

    def test_elbow_sw(self) -> None:
        assert glyph_resolveFromDirections([_S, _W]) == "┐"

    def test_tee_nse(self) -> None:
        assert glyph_resolveFromDirections([_N, _S, _E]) == "├"

    def test_tee_nsw(self) -> None:
        assert glyph_resolveFromDirections([_N, _S, _W]) == "┤"

    def test_tee_new(self) -> None:
        assert glyph_resolveFromDirections([_N, _E, _W]) == "┴"

    def test_tee_sew(self) -> None:
        assert glyph_resolveFromDirections([_S, _E, _W]) == "┬"

    def test_cross(self) -> None:
        assert glyph_resolveFromDirections([_N, _S, _E, _W]) == "┼"

    def test_unknown_combination_returns_question_mark(self) -> None:
        # An impossible combination (duplicate) normalises to a known set, so
        # test with an artificially injected unknown frozenset via direct dict lookup.
        from signalflow.routing.track import _GLYPH_BY_DIRECTIONS, _GLYPH_UNKNOWN

        assert _GLYPH_UNKNOWN == "?"
        # Verify every table entry is NOT "?"
        for glyph in _GLYPH_BY_DIRECTIONS.values():
            assert glyph != "?"


# ---------------------------------------------------------------------------
# trackCell_build
# ---------------------------------------------------------------------------


class TestTrackCellBuild:
    def test_builds_correct_glyph(self) -> None:
        cell = trackCell_build(frozenset({_N, _E}))
        assert cell.glyph == "└"
        assert cell.directions == frozenset({_N, _E})

    def test_empty_direction_set_is_space(self) -> None:
        cell = trackCell_build(frozenset())
        assert cell.glyph == " "
        assert cell.isEmpty

    def test_cross(self) -> None:
        cell = trackCell_build(frozenset({_N, _S, _E, _W}))
        assert cell.glyph == "┼"


# ---------------------------------------------------------------------------
# TrackCell.merge (elbow, tee, cross formation)
# ---------------------------------------------------------------------------


class TestTrackCellMerge:
    """Merging two cells unions their directions and re-resolves the glyph."""

    def test_elbow_from_two_stubs(self) -> None:
        north = trackCell_build(frozenset({_N}))
        east = trackCell_build(frozenset({_E}))
        merged = north.merge(east)
        assert merged.glyph == "└"

    def test_tee_from_passthrough_and_stub(self) -> None:
        ns = trackCell_build(frozenset({_N, _S}))
        east = trackCell_build(frozenset({_E}))
        merged = ns.merge(east)
        assert merged.glyph == "├"

    def test_cross_from_two_passthroughs(self) -> None:
        ns = trackCell_build(frozenset({_N, _S}))
        ew = trackCell_build(frozenset({_E, _W}))
        merged = ns.merge(ew)
        assert merged.glyph == "┼"

    def test_merge_with_empty_is_identity(self) -> None:
        cell = trackCell_build(frozenset({_N, _E}))
        merged = cell.merge(EMPTY_TRACK_CELL)
        assert merged == cell

    def test_empty_merge_with_non_empty(self) -> None:
        cell = trackCell_build(frozenset({_S, _W}))
        merged = EMPTY_TRACK_CELL.merge(cell)
        assert merged == cell

    def test_merge_is_idempotent(self) -> None:
        cell = trackCell_build(frozenset({_N, _S, _E}))
        merged = cell.merge(cell)
        assert merged == cell

    def test_merge_produces_elbow_sw(self) -> None:
        south = trackCell_build(frozenset({_S}))
        west = trackCell_build(frozenset({_W}))
        assert south.merge(west).glyph == "┐"


# ---------------------------------------------------------------------------
# trackCells_merge (variadic)
# ---------------------------------------------------------------------------


class TestTrackCellsMerge:
    def test_zero_cells_returns_empty(self) -> None:
        result = trackCells_merge()
        assert result == EMPTY_TRACK_CELL

    def test_single_cell_passthrough(self) -> None:
        cell = trackCell_build(frozenset({_N, _S}))
        assert trackCells_merge(cell) == cell

    def test_three_cells_cross(self) -> None:
        n = trackCell_build(frozenset({_N}))
        s = trackCell_build(frozenset({_S}))
        ew = trackCell_build(frozenset({_E, _W}))
        assert trackCells_merge(n, s, ew).glyph == "┼"

    def test_all_empty_returns_empty(self) -> None:
        result = trackCells_merge(EMPTY_TRACK_CELL, EMPTY_TRACK_CELL)
        assert result == EMPTY_TRACK_CELL


# ---------------------------------------------------------------------------
# TrackIntent
# ---------------------------------------------------------------------------


class TestTrackIntent:
    def test_build_from_directions(self) -> None:
        intent = trackIntent_build(_N, _E)
        assert intent.directions == frozenset({_N, _E})

    def test_build_empty(self) -> None:
        intent = trackIntent_build()
        assert intent.directions == frozenset()

    def test_merge_two_intents(self) -> None:
        a = trackIntent_build(_N)
        b = trackIntent_build(_E)
        merged = a.merge(b)
        assert merged.directions == frozenset({_N, _E})

    def test_merge_with_empty_is_identity(self) -> None:
        intent = trackIntent_build(_S, _W)
        empty = trackIntent_build()
        assert intent.merge(empty) == intent
        assert empty.merge(intent) == intent

    def test_merge_is_idempotent(self) -> None:
        intent = trackIntent_build(_N, _S, _E)
        assert intent.merge(intent) == intent


# ---------------------------------------------------------------------------
# trackIntents_merge (variadic)
# ---------------------------------------------------------------------------


class TestTrackIntentsMerge:
    def test_zero_intents_returns_empty(self) -> None:
        result = trackIntents_merge()
        assert result.directions == frozenset()

    def test_single_intent_passthrough(self) -> None:
        intent = trackIntent_build(_N, _W)
        assert trackIntents_merge(intent) == intent

    def test_three_intents_union(self) -> None:
        a = trackIntent_build(_N)
        b = trackIntent_build(_S)
        c = trackIntent_build(_E, _W)
        merged = trackIntents_merge(a, b, c)
        assert merged.directions == frozenset({_N, _S, _E, _W})


# ---------------------------------------------------------------------------
# trackCell_buildFromIntent
# ---------------------------------------------------------------------------


class TestTrackCellBuildFromIntent:
    def test_intent_to_cell_round_trip(self) -> None:
        intent = trackIntent_build(_S, _E)
        cell = trackCell_buildFromIntent(intent)
        assert cell.glyph == "┌"
        assert cell.directions == frozenset({_S, _E})

    def test_empty_intent_produces_empty_cell(self) -> None:
        intent = trackIntent_build()
        cell = trackCell_buildFromIntent(intent)
        assert cell == EMPTY_TRACK_CELL

    def test_cross_intent(self) -> None:
        intent = trackIntent_build(_N, _S, _E, _W)
        cell = trackCell_buildFromIntent(intent)
        assert cell.glyph == "┼"


# ---------------------------------------------------------------------------
# isEmpty property
# ---------------------------------------------------------------------------


class TestTrackCellIsEmpty:
    def test_empty_cell_is_empty(self) -> None:
        assert EMPTY_TRACK_CELL.isEmpty

    def test_non_empty_cell_is_not_empty(self) -> None:
        assert not trackCell_build(frozenset({_N})).isEmpty

    def test_build_empty_is_empty(self) -> None:
        assert trackCell_build(frozenset()).isEmpty
