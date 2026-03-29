"""Compatibility wrapper for board-domain route realization.

The canonical home for symbolic board realization is now
`signalflow.board.realizer`. This module remains as a migration shim so older
imports continue to work while the rest of the codebase moves over.
"""
from __future__ import annotations

from signalflow.board.realizer import (
    AlgebraicRouteRealization,
    BoardRealizationPlan,
    RealizerRouteInput,
    WorldPoint,
    algebraicRouteRealization_build,
    realizationPlan_build,
    regionFramesRelaxed_build,
)

__all__ = [
    "AlgebraicRouteRealization",
    "BoardRealizationPlan",
    "RealizerRouteInput",
    "WorldPoint",
    "algebraicRouteRealization_build",
    "realizationPlan_build",
    "regionFramesRelaxed_build",
]
