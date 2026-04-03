"""Compare quarantine symbolic solver policies for `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/hub_policy_compare.py")
"""

from __future__ import annotations

from signalflow.board import Board, BoardKernel, BoardSolver, BoardZone
from signalflow.models import RoutingZoneChannelSense

zone: BoardZone = zones.zone_get(1, 1)
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    raise RuntimeError("Expected intra kernel for zone (1,1)")
board: Board = kernel.board_get()
solver: BoardSolver = kernel.solver_get(board)
anticlockwiseSolver: BoardSolver = solver.policy_set(
    rotationSense=RoutingZoneChannelSense.ANTICLOCKWISE
)

print("clockwise:")
print(solver.algebraic_sprint("App.ts.main().s1"))
print()
print("anticlockwise:")
print(anticlockwiseSolver.algebraic_sprint("App.ts.main().s1"))
