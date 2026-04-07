# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `agentic/PLAN.md`

Current branch is `worldscale-extra-routing`. Current version is `5.9.19`.

## Immediate Focus

Do not restart old WiringSolution phases. That work is already baseline.

The current major task is:

**make the board substrate authoritative before adding pressure-driven
intra-zone geometry operations**

## First Step

Do Phase `A0` from `agentic/PLAN.md`.

That means:

1. audit all reads of imported substrate truth from `RoutingZone.intraKernel`
   or placed-zone geometry inside the board-era path
2. classify each read as:
   - `must_replace`
   - `temporary_input`
   - `compatibility_only`
3. write down the map before making broad edits

## Verification Surface

Before and after each meaningful change, use:

1. `python -m pytest tests_symbolic -q`
2. `snippets/algebraic/zone_geometry.py -- --zone 1,1`
3. `snippets/algebraic/hub_kernel_solver.py -- --zone 1,1`
4. `snippets/algebraic/hub_internal_wiring.py`

## Primary Files For This Phase

- `src/signalflow/board/builders.py`
- `src/signalflow/board/invariants.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/board/chip_internal.py`
- `src/signalflow/board/geometry.py`
- `src/signalflow/engine/inspect/build.py`

## Things Not To Do

- do not spend time on more inspect cosmetic refactors
- do not restart a repo-wide lint pass
- do not claim the board substrate is already clean-room
- do not add region-motion features before the substrate ownership cut is clear
- do not use `signalflow.legacy.*` as a shortcut

## Current Reality Check

The board solve/materialize path is new and stable enough to build on.
The remaining architectural problem is upstream substrate authority, not the old
legacy engine.
