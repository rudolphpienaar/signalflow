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

from signalflow.board.board import Board
from signalflow.board.geometry import BoardGeometry
from signalflow.board.kernel_runtime import BoardKernel
from signalflow.board.types import ChipTerminalPositions, WorldPoint
from signalflow.board.zone_runtime import BoardZone
from signalflow.models import RoutingZoneRegionFrame, result_isOkCheck as OK

# 1. Parse snippet args (zone coordinate)
parser = argparse.ArgumentParser(description="Zone geometry inspector.")
parser.add_argument("--zone", default="1,1", help="Zone coordinate as 'col,row'")
args: argparse.Namespace = parser.parse_known_args(sys.argv[1:])[0]

try:
    colStr, rowStr = args.zone.split(",")
    columnIndex: int = int(colStr)
    rowIndex: int = int(rowStr)
except ValueError:
    print(f"Error: invalid zone coordinate '{args.zone}'. Use 'col,row'.")
    sys.exit(1)

# 2. source_yaml and ctx are injected by the SignalFlow snippet runner.
#    source_yaml is the path to the YAML file passed on the CLI.
#    ctx is the fully materialized SignalFlowContext for that document.
#    Equivalent live code:
import yaml
from signalflow.engine import context_buildFromDocument
from signalflow.engine.debug import SignalFlowContext
from signalflow.models import Result

with open(source_yaml) as f:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(f)
contextResult: Result[SignalFlowContext] = context_buildFromDocument(documentDict)
if not OK(contextResult):  # type: ignore[name-defined]  # noqa: F821
    sys.exit(1)
ctx: SignalFlowContext = contextResult.value  # type: ignore[union-attr]

# 3. Get zone geometry
zone: BoardZone = ctx.zones.zone_get(columnIndex, rowIndex)  # type: ignore[name-defined]  # noqa: F821
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
