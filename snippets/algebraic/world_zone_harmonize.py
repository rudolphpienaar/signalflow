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
from signalflow.engine import context_buildFromDocument
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import CircuitDocument, Result, result_isOkCheck
from signalflow.models.calling_stack import (
    CallingStack,
    callingStackResult_buildFromCircuitDocument,
)
from signalflow.notation.sfn import sfN

# ---------------------------------------------------------------------------
# 1. Load context
# ---------------------------------------------------------------------------

with open(source_yaml) as handle:  # type: ignore[name-defined]  # noqa: F821
    documentDict: dict[str, object] = yaml.safe_load(handle)

contextResult: Result[SignalFlowContext] = context_buildFromDocument(documentDict)
if not result_isOkCheck(contextResult):
    print("Error: failed to build SignalFlowContext.")
    sys.exit(1)
ctx: SignalFlowContext = contextResult.value

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
# 4. Collect active zones in west-to-east order (col=1..N, row=1)
#    Zones without an intra kernel are skipped.
# ---------------------------------------------------------------------------

activeCols: list[int] = []
kernelByCol: dict[int, BoardKernel] = {}

colIdx: int
for colIdx in range(1, numPairs + 2):
    bz: BoardZone = ctx.zones.zone_get(colIdx, 1)
    k: BoardKernel | None = bz.kernel_get("intra")
    if k is not None:
        activeCols.append(colIdx)
        kernelByCol[colIdx] = k

# ---------------------------------------------------------------------------
# 5. Snapshot original geometries before any mutation
# ---------------------------------------------------------------------------

geoByCol: dict[int, BoardGeometry] = {
    col: kernelByCol[col].board_get().geometry_get() for col in activeCols
}
beforeByCol: dict[int, BoardGeometry] = dict(geoByCol)

# ---------------------------------------------------------------------------
# 6. Harmonize each adjacent pair (Za, Zb)
# ---------------------------------------------------------------------------

print(f"--- WORLD ZONE HARMONIZATION: {source_yaml} ---")  # type: ignore[name-defined]  # noqa: F821
print()
print(
    f"bands: {bandCount}  pairs: {numPairs}"
    f"  active zones: {activeCols}"
)
print()
print("--- SEAM OPERATIONS ---")
print()

i: int
for i in range(len(activeCols) - 1):
    zaCol: int = activeCols[i]
    zbCol: int = activeCols[i + 1]
    zaGeo: BoardGeometry = geoByCol[zaCol]
    zbGeo: BoardGeometry = geoByCol[zbCol]

    dWe: int = _span_get(zbGeo, sfN.We, horizontal=True)
    dNe: int = _span_get(zbGeo, sfN.Ne, horizontal=False)

    print(f"  seam ({zaCol},1)→({zbCol},1)  dWe={dWe}  dNe={dNe}")

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
        geoByCol[zaCol] = zaResult.value

    # --- Z-cascade: displace Zb and all subsequent active zones eastward ---
    # Z anchor: _anchorDeltas_resolve returns (delta, 0) → horizontal only
    zbxCol: int
    for zbxCol in activeCols[i + 1 :]:
        zbxGeo: BoardGeometry = geoByCol[zbxCol]
        zbxResult: Result[BoardGeometry] = geometry_change(
            [(sfN.Z, GeoArgScalar(dWe), GeoOp.DISPLACE)],
            zbxGeo,
        )
        if result_isOkCheck(zbxResult):
            geoByCol[zbxCol] = zbxResult.value

print()

# ---------------------------------------------------------------------------
# 7. Before / after display per zone
# ---------------------------------------------------------------------------

col: int
for col in activeCols:
    print(f"--- ZONE ({col},1) BEFORE ---")
    print()
    print(beforeByCol[col].geometry_sprint(legend_show=False))
    print()
    print(f"--- ZONE ({col},1) AFTER  ---")
    print()
    print(geoByCol[col].geometry_sprint(legend_show=False))
    print()
