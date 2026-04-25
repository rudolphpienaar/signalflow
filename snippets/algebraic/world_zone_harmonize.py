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
from signalflow.engine.inspect.zone_local import contextResult_buildFromDocumentAndZone
from signalflow.models import CircuitDocument, Result, result_isOkCheck
from signalflow.models.calling_stack import (
    CallingStack,
    callingStackResult_buildFromCircuitDocument,
)
from signalflow.notation.sfn import sfN

# ---------------------------------------------------------------------------
# 1. Load document
# ---------------------------------------------------------------------------

with open(source_yaml) as handle:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(handle)

# ---------------------------------------------------------------------------
# 2. Calling depth → harmonization pair count
#    bandCount bands → bandCount-1 adjacent seams to process
# ---------------------------------------------------------------------------

cdResult: Result[CircuitDocument] = circuitDocumentResult_buildFromDocumentDict(
    documentDict
)
if not result_isOkCheck(cdResult):
    print("Error: failed to build CircuitDocument.")
    sys.exit(1)
circuitDocument: CircuitDocument = cdResult.value

csResult: Result[CallingStack] = callingStackResult_buildFromCircuitDocument(
    circuitDocument
)
if not result_isOkCheck(csResult):
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
    if result_isOkCheck(ridResult):
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
#    Each synthetic context places the zone at (1,1); read intra kernel from it.
# ---------------------------------------------------------------------------

geoByIdx: dict[int, BoardGeometry] = {}
overlapIdx: int
for overlapIdx in range(1, numPairs + 1):
    zoneCtxResult: Result[SignalFlowContext] = contextResult_buildFromDocumentAndZone(
        documentDict,
        columnIndex=overlapIdx,
        rowIndex=1,
    )
    if not result_isOkCheck(zoneCtxResult):
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

print(f"--- WORLD ZONE HARMONIZATION: {source_yaml} ---")  # type: ignore[name-defined]  # noqa: F821
print()
print(
    f"bands: {bandCount}  pairs: {numPairs}"
    f"  active zones: {activeIdxs}"
)
print()
print("--- SEAM OPERATIONS ---")
print()

i: int
for i in range(len(activeIdxs) - 1):
    zaIdx: int = activeIdxs[i]
    zbIdx: int = activeIdxs[i + 1]
    zaGeo: BoardGeometry = geoByIdx[zaIdx]
    zbGeo: BoardGeometry = geoByIdx[zbIdx]

    dWe: int = _span_get(zbGeo, sfN.We, horizontal=True)
    dNe: int = _span_get(zbGeo, sfN.Ne, horizontal=False)

    print(f"  seam ({zaIdx},1)→({zbIdx},1)  dWe={dWe}  dNe={dNe}")

    # --- Za mutations ---
    # Et: free-direction, positive = eastward expansion
    # Ne: floor-guard,    negative = northward expansion
    # Se: free-direction, positive = southward expansion
    zaChanges: list[GeoChange] = [(sfN.Et, GeoArgScalar(dWe), GeoOp.DISPLACE)]
    if dNe:
        zaChanges += [
            (sfN.Ne, GeoArgScalar(-dNe), GeoOp.DISPLACE),
            (sfN.Se, GeoArgScalar(dNe), GeoOp.DISPLACE),
        ]
    zaResult: Result[BoardGeometry] = geometry_change(zaChanges, zaGeo)
    if result_isOkCheck(zaResult):
        geoByIdx[zaIdx] = zaResult.value

    # --- Z-cascade: displace Zb and all subsequent active zones eastward ---
    zbxIdx: int
    for zbxIdx in activeIdxs[i + 1 :]:
        zbxGeo: BoardGeometry = geoByIdx[zbxIdx]
        zbxResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Z, GeoArgScalar(dWe), GeoOp.DISPLACE)],
            zbxGeo,
        )
        if result_isOkCheck(zbxResult):
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
