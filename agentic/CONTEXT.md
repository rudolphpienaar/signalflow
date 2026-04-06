# Project Context: SignalFlow — Board-Era Runtime And World-Scale Routing

This file is the current architectural baseline for agent work on this branch.

## Current Architectural State

- Branch: `worldscale-extra-routing`
- Version: `5.9.16`
- Base commit on this branch: `07c46b4`
- Current major runtime path is the board-era path, not the older `rearch-zone-grid`
  kernel-only path documented in stale notes.

## What Is Current Truth

- `chips.chip_get(...)` returns a real `BoardChip`.
- `chip.internalBoard_get()` returns a real `BoardKernel`.
- `kernel.board_get(...)` constructs a `Board`.
- `kernel.solver_get(board)` returns a `BoardSolver`.
- `solver.solution_get()` returns a `BoardSolution`.
- `solution.board_materialize(board, policy=...)` is the canonical realization API.
- `BoardMaterializePolicy` and `BoardRelaxationSymmetry` are real runtime policy surfaces.
- `BoardChipPlacementPolicy` is a real runtime policy surface.
- The REPL and snippets are part of the architecture. They are not convenience-only tooling.

## What Was Recently Stabilized

### Geometry centralization (v5.9.16)

`BoardGeometrySpec`, `ZoneSymbolicInvariants`, and `boardGeometryConfig` singleton are live.
All intra span policy floors now read from config at solver call time.
No more scattered defaults across `placement.py` / `builders.py`.

### `notation/` package (April 2026)

`src/signalflow/notation/` is new and canonical.

- `notation/sfn.py` — `sfN` enum: single source of truth for all 34 geometry
  region names. Members: `Wi`, `Ei`, `Ni`, `Si` (intra channels), `We`, `Ee`,
  `Ne`, `Se` (extra channels), `Wfi`, `Efi`, `Nfi`, `Sfi` (intra fans), plus
  extra fan variants. Properties: `region_key`, `channel_name`. Classmethods:
  `from_region_key()`, `from_channel_name()`, `intra_routing_channels()`,
  `extra_routing_channels()`.

- `notation/path.py` — algebraic path algebra:
  - `LaneSense` — `FIXED`/`FORWARD`/`REVERSE`. Single enum replacing both
    the old `LaneAssignment` and `RoutingLaneAttachmentSense` concepts.
  - `PathHop(area: sfN, laneSense: LaneSense)` — no lane integer.
  - `AlgebraicPath(source, hops, sink)` — topology only. `text_sprint()` and
    `fromText_build()` use `Result[T]`, not exceptions.
  - `PathSolutionBuilder` — named mutable topology. `.resolve(source, sink)`.
  - `WiringSolution` — wire bundle with lane state. **Partially complete.**
    Missing: `channelLaneCounts`, `_laneCount`, `kernel_wiring`, `laneMap_get()`.
    See `agentic/PLAN.md` Phase W1 for what to add.
  - `WTE_INTRA_FORWARD`, `WTE_INTRA_RETURN` — immutable topology constants.
    Safe to share. Do not create singletons around them.

- `notation/__init__.py` — exports `sfN`, `AlgebraicPath`, `LaneSense`,
  `PathHop`, `PathSolutionBuilder`, `WiringSolution`, `WTE_INTRA_FORWARD`,
  `WTE_INTRA_RETURN`, plus `Result` helpers from `signalflow.models.result`.

### Board layer migrations

- `board/solver.py` — uses `sfN.channel_name` for all tokens
- `board/channels_runtime.py` — channel order from `sfN` methods
- `board/realizer.py` — region key strings via `sfN.region_key`
- `board/builders.py` — region key literals replaced

### Error model

This project uses `Result[T]` — NOT exceptions for expected failure cases.
Import from `signalflow.models.result`:
- `resultOk_build(value)`, `resultErr_build()`, `result_isOkCheck()`, `result_isErrCheck()`
- On failure: push to `diagnosticStack` from `signalflow.models.diagnostics`
  before returning `resultErr_build()`

### Naming convention

`<camelCaseNoun>_<verb>()` — e.g. `token_sprint()`, `text_sprint()`,
`fromText_build()`, `channelHops_get()`, `laneMap_get()`.

## Important Runtime APIs

- `chip.geometry_get()`
- `chip.internalBoard_get()`
- `kernel.board_get(chipPlacementPolicy=...)`
- `kernel.solver_get(board)`
- `solver.solution_get()`
- `solution.board_materialize(board, policy=...)`
- `context_buildFromDocument(documentDict)` → `Result[SignalFlowContext]`
- `boardChannelLaneCounts_build(board)` → `dict[str, int]` (in `board/solver.py`)

## Important Snippets

- `snippets/algebraic/hub_internal_wiring.py` — internal chip wiring + collisions
- `snippets/algebraic/hub_internal_geometry.py` — board geometry text + frames
- `snippets/algebraic/zone_1_1_geometry.py` — zone (1,1) intra geometry (REPL)
- `snippets/algebraic/zone_geometry.py` — standalone zone geometry inspector
- `snippets/algebraic/zone_invariants.py` — full geometry centralization pipeline

These are truth surfaces. Use them before making architectural claims.

## Current Macro Design Direction

Two concurrent tracks:

### Track A: WiringSolution consolidation (immediate)

Make `WiringSolution` the authoritative single source of truth for wire
connections and lane assignment, eliminating the scattered five-representation
pattern currently in the board layer. See `agentic/PLAN.md` Phases W1–W7.

### Track B: World-scale `extra` routing (after Track A)

One local kernel owns an inner `intra` routing substrate and an outer `extra`
routing substrate. `extra` is concentric perimeter routing, not a new seam
object and not a new placed kernel. `intra` and `extra` connect through explicit
transfer regions. See `docs/worldscale_geometry.adoc`.

## Document Precedence

When there is tension between files, use this order:

1. `agentic/HANDOFF.md`
2. `agentic/DOTHIS.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `agentic/PLAN.md`
5. `docs/worldscale_geometry.adoc`
6. `papers/new_ways.adoc`
7. `docs/ideas.adoc`
8. `docs/architecture.adoc`

## Mandatory Operating Rule

Do not claim an architectural property unless you can point to at least one of:
- the owning runtime API
- the file/function implementing it
- snippet output
- rendered geometry
- a test assertion

If the implementation is partial, say it is partial.

## What Is No Longer Current

- branch assumptions in old `rearch-zone-grid` notes
- old milestone counts like `566/0`
- seam-kernel plans as the primary next step
- module-level `wteIntra`/`etwIntra` singletons — removed deliberately
- `LaneAssignment` enum — replaced by `LaneSense`
- `wteIntraForwardPath_build()` / `wteIntraReturnPath_build()` — removed
