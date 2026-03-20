"""World-canvas compositor for the new SignalFlow engine.

This module assembles the full world-coordinate ASCII canvas by placing chip
bodies at their terminal region positions and overlaying route wire glyphs.

Pipeline position
-----------------
``RoutingZoneGrid`` (placed) + ``CircuitChipSet`` + ``RealizedRouteSet``
    → ``worldCanvas_render``
    → ``tuple[str, ...]`` (one string per world row)

Chip placement
--------------
Chips placed in a WEST_TO_EAST zone stack vertically within their terminal
region (WEST side stacks top-to-bottom; EAST side likewise). Chips placed in
a NORTH_TO_SOUTH zone stack horizontally (NORTH side stacks left-to-right;
SOUTH side likewise). The ordering follows ``ChipPlacement.orderIndex``.

Route overlay
-------------
``RealizedRouteSet.mergedCellMap_get()`` provides a ``(worldRow, worldCol) →
TrackCell`` mapping.  Each cell's glyph is written on top of any chip-body
character at that position, so route wires that enter chip terminal stubs
render correctly.

Seam frames
-----------
``RoutingZoneInterconnect`` frames are single-cell-wide columns or rows
between zones.  This compositor leaves them as spaces; the caller is
responsible for building a ``RealizedRouteSet`` that includes seam-crossing
routes so the wire glyphs fill those cells.

Module boxes
------------
Chips that share the same ``moduleName`` are enclosed in a double-line box
(``╔═ ModuleName ═╗`` / ``║`` / ``╚════╝``) drawn before chip bodies are
blitted, so chip content overlays the box interior while the border frames
the group.
"""
from __future__ import annotations


from signalflow.models.chip import chipDrawLines_build
from signalflow.models.circuit import CircuitChipSet
from signalflow.models.result import result_isOkCheck
from signalflow.models.routing_zone import (
    RoutingZone,
    RoutingZoneRegionSide,
    RoutingZoneSense,
)
from signalflow.models.routing_zone_grid import RoutingZoneGrid
from signalflow.routing.route import RealizedRouteSet
from signalflow.routing.track import TrackCell, TrackDirection


def worldCanvas_render(
    placedGrid: RoutingZoneGrid,
    circuitChipSet: CircuitChipSet,
    realizedRouteSet: RealizedRouteSet,
) -> tuple[str, ...]:
    """Render the full world canvas as an ordered tuple of ASCII lines.

    Places chip body lines from ``chipDrawLines_build`` at their terminal
    region positions within each placed zone, then overlays route wire glyphs
    from the pre-realized route set.

    Args:
        placedGrid: The placed routing-zone world grid whose zone frames
            determine world bounds and chip positions.
        circuitChipSet: All canonical chips.  Each chip's body lines are
            obtained via the canonical ``chipDrawLines_build`` function.
        realizedRouteSet: Pre-realized routes (zone-local and/or seam) whose
            merged cell map supplies the wire glyph overlay.

    Returns:
        Ordered tuple of strings, one per world row, padded to uniform width.
        Returns an empty tuple when the placed grid has no zone frames with
        positive extents.
    """

    totalCols, totalRows = _worldSize_build(placedGrid)
    if totalCols <= 0 or totalRows <= 0:
        return ()

    # Allocate a mutable character grid (row-major, row × col).
    charGrid: list[list[str]] = [[" "] * totalCols for _ in range(totalRows)]

    # Draw module boxes first so chip bodies can overlay the interior.
    _moduleBoxes_blit(
        placedGrid=placedGrid,
        circuitChipSet=circuitChipSet,
        charGrid=charGrid,
        totalRows=totalRows,
        totalCols=totalCols,
    )

    # Blit chip bodies into the character grid.
    zone: RoutingZone
    for zone in placedGrid.routingZoneSet.routingZones:
        _chipBodies_blit(
            zone=zone,
            circuitChipSet=circuitChipSet,
            charGrid=charGrid,
            totalRows=totalRows,
            totalCols=totalCols,
        )

    # Overlay route wire glyphs, using piercing glyphs at box-wall crossings.
    for (row, col), trackCell in realizedRouteSet.mergedCellMap_get().items():
        if 0 <= row < totalRows and 0 <= col < totalCols and trackCell.glyph:
            charGrid[row][col] = _piercedGlyph(charGrid[row][col], trackCell)

    return tuple("".join(rowChars) for rowChars in charGrid)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _worldSize_build(placedGrid: RoutingZoneGrid) -> tuple[int, int]:
    """Return (totalColumns, totalRows) from zone frame extents."""

    maxCol: int = 0
    maxRow: int = 0
    zone: RoutingZone
    for zone in placedGrid.routingZoneSet.routingZones:
        maxCol = max(maxCol, zone.routingZoneFrame.horizontalEnd_calculate())
        maxRow = max(maxRow, zone.routingZoneFrame.verticalEnd_calculate())
    for ic in placedGrid.routingZoneInterconnectSet.routingZoneInterconnects:
        f = ic.routingZoneInterconnectFrame
        maxCol = max(maxCol, f.horizontalStart + f.horizontalSpan)
        maxRow = max(maxRow, f.verticalStart + f.verticalSpan)
    return maxCol, maxRow


def _chipBodies_blit(
    zone: RoutingZone,
    circuitChipSet: CircuitChipSet,
    charGrid: list[list[str]],
    totalRows: int,
    totalCols: int,
) -> None:
    """Blit all chip bodies for one placed zone into the character grid."""

    isWestToEast: bool = zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST

    # Process each terminal side independently so cumulative offsets are
    # correct within each side's band.
    for side in (
        RoutingZoneRegionSide.WEST,
        RoutingZoneRegionSide.EAST,
        RoutingZoneRegionSide.NORTH,
        RoutingZoneRegionSide.SOUTH,
    ):
        placements = sorted(
            (
                p
                for p in zone.chipPlacementSet.placements
                if p.chipTerminalRegionId.routingZoneRegionSide is side
            ),
            key=lambda p: p.orderIndex,
        )
        if not placements:
            continue

        # Get the terminal region frame for this side (same for all chips on
        # this side; the first placement's regionId is representative).
        regionResult = zone.routingZoneRegionSet.regionResult_get(
            placements[0].chipTerminalRegionId
        )
        if not result_isOkCheck(regionResult):
            continue
        regionFrame = regionResult.value.routingZoneRegionFrame

        # Stack chips along the appropriate axis.
        cumulativeOffset: int = 0
        for placement in placements:
            chipResult = circuitChipSet.chipResult_get(placement.chipRef.chipId)
            if not result_isOkCheck(chipResult):
                continue
            bodyLines = chipDrawLines_build(chipResult.value)
            if not bodyLines:
                continue

            if isWestToEast or side in {
                RoutingZoneRegionSide.WEST,
                RoutingZoneRegionSide.EAST,
            }:
                # WTE zone or explicit east/west side: chips stack vertically.
                # Each chip occupies a slot of (chipHeight + 2) rows:
                # 1 corridor row above, chip body, 1 corridor row below.
                worldRow = regionFrame.verticalStart + cumulativeOffset + 1
                worldCol = regionFrame.horizontalStart
                for lineIdx, line in enumerate(bodyLines):
                    r = worldRow + lineIdx
                    for charIdx, ch in enumerate(line):
                        c = worldCol + charIdx
                        if 0 <= r < totalRows and 0 <= c < totalCols:
                            charGrid[r][c] = ch
                cumulativeOffset += len(bodyLines) + 2
            else:
                # NTS zone, north/south side: chips stack horizontally.
                # Each chip occupies a slot of (chipWidth + 2) cols:
                # 1 corridor col left, chip body, 1 corridor col right.
                worldRow = regionFrame.verticalStart
                worldCol = regionFrame.horizontalStart + cumulativeOffset + 1
                for lineIdx, line in enumerate(bodyLines):
                    r = worldRow + lineIdx
                    for charIdx, ch in enumerate(line):
                        c = worldCol + charIdx
                        if 0 <= r < totalRows and 0 <= c < totalCols:
                            charGrid[r][c] = ch
                chipWidth = max((len(line) for line in bodyLines), default=0)
                cumulativeOffset += chipWidth + 2


def _piercedGlyph(existing: str, trackCell: TrackCell) -> str:
    """Return the correct glyph when a route wire overlaps a box-wall character.

    A horizontal single-line wire crossing a double-vertical wall (``║``)
    produces ``╫``.  A vertical single-line wire crossing a double-horizontal
    wall (``═``) produces ``╪``.  All other combinations fall back to the
    route wire's own glyph.
    """

    dirs = trackCell.directions
    hasH: bool = TrackDirection.EAST in dirs or TrackDirection.WEST in dirs
    hasV: bool = TrackDirection.NORTH in dirs or TrackDirection.SOUTH in dirs

    if existing == "║" and hasH and not hasV:
        return "╫"
    if existing == "═" and hasV and not hasH:
        return "╪"
    return trackCell.glyph


def _chipWorldCoords_collect(
    placedGrid: RoutingZoneGrid,
    circuitChipSet: CircuitChipSet,
) -> list[tuple[str, int, int, int, int]]:
    """Return ``(moduleName, worldRow, worldCol, chipH, chipW)`` per placed chip."""

    records: list[tuple[str, int, int, int, int]] = []
    zone: RoutingZone
    for zone in placedGrid.routingZoneSet.routingZones:
        isWestToEast: bool = zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST
        for side in (
            RoutingZoneRegionSide.WEST,
            RoutingZoneRegionSide.EAST,
            RoutingZoneRegionSide.NORTH,
            RoutingZoneRegionSide.SOUTH,
        ):
            placements = sorted(
                (
                    p
                    for p in zone.chipPlacementSet.placements
                    if p.chipTerminalRegionId.routingZoneRegionSide is side
                ),
                key=lambda p: p.orderIndex,
            )
            if not placements:
                continue
            regionResult = zone.routingZoneRegionSet.regionResult_get(
                placements[0].chipTerminalRegionId
            )
            if not result_isOkCheck(regionResult):
                continue
            regionFrame = regionResult.value.routingZoneRegionFrame

            cumulativeOffset: int = 0
            for placement in placements:
                chipResult = circuitChipSet.chipResult_get(
                    placement.chipRef.chipId
                )
                if not result_isOkCheck(chipResult):
                    continue
                chip = chipResult.value
                bodyLines = chipDrawLines_build(chip)
                if not bodyLines:
                    continue

                chipH: int = len(bodyLines)
                chipW: int = max(len(line) for line in bodyLines)

                if isWestToEast or side in {
                    RoutingZoneRegionSide.WEST,
                    RoutingZoneRegionSide.EAST,
                }:
                    worldRow = regionFrame.verticalStart + cumulativeOffset + 1
                    worldCol = regionFrame.horizontalStart
                    cumulativeOffset += chipH + 2
                else:
                    worldRow = regionFrame.verticalStart
                    worldCol = regionFrame.horizontalStart + cumulativeOffset + 1
                    cumulativeOffset += chipW + 2

                records.append(
                    (chip.chipId.moduleName, worldRow, worldCol, chipH, chipW)
                )
    return records


def _moduleBoxes_blit(
    placedGrid: RoutingZoneGrid,
    circuitChipSet: CircuitChipSet,
    charGrid: list[list[str]],
    totalRows: int,
    totalCols: int,
) -> None:
    """Draw double-line module boxes, one per chip placement.

    Each chip gets its own labeled ``╔═ ModuleName ═╗`` box.  Drawing one box
    per chip rather than one bounding box per module avoids the cross-zone
    spanning problem: chips from the same module placed in different zones
    can be far apart horizontally, and a single bounding box would engulf
    chips from other modules between them.
    """

    records = _chipWorldCoords_collect(placedGrid, circuitChipSet)
    if not records:
        return

    moduleName: str
    worldRow: int
    worldCol: int
    chipH: int
    chipW: int
    for moduleName, worldRow, worldCol, chipH, chipW in records:
        # One box tight around this single chip placement, with 1-cell padding.
        r0: int = worldRow - 1
        c0: int = worldCol - 1
        r1: int = worldRow + chipH
        c1: int = worldCol + chipW

        # Ensure the top border fits the label: ╔═ label ═╗ needs innerW ≥ len("═ label ").
        innerW: int = c1 - c0 - 1
        minInnerW: int = len("═ " + moduleName + " ")
        if innerW < minInnerW:
            c1 = c0 + 1 + minInnerW

        # Clamp to grid boundaries.
        r0 = max(0, r0)
        c0 = max(0, c0)
        r1 = min(totalRows - 1, r1)
        c1 = min(totalCols - 1, c1)
        innerW = c1 - c0 - 1

        if innerW <= 0 or r1 <= r0:
            continue

        # Top border: ╔═ label ════╗
        charGrid[r0][c0] = "╔"
        fill: str = ("═ " + moduleName + " ").ljust(innerW, "═")[:innerW]
        for i, ch in enumerate(fill):
            col: int = c0 + 1 + i
            if 0 <= col < totalCols:
                charGrid[r0][col] = ch
        charGrid[r0][c1] = "╗"

        # Side walls: ║
        for r in range(r0 + 1, r1):
            if 0 <= r < totalRows:
                charGrid[r][c0] = "║"
                charGrid[r][c1] = "║"

        # Bottom border: ╚════╝
        charGrid[r1][c0] = "╚"
        for col in range(c0 + 1, c1):
            if 0 <= col < totalCols:
                charGrid[r1][col] = "═"
        charGrid[r1][c1] = "╝"
