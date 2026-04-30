"""Inspect geometry zones and wiring for a circuit with back edges.

Shows the per-zone geometry layout followed by the materialized wiring,
useful for diagnosing back-edge (recursive / ancestor-call) route rendering.

Usage from CLI:
    uv run python -m signalflow \
        examples/simple-circuit/rearch-external-backedge.yaml \
        --run-snippet snippets/algebraic/zone_backedge_wiring.py \
        -- --zone 1,1

Run from the REPL with:
    load("snippets/algebraic/zone_backedge_wiring.py")
"""

from __future__ import annotations

import argparse
import sys

import yaml

from signalflow.board import (
    Board,
    BoardKernel,
    BoardMaterializedSolution,
    BoardMaterializePolicy,
    BoardRelaxationSymmetry,
    BoardSolution,
    BoardSolver,
    BoardZone,
)
from signalflow.engine.inspect import SignalFlowContext
from signalflow.engine.inspect.zone_local import (
    contextResult_buildFromDocumentAndZone,
)
from signalflow.models import (
    CallingStack,
    Result,
    callingStackResult_buildFromCircuitDocument,
    result_isOkCheck,
)

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(
    description="Geometry zones + wiring for back-edge circuits."
)
parser.add_argument(
    "--zone",
    default="1,1",
    help="Zone coordinate as 'col,row' (default: 1,1)",
)
args: argparse.Namespace = parser.parse_known_args(sys.argv[1:])[0]

try:
    colStr, rowStr = args.zone.split(",")
    columnIndex: int = int(colStr)
    rowIndex: int = int(rowStr)
except ValueError:
    print(f"Error: invalid zone coordinate '{args.zone}'. Use 'col,row'.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load context
# ---------------------------------------------------------------------------

with open(source_yaml) as handle:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(handle)

contextResult: Result[SignalFlowContext] = (
    contextResult_buildFromDocumentAndZone(
        documentDict,
        columnIndex=columnIndex,
        rowIndex=rowIndex,
    )
)
if not result_isOkCheck(contextResult):
    print("Error: could not build context.")
    sys.exit(1)
ctx: SignalFlowContext = contextResult.value

callingStackResult: Result[CallingStack] = (
    callingStackResult_buildFromCircuitDocument(ctx.circuitDocument)
)
if not result_isOkCheck(callingStackResult):
    print("Error: could not build calling stack.")
    sys.exit(1)
callingStack: CallingStack = callingStackResult.value

zone: BoardZone = ctx.zones.zone_get(1, 1)  # type: ignore[name-defined]
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    print(f"Error: no intra kernel for zone ({columnIndex},{rowIndex}).")
    sys.exit(1)

board: Board = kernel.board_get()

# ---------------------------------------------------------------------------
# Materialized wiring
# ---------------------------------------------------------------------------

solver: BoardSolver = kernel.solver_get(board)
solution: BoardSolution = solver.solution_get()
materialized: BoardMaterializedSolution = solution.board_materialize(
    board,
    policy=BoardMaterializePolicy(
        relaxationSymmetry=BoardRelaxationSymmetry.MINIMAL
    ),
)

print(f"=== ZONE ({columnIndex},{rowIndex}) — MATERIALIZED GEOMETRY ===")
print()
print(materialized.geometry_sprint())
print()
print("=== CALLING STACK ===")
print()
print(callingStack.levels_sprint())
print()
print(f"=== ZONE ({columnIndex},{rowIndex}) — WIRING ===")
print()
print(materialized.wiring_sprint())
print()

# ---------------------------------------------------------------------------
# Geometry zone sprint
# ---------------------------------------------------------------------------

print(f"=== ZONE ({columnIndex},{rowIndex}) — GEOMETRY (RELAXED) ===")
print()
print(materialized.geometryRelaxed_sprint(legend_show=True))
print()
print(f"=== ZONE ({columnIndex},{rowIndex}) — RELAXED REGION FRAMES ===")
print()
relaxedFrames = materialized.relaxedRegionFrames_get()
initialFrames = board.geometry.regionFramesByName
for regionName in sorted(relaxedFrames):
    rf = relaxedFrames[regionName]
    init = initialFrames.get(regionName)
    relaxedRange = (
        f"row={rf.verticalStart}..{rf.verticalEnd_calculate() - 1}  "
        f"col={rf.horizontalStart}..{rf.horizontalEnd_calculate() - 1}"
    )
    if init and (init.verticalStart != rf.verticalStart):
        initRange = (
            f"row={init.verticalStart}..{init.verticalEnd_calculate() - 1}"
        )
        print(f"  {regionName}: {relaxedRange}  [shifted from {initRange}]")
    else:
        print(f"  {regionName}: {relaxedRange}")
