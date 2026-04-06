# SignalFlow Execution Plan: World-Scale `extra` Routing + WiringSolution Consolidation

**Date:** April 2026
**Branch:** `worldscale-extra-routing`
**Version:** `5.9.16`
**Status:** geometry centralization complete; notation/ package built; WiringSolution consolidation in progress

---

## Phases 1–2b: COMPLETE (geometry centralization)

See `agentic/HANDOFF.md` for full history. Geometry centralization is done:
- `boardGeometryConfig` singleton owns all policy defaults
- `BoardGeometrySpec` + `RingGeometrySpec` are the canonical span knob objects
- `ZoneSymbolicInvariants` derives circuit-driven and placement-lifted minimums
- Solver (`routing/placement.py`) reads all intra policy floors from config at call time

---

## Immediate Work: WiringSolution Consolidation

**Why this exists:** The wiring pipeline has five representations of one wire,
with lane integers embedded in strings and parsed back out. See
`papers/brittle_patterns.adoc` for the diagnosis. This consolidation makes
`WiringSolution` the authoritative single source of truth for wire connections
and lane assignment.

**Current state:** `notation/path.py` has `WiringSolution` partially built.
`WTE_INTRA_FORWARD` and `WTE_INTRA_RETURN` are complete topology constants.
Lane-integer computation, `kernel_wiring`, and `laneMap_get()` are missing.

### Phase W1: Extend `WiringSolution` — `notation/path.py`

**This is the only file to touch in this phase.**

Add to `WiringSolution`:

1. `kernel_wiring: list[str]` — wire connections as
   `"module.fn.signal -> module.fn.signal"` strings. This is the upstream-provided
   list of what must be connected. Populated by `wire_add()` or `wiring_add()`.

2. `_laneCount: int = 0` — explicit integer state, incremented in `wire_add()`.
   Do not use `len(self._paths)` — make it explicit.

3. `channelLaneCounts: dict[str, int]` — per-channel lane capacities from the
   board. **CRITICAL: this must be set before `laneMap_get()` is called.**
   Source is `boardChannelLaneCounts_build()` in `board/solver.py`.
   Add as a required constructor parameter or via a `channelLaneCounts_set()`
   method called by `BoardSolver` before wires are added.

4. `laneMap_get(wireIndex: int) -> dict[sfN, int]` — returns the per-channel
   concrete lane for wire at position `wireIndex` in this bundle.

   **Implementation — this is the critical part:**
   ```python
   def laneMap_get(self, wireIndex: int) -> dict[sfN, int]:
       result: dict[sfN, int] = {}
       for hop in self.topology.topology_get():
           if hop.laneSense is LaneSense.FIXED:
               continue
           if hop.laneSense is LaneSense.FORWARD:
               result[hop.area] = wireIndex + 1
           else:  # REVERSE
               # Use channel capacity, NOT bundle size.
               # e.g. for sfN.Ei: channelLaneCounts["eLong"] - wireIndex
               channelName = hop.area.channel_name
               capacity = self.channelLaneCounts.get(channelName, self._laneCount)
               result[hop.area] = capacity - wireIndex
       return result
   ```

   **Why channel capacity not bundle size:** The existing solver computes
   `eastLaneIndex = eLongCount - forwardIndex + 1` where `eLongCount` is the
   board's east channel capacity (e.g. 10), not the number of wires (e.g. 5).
   Tests assert `eLong[10]` for the first wire of a 5-wire bundle on a 10-lane
   board. Using `_laneCount` would produce `eLong[5]` — wrong and silent.

5. Update `wire_add(source, sink)` to also append `f"{source} -> {sink}"` to
   `kernel_wiring` and increment `_laneCount`.

6. Add `laneCount_get() -> int` — returns `_laneCount`.

**After this phase:** Run `python -m pytest tests_symbolic/ -q`. All 18 must pass.
`WiringSolution` tests do not exist yet — add them in Phase W1b below.

### Phase W1b: New Tests For WiringSolution

Add to `tests_symbolic/test_symbolic_kernel_quarantine.py` or a new file:

1. `test_wiring_solution_forward_lane_map` — for a 5-wire `WTE_INTRA_FORWARD`
   bundle on a 10-lane board: wire 0 → `{sfN.Wi: 1, sfN.Ni: 1, sfN.Ei: 10}`;
   wire 4 → `{sfN.Wi: 5, sfN.Ni: 5, sfN.Ei: 6}`.

2. `test_wiring_solution_return_lane_map` — for `WTE_INTRA_RETURN`, all three
   routing hops have `FORWARD` sense, so no reversal. Wire 0 → `{sfN.Ei: 1,
   sfN.Si: 1, sfN.Wi: 1}`.

3. `test_wiring_solution_lane_count_explicit` — verify `_laneCount` increments
   and is independent of `len(paths)`.

4. `test_wiring_solution_is_per_instance_not_shared` — two separate
   `WiringSolution` instances do not share `_paths` or `_laneCount`.

### Phase W2: `BoardSolvedWire` — `board/solver_runtime.py`

**Read the full file before touching anything.**

`BoardSolvedWire` currently stores:
```python
algebraicPathText: str  # "App.ts.main().s1::wf[0]::wLong[1]::..."
```

Replace with:
```python
algebraicPath: AlgebraicPath   # topology-only, no lane integers
wireIndex: int                 # position in bundle for laneMap_get()
wiringSolution: WiringSolution # owning bundle
```

Add a property that preserves backward compatibility for all existing call sites:
```python
@property
def algebraicPathText(self) -> str:
    laneMap = self.wiringSolution.laneMap_get(self.wireIndex)
    parts: list[str] = [self.algebraicPath.source]
    for hop in self.algebraicPath.hops:
        token = hop.area.channel_name or ""
        if hop.laneSense is LaneSense.FIXED:
            parts.append(f"{token}[0]")
        else:
            lane = laneMap.get(hop.area, 0)
            parts.append(f"{token}[{lane}]")
    parts.append(self.algebraicPath.sink)
    return "::".join(parts)
```

Update `BoardSolver.solution_get()` to:
1. Call `boardChannelLaneCounts_build(board)` once
2. Construct a `WiringSolution(topology=..., channelLaneCounts=...)` for forward
   wires and one for return wires
3. Call `wiringSolution.wire_add(source, sink)` for each wire in order
4. Produce `BoardSolvedWire(algebraicPath=..., wireIndex=i, wiringSolution=...)`

The topology selection depends on `rotationSense`:
- `CLOCKWISE` → forward: `WTE_INTRA_FORWARD` (Ni latitude); return: `WTE_INTRA_RETURN` (Si)
- `ANTICLOCKWISE` → forward: south-bend topology (Si); return: north-bend (Ni)

**After this phase:** Run full test suite. The `algebraicPathText` property must
produce identical strings to the old f-string. If tests fail, the property is wrong.

### Phase W3: `realizer.py` — structured entry point

**Read the full file before touching anything.**

`algebraicRouteRealization_build()` currently parses the string with:
```python
re.fullmatch(r"([A-Za-z]+)\[(\d+)\]", channelToken)
```

Add a parallel structured entry point:
```python
def algebraicRouteRealization_buildFromPath(
    algebraicPath: AlgebraicPath,
    laneMap: dict[sfN, int],
    sourceAttachPoint: ...,
    destinationAttachPoint: ...,
    regionFramesByName: dict[str, ...],
) -> AlgebraicRouteRealization:
```

Keep the existing string-based `algebraicRouteRealization_build()` as a shim —
it calls `AlgebraicPath.fromText_build()` then the structured version.

Also add `realizationPlan_buildFromPaths()` parallel to `realizationPlan_build()`.

Do NOT delete the string shim yet. `engine/debug.py` still uses it.

**Hardcoded 7-token assumption (Risk 2):** The realizer checks
`len(pathTokens) != 7` and bails silently. The structured entry point should
dispatch on hop count and hop sequence, not a magic number. Handle this.

### Phase W4: `materialized_runtime.py` — replace string parse sites

**Read the full file before touching anything. It is large.**

There are three parse sites:

1. `materializedSolution_build()` — parses `algebraicPathText.split("::")` to
   get source/sink. Replace with `solvedWire.algebraicPath.source` / `.sink` directly.

2. `_collisionReport_build()` — parses tokens to build symbolic claim strings
   like `"wLong[3]"`. Replace with:
   ```python
   laneMap = solvedWire.wiringSolution.laneMap_get(solvedWire.wireIndex)
   for hop in solvedWire.algebraicPath.hops:
       if hop.laneSense is LaneSense.FIXED:
           token = f"{hop.area.channel_name}[0]"
       else:
           token = f"{hop.area.channel_name}[{laneMap[hop.area]}]"
   ```
   The output token strings MUST be identical to what the old parser produced.
   Tests assert exact collision token formats.

3. `_materializedPath_build()` — calls `algebraicRouteRealization_build()` with
   the string. Replace with `algebraicRouteRealization_buildFromPath()`.

### Phase W5: `solver.py` — demote to serializer

`boardWireAlgebraicPath_build()` currently owns all lane computation. After
Phase W2, `WiringSolution.laneMap_get()` owns it. Demote this function to a
thin serializer that calls `WiringSolution.laneMap_get()` and formats the string.

The goal: `boardWireAlgebraicPath_build()` should have no lane arithmetic of its
own. It should ask the `WiringSolution` for the lane map and format it.

Keep the function signature unchanged for now — callers in `solver_runtime.py`
and elsewhere do not change until all phases are complete.

### Phase W6: `engine/debug.py` — deferred

`engine/debug.py` is 3900+ lines with its own parallel type hierarchy
(`DebugKernelSolvedWire`, `DebugKernelSolutionHandle`). Two parse sites at
lines ~3864 and ~3905 that parse `algebraicPathText`.

This is the largest and riskiest file. Do not touch it until Phases W1–W5 are
stable and all 18 tests pass. Keep the string shim alive in `realizer.py`
specifically to support `debug.py` during the transition.

### Phase W7: Clean up

After all parse sites are replaced and tests pass:
- Remove the string shims in `realizer.py`
- Remove `boardWireAlgebraicPath_build()` or mark it deprecated
- Update module docstrings
- Consider `KernelObligation.laneIndex` — it is a ghost field (always 0).
  Leave it for now; it belongs to the legacy routing path, not the board path.

---

## Phase 3: Symbolic Algebra Across `intra` And `extra`

**Status: not started. Do not start until WiringSolution consolidation is complete.**

Goal: describe routes that leave `intra`, travel in `extra`, and re-enter.

1. Describe child-to-parent routing in `sfN`.
2. Describe child-to-self routing in `sfN`.
3. Describe world-scale long-haul routing in `sfN`.
4. Identify where row/layer identity must be preserved across the `extra` perimeter.

Hard unresolved: child-to-self routing. A route leaving `p4()` into `extra`
must preserve enough row/layer identity to return specifically to `p4()`, not
to the parent-facing side of the zone. Do not hand-wave this.

Deliverable: explicit route narratives documented before any solver code.

---

## Phase 4: Reconcile `extra` With World Construction

Goal: determine how local kernels compose at world scale.

Deliverable: world-construction doctrine note in `docs/worldscale_geometry.adoc`.

---

## Phase 5: Runtime Introduction

Goal: only after doctrine is explicit, introduce runtime changes for `extra`.

Deliverable: runtime changes backed by geometry and snippet evidence.

---

## Required Pass Order

For any new agent starting WiringSolution work:

1. Read `agentic/HANDOFF.md`
2. Read `agentic/NON-NEGOTIABLES.md`
3. Read `notation/path.py` fully — understand current `WiringSolution` state
4. Read `board/solver.py` — understand `boardChannelLaneCounts_build()` and
   current lane arithmetic
5. Run `python -m pytest tests_symbolic/ -q` — verify 18/18 baseline
6. Start Phase W1 — extend `WiringSolution` only
7. Verify tests still pass
8. Only then proceed to Phase W2
