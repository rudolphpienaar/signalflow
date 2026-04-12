"""Inspect east-neighbor chip-column overlap for one zone.

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_chip_overlap.py -- --zone 1,1

Run from the REPL with:
    load("snippets/algebraic/zone_chip_overlap.py")
"""

from __future__ import annotations

import argparse
import sys

import yaml

from signalflow.board import (
    Board,
    BoardChipDrawPlacement,
    BoardZone,
    ChipColumnOverlapApplied,
    ChipColumnOverlapResolution,
    GeometryZone,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, result_isOkCheck


def _geometryZone_print(
    label: str,
    geometryZone: GeometryZone | None,
) -> None:
    """Print one geometry zone and its owned chips.

    Args:
        label: Human-readable label for this section.
        geometryZone: Geometry zone to print.
    """

    print(label)
    if geometryZone is None:
        print("  <missing>")
        return
    print(f"  summary: {geometryZone.summary_sprint()}")
    print(f"  topLeft: {geometryZone.topLeft_get()}")
    print(f"  extent:  {geometryZone.extent_get()}")
    chips: tuple[BoardChipDrawPlacement, ...] = geometryZone.chips_get()
    if not chips:
        print("  chips:   <none>")
        return
    print("  chips:")
    chipPlacement: BoardChipDrawPlacement
    for chipPlacement in chips:
        print(
            "    "
            f"{chipPlacement.chipName}: "
            f"{chipPlacement.worldFrame_get()}"
        )


def _boardGeometryArea_print(
    label: str,
    board: Board,
    *,
    columnOffset: int,
) -> None:
    """Print rendered board geometry text for one local area.

    Args:
        label: Human-readable label for this section.
        board: Board whose geometry should be rendered.
        columnOffset: World-column offset used to crop the rendered output.
    """

    print(label)
    print(board.geometry_sprint(columnOffset=columnOffset))


parser = argparse.ArgumentParser(description="Zone chip overlap inspector.")


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
overlap: ChipColumnOverlapResolution | None = zone.chipOverlap_get("east")
applied: ChipColumnOverlapApplied | None = zone.chipOverlapApplied_get("east")
neighborZone: BoardZone = ctx.zones.zone_get(columnIndex + 1, rowIndex)

anchorKernel = zone.kernel_get("intra")
neighborKernel = neighborZone.kernel_get("intra")
if anchorKernel is None or neighborKernel is None:
    print(
        "Error: missing intra kernel for overlap pair "
        f"({columnIndex},{rowIndex}) and ({columnIndex + 1},{rowIndex})."
    )
    sys.exit(1)
anchorBoard: Board = anchorKernel.board_get()
neighborBoard: Board = neighborKernel.board_get()

anchorEastTerminalZoneBefore = anchorBoard.geometry_get().zone_get(
    "chip_terminal",
    "east",
)
neighborWestTerminalZoneBefore = neighborBoard.geometry_get().zone_get(
    "chip_terminal",
    "west",
)
if (
    anchorEastTerminalZoneBefore is None
    or neighborWestTerminalZoneBefore is None
):
    print("Error: missing chip-terminal geometry zones for overlap pair.")
    sys.exit(1)

beforeColumnOffset = min(
    anchorEastTerminalZoneBefore.topLeft_get()[0],
    neighborWestTerminalZoneBefore.topLeft_get()[0],
) - 6

print(f"--- CHIP OVERLAP ANCHOR ({columnIndex},{rowIndex}) -> EAST ---")
print()
if overlap is None:
    print("<no east-neighbor chip overlap>")
    sys.exit(0)

print(
    "This snippet treats the requested zone as the west/anchor zone in the "
    "overlap pair."
)
print(
    f"anchor zone:   ({columnIndex},{rowIndex}) "
    "[its east/chip_terminal]"
)
print(
    f"neighbor zone: ({columnIndex + 1},{rowIndex}) "
    "[its west/chip_terminal]"
)
print()

print("--- BEFORE ---")
_geometryZone_print(
    f"anchor ({columnIndex},{rowIndex}) east/chip_terminal:",
    anchorEastTerminalZoneBefore,
)
print()
_geometryZone_print(
    f"neighbor ({columnIndex + 1},{rowIndex}) west/chip_terminal:",
    neighborWestTerminalZoneBefore,
)
print()
_boardGeometryArea_print(
    f"anchor ({columnIndex},{rowIndex}) rendered geometry:",
    anchorBoard,
    columnOffset=beforeColumnOffset,
)
print()
_boardGeometryArea_print(
    f"neighbor ({columnIndex + 1},{rowIndex}) rendered geometry:",
    neighborBoard,
    columnOffset=beforeColumnOffset,
)

print()
print("--- RESOLUTION ---")
print(f"dominantSide: {overlap.dominantSide.value}")
print(f"westTopLeft:  {overlap.westTopLeft}")
print(f"eastTopLeft:  {overlap.eastTopLeft}")
print(f"targetTopLeft:{overlap.targetColumnFrame.topLeft}")
print(f"westSize:     {overlap.westSize}")
print(f"eastSize:     {overlap.eastSize}")
print(
    "westShift:    "
    f"({overlap.westDeltaColumns}, {overlap.westDeltaRows})"
)
print(
    "eastShift:    "
    f"({overlap.eastDeltaColumns}, {overlap.eastDeltaRows})"
)
print()
print("west chip targets:")
for chipName, chipFrame in sorted(overlap.westChipTargetFramesByName.items()):
    print(f"  {chipName}: {chipFrame}")
print()
print("east chip targets:")
for chipName, chipFrame in sorted(overlap.eastChipTargetFramesByName.items()):
    print(f"  {chipName}: {chipFrame}")

print()
print("--- APPLIED ---")
if applied is None:
    print("<no applied overlap>")
    sys.exit(0)

plan = applied.mutationPlan
print(f"recessiveSide: {plan.recessiveSide.value}")
print(f"recessiveDelta: ({plan.deltaColumns}, {plan.deltaRows})")
print(f"targetRegionFrame: {plan.targetRegionFrame}")
print()

anchorEastTerminalZoneAfter = applied.westBoard.geometry_get().zone_get(
    "chip_terminal",
    "east",
)
neighborWestTerminalZoneAfter = applied.eastBoard.geometry_get().zone_get(
    "chip_terminal",
    "west",
)
if (
    anchorEastTerminalZoneAfter is None
    or neighborWestTerminalZoneAfter is None
):
    print("Error: missing chip-terminal geometry zones after apply.")
    sys.exit(1)
afterColumnOffset = min(
    anchorEastTerminalZoneAfter.topLeft_get()[0],
    neighborWestTerminalZoneAfter.topLeft_get()[0],
) - 6

print("--- AFTER ---")
_geometryZone_print(
    f"anchor ({columnIndex},{rowIndex}) east/chip_terminal:",
    anchorEastTerminalZoneAfter,
)
print()
_geometryZone_print(
    f"neighbor ({columnIndex + 1},{rowIndex}) west/chip_terminal:",
    neighborWestTerminalZoneAfter,
)
print()
_boardGeometryArea_print(
    f"anchor ({columnIndex},{rowIndex}) rendered geometry:",
    applied.westBoard,
    columnOffset=afterColumnOffset,
)
print()
_boardGeometryArea_print(
    f"neighbor ({columnIndex + 1},{rowIndex}) rendered geometry:",
    applied.eastBoard,
    columnOffset=afterColumnOffset,
)
