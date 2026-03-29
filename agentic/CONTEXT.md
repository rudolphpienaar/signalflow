# Project Context: SignalFlow — Kernel Routing Vision

This file defines the authoritative architectural baseline for SignalFlow.

## Current Architectural State (March 2026 — v5.9.0)

**Milestones 1 and 2 are complete.** Milestone 3 (Functional Symmetry / Expansion)
is in progress. Suite: **566 passed, 0 failed** on branch `rearch-zone-grid`.

### What is working

- **WTE intrazone kernel:** `kernel_solver.py` handles all WEST→EAST routes within
  a WTE zone. Collision-free by construction (peel column parity, lane separation).
- **Zone solver shunt removed:** INTRAZONE obligations route through
  `routingKernelSolvedRouteSetResult_build` exclusively.
- **destinationPortIndex** correctly uses per-destination chip rank (not
  `childCallIndex`). Fan-out and fan-in both route to correct chip rows.
- **Ghost set deleted:** `RoutingZone.routingZoneRegionSet` removed; dispatcher
  functions replace all direct field access.
- **Full suite green:** all 566 tests pass including hub, asymmetric-fanout, NTS,
  interconnect, debug context, and grid solver tests.

### Architectural Goal

**All routes solved by `kernel_solver.py`.** The kernel's wall-to-wall API is
already generic: give it a `RoutingKernel` (region bundle) + obligations; it emits
planar, collision-free polylines. The plan is to apply this uniformly to every
routing context. See `KERNEL-ROUTING-VISION.md`.

### What is NOT yet on the kernel

| Context | Current solver |
|---|---|
| WTE backedge (EAST→WEST) | `_wteRoutePairResult_build` (legacy, active) |
| WTE same-side self-call | `_sameSideLocalRouteResult_build` |
| NTS intrazone | `_ntsRoutePairResult_build` |
| Seam-crossing | `interconnect_solver.py` |
| Grid long-haul | `grid_solver.py` |
| Chip-internal wiring | `chip_solver.py` (directive-based) |

### Architectural Components

1. **RoutingKernel:** Atomic bundle-first solver. Consumes two terminal walls +
   routing bands; emits 6-keypoint polyline pairs (forward + return).
2. **RoutingZone:** Composition of up to 5 kernels (West, Intra, East, North,
   South). Coordinates world-grid placement and macro-routing.
3. **Seam kernels (planned):** EAST-to-seam + seam-to-WEST kernels replace the
   current `interconnect_solver.py`. Each operates within one zone's spatial extent;
   they share only the seam coordinate as handoff.
4. **Chip-internal kernel (planned):** Chip box treated as a zone rectangle. Kernel
   solves WEST-input → EAST-output routing automatically, replacing explicit
   `internal_wiring` YAML directives for the common transverse case.
5. **REPL:** Interactive interface follows strict **RPN (noun_verb)** naming.

## Document Precedence

When there is tension between code and architecture direction, use these in order:

1. `ZEROSHOT.md` — Current agent handoff (most up-to-date status)
2. `KERNEL-ROUTING-VISION.md` — Kernel-everywhere goal and migration plan
3. `PLAN.md` — Milestone roadmap
4. `BREAKAGE.md` — Residual failure baseline
5. `NON-NEGOTIABLES.md` — Core physics (never override)
6. `docs/re-architecture.adoc` — Target design
7. `PYTHON-STYLE-GUIDE.md` — Naming standards

## Mandatory Development Gate

Before any implementation pass:
1. Verify the change against `NON-NEGOTIABLES.md`.
2. Restate the "No same-direction shared realized cells" invariant.
3. Orthogonal crossings (E/W ↔ N/S on the same cell) ARE allowed (drawn as `+`).
4. Prove success using helpers in `tests/routing_invariants.py`.

## Key Implementation Files

| File | Purpose | Status |
|---|---|---|
| `src/signalflow/routing/kernel_solver.py` | WTE intra kernel (longitude peel, parity-correct) | ✅ |
| `src/signalflow/routing/zone_solver.py` | Dispatches to kernel; legacy backedge path active | ✅ / ⚠️ |
| `src/signalflow/routing/chip_solver.py` | Chip-internal directive parsing | ⚠️ realization not yet kernel |
| `src/signalflow/routing/interconnect_solver.py` | Seam-crossing routes | ⚠️ to be replaced |
| `src/signalflow/routing/interconnect_solver.py` | NTS seam routing | ✅ covered by tests |
| `src/signalflow/engine/debug.py` | REPL debug views | ✅ |
| `tests/test_rearch_zone_solver.py` | Zone solver physics tests | ✅ 15/15 |
| `tests/test_rearch_interconnect_solver.py` | Interconnect physics tests | ✅ |
| `tests/routing_invariants.py` | Shared-cell invariant helpers | ✅ |
| `KERNEL-ROUTING-VISION.md` | Full vision + migration sequence | ✅ new |
