# Zero-Shot Handoff: SignalFlow Routing — v5.9.0, 566/0, Kernel Next Steps

**Branch:** `rearch-zone-grid` | **Commit:** 816fbd6 | **Suite:** 566 passed, 0 failed

Milestones 1 and 2 are **complete**. Milestone 3 (Functional Symmetry / Expansion)
is in progress. The kernel solver covers WTE intrazone WEST→EAST routes. The next
priority is extending kernel coverage to chip-internal routing and seam routing.

---

## What Was Done (This Arc — March 2026)

### 1. Milestones 1 & 2 Completed (see PLAN.md for full detail)
- Rescued physics invariants (corridor-aware peel columns, travel rows, seam walls)
- Removed zone_solver.py shunt — INTRAZONE routes now via `routingKernelSolvedRouteSetResult_build`
- Fixed all ~12 pre-existing failures; suite went from ~550/12 to 566/0
- Deleted `RoutingZone.routingZoneRegionSet` ghost set; added dispatcher functions

### 2. kernel_solver.py East-Peel Parity Fix (v5.9.0)
Eliminated self-collision at east peel columns by swapping parity:
- Forward uses **odd** offsets: `fwd_peel_right = longE_start + 2*laneIdx + 1`
- Return uses **even** offsets: `ret_peel_right = longE_start + 2*laneIdx`

This ensures `fwd_peel_right > ret_peel_right` for every lane so the forward
destination corner always lands **outside** the return horizontal span.

### 3. destinationPortIndex Fix (v5.9.0)
`zone_solver.py` was passing `destinationPortIndex=obligation.childCallIndex` (wrong
for fan-out — caused increasing row displacement). Now uses a per-destination chip
rank counter: each obligation gets the rank of its destination chip ref among all
obligations sharing that destination (0 for fan-out, 0..N-1 for fan-in).

### 4. KERNEL-ROUTING-VISION.md Created
Documents the goal (all routes via kernel_solver), current coverage gaps, migration
sequence, and the EAST-to-seam / seam-to-WEST decomposition rationale.

---

## Current Kernel Solver Coverage

`kernel_solver.py` handles **WTE intrazone WEST→EAST** only.

| Routing context | Solver today | Kernel? |
|---|---|---|
| WTE intrazone WEST→EAST | `kernel_solver.py` | ✅ |
| WTE backedge (EAST→WEST) | `_wteRoutePairResult_build` (legacy, active) | ❌ |
| WTE same-side self-call | `_sameSideLocalRouteResult_build` | ❌ |
| NTS intrazone | `_ntsRoutePairResult_build` | ❌ |
| Seam-crossing | `interconnect_solver.py` | ❌ |
| Grid long-haul | `grid_solver.py` | ❌ |
| Chip-internal wiring | `chip_solver.py` (directive-based) | ❌ |

Dead code in `zone_solver.py` (never called, safe to delete):
`_wteBundleWindowRoutesResult_build`, `_routeMayOccupyCellsCheck`,
`_routeOccupancy_commit`, `_wteStripKeys_build`, `_laneTriplesInPackingOrder_build`,
`_laneWindowsInSenseOrder_build`, `_routeLengthScore_calculate`.

---

## Next Priorities

### 1. Chip-Internal Kernel (highest leverage)
`chip_solver.py` currently parses `internal_wiring` directives and produces
`ChipInternalSolvedRoute` records. Route realization then calls
`_chipInternalRoutePointsResult_build` in `route.py` using ad-hoc manifold/detour
geometry. Replace with a kernel solve over the chip's own region geometry:
- WEST terminal wall = input ports (signal in, return out)
- EAST terminal wall = output ports (signal out, return in)
- Routing bands derived from chip bounding box

This unblocks process() fan-in display: 5 routes arrive at process()'s WEST wall
from zone(2,1); the chip-internal kernel routes each across to its output port.
Directive parsing in `chip_solver.py` stays (it classifies intent); only the solve
output changes.

### 2. NTS Intra Kernel
Port `_ntsRoutePairResult_build` to emit `KernelObligation` and call
`routingKernelSolvedRouteSetResult_build` with NORTH/SOUTH terminal walls.

### 3. Seam Kernels (EAST-to-seam + seam-to-WEST)
Replace `interconnect_solver.py` per-case logic. Each seam crossing becomes two
kernel calls sharing the seam coordinate as handoff. Lane index established at
obligation-dispatch time and threaded through both calls. See `KERNEL-ROUTING-VISION.md`.

### 4. Backedge + Same-Side Degenerate Kernels
Replace `_wteRoutePairResult_build` and `_sameSideLocalRouteResult_build`.

### 5. Dead Code Removal
Delete the obsolete functions listed above from `zone_solver.py`.

---

## What NOT to Redo

- Do NOT reintroduce `fanAssignments_build` into `kernel_solver.py`.
- Do NOT reintroduce `rowsSrc`/`rowsDst` pre-computation arrays.
- Do NOT restore the zone_solver.py shunt to any legacy solver.
- Do NOT change `destinationPortIndex` back to `childCallIndex`.
- `laneIndex` on `KernelObligation` is intentional; `FROM_END` gives reversed lane order
  for west-side sources (innermost chip gets smallest laneIdx).

---

## Key Files

| File | Purpose |
|---|---|
| `src/signalflow/routing/kernel_solver.py` | WTE intra kernel (longitude peel, parity-correct) |
| `src/signalflow/routing/zone_solver.py` | Dispatches to kernel; legacy backedge path still active |
| `src/signalflow/routing/chip_solver.py` | Chip-internal directive parsing (realization TBD) |
| `src/signalflow/routing/interconnect_solver.py` | Seam-crossing routes (to be replaced) |
| `tests/test_rearch_zone_solver.py` | 15/15 passing |
| `KERNEL-ROUTING-VISION.md` | Full vision + migration plan |
| `PLAN.md` | Milestone roadmap |
| `NON-NEGOTIABLES.md` | Hard physics gates — read before any routing change |
