# SignalFlow Execution Plan: Authoritative Board Substrate

**Date:** April 2026  
**Branch:** `worldscale-extra-routing`  
**Version:** `5.9.19`  
**Head at plan update:** `198035d`

## Current State

The previous major rescue/refactor is complete enough to treat as baseline:

- `notation/` is canonical for symbolic geometry naming and path algebra.
- `WiringSolution` consolidation is complete through the active board runtime.
- `engine/debug.py` is gone; `engine/inspect/` is the live inspection facade.
- the duplicate debug-side runtime is gone.
- board-local solve/materialize now runs through:
  - `BoardKernel`
  - `Board`
  - `BoardSolver`
  - `BoardSolution`
  - `BoardMaterializedSolution`

Recent corrective work also established:

- return-shell realization now uses the same lane indices that the algebraic
  path text reports.
- return-shell south-latitude and west-longitude packing now runs from the far
  edge (`REVERSE`) rather than the near edge.
- fan span policy defaults are currently `4` for intra and extra west/east fan
  bands in `config/board_defaults.py`.

## What Is Still Not Architecturally Honest

The active board runtime is new, but the substrate it consumes is not yet fully
board-authoritative.

The board layer still depends on upstream substrate facts from:

- `RoutingZone.intraKernel`
- placed-zone geometry produced before the board layer becomes authoritative
- imported region-frame assumptions carried through routing/placement

This matters because the next planned work requires geometric operations inside a
zone in response to world-grid pressure. That work needs one substrate owner.

## New Immediate Focus

Make the board substrate authoritative.

This means:

- board doctrine owns span policy
- board geometry owns region-frame construction
- board-local mutation/relaxation operates on board-owned geometry
- imported kernel region sets are no longer the substrate truth

Upstream routing/placement may still exist as inputs, but not as geometry
authorities.

## Goal Definition

The clean-room board substrate is authoritative when all of the following are
true:

1. `BoardGeometrySpec` and board-native builders determine the legal routing
   substrate for a zone.
2. `Board`, `BoardSolver`, `BoardRealizer`, and `BoardMaterializedSolution`
   consume board-owned region frames only.
3. `RoutingZone.intraKernel` is no longer used as the authority for board
   region geometry, lane counts, or mutable substrate shape.
4. Region motion in response to pressure can be expressed as mutation of
   board-owned frame families without reconciling against stale imported kernel
   frames.

## Phase A0: Audit And Boundary Map

**Objective**

Produce an exact list of where substrate truth still leaks in from
`RoutingZone.intraKernel` or placed-zone geometry.

**Modules to audit**

- `src/signalflow/board/builders.py`
- `src/signalflow/board/invariants.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/board/chip_internal.py`
- `src/signalflow/board/geometry.py`
- `src/signalflow/board/board.py`
- `src/signalflow/board/zone_runtime.py`
- `src/signalflow/engine/inspect/build.py`
- `src/signalflow/routing/placement.py`

**Deliverable**

A short map of each read of imported substrate truth, classified as:

- `must_replace`
- `temporary_input`
- `compatibility_only`

**Success criteria**

- every board-era substrate dependency on `intraKernel` is enumerated
- every dependency is classified

## Phase A1: Freeze Board Doctrine As Sole Span Authority

**Objective**

Confirm and tighten `BoardGeometrySpec` / `RingGeometrySpec` /
`boardGeometryConfig` as the only owners of span policy.

**What to do**

- ensure fan, terminal, longitude, latitude, transfer, and courtyard span policy
  is either:
  - owned directly by doctrine/config
  - or explicitly marked as derived-from-demand
- remove any hidden span defaults elsewhere in board construction

**Files likely touched**

- `src/signalflow/board/doctrine.py`
- `src/signalflow/config/board_defaults.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/routing/placement.py`

**Success criteria**

- there is one obvious policy home for every substrate span family
- docs and snippet outputs agree on current defaults

## Phase A2: Board-Native Region Frame Construction

**Objective**

Make board region frames derive from board doctrine plus placement facts, not
from imported kernel region sets.

**Key idea**

Placement may still tell the board:

- chip stack extents
- attachment rows
- demand-derived minimum channel counts

But the actual region frames should then be constructed by the board builder.

**What to do**

- identify any builder path that imports region frames directly from
  `routingZone.intraKernel`
- replace those reads with board-native frame derivation
- preserve current snippet-visible geometry where it is still valid

**Files likely touched**

- `src/signalflow/board/builders.py`
- `src/signalflow/board/geometry.py`
- `src/signalflow/board/board.py`
- possibly `src/signalflow/board/chip_internal.py`

**Success criteria**

- board geometry can be constructed without importing substrate frames from the
  kernel region set
- `board.geometry.regionFramesByName` is board-owned, not kernel-owned

## Phase A3: Replace `intraKernel` Reads In Invariants And Runtime

**Objective**

Stop reading substrate truth from `RoutingZone.intraKernel` in board-era
invariants/runtime code.

**Known current leak**

- `board/invariants.py` still derives some minimums from `routingZone.intraKernel`

**What to do**

- move invariant derivation onto board geometry and placement facts
- keep only the minimum upstream inputs actually required

**Files likely touched**

- `src/signalflow/board/invariants.py`
- `src/signalflow/board/zone_runtime.py`
- `src/signalflow/board/channels_runtime.py`

**Success criteria**

- board invariants no longer need `routingZone.intraKernel` as substrate source
- lane counts and region geometry are board-native

## Phase A4: Make Realizer And Relaxation Board-Sovereign

**Objective**

Make `realizer.py` operate on authoritative board-owned geometry only.

**Why**

The current realizer already contains compensating logic for stale imported axes.
That should disappear once board-owned geometry is authoritative.

**What to do**

- remove assumptions that the imported placed kernel owns the latitude axis
- keep relaxation as mutation over board-owned frame families
- ensure pressure scoring and region shifting operate on authoritative geometry

**Files likely touched**

- `src/signalflow/board/realizer.py`
- `src/signalflow/board/materialized_runtime.py`

**Success criteria**

- no comments or logic remain that treat the imported kernel as geometry owner
- pressure-driven shifts are expressed only in terms of board frames

## Phase A5: Inspect/Context Demotion Of Old Substrate Ownership

**Objective**

Make `engine/inspect` and context build present the board layer as the geometry
authority rather than the placed kernel.

**What to do**

- audit `engine/inspect/build.py` and the inspect surfaces for substrate
  authority leaks
- ensure inspect surfaces explain board-owned geometry
- keep upstream solved-route sets only as upstream inputs where still needed

**Files likely touched**

- `src/signalflow/engine/inspect/build.py`
- `src/signalflow/engine/inspect/surfaces.py`
- `src/signalflow/engine/inspect/primitives.py`

**Success criteria**

- REPL/snippet surface reflects board-owned substrate truth
- no inspect explanation depends on old kernel substrate semantics

## Phase A6: Mutation-Ready Board Geometry API

**Objective**

Prepare the board substrate for the next feature: geometric operations inside a
zone in response to world-grid pressure.

**What to add**

- explicit board-owned region-family movement operations
- immutable/mutable boundary between doctrine and derived geometry
- a clean API for shifting one or more region families while preserving
  invariants

**Likely design targets**

- family-level frame selection
- axis-safe shift operations
- post-shift validation helpers
- pressure-input adapter types

**Success criteria**

- there is a direct API to move region families inside a zone
- the API does not need to reconcile against imported kernel frames

## Phase A7: Delete Compatibility Ownership Paths

**Objective**

After board substrate authority is stable, remove the remaining code paths that
act as if the imported kernel owns the board substrate.

**What to remove or demote**

- substrate reads from `RoutingZone.intraKernel`
- compatibility comments and shims around stale imported axes
- any adapter code that still imports kernel region frames as board truth

**Success criteria**

- the board substrate can be described without reference to imported kernel
  region geometry

## Verification Gates

Every phase should be verified with:

1. `python -m pytest tests_symbolic -q`
2. zone geometry snippet:
   - `snippets/algebraic/zone_geometry.py -- --zone 1,1`
3. solver/materialization snippet:
   - `snippets/algebraic/hub_kernel_solver.py -- --zone 1,1`
4. internal wiring snippet:
   - `snippets/algebraic/hub_internal_wiring.py`
5. direct type/lint checks on touched files

And every phase must answer:

- does the board geometry shown by snippets come from board-owned construction?
- is any route realized against non-authoritative imported substrate frames?
- did any new shared occupancy or false geometry appear?

## Canonical Snippet Contract

The following snippet surface is a live contract during the migration:

- `snippets/algebraic/zone_geometry.py`
- `snippets/algebraic/hub_kernel_solver.py`
- `snippets/algebraic/hub_internal_wiring.py`
- `snippets/algebraic/hub_internal_geometry.py`

Rules:

1. No phase is complete if any canonical snippet stops working.
2. No phase is complete if any canonical snippet output changes and the change
   is not explicitly classified as:
   - expected and desired
   - expected but temporary
   - unexpected regression
3. If a phase requires an internal ownership cut that would otherwise break a
   canonical snippet, add a compatibility adapter in the same phase.
4. Do not accumulate “temporary breakage” across phases.

## Recommended Order

Do not start with mutation APIs.

Use this order:

1. `A0` audit
2. `A1` doctrine freeze
3. `A2` board-native frame construction
4. `A3` invariant/runtime cleanup
5. `A4` realizer sovereignty
6. `A5` inspect/context demotion of old ownership
7. `A6` mutation-ready geometry API
8. `A7` compatibility deletion

## What Is Explicitly Not The Immediate Focus

- whole-repo lint cleanup
- legacy engine removal
- world-scale `extra` long-haul routing semantics beyond current board doctrine
- cosmetic inspect refactors

## Stop Condition For This Plan

This plan is complete when:

- `BoardGeometrySpec` plus board-native builders own the zone substrate
- board solve/materialize operates only on board-owned frames
- inspect surfaces present board-owned geometry as the truth
- region-motion work can begin without reconciling against imported kernel
  substrate frames
