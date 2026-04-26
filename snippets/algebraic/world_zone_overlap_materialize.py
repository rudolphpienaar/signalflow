"""World zone overlap materializer — Phase 2 of world geometry assembly.

Harmonizes zone geometries (same algorithm as world_zone_harmonize.py), then
for each adjacent zone pair (Za, Zb) processes the seam chip override:

  1. Shared chips: Za's Et zone chip names (= Zb's Wt zone by calling-stack
     definition — no inference needed)
  2. Za's Et chipDrawPlacementsByChip + exactTerminalWorldPositionsByChip
     for shared chips overwrite the corresponding entries in Zb's Wt zone
     (Za is the dominant zone)
  3. Zb re-materialized: solution.board_materialize(board=adjusted_board)
  4. On boundary violations: Zb re-solved on adjusted_board, then
     re-materialized

Seam processing is strictly sequential — seam i fully resolved before i+1,
so that Zb's corrected east terminal feeds the next seam's Za correctly.

Usage:
    uv run python -m signalflow examples/simple-circuit/back-and-forth.yaml \\
        --run-snippet snippets/algebraic/world_zone_overlap_materialize.py
"""

from __future__ import annotations

import sys
from dataclasses import replace

import yaml

from signalflow.board import BoardGeometry, BoardKernel, BoardZone
from signalflow.board.board import Board
from signalflow.board.geometry.georules import (
    GeoArgScalar,
    GeoChange,
    GeoOp,
    geometry_change,
)
from signalflow.board.geometry.mutation import boardRegionIdResult_fromSfN
from signalflow.board.geometry.zones import GeometryZone
from signalflow.board.materialized_runtime import BoardMaterializedSolution
from signalflow.board.render import boardCanvas_render
from signalflow.board.solver_runtime import BoardSolution, BoardSolver
from signalflow.board.types import BoardRegionId
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.engine.inspect import SignalFlowContext
from signalflow.engine.inspect.zone_local import contextResult_buildFromDocumentAndZone
from signalflow.models import CircuitDocument, Result
from signalflow.models import result_isOkCheck as OK
from signalflow.models.calling_stack import (
    CallingStack,
    callingStackResult_buildFromCircuitDocument,
)
from signalflow.notation.sfn import sfN

# ---------------------------------------------------------------------------
# 1. Load document
# ---------------------------------------------------------------------------

_yaml_path: str = source_yaml  # type: ignore[name-defined]  # noqa: F821
with open(_yaml_path) as handle:
    documentDict: dict[str, object] = yaml.safe_load(handle)

# ---------------------------------------------------------------------------
# 2. Calling depth → harmonization pair count
# ---------------------------------------------------------------------------

cdResult: Result[CircuitDocument] = (
    circuitDocumentResult_buildFromDocumentDict(documentDict)
)
if not OK(cdResult):
    print("Error: failed to build CircuitDocument.")
    sys.exit(1)
circuitDocument: CircuitDocument = cdResult.value

csResult: Result[CallingStack] = callingStackResult_buildFromCircuitDocument(
    circuitDocument
)
if not OK(csResult):
    print("Error: failed to build CallingStack.")
    sys.exit(1)
callingStack: CallingStack = csResult.value

bandCount: int = callingStack.bandCount_calculate()
numPairs: int = max(0, bandCount - 1)

# ---------------------------------------------------------------------------
# 3. Span helper
# ---------------------------------------------------------------------------


def _span_get(geometry: BoardGeometry, anchor: sfN, horizontal: bool) -> int:
    ridResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(anchor)
    if OK(ridResult):
        rid: BoardRegionId = ridResult.value
        zoneGeo: GeometryZone | None = geometry.geometryZonesById.get(rid)
        if zoneGeo is not None:
            return (
                zoneGeo.frame.horizontalSpan
                if horizontal
                else zoneGeo.frame.verticalSpan
            )
    return 0


# ---------------------------------------------------------------------------
# 4. Build per-zone geometries and solver artifacts
# ---------------------------------------------------------------------------

geoByIdx: dict[int, BoardGeometry] = {}
boardByIdx: dict[int, Board] = {}
solverByIdx: dict[int, BoardSolver] = {}

overlapIdx: int
for overlapIdx in range(1, numPairs + 1):
    zoneCtxResult: Result[SignalFlowContext] = (
        contextResult_buildFromDocumentAndZone(
            documentDict,
            columnIndex=overlapIdx,
            rowIndex=1,
        )
    )
    if not OK(zoneCtxResult):
        continue
    zoneCtx: SignalFlowContext = zoneCtxResult.value
    bz: BoardZone = zoneCtx.zones.zone_get(1, 1)
    k: BoardKernel | None = bz.kernel_get("intra")
    if k is None:
        continue
    b: Board = k.board_get()
    geoByIdx[overlapIdx] = b.geometry_get()
    boardByIdx[overlapIdx] = b
    solverByIdx[overlapIdx] = k.solver_get()

activeIdxs: list[int] = sorted(geoByIdx)

# ---------------------------------------------------------------------------
# 5. Phase 1 — harmonize geometry (same algorithm as world_zone_harmonize.py)
# ---------------------------------------------------------------------------

print(f"--- WORLD ZONE OVERLAP MATERIALIZE: {_yaml_path} ---")
print()
print(f"bands: {bandCount}  pairs: {numPairs}  active zones: {activeIdxs}")
print()
print("--- PHASE 1: GEOMETRY HARMONIZATION ---")
print()

i: int
for i in range(len(activeIdxs) - 1):
    zaIdx: int = activeIdxs[i]
    zbIdx: int = activeIdxs[i + 1]
    zaGeo: BoardGeometry = geoByIdx[zaIdx]
    zbGeo: BoardGeometry = geoByIdx[zbIdx]

    dZbWe: int = _span_get(zbGeo, sfN.We, horizontal=True)
    dZbNe: int = _span_get(zbGeo, sfN.Ne, horizontal=False)
    dZaEe: int = _span_get(zaGeo, sfN.Ee, horizontal=True)

    print(f"  seam ({zaIdx},1)→({zbIdx},1)  Zb.We={dZbWe}  Zb.Ne={dZbNe}  Za.Ee={dZaEe}")

    zaChanges: list[GeoChange] = [(sfN.Efi, GeoArgScalar(dZbWe), GeoOp.DISPLACE)]
    if dZbNe:
        zaChanges += [
            (sfN.Ne, GeoArgScalar(-dZbNe), GeoOp.DISPLACE),
            (sfN.Se, GeoArgScalar(dZbNe), GeoOp.DISPLACE),
        ]
    zaResult: Result[BoardGeometry] = geometry_change(zaChanges, zaGeo)
    if OK(zaResult):
        geoByIdx[zaIdx] = zaResult.value

    if dZaEe:
        zbResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Wm, GeoArgScalar(dZaEe), GeoOp.DISPLACE)],
            zbGeo,
        )
        if OK(zbResult):
            geoByIdx[zbIdx] = zbResult.value

    zbxIdx: int
    for zbxIdx in activeIdxs[i + 1:]:
        zbxGeo: BoardGeometry = geoByIdx[zbxIdx]
        zbxResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Z, GeoArgScalar(dZbWe), GeoOp.DISPLACE)],
            zbxGeo,
        )
        if OK(zbxResult):
            geoByIdx[zbxIdx] = zbxResult.value

    if dZaEe:
        for zbxIdx in activeIdxs[i + 2:]:
            zbxGeo = geoByIdx[zbxIdx]
            zbxResult = geometry_change(
                [(sfN.Z, GeoArgScalar(dZaEe), GeoOp.DISPLACE)],
                zbxGeo,
            )
            if OK(zbxResult):
                geoByIdx[zbxIdx] = zbxResult.value

print()

# ---------------------------------------------------------------------------
# 6. Phase 2 — seam chip override and re-materialization (sequential)
# ---------------------------------------------------------------------------

print("--- PHASE 2: SEAM CHIP OVERRIDE + RE-MATERIALIZATION ---")
print()

etRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(sfN.Et)
wtRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(sfN.Wt)

if not OK(etRidResult) or not OK(wtRidResult):
    print("Error: could not resolve Et/Wt region IDs.")
    sys.exit(1)

etRid: BoardRegionId = etRidResult.value
wtRid: BoardRegionId = wtRidResult.value

matByIdx: dict[int, BoardMaterializedSolution] = {}

for i in range(len(activeIdxs) - 1):
    zaIdx = activeIdxs[i]
    zbIdx = activeIdxs[i + 1]

    zaGeo = geoByIdx[zaIdx]
    zbGeo = geoByIdx[zbIdx]

    etZone: GeometryZone | None = zaGeo.geometryZonesById.get(etRid)
    wtZone: GeometryZone | None = zbGeo.geometryZonesById.get(wtRid)

    if etZone is None or wtZone is None:
        print(f"  seam ({zaIdx},1)→({zbIdx},1): Et or Wt zone missing — skip")
        continue

    sharedChipNames: list[str] = list(etZone.chipDrawPlacementsByChip.keys())

    print(f"  seam ({zaIdx},1)→({zbIdx},1)")
    print(f"    shared chips: {sharedChipNames}")
    print()
    print("    Za east terminal (dominant):")
    for chipName in sharedChipNames:
        pos = etZone.exactTerminalWorldPositionsByChip.get(chipName, {})
        print(f"      {chipName}: {pos}")
    print()
    print("    Zb west terminal BEFORE override:")
    for chipName in sharedChipNames:
        pos = wtZone.exactTerminalWorldPositionsByChip.get(chipName, {})
        print(f"      {chipName}: {pos}")

    # Build overridden Wt zone — full entry replacement for shared chips
    newWtPlacements = {
        **wtZone.chipDrawPlacementsByChip,
        **{
            name: etZone.chipDrawPlacementsByChip[name]
            for name in sharedChipNames
            if name in etZone.chipDrawPlacementsByChip
        },
    }
    newWtTerminals = {
        **wtZone.exactTerminalWorldPositionsByChip,
        **{
            name: etZone.exactTerminalWorldPositionsByChip[name]
            for name in sharedChipNames
            if name in etZone.exactTerminalWorldPositionsByChip
        },
    }
    newWtZone: GeometryZone = GeometryZone(
        regionId=wtZone.regionId,
        frame=wtZone.frame,
        routingZoneRegionId=wtZone.routingZoneRegionId,
        chipDrawPlacementsByChip=newWtPlacements,
        exactTerminalWorldPositionsByChip=newWtTerminals,
    )

    # Rebuild Zb geometry with overridden Wt zone
    newZones: dict[BoardRegionId, GeometryZone] = dict(zbGeo.geometryZonesById)
    newZones[wtRid] = newWtZone
    overriddenGeo: BoardGeometry = BoardGeometry(
        geometryZonesById=newZones,
        effectiveBoundaryFramesByName=zbGeo.effectiveBoundaryFramesByName,
    )
    object.__setattr__(
        overriddenGeo,
        "_orphanChipDrawPlacementsByChip",
        zbGeo._orphanChipDrawPlacementsByChip,
    )
    object.__setattr__(
        overriddenGeo,
        "_orphanExactTerminalWorldPositionsByChip",
        zbGeo._orphanExactTerminalWorldPositionsByChip,
    )
    geoByIdx[zbIdx] = overriddenGeo

    print()
    print("    Zb west terminal AFTER override:")
    for chipName in sharedChipNames:
        pos = newWtZone.exactTerminalWorldPositionsByChip.get(chipName, {})
        print(f"      {chipName}: {pos}")

    # Build adjusted Zb board with overridden geometry
    zbBoard: Board = boardByIdx[zbIdx]
    adjustedBoard: Board = replace(zbBoard, geometry=overriddenGeo)

    # Re-materialize Zb
    zbSolver: BoardSolver = solverByIdx[zbIdx]
    zbSolution: BoardSolution = zbSolver.solution_get()
    mat = zbSolution.board_materialize(board=adjustedBoard)

    violations = mat.boundaryViolations_get()
    if violations:
        print(f"\n    boundary violations after re-materialize: {len(violations)}")
        print("    → re-solving Zb on adjusted board")
        adjustedSolver: BoardSolver = replace(zbSolver, board=adjustedBoard)
        adjustedSolution: BoardSolution = adjustedSolver.solution_get()
        mat = adjustedSolution.board_materialize(board=adjustedBoard)
        resolveViolations = mat.boundaryViolations_get()
        if resolveViolations:
            print(f"    ✗ violations persist after re-solve: {len(resolveViolations)}")
        else:
            print("    ✓ re-solve cleared boundary violations")
    else:
        print("\n    re-materialize: OK (no boundary violations)")

    matByIdx[zbIdx] = mat
    print()

# Also materialize Za (zone 1) against its harmonized geometry
if activeIdxs:
    zaFirst: int = activeIdxs[0]
    zaFirstBoard: Board = replace(boardByIdx[zaFirst], geometry=geoByIdx[zaFirst])
    zaFirstSol: BoardSolution = solverByIdx[zaFirst].solution_get()
    matByIdx[zaFirst] = zaFirstSol.board_materialize(board=zaFirstBoard)

# ---------------------------------------------------------------------------
# 7. Per-zone renders: (a) wiring — chip boxes + routes, cropped
#                      (b) relaxed zone geometry — Ni/Si at final positions
# ---------------------------------------------------------------------------

print()
print("--- PER-ZONE WIRING + RELAXED GEOMETRY ---")
print()

for idx in activeIdxs:
    mat = matByIdx.get(idx)
    print(f"=== ZONE ({idx},1) WIRING ===")
    print()
    if mat is not None:
        print(mat.geometry_sprint())
    else:
        print("  (not materialized)")
    print()
    print(f"=== ZONE ({idx},1) RELAXED ZONES ===")
    print()
    if mat is not None:
        print(mat.geometryRelaxed_sprint(legend_show=True))
    else:
        print("  (not materialized)")
    print()

# ---------------------------------------------------------------------------
# 8. World canvas — zone bands + chip boxes + routes at harmonized world coords
#
# Three-layer blit (back to front):
#   1. Zone band grid  — from geometry_sprint on the relaxed board geometry
#   2. Chip boxes + routes — from boardCanvas_render on the relaxed board
#
# Zone band lines carry world row labels ("NN: content"); the content string
# starts at displayStartCol = min(frame.horizontalStart) of the zone geometry.
# ---------------------------------------------------------------------------

print()
print("--- WORLD CANVAS ---")
print()


def _worldSize_from_mats(
    mats: dict[int, BoardMaterializedSolution],
) -> tuple[int, int]:
    """Return (maxCols, maxRows) needed to hold all zone content."""
    max_col: int = 0
    max_row: int = 0
    for m in mats.values():
        rb = m._relaxedShadowBoard_build()
        for frame in rb.geometry.regionFramesById.values():
            max_col = max(max_col, frame.horizontalEnd_calculate())
            max_row = max(max_row, frame.verticalEnd_calculate())
        for frame in rb.geometry.effectiveBoundaryFramesByName.values():
            max_col = max(max_col, frame.horizontalEnd_calculate())
            max_row = max(max_row, frame.verticalEnd_calculate())
        for cp in rb.geometry.chipDrawPlacementsByChip.values():
            wf = cp.worldFrame_get()
            max_col = max(max_col, wf.bottomRight[0] + 1)
            max_row = max(max_row, wf.bottomRight[1] + 1)
        for (col, row) in m._realizedRouteSet.mergedCellMap_get():
            max_col = max(max_col, col + 1)
            max_row = max(max_row, row + 1)
    return max_col, max_row


_wMaxCols, _wMaxRows = _worldSize_from_mats(matByIdx)
_worldGrid: list[list[str]] = [[" "] * _wMaxCols for _ in range(_wMaxRows)]

# Layer 1: zone band grid (post-relaxation zone geometry)
for idx in activeIdxs:
    _mat = matByIdx.get(idx)
    if _mat is None:
        continue
    _rb = _mat._relaxedShadowBoard_build()
    _dStartCol: int = min(
        frame.horizontalStart for frame in _rb.geometry.regionFramesById.values()
    )
    _geoText: str = _rb.geometry_sprint(legend_show=False)
    for _line in _geoText.split("\n")[1:]:  # skip ruler row
        if ": " not in _line:
            continue
        _label, _, _content = _line.partition(": ")
        try:
            _wRow: int = int(_label.strip())
        except ValueError:
            continue
        for _ci, _ch in enumerate(_content):
            _wCol: int = _dStartCol + _ci
            if _ch != " " and 0 <= _wRow < _wMaxRows and 0 <= _wCol < _wMaxCols:
                _worldGrid[_wRow][_wCol] = _ch

# Layer 2: chip boxes + realized routes (non-space overwrites zone symbols)
for idx in activeIdxs:
    _mat = matByIdx.get(idx)
    if _mat is None:
        continue
    _rb = _mat._relaxedShadowBoard_build()
    _chipRouteLines: tuple[str, ...] = boardCanvas_render(
        board=_rb,
        realizedRouteSet=_mat._realizedRouteSet,
    )
    for _ri, _line in enumerate(_chipRouteLines):
        for _ci, _ch in enumerate(_line):
            if _ch != " " and 0 <= _ri < _wMaxRows and 0 <= _ci < _wMaxCols:
                _worldGrid[_ri][_ci] = _ch

_ruler: str = "".join(str(c % 10) for c in range(_wMaxCols))
print(f"    {_ruler}")
for _ri, _row in enumerate(_worldGrid):
    if any(_ch != " " for _ch in _row):
        print(f"{_ri:3}: {''.join(_row)}")
