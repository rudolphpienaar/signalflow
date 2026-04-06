"""Cell-local track-laying algebra for the new SignalFlow engine.

This module owns all local glyph resolution so that renderer code never
re-implements cell-join rules.

The core model is the direction-mask: a `TrackCell` holds the set of cardinal
directions that are active at one grid position. The glyph is a deterministic
function of that set.

Merge algebra:
- Two `TrackCell`s at the same position are merged by unioning their direction
  sets.  This is the canonical way to compose overlapping wire paths.
- Merging with an empty cell is a no-op (identity element).
- Merging two identical cells is idempotent.

Glyph rules (box-drawing characters):
    {}           → ' '
    {N} or {S} or {N,S}  → '│'
    {E} or {W} or {E,W}  → '─'
    {N,E}        → '└'    (wire comes from south, turns east)
    {N,W}        → '┘'    (wire comes from south, turns west)
    {S,E}        → '┌'    (wire comes from north, turns east)
    {S,W}        → '┐'    (wire comes from north, turns west)
    {N,S,E}      → '├'    (T-junction: continuation N↔S with east branch)
    {N,S,W}      → '┤'    (T-junction: continuation N↔S with west branch)
    {N,E,W}      → '┴'    (T-junction: continuation E↔W with north branch)
    {S,E,W}      → '┬'    (T-junction: continuation E↔W with south branch)
    {N,S,E,W}    → '┼'    (cross)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum


class TrackDirection(Enum):
    """One of the four cardinal directions for a track wire at one cell.

    Attributes:
        NORTH: Wire exits the top of the cell.
        SOUTH: Wire exits the bottom of the cell.
        EAST: Wire exits the right of the cell.
        WEST: Wire exits the left of the cell.
    """

    NORTH = "N"
    SOUTH = "S"
    EAST = "E"
    WEST = "W"


# Convenience aliases for compact glyph-table construction
_N = TrackDirection.NORTH
_S = TrackDirection.SOUTH
_E = TrackDirection.EAST
_W = TrackDirection.WEST

_GLYPH_BY_DIRECTIONS: dict[frozenset[TrackDirection], str] = {
    # Empty cell
    frozenset(): " ",
    # Single-direction stubs and same-axis pass-throughs
    frozenset({_N}): "│",
    frozenset({_S}): "│",
    frozenset({_N, _S}): "│",
    frozenset({_E}): "─",
    frozenset({_W}): "─",
    frozenset({_E, _W}): "─",
    # Elbows (two perpendicular directions)
    frozenset({_N, _E}): "└",
    frozenset({_N, _W}): "┘",
    frozenset({_S, _E}): "┌",
    frozenset({_S, _W}): "┐",
    # Tee junctions (three directions)
    frozenset({_N, _S, _E}): "├",
    frozenset({_N, _S, _W}): "┤",
    frozenset({_N, _E, _W}): "┴",
    frozenset({_S, _E, _W}): "┬",
    # Cross (all four directions)
    frozenset({_N, _S, _E, _W}): "┼",
}

# Default fallback for any combination not in the table
_GLYPH_UNKNOWN: str = "?"


@dataclass(frozen=True)
class TrackIntent:
    """Raw directional intent for one cell contributed by one wire segment.

    A `TrackIntent` represents what one route wants to do at a given cell
    position.  Multiple intents from overlapping routes are merged to form the
    final `TrackCell`.

    Attributes:
        directions: Frozenset of active cardinal directions for this intent.
    """

    directions: frozenset[TrackDirection] = field(default_factory=frozenset)

    def merge(self, other: TrackIntent) -> TrackIntent:
        """Return a new intent whose directions are the union of both intents.

        Args:
            other: The second intent to merge with this one.

        Returns:
            A new `TrackIntent` with the unioned direction set.
        """

        return TrackIntent(directions=self.directions | other.directions)


@dataclass(frozen=True)
class TrackCell:
    """Resolved cell state for one grid position.

    A `TrackCell` is the canonical, glyph-ready representation of what wire
    segments exist at a single canvas coordinate.

    Attributes:
        directions: Frozenset of cardinal directions active at this cell.
        glyph: The box-drawing character that encodes the direction set.
    """

    directions: frozenset[TrackDirection] = field(default_factory=frozenset)
    glyph: str = " "

    def merge(self, other: TrackCell) -> TrackCell:
        """Return a new cell whose directions are the union of both cells.

        The glyph is re-resolved from the merged direction set.

        Args:
            other: The second cell to merge with this one.

        Returns:
            A new `TrackCell` with the merged direction set and correct glyph.
        """

        return trackCell_build(self.directions | other.directions)

    @property
    def isEmpty(self) -> bool:
        """Return True when no directions are active (cell is blank)."""

        return not self.directions


EMPTY_TRACK_CELL: TrackCell = TrackCell(directions=frozenset(), glyph=" ")


def trackCell_build(directions: frozenset[TrackDirection]) -> TrackCell:
    """Build a resolved `TrackCell` from a direction set.

    The glyph is looked up from the canonical table.  Unknown combinations
    map to ``'?'``.

    Args:
        directions: Frozenset of active cardinal directions.

    Returns:
        A `TrackCell` with the correct box-drawing glyph.
    """

    glyph: str = _GLYPH_BY_DIRECTIONS.get(directions, _GLYPH_UNKNOWN)
    return TrackCell(directions=directions, glyph=glyph)


def trackIntent_build(
    *directions: TrackDirection,
) -> TrackIntent:
    """Build a `TrackIntent` from one or more directions.

    Args:
        *directions: Active cardinal directions for this intent.

    Returns:
        A `TrackIntent` with the given direction set.
    """

    return TrackIntent(directions=frozenset(directions))


def trackCell_buildFromIntent(intent: TrackIntent) -> TrackCell:
    """Build a resolved `TrackCell` from a `TrackIntent`.

    Args:
        intent: The directional intent to resolve.

    Returns:
        A `TrackCell` with the correct box-drawing glyph.
    """

    return trackCell_build(intent.directions)


def trackIntents_merge(*intents: TrackIntent) -> TrackIntent:
    """Merge any number of `TrackIntent`s into one combined intent.

    The merged direction set is the union of all individual sets.  Merging
    with zero intents returns an empty intent.

    Args:
        *intents: Any number of intents to merge.

    Returns:
        A new `TrackIntent` with the unioned direction set.
    """

    merged: frozenset[TrackDirection] = frozenset()
    for intent in intents:
        merged = merged | intent.directions
    return TrackIntent(directions=merged)


def trackCells_merge(*cells: TrackCell) -> TrackCell:
    """Merge any number of `TrackCell`s into one resolved cell.

    The merged direction set is the union of all individual sets.  Merging
    with zero cells returns `EMPTY_TRACK_CELL`.

    Args:
        *cells: Any number of cells to merge.

    Returns:
        A new `TrackCell` with the merged direction set and correct glyph.
    """

    merged: frozenset[TrackDirection] = frozenset()
    for cell in cells:
        merged = merged | cell.directions
    return trackCell_build(merged)


def glyph_resolveFromDirections(
    directions: Iterable[TrackDirection],
) -> str:
    """Resolve the box-drawing glyph for an iterable of active directions.

    This is the canonical direction-mask to glyph promotion entry-point.
    Caller does not need to construct a `TrackCell` explicitly.

    Args:
        directions: Active cardinal directions.

    Returns:
        The box-drawing character for the given direction set.
    """

    return _GLYPH_BY_DIRECTIONS.get(frozenset(directions), _GLYPH_UNKNOWN)
