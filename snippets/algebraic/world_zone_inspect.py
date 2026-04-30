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

import yaml

from signalflow.board import (
    BoardGeometry,
    BoardKernel,
    BoardWorldMaterializedSolution,
    BoardZone,
)
from signalflow.board.board import Board
from signalflow.board.geometry.world_resolver import (
    WorldChainResolution,
    WorldGeometryResolver,
)
from signalflow.board.solver_runtime import BoardSolver
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
        print(
            f"Error: invalid zone spec '{_spec}'. "
            "Use col,row format (e.g. 1,1)."
        )
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
    print("      --run-snippet snippets/algebraic/world_zone_inspect.py \\")
    print(f"      --zones {args.zones} --geometry")
    print(f"  uv run python -m signalflow {_yaml_path} \\")
    print("      --run-snippet snippets/algebraic/world_zone_inspect.py \\")
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
                f"(1,{requestedIdxs[_i + 1]}). Zones must be consecutive "
                "(no gaps)."
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
# 3. Build per-zone geometries + solver artifacts (all active zones)
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
# 4. Full harmonization + materialization (all active zones)
# ---------------------------------------------------------------------------

worldResolution: WorldChainResolution = (
    WorldGeometryResolver.harmonized_chain_build(geoByIdx)
)
wOffsets: dict[int, int] = worldResolution.wOffsetsByIndex

worldMaterialized: BoardWorldMaterializedSolution = (
    BoardWorldMaterializedSolution.fromResolvedChain_build(
        boardByIndex=boardByIdx,
        solverByIndex=solverByIdx,
        resolution=worldResolution,
    )
)

# ---------------------------------------------------------------------------
# 5. Re-origin output to the leftmost requested zone
# ---------------------------------------------------------------------------

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
    print(worldMaterialized.geometry_sprint(requestedIdxs, legend_show=True))

# --- wiring view (combined world canvas, listed zones only, re-originated) ---
if args.wiring:
    print(worldMaterialized.wiring_sprint(requestedIdxs))
