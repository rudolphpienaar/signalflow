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
import yaml
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field, is_dataclass
from pathlib import Path
from pprint import pformat

from signalflow.algebraic.realizer import (
    algebraicRouteRealization_build,
    realizationPlan_build,
)
from signalflow.board import Board as DomainBoard
from signalflow.board import (
    BoardChip,
    BoardChipPlacementPolicy,
    BoardKernel,
    BoardKernelWire,
    BoardMaterializePolicy,
    BoardMaterializedSolution,
    BoardMaterializedWire,
    BoardRelaxationSymmetry,
    ChipInternalBoardSchema,
    BoardSolution,
    BoardSolvedWire,
    BoardSolver,
    BoardWiring,
    BoardZone,
    SolverWireInput,
    boardCanvas_render,
    boardChannelLaneCounts_build,
    chipInternalPlacedKernelArtifacts_build,
    chipInternalBoardSchema_build,
    materializedSolution_build,
    boardProblems_get,
    boardWireAlgebraicPath_build,
    board_buildFromKernel,
    realizedGeometry_text,
)
from signalflow.config import (
    SignalFlowConfig,
    signalFlowConfigResult_buildFromDocumentDict,
)
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    CallRouteObligation,
    ChipId,
    ChipInternalRouteObligation,
    ChipInternalRouteObligationSet,
    ChipInternalSolvedRouteSet,
    ChipPlacement,
    ChipPortDeclaration,
    ChipRef,
    ChipTerminalSide,
    ChipDrawGeometry,
    CircuitDocument,
    Diagnostic,
    GridCoord,
    Result,
    RouteObligationSet,
    RoutingKernel,
    RoutingLaneAttachmentSense,
    RoutingZone,
    RoutingZoneAssignmentSet,
    RoutingZoneChannelSense,
    RoutingZoneGrid,
    RoutingZoneGridSolvedRouteSet,
    RoutingZoneInterconnectSolvedRoute,
    RoutingZoneId,
    RoutingZoneInterconnectAxis,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneLocalSolvedRoute,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneRoutePoint,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    chipInternalRouteObligationSetResult_build,
    chipDrawLines_build,
    chipDrawGeometry_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneDrawLines_build,
    routingZoneRegionByIdResult_get,
    routingZoneRegionSetAll_get,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.render.world import worldCanvas_render
from signalflow.routing import (
    RealizedRoute,
    RealizedRouteCell,
    RealizedRouteSet,
    RouteSense,
    chipAttachPointSetResult_buildFromPlacedZone,
    chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet,
    chipLocalGeometrySetResult_buildFromChips,
    realizedRouteSetResult_buildFromChipInternalSolvedRouteSet,
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
from signalflow.routing.geometry import (
    chipCanvasPlacementGeometry_build,
    chipLocalGeometryResult_build,
    chipPlacementStackOffsetResult_build,
)
from signalflow.routing.track import TrackDirection, trackCell_build

try:
    import readline
    import rlcompleter
except ImportError:  # pragma: no cover - platform dependent
    readline = None
    rlcompleter = None

_HISTORY_FILE: str = os.path.expanduser("~/.signalflow_history")
_HISTORY_LENGTH: int = 1000
_BOARD_BACKEND: str = os.getenv("SIGNALFLOW_BOARD_BACKEND", "new").strip().lower()

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
    "  root_chip   root_placement prompt",
    "  ls(obj)     tree(obj)   man(topic)  sfhelp()  load(path)",
    "  solution_realize(board, solution)",
    "  solution.board_materialize(board)",
)


def _boardBackend_resolved_build(candidate: str | None = None) -> str:
    """Return the normalized board backend name.

    The board migration uses a single switch so the existing REPL surface can
    compare the legacy board-backed behavior against the new first-class board
    package without changing call sites.
    """

    normalized = (_BOARD_BACKEND if candidate is None else candidate).strip().lower()
    if normalized not in {"legacy", "new"}:
        return "new"
    return normalized


def _boardBackend_get() -> str:
    """Return the active board backend name."""

    return _boardBackend_resolved_build()


def _boardBackend_set(backendName: str) -> str:
    """Set the active board backend and return the resolved backend name."""

    global _BOARD_BACKEND
    _BOARD_BACKEND = _boardBackend_resolved_build(backendName)
    return _BOARD_BACKEND

_REPL_HELPER_LINES: tuple[str, ...] = (
    "  chips.names_get()",
    "  chips.all_text()",
    "  chip = chips.chip_get('App.ts', 'main()')",
    "  chip = chips['App.ts:main()']",
    "  chip.title_get()",
    "  chip.size_get()",
    "  chip.terminals_get()",
    "  chip.terminals_getLocalPositions('west')",
    "  chip.terminals_getWorldPositions('west')",
    "  chip.worldFrame_get()",
    "  chip.draw()",
    "  chip.children_get()",
    "  chip.child_get(0)",
    "  zones.all_text()",
    "  zone = zones.zone_get(1, 1)",
    "  ki = zone.kernel_get('intra')",
    "  kw = ki.wiring_get()",
    "  kw.list_text()",
    "  board = ki.board_get()",
    "  solver = ki.solver_get(board)",
    "  solution = solver.solution_get()",
    "  realized = solution_realize(board, solution)",
    "  materialized.geometry_text()",
    "  zone.world_text()",
    "  zone.placements_get()",
    "  zone.routes_get()",
    "  interconnects.all_text()",
    "  world.gridCanvas_text()        # full chip-body + route-wire canvas",
    "  world.gridStyle_text('zones')",
    "  routes.zoneLocal_get()",
    "  routes.seamCrossing_get()",
    "  routes.gridLongHaul_get()",
    "  calls.outgoing_get('App.ts', 'main()')",
    "  prompt.title.len_truncate(32)",
    "  prompt.title.full()",
    "  workflows.inspectOrder_print()",
    "  workflows.status_print()",
    "  ls(chips)",
    "  ls(chip)",
    "  tree(document)",
    "  load('snippets/hub_walk.py')",
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
        (
            "and chip-local internal wiring declarations. Chips do NOT own "
            "world placement."
        ),
        "",
        "chip geometry is upstream layout truth: the rendered chip body (chip.schematic_text())",
        (
            "determines the row/column budget that any containing RoutingZone "
            "must reserve."
        ),
        "If a chip gains a port row, its zone frame must grow to accommodate it.",
        "",
        "chips view  [chips]",
        "# The chips view is the entry point for all chip queries.",
        "# Select one chip, then stay on the handle for detailed inspection.",
        "",
        "  chips.all_get()                          # tuple[BoardChip]",
        "  chips.count_get()                        # int",
        "  chips.ids_get()                          # tuple[ChipId]",
        "  chips.names_get()                        # tuple[str]  'module:func' titles",
        "  chips.root_get()                         # BoardChip for root chip",
        "  chips.chip_get(moduleName, functionName) # BoardChip",
        "  chips.chipByTitle_get('App.ts:main()')  # BoardChip",
        "  chips['App.ts:main()']                   # BoardChip (index syntax)",
        "  chips.title_get(moduleName, functionName)",
        "  chips.size_get(moduleName, functionName)      # (widthCols, heightRows)",
        "  chips.terminals_get(moduleName, functionName) # {'north':N,'south':S,...}",
        "  chips.location_get(moduleName, functionName)",
        "  chips.routes_get(moduleName, functionName)",
        "  chips.schematic_text(moduleName, functionName) # canonical chip box drawing",
        "  chips.summary_text(moduleName, functionName)   # full debug summary text",
        "  chips.all_text()                              # all chip summaries",
        "",
        "chip handle  [chip = chips.chip_get(...)]",
        "# A chip handle is the ergonomic per-chip inspection surface.",
        "# It avoids passing moduleName/functionName into every call.",
        "",
        "  chip.title_get()        # 'module:func' string",
        "  chip.size_get()         # (widthCols, heightRows) — derived from schematic_text()",
        "  chip.dimensions_get()   # {'widthColumns': N, 'heightRows': M}",
        "  chip.width_get()        # int",
        "  chip.height_get()       # int",
        "  chip.terminals_get()    # {'north':N, 'south':S, 'east':E, 'west':W}",
        "  chip.placement_get()    # primary ChipPlacement result",
        "  chip.location_get()     # primary location record dict",
        "  chip.locations_get()    # all location records",
        "  chip.children_get()     # tuple[BoardChip] — outgoing call targets",
        "  chip.child_get(index)   # one child by call index",
        "  chip.routes_get()       # solved chip-internal routes",
        "  chip.internalBoard_get() # board-compatible chip-local harmonizer handle",
        (
            "  chip.schematic_text()   # canonical chip box — THIS IS "
            "UPSTREAM LAYOUT TRUTH"
        ),
        "  chip.summary_text()     # full debug summary",
        "  chip.raw_get()          # raw Result[Chip]",
        "",
        "terminal synthesis rule",
        "  input_ports  signal -> WEST terminal",
        "  input_ports  return -> WEST terminal",
        "  output_ports signal -> EAST terminal",
        "  output_ports return -> EAST terminal (inward arrow in schematic_text())",
        "",
        "  Same name on same wall deduplicates to one terminal.",
        "  chip.schematic_text() uses T-junction glyphs where wires meet the wall.",
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
        "  zones.summary_text(columnIndex, rowIndex)   # full debug summary",
        "  zones.routes_text(columnIndex, rowIndex)    # route geometry text",
        "  zones.schematic_text(columnIndex, rowIndex) # zone schematic text",
        "  zones.all_text()                            # all zone summaries",
        "",
        "zone handle  [zone = zones.zone_get(1, 1)]",
        "",
        "  zone.id_get()           # RoutingZoneId",
        "  zone.sense_get()        # 'west_to_east' | 'north_to_south'",
        "  zone.placements_get()   # chip placements",
        "  zone.routes_get()       # solved zone-local routes",
        "  zone.kernel_get('intra') # one routing kernel inside the zone",
        "  zone.kernels_get()      # {'north':..., 'south':..., ...}",
        "  zone.world_text()       # zone crop from world.gridCanvas_text()",
        "  zone.summary_text()     # full debug summary",
        "  zone.routes_text()      # route geometry",
        "  zone.schematic_text()   # zone schematic text",
        "  zone.raw_get()          # raw Result[RoutingZone]",
        "",
        "kernel handle  [kernel = zone.kernel_get('intra')]",
        "  kernel.side_get()       # 'intra' | 'west' | 'east' | 'north' | 'south'",
        "  kernel.areas_get()      # region set owned by this kernel",
        "  kernel.schematic_text() # cropped kernel substrate view",
        "  kernel.routes_text()    # realized route crop for this kernel",
        "  kernel.wiring_get()     # DebugKernelWiringHandle",
        "  kernel.board_get()      # DebugKernelBoardHandle",
        "  kernel.solver_get(board) # DebugKernelSolverHandle",
        "",
        "wiring handle  [wiring = kernel.wiring_get()]",
        "  wiring.all_get()        # tuple[DebugKernelWire]",
        "  wiring.list_text()      # one directed wire per line",
        "  wiring.algebraic_text(endpointText) # filtered symbolic view",
        "",
        "solver handle  [solver = kernel.solver_get(board)]",
        "  solver.solution_get()   # DebugKernelSolutionHandle",
        "",
        "solution handle  [solution = solver.solution_get()]",
        "  solution.list_text()",
        "  solution.algebraic_text(endpointText)",
        "",
        "materialize",
        "  realized = solution_realize(board, solution)",
        "  materialized.summary_text()",
        "  materialized.wiring_text()",
        "  materialized.geometry_text()",
        "",
        "wiring notation",
        "  module.func.signal:module.func.signal",
        "  forward example: App.ts.main().query:Worker.ts.run().query",
        "  return  example: Worker.ts.run().result:App.ts.main().result",
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
        "  world.gridSize_get()                   # GridCoord(columns, rows)",
        "  world.gridCanvas_text()                # chip bodies + route wires",
        "  world.gridSchematic_text()             # zone schematic (names only)",
        "  world.gridStyle_text('zones')          # named text view",
        "  world.gridStyle_text('placements')",
        "  world.gridStyle_text('routes')",
        "",
        "canvas vs schematic",
        "  world.gridCanvas_text()  — composite: real chip bodies at terminal",
        "    region positions with route wire glyphs overlaid.  This is the",
        "    authoritative visual output of the new engine.",
        "  world.gridSchematic_text() — schematic: chip names in abstract zone",
        "    boxes.  Useful for debugging zone topology without chip geometry.",
        "",
        "current simple regime",
        "  west_to_east with no explicit grid -> 1 x ceil(callingDepth/2) world",
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
        (
            "  routes.forChip_get(moduleName, functionName)          "
            "# chip-internal routes"
        ),
        "  routes.zoneLocalForChip_get(moduleName, functionName) # zone-local for chip",
        (
            "  routes.seamForChip_get(moduleName, functionName)      "
            "# seam routes for chip"
        ),
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
        "  interconnects.summary_text(srcCol, srcRow, dstCol, dstRow)",
        "  interconnects.all_text()         # all interconnect summaries",
        "",
        "interconnect handle  [ic = interconnects.interconnect_get(1,1, 2,1)]",
        "",
        "  ic.endpoints_get()   # (sourceGridCoord, destinationGridCoord)",
        "  ic.routes_get()      # solved seam routes",
        "  ic.summary_text()    # full debug summary",
        "  ic.schematic_text()  # seam schematic text",
        "  ic.world_text()      # world-canvas crop",
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
        (
            "  workflows.inspectOrder_print()         # canonical "
            "chip->zone->seam->world order"
        ),
        "  workflows.chipGeometryPush_run()       # [stub] re-derive zones from chips",
        "  workflows.zonesNormalize_run()         # [stub] normalization cascade",
        "  workflows.zoneRecalculate_run(col,row) # [stub] recalculate one zone",
        "",
        "typical REPL workflow (current — manual inspection):",
        "  1. chips.all_text()               # verify chip geometry is correct",
        "  2. chip = chips.chip_get(...)     # pick one chip",
        "  3. chip.schematic_text()        # inspect canonical drawing",
        "  4. zones.all_text()              # inspect current zone frames",
        "  5. zone = zones.zone_get(1, 1)  # pick one zone",
        "  6. zone.placements_get()         # see what chips are placed where",
        "  7. interconnects.all_text()      # inspect seam geometry",
        "  8. world.gridStyle_text('zones') # see full world grid",
        "",
        "when chipGeometryPush_run() is implemented:",
        "  workflows.chipGeometryPush_run()   # push chip geometry into zone frames",
        "  workflows.zonesNormalize_run()     # normalize + cascade re-solve",
        "  workflows.status_print()           # verify all zones are chip-driven",
        "  world.gridStyle_text('zones')    # final world geometry",
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
class DebugChipWorldFrame:
    """Placed world-frame for one chip drawing.

    Attributes:
        topLeft: Inclusive `(columnIndex, rowIndex)` of the full chip drawing.
        bottomRight: Inclusive `(columnIndex, rowIndex)` of the full chip
            drawing.
        widthColumns: Width of the full chip drawing in world columns.
        heightRows: Height of the full chip drawing in world rows.
    """

    topLeft: tuple[int, int]
    bottomRight: tuple[int, int]
    widthColumns: int
    heightRows: int

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public frame fields intended for interactive inspection.
        """

        return [
            "bottomRight",
            "heightRows",
            "topLeft",
            "widthColumns",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            One-line summary of the chip world-frame.
        """

        return (
            "<chip-world-frame "
            f"topLeft={self.topLeft} "
            f"bottomRight={self.bottomRight} "
            f"size={self.widthColumns}x{self.heightRows}>"
        )


@dataclass(frozen=True)
class DebugChipInternalBoardHandle:
    """Interactive handle for one chip-local board harmonization artifact."""

    debugContext: NewEngineDebugContext
    chipId: ChipId

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "raw_get",
            "schema_get",
            "summary_text",
            "wiring_text",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<chip-internal-board {_chipTitleText_build(self.chipId)}>"

    def raw_get(self):
        """Return the raw canonical chip result."""

        return self.debugContext.chipResult_get(self.chipId)

    def schema_get(self) -> ChipInternalBoardSchema:
        """Return the normalized board-compatible chip-local schema."""

        chipResult = self.debugContext.chipResult_get(self.chipId)
        assert result_isOkCheck(chipResult)
        return chipInternalBoardSchema_build(chipResult.value)

    def wiring_text(self) -> str:
        """Return normalized chip-local wiring declarations as readable text."""

        schema = self.schema_get()
        if not schema.wires:
            return "chip-internal board wiring:\n  <none>"
        lines = ["chip-internal board wiring:"]
        for wire in schema.wires:
            lines.append(
                "  "
                f"{wire.sourceTerminalName}:{wire.destinationTerminalName}"
                f"  ({wire.wiringDeclaration})"
            )
        return "\n".join(lines)

    def summary_text(self) -> str:
        """Return a readable summary of the harmonized chip-local schema."""

        schema = self.schema_get()
        lines = [
            f"chip-internal board for {schema.chipTitle}",
            f"  sense: {schema.sense.value}",
            (
                "  west terminals: "
                + (", ".join(schema.westTerminalNames) if schema.westTerminalNames else "<none>")
            ),
            (
                "  east terminals: "
                + (", ".join(schema.eastTerminalNames) if schema.eastTerminalNames else "<none>")
            ),
            f"  wires: {len(schema.wires)}",
        ]
        return "\n".join(lines)

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
            "all_text",
            "chipByTitle_get",
            "chip_get",
            "count_get",
            "ids_get",
            "location_get",
            "locations_get",
            "names_get",
            "placement_get",
            "root_get",
            "routes_get",
            "schematic_text",
            "size_get",
            "summary_text",
            "terminals_get",
            "terminals_getLocalPositions",
            "terminals_getWorldPositions",
            "title_get",
            "worldFrame_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<chips>"

    def all_get(self) -> tuple[BoardChip, ...]:
        """Return all canonical chips as interactive handles."""
        return tuple(
            _chipHandle_build(debugContext=self.debugContext, chipId=chip.chipId)
            for chip in self.debugContext.chips_getAll()
        )

    def count_get(self) -> int:
        """Return canonical chip count."""
        return len(self.all_get())

    def ids_get(self) -> tuple["ChipId", ...]:
        """Return all canonical chip ids."""
        return self.debugContext.chipIds_getAll()

    def names_get(self) -> tuple[str, ...]:
        """Return stable human-readable chip names."""
        return tuple(
            f"{chipId.moduleName}:{chipId.functionName}" for chipId in self.ids_get()
        )

    def all_text(self) -> str:
        """Return readable summaries for all canonical chips."""
        return "\n\n".join(
            self.summary_text(chipId.moduleName, chipId.functionName)
            for chipId in self.ids_get()
        )

    def root_get(self):
        """Return the canonical root chip as an interactive handle."""
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=self.debugContext.circuitDocument.rootChipRef.chipId,
        )

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

    def terminals_getLocalPositions(
        self,
        moduleName: str,
        functionName: str,
        wall: str,
    ) -> dict[str, tuple[int, int]]:
        """Return chip-local terminal positions on one wall for one chip.

        Args:
            moduleName: Canonical chip module name.
            functionName: Canonical chip function name.
            wall: Lowercase wall name such as ``"west"`` or ``"east"``.

        Returns:
            Mapping from terminal name to inclusive chip-local
            ``(columnIndex, rowIndex)`` positions.
        """

        return _chipTerminalLocalPositions_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
            wall=wall,
        )

    def terminals_getWorldPositions(
        self,
        moduleName: str,
        functionName: str,
        wall: str,
    ) -> dict[str, tuple[int, int]]:
        """Return world-coordinate terminal positions on one wall for one chip.

        Args:
            moduleName: Canonical chip module name.
            functionName: Canonical chip function name.
            wall: Lowercase wall name such as ``"west"`` or ``"east"``.

        Returns:
            Mapping from terminal name to inclusive world
            ``(columnIndex, rowIndex)`` positions.
        """

        return _chipTerminalWorldPositions_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
            wall=wall,
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

    def schematic_text(self, moduleName: str, functionName: str) -> str:
        """Return chip schematic as text."""
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return "\n".join(
            _chipDrawingLines_build(
                debugContext=self.debugContext,
                chipId=chipId,
            )
        )

    def summary_text(self, moduleName: str, functionName: str) -> str:
        """Return one canonical chip as a readable debug summary."""
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return _chipSummaryText_build(
            debugContext=self.debugContext,
            chipId=chipId,
        )

    def worldFrame_get(
        self,
        moduleName: str,
        functionName: str,
    ) -> DebugChipWorldFrame | None:
        """Return the placed world-frame for one canonical chip.

        Args:
            moduleName: Owning module name of the chip.
            functionName: Canonical function name of the chip.

        Returns:
            Typed world-frame record for the chip drawing when placed,
            otherwise `None`.
        """

        return _chipWorldFrameOrNone_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def chip_get(self, moduleName: str, functionName: str) -> BoardChip:
        """Return an interactive handle for one canonical chip."""
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def chipByTitle_get(self, chipTitle: str) -> BoardChip:
        """Return an interactive handle from one `module:function` title."""

        moduleName, functionName = _chipTitleParts_build(chipTitle)
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def __getitem__(self, chipTitle: str) -> BoardChip:
        """Return an interactive handle using index syntax."""

        return self.chipByTitle_get(chipTitle)


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
    def _tagged_name(self) -> str:
        """Canonical name including optional region tag."""

        baseName = self.name
        tag = self.routingZoneRegionId.routingZoneRegionTag
        return f"{baseName}:{tag}" if tag else baseName

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
    def _geometry(self) -> RoutingZoneRegionFrame:
        """Raw RoutingZoneRegionFrame."""
        return self.routingZoneRegionFrame


_REGION_SYMBOLS: dict[str, str] = {
    "west/inter_routing_longitude": "▌",
    "west/inter_routing_fan_in_out": "🬗",
    "west/inter_routing_transition": "X",
    "west/chip_terminal": "░",
    "west/intra_routing_fan_in_out": "🬤",
    "west/intra_routing_transition": "x",
    "west/intra_routing_longitude": "🭲",
    "east/intra_routing_longitude": "🭵",
    "east/intra_routing_transition": "x",
    "east/intra_routing_fan_in_out": "🮥",
    "east/chip_terminal": "▒",
    "east/inter_routing_transition": "X",
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
    columnOffset: int | None = None,
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

    displayStartColumn: int = (
        colBreaks[0] if columnOffset is None else max(0, columnOffset)
    )
    displayEndColumn: int = colBreaks[-1]
    if displayStartColumn >= displayEndColumn:
        return []

    visibleColBreaks: list[int] = sorted(
        {
            displayStartColumn,
            displayEndColumn,
            *(
                worldColumn
                for worldColumn in colBreaks
                if displayStartColumn <= worldColumn <= displayEndColumn
            ),
        }
    )

    if mode == "schematic":
        _minW, _maxW, _minH = 3, 8, 1
        colWidths = [
            max(_minW, min(_maxW, visibleColBreaks[i + 1] - visibleColBreaks[i]))
            for i in range(len(visibleColBreaks) - 1)
        ]
        rowHeights = [
            max(_minH, rowBreaks[i + 1] - rowBreaks[i])
            for i in range(len(rowBreaks) - 1)
        ]
    else:
        colWidths = [
            visibleColBreaks[i + 1] - visibleColBreaks[i]
            for i in range(len(visibleColBreaks) - 1)
        ]
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
        clippedHorizontalStart: int = max(f.horizontalStart, displayStartColumn)
        clippedHorizontalEnd: int = min(f.horizontalEnd_calculate(), displayEndColumn)
        if clippedHorizontalStart >= clippedHorizontalEnd:
            continue
        cbs = visibleColBreaks.index(clippedHorizontalStart)
        cbe = visibleColBreaks.index(clippedHorizontalEnd)
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
    for i, worldCol in enumerate(visibleColBreaks[:-1]):
        marker = str(worldCol % 100)
        dcs = colStarts[i]
        for ci, ch in enumerate(marker):
            if dcs + ci < totalCols:
                rulerTop[dcs + ci] = ch

    firstWorldRow: int = rowBreaks[0]
    rowLabelWidth: int = max(len(str(rowBreaks[-1] - 1)), 2)
    lines: list[str] = [f"{0:>{rowLabelWidth}}: {''.join(rulerTop)}"]
    for rowIndex, row in enumerate(grid):
        lines.append(f"{firstWorldRow + rowIndex:>{rowLabelWidth}}: {''.join(row)}")
    return lines


@dataclass(frozen=True)
class DebugZoneRegionSetHandle:
    """Interactive handle for the full set of regions in one placed zone."""

    _regions: tuple[DebugZoneRegionHandle, ...]

    def __dir__(self) -> list[str]:
        return [
            "all_get",
            "area_get",
            "grid_text",
            "info_text",
            "names_get",
        ]

    def __repr__(self) -> str:
        return f"<zone.areas  {len(self._regions)} regions>"

    def __iter__(self):
        return iter(self._regions)

    def __len__(self) -> int:
        return len(self._regions)

    def all_get(self) -> tuple[DebugZoneRegionHandle, ...]:
        """Return the raw tuple of all region handles."""
        return self._regions

    def area_get(
        self,
        kindOrKey: str,
        side: str | None = None,
    ) -> DebugZoneRegionHandle | None:
        """Return one region by kind and optional side.

        Args:
            kindOrKey: Either a ``'side/kind'`` key (for example
                ``'west/chip_terminal'``) or a bare kind string.
            side: Optional side override when ``kindOrKey`` is a bare kind.

        Returns:
            Matching ``DebugZoneRegionHandle``, or ``None`` if not found.
        """

        taggedName = kindOrKey
        handle: DebugZoneRegionHandle
        for handle in self._regions:
            if handle._tagged_name == taggedName:
                return handle

        if "/" in kindOrKey:
            sidePart, kindPart = kindOrKey.split("/", 1)
        else:
            kindPart = kindOrKey
            sidePart = side

        if ":" in kindPart:
            kindPart, tagPart = kindPart.split(":", 1)
        else:
            tagPart = None

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

        for handle in self._regions:
            if (
                handle.routingZoneRegionId.routingZoneRegionKind is wantKind
                and handle.routingZoneRegionId.routingZoneRegionSide is wantSide
                and (
                    tagPart is None
                    or handle.routingZoneRegionId.routingZoneRegionTag == tagPart
                )
            ):
                return handle
        return None

    def names_get(self) -> tuple[str, ...]:
        """Return the canonical names of all regions in this zone."""

        return tuple(handle.name for handle in self._regions)

    def info_text(self) -> str:
        """Return a formatted text block with every property of every area."""
        lines: list[str] = []
        handle: DebugZoneRegionHandle
        for handle in self._regions:
            lines.append(f"  {handle.name}")
            lines.append(f"    kind     : {handle.kind}")
            lines.append(f"    side     : {handle.side}")
            lines.append(f"    frame    : {handle.frame}")
            lines.append(f"    geometry : {handle._geometry}")
        return "\n".join(lines)

    def grid_text(
        self,
        mode: str = "pixel",
        columnOffset: int | None = None,
    ) -> str:
        """Return a labelled ASCII fill-grid of every region.

        Args:
            mode: ``'pixel'`` (default) — one display cell per world unit;
                  ``'schematic'`` — narrow bands widened to minimum 3 chars.
            columnOffset: Optional world-column offset for the left edge of the
                rendered crop. When omitted, the crop starts at the first
                visible region column.

        Returns:
            Multi-line string: column ruler, filled grid, then legend.
        """
        regions = self._regions
        if not regions:
            return "<no regions>"

        labels = [_REGION_SYMBOLS.get(region.name, "?") for region in regions]
        gridLines = _regionDrawGrid_build(
            regions,
            labels,
            mode,
            columnOffset=columnOffset,
        )

        legendLines: list[str] = ["", "legend:"]
        for i, region in enumerate(regions):
            horizontalEndInclusive: int = (
                region.routingZoneRegionFrame.horizontalEnd_calculate() - 1
            )
            verticalEndInclusive: int = (
                region.routingZoneRegionFrame.verticalEnd_calculate() - 1
            )
            legendLines.append(
                "  "
                f"{labels[i]}   {region._tagged_name}  "
                f"[col={region.routingZoneRegionFrame.horizontalStart}..{horizontalEndInclusive}  "
                f"row={region.routingZoneRegionFrame.verticalStart}..{verticalEndInclusive}  "
                f"span=({region.routingZoneRegionFrame.horizontalSpan}w x "
                f"{region.routingZoneRegionFrame.verticalSpan}h)]"
            )

        return "\n".join(gridLines + legendLines)

@dataclass(frozen=True)
class DebugZoneAreaView:
    """Dictionary-like view over partitioned zone regions with draw support."""

    _kernel_map: dict[str, DebugZoneRegionSetHandle]

    def __dir__(self) -> list[str]:
        return list(self._kernel_map.keys()) + ["grid_text"]

    def __getitem__(self, key: str) -> DebugZoneRegionSetHandle:
        return self._kernel_map[key]

    def keys(self):
        return self._kernel_map.keys()

    def values(self):
        return self._kernel_map.values()

    def items(self):
        return self._kernel_map.items()

    def __repr__(self) -> str:
        return f"<partitioned-areas: {list(self._kernel_map.keys())}>"

    def grid_text(
        self,
        mode: str = "pixel",
        columnOffset: int | None = None,
    ) -> str:
        """Return all partitioned regions combined as text."""
        # For now, we combine all regions into one set and draw
        all_regions = []
        for handle in self._kernel_map.values():
            all_regions.extend(handle._regions)
        return DebugZoneRegionSetHandle(_regions=tuple(all_regions)).grid_text(
            mode=mode,
            columnOffset=columnOffset,
        )


@dataclass(frozen=True)
class DebugKernelWire:
    """One directed symbolic wire entry in a kernel wiring scope.

    Attributes:
        sourceEndpointText: Canonical source endpoint text in
            `module.func.signal` form.
        destinationEndpointText: Canonical destination endpoint text in
            `module.func.signal` form.
        sourceChipRef: Owning chip reference for the source endpoint.
        destinationChipRef: Owning chip reference for the destination endpoint.
        sourceTerminalName: Canonical terminal/signal name on the source chip.
        destinationTerminalName: Canonical terminal/signal name on the
            destination chip.
        sourceTerminalSide: Physical terminal side for the source endpoint.
        destinationTerminalSide: Physical terminal side for the destination
            endpoint.
        isReturn: Whether this directed wire is a return-path obligation rather
            than a forward-path obligation.
    """

    sourceEndpointText: str
    destinationEndpointText: str
    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    sourceTerminalName: str
    destinationTerminalName: str
    sourceTerminalSide: ChipTerminalSide
    destinationTerminalSide: ChipTerminalSide
    isReturn: bool = False

    def wireText_get(self) -> str:
        """Return the canonical `source:destination` text form.

        Returns:
            Canonical directed wire text for this symbolic wire.
        """

        return f"{self.sourceEndpointText}:{self.destinationEndpointText}"

    def __str__(self) -> str:
        """Return the canonical one-line wiring text.

        Returns:
            Canonical directed wire text for this symbolic wire.
        """

        return self.wireText_get()


@dataclass(frozen=True)
class DebugKernelWiringHandle:
    """Inspectable symbolic wiring surface for one routing kernel.

    This handle is the first symbolic routing surface exposed in the REPL. It
    owns the directed wires visible in one kernel scope and exposes the
    quarantine symbolic solver used by the `symbolic-kernel-routing` branch.

    Attributes:
        debugContext: Live debug context for the current REPL session.
        routingZoneId: Owning routing-zone id for this wiring scope.
        side: Kernel side label such as `intra` or `west`.
        kernel: Raw routing-kernel model that defines the current board scope.
        _wires: Directed wires currently visible in this kernel scope.
    """

    debugContext: NewEngineDebugContext
    routingZoneId: RoutingZoneId
    side: str
    kernel: RoutingKernel
    _wires: tuple[DebugKernelWire, ...]

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public symbolic wiring methods intended for interactive use.
        """

        return [
            "algebraic_text",
            "all_get",
            "board_get",
            "channels_get",
            "list_text",
            "solver_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label summarizing this wiring scope.
        """

        return f"<kernel-wiring {len(self._wires)} wire(s)>"

    def all_get(self) -> tuple[DebugKernelWire, ...]:
        """Return all directed wires in stable display order.

        Returns:
            All symbolic wires visible in this kernel scope.
        """

        return self._wires

    def board_get(self) -> DebugKernelBoardHandle:
        """Return the symbolic board visible in this wiring scope.

        Returns:
            Board handle derived from the current kernel geometry.
        """

        return _kernelBoard_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
        )

    def channels_get(self) -> DebugKernelChannelsHandle:
        """Return the channel collection visible in this wiring scope.

        Returns:
            Symbolic channel collection derived from the current kernel board.
        """

        return self.board_get().channels_get()

    def solver_get(self) -> DebugKernelSolverHandle:
        """Return the quarantine symbolic solver for this wiring scope.

        Returns:
            Solver handle bound to this exact wiring scope and board.
        """

        return DebugKernelSolverHandle(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            board=self.board_get(),
            wiring=self,
        )

    def list_text(self) -> str:
        """Return one directed `source:destination` wire per line.

        Returns:
            Multi-line text containing one canonical directed wire per line.
        """

        if not self._wires:
            return "<no wiring in this kernel>"
        return "\n".join(kernelWire.wireText_get() for kernelWire in self._wires)

    def algebraic_text(self, endpointText: str) -> str:
        """Return symbolic algebraic path text for wires touching one endpoint.

        Args:
            endpointText: Endpoint text or full directed wire text used to
                select one or more wires in this scope.

        Returns:
            Algebraic path text for matching wires, or an explanatory fallback
            string when no matching wire exists.

        FUTURE UPDATES:
            Expand beyond the current quarantine intra/WTE solver once the full
            board and algebra layers are implemented.
        """

        matchingWires: tuple[DebugKernelWire, ...] = tuple(
            kernelWire
            for kernelWire in self._wires
            if endpointText in (
                kernelWire.sourceEndpointText,
                kernelWire.destinationEndpointText,
                kernelWire.wireText_get(),
            )
        )
        if not matchingWires:
            return f"<no wiring for endpoint {endpointText}>"
        return self.solver_get().algebraic_text(endpointText)


@dataclass(frozen=True)
class DebugKernelLaneHandle:
    """Inspectable lane handle for one symbolic channel.

    Attributes:
        channelName: Canonical symbolic channel name such as `nLat`.
        laneIndex: One-based lane index inside the owning channel.
    """

    channelName: str
    laneIndex: int

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public lane inspection methods intended for interactive use.
        """

        return ["canonicalName_get", "index_get"]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label for this symbolic lane.
        """

        return f"<lane {self.channelName}[{self.laneIndex}]>"

    def canonicalName_get(self) -> str:
        """Return the canonical symbolic name for this lane.

        Returns:
            Canonical lane text in `channel[index]` form.
        """

        return f"{self.channelName}[{self.laneIndex}]"

    def index_get(self) -> int:
        """Return the one-based lane index.

        Returns:
            One-based lane index inside the owning channel.
        """

        return self.laneIndex


@dataclass(frozen=True)
class DebugKernelLanesHandle:
    """Inspectable lane collection for one symbolic channel.

    Attributes:
        channelName: Canonical symbolic channel name for this lane collection.
        laneCount: Number of lanes currently exposed by the channel.
    """

    channelName: str
    laneCount: int

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public lane-collection methods intended for interactive use.
        """

        return ["all_get", "count_get", "lane_get", "list_text"]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label for this lane collection.
        """

        return f"<lanes {self.channelName} x{self.laneCount}>"

    def all_get(self) -> tuple[DebugKernelLaneHandle, ...]:
        """Return all lanes in stable index order.

        Returns:
            All lane handles exposed by this channel in increasing index order.
        """

        return tuple(
            DebugKernelLaneHandle(
                channelName=self.channelName,
                laneIndex=laneIndex,
            )
            for laneIndex in range(1, self.laneCount + 1)
        )

    def count_get(self) -> int:
        """Return the number of lanes in this channel.

        Returns:
            Lane count for the owning symbolic channel.
        """

        return self.laneCount

    def lane_get(self, laneIndex: int) -> DebugKernelLaneHandle | None:
        """Return one lane by one-based index.

        Args:
            laneIndex: One-based lane index to retrieve.

        Returns:
            Matching lane handle when the index is valid, otherwise `None`.
        """

        if laneIndex < 1 or laneIndex > self.laneCount:
            return None
        return DebugKernelLaneHandle(
            channelName=self.channelName,
            laneIndex=laneIndex,
        )

    def list_text(self) -> str:
        """Return all lane canonical names in stable order.

        Returns:
            Multi-line text containing one canonical lane name per line.
        """

        return "\n".join(
            laneHandle.canonicalName_get() for laneHandle in self.all_get()
        )


@dataclass(frozen=True)
class DebugKernelChannelHandle:
    """Inspectable symbolic channel handle.

    Attributes:
        channelName: Canonical symbolic channel name such as `wLong`.
        laneCount: Number of lanes currently exposed by this channel.
    """

    channelName: str
    laneCount: int

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public channel methods intended for interactive use.
        """

        return ["lanes_get", "name_get", "summary_text"]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label for this symbolic channel.
        """

        return f"<channel {self.channelName} x{self.laneCount}>"

    def lanes_get(self) -> DebugKernelLanesHandle:
        """Return the lane collection for this channel.

        Returns:
            Lane collection handle for this symbolic channel.
        """

        return DebugKernelLanesHandle(
            channelName=self.channelName,
            laneCount=self.laneCount,
        )

    def name_get(self) -> str:
        """Return the canonical symbolic name for this channel.

        Returns:
            Canonical symbolic channel name.
        """

        return self.channelName

    def summary_text(self) -> str:
        """Return a short textual summary of this channel.

        Returns:
            One-line summary containing the channel name and lane count.
        """

        return f"{self.channelName} ({self.laneCount} lanes)"


@dataclass(frozen=True)
class DebugKernelChannelsHandle:
    """Inspectable channel collection for one kernel board.

    Attributes:
        _channelsByName: Channel handles keyed by canonical symbolic name.
    """

    _channelsByName: dict[str, DebugKernelChannelHandle]

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public channel-collection methods intended for interactive use.
        """

        return ["all_get", "channel_get", "list_text"]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label listing the visible channel names.
        """

        return f"<channels {list(self._channelsByName.keys())}>"

    def all_get(self) -> tuple[DebugKernelChannelHandle, ...]:
        """Return all channels in stable display order.

        Returns:
            All symbolic channel handles in display order.
        """

        return tuple(self._channelsByName.values())

    def channel_get(self, channelName: str) -> DebugKernelChannelHandle | None:
        """Return one symbolic channel by canonical name.

        Args:
            channelName: Canonical symbolic channel name such as `nLat`.

        Returns:
            Matching channel handle when present, otherwise `None`.
        """

        return self._channelsByName.get(channelName)

    def list_text(self) -> str:
        """Return all channels as one-line summaries.

        Returns:
            Multi-line text containing one summary line per channel.
        """

        return "\n".join(
            channelHandle.summary_text() for channelHandle in self.all_get()
        )


@dataclass(frozen=True)
class DebugKernelBoardHandle:
    """Inspectable symbolic board for one kernel scope.

    The board is the quarantine symbolic substrate derived from kernel geometry
    before any symbolic wire is solved. It is intentionally upstream of the
    symbolic solver and downstream of realized region geometry.

    Attributes:
        routingZoneId: Owning routing-zone id for this board.
        side: Kernel side label such as `intra`.
        kernel: Raw routing-kernel model that owns the source geometry.
        boardBackend: Active board implementation backing this handle.
        boardModel: First-class board-domain model built from the kernel's
            placed-zone geometry and exact attach-point truth.
        channels: Symbolic channels derived from the kernel region set.
    """

    routingZoneId: RoutingZoneId
    side: str
    kernel: RoutingKernel
    boardBackend: str
    boardModel: DomainBoard
    channels: DebugKernelChannelsHandle

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public board-inspection methods intended for interactive use.
        """

        return [
            "boundaries_get",
            "boundary_get",
            "backend_get",
            "channels_get",
            "effective_get",
            "geometry_get",
            "geometry_text",
            "minimumCrossbarSpan_get",
            "model_get",
            "problems_get",
            "sense_get",
            "substrate_get",
            "summary_text",
            "terminal_get",
            "terminals_get",
            "validation_text",
            "worldFrame_get",
            "worldGridCoord_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label summarizing this symbolic board.
        """

        return f"<board {self.side} of {self.routingZoneId.id}>"

    def channels_get(self) -> DebugKernelChannelsHandle:
        """Return the symbolic channels exposed by this board.

        Returns:
            Symbolic channel collection derived from the board geometry.
        """

        return self.channels

    def backend_get(self) -> str:
        """Return the board backend that produced this handle."""

        return self.boardBackend

    def model_get(self) -> DomainBoard:
        """Return the underlying first-class board-domain object."""

        return self.boardModel

    def substrate_get(self) -> DebugKernelBoardHandle:
        """Return the raw substrate board behind this operational board.

        The substrate board preserves the same routing substrate and exact
        terminal positions but does not expose doctrine-derived effective
        boundaries. This is the comparison surface for inspecting what the
        board looked like before effective-boundary policy was applied.
        """

        return DebugKernelBoardHandle(
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            boardBackend=self.boardBackend,
            boardModel=self.boardModel.substrate_get(),
            channels=self.channels,
        )

    def effective_get(self) -> DebugKernelBoardHandle:
        """Return the doctrine-adjusted effective board used operationally."""

        if self.boardModel is self.boardModel.effective_get():
            return self
        return DebugKernelBoardHandle(
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            boardBackend=self.boardBackend,
            boardModel=self.boardModel.effective_get(),
            channels=self.channels,
        )

    def worldGridCoord_get(self):
        """Return the board's world-grid coordinate."""

        return self.boardModel.routingZoneId.id

    def worldFrame_get(self):
        """Return the inclusive world frame occupied by this board."""

        return self.boardModel.worldFrame_get()

    def sense_get(self):
        """Return the board's routing sense doctrine."""

        return self.boardModel.doctrine.sense

    def minimumCrossbarSpan_get(self) -> int:
        """Return the current doctrinal minimum cross-bar span."""

        return self.boardModel.doctrine.minimumCrossbarSpan

    def boundaries_get(self) -> dict[str, RoutingZoneRegionFrame]:
        """Return all effective layout boundaries known to the board."""

        return dict(self.boardModel.geometry.effectiveBoundaryFramesByName)

    def boundary_get(self, boundaryName: str) -> RoutingZoneRegionFrame | None:
        """Return one effective layout boundary by canonical name."""

        return self.boardModel.geometry.effectiveBoundaryFrame_get(boundaryName)

    def terminals_get(self) -> dict[str, dict[str, tuple[int, int]]]:
        """Return exact terminal world positions grouped by chip name."""

        return {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                self.boardModel.geometry.exactTerminalWorldPositionsByChip.items()
            )
        }

    def terminal_get(
        self,
        chipName: str,
        terminalName: str,
    ) -> tuple[int, int] | None:
        """Return one exact terminal world attach point."""

        return self.boardModel.geometry.exactTerminalWorldPosition_get(
            chipName,
            terminalName,
        )

    def problems_get(self) -> tuple[str, ...]:
        """Return human-readable board invariant problems."""

        return boardProblems_get(self.boardModel)

    def validation_text(self) -> str:
        """Return a human-readable board validation summary."""

        problems = self.problems_get()
        if not problems:
            return "board validation:\n  <none>"
        return "board validation:\n" + "\n".join(
            f"  {problem}" for problem in problems
        )

    def geometry_get(self) -> DebugZoneRegionSetHandle:
        """Return the source geometry used to build this board.

        Returns:
            Region-set handle containing the kernel-owned geometry areas from
            which the board channels were derived.
        """

        return DebugZoneRegionSetHandle(
            _regions=tuple(
                DebugZoneRegionHandle(
                    routingZoneRegionId=self.boardModel.geometry.regionIdsByName[
                        regionName
                    ],
                    routingZoneRegionFrame=regionFrame,
                )
                for regionName, regionFrame in (
                    self.boardModel.geometry.regionFramesByName.items()
                )
            )
        )

    def geometry_text(
        self,
        mode: str = "pixel",
        columnOffset: int | None = None,
    ) -> str:
        """Return the source geometry used to build this board as text.

        Args:
            mode: Region rendering mode passed through to the region-set
                geometry view. The default is world-true `pixel` mode so
                displayed rows and columns align directly with world
                coordinates.
            columnOffset: Optional world-column offset for the left edge of the
                rendered crop so the board geometry can be aligned against
                other world-coordinate renders.

        Returns:
            Region-grid text with legend for the kernel geometry that defines
            this board.
        """

        if self.boardBackend == "legacy" or mode != "pixel":
            return self.geometry_get().grid_text(
                mode=mode,
                columnOffset=columnOffset,
            )
        return self.boardModel.geometry_text(columnOffset=columnOffset)

    def summary_text(self) -> str:
        """Return a short textual summary of this board.

        Returns:
            Multi-line summary listing the board identity and visible channels.
        """

        return "\n".join(
            [
                f"board {self.side} of {self.routingZoneId.id}",
                f"worldFrame {self.boardModel.worldFrame_get()}",
                self.channels.list_text(),
            ]
        )


@dataclass(frozen=True)
class DebugKernelSolverHandle:
    """Quarantine symbolic solver handle for one kernel wiring scope.

    This solver is intentionally isolated inside the debug layer. It is the
    live experimental surface for symbolic routing policy and must not be
    mistaken for the production kernel solver in `src/signalflow/routing/`.

    Attributes:
        debugContext: Live debug context for the current REPL session.
        routingZoneId: Owning routing-zone id for this solver scope.
        side: Kernel side label such as `intra`.
        kernel: Raw routing-kernel model that defines the current board.
        board: Symbolic board used as the legal substrate for this solver.
        wiring: Symbolic wiring scope solved by this handle.
        rotationSense: Quarantine symbolic rotation policy.
        laneFillSense: Quarantine symbolic lane-fill policy.
    """

    debugContext: NewEngineDebugContext
    routingZoneId: RoutingZoneId
    side: str
    kernel: RoutingKernel
    board: DebugKernelBoardHandle
    wiring: DebugKernelWiringHandle
    rotationSense: RoutingZoneChannelSense = RoutingZoneChannelSense.CLOCKWISE
    laneFillSense: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_START
    )

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public solver methods intended for interactive experimentation.
        """

        return [
            "algebraic_text",
            "laneFillSense_get",
            "list_text",
            "policy_set",
            "rotationSense_get",
            "solution_get",
            "summary_text",
            "wiring_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label summarizing the current symbolic policy.
        """

        return (
            "<kernel-solver "
            f"rotation={self.rotationSense.value} "
            f"fill={self.laneFillSense.value}>"
        )

    def wiring_get(self) -> DebugKernelWiringHandle:
        """Return the wiring scope solved by this solver.

        Returns:
            Symbolic wiring handle bound to this solver.
        """

        return self.wiring

    def rotationSense_get(self) -> RoutingZoneChannelSense:
        """Return the current symbolic rotation sense.

        Returns:
            Current symbolic rotation policy enum.
        """

        return self.rotationSense

    def laneFillSense_get(self) -> RoutingLaneAttachmentSense:
        """Return the current lane fill sense.

        Returns:
            Current symbolic lane-fill policy enum.
        """

        return self.laneFillSense

    def policy_set(
        self,
        rotationSense: RoutingZoneChannelSense | None = None,
        laneFillSense: RoutingLaneAttachmentSense | None = None,
    ) -> DebugKernelSolverHandle:
        """Return a derived solver with updated symbolic policy.

        Args:
            rotationSense: Optional replacement rotation policy.
            laneFillSense: Optional replacement lane-fill policy.

        Returns:
            New solver handle that shares the same board and wiring scope but
            uses the requested symbolic policy.
        """

        return DebugKernelSolverHandle(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            board=self.board,
            wiring=self.wiring,
            rotationSense=rotationSense or self.rotationSense,
            laneFillSense=laneFillSense or self.laneFillSense,
        )

    def summary_text(self) -> str:
        """Return the current quarantine solver configuration.

        Returns:
            Multi-line summary of the active symbolic policy and wire count.
        """

        return "\n".join(
            [
                "kernel symbolic solver",
                f"  rotationSense: {self.rotationSense.value}",
                f"  laneFillSense: {self.laneFillSense.value}",
                f"  wireCount: {len(self.wiring.all_get())}",
            ]
        )

    def list_text(self) -> str:
        """Return algebraic paths for all wires in this scope.

        Returns:
            Multi-line algebraic path text for every wire in this solver scope.
        """

        return "\n".join(
            self._wireAlgebraicText_build(kernelWire)
            for kernelWire in self.wiring.all_get()
        )

    def algebraic_text(self, endpointText: str) -> str:
        """Return symbolic algebraic path text for wires touching one endpoint.

        Args:
            endpointText: Endpoint text or full directed wire text used to
                select one or more wires in this solver scope.

        Returns:
            Algebraic path text for matching wires, or an explanatory fallback
            string when no matching wire exists.
        """

        matchingWires: tuple[DebugKernelWire, ...] = tuple(
            kernelWire
            for kernelWire in self.wiring.all_get()
            if endpointText in (
                kernelWire.sourceEndpointText,
                kernelWire.destinationEndpointText,
                kernelWire.wireText_get(),
            )
        )
        if not matchingWires:
            return f"<no wiring for endpoint {endpointText}>"
        return "\n".join(
            self._wireAlgebraicText_build(kernelWire)
            for kernelWire in matchingWires
        )

    def _wireAlgebraicText_build(self, kernelWire: DebugKernelWire) -> str:
        """Build quarantine algebraic path text for one kernel wire.

        Args:
            kernelWire: Directed symbolic wire to solve.

        Returns:
            Algebraic path text produced by the quarantine symbolic solver.
        """

        return _kernelWireAlgebraicText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            wiring=self.wiring,
            kernelWire=kernelWire,
            rotationSense=self.rotationSense,
            laneFillSense=self.laneFillSense,
        )

    def solution_get(self) -> DebugKernelSolutionHandle:
        """Return the symbolic solution object for this solver configuration.

        Returns:
            Symbolic solution handle containing the algebraic solve for every
            wire in this solver scope.
        """

        solvedWires: tuple[DebugKernelSolvedWire, ...] = tuple(
            DebugKernelSolvedWire(
                kernelWire=kernelWire,
                algebraicPathText=self._wireAlgebraicText_build(kernelWire),
            )
            for kernelWire in self.wiring.all_get()
        )
        return DebugKernelSolutionHandle(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            board=self.board,
            wiring=self.wiring,
            _solvedWires=solvedWires,
        )


@dataclass(frozen=True)
class DebugKernelSolvedWire:
    """One solved symbolic wire path in a kernel solution.

    Attributes:
        kernelWire: Directed symbolic wire that was solved.
        algebraicPathText: Canonical algebraic path text for the solved wire.
    """

    kernelWire: DebugKernelWire
    algebraicPathText: str

    def wireText_get(self) -> str:
        """Return the canonical directed wire identity.

        Returns:
            Canonical `source:destination` text for the solved wire.
        """

        return self.kernelWire.wireText_get()


@dataclass(frozen=True)
class DebugKernelSolutionHandle:
    """Inspectable symbolic solution for one kernel board and wiring scope.

    Attributes:
        debugContext: Live debug context for the current REPL session.
        routingZoneId: Owning routing-zone id for this solution scope.
        side: Kernel side label such as `intra`.
        kernel: Raw routing-kernel model that owns the solved board.
        board: Symbolic board that constrained the solve.
        wiring: Symbolic wiring solved by this solution.
        _solvedWires: Solved wire paths in stable display order.
    """

    debugContext: NewEngineDebugContext
    routingZoneId: RoutingZoneId
    side: str
    kernel: RoutingKernel
    board: DebugKernelBoardHandle
    wiring: DebugKernelWiringHandle
    _solvedWires: tuple[DebugKernelSolvedWire, ...]

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public symbolic solution methods intended for interactive use.
        """

        return ["algebraic_text", "all_get", "list_text", "wiring_get"]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label summarizing the solved wire count.
        """

        return f"<kernel-solution {len(self._solvedWires)} wire(s)>"

    def all_get(self) -> tuple[DebugKernelSolvedWire, ...]:
        """Return all solved wires in stable display order.

        Returns:
            Solved symbolic wires for this kernel scope.
        """

        return self._solvedWires

    def wiring_get(self) -> DebugKernelWiringHandle:
        """Return the symbolic wiring solved by this solution.

        Returns:
            Wiring handle used to build this symbolic solution.
        """

        return self.wiring

    def algebraic_text(self, endpointText: str) -> str:
        """Return symbolic algebraic path text for matching solved wires.

        Args:
            endpointText: Endpoint text or full directed wire text used to
                select one or more solved wires in this solution.

        Returns:
            Algebraic path text for matching solved wires, or an explanatory
            fallback string when no matching wire exists.
        """

        matchingSolvedWires: tuple[DebugKernelSolvedWire, ...] = tuple(
            solvedWire
            for solvedWire in self._solvedWires
            if endpointText in (
                solvedWire.kernelWire.sourceEndpointText,
                solvedWire.kernelWire.destinationEndpointText,
                solvedWire.kernelWire.wireText_get(),
            )
        )
        if not matchingSolvedWires:
            return f"<no wiring for endpoint {endpointText}>"
        return "\n".join(
            solvedWire.algebraicPathText for solvedWire in matchingSolvedWires
        )

    def list_text(self) -> str:
        """Return all solved algebraic paths in stable display order.

        Returns:
            Multi-line algebraic path text for every solved wire.
        """

        return "\n".join(
            solvedWire.algebraicPathText for solvedWire in self._solvedWires
        )


@dataclass(frozen=True)
class DebugKernelMaterializedWire:
    """Materialized geometry for one symbolic solved wire.

    Attributes:
        solvedWire: Solved symbolic wire from the solution layer.
        tokenStartPoints: Ordered world-coordinate start points for the five
            symbolic non-endpoint tokens in the algebraic path.
        routePoints: Ordered world-coordinate points chosen by the materializer.
        routeCells: Full set of world-coordinate cells traversed by the route.
    """

    solvedWire: DebugKernelSolvedWire
    tokenStartPoints: tuple[tuple[int, int], ...]
    routePoints: tuple[tuple[int, int], ...]
    routeCells: tuple[tuple[int, int], ...]

    def algebraicWorld_text(self) -> str:
        """Return the solved algebraic path annotated with world coordinates.

        Returns:
            Algebraic path text where each non-endpoint symbolic token is
            annotated with the world `(row,col)` coordinate at which that
            segment begins. When the route-point count does not match the
            current quarantine algebra shape, the plain algebraic path text is
            returned unchanged.
        """

        pathTokens: list[str] = self.solvedWire.algebraicPathText.split("::")
        if len(pathTokens) != 7 or len(self.tokenStartPoints) != 5:
            return self.solvedWire.algebraicPathText

        annotatedTokens: list[str] = [pathTokens[0]]
        for tokenText, (columnIndex, rowIndex) in zip(
            pathTokens[1:6],
            self.tokenStartPoints,
            strict=True,
        ):
            annotatedTokens.append(f"{tokenText}@({rowIndex},{columnIndex})")
        annotatedTokens.append(pathTokens[6])
        return "::".join(annotatedTokens)

    def summary_text(self) -> str:
        """Return a readable summary for this materialized wire.

        Returns:
            Multi-line text containing the wire identity, symbolic path, and
            ordered materialized route points.
        """

        pointText: str = " -> ".join(
            f"({columnIndex},{rowIndex})"
            for columnIndex, rowIndex in self.routePoints
        )
        return "\n".join(
            [
                self.solvedWire.wireText_get(),
                f"  algebraic: {self.solvedWire.algebraicPathText}",
                f"  points: {pointText}",
            ]
        )


@dataclass(frozen=True)
class DebugKernelMaterializedSolutionHandle:
    """Inspectable materialized result for one symbolic kernel solution.

    Attributes:
        board: Board used as the substrate for materialization.
        solution: Symbolic solution being materialized.
        _materializedWires: Materialized wire geometry records.
    """

    board: DebugKernelBoardHandle
    solution: DebugKernelSolutionHandle
    _materializedWires: tuple[DebugKernelMaterializedWire, ...]
    _realizedRouteSet: RealizedRouteSet

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion.

        Returns:
            Public materialized-result methods intended for interactive use.
        """

        return [
            "algebraicWorld_text",
            "boundaryViolations_get",
            "boundaryViolations_text",
            "collisions_get",
            "collisions_text",
            "geometry_text",
            "occupancyViolations_get",
            "occupancyViolations_text",
            "occupancy_text",
            "summary_text",
            "wiring_text",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short debug label summarizing the materialized wire count.
        """

        return f"<materialized-solution {len(self._materializedWires)} wire(s)>"

    def summary_text(self) -> str:
        """Return a short summary of the current materialized result.

        Returns:
            Multi-line summary describing the board identity and wire count.
        """

        return "\n".join(
            [
                f"materialized solution on board {self.board.side} of {self.board.routingZoneId.id}",
                f"  wireCount: {len(self._materializedWires)}",
            ]
        )

    def wiring_text(self) -> str:
        """Return materialized wiring summaries for all solved wires.

        Returns:
            Multi-line text containing the algebraic path and materialized
            route points for every wire in this result.
        """

        if not self._materializedWires:
            return "<no materialized wires>"
        return "\n\n".join(
            materializedWire.summary_text()
            for materializedWire in self._materializedWires
        )

    def algebraicWorld_text(self, endpointText: str) -> str:
        """Return world-annotated algebraic text for matching wires.

        Args:
            endpointText: Endpoint text or full directed wire text used to
                select one or more materialized wires in this result.

        Returns:
            Algebraic path text with world-coordinate annotations for matching
            wires, or an explanatory fallback string when no match exists.
        """

        matchingMaterializedWires: tuple[DebugKernelMaterializedWire, ...] = tuple(
            materializedWire
            for materializedWire in self._materializedWires
            if endpointText in (
                materializedWire.solvedWire.kernelWire.sourceEndpointText,
                materializedWire.solvedWire.kernelWire.destinationEndpointText,
                materializedWire.solvedWire.wireText_get(),
            )
        )
        if not matchingMaterializedWires:
            return f"<no wiring for endpoint {endpointText}>"
        return "\n".join(
            materializedWire.algebraicWorld_text()
            for materializedWire in matchingMaterializedWires
        )

    def occupancy_text(self) -> str:
        """Return a symbolic-vs-rendered occupancy report for this result.

        Returns:
            Multi-line text containing symbolic channel-lane claims, shared
            fan usage, and duplicated rendered world cells partitioned by
            fan-versus-non-fan ownership. This is intended to catch
            materialization errors before inspecting the final world render.
        """

        report = self._collisionReport_build()
        occupancy = report["collisions"]
        symbolicChannelClaims = report["claims"]["symbolic_channel"]
        symbolicFanClaims = report["claims"]["symbolic_fan"]

        lines: list[str] = ["symbolic channel claims:"]
        for claimToken in sorted(symbolicChannelClaims):
            lines.append(f"  {claimToken}: {' | '.join(symbolicChannelClaims[claimToken])}")
        lines.append("")
        lines.append("symbolic fan claims:")
        for claimToken in sorted(symbolicFanClaims):
            lines.append(f"  {claimToken}: {' | '.join(symbolicFanClaims[claimToken])}")
        lines.append("")
        lines.append("symbolic channel collisions:")
        lines.extend(
            [
                f"  {entry['token']}: {' | '.join(entry['wires'])}"
                for entry in occupancy["symbolic_channel"]
            ]
            or ["  <none>"]
        )
        lines.append("")
        lines.append("symbolic fan sharing:")
        lines.extend(
            [
                f"  {entry['token']}: {' | '.join(entry['wires'])}"
                for entry in occupancy["symbolic_fan"]
            ]
            or ["  <none>"]
        )
        lines.append("")
        lines.append("rendered board-cell collisions:")
        lines.extend(
            [
                f"  ({entry['cell'][1]},{entry['cell'][0]})"
                f" [{', '.join(entry['regions']) or 'unowned'}]: "
                f"{' | '.join(entry['wires'])}"
                for entry in occupancy["rendered_board_cell"]
            ]
            or ["  <none>"]
        )
        lines.append("")
        lines.append("rendered fan-cell sharing:")
        lines.extend(
            [
                f"  ({entry['cell'][1]},{entry['cell'][0]})"
                f" [{', '.join(entry['regions']) or 'unowned'}]: "
                f"{' | '.join(entry['wires'])}"
                for entry in occupancy["rendered_fan"]
            ]
            or ["  <none>"]
        )
        return "\n".join(lines)

    def occupancyViolations_get(self) -> dict[str, list[dict[str, object]]]:
        """Return structured non-boundary occupancy violations."""

        collisions = self._collisionReport_build()["collisions"]
        return {
            "symbolic_channel": collisions["symbolic_channel"],
            "symbolic_fan": collisions["symbolic_fan"],
            "rendered_board_cell": collisions["rendered_board_cell"],
            "rendered_fan": collisions["rendered_fan"],
        }

    def occupancyViolations_text(self) -> str:
        """Return a text view of occupancy-related collisions."""

        return self.occupancy_text()

    def boundaryViolations_get(self) -> list[dict[str, object]]:
        """Return structured route-vs-boundary violations."""

        return self._collisionReport_build()["collisions"]["boundary"]

    def boundaryViolations_text(self) -> str:
        """Return a text view of boundary-only violations."""

        boundaryViolations = self.boundaryViolations_get()
        if not boundaryViolations:
            return "boundary violations:\n  <none>"
        lines = ["boundary violations:"]
        for entry in boundaryViolations:
            cellText = ", ".join(
                f"({rowIndex},{columnIndex})"
                for columnIndex, rowIndex in entry["cells"]
            )
            lines.extend(
                [
                    f"  {entry['wire']}",
                    f"    boundary: {entry['boundary']}",
                    f"    kind: {entry['kind']}",
                    f"    cells: {cellText}",
                ]
            )
        return "\n".join(lines)

    def collisions_get(self) -> dict[str, object]:
        """Return a structured catch-all collision report."""

        return self._collisionReport_build()

    def collisions_text(self) -> str:
        """Return a readable catch-all collision report."""

        report = self.collisions_get()
        counts = report["counts"]
        collisions = report["collisions"]
        lines = [
            "collisions:",
            f"  boundary: {counts['boundary']}",
            f"  symbolic_channel: {counts['symbolic_channel']}",
            f"  symbolic_fan: {counts['symbolic_fan']}",
            f"  rendered_board_cell: {counts['rendered_board_cell']}",
            f"  rendered_fan: {counts['rendered_fan']}",
        ]
        for category in (
            "boundary",
            "symbolic_channel",
            "symbolic_fan",
            "rendered_board_cell",
            "rendered_fan",
        ):
            entries = collisions[category]
            lines.append("")
            lines.append(f"{category}:")
            if not entries:
                lines.append("  <none>")
                continue
            if category == "boundary":
                for entry in entries:
                    lines.append(f"  {entry['wire']}")
                    lines.append(f"    boundary: {entry['boundary']}")
                    lines.append(f"    kind: {entry['kind']}")
                    lines.append(
                        "    cells: "
                        + ", ".join(
                            f"({rowIndex},{columnIndex})"
                            for columnIndex, rowIndex in entry["cells"]
                        )
                    )
            elif category in {"symbolic_channel", "symbolic_fan"}:
                for entry in entries:
                    lines.append(f"  {entry['token']}: {' | '.join(entry['wires'])}")
            else:
                for entry in entries:
                    lines.append(
                        f"  ({entry['cell'][1]},{entry['cell'][0]}) "
                        f"[{', '.join(entry['regions']) or 'unowned'}]: "
                        f"{' | '.join(entry['wires'])}"
                    )
        return "\n".join(lines)

    def _collisionReport_build(self) -> dict[str, object]:
        """Build one structured collision report for the realized result."""

        symbolicChannelClaims: dict[str, list[str]] = {}
        symbolicFanClaims: dict[str, list[str]] = {}
        cellClaims: dict[tuple[int, int], list[str]] = {}
        cellDirectionsByWire: dict[tuple[int, int], dict[str, frozenset[TrackDirection]]] = {}
        routeCellsByWire: dict[str, set[tuple[int, int]]] = {}
        geometry = self.board.geometry_get()
        boardGeometry = self.board.boardModel.geometry

        for materializedWire in self._materializedWires:
            wireText = materializedWire.solvedWire.wireText_get()
            routeCellsByWire[wireText] = set(materializedWire.routeCells)
            pathTokens = materializedWire.solvedWire.algebraicPathText.split("::")
            for tokenText in pathTokens[1:6]:
                if re.fullmatch(r"[a-zA-Z]+\[\d+\]", tokenText) is None:
                    continue
                if tokenText in {"wf[0]", "ef[0]"}:
                    symbolicFanClaims.setdefault(tokenText, []).append(wireText)
                    continue
                symbolicChannelClaims.setdefault(tokenText, []).append(wireText)
            for columnIndex, rowIndex in materializedWire.routeCells:
                cellClaims.setdefault((columnIndex, rowIndex), []).append(wireText)
        for realizedRoute in self._realizedRouteSet.realizedRoutes:
            wireText = (
                f"{realizedRoute.sourceChipRef.chipId.moduleName}."
                f"{realizedRoute.sourceChipRef.chipId.functionName}:"
                f"{realizedRoute.destinationChipRef.chipId.moduleName}."
                f"{realizedRoute.destinationChipRef.chipId.functionName}"
            )
            for realizedCell in realizedRoute.cells:
                cellDirectionsByWire.setdefault(
                    (realizedCell.worldCol, realizedCell.worldRow),
                    {},
                )[wireText] = realizedCell.trackCell.directions

        symbolicChannelCollisions: list[dict[str, object]] = []
        for claimToken in sorted(symbolicChannelClaims):
            claimants = symbolicChannelClaims[claimToken]
            if len(claimants) > 1:
                symbolicChannelCollisions.append(
                    {"token": claimToken, "wires": tuple(claimants)}
                )

        symbolicFanSharing: list[dict[str, object]] = []
        for claimToken in sorted(symbolicFanClaims):
            claimants = symbolicFanClaims[claimToken]
            if len(claimants) > 1:
                symbolicFanSharing.append(
                    {"token": claimToken, "wires": tuple(claimants)}
                )

        renderedBoardCollisions: list[dict[str, object]] = []
        renderedFanCollisions: list[dict[str, object]] = []
        collisionExemptRegionKinds: tuple[str, ...] = ("transition",)
        for (columnIndex, rowIndex), claimants in sorted(
            cellClaims.items(),
            key=lambda item: (item[0][1], item[0][0]),
        ):
            if len(claimants) <= 1:
                continue
            regionKinds = _regionTaggedNamesForWorldCell_build(
                geometry=geometry,
                columnIndex=columnIndex,
                rowIndex=rowIndex,
            )
            if any(
                exemptKind in regionName
                for exemptKind in collisionExemptRegionKinds
                for regionName in regionKinds
            ):
                continue
            directionsByWire = cellDirectionsByWire.get((columnIndex, rowIndex), {})
            claimantDirections = [
                directionsByWire.get(claimant, frozenset())
                for claimant in claimants
            ]
            if len(claimantDirections) == 2:
                directions0, directions1 = claimantDirections
                isHorizontal0 = directions0 <= {TrackDirection.EAST, TrackDirection.WEST}
                isVertical0 = directions0 <= {TrackDirection.NORTH, TrackDirection.SOUTH}
                isHorizontal1 = directions1 <= {TrackDirection.EAST, TrackDirection.WEST}
                isVertical1 = directions1 <= {TrackDirection.NORTH, TrackDirection.SOUTH}
                if (isHorizontal0 and isVertical1) or (isVertical0 and isHorizontal1):
                    continue
            entry = {
                "cell": (columnIndex, rowIndex),
                "wires": tuple(claimants),
                "regions": tuple(regionKinds),
            }
            if any("fan_in_out" in regionName for regionName in regionKinds):
                renderedFanCollisions.append(entry)
            else:
                renderedBoardCollisions.append(entry)

        exactTerminalCells: set[tuple[int, int]] = {
            terminalPosition
            for terminalPositions in boardGeometry.exactTerminalWorldPositionsByChip.values()
            for terminalPosition in terminalPositions.values()
        }
        chipDrawCells: set[tuple[int, int]] = set()
        for chipPlacement in boardGeometry.chipDrawPlacementsByChip.values():
            chipFrame = chipPlacement.worldFrame_get()
            for rowIndex in range(chipFrame.topLeft[1], chipFrame.bottomRight[1] + 1):
                for columnIndex in range(chipFrame.topLeft[0], chipFrame.bottomRight[0] + 1):
                    chipDrawCells.add((columnIndex, rowIndex))
        boundaryViolations: list[dict[str, object]] = []
        for boundaryName, frame in self.board.boardModel.geometry.effectiveBoundaryFramesByName.items():
            borderCells = _frameBorderCells_build(frame)
            interiorCells = _frameInteriorCells_build(frame)
            for wireText, routeCells in routeCellsByWire.items():
                overlappingBorderCells = tuple(
                    sorted(
                        (
                            cell
                            for cell in (routeCells & borderCells)
                            if cell not in exactTerminalCells
                            and cell not in chipDrawCells
                            and not any(
                                "chip_terminal" in regionName
                                for regionName in _regionTaggedNamesForWorldCell_build(
                                    geometry=geometry,
                                    columnIndex=cell[0],
                                    rowIndex=cell[1],
                                )
                            )
                        ),
                        key=lambda cell: (cell[1], cell[0]),
                    )
                )
                if overlappingBorderCells:
                    boundaryViolations.append(
                        {
                            "wire": wireText,
                            "boundary": boundaryName,
                            "kind": "border_overlap",
                            "cells": overlappingBorderCells,
                        }
                    )
                overlappingInteriorCells = tuple(
                    sorted(
                        (
                            cell
                            for cell in (routeCells & interiorCells)
                            if cell not in exactTerminalCells
                            and cell not in chipDrawCells
                            and not any(
                                "chip_terminal" in regionName
                                for regionName in _regionTaggedNamesForWorldCell_build(
                                    geometry=geometry,
                                    columnIndex=cell[0],
                                    rowIndex=cell[1],
                                )
                            )
                        ),
                        key=lambda cell: (cell[1], cell[0]),
                    )
                )
                if overlappingInteriorCells:
                    boundaryViolations.append(
                        {
                            "wire": wireText,
                            "boundary": boundaryName,
                            "kind": "interior_overlap",
                            "cells": overlappingInteriorCells,
                        }
                    )

        collisions = {
            "boundary": boundaryViolations,
            "symbolic_channel": symbolicChannelCollisions,
            "symbolic_fan": symbolicFanSharing,
            "rendered_board_cell": renderedBoardCollisions,
            "rendered_fan": renderedFanCollisions,
        }
        counts = {
            category: len(entries) for category, entries in collisions.items()
        }
        return {
            "hasCollisions": any(count > 0 for count in counts.values()),
            "counts": counts,
            "claims": {
                "symbolic_channel": symbolicChannelClaims,
                "symbolic_fan": symbolicFanClaims,
            },
            "collisions": collisions,
        }

    def geometry_text(self) -> str:
        """Return the realized chip-and-wire geometry for this solution.

        Returns:
            Pixel-grid text showing chip bodies, chip labels, and materialized
            route overlay glyphs for this symbolic solution.  Row ``0`` is a
            display-only header that shows the absolute world-column ruler.
            All subsequent rows are labeled with their absolute world-row
            indices so chip frames can be compared directly against
            ``chip.worldFrame_get()`` results.
        """
        baseCanvasLines = boardCanvas_render(
            board=self.board.boardModel,
            realizedRouteSet=self._realizedRouteSet,
        )

        routeCells: set[tuple[int, int]] = {
            routeCell
            for materializedWire in self._materializedWires
            for routeCell in materializedWire.routeCells
        }

        cropFrames: list[DebugChipWorldFrame] = []
        for materializedWire in self._materializedWires:
            for chipRef in (
                materializedWire.solvedWire.kernelWire.sourceChipRef,
                materializedWire.solvedWire.kernelWire.destinationChipRef,
            ):
                chipName = (
                    f"{chipRef.chipId.moduleName}.{chipRef.chipId.functionName}"
                )
                chipPlacement = self.board.boardModel.geometry.chipDrawPlacementsByChip.get(
                    chipName
                )
                if chipPlacement is None:
                    continue
                chipFrame = chipPlacement.worldFrame_get()
                cropFrames.append(
                    DebugChipWorldFrame(
                        topLeft=chipFrame.topLeft,
                        bottomRight=chipFrame.bottomRight,
                        widthColumns=chipFrame.widthColumns,
                        heightRows=chipFrame.heightRows,
                    )
                )
        for frame in self.board.boardModel.geometry.effectiveBoundaryFramesByName.values():
            cropFrames.append(
                DebugChipWorldFrame(
                    topLeft=(frame.horizontalStart, frame.verticalStart),
                    bottomRight=(
                        frame.horizontalEnd_calculate() - 1,
                        frame.verticalEnd_calculate() - 1,
                    ),
                    widthColumns=frame.horizontalSpan,
                    heightRows=frame.verticalSpan,
                )
            )
        wiringLegendLines: list[str] = [
            "",
            "wires:",
            *[
                f"  {materializedWire.solvedWire.wireText_get()}  ->  {materializedWire.solvedWire.algebraicPathText}"
                for materializedWire in self._materializedWires
            ],
        ]
        return realizedGeometry_text(
            baseCanvasLines=baseCanvasLines,
            routeCells=routeCells,
            extraFrames=tuple(cropFrames),
            wiringLegendLines=tuple(wiringLegendLines),
        )


def _kernelSolvedRoutes_get(
    debugContext: NewEngineDebugContext,
    kernel: RoutingKernel,
) -> tuple[RoutingZoneLocalSolvedRoute | RoutingZoneInterconnectSolvedRoute, ...]:
    """Return all solved routes that traverse one kernel's owned regions.

    Args:
        debugContext: Live debug context that owns the solved route layers.
        kernel: Kernel whose owned region ids define the filtering scope.

    Returns:
        Solved local or interconnect routes that traverse at least one region
        owned by the requested kernel.
    """

    allSolvedRoutes: tuple[
        RoutingZoneLocalSolvedRoute | RoutingZoneInterconnectSolvedRoute,
        ...,
    ] = (
        debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        + debugContext.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes
    )
    kernelRegionIds: set[RoutingZoneRegionId] = {
        routingZoneRegion.routingZoneRegionId
        for routingZoneRegion in kernel.routingZoneRegionSet.routingZoneRegions
    }
    return tuple(
        solvedRoute
        for solvedRoute in allSolvedRoutes
        if any(
            traversedRegionId in kernelRegionIds
            for traversedRegionId in solvedRoute.traversedRegionIds
        )
    )


def _chipEndpointText_build(
    chipRef: ChipRef,
    terminalName: str,
) -> str:
    """Build canonical `module.func.signal` endpoint text.

    Args:
        chipRef: Chip reference contributing the `module.func` prefix.
        terminalName: Terminal or signal name to append.

    Returns:
        Canonical endpoint text in `module.func.signal` form.
    """

    chipId: ChipId = chipRef.chipId
    return f"{chipId.moduleName}.{chipId.functionName}.{terminalName}"


def _destinationPortDeclarationOrNone_get(
    circuitDocument: CircuitDocument,
    callRouteObligation: CallRouteObligation,
) -> ChipPortDeclaration | None:
    """Return the destination input-port declaration chosen for one call.

    Args:
        circuitDocument: Validated circuit document that owns the canonical
            chip declarations.
        callRouteObligation: Call obligation whose destination input port must
            be resolved.

    Returns:
        Matching destination input-port declaration when the call maps
        unambiguously, otherwise `None`.
    """

    destinationChipResult = circuitDocument.circuitChipSet.chipResult_get(
        callRouteObligation.destinationChipRef.chipId
    )
    if not result_isOkCheck(destinationChipResult):
        return None

    inputPortDeclarations: tuple[ChipPortDeclaration, ...] = (
        destinationChipResult.value.inputPortDeclarationSet.portDeclarations
    )
    if not inputPortDeclarations:
        return None

    if callRouteObligation.sourcePortDeclaration is not None:
        portDeclaration: ChipPortDeclaration
        for portDeclaration in inputPortDeclarations:
            if portDeclaration == callRouteObligation.sourcePortDeclaration:
                return portDeclaration

    if len(inputPortDeclarations) == 1:
        return inputPortDeclarations[0]

    return None


def _terminalSideOrNone_get(
    circuitDocument: CircuitDocument,
    chipRef: ChipRef,
    terminalName: str,
) -> ChipTerminalSide | None:
    """Return the canonical terminal side for one chip-local terminal name.

    Args:
        circuitDocument: Validated circuit document that owns the canonical
            chip declarations.
        chipRef: Chip whose declared ports should be inspected.
        terminalName: Stable terminal name to resolve.

    Returns:
        Terminal side when the declaration is found, otherwise `None`.
    """

    chipResult = circuitDocument.circuitChipSet.chipResult_get(chipRef.chipId)
    if not result_isOkCheck(chipResult):
        return None

    portDeclaration: ChipPortDeclaration
    for portDeclaration in (
        chipResult.value.inputPortDeclarationSet.portDeclarations
    ):
        if terminalName in {
            portDeclaration.signalName,
            portDeclaration.returnName,
        }:
            return ChipTerminalSide.WEST

    for portDeclaration in (
        chipResult.value.outputPortDeclarationSet.portDeclarations
    ):
        if terminalName in {
            portDeclaration.signalName,
            portDeclaration.returnName,
        }:
            return ChipTerminalSide.EAST

    return None


def _kernelWire_build(
    circuitDocument: CircuitDocument,
    callRouteObligation: CallRouteObligation,
    solvedRoute: RoutingZoneLocalSolvedRoute | RoutingZoneInterconnectSolvedRoute,
) -> DebugKernelWire:
    """Build one directed symbolic wiring record from a solved route.

    Args:
        circuitDocument: Validated circuit document that owns the canonical
            chip port declarations.
        callRouteObligation: Source call obligation for the solved route.
        solvedRoute: Solved route whose direction determines forward versus
            return symbolic wiring.

    Returns:
        Directed symbolic wire record derived from the solved route and the
        call obligation's source and destination port declarations.
    """

    sourcePortDeclaration: ChipPortDeclaration | None = (
        callRouteObligation.sourcePortDeclaration
    )
    destinationPortDeclaration: ChipPortDeclaration | None = (
        _destinationPortDeclarationOrNone_get(
            circuitDocument=circuitDocument,
            callRouteObligation=callRouteObligation,
        )
    )
    solveKindValue: str = solvedRoute.solveKind.value
    isReturnRoute: bool = solveKindValue.endswith("_return")

    if isReturnRoute:
        destinationTerminalName = (
            sourcePortDeclaration.returnName
            if sourcePortDeclaration is not None
            and sourcePortDeclaration.returnName is not None
            else "<missing_return>"
        )
        sourceTerminalName = (
            destinationPortDeclaration.returnName
            if destinationPortDeclaration is not None
            and destinationPortDeclaration.returnName is not None
            else "<missing_return>"
        )
        return DebugKernelWire(
            sourceEndpointText=_chipEndpointText_build(
                chipRef=callRouteObligation.destinationChipRef,
                terminalName=sourceTerminalName,
            ),
            destinationEndpointText=_chipEndpointText_build(
                chipRef=callRouteObligation.sourceChipRef,
                terminalName=destinationTerminalName,
            ),
            sourceChipRef=callRouteObligation.destinationChipRef,
            destinationChipRef=callRouteObligation.sourceChipRef,
            sourceTerminalName=sourceTerminalName,
            destinationTerminalName=destinationTerminalName,
            sourceTerminalSide=_terminalSideOrNone_get(
                circuitDocument=circuitDocument,
                chipRef=callRouteObligation.destinationChipRef,
                terminalName=sourceTerminalName,
            )
            or ChipTerminalSide.WEST,
            destinationTerminalSide=_terminalSideOrNone_get(
                circuitDocument=circuitDocument,
                chipRef=callRouteObligation.sourceChipRef,
                terminalName=destinationTerminalName,
            )
            or ChipTerminalSide.WEST,
            isReturn=True,
        )

    sourceTerminalName = (
        sourcePortDeclaration.signalName
        if sourcePortDeclaration is not None
        and sourcePortDeclaration.signalName is not None
        else "<missing_signal>"
    )
    destinationTerminalName = (
        destinationPortDeclaration.signalName
        if destinationPortDeclaration is not None
        and destinationPortDeclaration.signalName is not None
        else "<missing_signal>"
    )
    return DebugKernelWire(
        sourceEndpointText=_chipEndpointText_build(
            chipRef=callRouteObligation.sourceChipRef,
            terminalName=sourceTerminalName,
        ),
        destinationEndpointText=_chipEndpointText_build(
            chipRef=callRouteObligation.destinationChipRef,
            terminalName=destinationTerminalName,
        ),
        sourceChipRef=callRouteObligation.sourceChipRef,
        destinationChipRef=callRouteObligation.destinationChipRef,
        sourceTerminalName=sourceTerminalName,
        destinationTerminalName=destinationTerminalName,
        sourceTerminalSide=_terminalSideOrNone_get(
            circuitDocument=circuitDocument,
            chipRef=callRouteObligation.sourceChipRef,
            terminalName=sourceTerminalName,
        )
        or ChipTerminalSide.WEST,
        destinationTerminalSide=_terminalSideOrNone_get(
            circuitDocument=circuitDocument,
            chipRef=callRouteObligation.destinationChipRef,
            terminalName=destinationTerminalName,
        )
        or ChipTerminalSide.EAST,
        isReturn=False,
    )


def _kernelChannels_build(kernel: RoutingKernel) -> DebugKernelChannelsHandle:
    """Build symbolic channel handles from one kernel region set.

    Args:
        kernel: Kernel whose routing regions define the current symbolic board.

    Returns:
        Symbolic channel collection derived from the kernel's longitude and
        latitude routing regions.
    """

    laneCountByChannelName: dict[str, int] = {}
    routingZoneRegion = None
    for routingZoneRegion in kernel.routingZoneRegionSet.routingZoneRegions:
        regionKind = routingZoneRegion.routingZoneRegionId.routingZoneRegionKind
        regionSide = routingZoneRegion.routingZoneRegionId.routingZoneRegionSide
        if regionKind not in (
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
        ):
            continue
        prefixBySide: dict[RoutingZoneRegionSide, str] = {
            RoutingZoneRegionSide.WEST: "w",
            RoutingZoneRegionSide.EAST: "e",
            RoutingZoneRegionSide.NORTH: "n",
            RoutingZoneRegionSide.SOUTH: "s",
        }
        prefix = prefixBySide.get(regionSide)
        if prefix is None:
            continue
        if regionKind in (
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
        ):
            channelName = f"{prefix}Long"
            laneCount = routingZoneRegion.routingZoneRegionFrame.horizontalSpan
        else:
            channelName = f"{prefix}Lat"
            laneCount = routingZoneRegion.routingZoneRegionFrame.verticalSpan
        previousLaneCount = laneCountByChannelName.get(channelName, 0)
        laneCountByChannelName[channelName] = max(previousLaneCount, laneCount)

    preferredChannelOrder: tuple[str, ...] = (
        "wLong",
        "nLat",
        "eLong",
        "sLat",
        "wLat",
        "nLong",
        "eLat",
        "sLong",
    )
    orderedChannelsByName: dict[str, DebugKernelChannelHandle] = {}
    channelName: str
    for channelName in preferredChannelOrder:
        laneCount = laneCountByChannelName.get(channelName)
        if laneCount is None:
            continue
        orderedChannelsByName[channelName] = DebugKernelChannelHandle(
            channelName=channelName,
            laneCount=laneCount,
        )
    for channelName in sorted(laneCountByChannelName):
        if channelName in orderedChannelsByName:
            continue
        orderedChannelsByName[channelName] = DebugKernelChannelHandle(
            channelName=channelName,
            laneCount=laneCountByChannelName[channelName],
        )
    return DebugKernelChannelsHandle(_channelsByName=orderedChannelsByName)


def _kernelChannelsFromBoard_build(boardModel: DomainBoard) -> DebugKernelChannelsHandle:
    """Build symbolic channel handles from first-class board geometry."""

    laneCountByChannelName = boardChannelLaneCounts_build(boardModel)
    preferredChannelOrder: tuple[str, ...] = (
        "wLong",
        "nLat",
        "eLong",
        "sLat",
        "wLat",
        "nLong",
        "eLat",
        "sLong",
    )
    orderedChannelsByName: dict[str, DebugKernelChannelHandle] = {}
    for channelName in preferredChannelOrder:
        laneCount = laneCountByChannelName.get(channelName)
        if laneCount is None:
            continue
        orderedChannelsByName[channelName] = DebugKernelChannelHandle(
            channelName=channelName,
            laneCount=laneCount,
        )
    for channelName in sorted(laneCountByChannelName):
        if channelName in orderedChannelsByName:
            continue
        orderedChannelsByName[channelName] = DebugKernelChannelHandle(
            channelName=channelName,
            laneCount=laneCountByChannelName[channelName],
        )
    return DebugKernelChannelsHandle(_channelsByName=orderedChannelsByName)


def _kernelBoard_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
    side: str,
    kernel: RoutingKernel,
) -> DebugKernelBoardHandle:
    """Build a quarantine symbolic board from kernel geometry.

    Args:
        routingZoneId: Owning routing-zone id for the requested board.
        side: Kernel side label such as `intra`.
        kernel: Raw routing-kernel model whose geometry defines the board.

    Returns:
        Symbolic board handle derived from the kernel's region geometry.
    """

    zoneResult = debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZoneId
    )
    if not result_isOkCheck(zoneResult):
        raise RuntimeError(f"Could not build board for missing zone {routingZoneId}")

    boardModel = board_buildFromKernel(
        routingZoneId=routingZoneId,
        side=side,
        routingZone=zoneResult.value,
        kernel=kernel,
        circuitDocument=debugContext.circuitDocument,
        moduleBoundaryPaddingCells=debugContext.placedRoutingZoneGrid.moduleBoxPadding,
    )
    boardBackend = _boardBackend_get()

    return DebugKernelBoardHandle(
        routingZoneId=routingZoneId,
        side=side,
        kernel=kernel,
        boardBackend=boardBackend,
        boardModel=boardModel,
        channels=_kernelChannelsFromBoard_build(boardModel),
    )


def _boardWiringRuntime_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
    side: str,
    kernel: RoutingKernel,
    boardModel: DomainBoard,
) -> BoardWiring:
    """Build real board-runtime wiring from the current kernel scope."""

    callRouteObligationByKey: dict[
        tuple[ChipRef, ChipRef, int],
        CallRouteObligation,
    ] = {
        (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        ): callRouteObligation
        for callRouteObligation in (
            debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations
        )
    }

    runtimeWiresMutable: list[BoardKernelWire] = []
    solvedRoute: RoutingZoneLocalSolvedRoute | RoutingZoneInterconnectSolvedRoute
    for solvedRoute in _kernelSolvedRoutes_get(
        debugContext=debugContext,
        kernel=kernel,
    ):
        routeKey = (
            solvedRoute.sourceChipRef,
            solvedRoute.destinationChipRef,
            solvedRoute.childCallIndex,
        )
        reverseRouteKey = (
            solvedRoute.destinationChipRef,
            solvedRoute.sourceChipRef,
            solvedRoute.childCallIndex,
        )
        callRouteObligation = callRouteObligationByKey.get(routeKey)
        if callRouteObligation is None:
            callRouteObligation = callRouteObligationByKey.get(reverseRouteKey)
        if callRouteObligation is None:
            continue
        debugWire = _kernelWire_build(
            circuitDocument=debugContext.circuitDocument,
            callRouteObligation=callRouteObligation,
            solvedRoute=solvedRoute,
        )
        runtimeWiresMutable.append(
            BoardKernelWire(
                sourceEndpointText=debugWire.sourceEndpointText,
                destinationEndpointText=debugWire.destinationEndpointText,
                sourceChipRef=debugWire.sourceChipRef,
                destinationChipRef=debugWire.destinationChipRef,
                sourceTerminalName=debugWire.sourceTerminalName,
                destinationTerminalName=debugWire.destinationTerminalName,
                sourceTerminalSide=debugWire.sourceTerminalSide,
                destinationTerminalSide=debugWire.destinationTerminalSide,
                isReturn=debugWire.isReturn,
            )
        )

    return BoardWiring(
        board=boardModel,
        _wires=tuple(runtimeWiresMutable),
    )


def _boardKernelRuntime_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
    side: str,
    kernel: RoutingKernel,
) -> BoardKernel:
    """Build the real board-runtime kernel for one routing kernel scope."""

    zoneResult = debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZoneId
    )
    if not result_isOkCheck(zoneResult):
        raise RuntimeError(f"Could not build board for missing zone {routingZoneId}")

    def _boardModel_build(
        chipPlacementPolicy: BoardChipPlacementPolicy = (
            BoardChipPlacementPolicy.CENTROIDAL
        ),
    ) -> DomainBoard:
        return board_buildFromKernel(
            routingZoneId=routingZoneId,
            side=side,
            routingZone=zoneResult.value,
            kernel=kernel,
            circuitDocument=debugContext.circuitDocument,
            moduleBoundaryPaddingCells=debugContext.placedRoutingZoneGrid.moduleBoxPadding,
            chipPlacementPolicy=chipPlacementPolicy,
        )

    boardModel = _boardModel_build()
    wiring = _boardWiringRuntime_build(
        debugContext=debugContext,
        routingZoneId=routingZoneId,
        side=side,
        kernel=kernel,
        boardModel=boardModel,
    )
    return BoardKernel(
        routingZoneId=routingZoneId,
        side=side,
        kernel=kernel,
        board=boardModel,
        wiring=wiring,
        areasProvider=lambda: DebugZoneRegionSetHandle(
            _regions=tuple(
                DebugZoneRegionHandle(
                    routingZoneRegionId=r.routingZoneRegionId,
                    routingZoneRegionFrame=r.routingZoneRegionFrame,
                )
                for r in kernel.routingZoneRegionSet.routingZoneRegions
            )
        ),
        schematicProvider=lambda: DebugKernelHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
            side=side,
            kernel=kernel,
        ).schematic_text(),
        routesProvider=lambda: DebugKernelHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
            side=side,
            kernel=kernel,
        ).routes_text(),
        yamlProvider=lambda: yaml.safe_dump(
            debugContext.documentDict,
            sort_keys=False,
        ).rstrip(),
        boardProvider=_boardModel_build,
    )


def _boardZoneRuntime_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
) -> BoardZone:
    """Build the real zone runtime object for one placed routing zone."""

    def _kernelRuntime_get(side: str) -> BoardKernel | None:
        return DebugZoneHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        )._routingKernel_get(side)

    def _kernelsRuntime_get() -> dict[str, BoardKernel]:
        kernelBySide: dict[str, BoardKernel] = {}
        for side in ("north", "south", "east", "west", "intra"):
            kernel = _kernelRuntime_get(side)
            if kernel is not None:
                kernelBySide[side] = kernel
        return kernelBySide

    return BoardZone(
        routingZoneId=routingZoneId,
        rawProvider=lambda: debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        ),
        areasProvider=lambda: DebugZoneHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ).areas_get(),
        areaProvider=lambda kindOrKey, side: DebugZoneHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ).area_get(kindOrKey, side),
        idProvider=lambda: routingZoneId,
        senseProvider=lambda: DebugZoneHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ).sense_get(),
        placementsProvider=lambda: debugContext.placementsForZone_get(routingZoneId),
        routesProvider=lambda: debugContext.zoneLocalRoutesForZone_get(routingZoneId),
        routesTextProvider=lambda: _zoneRoutesText_build(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ),
        schematicProvider=lambda: _zoneDrawingLines_build(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ),
        worldProvider=lambda: _zoneWorldCanvasText_build(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ),
        kernelsProvider=_kernelsRuntime_get,
        kernelProvider=_kernelRuntime_get,
        summaryProvider=lambda: _zoneSummaryText_build(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ),
    )


def _chipInternalBoardKernelRuntime_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> BoardKernel:
    """Build a chip-local board kernel through the normal board builder."""

    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        raise RuntimeError(f"Missing chip {chipId.moduleName}.{chipId.functionName}")
    chip = chipResult.value
    artifacts = chipInternalPlacedKernelArtifacts_build(
        chip,
        moduleBoundaryPaddingCells=debugContext.placedRoutingZoneGrid.moduleBoxPadding,
    )
    board = board_buildFromKernel(
        routingZoneId=artifacts.routingZone.routingZoneId,
        side="internal",
        routingZone=artifacts.routingZone,
        kernel=artifacts.kernel,
        circuitDocument=artifacts.circuitDocument,
        moduleBoundaryPaddingCells=artifacts.routingZoneGrid.moduleBoxPadding,
    )

    runtimeWiresMutable: list[BoardKernelWire] = []
    circuitCall = None
    for circuitCall in artifacts.circuitDocument.circuitCallSet.circuitCalls:
        sourceChipResult = artifacts.circuitDocument.circuitChipSet.chipResult_get(
            circuitCall.sourceChipRef.chipId
        )
        destinationChipResult = artifacts.circuitDocument.circuitChipSet.chipResult_get(
            circuitCall.destinationChipRef.chipId
        )
        if not result_isOkCheck(sourceChipResult) or not result_isOkCheck(
            destinationChipResult
        ):
            continue
        sourceChip = sourceChipResult.value
        destinationChip = destinationChipResult.value
        sourcePortDeclaration = circuitCall.sourcePortDeclaration
        if sourcePortDeclaration is None:
            if circuitCall.callIndex >= len(
                sourceChip.outputPortDeclarationSet.portDeclarations
            ):
                continue
            sourcePortDeclaration = (
                sourceChip.outputPortDeclarationSet.portDeclarations[
                    circuitCall.callIndex
                ]
            )
        if not destinationChip.inputPortDeclarationSet.portDeclarations:
            continue
        destinationPortDeclaration = (
            destinationChip.inputPortDeclarationSet.portDeclarations[0]
        )
        if (
            sourcePortDeclaration.signalName is not None
            and destinationPortDeclaration.signalName is not None
        ):
            runtimeWiresMutable.append(
                BoardKernelWire(
                    sourceEndpointText=_chipEndpointText_build(
                        chipRef=circuitCall.sourceChipRef,
                        terminalName=sourcePortDeclaration.signalName,
                    ),
                    destinationEndpointText=_chipEndpointText_build(
                        chipRef=circuitCall.destinationChipRef,
                        terminalName=destinationPortDeclaration.signalName,
                    ),
                    sourceChipRef=circuitCall.sourceChipRef,
                    destinationChipRef=circuitCall.destinationChipRef,
                    sourceTerminalName=sourcePortDeclaration.signalName,
                    destinationTerminalName=destinationPortDeclaration.signalName,
                    sourceTerminalSide=(
                        _terminalSideOrNone_get(
                            circuitDocument=artifacts.circuitDocument,
                            chipRef=circuitCall.sourceChipRef,
                            terminalName=sourcePortDeclaration.signalName,
                        )
                        or ChipTerminalSide.EAST
                    ),
                    destinationTerminalSide=(
                        _terminalSideOrNone_get(
                            circuitDocument=artifacts.circuitDocument,
                            chipRef=circuitCall.destinationChipRef,
                            terminalName=destinationPortDeclaration.signalName,
                        )
                        or ChipTerminalSide.WEST
                    ),
                    isReturn=False,
                )
            )
        if (
            destinationPortDeclaration.returnName is not None
            and sourcePortDeclaration.returnName is not None
        ):
            runtimeWiresMutable.append(
                BoardKernelWire(
                    sourceEndpointText=_chipEndpointText_build(
                        chipRef=circuitCall.destinationChipRef,
                        terminalName=destinationPortDeclaration.returnName,
                    ),
                    destinationEndpointText=_chipEndpointText_build(
                        chipRef=circuitCall.sourceChipRef,
                        terminalName=sourcePortDeclaration.returnName,
                    ),
                    sourceChipRef=circuitCall.destinationChipRef,
                    destinationChipRef=circuitCall.sourceChipRef,
                    sourceTerminalName=destinationPortDeclaration.returnName,
                    destinationTerminalName=sourcePortDeclaration.returnName,
                    sourceTerminalSide=(
                        _terminalSideOrNone_get(
                            circuitDocument=artifacts.circuitDocument,
                            chipRef=circuitCall.destinationChipRef,
                            terminalName=destinationPortDeclaration.returnName,
                        )
                        or ChipTerminalSide.EAST
                    ),
                    destinationTerminalSide=(
                        _terminalSideOrNone_get(
                            circuitDocument=artifacts.circuitDocument,
                            chipRef=circuitCall.sourceChipRef,
                            terminalName=sourcePortDeclaration.returnName,
                        )
                        or ChipTerminalSide.WEST
                    ),
                    isReturn=True,
                )
            )
    runtimeWires = tuple(runtimeWiresMutable)
    wiring = BoardWiring(board=board, _wires=runtimeWires)

    return BoardKernel(
        routingZoneId=artifacts.routingZone.routingZoneId,
        side="internal",
        kernel=artifacts.kernel,
        board=board,
        wiring=wiring,
        areasProvider=lambda: DebugZoneRegionSetHandle(
            _regions=tuple(
                DebugZoneRegionHandle(
                    routingZoneRegionId=r.routingZoneRegionId,
                    routingZoneRegionFrame=r.routingZoneRegionFrame,
                )
                for r in artifacts.kernel.routingZoneRegionSet.routingZoneRegions
            )
        ),
        schematicProvider=lambda: "\n".join(
            routingZoneDrawLines_build(artifacts.routingZone)
        ),
        routesProvider=lambda: "\n".join(
            wire.wiringDeclaration for wire in artifacts.schema.wires
        )
        if artifacts.schema.wires
        else "<kernel routes unavailable>",
        yamlProvider=lambda: yaml.safe_dump(
            artifacts.syntheticDocumentDict,
            sort_keys=False,
        ).rstrip(),
        boardProvider=lambda chipPlacementPolicy: board_buildFromKernel(
            routingZoneId=artifacts.routingZone.routingZoneId,
            side="internal",
            routingZone=artifacts.routingZone,
            kernel=artifacts.kernel,
            circuitDocument=artifacts.circuitDocument,
            moduleBoundaryPaddingCells=artifacts.routingZoneGrid.moduleBoxPadding,
            chipPlacementPolicy=chipPlacementPolicy,
        ),
    )


def _kernelWireAlgebraicText_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
    side: str,
    kernel: RoutingKernel,
    wiring: DebugKernelWiringHandle,
    kernelWire: DebugKernelWire,
    rotationSense: RoutingZoneChannelSense,
    laneFillSense: RoutingLaneAttachmentSense,
) -> str:
    """Build quarantine algebraic path text for one kernel wire.

    Args:
        debugContext: Live debug context that owns the current zone and board.
        routingZoneId: Owning routing-zone id for the requested solve.
        side: Kernel side label such as `intra`.
        kernel: Kernel whose board geometry constrains the solve.
        wiring: Symbolic wiring scope for this solve.
        kernelWire: Directed symbolic wire to solve.
        rotationSense: Quarantine symbolic rotation policy enum.
        laneFillSense: Quarantine symbolic lane-fill policy enum.

    Returns:
        Algebraic path text when the current quarantine solver supports the
        requested context, otherwise an explanatory fallback string.
    """

    boardHandle = _kernelBoard_build(
        debugContext=debugContext,
        routingZoneId=routingZoneId,
        side=side,
        kernel=kernel,
    )
    allWires: tuple[SolverWireInput, ...] = tuple(
        SolverWireInput(
            sourceEndpointText=wire.sourceEndpointText,
            destinationEndpointText=wire.destinationEndpointText,
            isReturn=wire.isReturn,
        )
        for wire in wiring.all_get()
    )
    return boardWireAlgebraicPath_build(
        board=boardHandle.boardModel,
        allWires=allWires,
        wire=SolverWireInput(
            sourceEndpointText=kernelWire.sourceEndpointText,
            destinationEndpointText=kernelWire.destinationEndpointText,
            isReturn=kernelWire.isReturn,
        ),
        rotationSense=rotationSense,
        laneFillSense=laneFillSense,
    )


def solution_realize(
    board: DomainBoard,
    solution: BoardSolution,
    policy: BoardMaterializePolicy | None = None,
) -> BoardMaterializedSolution:
    """Realize one symbolic solution onto one board.

    Args:
        board: Symbolic board that defines the legal routing substrate.
        solution: Symbolic solution to materialize on the board.

    Returns:
        Inspectable materialized-result handle containing per-wire route points
        and board-overlay text.
    """

    return solution.board_materialize(board, policy=policy)


def solution_materialize(
    board: DomainBoard,
    solution: BoardSolution,
    policy: BoardMaterializePolicy | None = None,
) -> BoardMaterializedSolution:
    """Compatibility wrapper for the old materializer entry point.

    Args:
        board: Symbolic board that defines the legal routing substrate.
        solution: Symbolic solution to realize on the board.

    Returns:
        Realized solution handle. This is an alias for `solution_realize(...)`.
    """

    return solution_realize(board=board, solution=solution, policy=policy)


@dataclass(frozen=True)
class DebugKernelMaterializedPath:
    """Board-derived symbolic-token starts and realized route points.

    Attributes:
        tokenStartPoints: Ordered world-coordinate start points for the five
            non-endpoint algebraic tokens.
        routePoints: Ordered world-coordinate points used to realize the route
            through the board geometry.
    """

    tokenStartPoints: tuple[tuple[int, int], ...]
    routePoints: tuple[tuple[int, int], ...]
    routeCells: tuple[tuple[int, int], ...]


def _materializedPath_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
    board: DebugKernelBoardHandle,
    solvedWire: DebugKernelSolvedWire,
    regionFramesByName: dict[str, RoutingZoneRegionFrame] | None = None,
    prebuiltRealization=None,
) -> DebugKernelMaterializedPath:
    """Build token starts and exact route geometry for one solved wire.

    Args:
        debugContext: Live debug context owning the placed zone and chips.
        routingZoneId: Owning routing-zone id for the materialization scope.
        board: Symbolic board used as the materialization substrate.
        solvedWire: Solved symbolic wire whose algebraic path must be laid out.

    Returns:
        Board-derived token starts, route points, and route cells in
        `(columnIndex, rowIndex)` form.
    """
    pathTokens = solvedWire.algebraicPathText.split("::")
    if len(pathTokens) != 7:
        return DebugKernelMaterializedPath(
            tokenStartPoints=tuple(),
            routePoints=tuple(),
            routeCells=tuple(),
        )

    sourceEndpointText: str = pathTokens[0]
    destinationEndpointText: str = pathTokens[6]

    sourceAttachPoint = _boardEndpointAttachPoint_build(
        board=board,
        endpointText=sourceEndpointText,
    )
    destinationAttachPoint = _boardEndpointAttachPoint_build(
        board=board,
        endpointText=destinationEndpointText,
    )
    if sourceAttachPoint is None or destinationAttachPoint is None:
        return DebugKernelMaterializedPath(
            tokenStartPoints=tuple(),
            routePoints=tuple(),
            routeCells=tuple(),
        )

    if prebuiltRealization is not None:
        realizedRoute = prebuiltRealization
        return DebugKernelMaterializedPath(
            tokenStartPoints=realizedRoute.tokenStartPoints,
            routePoints=realizedRoute.routePoints,
            routeCells=realizedRoute.routeCells,
        )

    if regionFramesByName is None:
        geometry = board.geometry_get()
        regionFramesByName = {
            regionHandle._tagged_name: regionHandle.routingZoneRegionFrame
            for regionHandle in geometry.all_get()
        }
    realizedRoute = algebraicRouteRealization_build(
        algebraicPathText=solvedWire.algebraicPathText,
        sourceAttachPoint=sourceAttachPoint,
        destinationAttachPoint=destinationAttachPoint,
        regionFramesByName=regionFramesByName,
    )
    return DebugKernelMaterializedPath(
        tokenStartPoints=realizedRoute.tokenStartPoints,
        routePoints=realizedRoute.routePoints,
        routeCells=realizedRoute.routeCells,
    )


def _boardEndpointAttachPoint_build(
    *,
    board: DebugKernelBoardHandle,
    endpointText: str,
) -> tuple[int, int] | None:
    """Return one exact board-owned terminal attach point by endpoint text."""

    endpointParts = endpointText.split(".")
    if len(endpointParts) < 3:
        return None
    terminalName = endpointParts[-1]
    chipName = ".".join(endpointParts[:-1])
    return board.terminal_get(chipName, terminalName)


def _regionByTaggedNameOrNone_get(
    geometry: DebugZoneRegionSetHandle,
    taggedName: str,
) -> DebugZoneRegionHandle | None:
    """Return one region handle by full tagged name.

    Args:
        geometry: Region-set geometry view to search.
        taggedName: Full region key, optionally including a `:tag` suffix.

    Returns:
        Matching region handle when present, otherwise `None`.
    """

    regionHandle: DebugZoneRegionHandle
    for regionHandle in geometry.all_get():
        if regionHandle._tagged_name == taggedName:
            return regionHandle
    return None


def _regionTaggedNamesForWorldCell_build(
    geometry: DebugZoneRegionSetHandle,
    columnIndex: int,
    rowIndex: int,
) -> tuple[str, ...]:
    """Return all tagged region names that own one world cell.

    Args:
        geometry: Region-set geometry view to search.
        columnIndex: World column to classify.
        rowIndex: World row to classify.

    Returns:
        Sorted tagged region names that contain the requested cell.
    """

    taggedNamesMutable: list[str] = []
    regionHandle: DebugZoneRegionHandle
    for regionHandle in geometry.all_get():
        frame = regionHandle.routingZoneRegionFrame
        if not (
            frame.horizontalStart
            <= columnIndex
            < frame.horizontalEnd_calculate()
            and frame.verticalStart <= rowIndex < frame.verticalEnd_calculate()
        ):
            continue
        taggedNamesMutable.append(regionHandle._tagged_name)
    return tuple(sorted(taggedNamesMutable))


def _frameBorderCells_build(
    frame: RoutingZoneRegionFrame,
) -> set[tuple[int, int]]:
    """Return the inclusive border cells of one frame as world points."""

    horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
    verticalEndInclusive = frame.verticalEnd_calculate() - 1
    cells: set[tuple[int, int]] = set()
    for columnIndex in range(frame.horizontalStart, horizontalEndInclusive + 1):
        cells.add((columnIndex, frame.verticalStart))
        cells.add((columnIndex, verticalEndInclusive))
    for rowIndex in range(frame.verticalStart, verticalEndInclusive + 1):
        cells.add((frame.horizontalStart, rowIndex))
        cells.add((horizontalEndInclusive, rowIndex))
    return cells


def _frameInteriorCells_build(
    frame: RoutingZoneRegionFrame,
) -> set[tuple[int, int]]:
    """Return the strict interior cells of one frame as world points."""

    horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
    verticalEndInclusive = frame.verticalEnd_calculate() - 1
    if horizontalEndInclusive - frame.horizontalStart < 2:
        return set()
    if verticalEndInclusive - frame.verticalStart < 2:
        return set()
    return {
        (columnIndex, rowIndex)
        for columnIndex in range(frame.horizontalStart + 1, horizontalEndInclusive)
        for rowIndex in range(frame.verticalStart + 1, verticalEndInclusive)
    }


def _cellWalk_buildFromRoutePoints(
    routePoints: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    """Expand ordered route points into a unit-step world cell walk.

    Args:
        routePoints: Ordered world-coordinate route points in
            `(columnIndex, rowIndex)` form.

    Returns:
        Ordered tuple of adjacent occupied world cells in
        `(columnIndex, rowIndex)` form.
    """

    if not routePoints:
        return tuple()

    cellWalkMutable: list[tuple[int, int]] = [routePoints[0]]
    for (column0, row0), (column1, row1) in zip(
        routePoints,
        routePoints[1:],
        strict=False,
    ):
        if column0 == column1 and row0 == row1:
            continue
        if column0 != column1 and row0 != row1:
            return tuple()
        if row0 == row1:
            step = 1 if column1 > column0 else -1
            for columnIndex in range(column0 + step, column1 + step, step):
                cellWalkMutable.append((columnIndex, row0))
        else:
            step = 1 if row1 > row0 else -1
            for rowIndex in range(row0 + step, row1 + step, step):
                cellWalkMutable.append((column0, rowIndex))
    return tuple(cellWalkMutable)


def _realizedRoute_buildFromCellWalk(
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    cellWalk: tuple[tuple[int, int], ...],
    routeSense: RouteSense,
) -> RealizedRoute | None:
    """Build a realized route directly from an exact adjacent cell walk.

    Args:
        sourceChipRef: Originating chip reference.
        destinationChipRef: Target chip reference.
        childCallIndex: Call-sequence index for disambiguation.
        cellWalk: Ordered adjacent occupied cells in `(columnIndex, rowIndex)`
            form.
        routeSense: Semantic route sense to attach to the realized route.

    Returns:
        Realized route when the walk is valid, otherwise `None`.
    """

    if len(cellWalk) < 2:
        return None

    directionMap: dict[tuple[int, int], set[TrackDirection]] = {}

    def _directionSet_get(
        columnIndex: int,
        rowIndex: int,
    ) -> set[TrackDirection]:
        return directionMap.setdefault((columnIndex, rowIndex), set())

    for (column0, row0), (column1, row1) in zip(
        cellWalk,
        cellWalk[1:],
        strict=False,
    ):
        columnDelta = column1 - column0
        rowDelta = row1 - row0
        if abs(columnDelta) + abs(rowDelta) != 1:
            return None
        if columnDelta == 1:
            _directionSet_get(column0, row0).add(TrackDirection.EAST)
            _directionSet_get(column1, row1).add(TrackDirection.WEST)
        elif columnDelta == -1:
            _directionSet_get(column0, row0).add(TrackDirection.WEST)
            _directionSet_get(column1, row1).add(TrackDirection.EAST)
        elif rowDelta == 1:
            _directionSet_get(column0, row0).add(TrackDirection.SOUTH)
            _directionSet_get(column1, row1).add(TrackDirection.NORTH)
        else:
            _directionSet_get(column0, row0).add(TrackDirection.NORTH)
            _directionSet_get(column1, row1).add(TrackDirection.SOUTH)

    realizedCells: tuple[RealizedRouteCell, ...] = tuple(
        RealizedRouteCell(
            worldRow=rowIndex,
            worldCol=columnIndex,
            trackCell=trackCell_build(frozenset(directions)),
        )
        for (columnIndex, rowIndex), directions in sorted(
            directionMap.items(),
            key=lambda item: (item[0][1], item[0][0]),
        )
    )
    return RealizedRoute(
        sourceChipRef=sourceChipRef,
        destinationChipRef=destinationChipRef,
        childCallIndex=childCallIndex,
        routeSense=routeSense,
        cells=realizedCells,
    )


def _endpointAttachPoint_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
    kernelWire: DebugKernelWire,
    endpointText: str,
) -> tuple[int, int] | None:
    """Build the world-coordinate attach point for one endpoint text.

    Args:
        debugContext: Live debug context owning the placed zone.
        routingZoneId: Owning routing-zone id for the requested attach point.
        kernelWire: Wire providing chip and terminal metadata.
        endpointText: Endpoint text to resolve.

    Returns:
        `(columnIndex, rowIndex)` world-coordinate attach point when available,
        otherwise `None`.
    """

    zoneResult = debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZoneId
    )
    if not result_isOkCheck(zoneResult):
        return None
    geometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        debugContext.circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(geometrySetResult):
        return None
    attachPointSetResult = chipAttachPointSetResult_buildFromPlacedZone(
        zone=zoneResult.value,
        chipLocalGeometrySet=geometrySetResult.value,
        circuitDocument=debugContext.circuitDocument,
    )
    if not result_isOkCheck(attachPointSetResult):
        return None

    if endpointText == kernelWire.sourceEndpointText:
        chipRef = kernelWire.sourceChipRef
        terminalName = kernelWire.sourceTerminalName
        terminalSide = kernelWire.sourceTerminalSide
    elif endpointText == kernelWire.destinationEndpointText:
        chipRef = kernelWire.destinationChipRef
        terminalName = kernelWire.destinationTerminalName
        terminalSide = kernelWire.destinationTerminalSide
    else:
        return None

    attachPointResult = attachPointSetResult.value.attachPointForTerminalResult_get(
        chipRef=chipRef,
        terminalSide=terminalSide,
        terminalName=terminalName,
    )
    if not result_isOkCheck(attachPointResult):
        return None
    return (
        attachPointResult.value.worldColumn,
        attachPointResult.value.worldRow,
    )


def _channelAnchorPoint_build(
    board: DebugKernelBoardHandle,
    channelToken: str,
    isReturn: bool,
) -> tuple[int, int] | None:
    """Build the canonical anchor point for one channel token on the board.

    Args:
        board: Board whose geometry owns the requested channel.
        channelToken: Channel token such as `wLong[3]` or `nLat[6]`.
        isReturn: Whether the owning solved wire is a return-path route.

    Returns:
        `(columnIndex, rowIndex)` anchor point inside the requested channel when the
        token resolves cleanly, otherwise `None`.
    """

    channelMatch = re.fullmatch(r"([a-zA-Z]+)\[(\d+)\]", channelToken)
    if channelMatch is None:
        return None

    channelName = channelMatch.group(1)
    laneIndex = int(channelMatch.group(2))
    geometry = board.geometry_get()

    if channelName == "wLong":
        laneRegion = geometry.area_get("west/intra_routing_longitude")
        if laneRegion is None:
            return None
        frame = laneRegion.routingZoneRegionFrame
        if laneIndex > frame.horizontalSpan:
            return None
        columnIndex = frame.horizontalStart + laneIndex - 1
        return (columnIndex, 0)
    if channelName == "eLong":
        laneRegion = geometry.area_get("east/intra_routing_longitude")
        if laneRegion is None:
            return None
        frame = laneRegion.routingZoneRegionFrame
        if laneIndex > frame.horizontalSpan:
            return None
        columnIndex = frame.horizontalStart + laneIndex - 1
        return (columnIndex, 0)
    if channelName == "nLat":
        laneRegion = geometry.area_get("north/intra_routing_latitude")
        if laneRegion is None:
            return None
        frame = laneRegion.routingZoneRegionFrame
        if laneIndex > frame.verticalSpan:
            return None
        rowIndex = frame.verticalStart + laneIndex - 1
        return (0, rowIndex)
    if channelName == "sLat":
        laneRegion = geometry.area_get("south/intra_routing_latitude")
        if laneRegion is None:
            return None
        frame = laneRegion.routingZoneRegionFrame
        if laneIndex > frame.verticalSpan:
            return None
        rowIndex = frame.verticalStart + laneIndex - 1
        return (0, rowIndex)
    return None


@dataclass(frozen=True)
class DebugKernelHandle:
    """Interactive handle for a single Routing Kernel."""

    debugContext: NewEngineDebugContext
    routingZoneId: RoutingZoneId
    side: str
    kernel: RoutingKernel

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "areas_get",
            "board_get",
            "raw_get",
            "routes_text",
            "side_get",
            "schematic_text",
            "solver_get",
            "wiring_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<kernel {self.side} of {self.routingZoneId.id}>"

    def side_get(self) -> str:
        """Return the side of the zone this kernel solves."""
        return self.side

    def areas_get(self) -> DebugZoneRegionSetHandle:
        """Return the specific region set owned by this kernel."""
        return DebugZoneRegionSetHandle(
            _regions=tuple(
                DebugZoneRegionHandle(
                    routingZoneRegionId=r.routingZoneRegionId,
                    routingZoneRegionFrame=r.routingZoneRegionFrame,
                )
                for r in self.kernel.routingZoneRegionSet.routingZoneRegions
            )
        )

    def board_get(self) -> DebugKernelBoardHandle:
        """Return the quarantine symbolic board for this kernel.

        Returns:
            Board handle derived from the kernel's realized region geometry.
        """

        return _kernelBoard_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
        )

    def _kernelDraw_render(self, mode: str = "pixel") -> str:
        """Render this kernel's internal substrate logic."""
        
        # 1. Calculate the bounding box of the kernel's regions
        regions = self.kernel.routingZoneRegionSet.routingZoneRegions
        if not regions:
            return f"<kernel {self.side} has no regions>"
            
        h_start = min(r.routingZoneRegionFrame.horizontalStart for r in regions)
        h_end = max(r.routingZoneRegionFrame.horizontalEnd_calculate() for r in regions)
        v_start = min(r.routingZoneRegionFrame.verticalStart for r in regions)
        v_end = max(r.routingZoneRegionFrame.verticalEnd_calculate() for r in regions)
        
        # 2. Get the full world canvas lines
        worldCanvasLines = _worldCanvasLines_build(self.debugContext)
        if not worldCanvasLines:
            return "<error: could not build world canvas>"
            
        # 3. Crop to the kernel's bounding box
        croppedLines: list[str] = []
        for rowIndex in range(v_start, v_end):
            if rowIndex < len(worldCanvasLines):
                line = worldCanvasLines[rowIndex]
                croppedLines.append(line[h_start:h_end])
                
        header = f"kernel {self.side} of {self.routingZoneId.id}  ({h_end-h_start}x{v_end-v_start})"
        return header + "\n" + "\n".join(croppedLines)

    def schematic_text(self, mode: str = "pixel") -> str:
        """Return this kernel's internal substrate logic as text."""
        return self._kernelDraw_render(mode=mode)

    def wiring_get(self) -> DebugKernelWiringHandle:
        """Return the symbolic wiring handle for this kernel."""

        callRouteObligationByKey: dict[
            tuple[ChipRef, ChipRef, int],
            CallRouteObligation,
        ] = {
            (
                callRouteObligation.sourceChipRef,
                callRouteObligation.destinationChipRef,
                callRouteObligation.childCallIndex,
            ): callRouteObligation
            for callRouteObligation in (
                self.debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations
            )
        }

        wiringMutable: list[DebugKernelWire] = []
        solvedRoute: RoutingZoneLocalSolvedRoute | RoutingZoneInterconnectSolvedRoute
        for solvedRoute in _kernelSolvedRoutes_get(
            debugContext=self.debugContext,
            kernel=self.kernel,
        ):
            routeKey = (
                solvedRoute.sourceChipRef,
                solvedRoute.destinationChipRef,
                solvedRoute.childCallIndex,
            )
            reverseRouteKey = (
                solvedRoute.destinationChipRef,
                solvedRoute.sourceChipRef,
                solvedRoute.childCallIndex,
            )
            callRouteObligation = callRouteObligationByKey.get(routeKey)
            if callRouteObligation is None:
                callRouteObligation = callRouteObligationByKey.get(reverseRouteKey)
            if callRouteObligation is None:
                continue
            wiringMutable.append(
                _kernelWire_build(
                    circuitDocument=self.debugContext.circuitDocument,
                    callRouteObligation=callRouteObligation,
                    solvedRoute=solvedRoute,
                )
            )
        return DebugKernelWiringHandle(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            _wires=tuple(wiringMutable),
        )

    def solver_get(
        self,
        board: DebugKernelBoardHandle | None = None,
    ) -> DebugKernelSolverHandle:
        """Return the quarantine symbolic solver for this kernel.

        Args:
            board: Optional explicit symbolic board. When omitted, the solver
                uses `kernel.board_get()`.

        Returns:
            Solver handle bound to this kernel, its wiring scope, and the
            requested symbolic board.
        """

        activeBoard = board or self.board_get()
        wiring = self.wiring_get()
        return DebugKernelSolverHandle(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            board=activeBoard,
            wiring=wiring,
        )

    def _kernelRoutesDraw_render(self) -> str:
        """Render realized routes only for this kernel."""

        # 1. Get the zone handle to access its frame
        zoneResult = self.debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(self.routingZoneId)
        if not result_isOkCheck(zoneResult):
            return "<error: zone not found>"
        
        # 2. Identify routes belonging to this kernel's regions
        # We collect ALL solved routes (local and interconnect) and filter
        # by the kernel's region set.
        filteredSolvedRoutes = _kernelSolvedRoutes_get(
            debugContext=self.debugContext,
            kernel=self.kernel,
        )
        if not filteredSolvedRoutes:
            return "<no routes in this kernel>"

        # 3. Realize the filtered routes
        from signalflow.routing.route import RealizedRouteSet, routePoints_realize
        realizedRoutes = []
        for r in filteredSolvedRoutes:
            res = routePoints_realize(
                sourceChipRef=r.sourceChipRef,
                destinationChipRef=r.destinationChipRef,
                childCallIndex=r.childCallIndex,
                routePoints=r.routePoints
            )
            if result_isOkCheck(res):
                realizedRoutes.append(res.value)
            
        realizedRouteSet = RealizedRouteSet(tuple(realizedRoutes))
            
        # 4. Render to full zone canvas
        from signalflow.render.routes import routeWorldCanvas_render, RouteCanvasSize
        frame = zoneResult.value.routingZoneFrame
        canvasSize = RouteCanvasSize(width=frame.horizontalSpan, height=frame.verticalSpan)
        fullCanvasLines = routeWorldCanvas_render(realizedRouteSet, canvasSize=canvasSize)
        
        # 5. Crop to the kernel's bounding box
        regions = self.kernel.routingZoneRegionSet.routingZoneRegions
        h_start = min(r.routingZoneRegionFrame.horizontalStart for r in regions)
        h_end = max(r.routingZoneRegionFrame.horizontalEnd_calculate() for r in regions)
        v_start = min(r.routingZoneRegionFrame.verticalStart for r in regions)
        v_end = max(r.routingZoneRegionFrame.verticalEnd_calculate() for r in regions)
        
        # Relative coordinates within the zone frame
        rel_h0 = h_start - frame.horizontalStart
        rel_h1 = h_end - frame.horizontalStart
        rel_v0 = v_start - frame.verticalStart
        rel_v1 = v_end - frame.verticalStart
        
        croppedLines: list[str] = []
        for rowIndex in range(rel_v0, rel_v1):
            if 0 <= rowIndex < len(fullCanvasLines):
                line = fullCanvasLines[rowIndex]
                croppedLines.append(line[rel_h0:rel_h1])
                
        header = f"kernel routes {self.side} of {self.routingZoneId.id}  ({h_end-h_start}x{v_end-v_start})"
        return header + "\n" + "\n".join(croppedLines)

    def routes_text(self) -> str:
        """Return realized routes only for this kernel as text."""
        return self._kernelRoutesDraw_render()
    def raw_get(self) -> RoutingKernel:
        """Return the raw kernel model."""
        return self.kernel


@dataclass(frozen=True)
class DebugZoneHandle:
    """Interactive handle for one placed routing zone."""

    debugContext: NewEngineDebugContext
    routingZoneId: RoutingZoneId

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "area_get",
            "areas_get",
            "id_get",
            "kernel_get",
            "kernels_get",
            "placements_get",
            "raw_get",
            "routes_get",
            "routes_text",
            "schematic_text",
            "sense_get",
            "summary_text",
            "world_text",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<zone {self.routingZoneId.id}>"

    def raw_get(self):
        """Return the raw placed routing-zone result."""
        return self._routingZone_get()

    def areas_get(self) -> "DebugZoneRegionSetHandle":
        """Return all zone regions as a flat inspectable region set."""
        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return DebugZoneRegionSetHandle(_regions=())
        zone = zoneResult.value

        def _handles(kernel):
            if kernel is None:
                return ()
            return tuple(
                DebugZoneRegionHandle(
                    routingZoneRegionId=r.routingZoneRegionId,
                    routingZoneRegionFrame=r.routingZoneRegionFrame,
                )
                for r in kernel.routingZoneRegionSet.routingZoneRegions
            )

        all_handles = (
            _handles(zone.intraKernel)
            + _handles(zone.westKernel)
            + _handles(zone.eastKernel)
            + _handles(zone.northKernel)
            + _handles(zone.southKernel)
        )
        return DebugZoneRegionSetHandle(_regions=all_handles)

    def area_get(self, kindOrKey: str, side: str | None = None):
        """Return one region by kind and optional side."""
        return self.areas_get().area_get(kindOrKey, side)

    def id_get(self):
        """Return the stable routing-zone id."""
        return self._routingZoneId_get()

    def sense_get(self) -> str | None:
        """Return the routing sense of this placed zone when available."""
        return self._routingZoneSense_get()

    def placements_get(self):
        """Return chip placements owned by this placed zone."""
        return self._routingZonePlacements_get()

    def routes_get(self):
        """Return solved zone-local routes owned by this placed zone."""
        return self._routingZoneLocalRoutes_get()

    def routes_text(self) -> str:
        """Return solved local routes for this placed routing zone as text."""
        return self._routingZoneRoutesDraw_render()

    def schematic_text(self) -> str:
        """Return a schematic ASCII drawing of this placed routing zone."""
        return self._routingZoneDraw_render()

    def world_text(self) -> str:
        """Return this zone exactly as the composed world canvas draws it."""
        return self._routingZoneWorldCanvas_render()

    def kernels_get(self) -> dict[str, BoardKernel]:
        """Return all present routing kernels for this placed zone."""

        kernelBySide: dict[str, BoardKernel] = {}
        for side in ("north", "south", "east", "west", "intra"):
            kernelHandle = self.kernel_get(side)
            if kernelHandle is not None:
                kernelBySide[side] = kernelHandle
        return kernelBySide

    def kernel_get(self, side: str = "intra") -> BoardKernel | None:
        """Return one routing kernel handle for the specified zone side."""

        return self._routingKernel_get(side)

    def _routingZone_get(self):
        """Return the raw placed routing-zone result."""

        return self.debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            self.routingZoneId
        )

    def _routingZoneAreas_get(self) -> DebugZoneAreaView:
        """Return all regions partitioned by Routing Kernel."""

        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return DebugZoneAreaView({})
        zone = zoneResult.value

        def _handle_build(regions):
            return DebugZoneRegionSetHandle(
                _regions=tuple(
                    DebugZoneRegionHandle(
                        routingZoneRegionId=r.routingZoneRegionId,
                        routingZoneRegionFrame=r.routingZoneRegionFrame,
                    )
                    for r in regions
                )
            )

        return DebugZoneAreaView({
            "intra": _handle_build(zone.intraKernel.routingZoneRegionSet.routingZoneRegions if zone.intraKernel else ()),
            "west": _handle_build(zone.westKernel.routingZoneRegionSet.routingZoneRegions if zone.westKernel else ()),
            "east": _handle_build(zone.eastKernel.routingZoneRegionSet.routingZoneRegions if zone.eastKernel else ()),
            "north": _handle_build(zone.northKernel.routingZoneRegionSet.routingZoneRegions if zone.northKernel else ()),
            "south": _handle_build(zone.southKernel.routingZoneRegionSet.routingZoneRegions if zone.southKernel else ()),
        })

    def _routingZoneArea_get(
        self,
        kindOrKey: str,
        side: str | None = None,
    ) -> DebugZoneRegionHandle | None:
        """Return one region by kind and optional side."""

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

        # Look in partitioned kernels
        areas = self._routingZoneAreas_get()
        for kernel_side in areas:
            for handle in areas[kernel_side]._regions:
                if (
                    handle.routingZoneRegionId.routingZoneRegionKind is wantKind
                    and handle.routingZoneRegionId.routingZoneRegionSide is wantSide
                ):
                    return handle
        return None

    def _routingZoneId_get(self):
        """Return the stable routing-zone id."""

        return self.routingZoneId

    def _routingZoneSense_get(self) -> str | None:
        """Return the routing sense of this placed zone when available."""

        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return None
        return zoneResult.value.routingZoneSense.value

    def _routingZonePlacements_get(self):
        """Return chip placements owned by this placed zone."""

        return self.debugContext.placementsForZone_get(self.routingZoneId)

    def _routingZoneLocalRoutes_get(self):
        """Return solved zone-local routes owned by this placed zone."""

        return self.debugContext.zoneLocalRoutesForZone_get(self.routingZoneId)

    def _routingKernel_get(self, side: str = "intra") -> BoardKernel | None:
        """Return one routing kernel handle for the specified zone side."""

        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return None
        zone = zoneResult.value
        
        kernel_map = {
            "intra": zone.intraKernel,
            "west": zone.westKernel,
            "east": zone.eastKernel,
            "north": zone.northKernel,
            "south": zone.southKernel,
        }
        
        kernel = kernel_map.get(side.lower())
        if not kernel:
            return None
            
        return _boardKernelRuntime_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=side.lower(),
            kernel=kernel,
        )

    def _routingZoneCrossbarDraw_render(self) -> str:
        """Render a high-level schematic of the 5-kernel crossbar."""

        return (
            "      INTER-NORTH Kernel\n"
            "             ⇅\n"
            "INTER-WEST ↔ INTRAZONE ↔ INTER-EAST\n"
            "Kernel       Kernel      Kernel\n"
            "             ⇅\n"
            "      INTER-SOUTH Kernel"
        )

    def _routingZoneCrossbarDraw_print(self) -> None:
        """Print the high-level schematic of the 5-kernel crossbar."""
        _summary_print(self._routingZoneCrossbarDraw_render())

    def _routingZoneCrossbar_draw(self) -> None:
        """Alias for routingZoneCrossbarDraw_print."""
        self._routingZoneCrossbarDraw_print()

    def _routingZoneRoutesDraw_render(self) -> str:
        """Render solved local routes for this placed routing zone."""

        return _zoneRoutesText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def _routingZoneRoutesDraw_print(self) -> None:
        """Print solved local routes for this placed routing zone."""

        _summary_print(self._routingZoneRoutesDraw_render())

    def _routingZoneWorldCanvas_render(self) -> str:
        """Render this zone exactly as the composed world canvas draws it."""

        return _zoneWorldCanvasText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def _routingZoneWorldCanvas_print(self) -> None:
        """Print this zone exactly as the composed world canvas draws it."""

        _summary_print(self._routingZoneWorldCanvas_render())

    def _routingZoneDraw_render(self) -> str:
        """Render a schematic ASCII drawing of this placed routing zone."""

        return _zoneDrawingLines_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def _routingZoneDraw_print(self) -> None:
        """Print a schematic ASCII drawing of this placed routing zone."""

        _summary_print(self._routingZoneDraw_render())

    def _routingZone_draw(self) -> None:
        """Print a schematic ASCII drawing (alias for routingZoneDraw_print)."""
        self._routingZoneDraw_print()

    def _routingZone_print(self) -> None:
        """Print a summary of the zone."""
        self._routingZoneDraw_print()

    def summary_text(self) -> str:
        """Return this placed routing zone as a readable debug summary."""

        return _zoneSummaryText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

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
            "raw_get",
            "routes_get",
            "schematic_text",
            "summary_text",
            "world_text",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return f"<interconnect {self.sourceGridCoord}->{self.destinationGridCoord}>"

    def raw_get(self):
        """Return the raw placed interconnect result."""
        return self._routingZoneInterconnect_get()

    def endpoints_get(self) -> tuple:
        """Return the source and destination world coordinates."""
        return self._routingZoneInterconnectEndpoints_get()

    def routes_get(self):
        """Return solved seam routes owned by this interconnect."""
        return self._routingZoneInterconnectRoutes_get()

    def schematic_text(self, mode: str = "pixel") -> str:
        """Return this interconnect frame in a compact debug draw mode."""
        return self._routingZoneInterconnectDraw_render(mode=mode)

    def world_text(self) -> str:
        """Return this interconnect as the world canvas draws it."""
        return self._routingZoneInterconnectWorldCanvas_render()

    def _routingZoneInterconnect_get(self):
        """Return the raw placed interconnect result."""

        return self.debugContext.placedRoutingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=self.sourceGridCoord,
            destinationGridCoord=self.destinationGridCoord,
        )

    def _routingZoneInterconnectEndpoints_get(self) -> tuple[GridCoord, GridCoord]:
        """Return the source and destination world coordinates."""

        return (self.sourceGridCoord, self.destinationGridCoord)

    def _routingZoneInterconnectRoutes_get(self):
        """Return solved seam routes owned by this interconnect."""

        interconnectResult = self._routingZoneInterconnect_get()
        if not result_isOkCheck(interconnectResult):
            return ()
        return self.debugContext.interconnectRoutesForInterconnect_get(
            interconnectResult.value.routingZoneInterconnectId
        )

    def _routingZoneBreakout_get(self):
        """Return the EmbeddedRoutingZone handle for this interconnect."""

        interconnectResult = self._routingZoneInterconnect_get()
        if not result_isOkCheck(interconnectResult):
            return None
        
        breakout = interconnectResult.value.breakoutZone
        if not breakout:
            return None
            
        return _boardZoneRuntime_build(
            debugContext=self.debugContext,
            routingZoneId=breakout.routingZoneId,
        )

    def _routingZoneInterconnectDraw_render(self, mode: str = "pixel") -> str:
        """Render this interconnect frame in a compact debug draw mode."""

        return _interconnectDrawingText_build(
            debugContext=self.debugContext,
            sourceGridCoord=self.sourceGridCoord,
            destinationGridCoord=self.destinationGridCoord,
            mode=mode,
        )

    def _routingZoneInterconnectDraw_print(self, mode: str = "pixel") -> None:
        """Print this interconnect frame in a compact debug draw mode."""

        _summary_print(self._routingZoneInterconnectDraw_render(mode=mode))

    def _routingZoneInterconnect_draw(self, mode: str = "pixel") -> None:
        """Alias for routingZoneInterconnectDraw_print."""
        self._routingZoneInterconnectDraw_print(mode=mode)

    def _routingZoneInterconnect_print(self) -> None:
        """Print a summary of the interconnect."""
        self._routingZoneInterconnectDraw_print()

    def _routingZoneInterconnectWorldCanvas_render(self) -> str:
        """Render this interconnect as the world canvas draws it."""

        return _interconnectWorldCanvasText_build(
            debugContext=self.debugContext,
            sourceGridCoord=self.sourceGridCoord,
            destinationGridCoord=self.destinationGridCoord,
        )

    def _routingZoneInterconnectWorldCanvas_print(self) -> None:
        """Print this interconnect as the world canvas draws it."""

        _summary_print(self._routingZoneInterconnectWorldCanvas_render())

    def summary_text(self) -> str:
        """Return this interconnect plus its seam routes."""

        interconnectResult = self.raw_get()
        if not result_isOkCheck(interconnectResult):
            return "interconnect\n  status: missing"
        return _interconnectSummaryText_build(
            debugContext=self.debugContext,
            routingZoneInterconnectId=interconnectResult.value.routingZoneInterconnectId,
        )


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
            "summary_text",
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

    def summary_text(self) -> str:
        """Return a compact summary of this chip placement."""

        return "\n".join(
            [
                f"placement {_chipTitleText_build(self.chipId)}",
                f"  zone: {self.zone_get()}",
                f"  side: {self.side_get()}",
                f"  order: {self.order_get()}",
                f"  point: {self.worldPoint_get()}",
            ]
        )


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
            "all_text",
            "count_get",
            "ids_get",
            "placements_get",
            "routes_get",
            "routes_text",
            "schematic_text",
            "summary_text",
            "zoneForChip_get",
            "zone_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<zones>"

    def all_get(self):
        """Return all placed routing zones."""
        return self._routingZonesAll_get()

    def count_get(self) -> int:
        """Return placed routing-zone count."""
        return self._routingZonesCount_get()

    def ids_get(self):
        """Return all placed routing-zone ids."""
        return self._routingZoneIds_get()

    def all_text(self) -> str:
        """Return readable summaries for all placed routing zones as text."""
        return self._routingZonesAll_render()

    def zone_get(self, columnIndex: int, rowIndex: int):
        """Return one placed routing zone handle by grid coordinate."""
        return self._routingZone_get(columnIndex, rowIndex)

    def zoneForChip_get(self, moduleName: str, functionName: str):
        """Return the placed routing zone handle owning one canonical chip."""
        return self._routingZoneForChip_get(moduleName, functionName)

    def placements_get(self, columnIndex: int, rowIndex: int):
        """Return placements for one placed routing zone."""
        return self._routingZonePlacements_get(columnIndex, rowIndex)

    def routes_get(self, columnIndex: int, rowIndex: int):
        """Return solved zone-local routes for one placed routing zone."""
        return self._routingZoneLocalRoutes_get(columnIndex, rowIndex)

    def routes_text(self, columnIndex: int, rowIndex: int) -> str:
        """Return solved local routes for one placed routing zone as text."""
        return self._routingZoneRoutesDraw_render(columnIndex, rowIndex)

    def schematic_text(self, columnIndex: int, rowIndex: int) -> str:
        """Return a schematic ASCII drawing of one placed routing zone."""
        return self._routingZoneDraw_render(columnIndex, rowIndex)

    def summary_text(self, columnIndex: int, rowIndex: int) -> str:
        """Return one placed routing zone as a readable debug summary."""
        return self._routingZone_render(columnIndex, rowIndex)

    def _routingZonesAll_get(self):
        """Return all placed routing zones."""

        return tuple(
            _boardZoneRuntime_build(
                debugContext=self.debugContext,
                routingZoneId=routingZone.routingZoneId,
            )
            for routingZone in self.debugContext.zones_getAll()
        )

    def _routingZonesCount_get(self) -> int:
        """Return placed routing-zone count."""

        return len(self._routingZonesAll_get())

    def _routingZoneIds_get(self):
        """Return all placed routing-zone ids."""

        return tuple(
            routingZoneHandle.routingZoneId for routingZoneHandle in self._routingZonesAll_get()
        )

    def _routingZonesAll_render(self) -> str:
        """Render readable summaries for all placed routing zones."""

        return "\n\n".join(
            self._routingZone_render(
                routingZoneId.id.columnIndex,
                routingZoneId.id.rowIndex,
            )
            for routingZoneId in self._routingZoneIds_get()
            if isinstance(routingZoneId.id, GridCoord)
        )

    def _routingZonesAll_print(self) -> None:
        """Print readable summaries for all placed routing zones."""

        _summary_print(self._routingZonesAll_render())

    def _routingZone_get(self, columnIndex: int, rowIndex: int):
        """Return one placed routing zone handle by grid coordinate."""

        return _boardZoneRuntime_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def _routingZoneForChip_get(self, moduleName: str, functionName: str):
        """Return the placed routing zone handle owning one canonical chip."""

        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        zoneResult = self.debugContext.zoneOwningChipResult_get(chipId)
        if not result_isOkCheck(zoneResult):
            raise KeyError(f"No placed zone for chip {_chipTitleText_build(chipId)!r}")
        return _boardZoneRuntime_build(
            debugContext=self.debugContext,
            routingZoneId=zoneResult.value.routingZoneId,
        )

    def _routingZonePlacements_get(self, columnIndex: int, rowIndex: int):
        """Return placements for one placed routing zone."""

        return self.debugContext.placementsForZone_get(
            RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
        )

    def _routingZoneLocalRoutes_get(self, columnIndex: int, rowIndex: int):
        """Return solved zone-local routes for one placed routing zone."""

        return self.debugContext.zoneLocalRoutesForZone_get(
            RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
        )

    def _routingKernel_get(self, columnIndex: int, rowIndex: int, side: str = "intra"):
        """Return one routing kernel handle for the specified zone side."""

        return self._routingZone_get(columnIndex, rowIndex).kernel_get(side)

    def _routingZoneRoutesDraw_render(self, columnIndex: int, rowIndex: int) -> str:
        """Render solved local routes for one placed routing zone."""

        return _zoneRoutesText_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def _routingZoneRoutesDraw_print(self, columnIndex: int, rowIndex: int) -> None:
        """Print solved local routes for one placed routing zone."""

        _summary_print(self._routingZoneRoutesDraw_render(columnIndex, rowIndex))

    def _routingZone_render(self, columnIndex: int, rowIndex: int) -> str:
        """Render one placed routing zone as a readable debug summary."""

        return _zoneSummaryText_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def _routingZoneDraw_render(self, columnIndex: int, rowIndex: int) -> str:
        """Render a schematic ASCII drawing of one placed routing zone."""

        return _zoneDrawingLines_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def _routingZoneDraw_print(self, columnIndex: int, rowIndex: int) -> None:
        """Print a schematic ASCII drawing of one placed routing zone."""

        _summary_print(self._routingZoneDraw_render(columnIndex, rowIndex))

    def _routingZone_draw(self, columnIndex: int, rowIndex: int) -> None:
        """Alias for routingZoneDraw_print."""
        self._routingZoneDraw_print(columnIndex, rowIndex)

    def _routingZone_print(self, columnIndex: int, rowIndex: int) -> None:
        """Print one placed routing zone as a readable debug summary."""

        _summary_print(self._routingZone_render(columnIndex, rowIndex))

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
            "gridCanvas_text",
            "gridSchematic_text",
            "gridSize_get",
            "gridStyle_text",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<world>"

    def gridSize_get(self) -> "GridCoord":
        """Return placed world grid size."""

        return self.debugContext.placedRoutingZoneGrid.gridSize

    def gridCanvas_text(self) -> str:
        """Render the full world as a chip-body + route-wire ASCII canvas."""

        return _worldCanvasText_build(self.debugContext)

    def gridSchematic_text(self) -> str:
        """Render the full world as a spatial ASCII schematic of all zones."""

        return _worldDrawText_build(self.debugContext)

    def gridStyle_text(self, style: str = "zones") -> str:
        """Render the placed world grid in one named debug style."""

        return _gridText_build(
            debugContext=self.debugContext,
            style=style,
        )



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
            "all_text",
            "count_get",
            "interconnect_get",
            "routes_get",
            "summary_text",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<interconnects>"

    def all_get(self):
        """Return all placed routing-zone interconnects."""
        return self._routingZoneInterconnectsAll_get()

    def count_get(self) -> int:
        """Return interconnect count."""
        return self._routingZoneInterconnectsCount_get()

    def all_text(self) -> str:
        """Return readable summaries for all placed routing-zone interconnects."""
        return self._routingZoneInterconnectsAll_render()

    def interconnect_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return one interconnect handle by endpoint coordinates."""
        return self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )

    def routes_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return solved seam routes for one interconnect."""
        return self._routingZoneInterconnectRoutes_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )

    def summary_text(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> str:
        """Return one interconnect plus its seam routes."""
        return self._routingZoneInterconnect_render(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )

    def _routingZoneInterconnectsAll_get(self):
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

    def _routingZoneInterconnectsCount_get(self) -> int:
        """Return interconnect count."""

        return len(self._routingZoneInterconnectsAll_get())

    def _routingZoneInterconnectsAll_render(self) -> str:
        """Render readable summaries for all placed routing-zone interconnects."""

        return "\n\n".join(
            interconnect.summary_text()
            for interconnect in self._routingZoneInterconnectsAll_get()
        )

    def _routingZoneInterconnectsAll_print(self) -> None:
        """Print readable summaries for all placed routing-zone interconnects."""

        _summary_print(self._routingZoneInterconnectsAll_render())

    def _routingZoneInterconnect_get(
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

    def _routingZoneInterconnectRoutes_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return solved seam routes for one interconnect."""

        interconnectHandle = self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )
        return interconnectHandle.routes_get()

    def _routingZoneBreakout_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return the EmbeddedRoutingZone for one interconnect."""

        interconnectHandle = self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )
        return interconnectHandle._routingZoneBreakout_get()

    def _routingZoneInterconnect_render(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> str:
        """Render one interconnect plus its seam routes."""

        interconnectHandle = self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )
        return interconnectHandle.summary_text()

    def _routingZoneInterconnect_print(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> None:
        """Print one interconnect plus its seam routes."""

        _summary_print(
            self._routingZoneInterconnect_render(
                sourceColumnIndex=sourceColumnIndex,
                sourceRowIndex=sourceRowIndex,
                destinationColumnIndex=destinationColumnIndex,
                destinationRowIndex=destinationRowIndex,
            )
        )

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
            "forChip_get",
            "forZone_get",
            "gridLongHaulForChip_get",
            "gridLongHaul_get",
            "seamCrossing_get",
            "seamForChip_get",
            "zoneLocalForChip_get",
            "zoneLocal_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<routes>"

    def _routingCallObligations_get(self):
        """Return all call-route obligations."""

        return (
            self.debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations
        )

    def _chipInternalRoutes_get(self):
        """Return all solved chip-internal routes."""

        return self.debugContext.chipInternalSolvedRouteSet.chipInternalSolvedRoutes


    def _routingZoneLocalRoutes_get(self):
        """Return all solved zone-local routes."""

        return (
            self.debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        )


    def _routingZoneInterconnectRoutes_get(self):
        """Return all solved seam-crossing interconnect routes."""

        return (
            self.debugContext.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes
        )

    def _routingZoneGridSolvedRoutes_get(self):
        """Return all solved grid-level long-haul routes."""

        return (
            self.debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
        )

    def _chipRoutes_get(self, moduleName: str, functionName: str):
        """Return solved chip-internal routes for one canonical chip."""

        return self.debugContext.chipRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def _routingZoneLocalForChip_get(self, moduleName: str, functionName: str):
        """Return solved zone-local routes touching one canonical chip."""

        return self.debugContext.zoneLocalRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def _routingZoneLocalForZone_get(self, columnIndex: int, rowIndex: int):
        """Return solved zone-local routes for one placed routing zone."""

        return self.debugContext.zoneLocalRoutesForZone_get(
            RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))
        )

    def _routingZoneInterconnectForChip_get(self, moduleName: str, functionName: str):
        """Return solved seam routes touching one canonical chip."""

        return self.debugContext.interconnectRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def _routingZoneGridForChip_get(self, moduleName: str, functionName: str):
        """Return solved grid-level routes touching one canonical chip."""

        return self.debugContext.gridRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def callObligations_get(self):
        """Return all call-route obligations."""

        return self._routingCallObligations_get()

    def chipInternal_get(self):
        """Return all solved chip-internal routes."""

        return self._chipInternalRoutes_get()

    def zoneLocal_get(self):
        """Return all solved zone-local routes."""

        return self._routingZoneLocalRoutes_get()

    def seamCrossing_get(self):
        """Return all solved seam-crossing interconnect routes."""

        return self._routingZoneInterconnectRoutes_get()

    def gridLongHaul_get(self):
        """Return all solved grid-level long-haul routes."""

        return self._routingZoneGridSolvedRoutes_get()

    def forChip_get(self, moduleName: str, functionName: str):
        """Return solved chip-internal routes for one canonical chip."""

        return self._chipRoutes_get(moduleName, functionName)

    def forZone_get(self, columnIndex: int, rowIndex: int):
        """Return solved zone-local routes for one placed routing zone."""

        return self._routingZoneLocalForZone_get(columnIndex, rowIndex)

    def zoneLocalForChip_get(self, moduleName: str, functionName: str):
        """Return solved zone-local routes touching one canonical chip."""

        return self._routingZoneLocalForChip_get(moduleName, functionName)

    def seamForChip_get(self, moduleName: str, functionName: str):
        """Return solved seam routes touching one canonical chip."""

        return self._routingZoneInterconnectForChip_get(moduleName, functionName)

    def gridLongHaulForChip_get(self, moduleName: str, functionName: str):
        """Return solved grid-level routes touching one canonical chip."""

        return self._routingZoneGridForChip_get(moduleName, functionName)

@dataclass(frozen=True)
class DebugDocumentView:
    """Interactive inspection view over the loaded source document."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "callCount_get",
            "callingDepth_get",
            "chipCount_get",
            "raw_get",
            "root_get",
            "title_get",
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

    def root_get(self) -> BoardChip:
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

@dataclass(frozen=True)
class DebugCircuitView:
    """Interactive inspection view over the validated circuit graph."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "callCount_get",
            "calls_get",
            "chipCount_get",
            "chips_get",
            "raw_get",
            "root_get",
            "title_get",
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

    def root_get(self) -> BoardChip:
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

@dataclass(frozen=True)
class DebugConfigView:
    """Interactive inspection view over validated application config."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "channelSense_get",
            "gridSize_get",
            "interconnectCount_get",
            "moduleBoxPadding_get",
            "occupancyPolicy_get",
            "packingPolicy_get",
            "pathPolicy_get",
            "raw_get",
            "sense_get",
            "zoneCount_get",
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

        dimensions = (
            self.debugContext.signalFlowConfig.routingZoneGridConfig.routingZoneGridDimensions
        )
        return GridCoord(
            columnIndex=dimensions.columnCount,
            rowIndex=dimensions.rowCount,
        )

    def zoneCount_get(self) -> int:
        """Return configured zone count."""

        return (
            self.debugContext.signalFlowConfig.routingZoneGridConfig.routingZoneCount_calculate()
        )

    def interconnectCount_get(self) -> int:
        """Return configured interconnect count."""

        return (
            self.debugContext.signalFlowConfig.routingZoneGridConfig.routingZoneInterconnectCount_calculate()
        )

    def moduleBoxPadding_get(self) -> int:
        """Return the configured module-border padding."""

        return self.debugContext.signalFlowConfig.routingZoneGridConfig.moduleBoxPadding

    def pathPolicy_get(self) -> str:
        """Return the configured grid path policy."""

        return self.debugContext.signalFlowConfig.routingZoneGridConfig.pathPolicy.value

    def channelSense_get(self) -> str:
        """Return the configured default channel sense."""

        return (
            self.debugContext.signalFlowConfig.routingZoneGridConfig.channelSense.value
        )

    def occupancyPolicy_get(self) -> str:
        """Return the configured default occupancy policy."""

        return (
            self.debugContext.signalFlowConfig.routingZoneGridConfig.occupancyPolicy.value
        )

    def packingPolicy_get(self) -> str:
        """Return the configured default lane-packing policy."""

        return (
            self.debugContext.signalFlowConfig.routingZoneGridConfig.packingPolicy.value
        )

@dataclass(frozen=True)
class DebugTopologyGridView:
    """Interactive inspection view over the unplaced topology grid."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return [
            "interconnectAt_get",
            "interconnectCount_get",
            "raw_get",
            "size_get",
            "zoneAt_get",
            "zoneCount_get",
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
            "raw_get",
            "summary_text",
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

    def summary_text(self) -> str:
        """Return all assignments as a readable summary."""

        lines = ["assignment"]
        for assignment in self.all_get():
            lines.append(
                "  - "
                f"{_chipTitleText_build(assignment.chipRef.chipId)} -> "
                f"{assignment.routingZoneId.id} "
                f"{assignment.terminalSide.value}"
            )
        return "\n".join(lines)


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
            "raw_get",
            "summary_text",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation."""

        return "<obligations>"

    def raw_get(self):
        """Return the raw `RouteObligationSet`."""

        return self.debugContext.routeObligationSet

    def calls_get(self):
        """Return call-route obligations."""

        return (
            self.debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations
        )

    def chipInternal_get(self):
        """Return chip-internal obligations."""

        return (
            self.debugContext.routeObligationSet.chipInternalRouteObligationSet.chipInternalRouteObligations
        )

    def count_get(self) -> int:
        """Return the total obligation count."""

        return len(self.calls_get()) + len(self.chipInternal_get())

    def summary_text(self) -> str:
        """Return obligations as a readable summary."""

        return "\n".join(
            [
                "obligations",
                f"  call: {len(self.calls_get())}",
                f"  chip_internal: {len(self.chipInternal_get())}",
            ]
        )


@dataclass(frozen=True)
class DebugDiagnosticView:
    """Interactive inspection view over accumulated diagnostics."""

    debugContext: NewEngineDebugContext

    def __dir__(self) -> list[str]:
        """Return curated interactive attributes for tab completion."""

        return ["all_get", "codes_get", "count_get", "raw_get", "summary_text"]

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

    def summary_text(self) -> str:
        """Return diagnostics as a readable summary."""

        if not self.all_get():
            return "diagnostics\n  <none>"
        return "\n".join(
            [
                "diagnostics",
                *(f"  - {diagnostic.code}" for diagnostic in self.all_get()),
            ]
        )


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
            "calls",
            "chipCount_get",
            "chips",
            "diagnostics_getAll",
            "interconnectCount_get",
            "interconnects",
            "placementForChipResult_get",
            "rootPlacementResult_get",
            "routes",
            "routingZoneCount_get",
            "world",
            "zoneOwningChipResult_get",
            "zones",
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

        return (
            self.placedRoutingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects
        )

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

    def interconnectRoutesForZone_get(self, routingZoneId: RoutingZoneId):
        """Return all solved seam routes owned by one placed routing zone."""

        return self.routingZoneInterconnectSolvedRouteSet.routesForZone_get(routingZoneId)

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
    loadSnippetPath: str | None = None,
) -> int:
    """Run the operator-facing debug REPL for one source document.

    The REPL is intentionally thin over the already-built debug context. This
    function is responsible only for lifecycle concerns such as prompt setup,
    completion, startup snippet loading, display hooks, and console cleanup.

    Args:
        documentDict: Parsed YAML document to inspect.
        sourcePath: Optional source description shown in the REPL banner.
        loadSnippetPath: Optional snippet path to execute before entering the
            interactive console.

    Returns:
        Process-style exit code for the REPL session.
    """

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(documentDict)
    if not result_isOkCheck(debugContextResult):
        _diagnostics_printToStdout()
        return 1

    debugContext: NewEngineDebugContext = debugContextResult.value
    sourceDescription: str = sourcePath or "<in-memory>"
    banner: str = _replBanner_build(sourceDescription)
    previousPs1: str | None = getattr(sys, "ps1", None)
    previousPs2: str | None = getattr(sys, "ps2", None)
    previousDisplayHook = sys.displayhook
    prompt = _replPrompts_configure(debugContext)
    replLocals: dict[str, object] = {}
    replLocals.update(_replLocals_build(debugContext, prompt=prompt, replLocals=replLocals))
    if loadSnippetPath is not None:
        _snippetFile_run(loadSnippetPath, replLocals)
    _readline_setup(replLocals)
    _displayHook_configure()
    interactiveConsole = _SignalFlowInteractiveConsole(locals=replLocals)
    try:
        interactiveConsole.interact(banner=banner, exitmsg="")
    finally:
        _readlineHistory_save()
        _replPrompts_restore(previousPs1, previousPs2)
        _displayHook_restore(previousDisplayHook)
    return 0


def newEngineDebugSnippet_run(
    documentDict: dict[str, object],
    snippetPath: str,
) -> int:
    """Run one snippet against the new-engine debug context and exit.

    Args:
        documentDict: Parsed YAML document to inspect.
        snippetPath: Filesystem path to the snippet file to execute.

    Returns:
        Process-style exit code for the snippet run.
    """

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(documentDict)
    if not result_isOkCheck(debugContextResult):
        _diagnostics_printToStdout()
        return 1

    debugContext: NewEngineDebugContext = debugContextResult.value
    replLocals: dict[str, object] = {}
    replLocals.update(_replLocals_build(debugContext, replLocals=replLocals))
    _snippetFile_run(snippetPath, replLocals)
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


@dataclass
class _ReplTitleController:
    """Mutable title-format controller for the live REPL prompt."""

    prompt: _ReplPs1

    def __dir__(self) -> list[str]:
        return ["full", "len_truncate"]

    def __repr__(self) -> str:
        return "<prompt.title>"

    def full(self) -> _ReplTitleController:
        """Render the document title in full."""

        self.prompt.titleTransform = None
        return self

    def len_truncate(self, maxLength: int) -> _ReplTitleController:
        """Keep only the first `maxLength` title characters."""

        if maxLength < 0:
            raise ValueError("maxLength must be >= 0")
        self.prompt.titleTransform = lambda title: title[:maxLength]
        return self


@dataclass
class _ReplPs1:
    """Dynamic sys.ps1 object whose __str__ is called fresh before every prompt.

    Python calls str(sys.ps1) before displaying each primary prompt, so this
    object naturally reflects live state (e.g. current diagnostic count).
    """

    debugContext: NewEngineDebugContext
    titleTransform: Callable[[str], str] | None = None
    title: _ReplTitleController = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.title = _ReplTitleController(prompt=self)

    def __dir__(self) -> list[str]:
        return ["print", "reset", "title", "toStr"]

    def __repr__(self) -> str:
        return "<prompt>"

    def _titleText_get(self) -> str:
        """Return the current document title after prompt-local transforms."""

        title = self.debugContext.circuitDocument.title or "untitled"
        if self.titleTransform is None:
            return title
        return self.titleTransform(title)

    def toStr(self) -> str:
        """Render the current prompt as plain text (no ANSI codes)."""

        display = _promptDisplayText_build(str(self))
        return re.sub(r"\x1b\[[0-9;]*m", "", display)

    def print(self) -> None:
        """Print the current prompt display text."""

        print(self.toStr(), end="")

    def reset(self) -> _ReplPs1:
        """Reset prompt-local formatting to defaults."""

        self.title.full()
        return self

    def __str__(self) -> str:
        ctx = self.debugContext
        title = self._titleText_get()

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
            _promptSegment_build(f"{title}[", _ANSI_CYAN)
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

    Calling any run method rebuilds the full pipeline from the source document
    and refreshes the live REPL namespace (ctx, zones, chips, world, etc.).
    """

    debugContext: NewEngineDebugContext
    replLocals: dict  # mutable reference to live REPL namespace

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

    def _rebuildAndRefresh(self, label: str) -> bool:
        """Rebuild the full pipeline and refresh the live REPL namespace."""
        diagnosticStack.stack_clear()
        newContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            self.debugContext.documentDict
        )
        if not result_isOkCheck(newContextResult):
            print(
                _ansiWrap_build(label, _ANSI_BOLD, _ANSI_YELLOW)
                + ": "
                + _ansiWrap_build("pipeline rebuild failed", _ANSI_RED)
            )
            _diagnostics_printToStdout()
            return False
        newLocals = _replLocals_build(
            newContextResult.value, replLocals=self.replLocals
        )
        self.replLocals.update(newLocals)
        return True

    def status_print(self) -> None:
        """Print current zone geometry derivation status."""
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
                "per-column width + per-row height, full pipeline rebuild on demand",
                _ANSI_WHITE,
            ),
        ]
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
            "    " + _ansiWrap_build("chips.all_text()", _ANSI_DIM),
            "    "
            + _ansiWrap_build("chip = chips.chip_get('App.ts', 'main()')", _ANSI_DIM),
            "    " + _ansiWrap_build("chip.schematic_text()", _ANSI_DIM),
            "    " + _ansiWrap_build("zones.all_text()", _ANSI_DIM),
            "    " + _ansiWrap_build("zone = zones.zone_get(1, 1)", _ANSI_DIM),
            "    " + _ansiWrap_build("zone.placements_get()", _ANSI_DIM),
            "    " + _ansiWrap_build("interconnects.all_text()", _ANSI_DIM),
            "    " + _ansiWrap_build("world.gridStyle_text('zones')", _ANSI_DIM),
        ]
        print("\n".join(lines))

    def chipGeometryPush_run(self) -> None:
        """Re-derive every zone's natural frame from chip geometry and refresh state."""
        print(
            _ansiWrap_build("chipGeometryPush_run", _ANSI_BOLD, _ANSI_CYAN)
            + ": rebuilding pipeline from chip geometry…"
        )
        if self._rebuildAndRefresh("chipGeometryPush_run"):
            print(
                "  done — "
                + _ansiWrap_build(
                    "ctx  zones  chips  world  interconnects  routes",
                    _ANSI_MAGENTA,
                )
                + " refreshed"
            )

    def zonesNormalize_run(self) -> None:
        """Run the per-row/column normalization cascade and refresh state."""
        print(
            _ansiWrap_build("zonesNormalize_run", _ANSI_BOLD, _ANSI_CYAN)
            + ": rebuilding pipeline with per-column/row normalization…"
        )
        if self._rebuildAndRefresh("zonesNormalize_run"):
            print(
                "  done — zones normalized to column max-width / row max-height\n"
                "  "
                + _ansiWrap_build(
                    "ctx  zones  chips  world  interconnects  routes",
                    _ANSI_MAGENTA,
                )
                + " refreshed"
            )

    def zoneRecalculate_run(self, columnIndex: int, rowIndex: int) -> None:
        """Recalculate one zone from chip geometry, re-solve routing and seams."""
        print(
            _ansiWrap_build("zoneRecalculate_run", _ANSI_BOLD, _ANSI_CYAN)
            + f"({columnIndex}, {rowIndex}): rebuilding pipeline…"
        )
        if self._rebuildAndRefresh("zoneRecalculate_run"):
            print(
                f"  done — zone ({columnIndex},{rowIndex}) recalculated\n"
                "  "
                + _ansiWrap_build(
                    "ctx  zones  chips  world  interconnects  routes",
                    _ANSI_MAGENTA,
                )
                + " refreshed"
            )


def _replLocals_build(
    debugContext: NewEngineDebugContext,
    prompt: _ReplPs1 | None = None,
    replLocals: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the curated local namespace exposed to the debug REPL."""

    if replLocals is None:
        replLocals = {}
    livePrompt = prompt or _ReplPs1(debugContext=debugContext)
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
        "prompt": livePrompt,
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
        "load": lambda path: _snippetFile_run(path, replLocals),
        "board_backend_get": _boardBackend_get,
        "board_backend_set": _boardBackend_set,
        "solution_realize": solution_realize,
        "solution_materialize": solution_materialize,
        "workflows": DebugWorkflowView(debugContext=debugContext, replLocals=replLocals),
        "ls": ls,
        "tree": tree,
    }


def _replPrompts_configure(
    debugContext: NewEngineDebugContext | None = None,
) -> _ReplPs1 | None:
    """Configure a context-bearing colored prompt.

    When called with a debug context sys.ps1 is set to a _ReplPs1 object.
    Python calls str(sys.ps1) before every primary prompt, so the indicator
    (diagnostic error count or green checkmark) stays live as you work.

    Color scheme:
      title[          cyan        — full document context
      ✓               bold green  — no diagnostic errors
      N!              bold red    — N errors in the diagnostic stack
      ]>              cyan
      (after >)       ANSI reset  — user input in terminal default color
    """

    if debugContext is None:
        sys.ps1 = "> "
        sys.ps2 = "... "
        return None

    prompt = _ReplPs1(debugContext=debugContext)
    sys.ps1 = prompt
    sys.ps2 = _ansiPrompt_build(
        "... ",
        _ANSI_DIM,
        trailingAnsiCodes=(_ANSI_RESET,),
    )
    return prompt


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
            "'App.ts:main()'. Run chips.names_get() to list valid titles."
        )
    moduleName, functionName = chipTitle.split(":", 1)
    if not moduleName or not functionName:
        raise ValueError(
            "Invalid chip title "
            f"{chipTitle!r}. Use 'moduleName:functionName', for example "
            "'App.ts:main()'. Run chips.names_get() to list valid titles."
        )
    return (moduleName, functionName)


def _chipHandle_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> BoardChip:
    """Build one validated chip handle for interactive use."""

    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        raise KeyError(
            "Unknown chip "
            f"{_chipTitleText_build(chipId)!r}. Run chips.names_get() to list valid "
            "titles."
        )
    return BoardChip(
        chipId=chipId,
        rawProvider=lambda: debugContext.chipResult_get(chipId),
        titleProvider=lambda: _chipTitleText_build(chipId),
        geometryProvider=lambda: _chipGeometry_build(
            debugContext=debugContext,
            chipId=chipId,
        ),
        sizeProvider=lambda: _textBlockSize_build(
            _chipGeometry_build(
                debugContext=debugContext,
                chipId=chipId,
            ).drawLines
        ),
        terminalsProvider=lambda: debugContext.terminalCountsForChip_build(chipId),
        localTerminalPositionsProvider=lambda wall: _chipTerminalLocalPositions_build(
            debugContext=debugContext,
            chipId=chipId,
            wall=wall,
        ),
        worldTerminalPositionsProvider=lambda wall: _chipTerminalWorldPositions_build(
            debugContext=debugContext,
            chipId=chipId,
            wall=wall,
        ),
        placementProvider=lambda: debugContext.placementForChipResult_get(chipId),
        locationProvider=lambda: (
            debugContext.locationRecordsForChip_build(chipId)[0]
            if debugContext.locationRecordsForChip_build(chipId)
            else None
        ),
        locationsProvider=lambda: debugContext.locationRecordsForChip_build(chipId),
        routesProvider=lambda: debugContext.chipRoutesForChip_get(chipId),
        internalBoardProvider=lambda: _chipInternalBoardKernelRuntime_build(
            debugContext=debugContext,
            chipId=chipId,
        ),
        worldFrameProvider=lambda: _chipWorldFrameOrNone_build(
            debugContext=debugContext,
            chipId=chipId,
        ),
        childrenProvider=lambda: tuple(
            _chipHandle_build(
                debugContext=debugContext,
                chipId=circuitCall.destinationChipRef.chipId,
            )
            for circuitCall in (
                debugContext.circuitDocument.circuitCallSet.outgoingCallsForChip_get(
                    chipId
                )
            )
        ),
        schematicProvider=lambda: "\n".join(
            _chipGeometry_build(
                debugContext=debugContext,
                chipId=chipId,
            ).drawLines
        ),
        summaryProvider=lambda: _chipSummaryText_build(
            debugContext=debugContext,
            chipId=chipId,
        ),
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


def _chipGeometry_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> ChipDrawGeometry:
    """Resolve a chip from the debug context and delegate to canonical geometry.

    The canonical chip-local render truth lives in `models.chip.
    chipDrawGeometry_build(...)` so the debugger and the board renderer share
    one geometry source.
    """

    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        return ChipDrawGeometry(
            drawLines=("<missing chip>",),
            lineCount=1,
            lineWidth=len("<missing chip>"),
            boxTopLineOffset=0,
            boxBottomLineOffset=0,
            boxLeftColumnOffset=0,
            boxRightColumnOffset=len("<missing chip>") - 1,
            visibleTopLineOffset=0,
            visibleBottomLineOffset=0,
            visibleLeftColumnOffset=0,
            visibleRightColumnOffset=len("<missing chip>") - 1,
        )
    return chipDrawGeometry_build(chipResult.value)


def _chipDrawingLines_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> tuple[str, ...]:
    """Resolve one chip's canonical draw lines from chip-local geometry truth."""

    return _chipGeometry_build(
        debugContext=debugContext,
        chipId=chipId,
    ).drawLines


def _chipWorldFrameOrNone_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
) -> DebugChipWorldFrame | None:
    """Build the placed world-frame for one canonical chip.

    Args:
        debugContext: Live debug context that owns chip placement and zone
            geometry.
        chipId: Canonical chip id to resolve.

    Returns:
        Typed world-frame record for the full chip drawing when the chip is
        placed successfully, otherwise `None`.
    """

    chipResult = debugContext.chipResult_get(chipId)
    placementResult = debugContext.placementForChipResult_get(chipId)
    zoneResult = debugContext.zoneOwningChipResult_get(chipId)
    if not (
        result_isOkCheck(chipResult)
        and result_isOkCheck(placementResult)
        and result_isOkCheck(zoneResult)
    ):
        return None

    geometryResult = chipLocalGeometryResult_build(chipResult.value)
    if not result_isOkCheck(geometryResult):
        return None

    terminalRegionResult = routingZoneRegionByIdResult_get(
        zoneResult.value,
        placementResult.value.chipTerminalRegionId,
    )
    if not result_isOkCheck(terminalRegionResult):
        return None

    regionSide = placementResult.value.chipTerminalRegionId.routingZoneRegionSide
    if regionSide is None:
        return None

    placementGeometry = chipCanvasPlacementGeometry_build(
        chipLocalGeometry=geometryResult.value,
        routingZoneSense=zoneResult.value.routingZoneSense,
        regionSide=regionSide,
        terminalRegionVerticalStart=(
            terminalRegionResult.value.routingZoneRegionFrame.verticalStart
        ),
        terminalRegionHorizontalStart=(
            terminalRegionResult.value.routingZoneRegionFrame.horizontalStart
        ),
        stackOffset=_chipStackOffsetOrNone_build(
            debugContext=debugContext,
            zone=zoneResult.value,
            chipPlacement=placementResult.value,
        )
        or 0,
    )

    topLeft = (
        placementGeometry.drawWorldColumn,
        placementGeometry.drawWorldRow,
    )
    bottomRight = (
        placementGeometry.drawWorldColumn + geometryResult.value.lineWidth - 1,
        placementGeometry.drawWorldRow + geometryResult.value.lineCount - 1,
    )
    return DebugChipWorldFrame(
        topLeft=topLeft,
        bottomRight=bottomRight,
        widthColumns=geometryResult.value.lineWidth,
        heightRows=geometryResult.value.lineCount,
    )


def _chipTerminalSideResult_build(wall: str) -> Result[ChipTerminalSide]:
    """Build one terminal side enum from a REPL wall string.

    Args:
        wall: Lowercase wall name such as ``"west"`` or ``"east"``.

    Returns:
        Successful result containing the matching `ChipTerminalSide`, or a
        failed result when the wall text is not recognized.
    """

    wallNormalized = wall.strip().lower()
    wallToSide: dict[str, ChipTerminalSide] = {
        "north": ChipTerminalSide.NORTH,
        "south": ChipTerminalSide.SOUTH,
        "east": ChipTerminalSide.EAST,
        "west": ChipTerminalSide.WEST,
    }
    terminalSide = wallToSide.get(wallNormalized)
    if terminalSide is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="debug.chip.wall.invalid",
            message="Unknown chip wall requested for terminal positions",
            context=(wall,),
        )
        return resultErr_build()
    return resultOk_build(terminalSide)


def _chipTerminalLocalPositions_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
    wall: str,
) -> dict[str, tuple[int, int]]:
    """Build chip-local terminal positions for one chip wall.

    Args:
        debugContext: Live debug context that owns chip geometry.
        chipId: Canonical chip id to inspect.
        wall: Lowercase wall name such as ``"west"`` or ``"east"``.

    Returns:
        Mapping from terminal name to inclusive chip-local
        ``(columnIndex, rowIndex)`` positions inside the chip drawing.
    """

    terminalSideResult = _chipTerminalSideResult_build(wall)
    chipResult = debugContext.chipResult_get(chipId)
    if not (
        result_isOkCheck(terminalSideResult)
        and result_isOkCheck(chipResult)
    ):
        return {}

    geometryResult = chipLocalGeometryResult_build(chipResult.value)
    if not result_isOkCheck(geometryResult):
        return {}

    terminalSide = terminalSideResult.value
    geometry = geometryResult.value

    if terminalSide is ChipTerminalSide.WEST:
        terminalColumnIndex = geometry.boxLeftColumnOffset
    elif terminalSide is ChipTerminalSide.EAST:
        terminalColumnIndex = geometry.boxRightColumnOffset
    else:
        return {}

    terminalPositions: dict[str, tuple[int, int]] = {}
    for terminalOffset in geometry.terminalLineOffsets:
        if terminalOffset.chipTerminalRef.terminalSide is not terminalSide:
            continue
        terminalPositions[terminalOffset.terminalName] = (
            terminalColumnIndex,
            terminalOffset.lineOffset,
        )
    return terminalPositions


def _chipTerminalWorldPositions_build(
    debugContext: NewEngineDebugContext,
    chipId: ChipId,
    wall: str,
) -> dict[str, tuple[int, int]]:
    """Build world-coordinate terminal positions for one chip wall.

    Args:
        debugContext: Live debug context that owns zone placement and attach
            geometry.
        chipId: Canonical chip id to inspect.
        wall: Lowercase wall name such as ``"west"`` or ``"east"``.

    Returns:
        Mapping from terminal name to inclusive world
        ``(columnIndex, rowIndex)`` positions.
    """

    terminalSideResult = _chipTerminalSideResult_build(wall)
    zoneResult = debugContext.zoneOwningChipResult_get(chipId)
    chipResult = debugContext.chipResult_get(chipId)
    if not (
        result_isOkCheck(terminalSideResult)
        and result_isOkCheck(zoneResult)
        and result_isOkCheck(chipResult)
    ):
        return {}

    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        debugContext.circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(chipLocalGeometrySetResult):
        return {}

    attachPointSetResult = chipAttachPointSetResult_buildFromPlacedZone(
        zoneResult.value,
        chipLocalGeometrySetResult.value,
        debugContext.circuitDocument,
    )
    if not result_isOkCheck(attachPointSetResult):
        return {}

    chipRef = chipResult.value.chipRef_build()
    terminalSide = terminalSideResult.value
    terminalPositions: dict[str, tuple[int, int]] = {}
    for attachPoint in attachPointSetResult.value.attachPointsForChip_get(chipRef):
        if attachPoint.terminalSide is not terminalSide:
            continue
        terminalPositions[attachPoint.terminalName] = (
            attachPoint.worldColumn,
            attachPoint.worldRow,
        )
    return terminalPositions


def _chipStackOffsetOrNone_build(
    debugContext: NewEngineDebugContext,
    zone: RoutingZone,
    chipPlacement: ChipPlacement,
) -> int | None:
    """Build the cumulative stack offset for one placed chip.

    Args:
        debugContext: Live debug context that owns canonical chip geometry.
        zone: Owning placed routing zone of the chip.
        chipPlacement: Placement whose stack offset is required.

    Returns:
        Cumulative stack offset used by the canonical world compositor, or
        `None` when the required chip geometry cannot be resolved.
    """

    regionSide = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
    if regionSide is None:
        return None

    sidePlacements: list[ChipPlacement] = sorted(
        (
            placement
            for placement in zone.chipPlacementSet.placements
            if placement.chipTerminalRegionId.routingZoneRegionSide is regionSide
        ),
        key=lambda placement: placement.orderIndex,
    )

    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        debugContext.circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(chipLocalGeometrySetResult):
        return None

    stackOffsetResult = chipPlacementStackOffsetResult_build(
        sidePlacements=sidePlacements,
        targetPlacement=chipPlacement,
        chipLocalGeometrySet=chipLocalGeometrySetResult.value,
        routingZoneSense=zone.routingZoneSense,
        regionSide=regionSide,
    )
    if not result_isOkCheck(stackOffsetResult):
        return None
    return stackOffsetResult.value


def _zoneDrawingLines_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Resolve a zone from the debug context and delegate to the canonical drawer.

    The canonical drawing logic lives in
    `models.routing_zone.routingZoneDrawLines_build` so that the debugger and
    the final renderer share a single representation.
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

    regionResult = routingZoneRegionByIdResult_get(
        routingZone,
        chipPlacement.chipTerminalRegionId,
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
        f"  regions: {len(routingZoneRegionSetAll_get(routingZone))}",
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


def _interconnectDrawingText_build(
    debugContext: NewEngineDebugContext,
    sourceGridCoord: GridCoord,
    destinationGridCoord: GridCoord,
    mode: str = "pixel",
) -> str:
    """Build a compact pixel draw for one placed interconnect frame."""

    interconnectResult = (
        debugContext.placedRoutingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=sourceGridCoord,
            destinationGridCoord=destinationGridCoord,
        )
    )
    if not result_isOkCheck(interconnectResult):
        return "interconnect draw\n  status: missing"

    interconnect = interconnectResult.value
    frame = interconnect.routingZoneInterconnectFrame
    axisResult = interconnect.interconnectAxisResult_get()
    if not result_isOkCheck(axisResult):
        return "interconnect draw\n  error: missing axis"

    if mode != "pixel":
        return "interconnect draw\n  expected mode: pixel"

    if axisResult.value is RoutingZoneInterconnectAxis.HORIZONTAL:
        header = (
            " ".join(
                str(frame.horizontalStart + index)
                for index in range(frame.horizontalSpan)
            )
            if frame.horizontalSpan > 0
            else ""
        )
        rows = ["▓" * frame.horizontalSpan for _ in range(frame.verticalSpan)]
        legend = [
            "",
            "legend:",
            (
                "  ▓   seam/interconnect  "
                f"[col={frame.horizontalStart}.."
                f"{frame.horizontalStart + frame.horizontalSpan}  "
                f"row={frame.verticalStart}.."
                f"{frame.verticalStart + frame.verticalSpan}]"
            ),
        ]
        return "\n".join(([header] if header else []) + rows + legend)

    rows = [("▓" * frame.horizontalSpan) for _ in range(frame.verticalSpan)]
    legend = [
        "legend:",
        (
            "  ▓   seam/interconnect  "
            f"[col={frame.horizontalStart}.."
            f"{frame.horizontalStart + frame.horizontalSpan}  "
            f"row={frame.verticalStart}.."
            f"{frame.verticalStart + frame.verticalSpan}]"
        ),
    ]
    return "\n".join(rows + [""] + legend)


def _interconnectWorldCanvasText_build(
    debugContext: NewEngineDebugContext,
    sourceGridCoord: GridCoord,
    destinationGridCoord: GridCoord,
) -> str:
    """Build one placed-interconnect crop from the composed world canvas."""

    interconnectResult = (
        debugContext.placedRoutingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=sourceGridCoord,
            destinationGridCoord=destinationGridCoord,
        )
    )
    if not result_isOkCheck(interconnectResult):
        return "interconnect world canvas\n  status: missing"

    worldCanvasLines = _worldCanvasLines_build(debugContext)
    if worldCanvasLines is None:
        return "interconnect world canvas\n  error: route realization failed"
    if not worldCanvasLines:
        return "interconnect world canvas\n  <empty>"

    frame = interconnectResult.value.routingZoneInterconnectFrame
    horizontalStart: int = frame.horizontalStart
    horizontalEnd: int = horizontalStart + frame.horizontalSpan
    verticalStart: int = frame.verticalStart
    verticalEnd: int = verticalStart + frame.verticalSpan

    croppedLines: list[str] = []
    rowIndex: int
    for rowIndex in range(verticalStart, verticalEnd):
        if rowIndex >= len(worldCanvasLines):
            break
        croppedLines.append(worldCanvasLines[rowIndex][horizontalStart:horizontalEnd])

    if not croppedLines:
        return "interconnect world canvas\n  <empty>"
    return "\n".join(croppedLines)


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
            seamRoutes = debugContext.interconnectRoutesForInterconnect_get(
                interconnect.routingZoneInterconnectId
            )
            seamText: str = (
                ", ".join(
                    (
                        f"{solvedRoute.sourceChipRef.chipId.functionName}->"
                        f"{solvedRoute.destinationChipRef.chipId.functionName}"
                    )
                    for solvedRoute in seamRoutes
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
        padded = [_pad(b, height, w) for b, w in zip(blocks, widths, strict=True)]
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
        for idx, (w, seam) in enumerate(zip(widths, seams, strict=True)):
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

    worldCanvasLines = _worldCanvasLines_build(debugContext)
    if worldCanvasLines is None:
        return "world canvas\n  error: route realization failed"
    if not worldCanvasLines:
        return "world canvas\n  <empty>"
    return "\n".join(worldCanvasLines)


def _worldCanvasLines_build(
    debugContext: NewEngineDebugContext,
) -> tuple[str, ...] | None:
    """Build authoritative world canvas lines, or ``None`` on failure."""

    chipInternalResult = realizedRouteSetResult_buildFromChipInternalSolvedRouteSet(
        debugContext.circuitDocument,
        debugContext.placedRoutingZoneGrid,
        debugContext.chipInternalSolvedRouteSet,
    )
    if not result_isOkCheck(chipInternalResult):
        return None

    zoneLocalResult = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
        debugContext.routingZoneLocalSolvedRouteSet
    )
    if not result_isOkCheck(zoneLocalResult):
        return None

    interconnectResult = realizedRouteSetResult_buildFromInterconnectSolvedRouteSet(
        debugContext.routingZoneInterconnectSolvedRouteSet
    )
    if not result_isOkCheck(interconnectResult):
        return None

    combinedRoutes = RealizedRouteSet(
        realizedRoutes=(
            chipInternalResult.value.realizedRoutes
            + zoneLocalResult.value.realizedRoutes
            + interconnectResult.value.realizedRoutes
        )
    )
    lines = worldCanvas_render(
        placedGrid=debugContext.placedRoutingZoneGrid,
        circuitDocument=debugContext.circuitDocument,
        realizedRouteSet=combinedRoutes,
    )
    return lines


def _zoneWorldCanvasText_build(
    debugContext: NewEngineDebugContext,
    routingZoneId: RoutingZoneId,
) -> str:
    """Build one placed-zone crop from the composed world canvas."""

    zoneResult = debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
        routingZoneId
    )
    if not result_isOkCheck(zoneResult):
        return f"zone world canvas {routingZoneId.id}\n  status: missing"

    worldCanvasLines = _worldCanvasLines_build(debugContext)
    if worldCanvasLines is None:
        return (
            f"zone world canvas {routingZoneId.id}\n"
            "  error: route realization failed"
        )
    if not worldCanvasLines:
        return f"zone world canvas {routingZoneId.id}\n  <empty>"

    zoneFrame = zoneResult.value.routingZoneFrame
    horizontalStart: int = zoneFrame.horizontalStart
    horizontalEnd: int = zoneFrame.horizontalEnd_calculate()
    verticalStart: int = zoneFrame.verticalStart
    verticalEnd: int = zoneFrame.verticalEnd_calculate()

    croppedLines: list[str] = []
    rowIndex: int
    for rowIndex in range(verticalStart, verticalEnd):
        if rowIndex >= len(worldCanvasLines):
            break
        croppedLines.append(worldCanvasLines[rowIndex][horizontalStart:horizontalEnd])

    if not croppedLines:
        return f"zone world canvas {routingZoneId.id}\n  <empty>"
    return "\n".join(croppedLines)


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


def _snippetFile_run(pathText: str, replLocals: dict[str, object]) -> None:
    """Execute one Python snippet file inside the live REPL namespace."""

    snippetPath = Path(pathText).expanduser()
    snippetSource = snippetPath.read_text(encoding="utf-8")
    exec(compile(snippetSource, str(snippetPath), "exec"), replLocals, replLocals)


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
    drawing blocks are intentionally colored differently so `*_text()` output
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
