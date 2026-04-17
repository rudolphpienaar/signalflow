"""World-canvas compositor for the new SignalFlow engine.

This module assembles the full world-coordinate ASCII canvas from effective
board geometry and overlays realized route glyphs on top.

Pipeline position
-----------------
``RoutingZoneGrid`` (placed) + ``CircuitDocument`` + ``RealizedRouteSet``
    → ``worldCanvas_render``
    → ``tuple[str, ...]`` (one string per world row)

Board composition
-----------------
Each placed routing zone contributes an effective ``intra`` board. World chip
placement and module-boundary composition therefore follow the same effective
geometry that local solve and realization already use.

Route overlay
-------------
``RealizedRouteSet.mergedCellMap_get()`` provides a ``(worldRow, worldCol) →
TrackCell`` mapping. Each cell's glyph is written on top of any chip-body
character at that position, so route wires that enter chip terminal stubs
render correctly.

Overlap model
-------------
World geometry is sized from zone-owned board frames only. Inter-zone
continuity may still be represented by realized routes, but seam/interconnect
frames are no longer treated here as geometry-owning substrate.

Module boxes
------------
Effective module boundaries are now first-class board geometry and are composed
from the effective board, not recovered later from raw chip extents.
"""

from __future__ import annotations

from signalflow.board import board_buildFromZoneAndSide
from signalflow.board.board import Board
from signalflow.board.render import boardCanvas_render
from signalflow.models import result_isOkCheck
from signalflow.models.circuit import CircuitDocument
from signalflow.models.routing_zone_grid import RoutingZoneGrid
from signalflow.routing.route import RealizedRouteSet
from signalflow.routing.track import TrackCell, TrackDirection


def worldCanvas_render(
    placedGrid: RoutingZoneGrid,
    circuitDocument: CircuitDocument,
    realizedRouteSet: RealizedRouteSet,
) -> tuple[str, ...]:
    """Render the full world canvas as an ordered tuple of ASCII lines.

    Places chip body lines from ``chipDrawLines_build`` at their terminal
    region positions within each placed zone, then overlays route wire glyphs
    from the pre-realized route set.

    Args:
        placedGrid: The placed routing-zone world grid whose zone frames
            determine world bounds and chip positions.
        circuitDocument: Canonical circuit document used to derive each zone's
            effective operational board.
        realizedRouteSet: Pre-realized routes (zone-local and/or seam) whose
            merged cell map supplies the wire glyph overlay.

    Returns:
        Ordered tuple of strings, one per world row, padded to uniform width.
        Returns an empty tuple when the placed grid has no zone frames with
        positive extents.
    """

    boards = _effectiveBoards_build(
        placedGrid=placedGrid,
        circuitDocument=circuitDocument,
    )
    totalCols, totalRows = _worldSize_build(boards)
    if totalCols <= 0 or totalRows <= 0:
        return ()

    # Allocate a mutable character grid (row-major, row × col).
    charGrid: list[list[str]] = [[" "] * totalCols for _ in range(totalRows)]

    for board in boards:
        _boardCanvas_blit(
            board=board,
            charGrid=charGrid,
            totalRows=totalRows,
            totalCols=totalCols,
        )

    # Overlay route wire glyphs, using piercing glyphs at box-wall crossings.
    for (row, col), trackCell in realizedRouteSet.mergedCellMap_get().items():
        if 0 <= row < totalRows and 0 <= col < totalCols and trackCell.glyph:
            charGrid[row][col] = _routeOverlayGlyph_build(
                existing=charGrid[row][col],
                trackCell=trackCell,
            )

    return tuple("".join(rowChars) for rowChars in charGrid)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _worldSize_build(boards: tuple[Board, ...]) -> tuple[int, int]:
    """Return `(totalColumns, totalRows)` from zone-owned board extents."""

    maxCol: int = 0
    maxRow: int = 0
    board: Board
    for board in boards:
        maxCol = max(maxCol, board.worldFrame.bottomRight[0] + 1)
        maxRow = max(maxRow, board.worldFrame.bottomRight[1] + 1)
    return maxCol, maxRow


def _effectiveBoards_build(
    *,
    placedGrid: RoutingZoneGrid,
    circuitDocument: CircuitDocument,
) -> tuple[Board, ...]:
    """Return effective `intra` boards for all placed zones."""

    boardsMutable: list[Board] = []
    for zone in placedGrid.routingZoneSet.routingZones:
        boardResult = board_buildFromZoneAndSide(
            routingZoneId=zone.routingZoneId,
            side="intra",
            routingZone=zone,
            circuitDocument=circuitDocument,
            moduleBoundaryPaddingCells=placedGrid.moduleBoxPadding,
        )
        if not result_isOkCheck(boardResult):
            continue
        boardsMutable.append(boardResult.value)
    return tuple(boardsMutable)


def _boardCanvas_blit(
    *,
    board: Board,
    charGrid: list[list[str]],
    totalRows: int,
    totalCols: int,
) -> None:
    """Blit one effective board canvas into the world character grid."""

    boardCanvasLines = boardCanvas_render(
        board=board,
        realizedRouteSet=RealizedRouteSet(),
    )
    for rowIndex, line in enumerate(boardCanvasLines):
        if rowIndex >= totalRows:
            break
        for columnIndex, character in enumerate(line):
            if columnIndex >= totalCols or character == " ":
                continue
            charGrid[rowIndex][columnIndex] = character


def _piercedGlyph(existing: str, trackCell: TrackCell) -> str:
    """Return the glyph for a route wire overlapping a box-wall character.

    A horizontal single-line wire crossing a double-vertical wall (``║``)
    produces ``╫``.  A vertical single-line wire crossing a double-horizontal
    wall (``═``) produces ``╪``.  All other combinations fall back to the
    route wire's own glyph.
    """

    dirs = trackCell.directions
    hasH: bool = TrackDirection.EAST in dirs or TrackDirection.WEST in dirs
    hasV: bool = TrackDirection.NORTH in dirs or TrackDirection.SOUTH in dirs

    if existing == "║":
        if hasH:
            return "╫"
        return "║"
    if existing == "═":
        if hasV:
            return "╪"
        return "═"
    return trackCell.glyph


def _routeOverlayGlyph_build(existing: str, trackCell: TrackCell) -> str:
    """Return the visible glyph when a realized route overlays one canvas cell.

    Route wires are allowed to pierce final module borders, but they must not
    erase already-materialized chip stub labels. The canonical chip drawing
    already contributes the visible labeled stub geometry; when a route reaches
    that surface, the route should continue logically without overwriting the
    label text itself.
    """

    if existing in {"║", "═"}:
        return _piercedGlyph(existing, trackCell)
    if existing != " ":
        return existing
    return trackCell.glyph
