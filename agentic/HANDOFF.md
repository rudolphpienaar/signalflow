# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.16`
- Branch point commit: `07c46b4`

---

## What Just Happened (April 2026 — notation/ and WiringSolution arc)

### The `notation/` package was created

`src/signalflow/notation/` is a new canonical package for all geometry naming
and algebraic path algebra. It is the single source of truth for sfN notation.

#### `notation/sfn.py` — `sfN` enum

All 34 geometry region members as a single Python enum. This replaces all
scattered string literals across the board layer.

- `sfN.Wi`, `sfN.Ni`, `sfN.Ei`, `sfN.Si` — intra longitude and latitude
- `sfN.We`, `sfN.Ne`, `sfN.Ee`, `sfN.Se` — extra ring channels
- `sfN.Wfi`, `sfN.Efi`, `sfN.Nfi`, `sfN.Sfi` — intra fans
- `sfN.Wfe`, `sfN.Efe` etc. — extra fans
- `sfN.region_key` — `"side/family"` string for geometry layer lookups
- `sfN.channel_name` — legacy solver tokens (`"wLong"`, `"nLat"`, `"wf"`, etc.)
- `sfN.from_region_key()`, `sfN.from_channel_name()` — reverse lookups
- `sfN.intra_routing_channels()`, `sfN.extra_routing_channels()` — ordered channel lists

#### `notation/path.py` — algebraic path algebra

The full path algebra. Key design decisions made during this arc:

**`LaneSense` enum replaces both `LaneAssignment` and `RoutingLaneAttachmentSense`.**
These were found to be the same concept at two scopes — index mapping sense:
- `FIXED` — fan/transition hops, no routing lane
- `FORWARD` — wire index maps directly: wire 1 → lane 1, wire N → lane N
- `REVERSE` — wire index maps inverted: wire 1 → lane N, wire N → lane 1

**`PathHop(area: sfN, laneSense: LaneSense)`** — no lane integer. Lane integers
do NOT belong on PathHop. They are owned by WiringSolution.

**`AlgebraicPath(source, hops, sink)`** — pure topology descriptor. No lane
integers anywhere. `text_sprint()` and `fromText_build()` return `Result[str]`
and `Result[AlgebraicPath]` — the project uses `Result[T]` not exceptions.

**`PathSolutionBuilder`** — named mutable topology. `.resolve(source, sink)`
produces an `AlgebraicPath`. This is the user-facing extension point.

**`WiringSolution(topology, _paths, _laneCount)`** — owns lane state for a
wire bundle. Currently partially complete — see PLAN.md for what is missing.

**Named topology constants** (immutable, safe to share):
```python
WTE_INTRA_FORWARD  # Wfi, Wi/FORWARD, Ni/FORWARD, Ei/REVERSE, Efi
WTE_INTRA_RETURN   # Efi, Ei/FORWARD, Si/FORWARD, Wi/FORWARD, Wfi
```

**No module-level WiringSolution singletons.** `wteIntra`/`etwIntra` were
removed because mutable module-level state causes test ordering failures.
`BoardSolver` must construct a fresh `WiringSolution` per solve.

#### Migrations done

- `board/solver.py` — uses `sfN.X.channel_name` for all tokens
- `board/channels_runtime.py` — `preferredChannelOrder` from `sfN` methods
- `board/realizer.py` — all region key strings via `sfN.X.region_key`
- `board/builders.py` — region key literals replaced with sfN
- `board/chip_runtime.py` — Pyright fixes
- `engine/debug.py` — import fixed, fan token set uses sfN
- `tests_symbolic/` — Pyright clean, 18/18 passing

### The fragmentation problem was diagnosed

The current wiring pipeline has five representations of one wire (see
`papers/brittle_patterns.adoc` for the full analysis):

1. `CallRouteObligation` — logical intent
2. `KernelObligation.laneIndex` — ghost field, defaulted to 0, never used
3. `BoardKernelWire` — endpoint text + chip refs
4. `BoardSolvedWire.algebraicPathText: str` — lanes embedded in strings
5. `BoardMaterializedWire` — lanes parsed back out from the string

The most broken pattern: lane integers are computed in
`boardWireAlgebraicPath_build()`, formatted into `"wLong[3]"` strings, then
parsed back out by regex in `materialized_runtime.py`. This is an information
loop that exists only because two representations were developed independently.

### The consolidation plan was produced

See `agentic/PLAN.md` for the full 7-phase implementation plan. The work is
not started beyond the `notation/` package and the singleton removal.

---

## Critical Semantic Issue Before Phase 1

**Risk 4 — REVERSE sense uses channel capacity, not bundle size.**

The current `boardWireAlgebraicPath_build()` computes REVERSE lane for `Ei` as:
```python
eastLaneIndex = eLongCount - forwardIndex + 1
```
where `eLongCount` is the board's total east channel capacity (e.g., 10).

The proposed `WiringSolution.laneMap_get()` currently uses `_laneCount` (bundle
size, e.g., 5). These are DIFFERENT when the bundle is smaller than the channel.

The tests assert `eLong[10]` for the FIRST wire in a 5-wire bundle on a 10-lane
board. `WiringSolution` must receive `channelLaneCounts: dict[str, int]` from
`boardChannelLaneCounts_build()` at construction time, and `laneMap_get()` must
use `channelLaneCounts["eLong"]` for REVERSE hops, not `_laneCount`.

Do NOT implement `laneMap_get()` without resolving this. It will break the
materialization pipeline silently.

---

## Test Baseline

18/18 symbolic tests passing in `tests_symbolic/test_symbolic_kernel_quarantine.py`.

Tests assert exact string forms:
- `"wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]"` — format with brackets
- World-annotated paths with `@(row,col)` annotations
- Collision tokens like `"wLong[1]: App.ts..."`

These string forms are a PUBLIC output. The `algebraicPathText` property shim
in Phase 2 must reproduce them exactly. Run tests after every phase.

---

## What Not To Trust

- Stale notes mentioning `rearch-zone-grid`, `566/0`, seam kernels as settled
- Any claim that `WiringSolution.laneMap_get()` is complete — it is not
- Module-level `wteIntra`/`etwIntra` — removed, do not recreate as singletons

## Operating Discipline

- if you are guessing, say so
- if something is partial, say so
- if a property is claimed, point to the runtime path or snippet output
- if the user says `DNC`, do not code
- do not do broad rewrites — surgical changes only, one phase at a time
- run `python -m pytest tests_symbolic/ -q` after every change
