# ruff: noqa: F821
"""Inspect symbolic invariants and generative spec for a specific zone.

Usage from CLI:
    uv run python -m signalflow examples/hub.yaml \
        --run-snippet snippets/algebraic/zone_invariants.py -- --zone 1,1

Run from the REPL with:
    load("snippets/algebraic/zone_invariants.py")
"""

from __future__ import annotations

# Standard library
import argparse
import sys

# Local
from signalflow.board.doctrine import (
    BoardAreaGeometry,
    BoardGeometrySpec,
    ZoneSymbolicInvariants,
)
from signalflow.board.zone_runtime import BoardZone
from signalflow.models import (
    Result,
    RoutingZone,
    RoutingZoneId,
    result_isOkCheck,
)

# 1. Parse CLI arguments for the zone coordinate
parser: argparse.ArgumentParser = argparse.ArgumentParser(
    description="Zone invariant report."
)
parser.add_argument("--zone", default="1,1", help="Zone coordinate as 'col,row'")
# sys.argv is patched by the engine to contain only the snippet's args
args: argparse.Namespace = parser.parse_known_args(sys.argv[1:])[0]

try:
    colStr, rowStr = args.zone.split(",")
    columnIndex: int = int(colStr)
    rowIndex: int = int(rowStr)
except ValueError:
    print(f"Error: invalid zone coordinate format '{args.zone}'. Use 'col,row'.")
    sys.exit(1)

# 2. Access symbolic facts from REPL-injected objects
# ctx is the NewEngineDebugContext provided by the SignalFlow REPL environment
boardZone: BoardZone = ctx.zones.zone_get(columnIndex, rowIndex)  # type: ignore
zoneId: RoutingZoneId = boardZone.routingZoneId

# BoardZone is a wrapper, we need the raw RoutingZone for the obligation facts
# rawProvider() returns a Result[RoutingZone]
rawZoneResult: Result[RoutingZone] = boardZone.rawProvider()  # type: ignore
if not result_isOkCheck(rawZoneResult):
    print("error: failed to build raw routing zone from kernel")
    sys.exit(1)
rawZone: RoutingZone = rawZoneResult.value

print(f"--- SYMBOLIC INVARIANTS REPORT [Zone {zoneId.id}] ---")

# 3. Extract authoritative invariants directly from YAML and symbolic assignments
symbolicInvariants: ZoneSymbolicInvariants = ZoneSymbolicInvariants.build(
    circuitDocument=ctx.circuitDocument,
    routingZone=rawZone,
    obligationSet=ctx.routeObligationSet,
    assignmentSet=ctx.routingZoneAssignmentSet,
    moduleBoxPadding=3,  # As specified in hub.yaml
)

print(f"Max Label Length: {symbolicInvariants.maxLabelLength}")
print(f"Doctrinal Fan Span: {symbolicInvariants.doctrinalFanSpan}")
print("\nNatural Module Widths:")
for moduleName, naturalWidth in symbolicInvariants.moduleWidthsByName.items():
    print(f"  {moduleName:20}: {naturalWidth} columns")

# 4. Build the generative Spec from these invariants
geometrySpec: BoardGeometrySpec = BoardGeometrySpec.build(
    invariants=symbolicInvariants, courtyardSpan=10
)

print("\n--- GENERATIVE SPEC ---")
print(geometrySpec.areas_sprint())

# 5. Show the authoritative generative stack (WTE)
print("\n--- GENERATIVE STACK ANALYSIS (WTE) ---")
# Use a logical anchor of 0 for diagnostic clarity
generativeLayout: list[BoardAreaGeometry] = geometrySpec.wteLayout_build(xAnchor=0)
areaGeometry: BoardAreaGeometry
for areaGeometry in generativeLayout:
    print(areaGeometry.span_sprint())
