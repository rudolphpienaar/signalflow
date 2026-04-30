"""Zone geometry inspector.

Materializes and reports the geometry for one zone by coordinate.

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_geometry.py -- --zone 1,1

Run from the REPL with:
    load("snippets/algebraic/zone_geometry.py")
"""

from __future__ import annotations

import argparse
import sys

import yaml

from signalflow.board.board import Board
from signalflow.board.geometry import BoardGeometry, GeometryZone
from signalflow.board.kernel_runtime import BoardKernel
from signalflow.board.types import ChipTerminalPositions, WorldPoint
from signalflow.board.zone_runtime import BoardZone
from signalflow.engine.inspect import SignalFlowContext
from signalflow.engine.inspect.zone_local import (
    contextResult_buildFromDocumentAndZone,
)
from signalflow.models import RoutingZoneRegionFrame
from signalflow.models import result_isOkCheck as OK
from signalflow.models.result import Result

# 1. Parse snippet args (zone coordinate)
parser = argparse.ArgumentParser(description="Zone geometry inspector.")
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

with open(source_yaml) as f:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(f)
contextResult: Result[SignalFlowContext] = (
    contextResult_buildFromDocumentAndZone(
        documentDict,
        columnIndex=columnIndex,
        rowIndex=rowIndex,
    )
)
if not OK(contextResult):  # type: ignore[name-defined]  # noqa: F821
    sys.exit(1)
ctx: SignalFlowContext = contextResult.value  # type: ignore[union-attr]

# 3. Get zone geometry
zone: BoardZone = ctx.zones.zone_get(1, 1)  # type: ignore[name-defined]  # noqa: F821
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    print(f"Error: no intra kernel for zone ({columnIndex},{rowIndex}).")
    sys.exit(1)
board: Board = kernel.board_get()
geometry: BoardGeometry = board.geometry_get()

print(f"--- ZONE ({columnIndex},{rowIndex}) GEOMETRY ---")
print()
print(board.geometry_sprint())
print()
print("geometry zones:")
geometryZone: GeometryZone
for geometryZone in geometry.zones_get():
    print(f"  {geometryZone.summary_sprint()}")
print()
print("region frames:")
regionName: str
frame: RoutingZoneRegionFrame
for regionName, frame in sorted(geometry.regionFramesByName.items()):
    print(f"  {regionName}: {frame}")
print()
print("exact terminals:")
chipName: str
terminalPositions: ChipTerminalPositions
for chipName, terminalPositions in sorted(
    geometry.exactTerminalWorldPositionsByChip.items()
):
    print(f"  {chipName}:")
    terminalName: str
    worldPoint: WorldPoint
    for terminalName, worldPoint in sorted(terminalPositions.items()):
        print(f"    {terminalName}: {worldPoint}")
