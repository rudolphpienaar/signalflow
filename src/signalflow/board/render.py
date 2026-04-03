"""Board-native rendering helpers.

This module owns board-domain text rendering. The immediate scope is still
small: render the board substrate as a world-true region grid plus legend.
Even in this limited form it is useful to separate rendering from the data
container so geometry storage and geometry presentation do not accrete in one
place.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    RegionBand,
    RegionBranch,
    RegionFamily,
    WorldFrame,
    WorldPoint,
    boardRegionLabel_build,
)
from signalflow.models import RoutingZoneRegionFrame
from signalflow.routing.route import RealizedRouteSet
from signalflow.routing.track import TrackCell, TrackDirection

if TYPE_CHECKING:
    from signalflow.board.board import Board

REGION_SYMBOLS: dict[RegionFamily, str] = {
    RegionFamily.INTER_LONGITUDE: "▌",
    RegionFamily.INTER_FAN: "🬗",
    RegionFamily.INTER_TRANSITION: "X",
    RegionFamily.CHIP_TERMINAL: "░",
    RegionFamily.INTRA_FAN: "🬤",
    RegionFamily.INTRA_TRANSITION: "x",
    RegionFamily.INTRA_LONGITUDE: "🭲",
    RegionFamily.INTRA_LATITUDE: "🭷",
    RegionFamily.INTER_LATITUDE: "🭶",
}


def boardGeometry_sprint(
    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame],
    effectiveBoundaryFramesByName: dict[str, RoutingZoneRegionFrame] | None = None,
    columnOffset: int | None = None,
) -> str:
    """Render board region geometry as a world-true text grid.

    Args:
        regionFramesById: Canonical board region frames keyed by canonical
            board region id.
        effectiveBoundaryFramesByName: Optional effective module/layout
            boundaries overlaid on top of the routing substrate.
        columnOffset: Optional world-column at which to begin the visible crop.

    Returns:
        A rendered region grid with a top ruler and legend.
    """

    if not regionFramesById:
        return "<no board geometry>"

    gridLines = _regionDrawGrid_build(
        regionFramesById=regionFramesById,
        effectiveBoundaryFramesByName=effectiveBoundaryFramesByName or {},
        columnOffset=columnOffset,
    )
    legendLines: list[str] = ["", "legend:"]
    for regionId, frame in regionFramesById.items():
        horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
        verticalEndInclusive = frame.verticalEnd_calculate() - 1
        legendLines.append(
            "  "
            f"{_regionSymbol_get(regionId)}   {boardRegionLabel_build(regionId)}  "
            f"[col={frame.horizontalStart}..{horizontalEndInclusive}  "
            f"row={frame.verticalStart}..{verticalEndInclusive}  "
            f"span=({frame.horizontalSpan}w x {frame.verticalSpan}h)]"
        )
    for boundaryName, frame in (effectiveBoundaryFramesByName or {}).items():
        horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
        verticalEndInclusive = frame.verticalEnd_calculate() - 1
        legendLines.append(
            "  "
            f"□   {boundaryName}  "
            f"[col={frame.horizontalStart}..{horizontalEndInclusive}  "
            f"row={frame.verticalStart}..{verticalEndInclusive}  "
            f"span=({frame.horizontalSpan}w x {frame.verticalSpan}h)]"
        )
    return "\n".join(gridLines + legendLines)


def realizedGeometry_sprint(
    *,
    baseCanvasLines: list[str],
    routeCells: set[WorldPoint],
    extraFrames: tuple[WorldFrame, ...] = tuple(),
    wiringLegendLines: tuple[str, ...] = tuple(),
    horizontalMargin: int = 18,
    verticalMargin: int = 3,
) -> str:
    """Render a realized chip-and-wire world canvas as cropped text.

    Args:
        baseCanvasLines: Fully rendered world canvas lines.
        routeCells: Occupied realized route cells in world coordinates.
        extraFrames: Optional inclusive frames that must remain visible in the
            cropped output, such as source and destination chip frames.
        wiringLegendLines: Optional trailing legend lines appended after the
            cropped canvas.
        horizontalMargin: Horizontal crop breathing room around occupied cells.
        verticalMargin: Vertical crop breathing room around occupied cells.

    Returns:
        Cropped, row-labeled geometry text with a top ruler and optional
        trailing legend.
    """

    if not baseCanvasLines:
        return "<materialized geometry unavailable>"
    if not routeCells:
        return "<no materialized route geometry>"

    charGrid: list[list[str]] = [list(line) for line in baseCanvasLines]
    totalRows: int = len(charGrid)
    totalColumns: int = max(len(row) for row in charGrid) if charGrid else 0

    minRouteColumn = min(columnIndex for columnIndex, _ in routeCells)
    maxRouteColumn = max(columnIndex for columnIndex, _ in routeCells)
    minRouteRow = min(rowIndex for _, rowIndex in routeCells)
    maxRouteRow = max(rowIndex for _, rowIndex in routeCells)

    minFrameColumn = min(
        (frame.topLeft[0] for frame in extraFrames),
        default=minRouteColumn,
    )
    maxFrameColumn = max(
        (frame.bottomRight[0] for frame in extraFrames),
        default=maxRouteColumn,
    )
    minFrameRow = min(
        (frame.topLeft[1] for frame in extraFrames),
        default=minRouteRow,
    )
    maxFrameRow = max(
        (frame.bottomRight[1] for frame in extraFrames),
        default=maxRouteRow,
    )

    minColumn: int = max(0, min(minRouteColumn, minFrameColumn) - horizontalMargin)
    maxColumn: int = min(
        totalColumns,
        max(maxRouteColumn, maxFrameColumn) + horizontalMargin + 1,
    )
    minRow: int = max(0, min(minRouteRow, minFrameRow) - verticalMargin)
    maxRow: int = min(totalRows, max(maxRouteRow, maxFrameRow) + verticalMargin + 1)

    croppedGridLines: list[str] = [
        "".join(row[minColumn:maxColumn]) for row in charGrid[minRow:maxRow]
    ]
    ruler: str = "".join(
        str(worldColumn % 10) for worldColumn in range(minColumn, maxColumn)
    )
    rowLabelWidth: int = max(len(str(maxRow - 1)), 2)
    labeledGridLines: list[str] = [
        f"{rowIndex:>{rowLabelWidth}}: {croppedGridLine}"
        for rowIndex, croppedGridLine in enumerate(
            croppedGridLines,
            start=minRow,
        )
    ]
    labeledRuler: str = f"{0:>{rowLabelWidth}}: {ruler}"
    return "\n".join([labeledRuler, *labeledGridLines, *wiringLegendLines])


def boardCanvas_render(
    *,
    board: Board,
    realizedRouteSet: RealizedRouteSet,
) -> tuple[str, ...]:
    """Render one board's chip/module canvas from canonical board geometry."""

    totalColumns = board.worldFrame.bottomRight[0] + 1
    totalRows = board.worldFrame.bottomRight[1] + 1
    charGrid: list[list[str]] = [[" "] * totalColumns for _ in range(totalRows)]

    for chipPlacement in board.geometry.chipDrawPlacementsByChip.values():
        _chipDrawPlacement_blit(
            chipPlacement=chipPlacement,
            charGrid=charGrid,
            totalRows=totalRows,
            totalCols=totalColumns,
        )

    for boundaryName, frame in board.geometry.effectiveBoundaryFramesByName.items():
        _moduleBoundary_blit(
            moduleName=boundaryName.removeprefix("module/"),
            frame=frame,
            charGrid=charGrid,
            totalRows=totalRows,
            totalCols=totalColumns,
        )

    chipPlacements = tuple(board.geometry.chipDrawPlacementsByChip.values())
    chipFrames = tuple(
        chipPlacement.worldFrame_get()
        for chipPlacement in chipPlacements
    )

    for (rowIndex, columnIndex), trackCell in realizedRouteSet.mergedCellMap_get().items():
        if _modulePaddingCell_check(
            columnIndex=columnIndex,
            rowIndex=rowIndex,
            moduleFrames=tuple(board.geometry.effectiveBoundaryFramesByName.values()),
            chipFrames=chipFrames,
            chipPlacements=chipPlacements,
        ):
            continue
        if 0 <= rowIndex < totalRows and 0 <= columnIndex < totalColumns and trackCell.glyph:
            charGrid[rowIndex][columnIndex] = _routeOverlayGlyph_build(
                existing=charGrid[rowIndex][columnIndex],
                trackCell=trackCell,
            )

    return tuple("".join(rowChars) for rowChars in charGrid)


def _regionDrawGrid_build(
    *,
    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame],
    effectiveBoundaryFramesByName: dict[str, RoutingZoneRegionFrame],
    columnOffset: int | None = None,
) -> list[str]:
    """Render filled board-region bands as a world-true text grid."""

    if not regionFramesById:
        return []

    regionIds = list(regionFramesById.keys())
    frames = list(regionFramesById.values()) + list(effectiveBoundaryFramesByName.values())

    colBreaks = sorted(
        {
            value
            for frame in frames
            for value in (
                frame.horizontalStart,
                frame.horizontalEnd_calculate(),
            )
        }
    )
    rowBreaks = sorted(
        {
            value
            for frame in frames
            for value in (
                frame.verticalStart,
                frame.verticalEnd_calculate(),
            )
        }
    )

    displayStartColumn = colBreaks[0] if columnOffset is None else max(0, columnOffset)
    displayEndColumn = colBreaks[-1]
    if displayStartColumn >= displayEndColumn:
        return []

    visibleColBreaks = sorted(
        {
            displayStartColumn,
            displayEndColumn,
            *(
                worldColumn
                for worldColumn in colBreaks
                if displayStartColumn <= worldColumn <= displayEndColumn
            ),
        }
    )

    colWidths = [
        visibleColBreaks[index + 1] - visibleColBreaks[index]
        for index in range(len(visibleColBreaks) - 1)
    ]
    rowHeights = [
        rowBreaks[index + 1] - rowBreaks[index]
        for index in range(len(rowBreaks) - 1)
    ]

    colStarts = [0]
    for width in colWidths:
        colStarts.append(colStarts[-1] + width)
    rowStarts = [0]
    for height in rowHeights:
        rowStarts.append(rowStarts[-1] + height)

    totalColumns = colStarts[-1]
    totalRows = rowStarts[-1]
    grid: list[list[str]] = [[" "] * totalColumns for _ in range(totalRows)]

    sortedRegionIds = sorted(
        regionIds,
        key=lambda regionId: -(
            regionFramesById[regionId].horizontalSpan
            * regionFramesById[regionId].verticalSpan
        ),
    )
    for regionId in sortedRegionIds:
        frame = regionFramesById[regionId]
        label = _regionSymbol_get(regionId)
        clippedHorizontalStart = max(frame.horizontalStart, displayStartColumn)
        clippedHorizontalEnd = min(frame.horizontalEnd_calculate(), displayEndColumn)
        if clippedHorizontalStart >= clippedHorizontalEnd:
            continue

        colBandStart = visibleColBreaks.index(clippedHorizontalStart)
        colBandEnd = visibleColBreaks.index(clippedHorizontalEnd)
        rowBandStart = rowBreaks.index(frame.verticalStart)
        rowBandEnd = rowBreaks.index(frame.verticalEnd_calculate())

        for rowBandIndex in range(rowBandStart, rowBandEnd):
            for colBandIndex in range(colBandStart, colBandEnd):
                displayRowStart = rowStarts[rowBandIndex]
                displayRowEnd = rowStarts[rowBandIndex + 1]
                displayColStart = colStarts[colBandIndex]
                displayColEnd = colStarts[colBandIndex + 1]
                for displayRow in range(displayRowStart, displayRowEnd):
                    for displayCol in range(displayColStart, displayColEnd):
                        grid[displayRow][displayCol] = label

    for boundaryName, frame in effectiveBoundaryFramesByName.items():
        _moduleBoundaryOverlay_blit(
            moduleName=boundaryName.removeprefix("module/"),
            frame=frame,
            grid=grid,
            displayStartColumn=displayStartColumn,
            firstWorldRow=rowBreaks[0],
        )

    rulerTop: list[str] = [" "] * totalColumns
    for bandIndex, worldColumn in enumerate(visibleColBreaks[:-1]):
        marker = str(worldColumn % 100)
        displayColumnStart = colStarts[bandIndex]
        for charIndex, character in enumerate(marker):
            if displayColumnStart + charIndex < totalColumns:
                rulerTop[displayColumnStart + charIndex] = character

    firstWorldRow = rowBreaks[0]
    rowLabelWidth = max(len(str(rowBreaks[-1] - 1)), 2)
    lines = [f"{0:>{rowLabelWidth}}: {''.join(rulerTop)}"]
    for displayRowIndex, row in enumerate(grid):
        lines.append(f"{firstWorldRow + displayRowIndex:>{rowLabelWidth}}: {''.join(row)}")
    return lines


def _moduleBoundaryOverlay_blit(
    *,
    moduleName: str,
    frame: RoutingZoneRegionFrame,
    grid: list[list[str]],
    displayStartColumn: int,
    firstWorldRow: int,
) -> None:
    """Overlay one effective module boundary on the board geometry grid."""

    totalRows = len(grid)
    totalCols = len(grid[0]) if grid else 0
    if totalRows == 0 or totalCols == 0:
        return

    r0 = frame.verticalStart - firstWorldRow
    c0 = frame.horizontalStart - displayStartColumn
    r1 = frame.verticalEnd_calculate() - 1 - firstWorldRow
    c1 = frame.horizontalEnd_calculate() - 1 - displayStartColumn
    if c1 <= c0 or r1 <= r0:
        return
    if r1 < 0 or c1 < 0 or r0 >= totalRows or c0 >= totalCols:
        return

    r0 = max(0, r0)
    c0 = max(0, c0)
    r1 = min(totalRows - 1, r1)
    c1 = min(totalCols - 1, c1)
    innerWidth = c1 - c0 - 1
    if innerWidth <= 0 or r1 <= r0:
        return

    def _write(rowIndex: int, columnIndex: int, ch: str) -> None:
        grid[rowIndex][columnIndex] = ch

    _write(r0, c0, "╔")
    fill = ("═ " + moduleName + " ").ljust(innerWidth, "═")[:innerWidth]
    for offset, ch in enumerate(fill):
        _write(r0, c0 + 1 + offset, ch)
    _write(r0, c1, "╗")
    for rowIndex in range(r0 + 1, r1):
        _write(rowIndex, c0, "║")
        _write(rowIndex, c1, "║")
    _write(r1, c0, "╚")
    for columnIndex in range(c0 + 1, c1):
        _write(r1, columnIndex, "═")
    _write(r1, c1, "╝")


def _chipDrawPlacement_blit(
    *,
    chipPlacement: BoardChipDrawPlacement,
    charGrid: list[list[str]],
    totalRows: int,
    totalCols: int,
) -> None:
    """Blit one chip's canonical draw lines into the board canvas."""

    drawColumn, drawRow = chipPlacement.drawTopLeft
    for lineIndex, line in enumerate(chipPlacement.drawLines):
        rowIndex = drawRow + lineIndex
        if not (0 <= rowIndex < totalRows):
            continue
        for charIndex, ch in enumerate(line):
            if ch == " ":
                continue
            columnIndex = drawColumn + charIndex
            if 0 <= columnIndex < totalCols:
                charGrid[rowIndex][columnIndex] = ch


def _moduleBoundary_blit(
    *,
    moduleName: str,
    frame: RoutingZoneRegionFrame,
    charGrid: list[list[str]],
    totalRows: int,
    totalCols: int,
) -> None:
    """Draw one effective module boundary as a double-line box."""

    r0 = max(0, frame.verticalStart)
    c0 = max(0, frame.horizontalStart)
    r1 = min(totalRows - 1, frame.verticalEnd_calculate() - 1)
    c1 = min(totalCols - 1, frame.horizontalEnd_calculate() - 1)
    innerWidth = c1 - c0 - 1
    if innerWidth <= 0 or r1 <= r0:
        return

    def _writeIfBlank(rowIndex: int, columnIndex: int, ch: str) -> None:
        if charGrid[rowIndex][columnIndex] == " ":
            charGrid[rowIndex][columnIndex] = ch

    _writeIfBlank(r0, c0, "╔")
    fill = ("═ " + moduleName + " ").ljust(innerWidth, "═")[:innerWidth]
    for offset, ch in enumerate(fill):
        _writeIfBlank(r0, c0 + 1 + offset, ch)
    _writeIfBlank(r0, c1, "╗")
    for rowIndex in range(r0 + 1, r1):
        _writeIfBlank(rowIndex, c0, "║")
        _writeIfBlank(rowIndex, c1, "║")
    _writeIfBlank(r1, c0, "╚")
    for columnIndex in range(c0 + 1, c1):
        _writeIfBlank(r1, columnIndex, "═")
    _writeIfBlank(r1, c1, "╝")


def _piercedGlyph(existing: str, trackCell: TrackCell) -> str:
    """Return the correct glyph when a route overlaps a module border cell."""

    directions = trackCell.directions
    hasHorizontal = TrackDirection.EAST in directions or TrackDirection.WEST in directions
    hasVertical = TrackDirection.NORTH in directions or TrackDirection.SOUTH in directions
    if existing == "║":
        return "╫" if hasHorizontal else "║"
    if existing == "═":
        return "╪" if hasVertical else "═"
    return trackCell.glyph


def _routeOverlayGlyph_build(existing: str, trackCell: TrackCell) -> str:
    """Return the visible glyph when a realized route overlays one board cell."""

    if existing in {"║", "═"}:
        return _piercedGlyph(existing, trackCell)
    if existing != " ":
        return existing
    return trackCell.glyph


def _modulePaddingCell_check(
    *,
    columnIndex: int,
    rowIndex: int,
    moduleFrames: tuple[RoutingZoneRegionFrame, ...],
    chipFrames: tuple[WorldFrame, ...],
    chipPlacements: tuple[BoardChipDrawPlacement, ...],
) -> bool:
    """Return whether one world cell is module padding reserved by doctrine.

    Effective module boundaries include explicit interior padding used to keep
    labels and chip drawings visually separated from the border. Realized route
    geometry may still traverse those cells on its way to exact terminals, but
    the padding itself should remain visually blank. A cell is considered
    module-padding when it lies inside a module boundary while outside every
    chip draw frame.
    """

    insideModule = any(
        frame.horizontalStart <= columnIndex < frame.horizontalEnd_calculate()
        and frame.verticalStart <= rowIndex < frame.verticalEnd_calculate()
        for frame in moduleFrames
    )
    if not insideModule:
        return False
    insideChip = any(
        frame.topLeft[0] <= columnIndex <= frame.bottomRight[0]
        and frame.topLeft[1] <= rowIndex <= frame.bottomRight[1]
        for frame in chipFrames
    )
    if insideChip:
        return False
    return not _terminalEntryPaddingCell_check(
        columnIndex=columnIndex,
        rowIndex=rowIndex,
        chipPlacements=chipPlacements,
    )


def _terminalEntryPaddingCell_check(
    *,
    columnIndex: int,
    rowIndex: int,
    chipPlacements: tuple[BoardChipDrawPlacement, ...],
) -> bool:
    """Return whether a padding cell belongs to a chip terminal-entry row."""

    for chipPlacement in chipPlacements:
        drawColumn, drawRow = chipPlacement.drawTopLeft
        lineIndex = rowIndex - drawRow
        if not (0 <= lineIndex < len(chipPlacement.drawLines)):
            continue
        line = chipPlacement.drawLines[lineIndex]
        nonSpaceIndices = [index for index, character in enumerate(line) if character != " "]
        if not nonSpaceIndices or min(nonSpaceIndices) != 0:
            continue
        if chipPlacement.side.value == "east" and columnIndex < drawColumn:
            return True
        if chipPlacement.side.value == "west" and columnIndex > drawColumn + max(nonSpaceIndices):
            return True
    return False


def _regionSymbol_get(regionId: BoardRegionId) -> str:
    """Return the board render glyph for one typed region id."""

    if regionId.family is RegionFamily.CHIP_TERMINAL and regionId.side is not None:
        return {
            "west": "░",
            "east": "▒",
            "north": "▓",
            "south": "█",
        }[regionId.side.value]
    if regionId.family is RegionFamily.INTRA_FAN and regionId.side is not None:
        return {
            "west": "🬤",
            "east": "🮥",
            "north": "🮧",
            "south": "🮪",
        }[regionId.side.value]
    if regionId.family is RegionFamily.INTER_FAN and regionId.side is not None:
        return {
            "west": "🬗",
            "east": "🮤",
            "north": "🮦",
            "south": "🮭",
        }[regionId.side.value]
    if regionId.family is RegionFamily.INTRA_LONGITUDE and regionId.side is not None:
        if regionId.side.value == "west":
            return "🭲"
        if regionId.side.value == "east":
            return "🭵"
    if regionId.family is RegionFamily.INTER_LONGITUDE and regionId.side is not None:
        if regionId.side.value == "west":
            return "▌"
        if regionId.side.value == "east":
            return "▐"
    if regionId.family is RegionFamily.INTRA_LATITUDE and regionId.side is not None:
        if regionId.side.value == "north":
            return "🭷"
        if regionId.side.value == "south":
            return "🭺"
    if regionId.family is RegionFamily.INTER_LATITUDE and regionId.side is not None:
        if regionId.side.value == "north":
            return "🭶"
        if regionId.side.value == "south":
            return "🭻"
    if regionId.family is RegionFamily.EXTRA_FAN and regionId.side is not None:
        return {
            "west": "◁",
            "east": "▷",
        }.get(regionId.side.value, "?")
    if regionId.family is RegionFamily.EXTRA_LONGITUDE and regionId.side is not None:
        return {
            "west": "▏",
            "east": "▕",
        }.get(regionId.side.value, "?")
    if regionId.family is RegionFamily.EXTRA_LATITUDE and regionId.side is not None:
        return {
            "north": "▔",
            "south": "▁",
        }.get(regionId.side.value, "?")
    if regionId.family is RegionFamily.EXTRA_TRANSITION:
        if regionId.side is not None and regionId.branch is not None:
            return {
                ("east", "north"): "╗",
                ("west", "north"): "╔",
                ("east", "south"): "╝",
                ("west", "south"): "╚",
            }.get((regionId.side.value, regionId.branch.value), "?")
    if regionId.family is RegionFamily.INTRA_EXTRA_TRANSFER:
        if regionId.side is not None and regionId.branch is not None:
            return {
                ("east", "north"): "╗",
                ("west", "north"): "╔",
                ("east", "south"): "╝",
                ("west", "south"): "╚",
            }.get((regionId.side.value, regionId.branch.value), "?")
    if regionId.family in {RegionFamily.INTRA_TRANSITION, RegionFamily.INTER_TRANSITION}:
        return "x" if regionId.family is RegionFamily.INTRA_TRANSITION else "X"
    if regionId.band in {RegionBand.UPPER, RegionBand.LOWER}:
        return REGION_SYMBOLS.get(regionId.family, "?")
    if regionId.branch in {RegionBranch.NORTH, RegionBranch.SOUTH}:
        return REGION_SYMBOLS.get(regionId.family, "?")
    return REGION_SYMBOLS.get(regionId.family, "?")
