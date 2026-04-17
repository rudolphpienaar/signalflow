"""Show zone geometry before and after a geo-rule displacement.

Demonstrates ``geometry_change`` from the explicit geo-zone displacement
rule bank for any supported anchor.  The RULES bank drives all cascaded
effects automatically (floor guards, face stretches, bulk collects).

Sign convention for ``--delta``:
    Positive = outward for free-direction anchors (Ee, Se, Et).
    Negative = outward for floor-guard anchors (We, Ne, Wt).

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_georules_displace.py \
        -- --zone 1,1 --anchor Ee --delta 5

    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_georules_displace.py \
        -- --zone 1,1 --anchor We --delta -3 --wiring

Run from the REPL with:
    load("snippets/algebraic/zone_georules_displace.py")
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import yaml

from signalflow.board import (
    Board,
    BoardGeometry,
    BoardKernel,
    BoardMaterializePolicy,
    BoardMaterializedSolution,
    BoardRelaxationSymmetry,
    BoardSolution,
    BoardSolver,
    BoardZone,
)
from signalflow.board.geometry.georules import (
    GeoArgScalar,
    GeoChange,
    GeoOp,
    RULES,
    geometry_change,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, result_isOkCheck
from signalflow.notation.sfn import sfN

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

_SUPPORTED: list[str] = sorted(anchor.name for anchor in RULES)

parser = argparse.ArgumentParser(
    description="Geo-rule displacement demo — any supported anchor."
)
parser.add_argument(
    "--zone",
    default="1,1",
    help="Zone coordinate as 'col,row' (default: 1,1)",
)
parser.add_argument(
    "--anchor",
    default="Ee",
    choices=_SUPPORTED,
    help=f"sfN anchor to displace (default: Ee). Supported: {_SUPPORTED}",
)
parser.add_argument(
    "--delta",
    type=int,
    default=5,
    help=(
        "Signed displacement delta (default: 5). "
        "Use negative values for floor-guard anchors: We, Ne, Wt."
    ),
)
parser.add_argument(
    "--wiring",
    action="store_true",
    help="Also solve and render the wiring on the displaced geometry.",
)
args: argparse.Namespace = parser.parse_known_args(sys.argv[1:])[0]
delta: int = args.delta
anchor: sfN = sfN[args.anchor]
showWiring: bool = args.wiring

try:
    _col, _row = args.zone.split(",")
    zoneCol: int = int(_col)
    zoneRow: int = int(_row)
except ValueError:
    print(f"Error: invalid zone '{args.zone}'. Use 'col,row'.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load context — source_yaml injected by the SignalFlow REPL or CLI runner
# ---------------------------------------------------------------------------

with open(source_yaml) as handle:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(handle)

contextResult: Result[SignalFlowContext] = context_buildFromDocument(
    documentDict
)
if not result_isOkCheck(contextResult):
    print("Error: could not build context.")
    sys.exit(1)
ctx: SignalFlowContext = contextResult.value

zone: BoardZone = ctx.zones.zone_get(  # type: ignore[name-defined]
    zoneCol, zoneRow
)
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    print(f"Error: no intra kernel for zone ({zoneCol},{zoneRow}).")
    sys.exit(1)

board: Board = kernel.board_get()
beforeGeo: BoardGeometry = board.geometry_get()

# ---------------------------------------------------------------------------
# Apply displacement via the rule bank
# ---------------------------------------------------------------------------

changes: list[GeoChange] = [
    (anchor, GeoArgScalar(delta), GeoOp.DISPLACE),
]
afterResult: Result[BoardGeometry] = geometry_change(changes, beforeGeo)
if not result_isOkCheck(afterResult):
    print(f"geometry_change failed: {afterResult.reason}")
    sys.exit(1)
afterGeo: BoardGeometry = afterResult.value

# ---------------------------------------------------------------------------
# Render geometry
# ---------------------------------------------------------------------------

print(f"=== ZONE ({zoneCol},{zoneRow}) — BEFORE  ({anchor.name} += {delta}) ===")
print()
print(beforeGeo.geometry_sprint(legend_show=False))
print()
print(f"=== ZONE ({zoneCol},{zoneRow}) — AFTER   ({anchor.name} += {delta}) ===")
print()
print(afterGeo.geometry_sprint(legend_show=False))

# ---------------------------------------------------------------------------
# Optional wiring sprint on displaced geometry
# ---------------------------------------------------------------------------

if showWiring:
    afterBoard: Board = replace(board, geometry=afterGeo)
    solver: BoardSolver = kernel.solver_get(afterBoard)
    solution: BoardSolution = solver.solution_get()
    materialized: BoardMaterializedSolution = solution.board_materialize(
        afterBoard,
        policy=BoardMaterializePolicy(
            relaxationSymmetry=BoardRelaxationSymmetry.MINIMAL
        ),
    )
    print()
    print(
        f"=== ZONE ({zoneCol},{zoneRow}) — WIRING  ({anchor.name} += {delta}) ==="
    )
    print()
    print(materialized.geometry_sprint())
    print()
    print(materialized.wiring_sprint())
