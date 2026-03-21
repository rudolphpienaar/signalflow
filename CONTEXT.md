# Project Context: SignalFlow — Current Architectural Baseline

This file is agent-facing context. It is intentionally higher level than the
legacy implementation reference and lower level than the design contract.

The repo currently contains:

- a quarantined legacy engine under `src/signalflow/legacy/`
- a new-engine boundary with `--engine new|legacy`
- first-class `Chip`, `RoutingZone`, `RoutingZoneInterconnect`, and `RoutingZoneGrid` models
- typed `Result`/diagnostic handling for the new engine line

The critical March 2026 update is architectural:

- the intended world-level topology owner is now `RoutingZoneGrid`
- the intended atomic local routing unit is now `RoutingZone`
- the intended continuity mediator between neighboring zones is `RoutingZoneInterconnect`

Document precedence
-------------------

When there is tension between code and architecture direction, use these in order:

1. `PYTHON-STYLE-GUIDE.md`
2. `docs/re-architecture.adoc`
3. `docs/routingZone.txt`
4. `RE-ARCH-PLAN.md`
5. then current code

Current architectural reading
-----------------------------

1. Chips remain first-class objects.
   They own identity, semantics, ports, and chip-local declarations.

2. Chip-local routing must be solved first.
   Solved chip geometry is an input to later zone placement.

3. `RoutingZone` owns chip placement, not chip identity.
   No chip may appear in more than one zone.

4. `RoutingZoneInterconnect` connects exactly two neighboring zones.
   It mediates continuity from one zone into the next.

5. `RoutingZoneGrid` is the world topology.
   It places zones in a 2D grid, places interconnects between neighbors,
   chooses macro route paths, and reserves interconnect capacity classes for
   long-haul traffic.

6. The current simple world regime is `1 x (callingDepth - 1)` under `WestToEast`.

7. `RoutingZone` is the world-local owner, not the universal owner of every
   routing problem.
   Chip-internal routing should converge toward the same routing-substrate
   family, but through a distinct chip-local owner over that substrate rather
   than by overloading world-zone identity.

Tiered solve order
------------------

1. Solve chip-local routing first (`chipDrawLines_build` fixes chip geometry).
2. Derive each `RoutingZone`'s natural frame from its chips' geometries.
3. Normalize the grid: each column takes the widest zone's width; each row
   takes the tallest zone's height.  Any zone that grows must re-solve its
   chip placement positions, zone-local routing subregion geometry, and the
   seam geometry of every touching `RoutingZoneInterconnect`.  This step
   repeats until no zone grows (in practice one pass suffices for regular grids).
4. Let `RoutingZoneGrid` detect long-haul traffic and reserve interconnect
   capacity classes.
5. Let each `RoutingZone` batch-solve its local connectivity.
6. Let each `RoutingZoneInterconnect` solve local seam continuity.
7. Let `RoutingZoneGrid` finalize longer cross-grid connections.

Current gap: step 2 uses a provisional terminal-count formula instead of real
chip geometry.  Step 3 (normalization) runs but the cascade re-solve of zone
routing and seam geometry after a zone grows is not yet implemented.

Terminal synthesis rule (canonical)
-------------------------------------

`input_ports` names the west wall; `output_ports` names the east wall.
Both `signal` and `return` within a port declaration stay on the same wall as
the port — they do not cross to the opposite wall.

```
input_ports  signal → WEST
input_ports  return → WEST
output_ports signal → EAST
output_ports return → EAST
```

This is consistent with the legacy `chip_geometry` model (`leftNames` =
all `input_ports` labels, `rightNames` = all `output_ports` labels).
The same label appearing in multiple roles on the same wall deduplicates to one
terminal.  The chip-internal solver (`routing.chip_solver`) follows the same
rule for preferred-side inference.

Current repo state
------------------

- The code now contains the first canonical zone-grid model layer.
- The `new` engine path now builds and renders a planning/debug projection, but
  that projection is not the target presentation renderer.
- The CLI default is currently `--engine new`, with `legacy` still selectable.
- The debugger REPL is now the primary render-design instrument.
- REPL ergonomics are stable: tab completion, persistent history, prompt fixed.
- `chip.draw()` now implements the correct legacy visual grammar with accurate
  west/east terminal stubs (terminal synthesis bug fixed March 2026).
- Cardinal side vocabulary is now shared between chip terminals and zone
  regions as a small extracted routing-substrate primitive.
- Chip-internal directional orientation tokens now sit on a shared
  directional-orientation primitive rather than a chip-only enum.
- chip-internal solved routes and chip-local geometry now use a concrete
  `ChipLocalRoutingOwner` instead of pretending to be owned by a world
  `RoutingZoneId` or hanging directly off a bare chip id.
- Attach-side inference now sits on a shared helper layer: chip-local endpoint
  side preference and zone channel-facing terminal-side resolution use the same
  substrate vocabulary.
- Chip-local terminal offsets and world attach points now share one
  owner-qualified `ChipTerminalRef` identity record.
- Chip-internal routing directives are parsed, classified, solved, and now
  realized into the authoritative world-canvas route compositor.
- The full test suite most recently passed at `513` tests.

Shared routing substrate direction (March 2026)
-----------------------------------------------

The project is converging on one routing-substrate family with two owners:

- world-local owner: `RoutingZone`
- chip-local owner: a future chip-internal routing substrate owner

The shared substrate family should own:

- explicit region frames
- side-qualified travel bands
- fan-in / fan-out transition regions
- lane ownership
- attach-point ownership
- orthogonal route solving over named surfaces

This is not an inheritance-first statement. The important split is between the
shared substrate machinery and the owners above it. A world zone owns chip
placement and seam-facing geometry. A chip-local owner would own terminals and
explicit `internal_wiring` continuity inside one chip body.

Seam routing status (March 2026)
--------------------------------

**Current implementation**: seams now materialize **per directed wire**. A
fully materialized seam corridor preserves distinct lane identity across:

- source-side `INTER_ROUTING_FAN_IN_OUT`
- source-side `INTER_ROUTING_LONGITUDE`
- `RoutingZoneInterconnectFrame`
- destination-side `INTER_ROUTING_LONGITUDE`
- destination-side `INTER_ROUTING_FAN_IN_OUT`

The fan regions are not pure capacity strips. They also own the breakout / tee
/ elbow structure needed to leave or enter chip terminal neighborhoods cleanly.
That means fan width must include both directed-wire lane capacity and the
fixed structural overhead needed to realize those turns.

Zone horizontal span formula (WTE zones):

```
zoneHorizontalSpan = W + E + K + 2*F + 2*L + 4
```

where W = west terminal width, E = east terminal width, K = crossbar width, F =
inter-fan span, and L = seam-side inter-lane span.

Column layout within a zone (col offsets from zone horizontalStart):

```
col 0                   INTER_LONG/WEST      hSpan=L
col L                   INTER_FAN/WEST       hSpan=F
col L+F                 CHIP_TERM/WEST       hSpan=W
col L+F+W               INTRA_FAN/WEST       hSpan=1
col L+F+W+1             INTRA_LONG/WEST      hSpan=1
col L+F+W+2             crossbar             hSpan=K
col L+F+W+2+K           INTRA_LONG/EAST      hSpan=1
col L+F+W+3+K           INTRA_FAN/EAST       hSpan=1
col L+F+W+4+K           CHIP_TERM/EAST       hSpan=E
col L+F+W+4+K+E         INTER_FAN/EAST       hSpan=F
col L+2F+W+4+K+E        INTER_LONG/EAST      hSpan=L
```

Here `L` is the directed-wire inter-lane span and `F` is the seam fan span.
The current policy is:

- `L = 2 * directed seam-crossing call count`, plus any same-zone perimeter
  backedge demand that uses the same `INTER` capacity family
- `F = L + structural fan overhead`
- seam lane allocation is per interconnect demand set, not per source chip's
  local `childCallIndex`; converging sources into one destination therefore get
  distinct seam lanes and distinct destination attach rows when the destination
  declares multiple input ports

`CHIP_TERMINAL` is now anchored to the actual chip box walls rather than the
full rendered chip-body width. Placement sizes west/east terminal bands from
chip box width, while chip draw lines are blitted relative to that box anchor
so terminal stubs can extend into adjacent routing regions. Module boxes remain
render overlays derived from chip box extents only; they are not geometry
owners. The world compositor order is now:

- chip bodies
- module boxes
- route wires

This keeps module borders intact while still allowing route piercing glyphs to
resolve against the final box walls.

Current route-class reading
---------------------------

- zone-local forward transverse routes use `INTRA_*`
- same-zone backedges use the outer `INTER_*` perimeter
- inter-zone seam crossings use `INTER_*` plus `RoutingZoneInterconnect`

This means same-zone perimeter backedges and adjacent-zone seam crossings now
compete for the same `INTER` channel budget, and placement must size those
regions from both demand sources.

Current non-goal / gap
----------------------

Chip-internal routes now enter the authoritative world-canvas compositor, but
their realization is still a first concrete owner-backed step rather than the
final shared-substrate endpoint geometry. In particular, west/east chip-local
internal routes are realized today, while north/south chip-local terminal
realization remains deferred.

Planned migration order for the shared-substrate direction:

1. Keep `RoutingZone` world-scoped.
2. Extract shared routing-substrate concepts under both worlds.
3. Introduce a chip-local owner over that same substrate family.
4. Realize chip-internal solved routes through the same style of realized-route
   pipeline used by zone-local and seam routes.

**REPL inspection command** for zone region layout:

```python
from signalflow.engine.debug import newEngineDebugContextResult_buildFromDocumentDict
from signalflow.models.diagnostics import diagnosticStack
import yaml
with open('examples/branch-converging.yaml') as f:
    doc = yaml.safe_load(f)
diagnosticStack.stack_clear()
result = newEngineDebugContextResult_buildFromDocumentDict(doc)
ctx = result.value
grid = ctx.placedRoutingZoneGrid
zone1 = grid.routingZoneSet.routingZones[0]
for region in zone1.routingZoneRegionSet.routingZoneRegions:
    rid = region.routingZoneRegionId
    fr = region.routingZoneRegionFrame
    print(f'{rid.routingZoneRegionKind.value:40s} {str(rid.routingZoneRegionSide):30s} '
          f'hStart={fr.horizontalStart} hSpan={fr.horizontalSpan} '
          f'vStart={fr.verticalStart} vSpan={fr.verticalSpan}')
```

Practical instruction for agents
--------------------------------

- Do not reintroduce lane-first `ChipLayout` or layout-input code as if it were
  the canonical architecture.
- Build from the `RoutingZoneGrid` / `RoutingZone` / `RoutingZoneInterconnect`
  ontology outward.
- Any substantial new topology work should be documented first in `docs/re-architecture.adoc`,
  `docs/routingZone.txt`, and `RE-ARCH-PLAN.md` before code is written.
- When in doubt, preserve the hard legacy/new boundary already established in the repo.
- The terminal synthesis rule above is now correct and locked by tests — do not
  reintroduce the crossing model (`input return → EAST`, `output return → WEST`).
- The current immediate work (as of March 2026):
  1. Seam bus-collapse fix is complete — 513 tests pass.
  2. The next open item is Rule 1B: `_zoneMetrics_build` uses a provisional
     terminal-count formula; needs chip-geometry-driven zone sizing + cascade
     re-solve (see CONTEXT.md "Tiered solve order" step 3).
  3. REPL `workflows` namespace (`workflows.chip_geometry_push()`,
     `workflows.zones_normalize()`) is not yet implemented.
- Do not keep polishing the top-level renderer speculatively. Treat the REPL
  as the primary render-design surface.

Recommended handoff docs
------------------------

If a new agent needs to pick up the current work, start with:

1. `docs/debugger.adoc`
2. `docs/yamlToCircuits.adoc`
3. `docs/re-architecture.adoc`
4. `RE-ARCH-PLAN.md`
5. `docs/chip.adoc`
6. `docs/routingZone.adoc`
7. `docs/routingZoneGrid.adoc`
8. `docs/wire-model.md`
9. `docs/architecture.adoc`
10. `examples/one.txt`
11. `examples/receiver.txt`
