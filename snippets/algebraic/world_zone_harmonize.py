"""World zone seam harmonizer.

Derives the number of seam harmonizations from the circuit calling depth
(bandCount - 1 pairs) and applies the canonical Za→Zb mutation sequence to
each adjacent zone pair with a realized intra kernel:

  1. dWe = We(Zb).horizontalSpan
  2. DISPLACE Et  of Za  by  +dWe   east terminal expands eastward
  3. dNe = Ne(Zb).verticalSpan
  4. DISPLACE Ne  of Za  by  -dNe   north ring expands northward (floor-guard)
     DISPLACE Se  of Za  by  +dNe   south ring expands southward
  5. DISPLACE Z   of Zb and all subsequent active zones by +dWe

Each zone's geometry is built via contextResult_buildFromDocumentAndZone so
that overlapIndex i → lowerDepth=i-1, upperDepth=i (overlapping model).

All mutations use geometry_change from georules.py with GeoArgScalar,
matching the sign conventions in zone_georules_displace.py:
    positive = outward for free-direction anchors (Et, Se, Ee)
    negative = outward for floor-guard anchors (Ne, We, Wt)

Usage from CLI:
    uv run python -m signalflow examples/simple-circuit/back-and-forth.yaml \\
        --run-snippet snippets/algebraic/world_zone_harmonize.py

Run from the REPL with:
    load("snippets/algebraic/world_zone_harmonize.py")
"""

from __future__ import annotations

import sys

import yaml

from signalflow.board import BoardGeometry, BoardKernel, BoardZone
from signalflow.board.geometry.georules import (
    GeoArgScalar,
    GeoChange,
    GeoOp,
    geometry_change,
)
from signalflow.board.geometry.mutation import boardRegionIdResult_fromSfN
from signalflow.board.geometry.zones import GeometryZone
from signalflow.board.types import BoardRegionId
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.engine.inspect import SignalFlowContext
from signalflow.engine.inspect.zone_local import (
    contextResult_buildFromDocumentAndZone,
)
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
#    bandCount bands → bandCount-1 adjacent seams to process
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
# 3. Span helper — read horizontalSpan or verticalSpan of one sfN region
# ---------------------------------------------------------------------------


def _span_get(geometry: BoardGeometry, anchor: sfN, horizontal: bool) -> int:
    """Return the span of one sfN region in geometry, 0 if absent."""
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
# 4. Build per-zone geometries using zone_local (overlapping model)
#    overlapIndex i → lowerDepth=i-1 (west chip), upperDepth=i (east chip)
#    Each synthetic context places the zone at (1,1); read kernel from it.
# ---------------------------------------------------------------------------

geoByIdx: dict[int, BoardGeometry] = {}
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
    geoByIdx[overlapIdx] = k.board_get().geometry_get()

activeIdxs: list[int] = sorted(geoByIdx)
beforeByIdx: dict[int, BoardGeometry] = dict(geoByIdx)

# ---------------------------------------------------------------------------
# 5. Harmonize each adjacent pair (Za, Zb)
# ---------------------------------------------------------------------------

print(f"--- WORLD ZONE HARMONIZATION: {_yaml_path} ---")
print()
print(f"bands: {bandCount}  pairs: {numPairs}  active zones: {activeIdxs}")
print()
print("--- SEAM OPERATIONS ---")
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

    # --- Za mutations: make room for Zb's extra rings inside overlap space ---
    # Efi: free-direction, positive = eastward
    # Ne:  floor-guard,    negative = northward
    # Se:  free-direction, positive = southward
    zaChanges: list[GeoChange] = [(sfN.Efi, GeoArgScalar(dZbWe), GeoOp.DISPLACE)]
    if dZbNe:
        zaChanges += [
            (sfN.Ne, GeoArgScalar(-dZbNe), GeoOp.DISPLACE),
            (sfN.Se, GeoArgScalar(dZbNe), GeoOp.DISPLACE),
        ]
    zaResult: Result[BoardGeometry] = geometry_change(zaChanges, zaGeo)
    if OK(zaResult):
        geoByIdx[zaIdx] = zaResult.value

    # --- Zb mutation: make room for Za's east extra ring inside overlap space ---
    if dZaEe:
        zbResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Wm, GeoArgScalar(dZaEe), GeoOp.DISPLACE)],
            zbGeo,
        )
        if OK(zbResult):
            geoByIdx[zbIdx] = zbResult.value

    # --- Z-cascade 1: propagate Za's Efi expansion (dZbWe) to Zb and beyond ---
    zbxIdx: int
    for zbxIdx in activeIdxs[i + 1:]:
        zbxGeo: BoardGeometry = geoByIdx[zbxIdx]
        zbxResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Z, GeoArgScalar(dZbWe), GeoOp.DISPLACE)],
            zbxGeo,
        )
        if OK(zbxResult):
            geoByIdx[zbxIdx] = zbxResult.value

    # --- Z-cascade 2: propagate Zb's Wm expansion (dZaEe) to zones beyond Zb ---
    # Zb already received dZaEe internally via the Wm floor-guard rule.
    # Zb+1 onward have not; they need to shift east to clear Zb's expanded east extent.
    if dZaEe:
        for zbxIdx in activeIdxs[i + 2:]:
            zbxGeo: BoardGeometry = geoByIdx[zbxIdx]
            zbxResult: Result[BoardGeometry] = geometry_change(
                [(sfN.Z, GeoArgScalar(dZaEe), GeoOp.DISPLACE)],
                zbxGeo,
            )
            if OK(zbxResult):
                geoByIdx[zbxIdx] = zbxResult.value

print()

# ---------------------------------------------------------------------------
# 6. Before / after display per zone
# ---------------------------------------------------------------------------

idx: int
for idx in activeIdxs:
    print(f"--- ZONE ({idx},1) BEFORE ---")
    print()
    print(beforeByIdx[idx].geometry_sprint(legend_show=False))
    print()
    print(f"--- ZONE ({idx},1) AFTER  ---")
    print()
    print(geoByIdx[idx].geometry_sprint(legend_show=False))
    print()
