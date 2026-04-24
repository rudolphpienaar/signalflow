"""World geometry assembly inspector.

Loads all zones from a multi-zone circuit, builds a WorldGeometryState,
runs WorldGeometryResolver.propagate_run, and reports per-seam budgets and
per-zone before/after geometry.

Usage from CLI:
    uv run python -m signalflow examples/simple-circuit/back-and-forth.yaml \
        --run-snippet snippets/algebraic/world_geometry_assembly.py

Run from the REPL with:
    load("snippets/algebraic/world_geometry_assembly.py")
"""

from __future__ import annotations

import sys

import yaml

from signalflow.board import (
    Board,
    BoardGeometry,
    BoardKernel,
    BoardZone,
    SeamBudgets,
    WorldGeometryResolver,
    WorldGeometryState,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, result_isOkCheck
from signalflow.models.routing_zone import GridCoord, RoutingZoneRegionFrame

# ---------------------------------------------------------------------------
# 1. Load document and build context
# ---------------------------------------------------------------------------

with open(source_yaml) as handle:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(handle)

contextResult: Result[SignalFlowContext] = context_buildFromDocument(
    documentDict
)
if not result_isOkCheck(contextResult):
    print("Error: failed to build SignalFlowContext.")
    sys.exit(1)
ctx: SignalFlowContext = contextResult.value

# ---------------------------------------------------------------------------
# 2. Collect per-zone boards
#
# Each zone in the world grid is keyed by its GridCoord.  A zone without an
# intra kernel (e.g. a degenerate zone) is silently skipped.
# ---------------------------------------------------------------------------

boardsByCoord: dict[GridCoord, Board] = {}
zoneHandle: BoardZone
for zoneHandle in ctx.zones._routingZonesAll_get():  # type: ignore[attr-defined]
    zoneId = zoneHandle.routingZoneId
    coordResult = zoneId.worldGridCoordResult_get()
    if not result_isOkCheck(coordResult):
        continue
    coord: GridCoord = coordResult.value
    kernel: BoardKernel | None = zoneHandle.kernel_get("intra")
    if kernel is None:
        continue
    boardsByCoord[coord] = kernel.board_get()

if not boardsByCoord:
    print("Error: no zones with intra kernels found.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Build WorldGeometryState and run propagate_run
# ---------------------------------------------------------------------------

anchorCoord: GridCoord = min(
    boardsByCoord, key=lambda c: (c.columnIndex, c.rowIndex)
)
geometryByCoord: dict[GridCoord, BoardGeometry] = {
    coord: board.geometry_get()
    for coord, board in boardsByCoord.items()
}
worldBefore: WorldGeometryState = WorldGeometryState(
    zoneGeometryByCoord=geometryByCoord,
    anchorCoord=anchorCoord,
)

budgets: SeamBudgets = WorldGeometryResolver.budgets_collect(worldBefore)
worldAfter: WorldGeometryState = WorldGeometryResolver.displacements_apply(
    worldBefore, budgets
)

# ---------------------------------------------------------------------------
# 4. Report
# ---------------------------------------------------------------------------

sortedCoords: list[GridCoord] = sorted(
    boardsByCoord, key=lambda c: (c.columnIndex, c.rowIndex)
)

print(f"--- WORLD GEOMETRY ASSEMBLY: {source_yaml} ---")  # type: ignore[name-defined]  # noqa: F821
print()
print(f"zones:   {len(sortedCoords)}")
print(f"anchor:  ({anchorCoord.columnIndex},{anchorCoord.rowIndex})")
print()

# --- seam budgets ---
print("--- SEAM BUDGETS ---")
print()
coord: GridCoord
for coord in sortedCoords:
    eastCoord: GridCoord | None = worldBefore.eastNeighbor_get(coord)
    if eastCoord is not None:
        hBudget: int = budgets.horizontal.get((coord, eastCoord), 0)
        print(
            f"  ({coord.columnIndex},{coord.rowIndex})"
            f"→({eastCoord.columnIndex},{eastCoord.rowIndex})"
            f"  H = {hBudget}"
        )
    southCoord: GridCoord | None = worldBefore.southNeighbor_get(coord)
    if southCoord is not None:
        vBudget: int = budgets.vertical.get((coord, southCoord), 0)
        print(
            f"  ({coord.columnIndex},{coord.rowIndex})"
            f"→({southCoord.columnIndex},{southCoord.rowIndex})"
            f"  V = {vBudget}"
        )

print()

# --- world displacements ---
print("--- WORLD DISPLACEMENTS ---")
print()
for coord in sortedCoords:
    geoBefore: BoardGeometry | None = worldBefore.zone_get(coord)
    geoAfter: BoardGeometry | None = worldAfter.zone_get(coord)
    if geoBefore is None or geoAfter is None:
        continue
    # Infer displacement from anchor shift of any named region frame.
    # Use the first region frame available in both snapshots.
    framesBefore: dict[str, RoutingZoneRegionFrame] = geoBefore.regionFramesByName
    framesAfter: dict[str, RoutingZoneRegionFrame] = geoAfter.regionFramesByName
    firstKey: str | None = next(iter(framesBefore), None)
    dx: int = 0
    dy: int = 0
    if firstKey is not None and firstKey in framesAfter:
        frameBefore: RoutingZoneRegionFrame = geoBefore.regionFramesByName[firstKey]
        frameAfter: RoutingZoneRegionFrame = geoAfter.regionFramesByName[firstKey]
        dx = frameAfter.horizontalStart - frameBefore.horizontalStart
        dy = frameAfter.verticalStart - frameBefore.verticalStart
    anchor_tag: str = "  (anchor)" if coord == anchorCoord else ""
    print(
        f"  ({coord.columnIndex},{coord.rowIndex})"
        f"  Δx={dx:+d}  Δy={dy:+d}{anchor_tag}"
    )

print()

# --- per-zone before/after geometry ---
for coord in sortedCoords:
    board: Board = boardsByCoord[coord]
    geomAfter: BoardGeometry | None = worldAfter.zone_get(coord)
    if geomAfter is None:
        continue
    from dataclasses import replace as dc_replace
    assembledBoard: Board = dc_replace(board, geometry=geomAfter)

    print(
        f"--- ZONE ({coord.columnIndex},{coord.rowIndex}) BEFORE ---"
    )
    print()
    print(board.geometry_sprint(legend_show=False))
    print()
    print(
        f"--- ZONE ({coord.columnIndex},{coord.rowIndex}) AFTER  ---"
    )
    print()
    print(assembledBoard.geometry_sprint(legend_show=False))
    print()
