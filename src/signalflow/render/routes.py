"""Route canvas rendering for the new SignalFlow engine.

This module projects a ``RealizedRouteSet`` into a world-coordinate ASCII
canvas.  It consumes only pre-realized route objects (built by Phase 7) and
produces text lines.  No topology discovery, reclassification, or routing
solve occurs here.

Pipeline position
-----------------
``RealizedRouteSet`` (from ``routing.route``)
    → ``routeWorldCanvas_render``
    → ``tuple[str, ...]`` (one string per world row)

The world canvas is built from the merged cell map provided by
``RealizedRouteSet.mergedCellMap_get()``.  Overlapping routes are already
merged by the Phase 6 track algebra before this module sees them.  This
module only maps ``TrackCell.glyph`` values to character positions.

Canvas sizing
-------------
If an explicit ``RouteCanvasSize`` is supplied the canvas is padded to that
exact size, filling empty positions with spaces.  If no size is given the
canvas is sized to the bounding box of the populated cells (no extra
padding).
"""
from __future__ import annotations

from dataclasses import dataclass

from signalflow.routing.route import RealizedRouteSet


@dataclass(frozen=True)
class RouteCanvasSize:
    """Explicit world-canvas dimensions for route rendering.

    Attributes:
        width: Number of columns in the canvas (horizontal extent).
        height: Number of rows in the canvas (vertical extent).
    """

    width: int
    height: int


def routeWorldCanvas_render(
    realizedRouteSet: RealizedRouteSet,
    canvasSize: RouteCanvasSize | None = None,
) -> tuple[str, ...]:
    """Render a RealizedRouteSet to a world-coordinate ASCII canvas.

    Projects each ``TrackCell`` glyph from the merged cell map to its
    world-coordinate position.  Empty positions render as a single space.

    Args:
        realizedRouteSet: Pre-realized routes whose cells supply the glyph
            data.  Routes are merged by the Phase 6 track algebra before
            projection; intersecting wires produce the correct tee or cross
            glyph automatically.
        canvasSize: Optional explicit canvas dimensions.  When supplied the
            output has exactly ``height`` rows each of exactly ``width``
            characters.  When omitted the canvas is sized to the bounding
            box of the populated cells (minimum size to contain all routes).

    Returns:
        Ordered tuple of strings, one per world row.  Returns an empty
        tuple when the route set is empty and no explicit size is given.
    """

    cellMap = realizedRouteSet.mergedCellMap_get()

    if not cellMap and canvasSize is None:
        return ()

    if canvasSize is not None:
        width: int = canvasSize.width
        height: int = canvasSize.height
    else:
        height = max(r for r, _ in cellMap) + 1
        width = max(c for _, c in cellMap) + 1

    lines: list[str] = []
    for row in range(height):
        rowChars: list[str] = []
        for col in range(width):
            cell = cellMap.get((row, col))
            rowChars.append(cell.glyph if cell is not None else " ")
        lines.append("".join(rowChars))
    return tuple(lines)
