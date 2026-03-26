# SignalFlow Execution Plan: Kernel-Crossbar Realization

**Date:** March 25, 2026
**Status:** MILESTONE 1 COMPLETE — MILESTONE 2 NEXT
**Baseline:** See `BREAKAGE.md` for the residual debt still to be cleared.

---

## Milestone 1: Rescue Mission (Physics & Invariants) ✅ COMPLETE

*Goal: Fix the atomic kernel so it respects the visual map and stops colliding.*

All four physics violations were identified and fixed:

1. **✅ Corridor-Aware Peel Column Logic (`fan_solver.py`)**
   - `isWestSide=True` for the source fan: northernmost wire gets innermost (leftmost) peel.
   - Peel columns grow outward from the fan's inner edge, ensuring no early-column crossings.

2. **✅ Correct Travel Row Assignment (`kernel_solver.py`)**
   - Removed INTRA_ROUTING_LATITUDE dependency for travel rows (wrong region — belongs to Intra kernel).
   - Forward wires pack northbound from `lonRegion.verticalStart + i`.
   - Return wires pack southbound from `lonRegion.verticalEnd - 1 - i`.
   - Straight seams (`srcRow == dstRow`) short-circuit the longitude band entirely.

3. **✅ Correct Seam Wall Sides (`interconnect_solver.py`)**
   - Detect seam axis via `interconnect.interconnectAxisResult_get()`.
   - HORIZONTAL seam → `srcWallSide=EAST`, `dstWallSide=WEST`.
   - VERTICAL seam → `srcWallSide=SOUTH`, `dstWallSide=NORTH`.

4. **✅ Clean Mega-Kernel (`interconnect_solver.py`)**
   - INTRA_ROUTING_LATITUDE bands removed from `megaRegions` (7 items, not 9).
   - `latN`/`latS` fetch and guard removed entirely.

**Test Gate:** `pytest tests/test_rearch_interconnect_solver.py` → **4/4 PASS**

---

## Milestone 2: Substrate Unification (The Cutover) — IN PROGRESS

*Goal: Delete the legacy solver and the redundant region storage.*

1. **✅ Remove the zone_solver.py shunt:**
   - INTRAZONE obligations now delegate to `zone.intraKernel` via
     `routingKernelSolvedRouteSetResult_build`.
   - Attachment-policy lane indices (`FROM_END` for west-side sources) threaded
     through `KernelObligation.laneIndex`.

2. **✅ Fix debug context test failures (22 tests):**
   - All `__dir__` methods alphabetically reordered in `debug.py`.
   - Short RPN alias methods added to `DebugRouteView`.
   - `_ReplPs1.render()` strips ANSI codes; `chipByTitle_get` validates chip existence.

3. **✅ kernel_solver.py rewritten with longitude-based peel columns:**
   - `fwd_peel_left = longW_start + 2*laneIdx`, `fwd_peel_right = longE_end - 2*laneIdx`
   - `ret_peel_left = longW_start + (2*laneIdx+1)`, `ret_peel_right = longE_end - (2*laneIdx+1)`
   - Travel rows: `latN_end - 2*laneIdx` (fwd) and `latS_start + (2*laneIdx+1)` (ret)
   - Return routes swap sourceChipRef/destinationChipRef (callee → caller direction)
   - `fanAssignments_build` no longer used or imported

4. **🚧 Resolve 1-row boundary discrepancy (BLOCKING):**
   - 5 hub/asymmetric-fanout tests still fail: route cells escape terminal region by 1 row.
   - Symptom: `r_d = 45` for proxy-4 but `FAN_IN_OUT EAST` ends at row 44.
   - Root cause: chip height fetched via `chipResult_get` in solver context may differ
     from the chips-list height (7 vs 6), OR terminal region is undersized.
   - Fix: verify `dstChipH` at solve time, then correct formula or zone sizing.

5. **Delete the ghost set (`RoutingZone.routingZoneRegionSet`):**
   - The monolithic legacy set is kept alive only for remaining legacy paths.
   - Once step 4 is resolved and zone solver tests pass, delete this field.
   - Update all lookups to use the 5 internal kernels directly.

6. **Fix ~12 remaining pre-existing test failures:**
   - Assignment/obligations (5): `circuitDocumentResult` fails before routing layer — fix first.
   - Engine/render (3): world canvas rendering issues.
   - Routing zone model validation (2): bad-input rejection broken.
   - Circuit doc canonicalization (1): `chipIoInput.explicit` returns None.

7. **Full-power kernel validation across the suite:**
   - Prove zero same-direction shared cells for all INTRAZONE solves.
   - Align remaining test assertions to real geometry (no stale expected values).

---

## Milestone 3: Functional Symmetry (Expansion)

*Goal: Apply the kernel to all remaining routing problems.*

1. **Chip Internal Wiring:** Replace `chip_solver.py` with an Embedded RoutingZone solve.
2. **North/South Seam Kernels:** Fully implement NTS seam routing in `interconnect_solver.py`.
3. **REPL `workflows` namespace:** Implement `workflows.chip_geometry_push()`, `workflows.zones_normalize()`.
4. **Rule 1B:** `_zoneMetrics_build` uses provisional terminal-count formula; needs
   chip-geometry-driven zone sizing + cascade re-solve.

---

## Current Success Criteria

- [x] `pytest tests/test_rearch_interconnect_solver.py` passes 4/4
- [x] No new ruff violations introduced
- [x] `zone_solver.py` shunt removed; INTRAZONE routes via `intraKernel`
- [x] Debug context test failures (22) fixed
- [x] `kernel_solver.py` rewritten with longitude-based peel columns
- [ ] 1-row `r_d` boundary discrepancy resolved; hub/asymfanout tests pass (5 remaining)
- [ ] `ke.kernel_routesDraw()` in zone(1,1) shows no tunneling (visual gate)
- [ ] `kw.kernel_routesDraw()` in zone(2,1) is contiguous with zone(1,1) neighbor
- [ ] `RoutingZone.routingZoneRegionSet` ghost set deleted
- [ ] All ~12 remaining pre-existing failures fixed
