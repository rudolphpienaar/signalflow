# Zero-Shot Handoff: SignalFlow Board Runtime And Authoritative Substrate Work

**Branch:** `worldscale-extra-routing`  
**Version:** `5.9.19`

## Current Truth In One Screen

- the active runtime is the board-era runtime
- `notation/` is canonical
- `engine/inspect/` is the live inspection facade
- the duplicate debug runtime is gone
- `WiringSolution` is the live lane-assignment authority in the board solve path
- the next architectural problem is not legacy-engine use but mixed substrate
  authority

## Active Runtime Path

- `zones.zone_get(col, row)`
- `zone.kernel_get("intra")`
- `kernel.board_get(...)`
- `kernel.solver_get(board)`
- `solver.solution_get()`
- `solution.board_materialize(board, policy=...)`

## Recent Important Corrections

- solved algebraic path text and realized geometry now use the same return-lane
  indices
- return-shell south-latitude and west-longitude packing now runs from the far
  edge (`REVERSE`)
- fan-span defaults are now `4` for intra/extra west/east fan bands

## The Real Remaining Problem

The board runtime is new, but its substrate is not yet fully authoritative.

The board layer still consumes upstream substrate facts from:

- `RoutingZone.intraKernel`
- placed-zone geometry
- imported region-frame assumptions in routing/placement-era code

That is now the main architectural target.

## The Immediate Job

Follow `agentic/PLAN.md` Phase `A0` and then the authoritative-board-substrate
phases.

Do not restart the old WiringSolution migration plan.

## Most Important Files

- `src/signalflow/board/doctrine.py`
- `src/signalflow/config/board_defaults.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/board/invariants.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/board/materialized_runtime.py`
- `src/signalflow/engine/inspect/build.py`

## Most Important Snippets

- `snippets/algebraic/zone_geometry.py`
- `snippets/algebraic/hub_kernel_solver.py`
- `snippets/algebraic/hub_internal_wiring.py`

## First Action For A New Agent

```bash
python -m pytest tests_symbolic/ -q
```

Then read `agentic/HANDOFF.md` and `agentic/PLAN.md` before modifying any file.
