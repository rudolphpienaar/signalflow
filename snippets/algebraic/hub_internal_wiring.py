"""Inspect the internal wiring board for `Hub.ts.process()` in `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/hub_internal_wiring.py")
"""

from __future__ import annotations

from signalflow.board import (
    Board,
    BoardChip,
    BoardChipPlacementPolicy,
    BoardKernel,
    BoardMaterializePolicy,
    BoardMaterializedSolution,
    BoardRelaxationSymmetry,
    BoardSolution,
    BoardSolver,
)

chip: BoardChip = chips.chip_get("Hub.ts", "process()")
kernel: BoardKernel = chip.internalBoard_get()
board: Board = kernel.board_get(
    chipPlacementPolicy=BoardChipPlacementPolicy.CENTROIDAL
)
solver: BoardSolver = kernel.solver_get(board)
solution: BoardSolution = solver.solution_get()
materialized: BoardMaterializedSolution = solution.board_materialize(
    board,
    policy=BoardMaterializePolicy(
        relaxationSymmetry=BoardRelaxationSymmetry.MINIMAL
    ),
)

print(materialized.geometry_text())
print()
print(materialized.wiring_text())
print()
print(materialized.collisions_text())
