# SignalFlow Routing Breakage Report

**Date:** March 25, 2026
**Status:** MILESTONE 2 IN PROGRESS — 1-ROW BOUNDARY ISSUE BLOCKING

The four physics violations from the original rescue mission are **fixed**.
The remaining failures are Milestone 2 substrate-unification work.

---

## Resolved (Milestone 1 — March 25, 2026)

### ✅ Physics Violation 1: Wrong Travel Rows
`kernel_solver.py` used `INTRA_ROUTING_LATITUDE NORTH/SOUTH` regions for travel row
calculation. These belong to the Intra kernel, not seam kernels. Fixed: use the first
`INTRA_ROUTING_LONGITUDE` or `INTER_ROUTING_LONGITUDE` region's `verticalStart`.

### ✅ Physics Violation 2: Wrong Seam Wall Sides
`interconnect_solver.py` hardcoded `CHIP_TERMINAL EAST/WEST` for all seams regardless
of axis. Fixed: detect axis via `interconnect.interconnectAxisResult_get()`, then use
`SOUTH/NORTH` for VERTICAL (NTS) seams.

### ✅ Physics Violation 3: INTRA Bands in Mega-Kernel
`latN`/`latS` (INTRA_ROUTING_LATITUDE) were included in `megaRegions`. INTRA latitude
bands do not belong in seam kernels. Fixed: `megaRegions` now has exactly 7 items
(`[srcWall, srcFan, srcTravel, seam, dstTravel, dstFan, dstWall]`).

### ✅ Physics Violation 4: Source Fan Peel Direction
`isWestSide=wallSrc.side==WEST` evaluated to `False` for the EAST source fan, giving the
northernmost wire the outermost (longest) peel column. This caused the northernmost wire's
P1→P2 horizontal to cross all inner wires' P2→P3 peel verticals. Fixed: always pass
`isWestSide=True` for the source fan, so the northernmost wire gets the leftmost (innermost,
shortest P1→P2) peel.

---

## Resolved (Milestone 2 — In Progress, March 25, 2026)

### ✅ Zone Solver Shunt Removed
INTRAZONE obligations now route through `zone.intraKernel` via
`routingKernelSolvedRouteSetResult_build`. Attachment-policy lane indices (`FROM_END` for
west-side sources) are threaded through `KernelObligation.laneIndex`.

### ✅ kernel_solver.py Rewritten (Longitude-Based Peel Columns)
Replaced the broken `fanAssignments_build` approach with direct longitude arithmetic:
- `fwd_peel_left = longW_start + 2*laneIdx`, `fwd_peel_right = longE_end - 2*laneIdx`
- `ret_peel_left = longW_start + (2*laneIdx+1)`, `ret_peel_right = longE_end - (2*laneIdx+1)`
- Travel rows: `latN_end - 2*laneIdx` (fwd), `latS_start + (2*laneIdx+1)` (ret)
- Return routes correctly swap src/dst (callee → caller direction)
Result: 8/13 zone solver tests now pass (was 0/13 for the hub-related tests).

### ✅ Debug Context Tests Fixed (22 tests)
All `__dir__` methods in `debug.py` reordered alphabetically. Short RPN alias methods
added to `DebugRouteView`. `_ReplPs1.render()` strips ANSI codes.

---

## Residual: Blocking Issue (Milestone 2)

### 1. 1-Row Boundary Discrepancy in `r_d` Formula (5 tests blocked)
- The `r_d` formula in `kernel_solver.py` computes row 45 for the 5th proxy chip
  (orderIndex=4), but `FAN_IN_OUT EAST` only covers rows 5..44.
- Expected with `dstChipH=6`: `r_d = 5 + 4*(6+2) + 4 = 41`. Actual computed: 45.
- This implies `dstChipH` is being fetched as 7 (not 6) inside the solver, OR the
  zone terminal region is sized 1 row short of where chips actually land.
- **Next step:** Add debug print in solve loop; verify `len(chipDrawLines_build(chip))`
  for the chip fetched via `chipResult_get` vs direct iteration over `chipSet.chips`.
- **Tests blocked:** hub coincidence, hub cells-in-regions, hub west-long-strips,
  hub monotone-packing, asymmetric-fanout cells-in-regions.

### 2. Ghost Set / Dual Storage
- `RoutingZone` still holds a legacy monolithic `routingZoneRegionSet` alongside the
  5 internal kernels.
- Can be deleted once the 1-row boundary issue is resolved and zone solver tests pass.

### 3. Remaining Pre-Existing Test Failures (~12 tests)

| Category | Count | Root Cause |
|----------|-------|------------|
| Routing zone model validation | 2 | `routingZone_rejects_*` — validation doesn't reject bad input |
| Circuit document canonicalization | 1 | `chipIoInput.explicit` returns None instead of True |
| Assignment / obligations | 5 | `circuitDocumentResult` fails before routing layer |
| Engine boundary / render | 3 | World canvas rendering issues |

### 4. Orthogonal Crossings (Accepted Design — Not a Bug)
In monotone ribbon packing, straight-through wires (srcRow==dstRow) cross peel verticals
of wires routing to northward travel rows. This is geometrically unavoidable and valid
in ASCII art (drawn as `+`). Test 4 uses `allow_orthogonal_crossings=True` deliberately.

---

## Instructions for Next Agent

See `PLAN.md` Milestone 2 and `ZEROSHOT.md` for full context. Next steps in order:

1. Resolve the 1-row `r_d` boundary discrepancy (see ZEROSHOT.md for investigation steps).
2. Once all 13 zone solver tests pass, delete `RoutingZone.routingZoneRegionSet`.
3. Fix the ~12 remaining pre-existing failures (start with assignment/obligations).
4. Do not introduce new ruff violations. Run `ruff check` on every changed file.
