"""Inspect the quarantine symbolic solver for `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/hub_kernel_solver.py")
"""

from __future__ import annotations

from signalflow.engine.debug import (
    DebugKernelHandle,
    DebugKernelMaterializedSolutionHandle,
    DebugKernelSolutionHandle,
    DebugKernelSolverHandle,
    DebugZoneHandle,
    solution_materialize,
)

zone: DebugZoneHandle = zones.zone_get(1, 1)
kernel: DebugKernelHandle | None = zone.kernel_get("intra")
if kernel is None:
    raise RuntimeError("Expected intra kernel for zone (1,1)")
board = kernel.board_get()
solver: DebugKernelSolverHandle = kernel.solver_get(board)
solution: DebugKernelSolutionHandle = solver.solution_get()
materialized: DebugKernelMaterializedSolutionHandle = solution_materialize(
    board,
    solution,
)

print(solver.summary_text())
print()
print("solution:")
print(solution.list_text())
print()
print("materialized:")
print(materialized.summary_text())
print()
print(materialized.geometry_text())
