"""Compare quarantine symbolic solver policies for `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/hub_policy_compare.py")
"""

from __future__ import annotations

from signalflow.engine.debug import (
    DebugKernelHandle,
    DebugKernelSolverHandle,
    DebugZoneHandle,
)
from signalflow.models import RoutingZoneChannelSense

zone: DebugZoneHandle = zones.zone_get(1, 1)
kernel: DebugKernelHandle | None = zone.kernel_get("intra")
if kernel is None:
    raise RuntimeError("Expected intra kernel for zone (1,1)")
board = kernel.board_get()
solver: DebugKernelSolverHandle = kernel.solver_get(board)
anticlockwiseSolver: DebugKernelSolverHandle = solver.policy_set(
    rotationSense=RoutingZoneChannelSense.ANTICLOCKWISE
)

print("clockwise:")
print(solver.algebraic_text("App.ts.main().s1"))
print()
print("anticlockwise:")
print(anticlockwiseSolver.algebraic_text("App.ts.main().s1"))
