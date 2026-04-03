"""Inspect the quarantine symbolic solver for `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/hub_kernel_solver.py")
"""

from __future__ import annotations

from signalflow.board import (
    Board,
    BoardChipPlacementPolicy,
    BoardKernel,
    BoardMaterializePolicy,
    BoardMaterializedSolution,
    BoardRelaxationSymmetry,
    BoardSolution,
    BoardSolver,
    BoardZone,
)
zone: BoardZone = zones.zone_get(1, 1)
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    raise RuntimeError("Expected intra kernel for zone (1,1)")
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

print(solver.summary_sprint())
print()
print("solution:")
print(solution.list_sprint())
print()
print("materialized:")
print(materialized.summary_sprint())
print()
print(materialized.geometry_sprint())
