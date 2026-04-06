# Agent Coding Hints And Guides

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

The WiringSolution consolidation is a 7-phase migration. Do not attempt to
do two phases in one pass. Each phase has specific pre-conditions and must be
verified with the test suite before the next phase begins.

Phase sequence: W1 → W1b tests → W2 → W3 → W4 → W5 → W6 (deferred).

Never touch `board/` files during Phase W1. Never touch `notation/` during
Phase W2 unless fixing something broken by W2.

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

The east longitude (`sfN.Ei`) uses `REVERSE`. For a 5-wire bundle on a 10-lane
board: wire 0 → `eLong[10]`, wire 4 → `eLong[6]`. Using `_laneCount` (5)
gives `eLong[5]` for wire 0 — wrong, and tests will catch it if you write them.

## REPL / Snippet Priority

When architecture is under discussion, prefer truth surfaces over source-only
reasoning. Use snippet outputs as architectural evidence.

## Physics First

Do not distort routing doctrine to satisfy stale expectations. If geometry,
algebra, and render output disagree: identify the owning layer, fix it, then
update expectations.

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
