"""Inspect the quarantine symbolic solver for one hub zone.

Usage from CLI:
    signalflow --engine new --run-snippet \
        snippets/algebraic/hub_kernel_solver.py examples/hub.yaml \
        -- --zone 1,1

Run from the REPL with:
    load("snippets/algebraic/hub_kernel_solver.py")
"""

from __future__ import annotations

import argparse
import sys

from signalflow.board import (
    Board,
    BoardChipPlacementPolicy,
    BoardKernel,
    BoardMaterializedSolution,
    BoardMaterializePolicy,
    BoardRelaxationSymmetry,
    BoardSolution,
    BoardSolver,
    BoardZone,
)

parser = argparse.ArgumentParser(
    description="Inspect the symbolic solver for one zone."
)
parser.add_argument(
    "--zone",
    default="1,1",
    help="Zone coordinate as 'col,row'",
)
args: argparse.Namespace = parser.parse_known_args(sys.argv[1:])[0]

try:
    colStr, rowStr = args.zone.split(",")
    columnIndex: int = int(colStr)
    rowIndex: int = int(rowStr)
except ValueError:
    print(f"Error: invalid zone coordinate '{args.zone}'. Use 'col,row'.")
    sys.exit(1)

zone: BoardZone = zones.zone_get(  # noqa: F821 -- injected by snippet runner
    columnIndex, rowIndex
)
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    raise RuntimeError(
        f"Expected intra kernel for zone ({columnIndex},{rowIndex})"
    )
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

print(f"--- ZONE ({columnIndex},{rowIndex}) SOLVER ---")
print()
print(solver.summary_sprint())
print()
print("solution:")
print(solution.list_sprint())
print()
print("materialized:")
print(materialized.summary_sprint())
print()
print(materialized.geometry_sprint())
