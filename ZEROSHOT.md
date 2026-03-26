# Zero-Shot Handoff: SignalFlow Routing — Kernel Solver Rewritten, 1-Row Boundary Blocking

This file is the fresh-context handoff for the next agent.
**STATUS: MILESTONE 2 IN PROGRESS — SHUNT REMOVED, KERNEL SOLVER REWRITTEN, 1-ROW GAP REMAINING**

Milestone 1 (Rescue Mission) is **complete**. Milestone 2 (Substrate Unification) is
partially complete: the zone_solver.py shunt has been removed, the debug context tests
are fixed, and the kernel_solver.py has been rewritten with correct longitude-based peel
columns. One blocking issue remains before Milestone 2 can close.

---

## What Was Done This Session (March 25, 2026)

### 1. Debug Context Tests Fixed (22 tests — now all pass)
All `__dir__` methods in `src/signalflow/engine/debug.py` reordered alphabetically.
Short RPN alias methods added to `DebugRouteView`. Additional fixes:
- `_ReplPs1.render()` now strips ANSI codes for plain-text output
- `DebugChipView.chipByTitle_get` now validates chip existence via `_chipHandle_build`

### 2. Zone Solver Shunt Removed
`zone_solver.py` no longer delegates INTRAZONE obligations to the legacy solver.
INTRAZONE routing now goes through `zone.intraKernel` via
`routingKernelSolvedRouteSetResult_build`. The attachment-policy lane index assignment
(`FROM_END` for west-side sources) is wired through `KernelObligation.laneIndex`.

### 3. kernel_solver.py Rewritten
The kernel solver now uses **longitude-based peel columns** matching the legacy solver
geometry exactly:
- `fwd_peel_left  = longW_start + 2 * laneIdx`
- `fwd_peel_right = longE_end   - 2 * laneIdx`
- `ret_peel_left  = longW_start + (2 * laneIdx + 1)`
- `ret_peel_right = longE_end   - (2 * laneIdx + 1)`
- Travel rows: `latN_end - 2*laneIdx` (forward) and `latS_start + (2*laneIdx+1)` (return)
- Return routes correctly swap `sourceChipRef`/`destinationChipRef` (callee → caller)
- `fanAssignments_build` no longer used (removed from import)

---

## Current Test Status

```
pytest tests/test_rearch_zone_solver.py        →  8 passed, 5 failed (down from 13 failed)
pytest tests/test_rearch_debug_context.py      →  all passing (was 22 failed)
pytest (full suite, approximate)               →  ~540 passed, ~12 failed
```

---

## Blocking Issue: 1-Row Boundary Discrepancy

The 5 remaining zone solver failures are all in the hub and asymmetric-fanout fixtures.
Symptom: route cells escape declared region boundaries by exactly 1 row.

Example: `main() -> p5() at (col=66, row=45)` — but `FAN_IN_OUT EAST` covers rows 5..44.
The route's computed `r_d = 45` lands just past the terminal boundary.

**Root cause (unresolved):** The `r_d` formula:
```python
r_d = wallDst.routingZoneRegionFrame.verticalStart
      + dstP.orderIndex * (dstChipH + 2) + 1 + _HEADER + 2 * destinationPortIndex
```
is computing `r_d = 45` for the 5th proxy chip (orderIndex=4) when `chipDrawLines_build`
returns height=6 for proxy chips. Expected: `5 + 4*(6+2) + 4 = 41`. Actual: 45.
The discrepancy implies the chip height fetched at solve time is 7, not 6 — or the
terminal region is 1 row too small for the actual chip layout.

**The two candidate fixes (one needs investigation first):**
1. `chipResult_get` returns a chip object that `chipDrawLines_build` measures differently
   than the direct `chips` list iteration. Verify what height is actually fetched.
2. The zone terminal region is undersized by N rows (zone sizing formula in
   `_zoneMetrics_build` doesn't account for chip body + spacing correctly).

**How to investigate:**
```python
# Inside kernel_solver.py solve loop, add:
print(f"dstChipH={dstChipH} orderIndex={dstP.orderIndex} r_d={r_d} termEnd={wallDst.routingZoneRegionFrame.verticalEnd_calculate()-1}")
```

---

## Remaining Pre-Existing Failures (~12 tests)

| Category | Count | Root Cause |
|----------|-------|------------|
| Routing zone model validation | 2 | `routingZone_rejects_*` — bad-input rejection broken |
| Circuit document canonicalization | 1 | `chipIoInput.explicit` returns None instead of True |
| Assignment / obligations | 5 | `circuitDocumentResult` fails before routing layer |
| Engine boundary / render | 3 | World canvas rendering issues |

These were pre-existing before Milestone 2 started. Fix order: assignment/obligations
first (they likely gate the others).

---

## Key Files

- `src/signalflow/routing/kernel_solver.py` — Longitude-based peel columns (rewritten)
- `src/signalflow/routing/zone_solver.py` — Shunt removed; routes via `intraKernel`
- `src/signalflow/engine/debug.py` — All `__dir__` fixed; alias methods added
- `src/signalflow/models/routing_zone.py` — `KernelObligation.laneIndex` field added
- `tests/test_rearch_zone_solver.py` — 8/13 passing; 5 hub/asymfanout still blocked
- `tests/test_rearch_debug_context.py` — all passing
- `PLAN.md` — Milestone roadmap (M1 done, M2 in progress)
- `CONTEXT.md` — Architecture overview
- `NON-NEGOTIABLES.md` — Hard physics gates

---

## What NOT to Redo

- Do NOT reintroduce `fanAssignments_build` into `kernel_solver.py`.
- Do NOT reintroduce the `rowsSrc`/`rowsDst` pre-computation arrays.
- Do NOT restore the zone_solver.py shunt to the legacy solver.
- The `laneIndex` field on `KernelObligation` is intentional and needed.
