"""Resolve pairwise board-side overlap for adjacent zones.

This module currently handles the first overlap phase for west/east neighbors:

- compare the west zone's east chip-terminal column with the east zone's west
  chip-terminal column
- choose one dominant column
- report the shared target frame and the shifts required to align the
  recessive column to it
- project per-chip target frames for read-only inspection
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from signalflow.board.board import Board
from signalflow.board.geometry.zones import BoardGeometry, GeometryZone
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    BoardSide,
    RegionFamily,
    TerminalPositionsByChip,
    WorldFrame,
    WorldPoint,
)
from signalflow.models import RoutingZoneRegionFrame
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)


def _worldFrameShifted_build(
    frame: WorldFrame,
    *,
    deltaColumns: int,
    deltaRows: int,
) -> WorldFrame:
    """Build a world frame shifted by the given deltas.

    Args:
        frame: Source world frame.
        deltaColumns: Horizontal shift to apply in world columns.
        deltaRows: Vertical shift to apply in world rows.

    Returns:
        One inclusive world frame translated by the given column and row
        deltas.
    """

    return WorldFrame(
        topLeft=(
            frame.topLeft[0] + deltaColumns,
            frame.topLeft[1] + deltaRows,
        ),
        bottomRight=(
            frame.bottomRight[0] + deltaColumns,
            frame.bottomRight[1] + deltaRows,
        ),
    )


def _worldPointShifted_build(
    worldPoint: WorldPoint,
    *,
    deltaColumns: int,
    deltaRows: int,
) -> WorldPoint:
    """Build a world point shifted by the given deltas.

    Args:
        worldPoint: Source world point.
        deltaColumns: Horizontal shift to apply in world columns.
        deltaRows: Vertical shift to apply in world rows.

    Returns:
        Shifted `(columnIndex, rowIndex)` world coordinate.
    """

    return (worldPoint[0] + deltaColumns, worldPoint[1] + deltaRows)


def _routingZoneRegionFrameShifted_build(
    frame: RoutingZoneRegionFrame,
    *,
    deltaColumns: int,
    deltaRows: int,
) -> RoutingZoneRegionFrame:
    """Build a routing-zone region frame shifted by the given deltas.

    Args:
        frame: Source routing-zone region frame.
        deltaColumns: Horizontal shift to apply in world columns.
        deltaRows: Vertical shift to apply in world rows.

    Returns:
        Shifted routing-zone region frame with unchanged spans.
    """

    return RoutingZoneRegionFrame(
        horizontalStart=frame.horizontalStart + deltaColumns,
        verticalStart=frame.verticalStart + deltaRows,
        horizontalSpan=frame.horizontalSpan,
        verticalSpan=frame.verticalSpan,
    )


def _columnWorldFrame_build(
    geometryZone: GeometryZone,
) -> WorldFrame:
    """Build the effective chip-column frame for a chip-terminal zone.

    Chip occupancy is authoritative when present. Otherwise the geometry-zone
    frame itself acts as the chip-column envelope.

    Args:
        geometryZone: Chip-terminal geometry zone whose effective column frame
            should be derived.

    Returns:
        The effective chip-column world frame for the given geometry zone.
    """

    chips = geometryZone.chips_get()
    if not chips:
        return geometryZone.worldFrame_get()

    chipFrames = tuple(
        chipPlacement.worldFrame_get() for chipPlacement in chips
    )
    return WorldFrame(
        topLeft=(
            min(chipFrame.topLeft[0] for chipFrame in chipFrames),
            min(chipFrame.topLeft[1] for chipFrame in chipFrames),
        ),
        bottomRight=(
            max(chipFrame.bottomRight[0] for chipFrame in chipFrames),
            max(chipFrame.bottomRight[1] for chipFrame in chipFrames),
        ),
    )


def _chipTargetFramesByName_build(
    *,
    chipPlacements: tuple[BoardChipDrawPlacement, ...],
    deltaColumns: int,
    deltaRows: int,
) -> dict[str, WorldFrame]:
    """Build projected target chip frames after a rigid column shift.

    Args:
        chipPlacements: Chip placements to project.
        deltaColumns: Horizontal shift to apply to every chip frame.
        deltaRows: Vertical shift to apply to every chip frame.

    Returns:
        A mapping from chip name to projected target world frame.
    """

    return {
        chipPlacement.chipName: _worldFrameShifted_build(
            chipPlacement.worldFrame_get(),
            deltaColumns=deltaColumns,
            deltaRows=deltaRows,
        )
        for chipPlacement in chipPlacements
    }


def _chipPlacementsShiftedByName_build(
    *,
    chipPlacements: dict[str, BoardChipDrawPlacement],
    deltaColumns: int,
    deltaRows: int,
) -> dict[str, BoardChipDrawPlacement]:
    """Build shifted chip placements keyed by chip name.

    Args:
        chipPlacements: Chip placements to shift.
        deltaColumns: Horizontal shift to apply to each placement.
        deltaRows: Vertical shift to apply to each placement.

    Returns:
        Mapping from chip name to shifted placement.
    """

    return {
        chipName: replace(
            chipPlacement,
            drawTopLeft=_worldPointShifted_build(
                chipPlacement.drawTopLeft,
                deltaColumns=deltaColumns,
                deltaRows=deltaRows,
            ),
        )
        for chipName, chipPlacement in chipPlacements.items()
    }


def _terminalPositionsShiftedByChip_build(
    *,
    terminalPositionsByChip: TerminalPositionsByChip,
    deltaColumns: int,
    deltaRows: int,
) -> TerminalPositionsByChip:
    """Build shifted exact terminal positions keyed by chip and terminal.

    Args:
        terminalPositionsByChip: Exact terminal positions to shift.
        deltaColumns: Horizontal shift to apply to each terminal point.
        deltaRows: Vertical shift to apply to each terminal point.

    Returns:
        Shifted exact terminal positions keyed by chip and terminal.
    """

    return {
        chipName: {
            terminalName: _worldPointShifted_build(
                worldPoint,
                deltaColumns=deltaColumns,
                deltaRows=deltaRows,
            )
            for terminalName, worldPoint in terminalPositions.items()
        }
        for chipName, terminalPositions in terminalPositionsByChip.items()
    }


def _dominantSide_build(
    westColumnFrame: WorldFrame,
    eastColumnFrame: WorldFrame,
) -> BoardSide:
    """Choose the dominant chip column for a west/east overlap pair.

    Current doctrine:
    - taller column wins
    - if tied, wider column wins
    - if still tied, earlier north row wins
    - if still tied, prefer west for determinism

    Args:
        westColumnFrame: Effective west-side chip-column frame.
        eastColumnFrame: Effective east-side chip-column frame.

    Returns:
        The side whose chip column is currently dominant.
    """

    westRank = (
        westColumnFrame.heightRows,
        westColumnFrame.widthColumns,
        -westColumnFrame.topLeft[1],
    )
    eastRank = (
        eastColumnFrame.heightRows,
        eastColumnFrame.widthColumns,
        -eastColumnFrame.topLeft[1],
    )
    if westRank >= eastRank:
        return BoardSide.WEST
    return BoardSide.EAST


@dataclass(frozen=True)
class ChipColumnOverlapResolution:
    """Describe one pairwise chip-column overlap harmonization result.

    Attributes:
        westRegionId: East-side chip-terminal region id for the west board.
        eastRegionId: West-side chip-terminal region id for the east board.
        westZone: West board chip-terminal geometry zone participating in the
            overlap.
        eastZone: East board chip-terminal geometry zone participating in the
            overlap.
        westColumnFrame: Effective chip-column frame for the west zone.
        eastColumnFrame: Effective chip-column frame for the east zone.
        dominantSide: Side whose chip column currently defines the shared
            target frame.
        targetColumnFrame: Shared target chip-column frame after
            harmonization.
        westChipTargetFramesByName: Projected target chip frames for west-side
            chips after alignment.
        eastChipTargetFramesByName: Projected target chip frames for east-side
            chips after alignment.
    """

    westRegionId: BoardRegionId
    eastRegionId: BoardRegionId
    westZone: GeometryZone
    eastZone: GeometryZone
    westColumnFrame: WorldFrame
    eastColumnFrame: WorldFrame
    dominantSide: BoardSide
    targetColumnFrame: WorldFrame
    westChipTargetFramesByName: dict[str, WorldFrame]
    eastChipTargetFramesByName: dict[str, WorldFrame]

    @property
    def westTopLeft(self) -> tuple[int, int]:
        """Return the west chip-column top-left coordinate.

        Returns:
            The west chip-column top-left in world coordinates.
        """

        return self.westColumnFrame.topLeft

    @property
    def eastTopLeft(self) -> tuple[int, int]:
        """Return the east chip-column top-left coordinate.

        Returns:
            The east chip-column top-left in world coordinates.
        """

        return self.eastColumnFrame.topLeft

    @property
    def westSize(self) -> tuple[int, int]:
        """Return the west chip-column size.

        Returns:
            The west chip-column size as `(widthColumns, heightRows)`.
        """

        return (
            self.westColumnFrame.widthColumns,
            self.westColumnFrame.heightRows,
        )

    @property
    def eastSize(self) -> tuple[int, int]:
        """Return the east chip-column size.

        Returns:
            The east chip-column size as `(widthColumns, heightRows)`.
        """

        return (
            self.eastColumnFrame.widthColumns,
            self.eastColumnFrame.heightRows,
        )

    @property
    def westDeltaColumns(self) -> int:
        """Return the west chip-column horizontal alignment delta.

        Returns:
            The number of columns the west chip column must move to align with
            the target frame.
        """

        return (
            self.targetColumnFrame.topLeft[0]
            - self.westColumnFrame.topLeft[0]
        )

    @property
    def westDeltaRows(self) -> int:
        """Return the west chip-column vertical alignment delta.

        Returns:
            The number of rows the west chip column must move to align with the
            target frame.
        """

        return (
            self.targetColumnFrame.topLeft[1]
            - self.westColumnFrame.topLeft[1]
        )

    @property
    def eastDeltaColumns(self) -> int:
        """Return the east chip-column horizontal alignment delta.

        Returns:
            The number of columns the east chip column must move to align with
            the target frame.
        """

        return (
            self.targetColumnFrame.topLeft[0]
            - self.eastColumnFrame.topLeft[0]
        )

    @property
    def eastDeltaRows(self) -> int:
        """Return the east chip-column vertical alignment delta.

        Returns:
            The number of rows the east chip column must move to align with the
            target frame.
        """

        return (
            self.targetColumnFrame.topLeft[1]
            - self.eastColumnFrame.topLeft[1]
        )

    @property
    def westExtent(self) -> int:
        """Return the west chip-column height for compatibility.

        Returns:
            The west chip-column height in rows.
        """

        return self.westColumnFrame.heightRows

    @property
    def eastExtent(self) -> int:
        """Return the east chip-column height for compatibility.

        Returns:
            The east chip-column height in rows.
        """

        return self.eastColumnFrame.heightRows

    @property
    def targetExtent(self) -> int:
        """Return the shared target chip-column height for compatibility.

        Returns:
            The harmonized target chip-column height in rows.
        """

        return self.targetColumnFrame.heightRows

    @property
    def westDelta(self) -> int:
        """Return extra west chip-column height required for compatibility.

        Returns:
            The additional west chip-column height needed to reach the target
            extent.
        """

        return self.targetExtent - self.westExtent

    @property
    def eastDelta(self) -> int:
        """Return extra east chip-column height required for compatibility.

        Returns:
            The additional east chip-column height needed to reach the target
            extent.
        """

        return self.targetExtent - self.eastExtent


@dataclass(frozen=True)
class ChipColumnOverlapMutationPlan:
    """Describe the first concrete chip-column overlap mutation plan.

    Attributes:
        dominantSide: Side whose chip column remains fixed.
        recessiveSide: Side whose chip-terminal geometry must move.
        recessiveRegionId: Canonical region id of the recessive chip-terminal
            geometry zone.
        deltaColumns: Horizontal shift applied to the recessive side.
        deltaRows: Vertical shift applied to the recessive side.
        targetRegionFrame: Shifted target frame for the recessive geometry
            zone.
        targetChipPlacementsByChip: Shifted chip placements for the recessive
            chip column.
        targetExactTerminalWorldPositionsByChip: Shifted exact terminal points
            for the recessive chip column.
    """

    dominantSide: BoardSide
    recessiveSide: BoardSide
    recessiveRegionId: BoardRegionId
    deltaColumns: int
    deltaRows: int
    targetRegionFrame: RoutingZoneRegionFrame
    targetChipPlacementsByChip: dict[str, BoardChipDrawPlacement]
    targetExactTerminalWorldPositionsByChip: TerminalPositionsByChip


@dataclass(frozen=True)
class ChipColumnOverlapApplied:
    """Describe the applied result of the first chip-column overlap mutation.

    Attributes:
        resolution: Read-only overlap resolution used to choose the mutation.
        mutationPlan: Concrete mutation applied to the recessive chip-terminal
            zone.
        westBoard: West board after application.
        eastBoard: East board after application.
    """

    resolution: ChipColumnOverlapResolution
    mutationPlan: ChipColumnOverlapMutationPlan
    westBoard: Board
    eastBoard: Board


TerminalOverlapResolution = ChipColumnOverlapResolution


def chipColumnOverlapResolutionResult_build(
    westBoard: Board,
    eastBoard: Board,
) -> Result[ChipColumnOverlapResolution]:
    """Build a pairwise chip-column overlap resolution for two boards.

    Args:
        westBoard: Board whose east chip-terminal column participates in the
            overlap.
        eastBoard: Board whose west chip-terminal column participates in the
            overlap.

    Returns:
        A successful overlap resolution when both chip-terminal zones are
        present, otherwise an error result.
    """

    westRegionId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL,
        side=BoardSide.EAST,
    )
    eastRegionId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL,
        side=BoardSide.WEST,
    )
    westZone = westBoard.geometry_get().geometryZonesById.get(westRegionId)
    eastZone = eastBoard.geometry_get().geometryZonesById.get(eastRegionId)
    if westZone is None or eastZone is None:
        return resultErr_build()

    westColumnFrame = _columnWorldFrame_build(westZone)
    eastColumnFrame = _columnWorldFrame_build(eastZone)
    dominantSide = _dominantSide_build(westColumnFrame, eastColumnFrame)
    targetColumnFrame = (
        westColumnFrame if dominantSide is BoardSide.WEST else eastColumnFrame
    )
    return resultOk_build(
        ChipColumnOverlapResolution(
            westRegionId=westRegionId,
            eastRegionId=eastRegionId,
            westZone=westZone,
            eastZone=eastZone,
            westColumnFrame=westColumnFrame,
            eastColumnFrame=eastColumnFrame,
            dominantSide=dominantSide,
            targetColumnFrame=targetColumnFrame,
            westChipTargetFramesByName=_chipTargetFramesByName_build(
                chipPlacements=westZone.chips_get(),
                deltaColumns=(
                    targetColumnFrame.topLeft[0] - westColumnFrame.topLeft[0]
                ),
                deltaRows=(
                    targetColumnFrame.topLeft[1] - westColumnFrame.topLeft[1]
                ),
            ),
            eastChipTargetFramesByName=_chipTargetFramesByName_build(
                chipPlacements=eastZone.chips_get(),
                deltaColumns=(
                    targetColumnFrame.topLeft[0] - eastColumnFrame.topLeft[0]
                ),
                deltaRows=(
                    targetColumnFrame.topLeft[1] - eastColumnFrame.topLeft[1]
                ),
            ),
        )
    )


def chipColumnOverlapMutationPlan_build(
    resolution: ChipColumnOverlapResolution,
) -> ChipColumnOverlapMutationPlan:
    """Build a concrete chip-column overlap mutation plan.

    Args:
        resolution: Pairwise chip-column overlap resolution.

    Returns:
        Concrete mutation plan for the recessive chip-terminal zone.
    """

    if resolution.dominantSide is BoardSide.WEST:
        recessiveZone = resolution.eastZone
        recessiveRegionId = resolution.eastRegionId
        recessiveSide = BoardSide.EAST
        deltaColumns = resolution.eastDeltaColumns
        deltaRows = resolution.eastDeltaRows
        targetChipPlacementsByChip = _chipPlacementsShiftedByName_build(
            chipPlacements=recessiveZone.chipDrawPlacementsByChip,
            deltaColumns=deltaColumns,
            deltaRows=deltaRows,
        )
        targetExactTerminalWorldPositionsByChip = (
            _terminalPositionsShiftedByChip_build(
                terminalPositionsByChip=(
                    recessiveZone.exactTerminalWorldPositionsByChip
                ),
                deltaColumns=deltaColumns,
                deltaRows=deltaRows,
            )
        )
    else:
        recessiveZone = resolution.westZone
        recessiveRegionId = resolution.westRegionId
        recessiveSide = BoardSide.WEST
        deltaColumns = resolution.westDeltaColumns
        deltaRows = resolution.westDeltaRows
        targetChipPlacementsByChip = _chipPlacementsShiftedByName_build(
            chipPlacements=recessiveZone.chipDrawPlacementsByChip,
            deltaColumns=deltaColumns,
            deltaRows=deltaRows,
        )
        targetExactTerminalWorldPositionsByChip = (
            _terminalPositionsShiftedByChip_build(
                terminalPositionsByChip=(
                    recessiveZone.exactTerminalWorldPositionsByChip
                ),
                deltaColumns=deltaColumns,
                deltaRows=deltaRows,
            )
        )
    return ChipColumnOverlapMutationPlan(
        dominantSide=resolution.dominantSide,
        recessiveSide=recessiveSide,
        recessiveRegionId=recessiveRegionId,
        deltaColumns=deltaColumns,
        deltaRows=deltaRows,
        targetRegionFrame=_routingZoneRegionFrameShifted_build(
            recessiveZone.frame,
            deltaColumns=deltaColumns,
            deltaRows=deltaRows,
        ),
        targetChipPlacementsByChip=targetChipPlacementsByChip,
        targetExactTerminalWorldPositionsByChip=(
            targetExactTerminalWorldPositionsByChip
        ),
    )


def _boardGeometryWithAppliedPlan_build(
    boardGeometry: BoardGeometry,
    mutationPlan: ChipColumnOverlapMutationPlan,
) -> BoardGeometry:
    """Build board geometry with one recessive chip-terminal plan applied.

    Args:
        boardGeometry: Source canonical board geometry.
        mutationPlan: Concrete mutation plan to apply.

    Returns:
        New canonical board geometry with the recessive chip-terminal zone,
        owned chip placements, and owned exact terminal points shifted.
    """

    sourceZone = boardGeometry.geometryZonesById[
        mutationPlan.recessiveRegionId
    ]
    geometryZonesById = dict(boardGeometry.geometryZonesById)
    geometryZonesById[mutationPlan.recessiveRegionId] = GeometryZone(
        regionId=sourceZone.regionId,
        frame=mutationPlan.targetRegionFrame,
        routingZoneRegionId=sourceZone.routingZoneRegionId,
        chipDrawPlacementsByChip=mutationPlan.targetChipPlacementsByChip,
        exactTerminalWorldPositionsByChip=(
            mutationPlan.targetExactTerminalWorldPositionsByChip
        ),
    )
    return BoardGeometry(
        geometryZonesById=geometryZonesById,
        geometryScopes=boardGeometry.geometryScopes,
    )


def chipColumnOverlapAppliedResult_build(
    westBoard: Board,
    eastBoard: Board,
) -> Result[ChipColumnOverlapApplied]:
    """Build the first applied chip-column overlap result for two boards.

    Args:
        westBoard: Board whose east chip-terminal column participates in the
            overlap.
        eastBoard: Board whose west chip-terminal column participates in the
            overlap.

    Returns:
        Applied overlap result when both chip-terminal zones are present,
        otherwise an error result.
    """

    resolutionResult = chipColumnOverlapResolutionResult_build(
        westBoard=westBoard,
        eastBoard=eastBoard,
    )
    if not result_isOkCheck(resolutionResult):
        return resultErr_build()
    resolution = resolutionResult.value
    mutationPlan = chipColumnOverlapMutationPlan_build(resolution)
    if mutationPlan.recessiveSide is BoardSide.WEST:
        appliedWestBoard = replace(
            westBoard,
            geometry=_boardGeometryWithAppliedPlan_build(
                westBoard.geometry_get(),
                mutationPlan,
            ),
        )
        appliedEastBoard = eastBoard
    else:
        appliedWestBoard = westBoard
        appliedEastBoard = replace(
            eastBoard,
            geometry=_boardGeometryWithAppliedPlan_build(
                eastBoard.geometry_get(),
                mutationPlan,
            ),
        )
    return resultOk_build(
        ChipColumnOverlapApplied(
            resolution=resolution,
            mutationPlan=mutationPlan,
            westBoard=appliedWestBoard,
            eastBoard=appliedEastBoard,
        )
    )


def terminalOverlapResolutionResult_build(
    westBoard: Board,
    eastBoard: Board,
) -> Result[TerminalOverlapResolution]:
    """Build a compatibility terminal-overlap resolution.

    This is the legacy entrypoint name retained for compatibility. The
    returned value is the richer chip-column overlap resolution.

    Args:
        westBoard: Board whose east chip-terminal column participates in the
            overlap.
        eastBoard: Board whose west chip-terminal column participates in the
            overlap.

    Returns:
        The chip-column overlap resolution wrapped in the legacy result type
        alias.
    """

    return chipColumnOverlapResolutionResult_build(
        westBoard=westBoard,
        eastBoard=eastBoard,
    )


__all__ = [
    "ChipColumnOverlapResolution",
    "ChipColumnOverlapMutationPlan",
    "ChipColumnOverlapApplied",
    "TerminalOverlapResolution",
    "chipColumnOverlapAppliedResult_build",
    "chipColumnOverlapMutationPlan_build",
    "chipColumnOverlapResolutionResult_build",
    "terminalOverlapResolutionResult_build",
]
