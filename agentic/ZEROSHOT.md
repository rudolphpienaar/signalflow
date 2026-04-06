# Zero-Shot Handoff: SignalFlow Board Runtime, notation/ Package, And WiringSolution

**Branch:** `worldscale-extra-routing`
**Version:** `5.9.16`

## Current Truth In One Screen

- The main active runtime is the board-era runtime, not the old kernel-only rearch notes.
- `chips.chip_get(...)` → `BoardChip` → `.internalBoard_get()` → `BoardKernel`
  → `.board_get()` → `Board` → `.solver_get(board)` → `BoardSolver`
  → `.solution_get()` → `BoardSolution` → `.board_materialize(board, policy=...)`
- Geometry centralization is complete: `BoardGeometrySpec`, `ZoneSymbolicInvariants`,
  `boardGeometryConfig` singleton are all live in `board/doctrine.py`,
  `board/invariants.py`, `config/board_defaults.py`.
- `src/signalflow/notation/` is a new canonical package for sfN geometry naming
  and algebraic path algebra. It was built in the April 2026 arc.
- 18/18 symbolic tests passing.

## Most Important Current Files

- `src/signalflow/notation/path.py` — `LaneSense`, `PathHop`, `AlgebraicPath`,
  `PathSolutionBuilder`, `WiringSolution`, `WTE_INTRA_FORWARD`, `WTE_INTRA_RETURN`
- `src/signalflow/notation/sfn.py` — `sfN` enum, all 34 geometry region members
- `src/signalflow/board/solver.py` — `boardChannelLaneCounts_build()`,
  `boardWireAlgebraicPath_build()` (to be demoted to serializer)
- `src/signalflow/board/solver_runtime.py` — `BoardSolvedWire` (to gain structured fields)
- `src/signalflow/board/materialized_runtime.py` — three string parse sites to replace
- `src/signalflow/board/realizer.py` — to gain structured entry point
- `src/signalflow/board/doctrine.py` — `BoardGeometrySpec`, `RingGeometrySpec`
- `src/signalflow/board/invariants.py` — `ZoneSymbolicInvariants`
- `src/signalflow/config/board_defaults.py` — `boardGeometryConfig` singleton

## Key Snippets

- `snippets/algebraic/zone_invariants.py` — full geometry pipeline (CLI, `--zone`)
- `snippets/algebraic/zone_geometry.py` — zone geometry standalone (CLI, `--zone`)
- `snippets/algebraic/hub_internal_geometry.py` — chip internal board geometry
- `snippets/algebraic/hub_internal_wiring.py` — internal chip wiring + collisions

## The Immediate Job

Extend `WiringSolution` in `notation/path.py` (Phase W1 in `agentic/PLAN.md`).

Add: `channelLaneCounts: dict[str, int]`, `_laneCount: int`, `kernel_wiring: list[str]`,
`laneMap_get(wireIndex: int) -> dict[sfN, int]`.

**The single most important constraint:** `laneMap_get()` for `REVERSE` hops
must use `channelLaneCounts[hop.area.channel_name]` (board channel capacity),
NOT `_laneCount` (bundle size). Tests assert `eLong[10]` for wire 0 of a 5-wire
bundle on a 10-lane board. Using bundle size produces wrong results silently.

Before touching anything: read `notation/path.py` fully, read `board/solver.py`
to understand `boardChannelLaneCounts_build()`, run `pytest tests_symbolic/ -q`.

## Current Design Direction

Two concurrent tracks:
1. **WiringSolution consolidation** (Track A, immediate) — make `WiringSolution`
   the authoritative single source of truth for wire connections and lane
   assignment. Seven phases documented in `agentic/PLAN.md`.
2. **World-scale `extra` routing** (Track B, after Track A) — concentric
   perimeter `extra` routing substrate connecting to `intra` through explicit
   transfer regions.

The hard unresolved case for Track B: child-to-self routing through `extra`
preserving row/layer identity. Do not start Track B until Track A is complete.

## First Action For A New Agent

```
python -m pytest tests_symbolic/ -q
```

Confirm 18/18. Then read `agentic/HANDOFF.md` and `agentic/PLAN.md` before
modifying any file.
