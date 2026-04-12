"""Render one zone before and after a simple east chip-terminal bump.

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_geometry_bump.py \
        -- --zone 1,1 --delta-cols 5

Run from the REPL with:
    load("snippets/algebraic/zone_geometry_bump.py")
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import yaml

from signalflow.board import (
    Board,
    BoardKernel,
    BoardZone,
    GeometryZone,
    chipTerminalCouplingAppliedResult_build,
    chipTerminalCouplingFamilyResult_build,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, result_isOkCheck

parser = argparse.ArgumentParser(description="Zone geometry bump demo.")
parser.add_argument(
    "--zone",
    default="1,1",
    help="Zone coordinate as 'col,row'",
)
parser.add_argument(
    "--delta-cols",
    type=int,
    default=5,
    help="Horizontal bump applied to east/chip_terminal",
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

eastChipZone: GeometryZone | None = board.geometry_get().zone_get(
    "chip_terminal",
    "east",
)
if eastChipZone is None:
    print("Error: missing east/chip_terminal geometry zone.")
    sys.exit(1)

couplingFamilyResult = chipTerminalCouplingFamilyResult_build(
    board.geometry_get(),
    "east",
)
if not result_isOkCheck(couplingFamilyResult):
    print("Error: unable to build east chip-terminal coupling family.")
    sys.exit(1)

appliedResult = chipTerminalCouplingAppliedResult_build(
    board.geometry_get(),
    "east",
    deltaColumns=args.delta_cols,
)
if not result_isOkCheck(appliedResult):
    print("Error: unable to apply east chip-terminal coupling.")
    sys.exit(1)

shiftedGeometry = appliedResult.value.geometry
shiftedBoard = replace(board, geometry=shiftedGeometry)
shiftedEastChipZone = shiftedGeometry.zone_get("chip_terminal", "east")
assert shiftedEastChipZone is not None

print(f"--- ZONE ({columnIndex},{rowIndex}) BEFORE ---")
print()
print(board.geometry_sprint(legend_show=False))
print()
print(
    f"--- APPLY east/chip_terminal += {args.delta_cols} columns "
    f"on zone ({columnIndex},{rowIndex}) ---"
)
print()
print(couplingFamilyResult.value.text_sprint())
print()
print(f"before topLeft: {eastChipZone.topLeft_get()}")
print(f"after topLeft:  {shiftedEastChipZone.topLeft_get()}")
print()
print(f"--- ZONE ({columnIndex},{rowIndex}) AFTER ---")
print()
print(shiftedBoard.geometry_sprint(legend_show=False))
