"""REPL help and manual content for debug surfaces."""

from __future__ import annotations


def _lines(text: str) -> tuple[str, ...]:
    return tuple(text.strip("\n").splitlines())


REPL_AVAILABLE_NAMES_LINES: tuple[str, ...] = _lines(
    """
  document    circuit     config      grid        assignment
  chips       zones       calls       routes
  world       obligations diagnostics workflows   ctx
  root_chip   root_placement prompt
  ls(obj)     tree(obj)   man(topic)  sfhelp()  load(path)
  solution_realize(board, solution)
  solution.board_materialize(board)
"""
)


REPL_HELPER_LINES: tuple[str, ...] = _lines(
    """
  chips.names_get()
  chips.all_sprint()
  chip = chips.chip_get('App.ts', 'main()')
  chip = chips['App.ts:main()']
  chip.title_get()
  chip.size_get()
  chip.terminals_get()
  chip.terminals_getLocalPositions('west')
  chip.terminals_getWorldPositions('west')
  chip.worldFrame_get()
  chip.draw()
  chip.children_get()
  chip.child_get(0)
  zones.all_sprint()
  zone = zones.zone_get(1, 1)
  ki = zone.kernel_get('intra')
  kw = ki.wiring_get()
  kw.list_sprint()
  board = ki.board_get()
  solver = ki.solver_get(board)
  solution = solver.solution_get()
  realized = solution_realize(board, solution)
  materialized.geometry_sprint()
  zone.world_sprint()
  zone.placements_get()
  zone.routes_get()
  world.gridCanvas_sprint()        # full chip-body + route-wire canvas
  world.gridStyle_sprint('zones')
  routes.zoneLocal_get()
  routes.gridLongHaul_get()
  calls.outgoing_get('App.ts', 'main()')
  prompt.title.len_truncate(32)
  prompt.title.full()
  workflows.inspectOrder_print()
  workflows.status_print()
  ls(chips)
  ls(chip)
  tree(document)
  load('snippets/hub_walk.py')
  sfhelp()
  man('chips')
"""
)


MANUAL_BY_TOPIC: dict[str, tuple[str, ...]] = {
    "general": _lines(
        """
SignalFlow debug REPL — topics

  chips         chip geometry, terminals, drawing
  zones         placed routing zones and local routes
  world         world grid topology
  calls         circuit call edges
  routes        obligations and solved route layers
  workflows     geometry cascade and solver operations
  document      source document inspection
  circuit       validated circuit graph
  config        engine configuration
  grid          unplaced topology grid

  man()         with no argument shows this list
  man('chips')  full narrative for one topic

explore any live object:
  ls(chips)     list chips view surface
  ls(chip)      list one chip handle surface
  tree(document) recursive subtree preview
"""
    ),
    "chips": _lines(
        """
chips — chip geometry and terminal inspection

Chips are first-class objects in SignalFlow. A chip owns its identity,
declared port surfaces (input_ports, output_ports), synthesized terminals,
and chip-local internal wiring declarations. Chips do NOT own world placement.

chip geometry is upstream layout truth: the rendered chip body
(chip.schematic_sprint()) determines the row/column budget that any
containing RoutingZone must reserve.
If a chip gains a port row, its zone frame must grow to accommodate it.

chips view  [chips]
# The chips view is the entry point for all chip queries.
# Select one chip, then stay on the handle for detailed inspection.

  chips.all_get()                          # tuple[BoardChip]
  chips.count_get()                        # int
  chips.ids_get()                          # tuple[ChipId]
  chips.names_get()                        # tuple[str]  'module:func' titles
  chips.root_get()                         # BoardChip for root chip
  chips.chip_get(moduleName, functionName) # BoardChip
  chips.chipByTitle_get('App.ts:main()')  # BoardChip
  chips['App.ts:main()']                   # BoardChip (index syntax)
  chips.title_get(moduleName, functionName)
  chips.size_get(moduleName, functionName)      # (widthCols, heightRows)
  chips.terminals_get(moduleName, functionName) # {'north':N,'south':S,...}
  chips.location_get(moduleName, functionName)
  chips.routes_get(moduleName, functionName)
  chips.schematic_sprint(moduleName, functionName) # canonical chip box drawing
  chips.summary_sprint(moduleName, functionName)   # full debug summary text
  chips.all_sprint()                              # all chip summaries

chip handle  [chip = chips.chip_get(...)]
# A chip handle is the ergonomic per-chip inspection surface.
# It avoids passing moduleName/functionName into every call.

  chip.title_get()        # 'module:func' string
  chip.size_get()         # derived size from schematic_sprint()
  chip.dimensions_get()   # {'widthColumns': N, 'heightRows': M}
  chip.width_get()        # int
  chip.height_get()       # int
  chip.terminals_get()    # {'north':N, 'south':S, 'east':E, 'west':W}
  chip.placement_get()    # primary ChipPlacement result
  chip.location_get()     # primary location record dict
  chip.locations_get()    # all location records
  chip.children_get()     # tuple[BoardChip] — outgoing call targets
  chip.child_get(index)   # one child by call index
  chip.routes_get()       # solved chip-internal routes
  chip.internalBoard_get() # board-compatible chip-local harmonizer handle
  chip.schematic_sprint()   # canonical chip box, upstream layout truth
  chip.summary_sprint()     # full debug summary
  chip.raw_get()          # raw Result[Chip]

terminal synthesis rule
  input_ports  signal -> WEST terminal
  input_ports  return -> WEST terminal
  output_ports signal -> EAST terminal
  output_ports return -> EAST terminal (inward arrow in schematic_sprint())

  Same name on same wall deduplicates to one terminal.
  chip.schematic_sprint() uses T-junction glyphs where wires meet the wall.
"""
    ),
    "zones": _lines(
        """
zones — placed routing zones and local route inspection

A RoutingZone is the atomic local routing block. It owns chip placement
(not chip identity), the zone's outer frame, and all explicit subregion
geometry (CHIP_TERMINAL, INTRA_ROUTING_*, INTER_ROUTING_* bands).

Zone geometry is DERIVED from chip geometry — a zone's frame is the
smallest rectangle that can contain all its placed chips plus routing
subregions. If chips grow, the zone must grow with them.

No chip may appear in more than one zone.

zones view  [zones]

  zones.all_get()                  # tuple[ZoneHandle]
  zones.count_get()                # int
  zones.ids_get()                  # tuple[RoutingZoneId]
  zones.zone_get(columnIndex, rowIndex)       # ZoneHandle
  zones.zoneForChip_get(moduleName, functionName)  # owning zone handle
  zones.placements_get(columnIndex, rowIndex) # chip placements in zone
  zones.routes_get(columnIndex, rowIndex)     # zone-local solved routes
  zones.summary_sprint(columnIndex, rowIndex)   # full debug summary
  zones.routes_sprint(columnIndex, rowIndex)    # route geometry text
  zones.schematic_sprint(columnIndex, rowIndex) # zone schematic text
  zones.all_sprint()                            # all zone summaries

zone handle  [zone = zones.zone_get(1, 1)]

  zone.id_get()           # RoutingZoneId
  zone.sense_get()        # 'west_to_east' | 'north_to_south'
  zone.placements_get()   # chip placements
  zone.routes_get()       # solved zone-local routes
  zone.kernel_get('intra') # one routing kernel inside the zone
  zone.kernels_get()      # {'north':..., 'south':..., ...}
  zone.world_sprint()       # zone crop from world.gridCanvas_sprint()
  zone.summary_sprint()     # full debug summary
  zone.routes_sprint()      # route geometry
  zone.schematic_sprint()   # zone schematic text
  zone.raw_get()          # raw Result[RoutingZone]

kernel handle  [kernel = zone.kernel_get('intra')]
  kernel.side_get()       # 'intra' | 'west' | 'east' | 'north' | 'south'
  kernel.areas_get()      # region set owned by this kernel
  kernel.schematic_sprint() # cropped kernel substrate view
  kernel.routes_sprint()    # realized route crop for this kernel
  kernel.wiring_get()     # KernelWiringHandle
  kernel.board_get()      # KernelBoardHandle
  kernel.solver_get(board) # BoardSolver

wiring handle  [wiring = kernel.wiring_get()]
  wiring.all_get()        # tuple[KernelWire]
  wiring.list_sprint()      # one directed wire per line
  wiring.algebraic_sprint(endpointText) # filtered symbolic view

solver handle  [solver = kernel.solver_get(board)]
  solver.solution_get()   # BoardSolution

solution handle  [solution = solver.solution_get()]
  solution.list_sprint()
  solution.algebraic_sprint(endpointText)

materialize
  realized = solution_realize(board, solution)
  materialized.summary_sprint()
  materialized.wiring_sprint()
  materialized.geometry_sprint()

wiring notation
  module.func.signal:module.func.signal
  forward example: App.ts.main().query:Worker.ts.run().query
  return  example: Worker.ts.run().result:App.ts.main().result

current limitation
  Zone frames are currently sized from a terminal-count formula,
  NOT from real chip render geometry. Use workflows.status_print()
  to see the current state and what the cascade re-solve will fix.
"""
    ),
    "world": _lines(
        """
world — world grid topology

RoutingZoneGrid is the world topology. It places zones in a 2D grid and
owns macro path planning for wires that cross more than one zone.

The overlap model treats zone-local geometry as authoritative. Seam or
interconnect objects may still exist as compatibility/topology artifacts,
but they are not part of the target substrate model.

The world grid is regular: every zone in a column shares the same width,
every zone in a row shares the same height. Zone sizes are normalized
to the largest zone per row/column.

world view  [world]

  world.gridSize_get()                   # GridCoord(columns, rows)
  world.gridCanvas_sprint()                # chip bodies + route wires
  world.gridSchematic_sprint()             # zone schematic (names only)
  world.gridStyle_sprint('zones')          # named text view
  world.gridStyle_sprint('placements')
  world.gridStyle_sprint('routes')

canvas vs schematic
  world.gridCanvas_sprint()  — composite: real chip bodies at terminal
    region positions with route wire glyphs overlaid.  This is the
    authoritative visual output of the new engine.
  world.gridSchematic_sprint() — schematic: chip names in abstract zone
    boxes.  Useful for debugging zone topology without chip geometry.

current simple regime
  west_to_east with no explicit grid -> 1 x ceil(callingDepth/2) world
  zones consumed in serpentine row-major order
"""
    ),
    "calls": _lines(
        """
calls — circuit call edges

The circuit graph models chips as nodes and calls as directed edges.
Repeated references to the same (module, func) pair resolve to ONE
canonical chip with multiple incoming call edges — not cloned nodes.

calls view  [calls]

  calls.all_get()                         # all canonical call edges
  calls.count_get()                       # int
  calls.outgoing_get(moduleName, functionName)  # outgoing edges for chip
  calls.incoming_get(moduleName, functionName)  # incoming edges for chip
"""
    ),
    "routes": _lines(
        """
routes — obligations and solved route layers

Routes are solved in a tiered pipeline. Each tier builds on the previous.
The route view spans both the obligation (what needs to happen) and the
solved (what has been realized) layers so you can compare them.

Tier 1 — chip-internal:  routes inside one chip's body
Tier 2 — zone-local:     routes between chips in the same zone
Tier 3 — grid long-haul: routes that cross multiple zones

routes view  [routes]

  routes.callObligations_get()             # all call-route obligations
  routes.chipInternalObligations_get()     # chip-internal obligations
  routes.chipInternal_get()                # solved chip-internal routes
  routes.zoneLocal_get()                   # solved zone-local routes
  routes.gridLongHaul_get()                # solved grid long-haul routes
  routes.forChip_get(moduleName, functionName)          # chip-internal routes
  routes.zoneLocalForChip_get(moduleName, functionName) # zone-local for chip
  routes.gridLongHaulForChip_get(moduleName, functionName)
  routes.forZone_get(columnIndex, rowIndex)  # zone-local routes in one zone
"""
    ),
    "workflows": _lines(
        """
workflows — geometry cascade and solver operations

Workflows are multi-step operations that cross layer boundaries.
The canonical cascade is:

  chip geometry (fixed by chipDrawLines_build)
      |
  zone natural frame (derived from chips)
      |
  grid normalization (max per row/column)
      |  if any zone grew:
  re-solve chip placement + zone routing
      |  until stable
  world geometry is finalized

workflows view  [workflows]

  workflows.status_print()               # current geometry derivation state
  workflows.inspectOrder_print()         # canonical chip->zone->world order
  workflows.chipGeometryPush_run()       # [stub] re-derive zones from chips
  workflows.zonesNormalize_run()         # [stub] normalization cascade
  workflows.zoneRecalculate_run(col,row) # [stub] recalculate a zone

typical REPL workflow (current — manual inspection):
  1. chips.all_sprint()               # verify chip geometry is correct
  2. chip = chips.chip_get(...)     # pick one chip
  3. chip.schematic_sprint()        # inspect canonical drawing
  4. zones.all_sprint()              # inspect current zone frames
  5. zone = zones.zone_get(1, 1)  # pick one zone
  6. zone.placements_get()         # see what chips are placed where
  7. world.gridStyle_sprint('zones') # see full world grid

when chipGeometryPush_run() is implemented:
  workflows.chipGeometryPush_run()   # push chip geometry into zone frames
  workflows.zonesNormalize_run()     # normalize + cascade re-solve
  workflows.status_print()           # verify all zones are chip-driven
  world.gridStyle_sprint('zones')    # final world geometry
"""
    ),
}
