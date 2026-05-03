# Agent Coding Hints And Guides

Current checkpoint: per-zone routing is complete, the key `1,2` / `1,3`
world-inspect seam is vertically aligned, and `tests_symbolic/` reports
`179 passed`. `WorldGeometryResolver` and `BoardWorldMaterializedSolution` are
the current production board surfaces for harmonized world geometry and
materialized world rendering. Before editing world-solving code, run the
`1,2;1,3` geometry snippet and preserve the world canvas doctrine: no seam chip
override, chip-row vertical alignment, `wOffset` horizontal alignment, and
correct `mergedCellMap_get()` `(row, col)` key order.

Port doctrine is now equally concrete: omitted `return` means forward-only.
Do not reintroduce `2 * portIndex` signal/return pairing as geometry truth,
blank return stubs, or reverse solver routes for ports that do not declare a
return label.

## Depth-Layer Boundary Sprint

The next sprint separates source identity from geometry scope.

Do:

- keep `ChipId.moduleName` as source/module/file identity
- derive default load-bearing geometry scopes from `CallingStack` depth
- let geometry scopes exist without being drawable
- default implicit depth scopes to non-drawable
- treat source module/file boxes as optional overlays or explicit structural
  groups

Do not:

- reinterpret modules as stack-depth layers
- use fake source modules as the permanent layer model
- assume a boundary must be drawn to affect geometry
- let module-banded depth in `calling_stack.py` silently decide layout doctrine

Expected regression shape:

- a neural-network fixture with all chips in one real source module still lays
  out by input/hidden/output depth
- different real source modules at the same call depth do not force separate
  depth layers
- existing back-and-forth seam evidence remains unchanged

Useful model name:

```text
BoardGeometryScope(scopeId, kind, label, chipRefs, drawable)
```

Use `layer/N` for depth-layer scope ids and `module/<source>` for source-module
overlay scope ids. Do not overload one namespace for both meanings.

## Foreground First

Do not spawn sub-agents for ordinary repo work.

Prefer:

- read files directly
- run tests directly with `python -m pytest tests_symbolic/ -q`
- run snippets directly
- patch files directly

The current work is geometry-heavy and conceptually tight. Context loss hurts
more than parallelism helps.

## DNC Protocol

`DNC` means discussion only.

When the user says `DNC`:

- no file edits
- no code implementation
- no speculative patching

## One Phase At A Time

The current large task is depth-layer geometry scope separation. The symbolic
geometry topology plan (Arc G) is valid long-term work but does not resume
until the depth-layer geometry split and world resolver/materialized aggregate
have a stable production call path.

Do not improvise. For the depth-layer/R4 handoff:
- Keep `module` as source identity, not layout depth.
- Derive default load-bearing geometry scopes from `CallingStack`.
- Keep drawability separate from geometry existence.
- Keep harmonization + wOffset logic owned by `WorldGeometryResolver`.
- Keep materialization + world render algebra owned by
  `BoardWorldMaterializedSolution`.
- Keep snippet surface green throughout.
- Do not touch broad Arc G phases (G0–G7) until this split is done.

## Result[T] Not Exceptions

This project uses `Result[T]` for expected failure paths, not `raise`.

```python
from signalflow.models.result import Result, resultOk_build, resultErr_build, result_isOkCheck
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack

# On failure: push diagnostic first, then return err
diagnosticStack.error_push(
    phase=DiagnosticPhase.ROUTING,
    code="notation.path.hop.no_token",
    message="...",
    context=(self.area.name,),
)
return resultErr_build()

# On success:
return resultOk_build(value)
```

Never use `raise ValueError` or `raise RuntimeError` in `notation/` or `board/`
code for expected failure cases.

## Naming Convention

`<camelCaseNoun>_<verb>()` — strictly enforced.

Good: `laneMap_get()`, `text_sprint()`, `fromText_build()`, `wire_add()`,
`channelLaneCounts_set()`, `laneCount_get()`

Bad: `getLaneMap()`, `get_lane_map()`, `sprint()`, `build()`, `add_wire()`

## No Lane Integers On PathHop

`PathHop` does NOT carry a lane integer. It carries `area: sfN` and
`laneSense: LaneSense`. Lane integers belong exclusively to `WiringSolution`.

If you find yourself putting a lane integer on `PathHop` or `AlgebraicPath`,
stop. The design intent is that topology (what channels, what fold sense) lives
in `AlgebraicPath`/`PathHop`, and lane assignment lives in `WiringSolution`.

## No Module-Level WiringSolution Singletons

`WiringSolution` is mutable — it accumulates `_paths` via `wire_add()`. Module-
level instances are shared state that cause test-order failures.

`BoardSolver` must construct a fresh `WiringSolution` per solve:
```python
wiringSolution = WiringSolution(
    topology=WTE_INTRA_FORWARD,
    channelLaneCounts=boardChannelLaneCounts_build(board),
)
```

`WTE_INTRA_FORWARD` and `WTE_INTRA_RETURN` are immutable `PathSolutionBuilder`
instances and ARE safe as module-level constants.

## Backward Compatibility Via Property Shims

The `algebraicPathText: str` format like `"source::wf[0]::wLong[3]::..."` is a
public output. Tests assert exact string forms. Do not break this.

When replacing `BoardSolvedWire.algebraicPathText: str` with structured fields,
add a `@property` that reconstructs the exact string from `AlgebraicPath` +
`laneMap_get()`. Run the full test suite to verify format compatibility.

## REVERSE Semantics — The Critical Correctness Constraint

For `REVERSE` hops in `laneMap_get()`:

```python
# CORRECT: use channel capacity from the board
capacity = self.channelLaneCounts.get(hop.area.channel_name, self._laneCount)
result[hop.area] = capacity - wireIndex

# WRONG: do not use bundle size
result[hop.area] = self._laneCount - wireIndex  # WRONG
```

The east longitude (`sfN.Ei`) uses `REVERSE` in the forward shell. The return
south latitude (`sfN.Si`) and west longitude (`sfN.Wi`) now also use `REVERSE`
in the clockwise return shell. For a 5-wire bundle on a 10-lane board:

- forward wire 0 → `eLong[10]`
- return wire 0 → `sLat[10]`, `wLong[10]`

Using `_laneCount` (5) would silently produce wrong results.

## REPL / Snippet Priority

When architecture is under discussion, prefer truth surfaces over source-only
reasoning. Use snippet outputs as architectural evidence.

## Physics First

Do not distort routing doctrine to satisfy stale expectations. If geometry,
algebra, and render output disagree: identify the owning layer, fix it, then
update expectations.

## Doctrine First

When a bug or mismatch is found, first trace it to the general doctrinal,
ownership, or coupling issue before proposing a local-only fix.

Do not start with:

- a one-off patch
- a family-specific special case
- a rendering-only explanation

until you have stated whether the bug is actually evidence of:

- missing ownership doctrine
- missing coupling doctrine
- mixed centers of truth
- stale compatibility architecture

Only after that may you propose a local bounded fix, and you must say clearly
whether it is:

- the real architectural correction
- or only a temporary bounded patch

## Symbolic Topology First

When geometry order, adjacency, continuity, or coupling behavior is unclear, do
not rely only on builder arithmetic or raw frame inspection.

First ask:

- should this live in symbolic topology
- should this be an explicit coupling rule
- should this be an interpreter reaction

The next architecture target is not "more frame surgery." It is a symbolic
topology layer that makes those semantic relations explicit.

## Board-Substrate Ownership

The current architectural problem is not legacy-engine use in the board path.
It is mixed substrate authority.

If a board-era module reads substrate truth from `RoutingZone.intraKernel` or
imported placed-kernel frames, treat that as suspect and classify it explicitly:

- `must_replace`
- `temporary_input`
- `compatibility_only`

## Deprecated Concept Warning

Do not deepen any new dependency on:

- `RoutingKernel` as an active required runtime shape
- `RoutingZone.intraKernel|westKernel|eastKernel|northKernel|southKernel`
- `RoutingZoneInterconnect` as a routed substrate body

Those are now compatibility/deletion territory, not the intended design.

## Vague Centers Of Truth

The most important structural anti-pattern in this codebase (documented in
`papers/brittle_patterns.adoc`): the same domain concept represented in multiple
places, none authoritative. Signs of the pattern:
- structured data converted to a string, then parsed back out downstream
- fields that default to 0 and are never meaningfully set
- multiple classes each carrying a subset of information about one entity

If you find yourself adding a field that duplicates something already modelled
elsewhere, stop and ask whether the right fix is consolidation, not addition.

## Documentation Discipline

When a meaningful design idea emerges, write it down promptly in the right place:

- `docs/worldscale_geometry.adoc` for world-scale routing doctrine
- `docs/ideas.adoc` for candidate but not accepted design ideas
- `papers/` for architectural reflection (AsciiDoc, same style as existing papers)

## Token Efficiency

- Read only the ranges you need when the location is known.
- Use snippets to narrow uncertainty before opening many files.
- Do not rewrite whole modules unless the architectural seam truly demands it.
