"""Show zone geometry before and after ``Ee += delta`` via georules.

Demonstrates ``geometry_change`` from the explicit geo-zone displacement
rule bank.  Compare with ``zone_geometry_ee_displace.py`` which performs
the same shift by direct zone surgery — this version cascades to Ne and
Se east-face stretches automatically via RULES.

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_georules_ee_displace.py \
        -- --zone 1,1 --delta 5

Run from the REPL with:
    load("snippets/algebraic/zone_georules_ee_displace.py")
"""

from __future__ import annotations

import argparse
import sys

import yaml

from signalflow.board import (
    Board,
    BoardGeometry,
    BoardKernel,
    BoardZone,
)
from signalflow.board.geometry.georules import (
    GeoArgScalar,
    GeoChange,
    GeoOp,
    geometry_change,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, result_isOkCheck
from signalflow.notation.sfn import sfN

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(
    description="Ee displacement via georules demo."
)
parser.add_argument(
    "--zone",
    default="1,1",
    help="Zone coordinate as 'col,row' (default: 1,1)",
)
parser.add_argument(
    "--delta",
    type=int,
    default=5,
    help="Horizontal delta applied to Ee (default: 5)",
)
args: argparse.Namespace = parser.parse_known_args(sys.argv[1:])[0]
delta: int = args.delta

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
    print(
        f"Error: no intra kernel for zone ({zoneCol},{zoneRow})."
    )
    sys.exit(1)

board: Board = kernel.board_get()
beforeGeo: BoardGeometry = board.geometry_get()

# ---------------------------------------------------------------------------
# Apply  Ee += delta  via the rule bank
# ---------------------------------------------------------------------------

changes: list[GeoChange] = [
    (sfN.Ee, GeoArgScalar(delta), GeoOp.DISPLACE),
]
afterResult: Result[BoardGeometry] = geometry_change(changes, beforeGeo)
if not result_isOkCheck(afterResult):
    print(f"geometry_change failed: {afterResult.reason}")
    sys.exit(1)
afterGeo: BoardGeometry = afterResult.value

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

print(
    f"=== ZONE ({zoneCol},{zoneRow}) — BEFORE  (Ee += {delta}) ==="
)
print()
print(beforeGeo.geometry_sprint(legend_show=False))
print()
print(
    f"=== ZONE ({zoneCol},{zoneRow}) — AFTER   (Ee += {delta}) ==="
)
print()
print(afterGeo.geometry_sprint(legend_show=False))
