# SignalFlow Execution Plan

**Date:** April 2026
**Branch:** `worldscale-extra-routing`
**Version:** `5.9.27`

## Plan Structure

Two concurrent arcs:

- **Arc R (Reverse/Recursive Wiring)** — immediate, unblocking. Phases R0–R3.
- **Arc G (Symbolic Geometry Topology)** — longer-term semantic target. Phases G0–G7.

Arc R must land before Arc G resumes. The two arcs do not conflict — they address
different layers. Arc R completes the routing execution path. Arc G makes the
geometry semantic layer explicit. They can be interleaved once R0 is done.

---

## Arc R: Reverse / Recursive Wiring

### Phase R0: Extra Ring Realization (IMMEDIATE)

**Objective**

Extend `algebraicRouteRealization_buildFromPath` in `src/signalflow/board/realizer.py`
to realize extra ring paths onto board geometry.

**Why it is blocking**

The extra ring geometry exists. The path topologies exist. The kernel solver dispatches
backedge obligations via `WTE_EXTRA_CONTEXT`. But the realizer only handles two intra
shapes. All extra paths produce empty `routePoints`, making reverse routing invisible
in any rendered output.

**Four cases to add**

1. `Wfe → We → Ne → Ee → Efe` — extra forward (WTE_EXTRA_TOPARENT)
2. `Efe → Ee → Se → We → Wfe` — extra return (WTE_EXTRA_FROMPARENT)
3. `Efe → Ee → Ne → Em → Efi` — east medial U-turn (WTE_MEDIAL_EAST_FORWARD)
4. `Wfi → Wm → Ne → We → Wfe` — west medial U-turn (WTE_MEDIAL_WEST_FORWARD)

Use `sfN.*.region_key` to resolve frame names; never hardcode key strings.

**Acceptance**

- Extra ring paths produce non-empty `routePoints`
- 137 existing tests still pass
- At least one test verifies a non-empty extra ring realization

### Phase R1: Collision Check Extension

**Objective**

Extend `_geometryPressureScore_calculate` and the occupancy/collision framework to
account for extra ring routes (We/Ee/Ne/Se columns and rows are separate from intra lanes).

### Phase R2: Recursive Wiring End-to-End Demo

**Objective**

Demonstrate a child→parent call routed through the extra ring, fully materialized and
rendered without collisions.

### Phase R3: Medial U-Turn Demo

**Objective**

Demonstrate an Et→Et same-side call routed through the east medial U-turn (Em pillar),
fully materialized.

---

## Arc G: Symbolic Geometry Topology

The G-arc is valid and remains the long-term semantic target. See phases G0–G7 below.
Do not begin G1+ until R0 is complete.

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

## Phase G0: Freeze Current Baseline

**Objective**

Treat the current board-geometry, coupling, and displacement behavior as the
migration baseline.

**Acceptance**

- current symbolic tests stay green
- current geometry snippets stay green
- no architectural rewrite begins without a stable baseline

## Phase G1: Define Symbolic Topology Schema

**Objective**

Introduce a first-class symbolic geometry schema for one board/zone.

**What it must express**

- region families
- relative order
- neighborhood / adjacency
- family membership
- continuity group membership

**Key point**

This is not yet concrete frame construction. It is the semantic geometry
topology.

**Acceptance**

- one board can answer questions like:
  - what is west of `Ee`
  - what belongs to the east extra family
  - what must remain connected if `Ee` moves

## Phase G2: Make Symbolic Topology First-Class In Runtime Objects

**Objective**

A `Board` / `BoardGeometry` should expose symbolic topology directly.

**What to do**

- add topology-bearing runtime objects
- expose inspect-facing access to symbolic geometry
- stop requiring consumers to infer semantic order from raw frame coordinates

**Acceptance**

- runtime objects can provide symbolic neighborhood and family queries directly

## Phase G3: Move Coupling Doctrine Onto Symbolic Topology

**Objective**

Bind coupling rules to symbolic geometry rather than only to concrete region ids.

**What to do**

- keep current operators:
  - `~=>`
  - `~->`
  - `[]=`
- add continuity operator
- define first continuity family for the extra ring

**Acceptance**

- `chip_terminal` coupling family and `Ee` displacement family are both
  expressible as symbolic rule banks

## Phase G4: Build Local Geometry Interpreter

**Objective**

Interpret one local mutation against symbolic topology and coupling doctrine.

**Interpreter responsibilities**

1. apply direct mutation
2. fire direct coupling rules
3. validate enclosure constraints
4. validate continuity constraints
5. emit repair actions
6. repeat until stable or impossible

**Acceptance**

- interpreter exists for one-zone / local-family work
- no need for world propagation yet

## Phase G5: Solve The First Real Continuity Case

**Objective**

Handle the `Ee` displacement case doctrinally.

**Initial case**

- move `Ee` only
- blank space opens relative to `Efe`
- extra ring continuity must still be repaired

**Expected result**

- the extra ring remains connected after the move
- continuity repair is explainable from symbolic rules

**Acceptance**

- snippet and test evidence show continuity preserved for the first scoped case

## Phase G6: Broaden Family Coverage

**Objective**

Expand beyond `Ee` into the main first-order geometry families.

**Likely order**

1. extra ring continuity family
2. chip-terminal coupling family
3. intra clearance / exposure family

**Acceptance**

- no family-specific special case is added without first living inside the
  symbolic schema + coupling + interpreter structure

## Phase G7: Compile Metric Geometry From Symbolic Topology

**Objective**

Make concrete frame construction a realization of the symbolic topology rather
than the only geometry definition.

**What to do**

- gradually move hardcoded builder arithmetic behind symbolic topology
- preserve existing rendered output contract while doing so

**Acceptance**

- symbolic topology is the semantic source
- frame construction is a realization step

## Verification Surface

These must remain green throughout:

- `python -m pytest tests_symbolic -q`
- `snippets/algebraic/zone_geometry.py -- --zone 1,1`
- `snippets/algebraic/hub_kernel_solver.py -- --zone 1,1`
- `snippets/algebraic/hub_internal_wiring.py`
- `snippets/algebraic/hub_internal_geometry.py`

Add and keep green:

- `tests_symbolic/test_geometry_displacement.py`
- `snippets/algebraic/zone_geometry_ee_displace.py`
- geometry-topology / continuity snippets as they are introduced

## Current Immediate Next Step

Do **not** jump straight to a large interpreter implementation.

Do this first:

1. define the symbolic topology schema for one board
2. make `Ee` neighborhood and ring-family membership queryable from that schema
3. then add the first continuity operator and its scoped interpreter pass
