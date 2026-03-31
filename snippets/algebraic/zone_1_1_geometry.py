"""Inspect the board geometry for zone (1,1) in `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/zone_1_1_geometry.py")
"""

from __future__ import annotations

from signalflow.board import (
    Board,
    BoardChipPlacementPolicy,
    BoardKernel,
)

kernel: BoardKernel = zones.zone_get(1, 1).kernel_get("intra")  # noqa: F821 -- zones is injected by the SignalFlow REPL, not a module-level import
board: Board = kernel.board_get(
    chipPlacementPolicy=BoardChipPlacementPolicy.CENTROIDAL
)

print(board.geometry_text())
