"""Render one zone before and after a fixed east-extra-long displacement.

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_geometry_ee_displace.py \
        -- --zone 1,1 --delta-cols 5

Run from the REPL with:
    load("snippets/algebraic/zone_geometry_ee_displace.py")
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
    BoardZone,
    GeometryZone,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, RoutingZoneRegionFrame, result_isOkCheck


def _routingZoneRegionFrameShifted_build(
    frame: RoutingZoneRegionFrame,
    *,
    deltaColumns: int,
) -> RoutingZoneRegionFrame:
    """Build a routing-zone region frame shifted horizontally."""

    return RoutingZoneRegionFrame(
        horizontalStart=frame.horizontalStart + deltaColumns,
        verticalStart=frame.verticalStart,
        horizontalSpan=frame.horizontalSpan,
        verticalSpan=frame.verticalSpan,
    )


parser = argparse.ArgumentParser(
    description="East extra-long displacement demo."
)
parser.add_argument(
    "--zone",
    default="1,1",
    help="Zone coordinate as 'col,row'",
)
parser.add_argument(
    "--delta-cols",
    type=int,
    default=5,
    help="Horizontal displacement applied to east/extra_routing_longitude",
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

eastExtraFan: GeometryZone | None = board.geometry_get().zone_get(
    "extra_routing_fan_in_out",
    "east",
)
eastExtraLong: GeometryZone | None = board.geometry_get().zone_get(
    "extra_routing_longitude",
    "east",
)
if eastExtraFan is None or eastExtraLong is None:
    print("Error: missing east extra geometry zones.")
    sys.exit(1)

shiftedGeometryZonesById = dict(board.geometry_get().geometryZonesById)
shiftedGeometryZonesById[eastExtraLong.regionId] = GeometryZone(
    regionId=eastExtraLong.regionId,
    frame=_routingZoneRegionFrameShifted_build(
        eastExtraLong.frame,
        deltaColumns=args.delta_cols,
    ),
    routingZoneRegionId=eastExtraLong.routingZoneRegionId,
    chipDrawPlacementsByChip=eastExtraLong.chipDrawPlacementsByChip,
    exactTerminalWorldPositionsByChip=(
        eastExtraLong.exactTerminalWorldPositionsByChip
    ),
)
shiftedGeometry = BoardGeometry(
    geometryZonesById=shiftedGeometryZonesById,
    effectiveBoundaryFramesByName=(
        board.geometry_get().effectiveBoundaryFramesByName
    ),
)
shiftedBoard = replace(board, geometry=shiftedGeometry)
shiftedExtraLong = shiftedGeometry.zone_get("extra_routing_longitude", "east")
assert shiftedExtraLong is not None

beforeGap = (
    eastExtraLong.frame.horizontalStart
    - eastExtraFan.frame.horizontalEnd_calculate()
)
afterGap = (
    shiftedExtraLong.frame.horizontalStart
    - eastExtraFan.frame.horizontalEnd_calculate()
)

print(f"--- ZONE ({columnIndex},{rowIndex}) BEFORE ---")
print()
print(board.geometry_sprint(legend_show=False))
print()
print(
    f"--- APPLY Ee += {args.delta_cols} columns "
    f"on zone ({columnIndex},{rowIndex}) ---"
)
print()
print(f"before gap(Efe,Ee): {beforeGap}")
print(f"after gap(Efe,Ee):  {afterGap}")
print()
print(f"--- ZONE ({columnIndex},{rowIndex}) AFTER ---")
print()
print(shiftedBoard.geometry_sprint(legend_show=False))
