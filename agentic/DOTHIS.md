# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `agentic/PLAN.md`

Current branch is `worldscale-extra-routing`. Current version is `5.9.16`.

## Immediate Task: Phase W1 — Extend `WiringSolution`

The only file to touch is `src/signalflow/notation/path.py`.

Before touching anything:
1. Read `notation/path.py` fully to understand current `WiringSolution` state.
2. Read `board/solver.py` to understand `boardChannelLaneCounts_build()` —
   this is where `channelLaneCounts` comes from.
3. Run `python -m pytest tests_symbolic/ -q` — confirm 18/18 baseline.

### What to add to `WiringSolution`

See `agentic/PLAN.md` Phase W1 for the full specification.

Critical summary:

1. Add `channelLaneCounts: dict[str, int]` — **required constructor parameter**.
   This comes from `boardChannelLaneCounts_build(board)` in `board/solver.py`.
   Maps channel names like `"eLong"` to their board capacity (e.g., `10`).

2. Add `_laneCount: int = 0` field — incremented explicitly in `wire_add()`.

3. Add `kernel_wiring: list[str] = []` field — populated by `wire_add()` as
   `f"{source} -> {sink}"` strings.

4. Add `laneMap_get(wireIndex: int) -> dict[sfN, int]`:
   - `FORWARD` hops: `wireIndex + 1`
   - `REVERSE` hops: `channelLaneCounts[hop.area.channel_name] - wireIndex`
   - `FIXED` hops: excluded from the dict
   **Use channel capacity for REVERSE, not `_laneCount`.** This is the most
   important correctness constraint. See HANDOFF.md for why.

5. Update `wire_add(source, sink)`:
   - appends `AlgebraicPath` to `_paths`
   - appends `f"{source} -> {sink}"` to `kernel_wiring`
   - increments `_laneCount`

6. Add `laneCount_get() -> int`.

### After Phase W1

Write the tests described in PLAN.md Phase W1b. Then run all 18 tests.
If 18/18 pass and new tests pass, commit and move to Phase W2.

Phase W2 touches `board/solver_runtime.py`. Read it fully before starting.

## Things Not To Do

- do not touch `board/` files until Phase W1 and W1b tests are complete
- do not revive stale `rearch-zone-grid` milestone assumptions
- do not use broad rewrites — surgical changes only
- do not start world-scale `extra` routing algebra (Phase 3) until WiringSolution
  consolidation is complete
- do not recreate module-level `wteIntra`/`etwIntra` singletons — they were
  deliberately removed; `BoardSolver` constructs fresh instances per solve
