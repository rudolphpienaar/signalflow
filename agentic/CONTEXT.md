# Project Context: SignalFlow Board Runtime And Authoritative Substrate Work

This file is the current architectural baseline for work on this branch.

## Current Architectural State

- Branch: `worldscale-extra-routing`
- Version: `5.9.19`
- Head at this context update: `198035d`

## What Is Actually Stable Now

- `src/signalflow/notation/` is canonical for symbolic geometry naming and path
  algebra.
- `WiringSolution` is now the active lane-assignment authority through the live
  board solve/materialize path.
- `engine/debug.py` is gone.
- `engine/inspect/` is the live human-facing inspection facade.
- the duplicate debug-side runtime hierarchy is gone.

## Active Runtime Path

The active zone-local board path is:

- `context_buildFromDocument(documentDict)`
- `zones.zone_get(col, row)`
- `zone.kernel_get("intra")`
- `kernel.board_get(...)`
- `kernel.solver_get(board)`
- `solver.solution_get()`
- `solution.board_materialize(board, policy=...)`

This is the real path used by the snippets and REPL.

## What Was Recently Stabilized

### Inspect facade

- `src/signalflow/engine/inspect/` is the canonical inspection surface.
- `debug.py`, `_core.py`, and `common.py` are removed.
- inspect projects the board runtime instead of recomputing a second one.

### Wiring/runtime consolidation

- `BoardSolvedWire` carries structured algebraic state.
- `BoardMaterializedSolution` realizes from structured solved-wire state.
- string compatibility still exists as a projection, not as the solve source of
  truth.

### Return-shell correction

Recent fixes established:

- materialization uses the same live lane indices that the solved algebraic text
  reports
- the return shell packs from the far side on south latitude and west longitude
  (`REVERSE`)

### Fan-span defaults

Board policy defaults currently set:

- `intraWFanSpan = 4`
- `intraEFanSpan = 4`
- `extraWFanSpan = 4`
- `extraEFanSpan = 4`

in `src/signalflow/config/board_defaults.py`.

## What Is Still Mixed-Authority

The board runtime is new, but the substrate beneath it is not yet fully
board-sovereign.

Board-era code still depends on upstream substrate facts from:

- `RoutingZone.intraKernel`
- placed-zone geometry produced before the board layer becomes authoritative
- imported region-frame assumptions in assignment/placement-era code

That is now the main architectural problem.

## Current Strategic Direction

The next major phase is not more inspect cleanup and not more WiringSolution
cleanup.

The next major phase is:

**make the board substrate authoritative**

This is required before pressure-driven intra-zone geometric operations can be
added sanely.

## What "Authoritative Board Substrate" Means

- `BoardGeometrySpec` and board-native builders own the zone substrate
- board solve/materialize consumes board-owned region frames only
- `RoutingZone.intraKernel` is no longer the geometry authority for the board
  layer
- region motion happens by mutating board-owned frame families

## Important Files For The New Focus

- `src/signalflow/board/doctrine.py`
- `src/signalflow/config/board_defaults.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/board/geometry.py`
- `src/signalflow/board/invariants.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/board/materialized_runtime.py`
- `src/signalflow/board/chip_internal.py`
- `src/signalflow/engine/inspect/build.py`

## Important Snippets

- `snippets/algebraic/zone_geometry.py`
- `snippets/algebraic/hub_kernel_solver.py`
- `snippets/algebraic/hub_internal_wiring.py`
- `snippets/algebraic/hub_internal_geometry.py`

These are truth surfaces. Use them before making architectural claims.

## Current Verification Baseline

At the time of this context update:

- `python -m pytest tests_symbolic -q` passes `27`
- the hub and zone snippets are the expected verification surface for board
  geometry and solve/materialize behavior

## Document Precedence

When there is tension between files, use this order:

1. `agentic/HANDOFF.md`
2. `agentic/DOTHIS.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `agentic/PLAN.md`
5. runtime/snippet evidence

## Mandatory Operating Rule

Do not claim that the substrate is clean-room or authoritative unless you can
point to:

- the builder path
- the runtime object
- the snippet output
- or a test assertion

If old substrate facts still leak in, say so explicitly.
