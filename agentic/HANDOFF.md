# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.19`
- Head at this handoff update: `198035d`

## Current Baseline

The previous large refactor arc is complete enough to treat as baseline:

- `notation/` is canonical.
- `WiringSolution` owns live lane assignment through the board runtime.
- `engine/inspect/` replaced the old debug monolith.
- the duplicate debug-side solve/materialize runtime is gone.
- board-local solve/materialize is the live path.

## What Just Stabilized

### Inspect facade replacement

`engine/debug.py` is gone. The live inspection surface is now
`src/signalflow/engine/inspect/`.

This package:

- projects the real board runtime
- no longer recomputes a second solved-wire/materialized-wire hierarchy
- is the likely future external inspection/query surface

### Wiring/runtime consolidation

The board runtime now uses structured solved-wire state:

- `BoardSolvedWire`
- `BoardSolver`
- `BoardSolution`
- `BoardMaterializedSolution`

The active solve/materialize path no longer depends on parsing a string as the
source of truth.

### Return-shell correction

The following bug was fixed:

- the solved algebraic text and realized geometry used different return-lane
  indices because of a compatibility offset shim

Current state:

- realized geometry uses the same effective lane indices that the algebraic text
  reports
- return-shell south latitude and west longitude now pack from the far edge
  (`REVERSE`)

Observed current return shape for zone `(1,1)`:

- first return:
  - `Proxy.ts.p1().r1::ef[0]::eLong[1]::sLat[10]::wLong[10]::wf[0]::App.ts.main().r1`
- last return:
  - `Proxy.ts.p5().r5::ef[0]::eLong[5]::sLat[6]::wLong[6]::wf[0]::App.ts.main().r5`

### Fan-span policy

Board default fan spans are now `4` for west/east intra and extra fans in:

- `src/signalflow/config/board_defaults.py`

## What The Current Problem Actually Is

The old `signalflow.legacy` engine is not the immediate problem for the board
path.

The remaining architectural problem is:

**old substrate authority**

The board runtime is new, but it still consumes substrate facts that originate
upstream in:

- `RoutingZone.intraKernel`
- placed-zone geometry
- imported region-frame assumptions in routing/placement-era code

That mixed authority is the wrong base for the next planned feature:

- pressure-driven geometric operations inside a zone

## Current Strategic Decision

The next major phase should be:

**make the board substrate authoritative**

This means:

- board doctrine owns policy
- board builders own region-frame construction
- board realizer/materializer operate on board-owned frames
- imported kernel geometry stops being the board substrate truth

## Important Active Runtime Path

- `context_buildFromDocument(documentDict)`
- `zones.zone_get(col, row)`
- `zone.kernel_get("intra")`
- `kernel.board_get(...)`
- `kernel.solver_get(board)`
- `solver.solution_get()`
- `solution.board_materialize(board, policy=...)`

## Important Current Files

- `src/signalflow/notation/sfn.py`
- `src/signalflow/notation/path.py`
- `src/signalflow/board/doctrine.py`
- `src/signalflow/config/board_defaults.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/board/solver.py`
- `src/signalflow/board/solver_runtime.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/board/materialized_runtime.py`
- `src/signalflow/engine/inspect/build.py`

## Important Snippets

- `snippets/algebraic/zone_geometry.py`
- `snippets/algebraic/hub_kernel_solver.py`
- `snippets/algebraic/hub_internal_wiring.py`
- `snippets/algebraic/hub_internal_geometry.py`

Use snippets as architectural evidence.

## Verification Baseline

At this handoff update:

- `python -m pytest tests_symbolic -q` passes `27`

## What Not To Trust

- stale `agentic/*` instructions about Phase W1 / W2 WiringSolution work
- any claim that the board substrate is already fully clean-room
- any assumption that imported kernel geometry can safely remain authoritative
  once region-motion work begins

## Operating Discipline

- if you are guessing, say so
- if the board is still consuming old substrate truth, say so
- if a region-motion idea depends on mixed authority, stop and fix ownership
  first
- verify with snippets, not prose alone
