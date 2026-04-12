"""Geometry-zone inspector for one zone by coordinate.

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_geometry_zones.py -- --zone 1,1

Run from the REPL with:
    load("snippets/algebraic/zone_geometry_zones.py")
"""

from __future__ import annotations

import argparse
import sys

import yaml

from signalflow.board import (
    Board,
    BoardChipDrawPlacement,
    BoardKernel,
    BoardZone,
    GeometryZone,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, result_isOkCheck

parser = argparse.ArgumentParser(description="Geometry-zone inspector.")
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

with open(source_yaml) as handle:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(handle)
contextResult: Result[SignalFlowContext] = context_buildFromDocument(
    documentDict
)
if not result_isOkCheck(contextResult):
    sys.exit(1)
ctx: SignalFlowContext = contextResult.value

zone: BoardZone = ctx.zones.zone_get(  # type: ignore[name-defined]  # noqa: F821
    columnIndex,
    rowIndex,
)
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    print(f"Error: no intra kernel for zone ({columnIndex},{rowIndex}).")
    sys.exit(1)
board: Board = kernel.board_get()

print(f"--- ZONE ({columnIndex},{rowIndex}) GEOMETRY ZONES ---")
print()
geometryZone: GeometryZone
for geometryZone in board.geometry_get().zones_get():
    print(f"  {geometryZone.summary_sprint()}")
    chips: tuple[BoardChipDrawPlacement, ...] = geometryZone.chips_get()
    if chips:
        print("    chips:")
        chipPlacement: BoardChipDrawPlacement
        for chipPlacement in chips:
            print(
                "      "
                f"{chipPlacement.chipName}: "
                f"{chipPlacement.worldFrame_get()}"
            )
