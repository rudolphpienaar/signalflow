# SignalFlow Execution Plan

**Date:** April 2026
**Branch:** `worldscale-extra-routing`
**Version:** `5.9.33`

## Plan Structure

Two concurrent arcs:

- **Arc R (Reverse/Recursive Wiring)** — immediate, unblocking. Phases R0–R3.
- **Arc G (Symbolic Geometry Topology)** — longer-term semantic target. Phases G0–G7.

Arc R must land before Arc G resumes. The two arcs do not conflict; they address different layers. Arc R completes the routing execution path. Arc G makes the geometry semantic layer explicit. They can be interleaved once the reverse-routing fixtures and reporting surfaces are stable.

---

## Arc R: Reverse / Recursive Wiring

### Phase R0: Extra Ring Realization (COMPLETED)

**Objective**

Extend `algebraicRouteRealization_buildFromPath` in
`src/signalflow/board/realizer.py` to realize outer-ring paths onto board
geometry.

**Why it was blocking**

The extra ring geometry existed and the path topologies already existed, but reverse routing remained invisible in rendered output until those paths were realized onto board-owned geometry.

**Four cases added**

1. `Wfe → We → Ne → Ee → Efe` — outer eastbound arc (`WTE_OUTER_EASTBOUND_ARC`)
2. `Efe → Ee → Se → We → Wfe` — outer westbound arc (`WTE_OUTER_WESTBOUND_ARC`)
3. `Efe → Ee → Ne → Em → Efi` — east-side U-turn (`WTE_OUTER_EASTSIDE_UTURN`)
4. `Wfi → Wm → Ne → We → Wfe` — west-side U-turn (`WTE_OUTER_WESTSIDE_UTURN`)

Use `sfN.*.region_key` to resolve frame names; never hardcode key strings.

**Acceptance**

- Extra ring paths produce non-empty `routePoints`
- 145 existing tests still pass
- At least one test verifies a non-empty extra ring realization

### Phase R1: Collision Check Extension (MOSTLY COMPLETE)

**Objective**

Extend the occupancy/collision framework to account for extra ring routes. This is mostly complete in the live centroid-spread path, which now uses realized merged-cell congestion and paired Ni/Si spreading to completion. Remaining work is to align the formal collision reporting surface with that stricter metric.

### Phase R2: Recursive Wiring End-to-End Demo (CURRENT)

**Objective**

Demonstrate child→parent and same-side recursive calls through full fixtures, fully materialized and rendered with the expected outer topology labels and clean reporting.

### Phase R3: Medial U-Turn Demo

**Objective**

Demonstrate an Et→Et same-side call routed through the east medial U-turn (Em pillar),
fully materialized.

---

## Arc G: Symbolic Geometry Topology

The G-arc is valid and remains the long-term semantic target. See phases G0–G7 below.
Do not begin G1+ until R1 is complete enough to keep reverse-routing demos honest.

---

## Arc G Current State

The board-era geometry slice is now real enough to build on:

- `GeometryZone` is the canonical stored geometry unit.
- board geometry now lives under `src/signalflow/board/geometry/`.
- symbolic geometry expression support exists.
- first-order coupling doctrine exists.
- local displacement and chip-terminal coupling tests exist and are green.

The next architectural problem in Arc G is:

- make symbolic geometry topology the top-layer geometry definition

## Actual Target Model

The intended geometry stack is:

1. **symbolic topology schema**
   - the zone says what regions exist
   - in what order
   - what touches what
   - what continuity families exist

2. **coupling and constraint doctrine**
   - `~=>` drag
   - `~->` displace
   - `[]=` contain
   - future continuity operator

3. **interpreter**
   - takes one local mutation
   - finds triggered rules
   - applies secondary reactions
   - resolves until stable or contradiction

4. **metric realization**
   - concrete frames
   - chip placements
   - module boundaries
   - exact terminals

The symbolic topology must become the top layer. Concrete frames remain the
executed geometry, but they should no longer be the only place where order and
adjacency are knowable.

## Why This Is The Next Plan

Today, too much semantic geometry is still implicit in builder arithmetic:

- which family is east of which
- which families form a continuous ring
- which areas are coupled
- which local moves should open space versus drag neighbors

That implicit arithmetic makes downstream reasoning harder than it should be.

The symbolic topology plan is meant to make:

- order explicit
- adjacency explicit
- continuity explicit
- coupling attach to named symbolic regions instead of only to frame ids

## Goal Definition

This plan is complete when all of the following are true:

1. One zone can expose a first-class symbolic topology schema.
2. Coupling doctrine is expressed primarily against symbolic topology, not only
   against concrete frame ids.
3. A local geometry mutation can be interpreted through symbolic rules rather
   than by ad hoc frame surgery.
4. At least the `Ee` displacement continuity case is resolved by doctrine and
   interpreter logic.
5. Current green tests and truth-surface snippets remain green throughout the
   migration.
