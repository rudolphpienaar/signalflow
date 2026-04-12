# SignalFlow Execution Plan: Symbolic Geometry Topology

**Date:** April 2026  
**Branch:** `worldscale-extra-routing`  
**Version:** `5.9.19`

## Current State

The board-era geometry slice is now real enough to build on:

- `GeometryZone` is the canonical stored geometry unit.
- board geometry now lives under `src/signalflow/board/geometry/`.
- symbolic geometry expression support exists.
- first-order coupling doctrine exists.
- local displacement and chip-terminal coupling tests exist and are green.

This means the next architectural problem is no longer only:

- remove more legacy kernel/interconnect dependency

It is now:

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
