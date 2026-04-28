"""World zone inspector — targeted wiring and geometry views.

Full world harmonization always runs. Output is filtered to the listed zones.

Usage:
    uv run python -m signalflow examples/.../foo.yaml \\
        --run-snippet snippets/algebraic/world_zone_inspect.py \\
        --zones 1,1 [--geometry] [--wiring]
    uv run python -m signalflow examples/.../foo.yaml \\
        --run-snippet snippets/algebraic/world_zone_inspect.py \\
        --zones 1,1;1,2 --wiring

--zones     semicolon-separated zone list, each as col,row (e.g. 1,1;1,2)
--geometry  post-relaxed zone-band geometry per listed zone (sequential)
--wiring    combined world wiring canvas for listed zones, re-originated

Zone list must be in ascending sequential column order (no gaps, no reversal).
Zone index = max(col, row), matching contextResult_buildFromDocumentAndZone.
"""

from __future__ import annotations

import argparse
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
# 1. Parse args
# ---------------------------------------------------------------------------

_yaml_path: str = source_yaml  # type: ignore[name-defined]  # noqa: F821

parser = argparse.ArgumentParser(
    description="World zone inspector — wiring and geometry views.",
)
parser.add_argument(
    "--zones",
    default="1,1",
    help="Semicolon-separated zones as col,row. Example: --zones 1,1;1,2",
)
parser.add_argument(
    "--geometry",
    action="store_true",
    help="Show post-relaxed zone-band geometry for each listed zone.",
)
parser.add_argument(
    "--wiring",
    action="store_true",
    help="Show combined world wiring canvas for listed zones.",
)
args: argparse.Namespace = parser.parse_known_args(sys.argv[1:])[0]

# Parse zone specs and compute canonical zone indices (max(col, row))
zoneSpecs: list[tuple[int, int]] = []
for _spec in args.zones.split(";"):
    _spec = _spec.strip()
    try:
        _cStr, _rStr = _spec.split(",")
        zoneSpecs.append((int(_cStr), int(_rStr)))
    except ValueError:
        print(f"Error: invalid zone spec '{_spec}'. Use col,row format (e.g. 1,1).")
        sys.exit(1)

# Zone index = max(col, row), matching contextResult_buildFromDocumentAndZone
requestedIdxs: list[int] = [max(c, r) for c, r in zoneSpecs]

# Require at least one view mode
if not args.geometry and not args.wiring:
    print("Select at least one view mode:")
    print()
    print("  --geometry   post-relaxed zone bands, per listed zone")
    print("  --wiring     combined world wiring canvas for listed zones")
    print()
    print("Examples:")
    print(f"  uv run python -m signalflow {_yaml_path} \\")
    print(f"      --run-snippet snippets/algebraic/world_zone_inspect.py \\")
    print(f"      --zones {args.zones} --geometry")
    print(f"  uv run python -m signalflow {_yaml_path} \\")
    print(f"      --run-snippet snippets/algebraic/world_zone_inspect.py \\")
    print(f"      --zones {args.zones} --wiring")
    sys.exit(0)

# Validate ordering and sequentiality
if len(requestedIdxs) > 1:
    for _i in range(len(requestedIdxs) - 1):
        if requestedIdxs[_i] >= requestedIdxs[_i + 1]:
            print(
                f"Error: zones out of order at position {_i + 1}: "
                f"(1,{requestedIdxs[_i]}) then (1,{requestedIdxs[_i + 1]}). "
                f"Must be ascending."
            )
            sys.exit(1)
        if requestedIdxs[_i + 1] - requestedIdxs[_i] != 1:
            print(
                f"Error: non-sequential zones: (1,{requestedIdxs[_i]}) then "
                f"(1,{requestedIdxs[_i + 1]}). Zones must be consecutive (no gaps)."
            )
            sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Load document + calling stack
# ---------------------------------------------------------------------------

with open(_yaml_path) as _handle:
    documentDict: dict[str, object] = yaml.safe_load(_handle)

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
# 4. Build per-zone geometries + solver artifacts (all active zones)
# ---------------------------------------------------------------------------

geoByIdx: dict[int, BoardGeometry] = {}
boardByIdx: dict[int, Board] = {}
solverByIdx: dict[int, BoardSolver] = {}

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

# Validate requested zones exist in the active set
for _idx in requestedIdxs:
    if _idx not in activeIdxs:
        print(
            f"Error: zone (1,{_idx}) is not active. "
            f"Active zones: {[(1, i) for i in activeIdxs]}"
        )
        sys.exit(1)

# ---------------------------------------------------------------------------
# 5a. Ne span equalization across seam boundaries (before column harmonization)
#
# Adjacent zones may have different Ne spans because their circuit geometries
# differ (different fan-out). Phase 5's floor guard uses dZbNe as clearance.
# If Za.Ne != Zb.Ne, the ring routing in the smaller zone uses different rows
# than the larger zone at the seam — creating visible routing discontinuities
# where turning corners collide with horizontal ring wires.
#
# Fix: stretch the smaller zone's Ne-family zones southward to match the
# larger zone's Ne span. Phase 5 then uses the equalized span for both sides.
# ---------------------------------------------------------------------------

_NE_SIBLINGS: list[sfN] = [sfN.Ne, sfN.NWe, sfN.NEe, sfN.NWx, sfN.NEx]
_neRids: list[BoardRegionId] = []
for _sfn in _NE_SIBLINGS:
    _neRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(_sfn)
    if OK(_neRidResult):
        _neRids.append(_neRidResult.value)


def _neSpanStretch_apply(geo: BoardGeometry, extraRows: int) -> BoardGeometry:
    """Stretch Ne-family zone frames southward (verticalSpan += extraRows)."""
    _newZones: dict[BoardRegionId, GeometryZone] = dict(geo.geometryZonesById)
    for _rid in _neRids:
        if _rid in _newZones:
            _z: GeometryZone = _newZones[_rid]
            _newZones[_rid] = GeometryZone(
                regionId=_z.regionId,
                frame=replace(
                    _z.frame,
                    verticalSpan=_z.frame.verticalSpan + extraRows,
                ),
                routingZoneRegionId=_z.routingZoneRegionId,
                chipDrawPlacementsByChip=_z.chipDrawPlacementsByChip,
                exactTerminalWorldPositionsByChip=(
                    _z.exactTerminalWorldPositionsByChip
                ),
            )
    return BoardGeometry(
        geometryZonesById=_newZones,
        effectiveBoundaryFramesByName=geo.effectiveBoundaryFramesByName,
    )


for _i in range(len(activeIdxs) - 1):
    _dZaNe: int = _span_get(geoByIdx[activeIdxs[_i]], sfN.Ne, horizontal=False)
    _dZbNe: int = _span_get(geoByIdx[activeIdxs[_i + 1]], sfN.Ne, horizontal=False)
    if _dZaNe == _dZbNe or _dZaNe == 0 or _dZbNe == 0:
        continue
    _targetNe: int = max(_dZaNe, _dZbNe)
    for _5a_zIdx, _5a_origNe in (
        (activeIdxs[_i], _dZaNe),
        (activeIdxs[_i + 1], _dZbNe),
    ):
        _5a_extra: int = _targetNe - _5a_origNe
        if _5a_extra <= 0:
            continue
        geoByIdx[_5a_zIdx] = _neSpanStretch_apply(geoByIdx[_5a_zIdx], _5a_extra)
        _5a_floorResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Ne, GeoArgScalar(-_5a_extra), GeoOp.DISPLACE)],
            geoByIdx[_5a_zIdx],
        )
        if OK(_5a_floorResult):
            geoByIdx[_5a_zIdx] = _5a_floorResult.value

# ---------------------------------------------------------------------------
# 5. Full harmonization (all active zones)
# ---------------------------------------------------------------------------

etRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(sfN.Et)
wtRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(sfN.Wt)
if not OK(etRidResult) or not OK(wtRidResult):
    print("Error: could not resolve Et/Wt region IDs.")
    sys.exit(1)
etRid: BoardRegionId = etRidResult.value
wtRid: BoardRegionId = wtRidResult.value

_i: int
for _i in range(len(activeIdxs) - 1):
    zaIdx: int = activeIdxs[_i]
    zbIdx: int = activeIdxs[_i + 1]
    zaGeo: BoardGeometry = geoByIdx[zaIdx]
    zbGeo: BoardGeometry = geoByIdx[zbIdx]

    dZbWe: int = _span_get(zbGeo, sfN.We, horizontal=True)
    dZbNe: int = _span_get(zbGeo, sfN.Ne, horizontal=False)
    dZaEe: int = _span_get(zaGeo, sfN.Ee, horizontal=True)

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
    for zbxIdx in activeIdxs[_i + 1:]:
        zbxGeo: BoardGeometry = geoByIdx[zbxIdx]
        zbxResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Z, GeoArgScalar(dZbWe), GeoOp.DISPLACE)],
            zbxGeo,
        )
        if OK(zbxResult):
            geoByIdx[zbxIdx] = zbxResult.value

    if dZaEe:
        for zbxIdx in activeIdxs[_i + 2:]:
            zbxGeo = geoByIdx[zbxIdx]
            zbxResult = geometry_change(
                [(sfN.Z, GeoArgScalar(dZaEe), GeoOp.DISPLACE)],
                zbxGeo,
            )
            if OK(zbxResult):
                geoByIdx[zbxIdx] = zbxResult.value

# ---------------------------------------------------------------------------
# 5b. Vertical seam terminal alignment (separate pass, after all column
#     harmonization is complete).
#
# Column harmonization Ne/Se floor guards shift zone geometries vertically.
# Reading chip rows here — after all column harmonization — gives the stable
# canonical positions that are not perturbed by any subsequent seam's floor
# guard.  Za.Et is canonical; Zb.Wt displaces to match.
# ---------------------------------------------------------------------------

for _i in range(len(activeIdxs) - 1):
    zaIdx = activeIdxs[_i]
    zbIdx = activeIdxs[_i + 1]
    zaGeo = geoByIdx[zaIdx]
    zbGeo = geoByIdx[zbIdx]
    _etZone: GeometryZone | None = zaGeo.geometryZonesById.get(etRid)
    _wtZone: GeometryZone | None = zbGeo.geometryZonesById.get(wtRid)
    if _etZone and _wtZone:
        _etRows = [
            placement.drawTopLeft[1]
            for placement in _etZone.chipDrawPlacementsByChip.values()
        ]
        _wtRows = [
            placement.drawTopLeft[1]
            for placement in _wtZone.chipDrawPlacementsByChip.values()
        ]
        if _etRows and _wtRows:
            _vDelta = min(_etRows) - min(_wtRows)
            if _vDelta:
                _vtResult: Result[BoardGeometry] = geometry_change(
                    [(sfN.Wt, GeoArgScalar(_vDelta), GeoOp.DISPLACE_VERTICAL)],
                    zbGeo,
                )
                if OK(_vtResult):
                    geoByIdx[zbIdx] = _vtResult.value

# ---------------------------------------------------------------------------
# 6. Seam terminal recording + natural materialization (all active zones)
# ---------------------------------------------------------------------------

matByIdx: dict[int, BoardMaterializedSolution] = {}
zaEtColByIdx: dict[int, int] = {}
zbWtColByIdx: dict[int, int] = {}

for _i in range(len(activeIdxs) - 1):
    zaIdx = activeIdxs[_i]
    zbIdx = activeIdxs[_i + 1]
    zaGeo = geoByIdx[zaIdx]
    zbGeo = geoByIdx[zbIdx]

    etZone: GeometryZone | None = zaGeo.geometryZonesById.get(etRid)
    wtZone: GeometryZone | None = zbGeo.geometryZonesById.get(wtRid)

    if etZone is None or wtZone is None:
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

# Materialize all zones with harmonized natural geometry (no seam override).
# wOffsets handles world-canvas alignment — no chip position transplant needed.
for _i, _idx in enumerate(activeIdxs):
    _board: Board = replace(boardByIdx[_idx], geometry=geoByIdx[_idx])
    _sol = solverByIdx[_idx].solution_get()
    matByIdx[_idx] = _sol.board_materialize(board=_board)

# ---------------------------------------------------------------------------
# 7. World offsets (terminal alignment) + re-origination to leftmost requested
# ---------------------------------------------------------------------------

wOffsets: dict[int, int] = {}
if activeIdxs:
    wOffsets[activeIdxs[0]] = 0
for _j in range(len(activeIdxs) - 1):
    _zaI: int = activeIdxs[_j]
    _zbI: int = activeIdxs[_j + 1]
    _zaEt: int = zaEtColByIdx.get(_zaI, 0)
    _zbWt: int = zbWtColByIdx.get(_zbI, 0)
    wOffsets[_zbI] = wOffsets.get(_zaI, 0) + (_zaEt - _zbWt)

_originShift: int = wOffsets.get(requestedIdxs[0], 0)

# ---------------------------------------------------------------------------
# 8. Output
# ---------------------------------------------------------------------------

print(f"--- WORLD ZONE INSPECT: {_yaml_path} ---")
print()
_offsetSummary = "  ".join(
    f"(1,{idx}) off={wOffsets.get(idx, 0) - _originShift}"
    for idx in requestedIdxs
)
print(f"zones: {_offsetSummary}")
print()

# --- geometry view (per-zone, sequential) ---
if args.geometry:
    for _idx in requestedIdxs:
        _mat = matByIdx.get(_idx)
        print(f"=== ZONE (1,{_idx}) GEOMETRY ===")
        print()
        if _mat is not None:
            print(_mat.geometryRelaxed_sprint(legend_show=True))
        else:
            print("  (not materialized)")
        print()

# --- wiring view (combined world canvas, listed zones only, re-originated) ---
if args.wiring:
    _activeReq: list[int] = [idx for idx in requestedIdxs if idx in matByIdx]

    _wMaxCols: int = 0
    _wMaxRows: int = 0
    for _idx in _activeReq:
        _wOff = wOffsets.get(_idx, 0) - _originShift
        _m = matByIdx[_idx]
        _rb = _m._relaxedShadowBoard_build()
        for _frame in _rb.geometry.regionFramesById.values():
            _wMaxCols = max(_wMaxCols, _frame.horizontalEnd_calculate() + _wOff)
            _wMaxRows = max(_wMaxRows, _frame.verticalEnd_calculate())
        for _frame in _rb.geometry.effectiveBoundaryFramesByName.values():
            _wMaxCols = max(_wMaxCols, _frame.horizontalEnd_calculate() + _wOff)
            _wMaxRows = max(_wMaxRows, _frame.verticalEnd_calculate())
        for _cp in _rb.geometry.chipDrawPlacementsByChip.values():
            _wf = _cp.worldFrame_get()
            _wMaxCols = max(_wMaxCols, _wf.bottomRight[0] + 1 + _wOff)
            _wMaxRows = max(_wMaxRows, _wf.bottomRight[1] + 1)
        for (_row, _col) in _m._realizedRouteSet.mergedCellMap_get():
            _wMaxCols = max(_wMaxCols, _col + 1 + _wOff)
            _wMaxRows = max(_wMaxRows, _row + 1)

    _WIRE_H: frozenset[str] = frozenset({"═", "╪"})
    _WIRE_V: frozenset[str] = frozenset({"║", "╫"})
    _WIRE_ALL: frozenset[str] = _WIRE_H | _WIRE_V

    _BD_N, _BD_S, _BD_E, _BD_W = 1, 2, 4, 8
    _SINGLE_DIR: dict[str, int] = {
        "─": _BD_E | _BD_W,
        "│": _BD_N | _BD_S,
        "┌": _BD_E | _BD_S,
        "┐": _BD_W | _BD_S,
        "└": _BD_E | _BD_N,
        "┘": _BD_W | _BD_N,
        "├": _BD_N | _BD_S | _BD_E,
        "┤": _BD_N | _BD_S | _BD_W,
        "┬": _BD_E | _BD_W | _BD_S,
        "┴": _BD_E | _BD_W | _BD_N,
        "┼": _BD_N | _BD_S | _BD_E | _BD_W,
    }
    _DIR_SINGLE: dict[int, str] = {v: k for k, v in _SINGLE_DIR.items()}

    def _worldBlit(ex: str, ch: str) -> str:
        """Compose ch onto ex using wire-crossing and box-drawing algebra."""
        if ex in _WIRE_ALL:
            if ch not in _WIRE_ALL:
                return ex
            if ex in _WIRE_H and ch in _WIRE_V:
                return "╪"
            if ex in _WIRE_V and ch in _WIRE_H:
                return "╫"
            return ex
        if ex in _SINGLE_DIR and ch in _SINGLE_DIR:
            return _DIR_SINGLE.get(_SINGLE_DIR[ex] | _SINGLE_DIR[ch], ch)
        return ch

    _worldGrid: list[list[str]] = [[" "] * _wMaxCols for _ in range(_wMaxRows)]

    for _idx in _activeReq:
        _wOff = wOffsets.get(_idx, 0) - _originShift
        _m = matByIdx[_idx]
        _rb = _m._relaxedShadowBoard_build()
        _lines: tuple[str, ...] = boardCanvas_render(
            board=_rb,
            realizedRouteSet=_m._realizedRouteSet,
        )
        for _ri, _line in enumerate(_lines):
            for _ci, _ch in enumerate(_line):
                _wc = _ci + _wOff
                if _ch != " " and 0 <= _ri < _wMaxRows and 0 <= _wc < _wMaxCols:
                    _ex = _worldGrid[_ri][_wc]
                    _worldGrid[_ri][_wc] = _worldBlit(_ex, _ch) if _ex != " " else _ch
        for (_row, _col), _trackCell in _m._realizedRouteSet.mergedCellMap_get().items():
            if _trackCell.glyph and _trackCell.glyph != " ":
                _wc = _col + _wOff
                if 0 <= _row < _wMaxRows and 0 <= _wc < _wMaxCols:
                    if _worldGrid[_row][_wc] == " ":
                        _worldGrid[_row][_wc] = _trackCell.glyph

    _zoneLabel = "  ".join(f"(1,{idx})" for idx in _activeReq)
    print(f"--- WORLD WIRING: {_zoneLabel} ---")
    print()
    _ruler: str = "".join(str(c % 10) for c in range(_wMaxCols))
    print(f"    {_ruler}")
    for _ri, _row in enumerate(_worldGrid):
        if any(_ch != " " for _ch in _row):
            print(f"{_ri:3}: {''.join(_row)}")
    print()
