"""Materialized world-board aggregate for overlap-zone chains."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from signalflow.board.board import Board
from signalflow.board.geometry.world_resolver import WorldChainResolution
from signalflow.board.materialized_runtime import BoardMaterializedSolution
from signalflow.board.render import boardCanvas_render
from signalflow.board.solver_runtime import BoardSolver
from signalflow.routing.track import TrackCell

_WIRE_H: frozenset[str] = frozenset({"═", "╪"})
_WIRE_V: frozenset[str] = frozenset({"║", "╫"})
_WIRE_ALL: frozenset[str] = _WIRE_H | _WIRE_V

_BD_N: int = 1
_BD_S: int = 2
_BD_E: int = 4
_BD_W: int = 8

_SINGLE_DIR: dict[str, int] = {
    "─": _BD_E | _BD_W,
    "│": _BD_N | _BD_S,
    "┌": _BD_E | _BD_S,
    "┐": _BD_W | _BD_S,
    "└": _BD_E | _BD_N,
    "┘": _BD_W | _BD_N,
    "├": _BD_N | _BD_S | _BD_E,
    "┤": _BD_N | _BD_S | _BD_W,
    "┬": _BD_E | _BD_W | _BD_S,
    "┴": _BD_E | _BD_W | _BD_N,
    "┼": _BD_N | _BD_S | _BD_E | _BD_W,
}
_DIR_SINGLE: dict[int, str] = {
    value: key for key, value in _SINGLE_DIR.items()
}


def _worldBlit_apply(existing: str, incoming: str) -> str:
    """Compose one glyph onto another using route-crossing algebra."""

    if existing in _WIRE_ALL:
        if incoming not in _WIRE_ALL:
            return existing
        if existing in _WIRE_H and incoming in _WIRE_V:
            return "╪"
        if existing in _WIRE_V and incoming in _WIRE_H:
            return "╫"
        return existing
    if existing in _SINGLE_DIR and incoming in _SINGLE_DIR:
        return _DIR_SINGLE.get(
            _SINGLE_DIR[existing] | _SINGLE_DIR[incoming],
            incoming,
        )
    return incoming


@dataclass(frozen=True)
class BoardWorldMaterializedSolution:
    """Harmonized overlap-zone chain in world coordinates."""

    resolution: WorldChainResolution
    materializedByIndex: dict[int, BoardMaterializedSolution]

    @staticmethod
    def fromResolvedChain_build(
        boardByIndex: dict[int, Board],
        solverByIndex: dict[int, BoardSolver],
        resolution: WorldChainResolution,
    ) -> BoardWorldMaterializedSolution:
        """Materialize every resolved board with harmonized geometry."""

        materializedByIndex: dict[int, BoardMaterializedSolution] = {}
        for index, geometry in resolution.geometryByIndex.items():
            board: Board = replace(boardByIndex[index], geometry=geometry)
            materializedByIndex[index] = (
                solverByIndex[index].solution_get().board_materialize(
                    board=board
                )
            )
        return BoardWorldMaterializedSolution(
            resolution=resolution,
            materializedByIndex=materializedByIndex,
        )

    def offsetsReoriginated_get(self, originIndex: int) -> dict[int, int]:
        """Return offsets shifted so `originIndex` starts at column zero."""

        return self.resolution.reoriginatedOffsets_get(originIndex)

    def geometry_sprint(
        self,
        indexes: Sequence[int],
        *,
        legend_show: bool = True,
    ) -> str:
        """Render per-zone relaxed geometry for selected world indexes."""

        lines: list[str] = []
        for index in indexes:
            materialized: BoardMaterializedSolution | None = (
                self.materializedByIndex.get(index)
            )
            lines.append(f"=== ZONE (1,{index}) GEOMETRY ===")
            lines.append("")
            if materialized is None:
                lines.append("  (not materialized)")
            else:
                lines.append(
                    materialized.geometryRelaxed_sprint(
                        legend_show=legend_show
                    )
                )
            lines.append("")
        return "\n".join(lines)

    def wiring_sprint(self, indexes: Sequence[int]) -> str:
        """Render selected zones on one re-originated world canvas."""

        activeIndexes: list[int] = [
            index for index in indexes if index in self.materializedByIndex
        ]
        if not activeIndexes:
            return "--- WORLD WIRING:  ---\n"

        originIndex: int = indexes[0]
        wOffsets: dict[int, int] = self.offsetsReoriginated_get(originIndex)
        maxColumns: int = 0
        maxRows: int = 0

        for index in activeIndexes:
            wOffset: int = wOffsets.get(index, 0)
            materialized: BoardMaterializedSolution = (
                self.materializedByIndex[index]
            )
            relaxedBoard: Board = materialized._relaxedShadowBoard_build()
            for frame in relaxedBoard.geometry.regionFramesById.values():
                maxColumns = max(
                    maxColumns,
                    frame.horizontalEnd_calculate() + wOffset,
                )
                maxRows = max(maxRows, frame.verticalEnd_calculate())
            for frame in (
                relaxedBoard.geometry.effectiveBoundaryFramesByName.values()
            ):
                maxColumns = max(
                    maxColumns,
                    frame.horizontalEnd_calculate() + wOffset,
                )
                maxRows = max(maxRows, frame.verticalEnd_calculate())
            for chipPlacement in (
                relaxedBoard.geometry.chipDrawPlacementsByChip.values()
            ):
                worldFrame = chipPlacement.worldFrame_get()
                maxColumns = max(
                    maxColumns,
                    worldFrame.bottomRight[0] + 1 + wOffset,
                )
                maxRows = max(maxRows, worldFrame.bottomRight[1] + 1)
            routeCellMap: dict[tuple[int, int], TrackCell] = (
                materialized._realizedRouteSet.mergedCellMap_get()
            )
            for row, column in routeCellMap:
                maxColumns = max(maxColumns, column + 1 + wOffset)
                maxRows = max(maxRows, row + 1)

        worldGrid: list[list[str]] = [
            [" "] * maxColumns for _rowIndex in range(maxRows)
        ]

        for index in activeIndexes:
            wOffset = wOffsets.get(index, 0)
            materialized = self.materializedByIndex[index]
            relaxedBoard = materialized._relaxedShadowBoard_build()
            renderedLines: tuple[str, ...] = boardCanvas_render(
                board=relaxedBoard,
                realizedRouteSet=materialized._realizedRouteSet,
            )
            for rowIndex, line in enumerate(renderedLines):
                for columnIndex, glyph in enumerate(line):
                    worldColumn: int = columnIndex + wOffset
                    if (
                        glyph != " "
                        and 0 <= rowIndex < maxRows
                        and 0 <= worldColumn < maxColumns
                    ):
                        existing: str = worldGrid[rowIndex][worldColumn]
                        worldGrid[rowIndex][worldColumn] = (
                            _worldBlit_apply(existing, glyph)
                            if existing != " "
                            else glyph
                        )
            for (
                (row, column),
                trackCell,
            ) in materialized._realizedRouteSet.mergedCellMap_get().items():
                worldColumn = column + wOffset
                if (
                    trackCell.glyph
                    and trackCell.glyph != " "
                    and 0 <= row < maxRows
                    and 0 <= worldColumn < maxColumns
                    and worldGrid[row][worldColumn] == " "
                ):
                    worldGrid[row][worldColumn] = trackCell.glyph

        zoneLabel: str = "  ".join(f"(1,{index})" for index in activeIndexes)
        ruler: str = "".join(str(column % 10) for column in range(maxColumns))
        lines = [f"--- WORLD WIRING: {zoneLabel} ---", "", f"    {ruler}"]
        for rowIndex, row in enumerate(worldGrid):
            if any(glyph != " " for glyph in row):
                lines.append(f"{rowIndex:3}: {''.join(row)}")
        lines.append("")
        return "\n".join(lines)
