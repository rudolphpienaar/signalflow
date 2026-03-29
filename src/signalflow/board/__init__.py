"""First-class board boundary for SignalFlow.

This package is the intended home for canonical board-domain models. The long
term goal is to let geometry, layout doctrine, substrate structure, exact
terminal truth, realization, validation, and rendering all speak a shared
board-native vocabulary instead of re-encoding the same facts in unrelated
subsystems.
"""
from __future__ import annotations

from signalflow.board.board import Board
from signalflow.board.boxes import (
    BorderBox,
    ContentBox,
    EffectiveBoundary,
    KeepoutBox,
    PaddingBox,
)
from signalflow.board.builders import board_buildFromKernel
from signalflow.board.doctrine import BoardDoctrine, EffectiveBoundaryMode
from signalflow.board.geometry import BoardGeometry
from signalflow.board.realizer import (
    AlgebraicRouteRealization,
    BoardRealizationPlan,
    RealizerRouteInput,
    algebraicRouteRealization_build,
    realizationPlan_build,
    regionFramesRelaxed_build,
)
from signalflow.board.render import (
    REGION_SYMBOLS,
    boardCanvas_render,
    boardGeometry_text,
    realizedGeometry_text,
)
from signalflow.board.substrate import BoardSubstrate
from signalflow.board.solver import (
    SolverWireInput,
    boardChannelLaneCounts_build,
    boardWireAlgebraicPath_build,
)
from signalflow.board.terminals import ChipTerminalSet, TerminalAttachPoint
from signalflow.board.types import (
    BoardRegionId,
    BoardChipDrawPlacement,
    BoardSense,
    BoardSide,
    RegionBand,
    RegionBranch,
    RegionFamily,
    WorldFrame,
    WorldPoint,
    boardRegionId_buildFromRoutingZoneRegionId,
    boardRegionLabel_build,
)
from signalflow.board.validators import boardProblems_get

__all__: list[str] = [
    "Board",
    "BoardDoctrine",
    "BoardChipDrawPlacement",
    "EffectiveBoundaryMode",
    "BoardGeometry",
    "BoardRealizationPlan",
    "BoardRegionId",
    "BoardSense",
    "BoardSide",
    "BoardSubstrate",
    "BorderBox",
    "ChipTerminalSet",
    "ContentBox",
    "EffectiveBoundary",
    "KeepoutBox",
    "PaddingBox",
    "REGION_SYMBOLS",
    "boardCanvas_render",
    "RealizerRouteInput",
    "SolverWireInput",
    "RegionBand",
    "RegionBranch",
    "RegionFamily",
    "TerminalAttachPoint",
    "WorldFrame",
    "WorldPoint",
    "AlgebraicRouteRealization",
    "algebraicRouteRealization_build",
    "realizationPlan_build",
    "boardGeometry_text",
    "boardChannelLaneCounts_build",
    "boardWireAlgebraicPath_build",
    "realizedGeometry_text",
    "board_buildFromKernel",
    "boardRegionId_buildFromRoutingZoneRegionId",
    "boardRegionLabel_build",
    "boardProblems_get",
    "regionFramesRelaxed_build",
]
