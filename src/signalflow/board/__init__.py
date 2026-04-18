"""First-class board boundary for SignalFlow.

This package is the intended home for canonical board-domain models. The long
term goal is to let geometry, layout doctrine, substrate structure, exact
terminal truth, realization, validation, and rendering all speak a shared
board-native vocabulary instead of re-encoding the same facts in unrelated
subsystems.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from signalflow.board.board import Board
from signalflow.board.boxes import (
    BorderBox,
    ContentBox,
    EffectiveBoundary,
    KeepoutBox,
    PaddingBox,
)
from signalflow.board.channels_runtime import (
    BoardChannel,
    BoardChannels,
    BoardLane,
    BoardLanes,
)
from signalflow.board.chip_internal import (
    ChipInternalBoardSchema,
    ChipInternalBoardWire,
    ChipInternalPlacedKernelArtifacts,
    chipInternalBoardSchema_build,
    chipInternalCompatibilityKernel_build,
    chipInternalPlacedKernelArtifacts_build,
    compatibilityKernel_build,
)
from signalflow.board.chip_runtime import BoardChip
from signalflow.board.doctrine import (
    BoardAreaGeometry,
    BoardChipPlacementPolicy,
    BoardDoctrine,
    BoardGeometrySpec,
    BoardMaterializePolicy,
    BoardRelaxationSymmetry,
    EffectiveBoundaryMode,
    RingGeometrySpec,
)
from signalflow.board.geometry import BoardGeometry, GeometryZone
from signalflow.board.geometry.coupling import (
    GeometryCollectionOperand,
    GeometryCouplingApplied,
    GeometryCouplingExpr,
    GeometryCouplingFamily,
    GeometryCouplingOp,
    GeometryCouplingSymbolicExpr,
    GeometryCouplingZoneOperand,
    GeometryDependentKind,
    GeometryDependentRef,
    GeometryModuleOperand,
    chipTerminalCouplingAppliedResult_build,
    chipTerminalCouplingFamilyResult_build,
    chipTerminalCouplingSymbolicExprsResult_build,
    geometryCouplingAppliedResult_build,
    geometryCouplingExpr_buildFromSymbolic,
    zoneCouplingOperandResult_build,
    zoneCouplingOperandsResult_build,
)
from signalflow.board.geometry.mutation import (
    ZoneAdjacencyConstraint,
    ZoneGeometryMutation,
    ZoneGeometrySelector,
    boardRegionIdResult_fromSfN,
    zoneAdjacencyConstraint_buildFromExpr,
    zoneGeometryMutation_buildFromExpr,
    zoneGeometrySelector_buildFromTarget,
)
from signalflow.board.geometry.overlap import (
    ChipColumnOverlapApplied,
    ChipColumnOverlapMutationPlan,
    ChipColumnOverlapResolution,
    TerminalOverlapResolution,
    chipColumnOverlapAppliedResult_build,
    chipColumnOverlapMutationPlan_build,
    chipColumnOverlapResolutionResult_build,
    terminalOverlapResolutionResult_build,
)
from signalflow.board.invariants import ZoneSymbolicInvariants
from signalflow.board.kernel_runtime import (
    BoardKernel,
    BoardKernelWire,
    BoardWiring,
)
from signalflow.board.materialized_runtime import (
    BoardMaterializedSolution,
    BoardMaterializedWire,
    materializedSolution_build,
)
from signalflow.board.realizer import (
    AlgebraicRouteRealization,
    BoardRealizationPlan,
    RealizerPathInput,
    RealizerRouteInput,
    algebraicRouteRealization_build,
    algebraicRouteRealization_buildFromPath,
    realizationPlan_build,
    realizationPlan_buildFromPaths,
    regionFramesRelaxed_build,
)
from signalflow.board.render import (
    REGION_SYMBOLS,
    boardCanvas_render,
    boardGeometry_sprint,
    realizedGeometry_sprint,
)
from signalflow.board.solver import (
    SolverWireInput,
    boardChannelLaneCounts_build,
    boardChannelLaneCounts_buildBySfN,
    boardWireAlgebraicPath_build,
)
from signalflow.board.solver_runtime import (
    BoardSolution,
    BoardSolvedWire,
    BoardSolver,
)
from signalflow.board.substrate import BoardSubstrate
from signalflow.board.terminals import ChipTerminalSet, TerminalAttachPoint
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
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
from signalflow.board.zone_runtime import BoardZone

if TYPE_CHECKING:
    from signalflow.board.builders import (
        board_buildFromKernel as board_buildFromKernel,
    )
    from signalflow.board.builders import (
        board_buildFromZoneAndSide as board_buildFromZoneAndSide,
    )

__all__: list[str] = [
    "Board",
    "BoardAreaGeometry",
    "BoardDoctrine",
    "BoardGeometrySpec",
    "RingGeometrySpec",
    "ZoneSymbolicInvariants",
    "BoardChipDrawPlacement",
    "BoardChipPlacementPolicy",
    "BoardChip",
    "BoardChannel",
    "BoardChannels",
    "ChipInternalBoardSchema",
    "ChipInternalPlacedKernelArtifacts",
    "ChipInternalBoardWire",
    "compatibilityKernel_build",
    "EffectiveBoundaryMode",
    "BoardGeometry",
    "GeometryZone",
    "GeometryCouplingApplied",
    "GeometryCouplingExpr",
    "GeometryCouplingFamily",
    "GeometryCouplingOp",
    "GeometryCouplingSymbolicExpr",
    "GeometryCouplingZoneOperand",
    "GeometryCollectionOperand",
    "GeometryDependentKind",
    "GeometryDependentRef",
    "GeometryModuleOperand",
    "ZoneAdjacencyConstraint",
    "ZoneGeometryMutation",
    "ZoneGeometrySelector",
    "BoardKernel",
    "BoardKernelWire",
    "BoardLane",
    "BoardLanes",
    "BoardMaterializedSolution",
    "BoardMaterializedWire",
    "BoardMaterializePolicy",
    "ChipColumnOverlapApplied",
    "ChipColumnOverlapMutationPlan",
    "ChipColumnOverlapResolution",
    "TerminalOverlapResolution",
    "BoardRealizationPlan",
    "BoardRelaxationSymmetry",
    "BoardRegionId",
    "BoardSense",
    "BoardSide",
    "BoardSolution",
    "BoardSolvedWire",
    "BoardSolver",
    "BoardSubstrate",
    "BoardWiring",
    "BoardZone",
    "BorderBox",
    "ChipTerminalSet",
    "ContentBox",
    "EffectiveBoundary",
    "KeepoutBox",
    "PaddingBox",
    "REGION_SYMBOLS",
    "boardCanvas_render",
    "RealizerRouteInput",
    "RealizerPathInput",
    "SolverWireInput",
    "RegionBand",
    "RegionBranch",
    "RegionFamily",
    "TerminalAttachPoint",
    "WorldFrame",
    "WorldPoint",
    "AlgebraicRouteRealization",
    "algebraicRouteRealization_build",
    "algebraicRouteRealization_buildFromPath",
    "realizationPlan_build",
    "realizationPlan_buildFromPaths",
    "boardGeometry_sprint",
    "boardChannelLaneCounts_build",
    "boardChannelLaneCounts_buildBySfN",
    "chipInternalBoardSchema_build",
    "compatibilityKernel_build",
    "chipInternalCompatibilityKernel_build",
    "chipInternalPlacedKernelArtifacts_build",
    "boardWireAlgebraicPath_build",
    "realizedGeometry_sprint",
    "materializedSolution_build",
    "chipColumnOverlapAppliedResult_build",
    "chipColumnOverlapMutationPlan_build",
    "chipColumnOverlapResolutionResult_build",
    "terminalOverlapResolutionResult_build",
    "board_buildFromKernel",
    "board_buildFromZoneAndSide",
    "boardRegionIdResult_fromSfN",
    "chipTerminalCouplingAppliedResult_build",
    "chipTerminalCouplingFamilyResult_build",
    "chipTerminalCouplingSymbolicExprsResult_build",
    "geometryCouplingAppliedResult_build",
    "geometryCouplingExpr_buildFromSymbolic",
    "boardRegionId_buildFromRoutingZoneRegionId",
    "boardRegionLabel_build",
    "boardProblems_get",
    "regionFramesRelaxed_build",
    "zoneAdjacencyConstraint_buildFromExpr",
    "zoneCouplingOperandResult_build",
    "zoneCouplingOperandsResult_build",
    "zoneGeometryMutation_buildFromExpr",
    "zoneGeometrySelector_buildFromTarget",
]


def board_buildFromKernel(*args, **kwargs):
    from signalflow.board.builders import board_buildFromKernel as _impl

    return _impl(*args, **kwargs)


def board_buildFromZoneAndSide(*args, **kwargs):
    from signalflow.board.builders import (
        board_buildFromZoneAndSide as _impl,
    )

    return _impl(*args, **kwargs)
