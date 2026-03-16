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

Tiered solve order
------------------

1. Solve chip-local routing first.
2. Let `RoutingZoneGrid` detect long-haul traffic and reserve interconnect capacity classes.
3. Let each `RoutingZone` batch-solve its local connectivity.
4. Let each `RoutingZoneInterconnect` solve local seam continuity.
5. Let `RoutingZoneGrid` finalize longer cross-grid connections.

Current repo state
------------------

- The code now contains the first canonical zone-grid model layer.
- The `new` engine path currently reports pending zone-grid runtime status rather
  than pretending a removed prototype is still active.
- The CLI default is currently `--engine new`, with `legacy` still selectable.
- The full test suite most recently passed at `275` tests.

Practical instruction for agents
--------------------------------

- Do not reintroduce lane-first `ChipLayout` or layout-input code as if it were
  the canonical architecture.
- Build from the `RoutingZoneGrid` / `RoutingZone` / `RoutingZoneInterconnect`
  ontology outward.
- Any substantial new topology work should be documented first in `docs/re-architecture.adoc`,
  `docs/routingZone.txt`, and `RE-ARCH-PLAN.md` before code is written.
- When in doubt, preserve the hard legacy/new boundary already established in the repo.
