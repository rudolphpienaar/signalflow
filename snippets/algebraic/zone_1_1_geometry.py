"""Inspect the board geometry for zone (1,1) in `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/zone_1_1_geometry.py")
"""

from __future__ import annotations

from signalflow.board import (
    Board,
    BoardChipPlacementPolicy,
    BoardKernel,
    GeometryZone,
)

kernel: BoardKernel = zones.zone_get(  # type: ignore[name-defined]  # noqa: F821
    1, 1
).kernel_get(
    "intra"
)  # zones is injected by the SignalFlow REPL, not a module-level import
board: Board = kernel.board_get(
    chipPlacementPolicy=BoardChipPlacementPolicy.CENTROIDAL
)

print(board.geometry_sprint())
print()
print("geometry zones:")
geometryZone: GeometryZone
for geometryZone in board.geometry_get().zones_get():
    print(f"  {geometryZone.summary_sprint()}")
