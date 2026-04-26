"""World zone overlap materializer — harmonize + materialize world zones.

Harmonizes zone geometries (same algorithm as world_zone_harmonize.py), then
records seam terminal alignment columns and materializes each zone against its
natural harmonized geometry.  World canvas blits each zone at its wOffset so
seam chips align without transplanting chip positions across zone boundaries.

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
from signalflow.board.solver_runtime import BoardSolver
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

    print(f"  seam (1,{zaIdx})→(1,{zbIdx})  Zb.We={dZbWe}  Zb.Ne={dZbNe}  Za.Ee={dZaEe}")

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
# 6. Phase 2 — seam terminal recording + natural materialization
# ---------------------------------------------------------------------------

print("--- PHASE 2: SEAM TERMINALS + MATERIALIZATION ---")
print()

etRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(sfN.Et)
wtRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(sfN.Wt)

if not OK(etRidResult) or not OK(wtRidResult):
    print("Error: could not resolve Et/Wt region IDs.")
    sys.exit(1)

etRid: BoardRegionId = etRidResult.value
wtRid: BoardRegionId = wtRidResult.value

matByIdx: dict[int, BoardMaterializedSolution] = {}
zaEtColByIdx: dict[int, int] = {}
zbWtColByIdx: dict[int, int] = {}

for i in range(len(activeIdxs) - 1):
    zaIdx = activeIdxs[i]
    zbIdx = activeIdxs[i + 1]

    zaGeo = geoByIdx[zaIdx]
    zbGeo = geoByIdx[zbIdx]

    etZone: GeometryZone | None = zaGeo.geometryZonesById.get(etRid)
    wtZone: GeometryZone | None = zbGeo.geometryZonesById.get(wtRid)

    if etZone is None or wtZone is None:
        print(f"  seam (1,{zaIdx})→(1,{zbIdx}): Et or Wt zone missing — skip")
        continue

    sharedChipNames: list[str] = list(etZone.chipDrawPlacementsByChip.keys())

    _et_cols: list[int] = [
        pos[0]
        for cn in sharedChipNames
        for pos in (etZone.exactTerminalWorldPositionsByChip.get(cn) or {}).values()
    ]
    _wt_cols: list[int] = [
        pos[0]
        for cn in sharedChipNames
        for pos in (wtZone.exactTerminalWorldPositionsByChip.get(cn) or {}).values()
    ]
    if _et_cols:
        zaEtColByIdx[zaIdx] = min(_et_cols)
    if _wt_cols:
        zbWtColByIdx[zbIdx] = min(_wt_cols)

    print(f"  seam (1,{zaIdx})→(1,{zbIdx})  Za.Et={zaEtColByIdx.get(zaIdx, '?')}  Zb.Wt={zbWtColByIdx.get(zbIdx, '?')}")
    print(f"    shared chips: {sharedChipNames}")
    print()

# Materialize all zones with harmonized natural geometry (no seam override).
# wOffsets handles world-canvas alignment — no chip position transplant needed.
for _idx in activeIdxs:
    _board: Board = replace(boardByIdx[_idx], geometry=geoByIdx[_idx])
    _sol = solverByIdx[_idx].solution_get()
    matByIdx[_idx] = _sol.board_materialize(board=_board)

# ---------------------------------------------------------------------------
# 6b. World horizontal offsets (terminal alignment)
#
# Each zone is rendered in its own local coordinate system.  The world
# canvas must shift zone (i+1) east so that its Wt chips land exactly on
# zone i's Et chip positions (the shared seam chips).
#
# Offset recurrence:
#   wOffset[zone_1]   = 0
#   wOffset[zone_i+1] = wOffset[zone_i] + (Za.Et_minCol − Zb.Wt_minCol)
#
# The anchor cols are captured above from geoByIdx AFTER harmonization
# (Phase 5) but BEFORE the seam chip override.
# ---------------------------------------------------------------------------

wOffsets: dict[int, int] = {}
if activeIdxs:
    wOffsets[activeIdxs[0]] = 0
_j: int
for _j in range(len(activeIdxs) - 1):
    _zaI: int = activeIdxs[_j]
    _zbI: int = activeIdxs[_j + 1]
    _zaEt: int = zaEtColByIdx.get(_zaI, 0)
    _zbWt: int = zbWtColByIdx.get(_zbI, 0)
    wOffsets[_zbI] = wOffsets.get(_zaI, 0) + (_zaEt - _zbWt)

print("--- WORLD OFFSETS (terminal alignment) ---")
print()
_wi: int
_wo: int
for _wi, _wo in sorted(wOffsets.items()):
    print(f"  zone (1,{_wi}): +{_wo}  [Et_anchor={zaEtColByIdx.get(_wi, '—')}  Wt_anchor={zbWtColByIdx.get(_wi, '—')}]")
print()

# ---------------------------------------------------------------------------
# 7. Per-zone renders: (a) wiring — chip boxes + routes, cropped
#                      (b) relaxed zone geometry — Ni/Si at final positions
# ---------------------------------------------------------------------------

print()
print("--- PER-ZONE WIRING + RELAXED GEOMETRY ---")
print()

for idx in activeIdxs:
    mat = matByIdx.get(idx)
    print(f"=== ZONE (1,{idx}) WIRING ===")
    print()
    if mat is not None:
        print(mat.geometry_sprint())
    else:
        print("  (not materialized)")
    print()
    print(f"=== ZONE (1,{idx}) RELAXED ZONES ===")
    print()
    if mat is not None:
        print(mat.geometryRelaxed_sprint(legend_show=True))
    else:
        print("  (not materialized)")
    print()

# ---------------------------------------------------------------------------
# 8. World canvas — pure wiring: chip boxes + routes at harmonized world coords
#
# One pass per zone: blit boardCanvas_render output (chip boxes + routes)
# into a shared world grid.  Non-space wins over space.
# ---------------------------------------------------------------------------

print()
print("--- WORLD CANVAS ---")
print()


def _worldSize_from_mats(
    mats: dict[int, BoardMaterializedSolution],
    offsets: dict[int, int],
) -> tuple[int, int]:
    """Return (maxCols, maxRows) accounting for per-zone horizontal offsets."""
    max_col: int = 0
    max_row: int = 0
    for zIdx, m in mats.items():
        wOff = offsets.get(zIdx, 0)
        rb = m._relaxedShadowBoard_build()
        for cp in rb.geometry.chipDrawPlacementsByChip.values():
            wf = cp.worldFrame_get()
            max_col = max(max_col, wf.bottomRight[0] + 1 + wOff)
            max_row = max(max_row, wf.bottomRight[1] + 1)
        for (row, col) in m._realizedRouteSet.mergedCellMap_get():
            max_col = max(max_col, col + 1 + wOff)
            max_row = max(max_row, row + 1)
    return max_col, max_row


_wMaxCols, _wMaxRows = _worldSize_from_mats(matByIdx, wOffsets)
_worldGrid: list[list[str]] = [[" "] * _wMaxCols for _ in range(_wMaxRows)]

for idx in activeIdxs:
    _mat = matByIdx.get(idx)
    if _mat is None:
        continue
    _wOff: int = wOffsets.get(idx, 0)
    _rb = _mat._relaxedShadowBoard_build()
    _chipRouteLines: tuple[str, ...] = boardCanvas_render(
        board=_rb,
        realizedRouteSet=_mat._realizedRouteSet,
    )
    for _ri, _line in enumerate(_chipRouteLines):
        for _ci, _ch in enumerate(_line):
            _wc: int = _ci + _wOff
            if _ch != " " and 0 <= _ri < _wMaxRows and 0 <= _wc < _wMaxCols:
                _worldGrid[_ri][_wc] = _ch
    for (_row, _col), _trackCell in _mat._realizedRouteSet.mergedCellMap_get().items():
        if _trackCell.glyph and _trackCell.glyph != " ":
            _wc = _col + _wOff
            if 0 <= _row < _wMaxRows and 0 <= _wc < _wMaxCols:
                if _worldGrid[_row][_wc] == " ":
                    _worldGrid[_row][_wc] = _trackCell.glyph

_ruler: str = "".join(str(c % 10) for c in range(_wMaxCols))
print(f"    {_ruler}")
for _ri, _row in enumerate(_worldGrid):
    if any(_ch != " " for _ch in _row):
        print(f"{_ri:3}: {''.join(_row)}")
