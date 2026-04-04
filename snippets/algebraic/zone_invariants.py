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
from signalflow.board.doctrine import BoardAreaGeometry, BoardGeometrySpec
from signalflow.board.invariants import ZoneSymbolicInvariants
from signalflow.board.types import BoardSense
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
# ctx is the SignalFlowContext provided by the SignalFlow REPL environment
boardZone: BoardZone = ctx.zones.zone_get(columnIndex, rowIndex)  # type: ignore
zoneId: RoutingZoneId = boardZone.routingZoneId

# BoardZone is a wrapper; rawProvider() returns a Result[RoutingZone]
rawZoneResult: Result[RoutingZone] = boardZone.rawProvider()  # type: ignore
if not result_isOkCheck(rawZoneResult):
    print("error: failed to build raw routing zone from kernel")
    sys.exit(1)
rawZone: RoutingZone = rawZoneResult.value  # type: ignore[union-attr]

print(f"--- SYMBOLIC INVARIANTS REPORT [Zone {zoneId.id}] ---")

# 3. Derive invariants from circuit document + placed zone
invariants: ZoneSymbolicInvariants = ZoneSymbolicInvariants.build(
    circuitDocument=ctx.circuitDocument,  # type: ignore
    routingZone=rawZone,
    assignmentSet=ctx.routingZoneAssignmentSet,  # type: ignore
)
print(invariants.invariants_sprint())

# 4. Policy-default spec (singleton-sourced defaults; intra solver fields = 0)
geometrySpec: BoardGeometrySpec = BoardGeometrySpec()

print("\n--- GEOMETRY SPEC (policy defaults) ---")
print(geometrySpec.areas_sprint())

# 5. Lift invariants into the spec so intra solver-derived fields are populated
circuitSpec: BoardGeometrySpec = geometrySpec.with_invariants(invariants)

print("\n--- GEOMETRY SPEC (circuit-lifted) ---")
print(circuitSpec.areas_sprint())

# 6. Show the generative stack (WTE) using the circuit-lifted spec
print("\n--- GENERATIVE STACK ANALYSIS (WTE, circuit-lifted) ---")
generativeLayout: list[BoardAreaGeometry] = circuitSpec.layout_build(
    BoardSense.WEST_TO_EAST, xAnchor=0, intraWidth=0
)
areaGeometry: BoardAreaGeometry
for areaGeometry in generativeLayout:
    print(areaGeometry.span_sprint())
