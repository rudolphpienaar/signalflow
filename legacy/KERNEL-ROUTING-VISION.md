# Kernel Routing Vision

**Goal:** every route in the system — zone-local, seam-crossing, and chip-internal — is
solved by `kernel_solver.py`. No bespoke per-case solvers survive.

---

## Current Coverage (March 2026)

| Routing context | Solver today | Kernel? |
|---|---|---|
| WTE intrazone WEST→EAST (main signal path) | `kernel_solver.py` via `zone_solver.py` | ✅ |
| WTE backedge (EAST→WEST within zone) | `_wteRoutePairResult_build` (legacy) | ❌ |
| WTE same-side self-call | `_sameSideLocalRouteResult_build` | ❌ |
| NTS intrazone routing | `_ntsRoutePairResult_build` | ❌ |
| Seam-crossing (inter-zone) routes | `interconnect_solver.py` | ❌ |
| Grid-level long-haul | `grid_solver.py` | ❌ |
| Chip-internal wiring | `chip_solver.py` (directive-based) | ❌ |

The kernel currently covers exactly **one** case: the primary forward signal path
between chips in the same WTE zone (source on WEST wall, destination on EAST wall).

---

## What the Kernel Does

`routingKernelSolvedRouteSetResult_build` in `kernel_solver.py` receives:

- A `RoutingKernel` — a pre-built region geometry bundle (terminal walls, fan
  regions, longitude columns, latitude bands)
- A list of `KernelObligation` — each carrying a source chip placement, destination
  chip placement, lane index, and destination port index

It emits forward + return route pairs as 6-keypoint polylines:

```
wallSrc → peel_left → lat_row → peel_right → wallDst   (forward)
wallDst → peel_right → lat_row → peel_left → wallSrc   (return)
```

The geometry is collision-free by construction: west peels grow leftward by lane,
east peels alternate parity (forward=odd, return=even offset), latitude rows are
separated by lane.

---

## The Full Vision: Kernel Everywhere

Every routing segment is a wall-to-wall solve inside a rectangular region bundle.
The kernel's API is already generic enough: give it two terminal walls and a set of
routing bands; it produces planar, non-colliding polylines. The plan is to apply
this uniformly.

### Tier 1 — Chip-Internal Kernel

Process() (and all multi-port chips) currently uses `chip_solver.py` with
user-declared `internal_wiring` directives. The chip interior is a rectangle with
WEST and EAST (or NORTH/SOUTH) terminal walls — structurally identical to a zone
kernel. The kernel should solve it automatically:

- WEST wall terminals: input ports (signal in, return out)
- EAST wall terminals: output ports (signal out, return in)
- Routing bands: fan regions + longitude columns + latitude bands sized to the chip
  box

This eliminates explicit `internal_wiring` declarations for the common transverse
case. Same-side (loop) wiring is a degenerate case the kernel can also handle.

**Fan-in implication for process():** When p1..p5 all call process(), process()
receives 5 routes landing on its WEST terminal wall (one per input port). The
chip-internal kernel then routes each of those WEST inputs across to the
corresponding EAST output. This is a 5-lane intra-chip kernel solve — same
machinery, smaller rectangle.

### Tier 2 — Seam Kernels (Inter-Zone)

When a route crosses a zone boundary it currently goes through `interconnect_solver.py`.
The proposed decomposition is:

```
Zone(i) intra kernel          Seam kernel              Zone(i+1) intra kernel
[WEST chips → EAST wall]  →  [EAST wall → WEST wall]  →  [WEST wall → EAST chips]
                              └── two sub-kernels ──┘
                              EAST-to-seam + seam-to-WEST
```

**EAST-to-seam kernel:** routes from the EAST terminal region of zone(i) to the
seam midpoint. Its terminal walls are the zone's EAST chip wall and the seam
boundary. Its routing bands are the inter-zone FAN_IN_OUT and LONGITUDE regions
already present in the placed grid.

**Seam-to-WEST kernel:** routes from the seam midpoint to the WEST terminal region
of zone(i+1). Symmetric to the above.

Together these two kernels replace `interconnect_solver.py` for the WTE seam case.
The seam coordinate is the natural split point — each kernel is entirely within one
zone's spatial extent.

### Tier 3 — Backedge and Same-Side Kernels

WTE backedges (EAST→WEST within zone) and same-side self-calls are currently handled
by legacy functions. Both are structurally degenerate kernels:

- **Backedge:** source on EAST wall, destination on WEST wall — same kernel API,
  reversed terminal ordering.
- **Same-side:** source and destination on the same wall — kernel with a single
  terminal wall and a U-turn latitude band.

### Tier 4 — NTS Kernel

`_ntsRoutePairResult_build` already uses kernel-like column/row formulas. It should
be ported to emit `KernelObligation` and routed through `kernel_solver.py` with
NORTH/SOUTH terminal walls and vertical longitude bands.

---

## Migration Sequence

1. **Chip-internal kernel** — highest leverage, unblocks process() fan-in display.
   Replace `chip_solver.py` route realization with a kernel solve over the chip's
   own region geometry. Directive parsing in `chip_solver.py` stays (it classifies
   the wiring intent); the solver output changes.

2. **NTS intra kernel** — port `_ntsRoutePairResult_build` to use
   `routingKernelSolvedRouteSetResult_build`. Low risk: NTS already has test
   coverage and the formulas are documented.

3. **Seam kernels (EAST-to-seam, seam-to-WEST)** — replace
   `interconnect_solver.py`'s per-case logic with two kernel instances per seam.
   Requires defining a `SeamKernel` region bundle analogous to `RoutingKernel`.

4. **Backedge + same-side** — replace `_wteRoutePairResult_build` and
   `_sameSideLocalRouteResult_build` with degenerate kernel variants.

5. **Dead code removal** — delete `_wteBundleWindowRoutesResult_build`,
   `_routeMayOccupyCellsCheck`, `_routeOccupancy_commit`, `_wteStripKeys_build`,
   `_laneTriplesInPackingOrder_build`, `_laneWindowsInSenseOrder_build`,
   `_routeLengthScore_calculate` from `zone_solver.py`.

---

## Architectural Notes

**Kernel is wall-to-wall, not chip-to-chip.** The kernel's job is to fill a
rectangular routing region between two terminal walls. The caller (zone_solver,
chip_solver, interconnect_solver) is responsible for mapping chip placements to
terminal wall positions. This separation holds for all tiers.

**Region geometry is the contract.** The kernel consumes a `RoutingKernel` (or
equivalent region bundle). Every tier needs its geometry pre-built into the
analogous structure before the kernel is called. For chip-internal, this means
deriving fan/longitude/latitude regions from the chip's bounding box.

**Lane continuity across seams.** When the EAST-to-seam kernel and the
seam-to-WEST kernel serve the same logical route, their lane indices must agree at
the seam boundary. The seam coordinate is a shared waypoint; lane assignment
propagates from the originating zone outward.

**No kernel API changes needed for tiers 1–2.** The existing
`routingKernelSolvedRouteSetResult_build` signature works for chip-internal and NTS
without modification. Seam kernels may need a `SeamKernel` region bundle type (a
lightweight analogue of `RoutingKernel` covering only the inter-zone corridor).

---

## Design Notes: Why EAST-to-Seam / Seam-to-WEST Is the Right Decomposition

**The seam is the natural boundary.** Each zone already owns its spatial extent up
to the seam edge. An EAST-to-seam kernel operates entirely within zone(i)'s
geometry — the inter-zone FAN_IN_OUT and LONGITUDE regions are already present in
the placed grid. A seam-to-WEST kernel operates entirely within zone(i+1)'s
geometry. Neither kernel needs to know about the other zone. They share only the
seam coordinate as a handoff point.

**Lane continuity is the one binding constraint.** A route entering the seam at
lane `k` from zone(i) must exit at lane `k` into zone(i+1). The lane index must be
established at obligation-dispatch time — before either kernel is called — and
threaded through both. This is already the structure in `interconnect_solver.py`:
it computes a `laneIndex` per obligation and uses it on both sides. Migrating to
seam kernels means the existing lane-assignment logic stays; it just feeds
`KernelObligation` records instead of bespoke column/row formulas.

**What this fixes in `interconnect_solver.py`.** The current implementation
computes routes for both sides of the seam inside one function with interleaved
logic. Two distinct kernels (one per side) give independent test coverage for each
half and make asymmetric seam cases (NS vs WTE) straightforward to handle: just
supply the appropriate region geometry to each kernel. The symmetry also means the
same collision-freedom guarantees that hold for intra-zone kernels apply
automatically to seam kernels.

**No new kernel API needed for the seam case.** The existing
`routingKernelSolvedRouteSetResult_build` signature already takes a `RoutingKernel`
(region bundle) + obligations. A seam kernel instance is just a `RoutingKernel`
whose region set covers the inter-zone corridor rather than the full intra-zone
box. The caller constructs the right geometry; the solver is unchanged.
