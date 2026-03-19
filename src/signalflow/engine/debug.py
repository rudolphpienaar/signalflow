"""Debug context and interactive REPL for the new SignalFlow engine.

This module is the bridge between the internal new-engine pipeline and an
operator-facing debugging surface. It materializes the same staged models used
by the engine, then exposes them through curated interactive views instead of
leaking the raw object graph directly into the REPL.
"""

from __future__ import annotations

import builtins
import code
import os
import re
import sys
from contextlib import suppress
from dataclasses import dataclass, is_dataclass
from pprint import pformat

from signalflow.config import (
    SignalFlowConfig,
    signalFlowConfigResult_buildFromDocumentDict,
)
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipId,
    ChipInternalSolvedRouteSet,
    ChipPlacement,
    ChipRef,
    ChipTerminalSide,
    CircuitDocument,
    Diagnostic,
    GridCoord,
    Result,
    RouteObligationSet,
    RoutingZone,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneGridSolvedRouteSet,
    RoutingZoneId,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    chipDrawLines_build,
    routingZoneDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.render.world import worldCanvas_render
from signalflow.routing import (
    RealizedRouteSet,
    chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet,
    realizedRouteSetResult_buildFromInterconnectSolvedRouteSet,
    realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet,
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
    routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations,
    routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations,
    routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)

try:
    import readline
    import rlcompleter
except ImportError:  # pragma: no cover - platform dependent
    readline = None
    rlcompleter = None

_HISTORY_FILE: str = os.path.expanduser("~/.signalflow_history")
_HISTORY_LENGTH: int = 1000

_ANSI_RESET: str = "\033[0m"
_ANSI_BOLD: str = "\033[1m"
_ANSI_CYAN: str = "\033[36m"
_ANSI_GREEN: str = "\033[32m"
_ANSI_YELLOW: str = "\033[33m"
_ANSI_RED: str = "\033[31m"
_ANSI_BLUE: str = "\033[34m"
_ANSI_MAGENTA: str = "\033[35m"
_ANSI_DIM: str = "\033[2m"
_ANSI_WHITE: str = "\033[97m"

_REPL_AVAILABLE_NAMES_LINES: tuple[str, ...] = (
    "  document    circuit     config      grid        assignment",
    "  chips       zones       interconnects  calls    routes",
    "  world       obligations diagnostics workflows   ctx",
    "  root_chip   root_placement",
    "  ls(obj)     tree(obj)   man(topic)  sfhelp()",
)

_REPL_HELPER_LINES: tuple[str, ...] = (
    "  chips.names_get()",
    "  chips.all_print()",
    "  chip = chips.chip_get('App.ts', 'main()')",
    "  chip = chips['App.ts:main()']",
    "  chip.title_get()",
    "  chip.size_get()",
    "  chip.terminals_get()",
    "  chip.draw()",
    "  chip.children_get()",
    "  chip.child_get(0)",
    "  zones.all_print()",
    "  zone = zones.zone_get(1, 1)",
    "  zone.placements_get()",
    "  zone.routes_get()",
    "  interconnects.all_print()",
    "  world.canvas_print()           # full chip-body + route-wire canvas",
    "  world.print('zones')",
    "  routes.zoneLocal_get()",
    "  routes.seamCrossing_get()",
    "  routes.gridLongHaul_get()",
    "  calls.outgoing_get('App.ts', 'main()')",
    "  workflows.inspectOrder_print()",
    "  workflows.status_print()",
    "  ls(chips)",
    "  ls(chip)",
    "  tree(document)",
    "  sfhelp()",
    "  man('chips')",
)

_MANUAL_BY_TOPIC: dict[str, tuple[str, ...]] = {
    "general": (
        "SignalFlow debug REPL — topics",
        "",
        "  chips         chip geometry, terminals, drawing",
        "  zones         placed routing zones and local routes",
        "  world         world grid topology",
        "  calls         circuit call edges",
        "  routes        obligations and solved route layers",
        "  interconnects inter-zone seam continuity",
        "  workflows     geometry cascade and solver operations",
        "  document      source document inspection",
        "  circuit       validated circuit graph",
        "  config        engine configuration",
        "  grid          unplaced topology grid",
        "",
        "  man()         with no argument shows this list",
        "  man('chips')  full narrative for one topic",
        "",
        "explore any live object:",
        "  ls(chips)     list chips view surface",
        "  ls(chip)      list one chip handle surface",
        "  tree(document) recursive subtree preview",
    ),
    "chips": (
        "chips — chip geometry and terminal inspection",
        "",
        "Chips are first-class objects in SignalFlow. A chip owns its identity,",
        "declared port surfaces (input_ports, output_ports), synthesized terminals,",
        "and chip-local internal wiring declarations. Chips do NOT own world placement.",
        "",
        "chip geometry is upstream layout truth: the rendered chip body (chip.draw())",
        "determines the row/column budget that any containing RoutingZone must reserve.",
        "If a chip gains a port row, its zone frame must grow to accommodate it.",
        "",
        "chips view  [chips]",
        "# The chips view is the entry point for all chip queries.",
        "# Select one chip, then stay on the handle for detailed inspection.",
        "",
        "  chips.all_get()                          # tuple[DebugChipHandle]",
        "  chips.count_get()                        # int",
        "  chips.ids_get()                          # tuple[ChipId]",
        "  chips.names_get()                        # tuple[str]  'module:func' titles",
        "  chips.root_get()                         # DebugChipHandle for root chip",
        "  chips.chip_get(moduleName, functionName) # DebugChipHandle",
        "  chips.chipByTitle_get('App.ts:main()')  # DebugChipHandle",
        "  chips['App.ts:main()']                   # DebugChipHandle (index syntax)",
        "  chips.title_get(moduleName, functionName)",
        "  chips.size_get(moduleName, functionName)      # (widthCols, heightRows)",
        "  chips.terminals_get(moduleName, functionName) # {'north':N,'south':S,...}",
        "  chips.location_get(moduleName, functionName)",
        "  chips.routes_get(moduleName, functionName)",
        "  chips.draw(moduleName, functionName)     # canonical chip box drawing",
        "  chips.render(moduleName, functionName)   # full debug summary text",
        "  chips.print(moduleName, functionName)    # print summary",
        "  chips.all_print()                        # print all chips",
        "",
        "chip handle  [chip = chips.chip_get(...)]",
        "# A chip handle is the ergonomic per-chip inspection surface.",
        "# It avoids passing moduleName/functionName into every call.",
        "",
        "  chip.title_get()        # 'module:func' string",
        "  chip.size_get()         # (widthCols, heightRows) — derived from draw()",
        "  chip.dimensions_get()   # {'widthColumns': N, 'heightRows': M}",
        "  chip.width_get()        # int",
        "  chip.height_get()       # int",
        "  chip.terminals_get()    # {'north':N, 'south':S, 'east':E, 'west':W}",
        "  chip.placement_get()    # primary ChipPlacement result",
        "  chip.location_get()     # primary location record dict",
        "  chip.locations_get()    # all location records",
        "  chip.children_get()     # tuple[DebugChipHandle] — outgoing call targets",
        "  chip.child_get(index)   # one child by call index",
        "  chip.routes_get()       # solved chip-internal routes",
        "  chip.draw()             # canonical chip box — THIS IS UPSTREAM LAYOUT TRUTH",
        "  chip.render()           # full debug summary",
        "  chip.print()            # print summary",
        "  chip.raw_get()          # raw Result[Chip]",
        "",
        "terminal synthesis rule",
        "  input_ports  signal -> WEST terminal",
        "  input_ports  return -> WEST terminal",
        "  output_ports signal -> EAST terminal",
        "  output_ports return -> EAST terminal (inward arrow in draw())",
        "",
        "  Same name on same wall deduplicates to one terminal.",
        "  chip.draw() uses T-junction glyphs where wires meet the wall.",
    ),
    "zones": (
        "zones — placed routing zones and local route inspection",
        "",
        "A RoutingZone is the atomic local routing block. It owns chip placement",
        "(not chip identity), the zone's outer frame, and all explicit subregion",
        "geometry (CHIP_TERMINAL, INTRA_ROUTING_*, INTER_ROUTING_* bands).",
        "",
        "Zone geometry is DERIVED from chip geometry — a zone's frame is the",
        "smallest rectangle that can contain all its placed chips plus routing",
        "subregions. If chips grow, the zone must grow with them.",
        "",
        "No chip may appear in more than one zone.",
        "",
        "zones view  [zones]",
        "",
        "  zones.all_get()                  # tuple[DebugZoneHandle]",
        "  zones.count_get()                # int",
        "  zones.ids_get()                  # tuple[RoutingZoneId]",
        "  zones.zone_get(columnIndex, rowIndex)       # DebugZoneHandle",
        "  zones.zoneForChip_get(moduleName, functionName)  # owning zone handle",
        "  zones.placements_get(columnIndex, rowIndex) # chip placements in zone",
        "  zones.routes_get(columnIndex, rowIndex)     # zone-local solved routes",
        "  zones.render(columnIndex, rowIndex)         # full debug summary",
        "  zones.print(columnIndex, rowIndex)          # print summary",
        "  zones.routes_render(columnIndex, rowIndex)  # route geometry text",
        "  zones.routes_print(columnIndex, rowIndex)   # print route geometry",
        "  zones.all_print()                           # print all zones",
        "",
        "zone handle  [zone = zones.zone_get(1, 1)]",
        "",
        "  zone.id_get()           # RoutingZoneId",
        "  zone.sense_get()        # 'west_to_east' | 'north_to_south'",
        "  zone.placements_get()   # chip placements",
        "  zone.routes_get()       # solved zone-local routes",
        "  zone.render()           # full debug summary",
        "  zone.print()",
        "  zone.routes_render()    # route geometry",
        "  zone.routes_print()",
        "  zone.raw_get()          # raw Result[RoutingZone]",
        "",
        "current limitation",
        "  Zone frames are currently sized from a terminal-count formula,",
        "  NOT from real chip render geometry. Use workflows.status_print()",
        "  to see the current state and what the cascade re-solve will fix.",
    ),
    "world": (
        "world — world grid topology",
        "",
        "RoutingZoneGrid is the world topology. It places zones in a 2D grid,",
        "places interconnects between neighboring zones, and owns macro route",
        "path planning for wires that cross more than one zone.",
        "",
        "The world grid is regular: every zone in a column shares the same width,",
        "every zone in a row shares the same height. Zone sizes are normalized",
        "to the largest zone per row/column.",
        "",
        "world view  [world]",
        "",
        "  world.size_get()              # GridCoord(columns, rows)",
        "  world.canvas_render()         # chip bodies + route wires (string)",
        "  world.canvas_print()          # print chip bodies + route wires",
        "  world.draw_render()           # zone schematic (chip names, no bodies)",
        "  world.draw_print()            # print zone schematic",
        "  world.render(style='zones')   # text rendering",
        "  world.render(style='placements')",
        "  world.render(style='routes')",
        "  world.print(style='zones')    # print",
        "  world.print(style='placements')",
        "  world.print(style='routes')",
        "",
        "canvas vs schematic",
        "  world.canvas_print()  — composite: real chip bodies at terminal",
        "    region positions with route wire glyphs overlaid.  This is the",
        "    authoritative visual output of the new engine.",
        "  world.draw_print()    — schematic: chip names in abstract zone",
        "    boxes.  Useful for debugging zone topology without chip geometry.",
        "",
        "current simple regime",
        "  west_to_east with no explicit grid -> 1 x (callingDepth-1) world",
        "  zones consumed in serpentine row-major order",
    ),
    "calls": (
        "calls — circuit call edges",
        "",
        "The circuit graph models chips as nodes and calls as directed edges.",
        "Repeated references to the same (module, func) pair resolve to ONE",
        "canonical chip with multiple incoming call edges — not cloned nodes.",
        "",
        "calls view  [calls]",
        "",
        "  calls.all_get()                         # all canonical call edges",
        "  calls.count_get()                       # int",
        "  calls.outgoing_get(moduleName, functionName)  # outgoing edges for chip",
        "  calls.incoming_get(moduleName, functionName)  # incoming edges for chip",
    ),
    "routes": (
        "routes — obligations and solved route layers",
        "",
        "Routes are solved in a tiered pipeline. Each tier builds on the previous.",
        "The route view spans both the obligation (what needs to happen) and the",
        "solved (what has been realized) layers so you can compare them.",
        "",
        "Tier 1 — chip-internal:  routes inside one chip's body",
        "Tier 2 — zone-local:     routes between chips in the same zone",
        "Tier 3 — seam-crossing:  routes that cross one zone boundary",
        "Tier 4 — grid long-haul: routes that cross multiple zones",
        "",
        "routes view  [routes]",
        "",
        "  routes.callObligations_get()             # all call-route obligations",
        "  routes.chipInternalObligations_get()     # chip-internal obligations",
        "  routes.chipInternal_get()                # solved chip-internal routes",
        "  routes.zoneLocal_get()                   # solved zone-local routes",
        "  routes.seamCrossing_get()                # solved seam-crossing routes",
        "  routes.gridLongHaul_get()                # solved grid long-haul routes",
        "  routes.forChip_get(moduleName, functionName)          # chip-internal routes",
        "  routes.zoneLocalForChip_get(moduleName, functionName) # zone-local for chip",
        "  routes.seamForChip_get(moduleName, functionName)      # seam routes for chip",
        "  routes.gridLongHaulForChip_get(moduleName, functionName)",
        "  routes.forZone_get(columnIndex, rowIndex)  # zone-local routes in one zone",
    ),
    "interconnects": (
        "interconnects — inter-zone seam continuity",
        "",
        "A RoutingZoneInterconnect connects exactly two neighboring zones and",
        "mediates wire continuity at the zone boundary. It is NOT a routing engine",
        "itself — it owns the seam geometry and the handoff points between zones.",
        "",
        "Seam geometry depends on zone frames. If a zone grows (due to normalization),",
        "all interconnects touching that zone must re-solve their handoff geometry.",
        "",
        "interconnects view  [interconnects]",
        "",
        "  interconnects.all_get()          # tuple[DebugInterconnectHandle]",
        "  interconnects.count_get()        # int",
        "  interconnects.interconnect_get(srcCol, srcRow, dstCol, dstRow)",
        "  interconnects.routes_get(srcCol, srcRow, dstCol, dstRow)",
        "  interconnects.render(srcCol, srcRow, dstCol, dstRow)",
        "  interconnects.print(srcCol, srcRow, dstCol, dstRow)",
        "  interconnects.all_print()        # print all interconnects",
        "",
        "interconnect handle  [ic = interconnects.interconnect_get(1,1, 2,1)]",
        "",
        "  ic.endpoints_get()   # (sourceGridCoord, destinationGridCoord)",
        "  ic.routes_get()      # solved seam routes",
        "  ic.render()          # full debug summary",
        "  ic.print()",
        "  ic.raw_get()         # raw Result[RoutingZoneInterconnect]",
    ),
    "workflows": (
        "workflows — geometry cascade and solver operations",
        "",
        "Workflows are multi-step operations that cross layer boundaries.",
        "The canonical cascade is:",
        "",
        "  chip geometry (fixed by chipDrawLines_build)",
        "      |",
        "  zone natural frame (derived from chips)",
        "      |",
        "  grid normalization (max per row/column)",
        "      |  if any zone grew:",
        "  re-solve chip placement + zone routing + seam geometry",
        "      |  until stable",
        "  world geometry is finalized",
        "",
        "workflows view  [workflows]",
        "",
        "  workflows.status_print()               # current geometry derivation state",
        "  workflows.inspectOrder_print()         # canonical chip->zone->seam->world order",
        "  workflows.chipGeometryPush_run()       # [stub] re-derive zones from chips",
        "  workflows.zonesNormalize_run()         # [stub] normalization cascade",
        "  workflows.zoneRecalculate_run(col,row) # [stub] recalculate one zone",
        "",
        "typical REPL workflow (current — manual inspection):",
        "  1. chips.all_print()              # verify chip geometry is correct",
        "  2. chip = chips.chip_get(...)     # pick one chip",
        "  3. chip.draw()                   # inspect canonical drawing",
        "  4. zones.all_print()             # inspect current zone frames",
        "  5. zone = zones.zone_get(1, 1)  # pick one zone",
        "  6. zone.placements_get()         # see what chips are placed where",
        "  7. interconnects.all_print()     # inspect seam geometry",
        "  8. world.print('zones')          # see full world grid",
        "",
        "when chipGeometryPush_run() is implemented:",
        "  workflows.chipGeometryPush_run()   # push chip geometry into zone frames",
        "  workflows.zonesNormalize_run()     # normalize + cascade re-solve",
        "  workflows.status_print()           # verify all zones are chip-driven",
        "  world.print('zones')              # final world geometry",
    ),
}


@dataclass(frozen=True)
class _DebugBuildArtifacts:
    """Intermediate debug-pipeline artifacts before the context wrapper.

    The debug REPL builds the same staged engine objects that the render path
    consumes. This private bundle keeps those intermediate values grouped so the
    top-level builder does not become a long imperative god-function.
    """

    circuitDocument: CircuitDocument
    signalFlowConfig: SignalFlowConfig
    routingZoneGrid: RoutingZoneGrid
    routingZoneAssignmentSet: RoutingZoneAssignmentSet
    placedRoutingZoneGrid: RoutingZoneGrid
    routeObligationSet: RouteObligationSet
    chipInternalSolvedRouteSet: ChipInternalSolvedRouteSet
    routingZoneLocalSolvedRouteSet: RoutingZoneLocalSolvedRouteSet
    routingZoneInterconnectSolvedRouteSet: RoutingZoneInterconnectSolvedRouteSet
    routingZoneGridSolvedRouteSet: RoutingZoneGridSolvedRouteSet


@dataclass(frozen=True)
class DebugChipHandle:
    """Interactive handle for one canonical chip.

    A handle is the ergonomic REPL-friendly layer over the canonical `ChipId`.
    It avoids repeatedly passing `moduleName` and `functionName` into every
    inspection helper and keeps tab completion focused on chip-specific
    questions rather than raw dataclass internals.
    """

    debugContext: NewEngineDebugContext
    chipId: ChipId

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "title_get",
            "size_get",
            "dimensions_get",
            "width_get",
            "height_get",
            "terminals_get",
            "placement_get",
            "location_get",
            "locations_get",
            "children_get",
            "child_get",
            "routes_get",
            "raw_get",
            "all_render",
            "all_print",
            "draw",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<chip {self.title_get()}>"

    def raw_get(self):
        """Return the raw chip lookup result."""

        return self.debugContext.chipResult_get(self.chipId)

    def title_get(self) -> str:
        """Return stable human-readable chip title."""

        return _chipTitleText_build(self.chipId)

    def size_get(self) -> tuple[int, int]:
        """Return rendered chip drawing width and height."""

        drawingLines = _chipDrawingLines_build(
            debugContext=self.debugContext,
            chipId=self.chipId,
        )
        return _textBlockSize_build(drawingLines)

    def dimensions_get(self) -> dict[str, int]:
        """Return rendered chip drawing dimensions with explicit field names."""

        width, height = self.size_get()
        return {
            "widthColumns": width,
            "heightRows": height,
        }

    def width_get(self) -> int:
        """Return rendered chip drawing width in columns."""

        return self.size_get()[0]

    def height_get(self) -> int:
        """Return rendered chip drawing height in rows."""

        return self.size_get()[1]

    def terminals_get(self) -> dict[str, int]:
        """Return terminal counts by side."""

        return self.debugContext.terminalCountsForChip_build(self.chipId)

    def placement_get(self):
        """Return the primary raw placement result."""

        return self.debugContext.placementForChipResult_get(self.chipId)

    def location_get(self):
        """Return the primary location record."""

        locations = self.locations_get()
        return locations[0] if locations else None

    def locations_get(self):
        """Return all placement/location records."""

        return self.debugContext.locationRecordsForChip_build(self.chipId)

    def routes_get(self):
        """Return solved chip-internal routes."""

        return self.debugContext.chipRoutesForChip_get(self.chipId)

    def children_get(self) -> tuple[DebugChipHandle, ...]:
        """Return canonical child chips as interactive handles."""

        outgoingCalls = (
            self.debugContext.circuitDocument.circuitCallSet.outgoingCallsForChip_get(
                self.chipId
            )
        )
        return tuple(
            DebugChipHandle(
                debugContext=self.debugContext,
                chipId=circuitCall.destinationChipRef.chipId,
            )
            for circuitCall in outgoingCalls
        )

    def child_get(self, childIndex: int) -> DebugChipHandle:
        """Return one canonical child chip handle by outgoing-call index."""

        return self.children_get()[childIndex]

    def all_render(self) -> str:
        """Render a full debug summary for this chip."""

        return self.render()

    def all_print(self) -> None:
        """Print a full debug summary for this chip."""

        self.print()

    def render(self) -> str:
        """Render one canonical chip as a readable debug summary."""

        return _chipSummaryText_build(
            debugContext=self.debugContext,
            chipId=self.chipId,
        )

    def draw(self) -> str:
        """Draw one canonical chip as a focused chip-only text artifact."""

        return "\n".join(
            _chipDrawingLines_build(
                debugContext=self.debugContext,
                chipId=self.chipId,
            )
        )

    def print(self) -> None:
        """Print one canonical chip summary."""

        _summary_print(self.render())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def title(self) -> str:
        return self.title_get()  # noqa: E704

    def size(self) -> tuple[int, int]:
        return self.size_get()  # noqa: E704

    def dimensions(self) -> dict[str, int]:
        return self.dimensions_get()  # noqa: E704

    def width(self) -> int:
        return self.width_get()  # noqa: E704

    def height(self) -> int:
        return self.height_get()  # noqa: E704

    def terminals(self) -> dict[str, int]:
        return self.terminals_get()  # noqa: E704

    def placement(self):
        return self.placement_get()  # noqa: E704

    def location(self):
        return self.location_get()  # noqa: E704

    def locations(self):
        return self.locations_get()  # noqa: E704

    def routes(self):
        return self.routes_get()  # noqa: E704

    def children(self) -> tuple[DebugChipHandle, ...]:
        return self.children_get()  # noqa: E704

    def child(self, childIndex: int) -> DebugChipHandle:
        return self.child_get(childIndex)  # noqa: E704

    def render_all(self) -> str:
        return self.all_render()  # noqa: E704

    def print_all(self) -> None:
        return self.all_print()  # noqa: E704


@dataclass(frozen=True)
class DebugChipView:
    """Interactive inspection view over canonical chips.

    This view is the entrypoint for chip lookup and chip-oriented queries in the
    REPL. It intentionally wraps the raw `CircuitChipSet` so operators see a
    stable, compact command surface instead of the full model vocabulary.
    """

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "all_get",
            "count_get",
            "ids_get",
            "names_get",
            "all_render",
            "all_print",
            "root_get",
            "chip_get",
            "chipByTitle_get",
            "title_get",
            "size_get",
            "terminals_get",
            "placement_get",
            "location_get",
            "locations_get",
            "routes_get",
            "draw",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<chips>"

    def all_get(self) -> tuple[DebugChipHandle, ...]:
        """Return all canonical chips as interactive handles."""

        return tuple(
            DebugChipHandle(debugContext=self.debugContext, chipId=chip.chipId)
            for chip in self.debugContext.chips_getAll()
        )

    def count_get(self) -> int:
        """Return canonical chip count."""

        return len(self.all_get())

    def ids_get(self) -> tuple[ChipId, ...]:
        """Return all canonical chip ids."""

        return self.debugContext.chipIds_getAll()

    def names_get(self) -> tuple[str, ...]:
        """Return stable human-readable chip names."""

        return tuple(
            f"{chipId.moduleName}:{chipId.functionName}" for chipId in self.ids_get()
        )

    def all_render(self) -> str:
        """Render readable summaries for all canonical chips in stored order."""

        return "\n\n".join(
            self.render(chipId.moduleName, chipId.functionName)
            for chipId in self.ids_get()
        )

    def all_print(self) -> None:
        """Print readable summaries for all canonical chips in stored order."""

        _summary_print(self.all_render())

    def root_get(self):
        """Return the canonical root chip as an interactive handle."""

        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=self.debugContext.circuitDocument.rootChipRef.chipId,
        )

    def chip_get(self, moduleName: str, functionName: str) -> DebugChipHandle:
        """Return an interactive handle for one canonical chip."""

        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def chipByTitle_get(self, chipTitle: str) -> DebugChipHandle:
        """Return an interactive handle from one `module:function` title."""

        moduleName, functionName = _chipTitleParts_build(chipTitle)
        return self.chip_get(moduleName, functionName)

    def __getitem__(self, chipTitle: str) -> DebugChipHandle:
        """Return an interactive handle using index syntax."""

        return self.chipByTitle_get(chipTitle)

    def title_get(self, moduleName: str, functionName: str) -> str:
        """Return stable human-readable title for one canonical chip."""

        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return _chipTitleText_build(chipId)

    def size_get(self, moduleName: str, functionName: str) -> tuple[int, int]:
        """Return rendered chip drawing width and height."""

        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        drawingLines = _chipDrawingLines_build(
            debugContext=self.debugContext,
            chipId=chipId,
        )
        return _textBlockSize_build(drawingLines)

    def terminals_get(self, moduleName: str, functionName: str) -> dict[str, int]:
        """Return terminal counts by side for one canonical chip."""

        return self.debugContext.terminalCountsForChip_build(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def placement_get(self, moduleName: str, functionName: str):
        """Get placement result for one canonical chip."""

        return self.debugContext.placementForChipResult_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def location_get(self, moduleName: str, functionName: str):
        """Return the primary placement/location record for one canonical chip."""

        locations = self.locations_get(moduleName, functionName)
        return locations[0] if locations else None

    def locations_get(self, moduleName: str, functionName: str):
        """Return all placement/location records for one canonical chip."""

        return self.debugContext.locationRecordsForChip_build(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def routes_get(self, moduleName: str, functionName: str):
        """Get solved chip-internal routes for one canonical chip."""

        return self.debugContext.chipRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def render(self, moduleName: str, functionName: str) -> str:
        """Render one canonical chip as a readable debug summary."""

        return _chipSummaryText_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def draw(self, moduleName: str, functionName: str) -> str:
        """Draw one canonical chip as a focused chip-only text artifact."""

        return "\n".join(
            _chipDrawingLines_build(
                debugContext=self.debugContext,
                chipId=ChipId(moduleName=moduleName, functionName=functionName),
            )
        )

    def print(self, moduleName: str, functionName: str) -> None:
        """Print one canonical chip as a readable debug summary."""

        _summary_print(self.render(moduleName, functionName))

    # --- backward-compatible aliases (not in __dir__) ---
    def all(self) -> tuple[DebugChipHandle, ...]:
        return self.all_get()  # noqa: E704

    def count(self) -> int:
        return self.count_get()  # noqa: E704

    def ids(self) -> tuple[ChipId, ...]:
        return self.ids_get()  # noqa: E704

    def names(self) -> tuple[str, ...]:
        return self.names_get()  # noqa: E704

    def render_all(self) -> str:
        return self.all_render()  # noqa: E704

    def print_all(self) -> None:
        return self.all_print()  # noqa: E704

    def root(self):
        return self.root_get()  # noqa: E704

    def at(self, moduleName: str, functionName: str) -> DebugChipHandle:
        return self.chip_get(moduleName, functionName)  # noqa: E704

    def by_title(self, chipTitle: str) -> DebugChipHandle:
        return self.chipByTitle_get(chipTitle)  # noqa: E704

    def get(self, moduleName: str, functionName: str):
        return self.chip_get(moduleName, functionName)  # noqa: E704

    def title(self, moduleName: str, functionName: str) -> str:
        return self.title_get(moduleName, functionName)  # noqa: E704

    def size(self, moduleName: str, functionName: str) -> tuple[int, int]:
        return self.size_get(moduleName, functionName)  # noqa: E704

    def terminals(self, moduleName: str, functionName: str) -> dict[str, int]:
        return self.terminals_get(moduleName, functionName)  # noqa: E704

    def placement(self, moduleName: str, functionName: str):
        return self.placement_get(moduleName, functionName)  # noqa: E704

    def location(self, moduleName: str, functionName: str):
        return self.location_get(moduleName, functionName)  # noqa: E704

    def locations(self, moduleName: str, functionName: str):
        return self.locations_get(moduleName, functionName)  # noqa: E704

    def routes(self, moduleName: str, functionName: str):
        return self.routes_get(moduleName, functionName)  # noqa: E704


@dataclass(frozen=True)
class DebugZoneRegionHandle:
    """Interactive handle for one region inside a placed routing zone."""

    routingZoneRegionId: RoutingZoneRegionId
    routingZoneRegionFrame: RoutingZoneRegionFrame

    def __dir__(self) -> list[str]:
        return ["kind", "side", "name", "frame"]

    def __repr__(self) -> str:
        f = self.routingZoneRegionFrame
        return (
            f"<area {self.name}"
            f"  col={f.horizontalStart}..{f.horizontalEnd_calculate()}"
            f"  row={f.verticalStart}..{f.verticalEnd_calculate()}>"
        )

    @property
    def kind(self) -> str:
        """Region kind string (e.g. 'chip_terminal')."""
        return self.routingZoneRegionId.routingZoneRegionKind.value

    @property
    def side(self) -> str | None:
        """Cardinal side string (e.g. 'west') or None for unsided regions."""
        s = self.routingZoneRegionId.routingZoneRegionSide
        return s.value if s is not None else None

    @property
    def name(self) -> str:
        """Canonical 'side/kind' key (or just 'kind' for unsided regions)."""
        return f"{self.side}/{self.kind}" if self.side else self.kind

    @property
    def frame(self) -> str:
        """Human-readable geometry: 'col=start..end  row=start..end'."""
        f = self.routingZoneRegionFrame
        return (
            f"col={f.horizontalStart}..{f.horizontalEnd_calculate()}"
            f"  row={f.verticalStart}..{f.verticalEnd_calculate()}"
            f"  span=({f.horizontalSpan}w x {f.verticalSpan}h)"
        )

    @property
    def geometry(self) -> RoutingZoneRegionFrame:
        """Raw RoutingZoneRegionFrame."""
        return self.routingZoneRegionFrame


_REGION_SYMBOLS: dict[str, str] = {
    "west/inter_routing_longitude": "▌",
    "west/inter_routing_fan_in_out": "🬗",
    "west/chip_terminal": "░",
    "west/intra_routing_fan_in_out": "🬤",
    "west/intra_routing_longitude": "🭲",
    "east/intra_routing_longitude": "🭵",
    "east/intra_routing_fan_in_out": "🮥",
    "east/chip_terminal": "▒",
    "east/inter_routing_fan_in_out": "🮤",
    "east/inter_routing_longitude": "▐",
    "north/inter_routing_latitude": "🭶",
    "north/inter_routing_fan_in_out": "🮦",
    "north/chip_terminal": "▓",
    "north/intra_routing_fan_in_out": "🮧",
    "north/intra_routing_latitude": "🭷",
    "south/intra_routing_latitude": "🭺",
    "south/intra_routing_fan_in_out": "🮪",
    "south/chip_terminal": "█",
    "south/inter_routing_fan_in_out": "🮭",
    "south/inter_routing_latitude": "🭻",
}


def _regionDrawGrid_build(
    regions: tuple,
    labels: list[str],
    mode: str,
) -> list[str]:
    """Build a filled ASCII grid showing each region as a labeled band.

    In ``pixel`` mode each display cell is one world unit (1:1).
    In ``schematic`` mode narrow bands are widened to a minimum so labels fit.
    Smaller (inner) regions overwrite larger (outer) ones where they overlap.
    """

    if not regions:
        return []

    colBreaks: list[int] = sorted(
        {
            v
            for r in regions
            for v in (
                r.routingZoneRegionFrame.horizontalStart,
                r.routingZoneRegionFrame.horizontalEnd_calculate(),
            )
        }
    )
    rowBreaks: list[int] = sorted(
        {
            v
            for r in regions
            for v in (
                r.routingZoneRegionFrame.verticalStart,
                r.routingZoneRegionFrame.verticalEnd_calculate(),
            )
        }
    )

    if mode == "schematic":
        _minW, _maxW, _minH = 3, 8, 1
        colWidths = [
            max(_minW, min(_maxW, colBreaks[i + 1] - colBreaks[i]))
            for i in range(len(colBreaks) - 1)
        ]
        rowHeights = [
            max(_minH, rowBreaks[i + 1] - rowBreaks[i])
            for i in range(len(rowBreaks) - 1)
        ]
    else:
        colWidths = [colBreaks[i + 1] - colBreaks[i] for i in range(len(colBreaks) - 1)]
        rowHeights = [
            rowBreaks[i + 1] - rowBreaks[i] for i in range(len(rowBreaks) - 1)
        ]

    colStarts: list[int] = [0]
    for w in colWidths:
        colStarts.append(colStarts[-1] + w)
    rowStarts: list[int] = [0]
    for h in rowHeights:
        rowStarts.append(rowStarts[-1] + h)

    totalCols = colStarts[-1]
    totalRows = rowStarts[-1]
    grid: list[list[str]] = [[" "] * totalCols for _ in range(totalRows)]

    # Paint largest regions first; smaller (inner) overwrite on overlap.
    sortedIndexed = sorted(
        enumerate(regions),
        key=lambda ir: (
            -(
                ir[1].routingZoneRegionFrame.horizontalSpan
                * ir[1].routingZoneRegionFrame.verticalSpan
            )
        ),
    )
    for idx, region in sortedIndexed:
        f = region.routingZoneRegionFrame
        label = labels[idx]
        cbs = colBreaks.index(f.horizontalStart)
        cbe = colBreaks.index(f.horizontalEnd_calculate())
        rbs = rowBreaks.index(f.verticalStart)
        rbe = rowBreaks.index(f.verticalEnd_calculate())
        for ri in range(rbs, rbe):
            for ci in range(cbs, cbe):
                drs = rowStarts[ri]
                dre = rowStarts[ri + 1]
                dcs = colStarts[ci]
                dce = colStarts[ci + 1]
                for dr in range(drs, dre):
                    for dc in range(dcs, dce):
                        grid[dr][dc] = label

    # Column ruler (world coords at each band start).
    rulerTop: list[str] = [" "] * totalCols
    for i, worldCol in enumerate(colBreaks[:-1]):
        marker = str(worldCol % 100)
        dcs = colStarts[i]
        for ci, ch in enumerate(marker):
            if dcs + ci < totalCols:
                rulerTop[dcs + ci] = ch

    lines: list[str] = ["".join(rulerTop)]
    for row in grid:
        lines.append("".join(row))
    return lines


@dataclass(frozen=True)
class DebugZoneRegionSetHandle:
    """Interactive handle for the full set of regions in one placed zone."""

    _regions: tuple[DebugZoneRegionHandle, ...]

    def __dir__(self) -> list[str]:
        return ["draw_get", "draw_print", "draw", "info_get", "info_print", "all_get"]

    def __repr__(self) -> str:
        return f"<zone.areas  {len(self._regions)} regions>"

    def __iter__(self):
        return iter(self._regions)

    def __len__(self) -> int:
        return len(self._regions)

    def all_get(self) -> tuple[DebugZoneRegionHandle, ...]:
        """Return the raw tuple of all region handles."""
        return self._regions

    def info_get(self) -> str:
        """Return a formatted string with every property of every area."""
        lines: list[str] = []
        handle: DebugZoneRegionHandle
        for handle in self._regions:
            lines.append(f"  {handle.name}")
            lines.append(f"    kind     : {handle.kind}")
            lines.append(f"    side     : {handle.side}")
            lines.append(f"    frame    : {handle.frame}")
            lines.append(f"    geometry : {handle.geometry}")
        return "\n".join(lines)

    def info_print(self) -> None:
        """Print every property of every area."""
        _summary_print(self.info_get())

    def draw_get(self, mode: str = "pixel") -> str:
        """Return a labelled ASCII fill-grid of every region.

        Args:
            mode: ``'pixel'`` (default) — one display cell per world unit;
                  ``'schematic'`` — narrow bands widened to minimum 3 chars.

        Returns:
            Multi-line string: column ruler, filled grid, then legend.
        """
        regions = self._regions
        if not regions:
            return "<no regions>"

        labels = [_REGION_SYMBOLS.get(region.name, "?") for region in regions]
        gridLines = _regionDrawGrid_build(regions, labels, mode)

        legendLines: list[str] = ["", "legend:"]
        for i, region in enumerate(regions):
            legendLines.append(f"  {labels[i]}   {region.name}  [{region.frame}]")

        return "\n".join(gridLines + legendLines)

    def draw_print(self, mode: str = "pixel") -> None:
        """Print the labelled region fill-grid."""
        _summary_print(self.draw_get(mode))

    def draw(self, mode: str = "pixel") -> None:
        """Print the labelled region fill-grid (alias for draw_print)."""
        self.draw_print(mode)


@dataclass(frozen=True)
class DebugZoneHandle:
    """Interactive handle for one placed routing zone."""

    debugContext: NewEngineDebugContext
    routingZoneId: RoutingZoneId

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "areas_get",
            "area_get",
            "id_get",
            "sense_get",
            "placements_get",
            "routes_get",
            "routes_render",
            "routes_print",
            "draw_render",
            "draw_print",
            "raw_get",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<zone {self.routingZoneId.id}>"

    def raw_get(self):
        """Return the raw placed routing-zone result."""

        return self.debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            self.routingZoneId
        )

    def areas_get(self) -> DebugZoneRegionSetHandle:
        """Return all regions for this zone as a DebugZoneRegionSetHandle."""

        zoneResult = self.raw_get()
        if not result_isOkCheck(zoneResult):
            return DebugZoneRegionSetHandle(_regions=())
        return DebugZoneRegionSetHandle(
            _regions=tuple(
                DebugZoneRegionHandle(
                    routingZoneRegionId=region.routingZoneRegionId,
                    routingZoneRegionFrame=region.routingZoneRegionFrame,
                )
                for region in zoneResult.value.routingZoneRegionSet.routingZoneRegions
            )
        )

    def area_get(
        self,
        kindOrKey: str,
        side: str | None = None,
    ) -> DebugZoneRegionHandle | None:
        """Return one region by kind and optional side.

        Args:
            kindOrKey: Either a ``'side/kind'`` key (e.g. ``'west/chip_terminal'``)
                or just a kind string when ``side`` is provided separately.
            side: Optional side override (e.g. ``'west'``).  Ignored when
                ``kindOrKey`` already contains a ``/``.

        Returns:
            Matching ``DebugZoneRegionHandle``, or ``None`` if not found.
        """

        if "/" in kindOrKey:
            sidePart, kindPart = kindOrKey.split("/", 1)
        else:
            kindPart = kindOrKey
            sidePart = side

        try:
            wantKind = RoutingZoneRegionKind(kindPart)
        except ValueError:
            return None
        wantSide: RoutingZoneRegionSide | None = None
        if sidePart:
            try:
                wantSide = RoutingZoneRegionSide(sidePart)
            except ValueError:
                return None

        for handle in self.areas_get():
            if (
                handle.routingZoneRegionId.routingZoneRegionKind is wantKind
                and handle.routingZoneRegionId.routingZoneRegionSide is wantSide
            ):
                return handle
        return None

    def id_get(self):
        """Return the stable routing-zone id."""

        return self.routingZoneId

    def sense_get(self) -> str | None:
        """Return the routing sense of this placed zone when available."""

        zoneResult = self.raw_get()
        if not result_isOkCheck(zoneResult):
            return None
        return zoneResult.value.routingZoneSense.value

    def placements_get(self):
        """Return chip placements owned by this placed zone."""

        return self.debugContext.placementsForZone_get(self.routingZoneId)

    def routes_get(self):
        """Return solved zone-local routes owned by this placed zone."""

        return self.debugContext.zoneLocalRoutesForZone_get(self.routingZoneId)

    def routes_render(self) -> str:
        """Render solved local routes for this placed routing zone."""

        return _zoneRoutesText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def routes_print(self) -> None:
        """Print solved local routes for this placed routing zone."""

        _summary_print(self.routes_render())

    def draw_render(self) -> str:
        """Render a schematic ASCII drawing of this placed routing zone."""

        return _zoneDrawingLines_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def draw_print(self) -> None:
        """Print a schematic ASCII drawing of this placed routing zone."""

        _summary_print(self.draw_render())

    def render(self) -> str:
        """Render this placed routing zone as a readable debug summary."""

        return _zoneSummaryText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def print(self) -> None:
        """Print this placed routing zone as a readable debug summary."""

        _summary_print(self.render())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def id(self):
        return self.id_get()  # noqa: E704

    def sense(self) -> str | None:
        return self.sense_get()  # noqa: E704

    def placements(self):
        return self.placements_get()  # noqa: E704

    def routes(self):
        return self.routes_get()  # noqa: E704

    def render_routes(self) -> str:
        return self.routes_render()  # noqa: E704

    def print_routes(self) -> None:
        return self.routes_print()  # noqa: E704

    @property
    def areas(self) -> DebugZoneRegionSetHandle:
        return self.areas_get()  # noqa: E704


@dataclass(frozen=True)
class DebugInterconnectHandle:
    """Interactive handle for one placed routing-zone interconnect."""

    debugContext: NewEngineDebugContext
    sourceGridCoord: GridCoord
    destinationGridCoord: GridCoord

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "endpoints_get",
            "routes_get",
            "raw_get",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<interconnect {self.sourceGridCoord}->{self.destinationGridCoord}>"

    def raw_get(self):
        """Return the raw placed interconnect result."""

        return self.debugContext.placedRoutingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=self.sourceGridCoord,
            destinationGridCoord=self.destinationGridCoord,
        )

    def endpoints_get(self) -> tuple[GridCoord, GridCoord]:
        """Return the source and destination world coordinates."""

        return (self.sourceGridCoord, self.destinationGridCoord)

    def routes_get(self):
        """Return solved seam routes owned by this interconnect."""

        interconnectResult = self.raw_get()
        if not result_isOkCheck(interconnectResult):
            return ()
        return self.debugContext.interconnectRoutesForInterconnect_get(
            interconnectResult.value.routingZoneInterconnectId
        )

    def render(self) -> str:
        """Render this interconnect plus its seam routes."""

        interconnectResult = self.raw_get()
        if not result_isOkCheck(interconnectResult):
            return "interconnect\n  status: missing"
        return _interconnectSummaryText_build(
            debugContext=self.debugContext,
            routingZoneInterconnectId=interconnectResult.value.routingZoneInterconnectId,
        )

    def print(self) -> None:
        """Print this interconnect plus its seam routes."""

        _summary_print(self.render())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def endpoints(self) -> tuple[GridCoord, GridCoord]:
        return self.endpoints_get()  # noqa: E704

    def routes(self):
        return self.routes_get()  # noqa: E704


@dataclass(frozen=True)
class DebugPlacementHandle:
    """Interactive handle for one placed chip record."""

    debugContext: NewEngineDebugContext
    chipId: ChipId

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "zone_get",
            "side_get",
            "order_get",
            "worldPoint_get",
            "raw_get",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<placement {_chipTitleText_build(self.chipId)}>"

    def raw_get(self):
        """Return the raw placement result for the selected chip."""

        return self.debugContext.placementForChipResult_get(self.chipId)

    def zone_get(self):
        """Return the primary world zone for this placement."""

        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return location[0]["zone"] if location else None

    def side_get(self) -> str | None:
        """Return the terminal side used by this placement."""

        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return location[0]["terminalSide"] if location else None

    def order_get(self) -> int | None:
        """Return the order index of this placement within its terminal band."""

        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return location[0]["orderIndex"] if location else None

    def worldPoint_get(self):
        """Return the world point used for this placed chip marker."""

        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return location[0]["worldPoint"] if location else None

    def render(self) -> str:
        """Render a compact summary of this chip placement."""

        return "\n".join(
            [
                f"placement {_chipTitleText_build(self.chipId)}",
                f"  zone: {self.zone_get()}",
                f"  side: {self.side_get()}",
                f"  order: {self.order_get()}",
                f"  point: {self.worldPoint_get()}",
            ]
        )

    def print(self) -> None:
        """Print a compact summary of this chip placement."""

        _summary_print(self.render())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def zone(self):
        return self.zone_get()  # noqa: E704

    def side(self) -> str | None:
        return self.side_get()  # noqa: E704

    def order(self) -> int | None:
        return self.order_get()  # noqa: E704

    def world_point(self):
        return self.worldPoint_get()  # noqa: E704


@dataclass(frozen=True)
class DebugZoneView:
    """Interactive inspection view over placed routing zones.

    The zone view answers placement and local-routing questions against the
    placed world, not the pre-placement topology skeleton.
    """

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "all_get",
            "count_get",
            "ids_get",
            "all_render",
            "all_print",
            "zone_get",
            "zoneForChip_get",
            "placements_get",
            "routes_get",
            "routes_render",
            "routes_print",
            "draw_render",
            "draw_print",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<zones>"

    def all_get(self):
        """Return all placed routing zones."""

        return tuple(
            DebugZoneHandle(
                debugContext=self.debugContext,
                routingZoneId=routingZone.routingZoneId,
            )
            for routingZone in self.debugContext.zones_getAll()
        )

    def count_get(self) -> int:
        """Return placed routing-zone count."""

        return len(self.all_get())

    def ids_get(self):
        """Return all placed routing-zone ids."""

        return tuple(
            routingZoneHandle.routingZoneId for routingZoneHandle in self.all_get()
        )

    def all_render(self) -> str:
        """Render readable summaries for all placed routing zones."""

        return "\n\n".join(
            self.render(
                routingZoneId.id.columnIndex,
                routingZoneId.id.rowIndex,
            )
            for routingZoneId in self.ids_get()
            if isinstance(routingZoneId.id, GridCoord)
        )

    def all_print(self) -> None:
        """Print readable summaries for all placed routing zones."""

        _summary_print(self.all_render())

    def zone_get(self, columnIndex: int, rowIndex: int):
        """Return one placed routing zone handle by grid coordinate."""

        return _zoneHandle_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def zoneForChip_get(self, moduleName: str, functionName: str):
        """Return the placed routing zone handle owning one canonical chip."""

        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        zoneResult = self.debugContext.zoneOwningChipResult_get(chipId)
        if not result_isOkCheck(zoneResult):
            raise KeyError(f"No placed zone for chip {_chipTitleText_build(chipId)!r}")
        return _zoneHandle_build(
            debugContext=self.debugContext,
            routingZoneId=zoneResult.value.routingZoneId,
        )

    def placements_get(self, columnIndex: int, rowIndex: int):
        """Return placements for one placed routing zone."""

        return self.debugContext.placementsForZone_get(
            RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
        )

    def routes_get(self, columnIndex: int, rowIndex: int):
        """Return solved zone-local routes for one placed routing zone."""

        return self.debugContext.zoneLocalRoutesForZone_get(
            RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
        )

    def routes_render(self, columnIndex: int, rowIndex: int) -> str:
        """Render solved local routes for one placed routing zone."""

        return _zoneRoutesText_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def routes_print(self, columnIndex: int, rowIndex: int) -> None:
        """Print solved local routes for one placed routing zone."""

        print(self.routes_render(columnIndex, rowIndex))

    def render(self, columnIndex: int, rowIndex: int) -> str:
        """Render one placed routing zone as a readable debug summary."""

        return _zoneSummaryText_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def draw_render(self, columnIndex: int, rowIndex: int) -> str:
        """Render a schematic ASCII drawing of one placed routing zone."""

        return _zoneDrawingLines_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def draw_print(self, columnIndex: int, rowIndex: int) -> None:
        """Print a schematic ASCII drawing of one placed routing zone."""

        _summary_print(self.draw_render(columnIndex, rowIndex))

    def print(self, columnIndex: int, rowIndex: int) -> None:
        """Print one placed routing zone as a readable debug summary."""

        _summary_print(self.render(columnIndex, rowIndex))

    # --- backward-compatible aliases (not in __dir__) ---
    def all(self):
        return self.all_get()  # noqa: E704

    def count(self) -> int:
        return self.count_get()  # noqa: E704

    def ids(self):
        return self.ids_get()  # noqa: E704

    def render_all(self) -> str:
        return self.all_render()  # noqa: E704

    def print_all(self) -> None:
        return self.all_print()  # noqa: E704

    def get(self, columnIndex: int, rowIndex: int):
        return self.zone_get(columnIndex, rowIndex)  # noqa: E704

    def for_chip(self, moduleName: str, functionName: str):
        return self.zoneForChip_get(moduleName, functionName)  # noqa: E704

    def placements(self, columnIndex: int, rowIndex: int):
        return self.placements_get(columnIndex, rowIndex)  # noqa: E704

    def routes(self, columnIndex: int, rowIndex: int):
        return self.routes_get(columnIndex, rowIndex)  # noqa: E704

    def render_routes(self, columnIndex: int, rowIndex: int) -> str:
        return self.routes_render(columnIndex, rowIndex)  # noqa: E704

    def print_routes(self, columnIndex: int, rowIndex: int) -> None:
        return self.routes_print(columnIndex, rowIndex)  # noqa: E704


@dataclass(frozen=True)
class DebugGridView:
    """Interactive inspection and printing view over the placed world grid.

    This is the curated world-facing replacement for poking directly at the raw
    `RoutingZoneGrid` object in the REPL.
    """

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "size_get",
            "canvas_render",
            "canvas_print",
            "draw_render",
            "draw_print",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<world>"

    def size_get(self) -> GridCoord:
        """Return placed world grid size."""

        return self.debugContext.placedRoutingZoneGrid.gridSize

    # backward-compatible alias
    def size(self) -> GridCoord:
        return self.size_get()  # noqa: E704

    def canvas_render(self) -> str:
        """Render the full world as a chip-body + route-wire ASCII canvas."""

        return _worldCanvasText_build(self.debugContext)

    def canvas_print(self) -> None:
        """Print the full world as a chip-body + route-wire ASCII canvas."""

        _summary_print(self.canvas_render())

    def draw_render(self) -> str:
        """Render the full world as a spatial ASCII schematic of all zones."""

        return _worldDrawText_build(self.debugContext)

    def draw_print(self) -> None:
        """Print the full world as a spatial ASCII schematic of all zones."""

        _summary_print(self.draw_render())

    def render(self, style: str = "zones") -> str:
        """Render the placed world grid in one named debug style."""

        return _gridText_build(
            debugContext=self.debugContext,
            style=style,
        )

    def print(self, style: str = "zones") -> None:
        """Print the placed world grid in one named debug style."""

        _summary_print(self.render(style=style))


@dataclass(frozen=True)
class DebugInterconnectView:
    """Interactive inspection view over placed routing-zone interconnects.

    Interconnect inspection is kept separate from zone inspection so seam
    continuity questions remain explicit and do not disappear into the
    neighboring zones.
    """

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "all_get",
            "count_get",
            "all_render",
            "all_print",
            "interconnect_get",
            "routes_get",
            "render",
            "print",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<interconnects>"

    def all_get(self):
        """Return all placed routing-zone interconnects."""

        return tuple(
            DebugInterconnectHandle(
                debugContext=self.debugContext,
                sourceGridCoord=interconnect.sourceZoneId.id,
                destinationGridCoord=interconnect.destinationZoneId.id,
            )
            for interconnect in self.debugContext.interconnects_getAll()
            if isinstance(interconnect.sourceZoneId.id, GridCoord)
            and isinstance(interconnect.destinationZoneId.id, GridCoord)
        )

    def count_get(self) -> int:
        """Return interconnect count."""

        return len(self.all_get())

    def all_render(self) -> str:
        """Render readable summaries for all placed routing-zone interconnects."""

        return "\n\n".join(interconnect.render() for interconnect in self.all_get())

    def all_print(self) -> None:
        """Print readable summaries for all placed routing-zone interconnects."""

        _summary_print(self.all_render())

    def interconnect_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return one interconnect handle by endpoint coordinates."""

        return DebugInterconnectHandle(
            debugContext=self.debugContext,
            sourceGridCoord=GridCoord(
                columnIndex=sourceColumnIndex,
                rowIndex=sourceRowIndex,
            ),
            destinationGridCoord=GridCoord(
                columnIndex=destinationColumnIndex,
                rowIndex=destinationRowIndex,
            ),
        )

    def routes_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return solved seam routes for one interconnect."""

        interconnectHandle = self.interconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )
        return interconnectHandle.routes_get()

    def render(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> str:
        """Render one interconnect plus its seam routes."""

        interconnectHandle = self.interconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )
        return interconnectHandle.render()

    def print(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> None:
        """Print one interconnect plus its seam routes."""

        _summary_print(
            self.render(
                sourceColumnIndex=sourceColumnIndex,
                sourceRowIndex=sourceRowIndex,
                destinationColumnIndex=destinationColumnIndex,
                destinationRowIndex=destinationRowIndex,
            )
        )

    # --- backward-compatible aliases (not in __dir__) ---
    def all(self):
        return self.all_get()  # noqa: E704

    def count(self) -> int:
        return self.count_get()  # noqa: E704

    def render_all(self) -> str:
        return self.all_render()  # noqa: E704

    def print_all(self) -> None:
        return self.all_print()  # noqa: E704

    def get(self, srcCol: int, srcRow: int, dstCol: int, dstRow: int):
        return self.interconnect_get(srcCol, srcRow, dstCol, dstRow)  # noqa: E704

    def routes(self, srcCol: int, srcRow: int, dstCol: int, dstRow: int):
        return self.routes_get(srcCol, srcRow, dstCol, dstRow)  # noqa: E704


@dataclass(frozen=True)
class DebugCallView:
    """Interactive inspection view over canonical call edges.

    These helpers expose the canonical circuit graph as ordered edges so the
    operator can verify reuse, recursion, and ancestry without reading the raw
    source YAML again.
    """

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "all_get",
            "count_get",
            "outgoing_get",
            "incoming_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<calls>"

    def all_get(self):
        """Return all canonical ordered call edges."""

        return self.debugContext.calls_getAll()

    def count_get(self) -> int:
        """Return canonical call-edge count."""

        return len(self.all_get())

    def outgoing_get(self, moduleName: str, functionName: str):
        """Return outgoing call edges for one canonical chip."""

        return (
            self.debugContext.circuitDocument.circuitCallSet.outgoingCallsForChip_get(
                ChipId(moduleName=moduleName, functionName=functionName)
            )
        )

    def incoming_get(self, moduleName: str, functionName: str):
        """Return incoming call edges for one canonical chip."""

        return (
            self.debugContext.circuitDocument.circuitCallSet.incomingCallsForChip_get(
                ChipId(moduleName=moduleName, functionName=functionName)
            )
        )

    # --- backward-compatible aliases (not in __dir__) ---
    def all(self):
        return self.all_get()  # noqa: E704

    def count(self) -> int:
        return self.count_get()  # noqa: E704

    def outgoing(self, moduleName: str, functionName: str):
        return self.outgoing_get(moduleName, functionName)  # noqa: E704

    def incoming(self, moduleName: str, functionName: str):
        return self.incoming_get(moduleName, functionName)  # noqa: E704


@dataclass(frozen=True)
class DebugRouteView:
    """Interactive inspection view over obligations and solved routes.

    The route view intentionally spans obligations plus solved layers so the
    REPL can answer both "what needs to happen?" and "what has already been
    realized?" without switching surfaces.
    """

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "callObligations_get",
            "chipInternalObligations_get",
            "chipInternal_get",
            "zoneLocal_get",
            "seamCrossing_get",
            "gridLongHaul_get",
            "forChip_get",
            "zoneLocalForChip_get",
            "forZone_get",
            "seamForChip_get",
            "gridLongHaulForChip_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<routes>"

    def callObligations_get(self):
        """Return all call-route obligations."""

        return self.debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations

    def chipInternalObligations_get(self):
        """Return all chip-internal obligations."""

        return self.debugContext.routeObligationSet.chipInternalRouteObligationSet.chipInternalRouteObligations

    def chipInternal_get(self):
        """Return all solved chip-internal routes."""

        return self.debugContext.chipInternalSolvedRouteSet.chipInternalSolvedRoutes

    def zoneLocal_get(self):
        """Return all solved zone-local routes."""

        return self.debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes

    def seamCrossing_get(self):
        """Return all solved seam-crossing interconnect routes."""

        return self.debugContext.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes

    def gridLongHaul_get(self):
        """Return all solved grid-level long-haul routes."""

        return (
            self.debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
        )

    def forChip_get(self, moduleName: str, functionName: str):
        """Return solved chip-internal routes for one canonical chip."""

        return self.debugContext.chipRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def zoneLocalForChip_get(self, moduleName: str, functionName: str):
        """Return solved zone-local routes touching one canonical chip."""

        return self.debugContext.zoneLocalRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def forZone_get(self, columnIndex: int, rowIndex: int):
        """Return solved zone-local routes for one placed routing zone."""

        return self.debugContext.zoneLocalRoutesForZone_get(
            RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
        )

    def seamForChip_get(self, moduleName: str, functionName: str):
        """Return solved seam routes touching one canonical chip."""

        return self.debugContext.interconnectRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def gridLongHaulForChip_get(self, moduleName: str, functionName: str):
        """Return solved grid-level long-haul routes touching one chip."""

        return self.debugContext.gridRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    # --- backward-compatible aliases (not in __dir__) ---
    def call_obligations(self):
        return self.callObligations_get()  # noqa: E704

    def chip_internal_obligations(self):
        return self.chipInternalObligations_get()  # noqa: E704

    def chip_internal(self):
        return self.chipInternal_get()  # noqa: E704

    def zone_local(self):
        return self.zoneLocal_get()  # noqa: E704

    def seam_crossing(self):
        return self.seamCrossing_get()  # noqa: E704

    def grid_long_haul(self):
        return self.gridLongHaul_get()  # noqa: E704

    def for_chip(self, moduleName: str, functionName: str):
        return self.forChip_get(moduleName, functionName)  # noqa: E704

    def zone_local_for_chip(self, moduleName: str, functionName: str):
        return self.zoneLocalForChip_get(moduleName, functionName)  # noqa: E704

    def for_zone(self, columnIndex: int, rowIndex: int):
        return self.forZone_get(columnIndex, rowIndex)  # noqa: E704

    def seam_for_chip(self, moduleName: str, functionName: str):
        return self.seamForChip_get(moduleName, functionName)  # noqa: E704

    def grid_long_haul_for_chip(self, moduleName: str, functionName: str):
        return self.gridLongHaulForChip_get(moduleName, functionName)  # noqa: E704


@dataclass(frozen=True)
class DebugDocumentView:
    """Interactive inspection view over the loaded source document."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "title_get",
            "root_get",
            "callingDepth_get",
            "chipCount_get",
            "callCount_get",
            "raw_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<document>"

    def raw_get(self):
        """Return the raw loaded document mapping."""

        return self.debugContext.documentDict

    def title_get(self) -> str:
        """Return the document title."""

        return self.debugContext.circuitDocument.title

    def root_get(self) -> DebugChipHandle:
        """Return the canonical root chip as a handle."""

        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=self.debugContext.circuitDocument.rootChipRef.chipId,
        )

    def callingDepth_get(self) -> int:
        """Return the longest acyclic calling depth."""

        return self.debugContext.circuitDocument.callingDepth_calculate()

    def chipCount_get(self) -> int:
        """Return canonical chip count."""

        return self.debugContext.chipCount_get()

    def callCount_get(self) -> int:
        """Return canonical call-edge count."""

        return len(self.debugContext.calls_getAll())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def title(self) -> str:
        return self.title_get()  # noqa: E704

    def root(self) -> DebugChipHandle:
        return self.root_get()  # noqa: E704

    def calling_depth(self) -> int:
        return self.callingDepth_get()  # noqa: E704

    def chip_count(self) -> int:
        return self.chipCount_get()  # noqa: E704

    def call_count(self) -> int:
        return self.callCount_get()  # noqa: E704


@dataclass(frozen=True)
class DebugCircuitView:
    """Interactive inspection view over the validated circuit graph."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "title_get",
            "root_get",
            "chips_get",
            "calls_get",
            "chipCount_get",
            "callCount_get",
            "raw_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<circuit>"

    def raw_get(self):
        """Return the raw validated `CircuitDocument`."""

        return self.debugContext.circuitDocument

    def title_get(self) -> str:
        """Return the circuit title."""

        return self.debugContext.circuitDocument.title

    def root_get(self) -> DebugChipHandle:
        """Return the root chip as a handle."""

        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=self.debugContext.circuitDocument.rootChipRef.chipId,
        )

    def chips_get(self) -> DebugChipView:
        """Return the chip view for this circuit."""

        return self.debugContext.chips

    def calls_get(self) -> DebugCallView:
        """Return the call-edge view for this circuit."""

        return self.debugContext.calls

    def chipCount_get(self) -> int:
        """Return canonical chip count."""

        return self.debugContext.chipCount_get()

    def callCount_get(self) -> int:
        """Return canonical call-edge count."""

        return len(self.debugContext.calls_getAll())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def title(self) -> str:
        return self.title_get()  # noqa: E704

    def root(self) -> DebugChipHandle:
        return self.root_get()  # noqa: E704

    def chips(self) -> DebugChipView:
        return self.chips_get()  # noqa: E704

    def calls(self) -> DebugCallView:
        return self.calls_get()  # noqa: E704

    def chip_count(self) -> int:
        return self.chipCount_get()  # noqa: E704

    def call_count(self) -> int:
        return self.callCount_get()  # noqa: E704


@dataclass(frozen=True)
class DebugConfigView:
    """Interactive inspection view over validated application config."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "sense_get",
            "gridSize_get",
            "zoneCount_get",
            "interconnectCount_get",
            "pathPolicy_get",
            "channelSense_get",
            "raw_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<config>"

    def raw_get(self):
        """Return the raw validated `SignalFlowConfig`."""

        return self.debugContext.signalFlowConfig

    def sense_get(self) -> str:
        """Return the configured world sense."""

        return self.debugContext.signalFlowConfig.routingZoneGridConfig.worldSense.value

    def gridSize_get(self) -> GridCoord:
        """Return configured grid size as a `GridCoord`."""

        dimensions = self.debugContext.signalFlowConfig.routingZoneGridConfig.routingZoneGridDimensions
        return GridCoord(
            columnIndex=dimensions.columnCount,
            rowIndex=dimensions.rowCount,
        )

    def zoneCount_get(self) -> int:
        """Return configured zone count."""

        return self.debugContext.signalFlowConfig.routingZoneGridConfig.routingZoneCount_calculate()

    def interconnectCount_get(self) -> int:
        """Return configured interconnect count."""

        return self.debugContext.signalFlowConfig.routingZoneGridConfig.routingZoneInterconnectCount_calculate()

    def pathPolicy_get(self) -> str:
        """Return the configured grid path policy."""

        return self.debugContext.signalFlowConfig.routingZoneGridConfig.pathPolicy.value

    def channelSense_get(self) -> str:
        """Return the configured default channel sense."""

        return (
            self.debugContext.signalFlowConfig.routingZoneGridConfig.channelSense.value
        )

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def sense(self) -> str:
        return self.sense_get()  # noqa: E704

    def grid_size(self) -> GridCoord:
        return self.gridSize_get()  # noqa: E704

    def zone_count(self) -> int:
        return self.zoneCount_get()  # noqa: E704

    def interconnect_count(self) -> int:
        return self.interconnectCount_get()  # noqa: E704

    def path_policy(self) -> str:
        return self.pathPolicy_get()  # noqa: E704

    def channel_sense(self) -> str:
        return self.channelSense_get()  # noqa: E704


@dataclass(frozen=True)
class DebugTopologyGridView:
    """Interactive inspection view over the unplaced topology grid."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "size_get",
            "zoneCount_get",
            "interconnectCount_get",
            "zoneAt_get",
            "interconnectAt_get",
            "raw_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<grid>"

    def raw_get(self):
        """Return the raw unplaced `RoutingZoneGrid`."""

        return self.debugContext.routingZoneGrid

    def size_get(self) -> GridCoord:
        """Return the topology grid size."""

        return self.debugContext.routingZoneGrid.gridSize

    def zoneCount_get(self) -> int:
        """Return the number of zones in the topology grid."""

        return self.debugContext.routingZoneCount_get()

    def interconnectCount_get(self) -> int:
        """Return the number of interconnects in the topology grid."""

        return self.debugContext.interconnectCount_get()

    def zoneAt_get(self, columnIndex: int, rowIndex: int):
        """Return the raw zone lookup result at one topology coordinate."""

        return self.debugContext.routingZoneGrid.zoneAtCoordResult_get(
            GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
        )

    def interconnectAt_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return the raw interconnect lookup result at one topology seam."""

        return self.debugContext.routingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=GridCoord(
                columnIndex=sourceColumnIndex,
                rowIndex=sourceRowIndex,
            ),
            destinationGridCoord=GridCoord(
                columnIndex=destinationColumnIndex,
                rowIndex=destinationRowIndex,
            ),
        )

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def size(self) -> GridCoord:
        return self.size_get()  # noqa: E704

    def zone_count(self) -> int:
        return self.zoneCount_get()  # noqa: E704

    def interconnect_count(self) -> int:
        return self.interconnectCount_get()  # noqa: E704

    def zone_at(self, columnIndex: int, rowIndex: int):
        return self.zoneAt_get(columnIndex, rowIndex)  # noqa: E704

    def interconnect_at(self, srcCol: int, srcRow: int, dstCol: int, dstRow: int):
        return self.interconnectAt_get(srcCol, srcRow, dstCol, dstRow)  # noqa: E704


@dataclass(frozen=True)
class DebugAssignmentView:
    """Interactive inspection view over circuit-to-zone assignments."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "all_get",
            "count_get",
            "forChip_get",
            "forZone_get",
            "render",
            "print",
            "raw_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<assignment>"

    def raw_get(self):
        """Return the raw `RoutingZoneAssignmentSet`."""

        return self.debugContext.routingZoneAssignmentSet

    def all_get(self):
        """Return all routing-zone assignments."""

        return self.debugContext.routingZoneAssignmentSet.routingZoneAssignments

    def count_get(self) -> int:
        """Return assignment count."""

        return len(self.all_get())

    def forChip_get(self, moduleName: str, functionName: str):
        """Return the assignment for one canonical chip."""

        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return self.debugContext.routingZoneAssignmentSet.assignmentForChipResult_get(
            chipId
        )

    def forZone_get(self, columnIndex: int, rowIndex: int):
        """Return all assignments for one routing zone."""

        routingZoneId = RoutingZoneId(
            id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
        )
        return self.debugContext.routingZoneAssignmentSet.assignmentsForZone_get(
            routingZoneId
        )

    def render(self) -> str:
        """Render all assignments as a readable summary."""

        lines = ["assignment"]
        for assignment in self.all_get():
            lines.append(
                "  - "
                f"{_chipTitleText_build(assignment.chipRef.chipId)} -> "
                f"{assignment.routingZoneId.id} "
                f"{assignment.terminalSide.value}"
            )
        return "\n".join(lines)

    def print(self) -> None:
        """Print all assignments as a readable summary."""

        _summary_print(self.render())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def all(self):
        return self.all_get()  # noqa: E704

    def count(self) -> int:
        return self.count_get()  # noqa: E704

    def for_chip(self, m: str, f: str):
        return self.forChip_get(m, f)  # noqa: E704

    def for_zone(self, c: int, r: int):
        return self.forZone_get(c, r)  # noqa: E704


@dataclass(frozen=True)
class DebugObligationView:
    """Interactive inspection view over route obligations."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "calls_get",
            "chipInternal_get",
            "count_get",
            "render",
            "print",
            "raw_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<obligations>"

    def raw_get(self):
        """Return the raw `RouteObligationSet`."""

        return self.debugContext.routeObligationSet

    def calls_get(self):
        """Return call-route obligations."""

        return self.debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations

    def chipInternal_get(self):
        """Return chip-internal obligations."""

        return self.debugContext.routeObligationSet.chipInternalRouteObligationSet.chipInternalRouteObligations

    def count_get(self) -> int:
        """Return the total obligation count."""

        return len(self.calls_get()) + len(self.chipInternal_get())

    def render(self) -> str:
        """Render obligations as a readable summary."""

        return "\n".join(
            [
                "obligations",
                f"  call: {len(self.calls_get())}",
                f"  chip_internal: {len(self.chipInternal_get())}",
            ]
        )

    def print(self) -> None:
        """Print obligations as a readable summary."""

        _summary_print(self.render())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def calls(self):
        return self.calls_get()  # noqa: E704

    def chip_internal(self):
        return self.chipInternal_get()  # noqa: E704

    def count(self) -> int:
        return self.count_get()  # noqa: E704


@dataclass(frozen=True)
class DebugDiagnosticView:
    """Interactive inspection view over accumulated diagnostics."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return ["all_get", "count_get", "codes_get", "render", "print", "raw_get"]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<diagnostics>"

    def raw_get(self):
        """Return the raw diagnostic tuple."""

        return self.debugContext.diagnostics_getAll()

    def all_get(self):
        """Return all accumulated diagnostics."""

        return self.debugContext.diagnostics_getAll()

    def count_get(self) -> int:
        """Return accumulated diagnostic count."""

        return len(self.all_get())

    def codes_get(self) -> tuple[str, ...]:
        """Return all diagnostic codes in stored order."""

        return tuple(diagnostic.code for diagnostic in self.all_get())

    def render(self) -> str:
        """Render diagnostics as a readable summary."""

        if not self.all_get():
            return "diagnostics\n  <none>"
        return "\n".join(
            [
                "diagnostics",
                *(f"  - {diagnostic.code}" for diagnostic in self.all_get()),
            ]
        )

    def print(self) -> None:
        """Print diagnostics as a readable summary."""

        _summary_print(self.render())

    # --- backward-compatible aliases (not in __dir__) ---
    def raw(self):
        return self.raw_get()  # noqa: E704

    def all(self):
        return self.all_get()  # noqa: E704

    def count(self) -> int:
        return self.count_get()  # noqa: E704

    def codes(self) -> tuple[str, ...]:
        return self.codes_get()  # noqa: E704


@dataclass(frozen=True)
class NewEngineDebugContext:
    """Materialized current-stage debug context for the new engine.

    This object is the single assembled view of the debug pipeline for one
    source document. It stores both raw staged artifacts and curated helper
    properties that power the REPL views.
    """

    documentDict: dict[str, object]
    circuitDocument: CircuitDocument
    signalFlowConfig: SignalFlowConfig
    routingZoneGrid: RoutingZoneGrid
    routingZoneAssignmentSet: RoutingZoneAssignmentSet
    placedRoutingZoneGrid: RoutingZoneGrid
    routeObligationSet: RouteObligationSet
    chipInternalSolvedRouteSet: ChipInternalSolvedRouteSet
    routingZoneLocalSolvedRouteSet: RoutingZoneLocalSolvedRouteSet
    routingZoneInterconnectSolvedRouteSet: RoutingZoneInterconnectSolvedRouteSet
    routingZoneGridSolvedRouteSet: RoutingZoneGridSolvedRouteSet

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "chipCount_get",
            "routingZoneCount_get",
            "interconnectCount_get",
            "rootPlacementResult_get",
            "zoneOwningChipResult_get",
            "placementForChipResult_get",
            "diagnostics_getAll",
            "chips",
            "zones",
            "calls",
            "routes",
            "interconnects",
            "world",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<ctx>"

    def chipCount_get(self) -> int:
        """Return canonical chip count in the current circuit."""

        return len(self.circuitDocument.circuitChipSet.chips)

    def routingZoneCount_get(self) -> int:
        """Return zone count in the current world."""

        return len(self.routingZoneGrid.routingZoneSet.routingZones)

    def interconnectCount_get(self) -> int:
        """Return interconnect count in the current world."""

        return len(
            self.routingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects
        )

    def zoneOwningChipResult_get(self, chipId: ChipId) -> Result[RoutingZone]:
        """Get the placed routing zone that owns one canonical chip."""

        chipResult = self.circuitDocument.circuitChipSet.chipResult_get(chipId)
        if not result_isOkCheck(chipResult):
            return resultErr_build()
        routingZone: RoutingZone
        for routingZone in self.placedRoutingZoneGrid.routingZoneSet.routingZones:
            placement = routingZone.chipPlacementSet.placementForChipOrNone_get(
                chipResult.value.chipRef_build()
            )
            if placement is not None:
                return resultOk_build(routingZone)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="engine.debug.missing_chip_zone",
            message="Debug context could not find the owning placed zone for chip",
            context=(chipId.moduleName, chipId.functionName),
        )
        return resultErr_build()

    def placementForChipResult_get(self, chipId: ChipId) -> Result[ChipPlacement]:
        """Get the placed chip record for one canonical chip."""

        chipResult = self.circuitDocument.circuitChipSet.chipResult_get(chipId)
        if not result_isOkCheck(chipResult):
            return resultErr_build()
        routingZoneResult = self.zoneOwningChipResult_get(chipId)
        if not result_isOkCheck(routingZoneResult):
            return resultErr_build()
        return routingZoneResult.value.chipPlacementSet.placementForChipResult_get(
            chipResult.value.chipRef_build()
        )

    def rootPlacementResult_get(self) -> Result[ChipPlacement]:
        """Get the placed chip record for the canonical root chip."""

        return self.placementForChipResult_get(self.circuitDocument.rootChipRef.chipId)

    def diagnostics_getAll(self) -> tuple[Diagnostic, ...]:
        """Return diagnostics currently accumulated on the global stack."""

        return diagnosticStack.diagnosticSet_build().diagnostics_getAll()

    def chips_getAll(self):
        """Return all canonical chips in stable stored order."""

        return self.circuitDocument.circuitChipSet.chips

    def chipIds_getAll(self) -> tuple[ChipId, ...]:
        """Return all canonical chip ids in stable stored order."""

        return tuple(chip.chipId for chip in self.circuitDocument.circuitChipSet.chips)

    def chipResult_get(self, chipId: ChipId):
        """Get one canonical chip by id."""

        return self.circuitDocument.circuitChipSet.chipResult_get(chipId)

    def rootChipResult_get(self):
        """Get the canonical root chip."""

        return self.circuitDocument.rootChipResult_get()

    def calls_getAll(self):
        """Return all canonical ordered call edges."""

        return self.circuitDocument.circuitCallSet.circuitCalls

    def zones_getAll(self):
        """Return all placed routing zones."""

        return self.placedRoutingZoneGrid.routingZoneSet.routingZones

    def interconnects_getAll(self):
        """Return all placed routing-zone interconnects."""

        return self.placedRoutingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects

    def placementsForZone_get(self, routingZoneId):
        """Return all chip placements belonging to one placed zone."""

        routingZoneResult = self.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
        if not result_isOkCheck(routingZoneResult):
            return ()
        return routingZoneResult.value.chipPlacementSet.placements

    def chipRoutesForChip_get(self, chipId: ChipId):
        """Return all solved chip-internal routes for one canonical chip."""

        return self.chipInternalSolvedRouteSet.routesForChip_get(ChipRef(chipId=chipId))

    def zoneLocalRoutesForChip_get(self, chipId: ChipId):
        """Return all solved zone-local routes touching one canonical chip."""

        return self.routingZoneLocalSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def zoneLocalRoutesForZone_get(self, routingZoneId: RoutingZoneId):
        """Return all solved zone-local routes for one placed routing zone."""

        return self.routingZoneLocalSolvedRouteSet.routesForZone_get(routingZoneId)

    def interconnectRoutesForChip_get(self, chipId: ChipId):
        """Return all solved seam routes touching one canonical chip."""

        return self.routingZoneInterconnectSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def interconnectRoutesForInterconnect_get(self, routingZoneInterconnectId):
        """Return all solved seam routes for one placed interconnect."""

        return self.routingZoneInterconnectSolvedRouteSet.routesForInterconnect_get(
            routingZoneInterconnectId
        )

    def gridRoutesForChip_get(self, chipId: ChipId):
        """Return all solved grid-level long-haul routes touching one chip."""

        return self.routingZoneGridSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def gridRoutesForZone_get(self, routingZoneId: RoutingZoneId):
        """Return all solved grid-level long-haul routes traversing one zone."""

        return self.routingZoneGridSolvedRouteSet.routesForZone_get(routingZoneId)

    def terminalCountsForChip_build(self, chipId: ChipId) -> dict[str, int]:
        """Build terminal counts by side for one canonical chip."""

        chipResult = self.chipResult_get(chipId)
        if not result_isOkCheck(chipResult):
            return {}
        return {
            "north": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.NORTH
                ).terminals
            ),
            "south": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.SOUTH
                ).terminals
            ),
            "east": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.EAST
                ).terminals
            ),
            "west": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.WEST
                ).terminals
            ),
        }

    def locationRecordsForChip_build(
        self, chipId: ChipId
    ) -> tuple[dict[str, object], ...]:
        """Build all placement/location records for one canonical chip."""

        placementResult = self.placementForChipResult_get(chipId)
        zoneResult = self.zoneOwningChipResult_get(chipId)
        if not (result_isOkCheck(placementResult) and result_isOkCheck(zoneResult)):
            return ()
        worldGridCoordResult = zoneResult.value.routingZoneId.worldGridCoordResult_get()
        if not result_isOkCheck(worldGridCoordResult):
            return ()
        worldPoint = _chipPlacementPointForZone_build(
            routingZone=zoneResult.value,
            chipPlacement=placementResult.value,
        )
        return (
            {
                "zone": worldGridCoordResult.value,
                "terminalSide": (
                    placementResult.value.chipTerminalRegionId.routingZoneRegionSide.value
                ),
                "orderIndex": placementResult.value.orderIndex,
                "worldPoint": worldPoint,
            },
        )

    @property
    def chips(self) -> DebugChipView:
        """Return interactive chip inspection view."""

        return DebugChipView(self)

    @property
    def zones(self) -> DebugZoneView:
        """Return interactive zone inspection view."""

        return DebugZoneView(self)

    @property
    def calls(self) -> DebugCallView:
        """Return interactive call-edge inspection view."""

        return DebugCallView(self)

    @property
    def routes(self) -> DebugRouteView:
        """Return interactive route inspection view."""

        return DebugRouteView(self)

    @property
    def interconnects(self) -> DebugInterconnectView:
        """Return interactive interconnect inspection view."""

        return DebugInterconnectView(self)

    @property
    def world(self) -> DebugGridView:
        """Return interactive world-grid inspection view."""

        return DebugGridView(self)


class _SignalFlowInteractiveConsole(code.InteractiveConsole):
    """Interactive console with stable plain-text prompt handling.

    The debugger keeps prompt handling intentionally conservative so readline
    editing, completion, and backspace behavior remain stable across terminal
    frontends.
    """

    def raw_input(self, prompt: object = "") -> str:
        """Read one line, passing the prompt directly to readline via input().

        readline handles \001/\002 sentinel pairs natively — stripping them
        before this call breaks ANSI rendering and cursor-width accounting.
        """

        return input(str(prompt))


def newEngineDebugContextResult_buildFromDocumentDict(
    documentDict: dict[str, object],
) -> Result[NewEngineDebugContext]:
    """Build the full current debug context for one source document.

    This is the top-level entrypoint used by both the REPL and non-interactive
    debugging helpers. It intentionally runs the same staged pipeline as the new
    engine so any issue visible in the debugger is grounded in real engine
    state, not an alternate inspection-only path.
    """

    diagnosticStack.stack_clear()

    artifactsResult = _debugBuildArtifactsResult_build(documentDict)
    if not result_isOkCheck(artifactsResult):
        return resultErr_build()
    artifacts = artifactsResult.value

    return resultOk_build(
        NewEngineDebugContext(
            documentDict=documentDict,
            circuitDocument=artifacts.circuitDocument,
            signalFlowConfig=artifacts.signalFlowConfig,
            routingZoneGrid=artifacts.routingZoneGrid,
            routingZoneAssignmentSet=artifacts.routingZoneAssignmentSet,
            placedRoutingZoneGrid=artifacts.placedRoutingZoneGrid,
            routeObligationSet=artifacts.routeObligationSet,
            chipInternalSolvedRouteSet=artifacts.chipInternalSolvedRouteSet,
            routingZoneLocalSolvedRouteSet=artifacts.routingZoneLocalSolvedRouteSet,
            routingZoneInterconnectSolvedRouteSet=(
                artifacts.routingZoneInterconnectSolvedRouteSet
            ),
            routingZoneGridSolvedRouteSet=artifacts.routingZoneGridSolvedRouteSet,
        )
    )


def newEngineDebugRepl_run(
    documentDict: dict[str, object],
    sourcePath: str | None = None,
) -> int:
    """Run the operator-facing debug REPL for one source document.

    The REPL is intentionally thin over the already-built debug context. This
    function is responsible only for lifecycle concerns such as prompt setup,
    completion, display hooks, and console cleanup.
    """

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(documentDict)
    if not result_isOkCheck(debugContextResult):
        _diagnostics_printToStdout()
        return 1

    debugContext: NewEngineDebugContext = debugContextResult.value
    replLocals: dict[str, object] = _replLocals_build(debugContext)
    sourceDescription: str = sourcePath or "<in-memory>"
    banner: str = _replBanner_build(sourceDescription)
    previousPs1: str | None = getattr(sys, "ps1", None)
    previousPs2: str | None = getattr(sys, "ps2", None)
    previousDisplayHook = sys.displayhook
    _readline_setup(replLocals)
    _replPrompts_configure(debugContext)
    _displayHook_configure()
    interactiveConsole = _SignalFlowInteractiveConsole(locals=replLocals)
    try:
        interactiveConsole.interact(banner=banner, exitmsg="")
    finally:
        _readlineHistory_save()
        _replPrompts_restore(previousPs1, previousPs2)
        _displayHook_restore(previousDisplayHook)
    return 0


def _diagnostics_printToStdout() -> None:
    """Print accumulated diagnostics using the debugger's line formatter."""

    diagnostic: Diagnostic
    for diagnostic in diagnosticStack.diagnosticSet_build().diagnostics_getAll():
        print(_diagnosticLine_build(diagnostic))


def _summary_print(text: str) -> None:
    """Print one structured debug summary using summary-aware coloring."""

    print(_summaryTextColorize_build(text))


def _documentWithDefaultWorld_build(
    documentDict: dict[str, object],
) -> dict[str, object]:
    """Build effective debug document with default world config when absent."""

    if "world" in documentDict:
        return documentDict
    return {
        **documentDict,
        "world": {"sense": "west_to_east"},
    }


def _colorEnabled_check() -> bool:
    """Return whether ANSI coloring should be emitted."""

    return os.environ.get("NO_COLOR") is None


def _ansiWrap_build(text: str, *ansiCodes: str) -> str:
    """Wrap one text fragment in ANSI styles when color is enabled."""

    if not _colorEnabled_check():
        return text
    return f"{''.join(ansiCodes)}{text}{_ANSI_RESET}"


def _ansiPrompt_build(
    text: str,
    *ansiCodes: str,
    trailingAnsiCodes: tuple[str, ...] = (),
) -> str:
    """Build a readline-safe ANSI prompt string."""

    if not _colorEnabled_check():
        return text
    return f"\001{''.join(ansiCodes)}\002{text}\001{''.join(trailingAnsiCodes)}\002"


def _promptDisplayText_build(prompt: str) -> str:
    """Strip readline prompt sentinels before prompt text reaches `input()`."""

    return prompt.replace("\001", "").replace("\002", "")


def _promptSegment_build(text: str, *ansiCodes: str) -> str:
    """One colored segment for embedding in a multi-color readline-safe prompt.

    Each call wraps only the ANSI start codes in readline sentinels so cursor
    width accounting ignores them.  Call _promptReset_build() at the end of
    the whole prompt to restore the terminal's default color.
    """

    if not _colorEnabled_check() or not ansiCodes:
        return text
    return f"\001{''.join(ansiCodes)}\002{text}"


def _promptReset_build() -> str:
    """Readline-safe ANSI reset for the end of a multi-segment prompt."""

    if not _colorEnabled_check():
        return ""
    return f"\001{_ANSI_RESET}\002"


@dataclass(frozen=True)
class _ReplPs1:
    """Dynamic sys.ps1 object whose __str__ is called fresh before every prompt.

    Python calls str(sys.ps1) before displaying each primary prompt, so this
    object naturally reflects live state (e.g. current diagnostic count).
    """

    debugContext: "NewEngineDebugContext"

    def __str__(self) -> str:
        ctx = self.debugContext
        title = (ctx.circuitDocument.title or "untitled")[:14]

        # Diagnostic health indicator.
        errorCount = len(ctx.diagnostics_getAll())
        health = (
            _promptSegment_build("\u2713", _ANSI_GREEN, _ANSI_BOLD)
            if errorCount == 0
            else _promptSegment_build(f"{errorCount}!", _ANSI_RED, _ANSI_BOLD)
        )

        # Per-stage obligation and route counts.
        chipOblCount = len(
            ctx.routeObligationSet.chipInternalRouteObligationSet.chipInternalRouteObligations
        )
        callOblCount = len(
            ctx.routeObligationSet.callRouteObligationSet.callRouteObligations
        )
        chipRouteCount = len(ctx.chipInternalSolvedRouteSet.chipInternalSolvedRoutes)
        zoneRouteCount = len(
            ctx.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        )
        seamRouteCount = len(
            ctx.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes
        )
        gridRouteCount = len(
            ctx.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
        )
        # Seam obligations proxy: calls that cross a zone boundary exist when
        # there are >1 zones and call obligations exist.
        seamOblCount = callOblCount if ctx.routingZoneCount_get() > 1 else 0

        def _stage(letter: str, oblCount: int, routeCount: int) -> str:
            """Color one stage letter by solve state."""
            if routeCount > 0:
                return _promptSegment_build(letter, _ANSI_GREEN)
            if oblCount > 0:
                return _promptSegment_build(letter, _ANSI_YELLOW)
            return _promptSegment_build(letter, _ANSI_DIM)

        stages = (
            _stage("c", chipOblCount, chipRouteCount)
            + _stage("z", callOblCount, zoneRouteCount)
            + _stage("x", seamOblCount, seamRouteCount)
            + _stage("g", 0, gridRouteCount)
        )

        return (
            _promptSegment_build("sf", _ANSI_BOLD, _ANSI_CYAN)
            + _promptSegment_build(f":{title}[", _ANSI_CYAN)
            + health
            + _promptSegment_build("|", _ANSI_DIM)
            + stages
            + _promptSegment_build("]> ", _ANSI_CYAN)
            + _promptReset_build()
        )


def _replBanner_build(sourceDescription: str) -> str:
    """Build the startup banner shown when the debugger REPL launches."""

    return "\n".join(
        [
            _ansiWrap_build("SignalFlow new-engine debug REPL", _ANSI_BOLD, _ANSI_CYAN),
            f"{_ansiWrap_build('source', _ANSI_DIM)}: {sourceDescription}",
            "",
            _ansiWrap_build("available names", _ANSI_BOLD, _ANSI_GREEN),
            *_REPL_AVAILABLE_NAMES_LINES,
            "",
            _ansiWrap_build("useful helpers", _ANSI_BOLD, _ANSI_GREEN),
            *_REPL_HELPER_LINES,
            "",
            _ansiWrap_build(
                "tab completion is enabled when readline is available",
                _ANSI_DIM,
            ),
        ]
    )


@dataclass(frozen=True)
class DebugWorkflowView:
    """Interactive workflow surface for multi-step geometry operations.

    These methods cross layer boundaries — chip geometry -> zone geometry ->
    normalization -> seam re-solve. They are the canonical way to drive the
    zone geometry cascade from the REPL.

    Most methods are currently stubs. They will be implemented as the
    chip-geometry-driven zone sizing and normalization cascade work lands.
    """

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        return [
            "status_print",
            "inspectOrder_print",
            "chipGeometryPush_run",
            "zonesNormalize_run",
            "zoneRecalculate_run",
        ]

    def __repr__(self) -> str:
        return "<workflows>"

    def status_print(self) -> None:
        """Print current zone geometry derivation status (provisional vs chip-driven)."""
        lines = [
            _ansiWrap_build("workflow status", _ANSI_BOLD, _ANSI_CYAN),
            "",
            _ansiWrap_build("zone geometry source", _ANSI_BOLD, _ANSI_GREEN)
            + ": "
            + _ansiWrap_build(
                "chip-geometry-driven (chipDrawLines_build)", _ANSI_WHITE
            ),
            _ansiWrap_build("normalization cascade", _ANSI_BOLD, _ANSI_GREEN)
            + ": "
            + _ansiWrap_build(
                "runs but cascade re-solve after growth not yet implemented",
                _ANSI_YELLOW,
            ),
            "",
            _ansiWrap_build("next step", _ANSI_BOLD, _ANSI_GREEN)
            + ": implement "
            + _ansiWrap_build("workflows.zonesNormalize_run()", _ANSI_MAGENTA)
            + " cascade re-solve",
        ]
        # Show per-zone current frame sizes
        lines.append("")
        lines.append(_ansiWrap_build("current zone frames", _ANSI_BOLD, _ANSI_GREEN))
        for zone in self.debugContext.zones_getAll():
            zoneId = zone.routingZoneId
            frame = zone.routingZoneFrame
            lines.append(
                f"  {_ansiWrap_build(str(zoneId.id), _ANSI_CYAN)}"
                f"  w={_ansiWrap_build(str(frame.horizontalSpan), _ANSI_WHITE)}"
                f"  h={_ansiWrap_build(str(frame.verticalSpan), _ANSI_WHITE)}"
                f"  origin=({frame.horizontalStart},{frame.verticalStart})"
            )
        print("\n".join(lines))

    def inspectOrder_print(self) -> None:
        """Print the canonical REPL inspection order."""
        lines = [
            _ansiWrap_build("canonical inspection order", _ANSI_BOLD, _ANSI_CYAN),
            "",
            "  1. "
            + _ansiWrap_build("chips", _ANSI_BOLD, _ANSI_MAGENTA)
            + "           — chip geometry is upstream truth",
            "  2. "
            + _ansiWrap_build("zones", _ANSI_BOLD, _ANSI_MAGENTA)
            + "           — zone frame is derived from chips",
            "  3. "
            + _ansiWrap_build("interconnects", _ANSI_BOLD, _ANSI_MAGENTA)
            + "    — seam geometry depends on zone frames",
            "  4. "
            + _ansiWrap_build("world", _ANSI_BOLD, _ANSI_MAGENTA)
            + "           — world grid normalizes all zone frames",
            "",
            "  Example session:",
            "    " + _ansiWrap_build("chips.all_print()", _ANSI_DIM),
            "    "
            + _ansiWrap_build("chip = chips.chip_get('App.ts', 'main()')", _ANSI_DIM),
            "    " + _ansiWrap_build("chip.draw()", _ANSI_DIM),
            "    " + _ansiWrap_build("zones.all_print()", _ANSI_DIM),
            "    " + _ansiWrap_build("zone = zones.zone_get(1, 1)", _ANSI_DIM),
            "    " + _ansiWrap_build("zone.placements_get()", _ANSI_DIM),
            "    " + _ansiWrap_build("interconnects.all_print()", _ANSI_DIM),
            "    " + _ansiWrap_build("world.print('zones')", _ANSI_DIM),
        ]
        print("\n".join(lines))

    def chipGeometryPush_run(self) -> None:
        """[stub] Re-derive every zone's natural frame from chipDrawLines_build geometry."""
        lines = [
            _ansiWrap_build("chipGeometryPush_run", _ANSI_BOLD, _ANSI_YELLOW)
            + ": "
            + _ansiWrap_build("not yet implemented", _ANSI_RED),
            "",
            "When implemented this will:",
            "  1. call "
            + _ansiWrap_build("chipDrawLines_build(chip)", _ANSI_MAGENTA)
            + " for every chip in every zone",
            "  2. derive each zone's natural frame from the resulting chip row/col budgets",
            "  3. replace the current provisional terminal-count formula in placement.py",
        ]
        print("\n".join(lines))

    def zonesNormalize_run(self) -> None:
        """[stub] Run the per-row/column normalization cascade."""
        lines = [
            _ansiWrap_build("zonesNormalize_run", _ANSI_BOLD, _ANSI_YELLOW)
            + ": "
            + _ansiWrap_build("not yet implemented", _ANSI_RED),
            "",
            "When implemented this will:",
            "  1. promote every zone to the max width in its column and max height in its row",
            "  2. for every zone that grew: re-solve chip placements, zone routing, and seams",
            "  3. repeat until no zone grows (typically one pass for regular grids)",
        ]
        print("\n".join(lines))

    def zoneRecalculate_run(self, columnIndex: int, rowIndex: int) -> None:
        """[stub] Recalculate one zone from its chip geometry and re-solve its seams."""
        lines = [
            _ansiWrap_build("zoneRecalculate_run", _ANSI_BOLD, _ANSI_YELLOW)
            + f"({columnIndex}, {rowIndex}): "
            + _ansiWrap_build("not yet implemented", _ANSI_RED),
            "",
            "When implemented this will:",
            f"  1. re-derive zone ({columnIndex},{rowIndex}) frame from its chip geometries",
            "  2. re-solve zone-local routing subregions for the new frame",
            "  3. re-solve seam geometry for all interconnects touching this zone",
        ]
        print("\n".join(lines))


def _replLocals_build(debugContext: NewEngineDebugContext) -> dict[str, object]:
    """Build the curated local namespace exposed to the debug REPL."""

    return {
        "ctx": debugContext,
        "document": DebugDocumentView(debugContext),
        "circuit": DebugCircuitView(debugContext),
        "config": DebugConfigView(debugContext),
        "grid": DebugTopologyGridView(debugContext),
        "assignment": DebugAssignmentView(debugContext),
        "placed": debugContext.world,
        "obligations": DebugObligationView(debugContext),
        "chips": debugContext.chips,
        "zones": debugContext.zones,
        "world": debugContext.world,
        "calls": debugContext.calls,
        "routes": debugContext.routes,
        "interconnects": debugContext.interconnects,
        "diagnostics": DebugDiagnosticView(debugContext),
        "root_chip": _chipHandle_build(
            debugContext=debugContext,
            chipId=debugContext.circuitDocument.rootChipRef.chipId,
        ),
        "root_placement": DebugPlacementHandle(
            debugContext=debugContext,
            chipId=debugContext.circuitDocument.rootChipRef.chipId,
        ),
        "raw_placed": debugContext.placedRoutingZoneGrid,
        "raw_chips": debugContext.chips_getAll(),
        "raw_calls": debugContext.calls_getAll(),
        "raw_zones": debugContext.zones_getAll(),
        "raw_interconnects": debugContext.interconnects_getAll(),
        "raw_zone_local_routes": (
            debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        ),
        "raw_interconnect_routes": (
            debugContext.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes
        ),
        "raw_grid_routes": (
            debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
        ),
        "sfhelp": lambda: print(_replBanner_build("<current session>")),
        "man": _manual_print,
        "workflows": DebugWorkflowView(debugContext),
        "ls": ls,
        "tree": tree,
    }


def _replPrompts_configure(debugContext: NewEngineDebugContext | None = None) -> None:
    """Configure a context-bearing colored prompt.

    When called with a debug context sys.ps1 is set to a _ReplPs1 object.
    Python calls str(sys.ps1) before every primary prompt, so the indicator
    (diagnostic error count or green checkmark) stays live as you work.

    Color scheme:
      sf              bold cyan   — tool identifier
      :title[         cyan        — document context
      ✓               bold green  — no diagnostic errors
      N!              bold red    — N errors in the diagnostic stack
      ]>              cyan
      (after >)       ANSI reset  — user input in terminal default color
    """

    if debugContext is None:
        sys.ps1 = "sf> "
        sys.ps2 = "... "
        return

    sys.ps1 = _ReplPs1(debugContext=debugContext)
    sys.ps2 = _ansiPrompt_build(
        "... ",
        _ANSI_DIM,
        trailingAnsiCodes=(_ANSI_RESET,),
    )


def _replPrompts_restore(
    previousPs1: str | None,
    previousPs2: str | None,
) -> None:
    """Restore Python prompts after leaving the REPL."""

    if _colorEnabled_check():
        sys.stdout.write(_ANSI_RESET)
        sys.stdout.flush()

    if previousPs1 is None:
        with suppress(AttributeError):
            del sys.ps1
    else:
        sys.ps1 = previousPs1
    if previousPs2 is None:
        with suppress(AttributeError):
            del sys.ps2
    else:
        sys.ps2 = previousPs2


def _completionWrapper_build(
    completer: rlcompleter.Completer,
) -> object:
    """Build a safe tab-completion callable for readline.

    rlcompleter.Completer falls through to `global_matches("")` when the word
    under the cursor is empty (e.g. immediately after an opening parenthesis).
    That produces hundreds of candidates, which causes GNU readline to print its
    "Display all N possibilities?" prompt, corrupting the terminal column state
    and producing the double-prompt / `bck:` artifacts on the next redraw.

    The wrapper short-circuits that path: an empty word returns no completions
    and readline silently rings the bell instead.
    """

    def _complete(text: str, state: int) -> str | None:
        if not text:
            return None
        return completer.complete(text, state)

    return _complete


def _readlineHistory_save() -> None:
    """Write readline history to disk immediately.

    Called explicitly in the REPL finally-block rather than via atexit so the
    file is guaranteed to materialise when the REPL exits, independent of how
    the surrounding process eventually terminates.
    """

    if readline is None:  # pragma: no cover - platform dependent
        return
    with suppress(OSError):
        readline.write_history_file(_HISTORY_FILE)


def _readline_setup(replLocals: dict[str, object]) -> None:
    """Enable readline history and tab completion when available.

    History is persisted to `_HISTORY_FILE` (~/.signalflow_history).  The file
    is read at startup (silently ignored if absent) and written back explicitly
    in the REPL finally-block via `_readlineHistory_save`.
    """

    if readline is None or rlcompleter is None:  # pragma: no cover - platform dependent
        return
    with suppress(OSError):
        readline.read_history_file(_HISTORY_FILE)
    readline.set_history_length(_HISTORY_LENGTH)
    completer = rlcompleter.Completer(replLocals)
    readline.set_completer(_completionWrapper_build(completer))
    readline.set_completer_delims(" \t\n`~!@#$%^&*()-=+[{]}\\|;:'\",<>/?")
    if readline.__doc__ and "libedit" in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")


def _debugBuildArtifactsResult_build(
    documentDict: dict[str, object],
) -> Result[_DebugBuildArtifacts]:
    """Build the staged engine artifacts consumed by the debug context."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(documentDict)
    if not result_isOkCheck(circuitDocumentResult):
        return resultErr_build()
    circuitDocument = circuitDocumentResult.value

    signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
        _documentWithDefaultWorld_build(documentDict),
        callingDepth=circuitDocument.callingDepth_calculate(),
    )
    if not result_isOkCheck(signalFlowConfigResult):
        return resultErr_build()
    signalFlowConfig = signalFlowConfigResult.value

    routingZoneGridResult = routingZoneGridResult_buildFromSignalFlowConfig(
        signalFlowConfig
    )
    if not result_isOkCheck(routingZoneGridResult):
        return resultErr_build()
    routingZoneGrid = routingZoneGridResult.value

    routingZoneAssignmentSetResult = (
        routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
            circuitDocument,
            routingZoneGrid,
        )
    )
    if not result_isOkCheck(routingZoneAssignmentSetResult):
        return resultErr_build()
    routingZoneAssignmentSet = routingZoneAssignmentSetResult.value

    placedRoutingZoneGridResult = (
        routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
            routingZoneAssignmentSet,
            routingZoneGrid,
            circuitDocument,
        )
    )
    if not result_isOkCheck(placedRoutingZoneGridResult):
        return resultErr_build()
    placedRoutingZoneGrid = placedRoutingZoneGridResult.value

    routeObligationSetResult = (
        routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid(
            circuitDocument,
            placedRoutingZoneGrid,
        )
    )
    if not result_isOkCheck(routeObligationSetResult):
        return resultErr_build()
    routeObligationSet = routeObligationSetResult.value

    solvedRouteSetsResult = _debugSolvedRouteSetsResult_build(
        circuitDocument=circuitDocument,
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        routeObligationSet=routeObligationSet,
    )
    if not result_isOkCheck(solvedRouteSetsResult):
        return resultErr_build()
    (
        chipInternalSolvedRouteSet,
        routingZoneLocalSolvedRouteSet,
        routingZoneInterconnectSolvedRouteSet,
        routingZoneGridSolvedRouteSet,
    ) = solvedRouteSetsResult.value

    return resultOk_build(
        _DebugBuildArtifacts(
            circuitDocument=circuitDocument,
            signalFlowConfig=signalFlowConfig,
            routingZoneGrid=routingZoneGrid,
            routingZoneAssignmentSet=routingZoneAssignmentSet,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            routeObligationSet=routeObligationSet,
            chipInternalSolvedRouteSet=chipInternalSolvedRouteSet,
            routingZoneLocalSolvedRouteSet=routingZoneLocalSolvedRouteSet,
            routingZoneInterconnectSolvedRouteSet=(
                routingZoneInterconnectSolvedRouteSet
            ),
            routingZoneGridSolvedRouteSet=routingZoneGridSolvedRouteSet,
        )
    )


def _debugSolvedRouteSetsResult_build(
    *,
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    routeObligationSet: RouteObligationSet,
) -> Result[
    tuple[
        ChipInternalSolvedRouteSet,
        RoutingZoneLocalSolvedRouteSet,
        RoutingZoneInterconnectSolvedRouteSet,
        RoutingZoneGridSolvedRouteSet,
    ]
]:
    """Build the solved route layers used by the debugger."""

    chipInternalSolvedRouteSetResult = (
        chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet(
            circuitDocument,
            routeObligationSet.chipInternalRouteObligationSet,
        )
    )
    if not result_isOkCheck(chipInternalSolvedRouteSetResult):
        return resultErr_build()

    routingZoneLocalSolvedRouteSetResult = (
        routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocument,
            placedRoutingZoneGrid,
            routeObligationSet.callRouteObligationSet,
        )
    )
    if not result_isOkCheck(routingZoneLocalSolvedRouteSetResult):
        return resultErr_build()

    routingZoneInterconnectSolvedRouteSetResult = (
        routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocument,
            placedRoutingZoneGrid,
            routeObligationSet.callRouteObligationSet,
        )
    )
    if not result_isOkCheck(routingZoneInterconnectSolvedRouteSetResult):
        return resultErr_build()

    routingZoneGridSolvedRouteSetResult = (
        routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocument,
            placedRoutingZoneGrid,
            routeObligationSet.callRouteObligationSet,
        )
    )
    if not result_isOkCheck(routingZoneGridSolvedRouteSetResult):
        return resultErr_build()

    return resultOk_build(
        (
            chipInternalSolvedRouteSetResult.value,
            routingZoneLocalSolvedRouteSetResult.value,
            routingZoneInterconnectSolvedRouteSetResult.value,
            routingZoneGridSolvedRouteSetResult.value,
        )
    )


def _chipSummaryLines_build(
    *,
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
    chip,
) -> list[str]:
    """Build structured summary lines for one canonical chip."""

    placementResult = debugContext.placementForChipResult_get(chipId)
    zoneResult = debugContext.zoneOwningChipResult_get(chipId)
    chipInternalRoutes = debugContext.chipRoutesForChip_get(chipId)
    zoneLocalRoutes = debugContext.zoneLocalRoutesForChip_get(chipId)
    gridRoutes = debugContext.gridRoutesForChip_get(chipId)
    terminalCounts = debugContext.terminalCountsForChip_build(chipId)
    locations = debugContext.locationRecordsForChip_build(chipId)
    drawingLines = _chipDrawingLines_build(debugContext=debugContext, chipId=chipId)
    drawingWidth, drawingHeight = _textBlockSize_build(drawingLines)

    lines: list[str] = [
        f"chip {_chipTitleText_build(chipId)}",
        f"  title: {_chipTitleText_build(chipId)}",
        f"  size: {drawingWidth}x{drawingHeight}",
        (
            "  terminals: "
            f"N={terminalCounts.get('north', 0)} "
            f"S={terminalCounts.get('south', 0)} "
            f"E={terminalCounts.get('east', 0)} "
            f"W={terminalCounts.get('west', 0)}"
        ),
        f"  input ports: {len(chip.inputPortDeclarationSet.portDeclarations)}",
        f"  output ports: {len(chip.outputPortDeclarationSet.portDeclarations)}",
        f"  internal directives: {len(chip.internalWiringDirectiveSet.directives)}",
        f"  internal solved routes: {len(chipInternalRoutes)}",
        f"  zone-local routes: {len(zoneLocalRoutes)}",
        f"  grid routes: {len(gridRoutes)}",
    ]
    lines.extend(
        _chipPlacementSummaryLines_build(
            placementResult=placementResult,
            zoneResult=zoneResult,
            locations=locations,
        )
    )
    lines.append("  draw:")
    lines.extend(f"    {drawingLine}" for drawingLine in drawingLines)
    return lines


def _chipPlacementSummaryLines_build(
    *,
    placementResult: Result[ChipPlacement],
    zoneResult: Result[RoutingZone],
    locations: tuple[dict[str, object], ...],
) -> list[str]:
    """Build placement-specific summary lines for a chip summary block."""

    lines: list[str] = []
    if result_isOkCheck(zoneResult):
        lines.append(f"  zone: {zoneResult.value.routingZoneId.id}")
    if result_isOkCheck(placementResult):
        lines.append(
            "  placement: "
            f"{placementResult.value.chipTerminalRegionId.routingZoneRegionSide.value}"
            f" order={placementResult.value.orderIndex}"
        )
    if locations:
        locationRecord = locations[0]
        lines.append(
            "  location: "
            f"zone={locationRecord['zone']} "
            f"side={locationRecord['terminalSide']} "
            f"order={locationRecord['orderIndex']} "
            f"point={locationRecord['worldPoint']}"
        )
    return lines


def _chipSummaryText_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> str:
    """Build a readable summary block for one canonical chip."""

    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        return f"chip {chipId.moduleName}:{chipId.functionName}\n  status: missing"
    return "\n".join(
        _chipSummaryLines_build(
            debugContext=debugContext,
            chipId=chipId,
            chip=chipResult.value,
        )
    )


def _chipTitleText_build(chipId: ChipId) -> str:
    """Build a stable human-readable chip title."""

    return f"{chipId.moduleName}:{chipId.functionName}"


def _chipTitleParts_build(chipTitle: str) -> tuple[str, str]:
    """Build `(moduleName, functionName)` from one `module:function` title."""

    if chipTitle.count(":") != 1:
        raise ValueError(
            "Invalid chip title "
            f"{chipTitle!r}. Use 'moduleName:functionName', for example "
            "'App.ts:main()'. Run chips.names() to list valid titles."
        )
    moduleName, functionName = chipTitle.split(":", 1)
    if not moduleName or not functionName:
        raise ValueError(
            "Invalid chip title "
            f"{chipTitle!r}. Use 'moduleName:functionName', for example "
            "'App.ts:main()'. Run chips.names() to list valid titles."
        )
    return (moduleName, functionName)


def _chipHandle_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> DebugChipHandle:
    """Build one validated chip handle for interactive use."""

    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        raise KeyError(
            "Unknown chip "
            f"{_chipTitleText_build(chipId)!r}. Run chips.names() to list valid "
            "titles."
        )
    return DebugChipHandle(
        debugContext=debugContext,
        chipId=chipId,
    )


def _zoneHandle_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
) -> DebugZoneHandle:
    """Build one validated zone handle for interactive use."""

    zoneResult = debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZoneId
    )
    if not result_isOkCheck(zoneResult):
        raise KeyError(f"Unknown zone {routingZoneId.id!r}")
    return DebugZoneHandle(
        debugContext=debugContext,
        routingZoneId=routingZoneId,
    )


def _chipDrawingLines_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> tuple[str, ...]:
    """Resolve a chip from the debug context and delegate to the canonical drawer.

    The canonical drawing logic lives in `models.chip.chipDrawLines_build` so
    that the debugger and the final renderer share a single representation.
    """

    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        return ("<missing chip>",)
    return chipDrawLines_build(chipResult.value)


def _zoneDrawingLines_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Resolve a zone from the debug context and delegate to the canonical drawer.

    The canonical drawing logic lives in `models.routing_zone.routingZoneDrawLines_build`
    so that the debugger and the final renderer share a single representation.
    """

    zoneResult = debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZoneId
    )
    if not result_isOkCheck(zoneResult):
        return f"zone {routingZoneId.id}\n  status: missing"
    return "\n".join(routingZoneDrawLines_build(zoneResult.value))


def _textBlockSize_build(
    lines: tuple[str, ...] | list[str],
) -> tuple[int, int]:
    """Build width and height for one text block."""

    if not lines:
        return (0, 0)
    return (max(len(line) for line in lines), len(lines))


def _chipPlacementPointForZone_build(
    routingZone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> tuple[int, int]:
    """Build the world-coordinate point used for the placed chip marker."""

    regionResult = routingZone.routingZoneRegionSet.regionResult_get(
        chipPlacement.chipTerminalRegionId
    )
    assert result_isOkCheck(regionResult)
    regionFrame = regionResult.value.routingZoneRegionFrame
    side = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    assert side is not None
    if side in {RoutingZoneRegionSide.WEST, RoutingZoneRegionSide.EAST}:
        return (
            regionFrame.horizontalStart,
            regionFrame.verticalStart + chipPlacement.orderIndex,
        )
    return (
        regionFrame.horizontalStart + chipPlacement.orderIndex,
        regionFrame.verticalStart,
    )


def _zoneSummaryText_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Build a readable debug summary for one placed routing zone."""

    routingZoneResult = (
        debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(routingZoneId)
    )
    if not result_isOkCheck(routingZoneResult):
        return f"zone {routingZoneId.id}\n  status: missing"
    routingZone = routingZoneResult.value
    placements = debugContext.placementsForZone_get(routingZoneId)
    localRoutes = debugContext.zoneLocalRoutesForZone_get(routingZoneId)
    lines: list[str] = [
        f"zone {routingZone.routingZoneId.id}",
        f"  sense: {routingZone.routingZoneSense.value}",
        (
            "  frame: "
            f"({routingZone.routingZoneFrame.horizontalStart},"
            f"{routingZone.routingZoneFrame.verticalStart}) + "
            f"{routingZone.routingZoneFrame.horizontalSpan}x"
            f"{routingZone.routingZoneFrame.verticalSpan}"
        ),
        f"  regions: {len(routingZone.routingZoneRegionSet.routingZoneRegions)}",
        f"  placements: {len(placements)}",
        f"  zone-local routes: {len(localRoutes)}",
        (f"  grid routes: {len(debugContext.gridRoutesForZone_get(routingZoneId))}"),
    ]
    chipPlacement: ChipPlacement
    for chipPlacement in placements:
        lines.append(
            "  - "
            f"{chipPlacement.chipRef.chipId.moduleName}:"
            f"{chipPlacement.chipRef.chipId.functionName} "
            f"{chipPlacement.chipTerminalRegionId.routingZoneRegionSide.value}"
            f"#{chipPlacement.orderIndex}"
        )
    return "\n".join(lines)


def _zoneRoutesText_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Build readable solved-route text for one placed routing zone."""

    localRoutes = debugContext.zoneLocalRoutesForZone_get(routingZoneId)
    lines: list[str] = [
        f"zone routes {routingZoneId.id}",
        f"  count: {len(localRoutes)}",
    ]
    localRoute = None
    for localRoute in localRoutes:
        lines.append(
            "  - "
            f"{localRoute.sourceChipRef.chipId.functionName} -> "
            f"{localRoute.destinationChipRef.chipId.functionName} "
            f"[{localRoute.solveKind.value}]"
        )
        lines.append(f"    points: {localRoute.routePoints}")
    return "\n".join(lines)


def _interconnectSummaryText_build(
    debugContext: NewEngineDebugContext,
    routingZoneInterconnectId,
) -> str:
    """Build readable solved-route text for one placed interconnect."""

    solvedRoutes = debugContext.interconnectRoutesForInterconnect_get(
        routingZoneInterconnectId
    )
    lines: list[str] = [
        (
            "interconnect "
            f"{routingZoneInterconnectId.sourceZoneId.id} -> "
            f"{routingZoneInterconnectId.destinationZoneId.id}"
        ),
        f"  seam routes: {len(solvedRoutes)}",
    ]
    solvedRoute = None
    for solvedRoute in solvedRoutes:
        lines.append(
            "  - "
            f"{solvedRoute.sourceChipRef.chipId.functionName} -> "
            f"{solvedRoute.destinationChipRef.chipId.functionName} "
            f"[{solvedRoute.solveKind.value}]"
        )
        lines.append(f"    points: {solvedRoute.routePoints}")
    return "\n".join(lines)


def _gridText_build(
    debugContext: NewEngineDebugContext,
    style: str,
) -> str:
    """Build one readable placed-world text view for the named style."""

    if style == "zones":
        return _gridZonesText_build(debugContext)
    if style == "placements":
        return _gridPlacementsText_build(debugContext)
    if style == "routes":
        return _gridRoutesText_build(debugContext)
    return "unknown world print style\n  expected one of: zones, placements, routes"


def _gridZonesText_build(
    debugContext: NewEngineDebugContext,
) -> str:
    """Build grid text showing zone coordinates."""

    size = debugContext.placedRoutingZoneGrid.gridSize
    rows: list[str] = [f"world {size.columnIndex}x{size.rowIndex}"]
    rowIndex: int
    for rowIndex in range(1, size.rowIndex + 1):
        cells: list[str] = []
        columnIndex: int
        for columnIndex in range(1, size.columnIndex + 1):
            cells.append(f"[{columnIndex},{rowIndex}]")
        rows.append(" ".join(cells))
    return "\n".join(rows)


def _gridPlacementsText_build(
    debugContext: NewEngineDebugContext,
) -> str:
    """Build grid text showing chip placement ownership by zone."""

    lines: list[str] = ["world placements"]
    routingZone: RoutingZone
    for routingZone in debugContext.zones_getAll():
        placements = debugContext.placementsForZone_get(routingZone.routingZoneId)
        placementText: str = (
            ", ".join(
                (
                    f"{chipPlacement.chipRef.chipId.functionName}"
                    f"@{chipPlacement.chipTerminalRegionId.routingZoneRegionSide.value}"
                    f"#{chipPlacement.orderIndex}"
                )
                for chipPlacement in placements
            )
            or "<empty>"
        )
        lines.append(f"  {routingZone.routingZoneId.id}: {placementText}")
    return "\n".join(lines)


def _gridRoutesText_build(
    debugContext: NewEngineDebugContext,
) -> str:
    """Build grid text showing zone-local route ownership by zone."""

    lines: list[str] = ["world routes"]
    routingZone: RoutingZone
    for routingZone in debugContext.zones_getAll():
        localRoutes = debugContext.zoneLocalRoutesForZone_get(routingZone.routingZoneId)
        routeText: str = (
            ", ".join(
                (
                    f"{localRoute.sourceChipRef.chipId.functionName}->"
                    f"{localRoute.destinationChipRef.chipId.functionName}"
                )
                for localRoute in localRoutes
            )
            or "<none>"
        )
        lines.append(f"  {routingZone.routingZoneId.id}: local={routeText}")
    if debugContext.interconnects_getAll():
        lines.append("  seams:")
        for interconnect in debugContext.interconnects_getAll():
            seamText: str = (
                ", ".join(
                    (
                        f"{solvedRoute.sourceChipRef.chipId.functionName}->"
                        f"{solvedRoute.destinationChipRef.chipId.functionName}"
                    )
                    for solvedRoute in debugContext.interconnectRoutesForInterconnect_get(
                        interconnect.routingZoneInterconnectId
                    )
                )
                or "<none>"
            )
            lines.append(
                "    "
                f"{interconnect.sourceZoneId.id}->{interconnect.destinationZoneId.id}: "
                f"{seamText}"
            )
    lines.append("  grid:")
    for routingZone in debugContext.zones_getAll():
        gridText: str = (
            ", ".join(
                (
                    f"{solvedRoute.sourceChipRef.chipId.functionName}->"
                    f"{solvedRoute.destinationChipRef.chipId.functionName}"
                )
                for solvedRoute in debugContext.gridRoutesForZone_get(
                    routingZone.routingZoneId
                )
            )
            or "<none>"
        )
        lines.append(f"    {routingZone.routingZoneId.id}: {gridText}")
    return "\n".join(lines)


def _worldDrawText_build(
    debugContext: NewEngineDebugContext,
) -> str:
    """Build a spatial ASCII schematic of the full placed world grid.

    Each zone is drawn using `routingZoneDrawLines_build`. Zones are tiled
    side-by-side (columns) and stacked (rows). A `─` connector marks each
    horizontal seam; a `│` connector marks each vertical seam.
    """

    grid = debugContext.placedRoutingZoneGrid
    size = grid.gridSize

    def _zone_block(col: int, row: int) -> list[str]:
        r = grid.routingZoneSet.zoneResult_get(
            RoutingZoneId(id=GridCoord(columnIndex=col, rowIndex=row))
        )
        if result_isOkCheck(r):
            return list(routingZoneDrawLines_build(r.value))
        return [f"[{col},{row}]", " (missing) "]

    def _has_h_seam(col: int, row: int) -> bool:
        return result_isOkCheck(
            grid.interconnectAtCoordsResult_get(
                GridCoord(columnIndex=col, rowIndex=row),
                GridCoord(columnIndex=col + 1, rowIndex=row),
            )
        )

    def _has_v_seam(col: int, row: int) -> bool:
        return result_isOkCheck(
            grid.interconnectAtCoordsResult_get(
                GridCoord(columnIndex=col, rowIndex=row),
                GridCoord(columnIndex=col, rowIndex=row + 1),
            )
        )

    def _block_w(block: list[str]) -> int:
        return max(len(line) for line in block) if block else 0

    def _pad(block: list[str], height: int, width: int) -> list[str]:
        padded = [line.ljust(width) for line in block]
        while len(padded) < height:
            padded.append(" " * width)
        return padded

    def _compose_h_row(blocks: list[list[str]], seams: list[bool]) -> list[str]:
        height = max(len(b) for b in blocks)
        widths = [_block_w(b) for b in blocks]
        padded = [_pad(b, height, w) for b, w in zip(blocks, widths)]
        mid = height // 2
        lines: list[str] = []
        for i in range(height):
            parts = [padded[0][i]]
            for j, seam in enumerate(seams):
                parts.append(" \u2500 " if (seam and i == mid) else "   ")
                parts.append(padded[j + 1][i])
            lines.append("".join(parts))
        return lines

    def _compose_v_connector(blocks: list[list[str]], seams: list[bool]) -> list[str]:
        widths = [_block_w(b) for b in blocks]
        parts: list[str] = []
        for idx, (w, seam) in enumerate(zip(widths, seams)):
            center = w // 2
            ch = "\u2502" if seam else " "
            parts.append(" " * center + ch + " " * (w - center - 1))
            if idx < len(widths) - 1:
                parts.append("   ")
        return ["".join(parts)]

    all_lines: list[str] = [f"world {size.columnIndex}\u00d7{size.rowIndex}"]
    prev_blocks: list[list[str]] | None = None
    for rowIndex in range(1, size.rowIndex + 1):
        blocks = [_zone_block(col, rowIndex) for col in range(1, size.columnIndex + 1)]
        h_seams = [_has_h_seam(col, rowIndex) for col in range(1, size.columnIndex)]
        if prev_blocks is not None:
            v_seams = [
                _has_v_seam(col, rowIndex - 1) for col in range(1, size.columnIndex + 1)
            ]
            all_lines.extend(_compose_v_connector(prev_blocks, v_seams))
        all_lines.extend(_compose_h_row(blocks, h_seams))
        prev_blocks = blocks

    return "\n".join(all_lines)


def _worldCanvasText_build(
    debugContext: NewEngineDebugContext,
) -> str:
    """Build the full world canvas (chip bodies + route wires) as one string.

    Realizes zone-local and seam-crossing routes, then delegates to
    ``worldCanvas_render`` for the compositor.  Returns a human-readable
    error string (not a diagnostic) when realization fails so the REPL
    remains usable.
    """

    zoneLocalResult = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
        debugContext.routingZoneLocalSolvedRouteSet
    )
    if not result_isOkCheck(zoneLocalResult):
        return "world canvas\n  error: zone-local route realization failed"

    interconnectResult = realizedRouteSetResult_buildFromInterconnectSolvedRouteSet(
        debugContext.routingZoneInterconnectSolvedRouteSet
    )
    if not result_isOkCheck(interconnectResult):
        return "world canvas\n  error: seam route realization failed"

    combinedRoutes = RealizedRouteSet(
        realizedRoutes=(
            zoneLocalResult.value.realizedRoutes
            + interconnectResult.value.realizedRoutes
        )
    )
    lines = worldCanvas_render(
        placedGrid=debugContext.placedRoutingZoneGrid,
        circuitChipSet=debugContext.circuitDocument.circuitChipSet,
        realizedRouteSet=combinedRoutes,
    )
    return "\n".join(lines) if lines else "world canvas\n  <empty>"


def ls(obj=None) -> None:
    """List the navigable surface of any debug object.

    Shows all public methods with their first docstring line.
    Works on any object — curated views, handles, or raw Python values.
    Call with no argument to list the top-level REPL names.
    """
    if obj is None:
        print(_ansiWrap_build("top-level REPL names", _ANSI_BOLD, _ANSI_CYAN))
        print(
            _ansiWrap_build(
                "  use ls(name) on any of these to explore further", _ANSI_DIM
            )
        )
        return

    # Gather names: use __dir__ override if present, else dir()
    try:
        names: list[str] = [n for n in obj.__dir__() if not n.startswith("_")]
    except Exception:
        names = [n for n in dir(obj) if not n.startswith("_")]

    if not names:
        print(
            _ansiWrap_build(f"  (no public surface on {type(obj).__name__})", _ANSI_DIM)
        )
        return

    typeName: str = type(obj).__name__
    print(
        _ansiWrap_build(repr(obj), _ANSI_BOLD, _ANSI_CYAN)
        + "  "
        + _ansiWrap_build(f"[{typeName}]", _ANSI_DIM)
    )

    maxLen: int = max(len(n) for n in names)
    for name in names:
        attr = getattr(obj, name, None)
        if attr is None:
            docLine: str = ""
        elif callable(attr):
            rawDoc: str = getattr(attr, "__doc__", "") or ""
            docLine = rawDoc.strip().split("\n")[0]
        else:
            docLine = repr(attr)

        paddedName: str = name.ljust(maxLen)
        print(
            "  "
            + _ansiWrap_build(paddedName, _ANSI_MAGENTA)
            + "  "
            + _ansiWrap_build(docLine[:72], _ANSI_DIM)
        )


def tree(obj=None, _depth: int = 2, _prefix: str = "", _label: str = "") -> None:
    """Recursively show the navigable subtree of any debug object.

    Prints up to `_depth` levels of the object graph.  Useful for understanding
    the shape of a context or a sub-object without calling every method manually.
    """
    if obj is None:
        print(_ansiWrap_build("pass an object to tree(), e.g. tree(chips)", _ANSI_DIM))
        return

    label: str = _label or repr(obj)
    print(_prefix + _ansiWrap_build(label, _ANSI_BOLD, _ANSI_CYAN))

    if _depth <= 0:
        print(_prefix + "  " + _ansiWrap_build("...", _ANSI_DIM))
        return

    try:
        names: list[str] = [n for n in obj.__dir__() if not n.startswith("_")]
    except Exception:
        names = [n for n in dir(obj) if not n.startswith("_")]

    for name in names:
        attr = getattr(obj, name, None)
        if attr is None:
            continue
        if callable(attr):
            rawDoc: str = getattr(attr, "__doc__", "") or ""
            docLine: str = rawDoc.strip().split("\n")[0][:60]
            print(
                _prefix
                + "  "
                + _ansiWrap_build(name + "()", _ANSI_MAGENTA)
                + "  "
                + _ansiWrap_build(docLine, _ANSI_DIM)
            )
        else:
            childLabel: str = f"{name} = {repr(attr)[:60]}"
            if hasattr(attr, "__dir__") and not isinstance(
                attr, (str, int, float, bool, type(None))
            ):
                tree(attr, _depth=_depth - 1, _prefix=_prefix + "  ", _label=childLabel)
            else:
                print(_prefix + "  " + _ansiWrap_build(childLabel, _ANSI_WHITE))


def _manual_print(topic: str | None = None) -> None:
    """Print a topic-focused manual for the debug REPL surface."""

    resolvedTopic: str = "general" if topic is None else topic
    manualLines = _MANUAL_BY_TOPIC.get(resolvedTopic, _MANUAL_BY_TOPIC["general"])

    colorizedLines: list[str] = []
    for line in manualLines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if not stripped:
            colorizedLines.append("")
        elif indent == "" and not stripped.startswith("#"):
            # Top-level section header
            colorizedLines.append(_ansiWrap_build(line, _ANSI_BOLD, _ANSI_CYAN))
        elif stripped.startswith("#"):
            # Comment / note
            colorizedLines.append(_ansiWrap_build(line, _ANSI_DIM))
        elif (
            stripped.startswith("workflows.")
            or stripped.startswith("chips.")
            or stripped.startswith("chip.")
            or stripped.startswith("zones.")
            or stripped.startswith("zone.")
            or stripped.startswith("world.")
            or stripped.startswith("calls.")
            or stripped.startswith("routes.")
            or stripped.startswith("interconnects.")
            or stripped.startswith("ic.")
            or stripped.startswith("document.")
            or stripped.startswith("circuit.")
            or stripped.startswith("config.")
            or stripped.startswith("ls(")
            or stripped.startswith("tree(")
        ):
            # Method call examples — split at # comment if present
            if "  #" in line:
                codePart, commentPart = line.split("  #", 1)
                colorizedLines.append(
                    _ansiWrap_build(codePart, _ANSI_MAGENTA)
                    + _ansiWrap_build("  #" + commentPart, _ANSI_DIM)
                )
            else:
                colorizedLines.append(_ansiWrap_build(line, _ANSI_MAGENTA))
        else:
            colorizedLines.append(line)

    print("\n".join(colorizedLines))


def _displayHook_configure() -> None:
    """Install the debugger display hook for interactive expression results."""

    sys.displayhook = _displayHook_render


def _displayHook_restore(previousDisplayHook) -> None:
    """Restore the previous Python display hook after leaving the REPL."""

    sys.displayhook = previousDisplayHook


def _displayHook_render(value) -> None:
    """Render one interactive expression result with debugger color policy."""

    if value is None:
        return
    builtins._ = value
    print(_displayText_build(value))


def _displayText_build(value) -> str:
    """Build colorized interactive output for one Python value.

    The goal is not full syntax highlighting. The goal is predictable visual
    classification at the REPL: strings should read like strings, results like
    results, and object summaries like object summaries.
    """

    baseText: str = pformat(value, sort_dicts=False)
    if isinstance(value, str):
        if "\n" in value:
            return _ansiWrap_build(value, _ANSI_YELLOW)
        return _ansiWrap_build(baseText, _ANSI_YELLOW)
    if callable(value):
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_MAGENTA)
    if isinstance(value, type):
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_BLUE)
    if isinstance(value, bool):
        return _ansiWrap_build(
            baseText,
            _ANSI_BOLD,
            _ANSI_GREEN if value else _ANSI_RED,
        )
    if isinstance(value, (int, float)):
        return _ansiWrap_build(baseText, _ANSI_GREEN)
    if is_dataclass(value):
        return _ansiWrap_build(baseText, _ANSI_CYAN)
    if value.__class__.__name__ == "ResultOk":
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_GREEN)
    if value.__class__.__name__ == "ResultErr":
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_RED)
    if isinstance(value, dict):
        return _reprSyntaxColorize_build(baseText, defaultAnsiCodes=(_ANSI_BLUE,))
    if isinstance(value, (tuple, list, set, frozenset)):
        return _reprSyntaxColorize_build(baseText, defaultAnsiCodes=(_ANSI_WHITE,))
    return _reprSyntaxColorize_build(baseText, defaultAnsiCodes=(_ANSI_CYAN,))


def _reprSyntaxColorize_build(
    text: str,
    *,
    defaultAnsiCodes: tuple[str, ...],
) -> str:
    """Colorize a repr-like text buffer by simple token class.

    This is intentionally lightweight rather than a full parser. The goal is to
    make ordinary REPL values easier to scan by distinguishing:

    - string literals
    - numbers and booleans
    - punctuation and separators
    - type-like / callable-like identifiers
    - ordinary text that falls back to a default color for the value family
    """

    tokenPattern = re.compile(
        r"""
        (?P<string>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")
        |(?P<number>\b-?\d+(?:\.\d+)?\b)
        |(?P<boolnone>\bTrue\b|\bFalse\b|\bNone\b)
        |(?P<identifier>\b[A-Za-z_][A-Za-z0-9_]*\b)
        |(?P<operator>[=])
        |(?P<punct>[()\[\]{}:,])
        """,
        re.VERBOSE,
    )

    pieces: list[str] = []
    lastEnd: int = 0
    match: re.Match[str] | None
    for match in tokenPattern.finditer(text):
        if match.start() > lastEnd:
            pieces.append(
                _ansiWrap_build(text[lastEnd : match.start()], *defaultAnsiCodes)
            )
        tokenText = match.group(0)
        if match.lastgroup == "string":
            pieces.append(_ansiWrap_build(tokenText, _ANSI_YELLOW))
        elif match.lastgroup == "number":
            pieces.append(_ansiWrap_build(tokenText, _ANSI_GREEN))
        elif match.lastgroup == "boolnone":
            if tokenText == "False":
                pieces.append(_ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_RED))
            elif tokenText == "True":
                pieces.append(_ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_GREEN))
            else:
                pieces.append(_ansiWrap_build(tokenText, _ANSI_DIM))
        elif match.lastgroup == "identifier":
            nextIndex = match.end()
            nextChar = text[nextIndex : nextIndex + 1]
            if nextChar == "(":
                pieces.append(_ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_CYAN))
            elif nextChar == "=":
                pieces.append(_ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_GREEN))
            else:
                pieces.append(_ansiWrap_build(tokenText, *defaultAnsiCodes))
        elif match.lastgroup == "operator":
            pieces.append(_ansiWrap_build(tokenText, _ANSI_DIM))
        else:
            pieces.append(_ansiWrap_build(tokenText, _ANSI_DIM))
        lastEnd = match.end()
    if lastEnd < len(text):
        pieces.append(_ansiWrap_build(text[lastEnd:], *defaultAnsiCodes))
    return "".join(pieces)


def _summaryTextColorize_build(text: str) -> str:
    """Colorize one structured summary block for REPL printing.

    Summary rendering is line-role aware: headers, field labels, and embedded
    drawing blocks are intentionally colored differently so `*.print()` output
    is easier to scan than a plain monochrome text dump.
    """

    colorizedLines: list[str] = []
    inDrawBlock: bool = False
    line: str
    for line in text.splitlines():
        strippedLine: str = line.strip()
        if not strippedLine:
            colorizedLines.append(line)
            continue
        if not line.startswith(" "):
            colorizedLines.append(_ansiWrap_build(line, _ANSI_BOLD, _ANSI_CYAN))
            inDrawBlock = False
            continue
        if inDrawBlock and line.startswith("    "):
            colorizedLines.append(_ansiWrap_build(line, _ANSI_YELLOW))
            continue

        indentation: str = line[: len(line) - len(line.lstrip(" "))]
        body: str = line[len(indentation) :]
        if body.endswith(":"):
            colorizedLines.append(
                f"{indentation}{_ansiWrap_build(body, _ANSI_BOLD, _ANSI_GREEN)}"
            )
            inDrawBlock = body == "draw:"
            continue
        if ":" in body:
            label, valueText = body.split(":", 1)
            colorizedLines.append(
                f"{indentation}"
                f"{_ansiWrap_build(label + ':', _ANSI_BOLD, _ANSI_GREEN)}"
                f"{_ansiWrap_build(valueText, _ANSI_WHITE)}"
            )
            inDrawBlock = False
            continue
        if body.startswith("- "):
            colorizedLines.append(f"{indentation}{_ansiWrap_build(body, _ANSI_WHITE)}")
            inDrawBlock = False
            continue
        colorizedLines.append(_ansiWrap_build(line, _ANSI_WHITE))
        inDrawBlock = False
    return "\n".join(colorizedLines)


def _diagnosticLine_build(diagnostic: Diagnostic) -> str:
    """Build one colorized diagnostic output line."""

    contextSuffix: str = ""
    if diagnostic.context:
        contextSuffix = _ansiWrap_build(
            f" context={diagnostic.context}",
            _ANSI_DIM,
        )
    if diagnostic.level.value == "error":
        levelText = _ansiWrap_build(diagnostic.level.value, _ANSI_BOLD, _ANSI_RED)
    else:
        levelText = _ansiWrap_build(diagnostic.level.value, _ANSI_BOLD, _ANSI_YELLOW)
    phaseText = _ansiWrap_build(diagnostic.phase.value, _ANSI_CYAN)
    codeText = _ansiWrap_build(diagnostic.code, _ANSI_GREEN)
    return f"{levelText}:{phaseText}:{codeText}: {diagnostic.message}{contextSuffix}"
