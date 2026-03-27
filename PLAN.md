# SignalFlow Execution Plan: Kernel-Crossbar Realization

**Date:** March 27, 2026
**Status:** MILESTONE 1 COMPLETE — MILESTONE 2 COMPLETE — MILESTONE 3 IN PROGRESS (566/0)
**Baseline:** See `BREAKAGE.md` for the residual debt still to be cleared.

---

## Milestone 1: Rescue Mission (Physics & Invariants) ✅ COMPLETE

*Goal: Fix the atomic kernel so it respects the visual map and stops colliding.*

1. **✅ Corridor-Aware Peel Column Logic (`fan_solver.py`)**
2. **✅ Correct Travel Row Assignment (`kernel_solver.py`)**
3. **✅ Correct Seam Wall Sides (`interconnect_solver.py`)**
4. **✅ Clean Mega-Kernel (`interconnect_solver.py`)**

**Test Gate:** `pytest tests/test_rearch_interconnect_solver.py` → **4/4 PASS**

---

## Milestone 2: Substrate Unification (The Cutover) ✅ COMPLETE

*Goal: Delete the legacy solver and the redundant region storage.*

1. **✅ Remove the zone_solver.py shunt** — INTRAZONE obligations now delegate to
   `zone.intraKernel` via `routingKernelSolvedRouteSetResult_build`. Attachment-policy
   lane indices (`FROM_END` for west-side sources) threaded through `KernelObligation.laneIndex`.

2. **✅ Fix debug context test failures (22 tests)**

3. **✅ kernel_solver.py rewritten with longitude-based peel columns**

4. **✅ Resolve boundary discrepancy + collision fixes (v5.9.0):**
   - `destinationPortIndex` fixed: now per-destination chip rank counter (not
     `childCallIndex`). Corrects fan-in row placement for process() and fan-out
     for all WTE intrazone routes.
   - East peel parity fix: forward uses odd offsets (`longE_start + 2k+1`), return
     uses even (`longE_start + 2k`). Eliminates self-collision where forward corner
     and return horizontal shared E direction.
   - Removed obsolete test 4 (monotone packing compacts hub ribbon).
   - **Suite: 566/0.**

5. **✅ Delete the ghost set (`RoutingZone.routingZoneRegionSet`)** — 13 files
   changed; dispatcher functions replace all direct field access.

6. **✅ Fix ~12 remaining pre-existing test failures** — Suite: 566/0.

---

## Milestone 3: Functional Symmetry (Expansion)

*Goal: Apply the kernel to all remaining routing problems. See `KERNEL-ROUTING-VISION.md`.*

### Completed

- **✅ REPL `workflows` namespace:** `chipGeometryPush_run()`, `zonesNormalize_run()`,
  `zoneRecalculate_run()` implemented.
- **✅ Rule 1B:** `crossbarDim = max(2, intraLaneSpan)` — demand-driven crossbar.
- **✅ NTS zone solver tests (3):** single-call pair, N=3 hub no-collision, N=3
  distinct east peel columns.
- **✅ NTS N≥3 peel-column fix:** single-step column spacing avoids source-port
  collision.
- **✅ NTS seam test (converging lanes):** verifies distinct lanes and no shared
  realized cells for NTS multi-source vertical seam.

### In Progress / Open

8. **🚧 Chip-internal kernel** — Replace `_chipInternalRoutePointsResult_build` in
   `route.py` with a kernel solve over the chip's own region geometry. This is the
   **highest-leverage next step**: it unblocks process() fan-in display and eliminates
   explicit `internal_wiring` YAML directives for the common transverse case. Directive
   parsing in `chip_solver.py` stays; only the route realization changes.

9. **🚧 NTS intra kernel** — Port `_ntsRoutePairResult_build` to emit
   `KernelObligation` and call `routingKernelSolvedRouteSetResult_build` with
   NORTH/SOUTH terminal walls.

10. **🚧 Seam kernels (EAST-to-seam + seam-to-WEST)** — Replace
    `interconnect_solver.py` per-case logic with two kernel instances per seam.
    See `KERNEL-ROUTING-VISION.md` for decomposition rationale.

11. **🚧 Backedge + same-side degenerate kernels** — Replace
    `_wteRoutePairResult_build` and `_sameSideLocalRouteResult_build`.

12. **🚧 Dead code removal** — Delete from `zone_solver.py`:
    `_wteBundleWindowRoutesResult_build`, `_routeMayOccupyCellsCheck`,
    `_routeOccupancy_commit`, `_wteStripKeys_build`, `_laneTriplesInPackingOrder_build`,
    `_laneWindowsInSenseOrder_build`, `_routeLengthScore_calculate`.

13. **🚧 Final renderer visual gate:** `ke.kernel_routesDraw()` / `kw.kernel_routesDraw()`.

---

## Current Success Criteria

- [x] `pytest tests/test_rearch_interconnect_solver.py` passes 4/4
- [x] No new ruff violations introduced
- [x] `zone_solver.py` shunt removed; INTRAZONE routes via `intraKernel`
- [x] Debug context test failures (22) fixed
- [x] `kernel_solver.py` rewritten and collision-free (v5.9.0 parity fix)
- [x] `destinationPortIndex` correct for fan-out and fan-in
- [x] `RoutingZone.routingZoneRegionSet` ghost set deleted
- [x] All pre-existing failures fixed (suite: 566/0)
- [ ] Chip-internal kernel replaces `chip_solver.py` route realization
- [ ] NTS intra via kernel_solver
- [ ] Seam kernels replace `interconnect_solver.py`
- [ ] Dead code purged from `zone_solver.py`
- [ ] Visual gate: `ke.kernel_routesDraw()` no tunneling
