# Project Context: SignalFlow — Kernel-Crossbar Baseline

This file defines the authoritative architectural baseline for SignalFlow.

## Current Architectural State (March 25, 2026 — Milestone 2 In Progress)

The project has pivoted to a **Kernel-Crossbar** routing model. Milestone 1 (Rescue
Mission) is **complete**. Milestone 2 (Substrate Unification) is **in progress**:

- **Zone solver shunt removed:** INTRAZONE obligations now route through `zone.intraKernel`.
- **kernel_solver.py rewritten:** Longitude-based peel columns replace the broken fan-based
  approach. Return routes correctly swap source/destination (callee → caller).
- **Debug context tests fixed:** All 22 failures resolved; `debug.py` `__dir__` methods
  alphabetically ordered; RPN alias methods added.
- **1 blocking issue:** 5 hub/asymmetric-fanout zone solver tests still fail due to a
  1-row boundary discrepancy in the `r_d` row formula (see `ZEROSHOT.md`).

### Architectural Components

1. **Routing Kernel:** The atomic, bundle-first solver unit. Uses monotone ribbon
   packing to connect two parallel walls through a dedicated substrate.
2. **Standard RoutingZone:** A composition of 5 specialized kernels (`West`, `Intra`,
   `East`, `North`, `South`). Coordinates world-grid placement and macro-routing.
3. **Embedded RoutingZone:** A lean, single-kernel zone used for seams (breakouts)
   and chip internal wiring.
4. **REPL:** Interactive interface follows strict **RPN (noun_verb)** naming.

### Remaining Technical Debt (Milestone 2)

- **1-Row Boundary Issue:** `r_d` formula produces row 45 for the 5th proxy chip, but
  the FAN_IN_OUT EAST region only covers rows 5..44. Root cause under investigation:
  chip height fetched via `chipResult_get` may differ from the chips-list measurement
  (7 vs 6), OR the zone terminal region is undersized by 1 row.
- **Ghost Set:** `RoutingZone` still holds a legacy monolithic `routingZoneRegionSet`
  alongside the 5 internal kernels. Can be deleted once zone solver tests pass.
- **~12 Pre-existing Test Failures:** Assignment/obligations (5), engine/render (3),
  routing zone model validation (2), circuit doc canonicalization (1).

## Document Precedence

When there is tension between code and architecture direction, use these in order:

1. `ZEROSHOT.md` (Current Agent Handoff — most up-to-date status)
2. `PLAN.md` (Milestone Roadmap)
3. `BREAKAGE.md` (Residual Failure Baseline)
4. `NON-NEGOTIABLES.md` (Core Physics — never override)
5. `docs/re-architecture.adoc` (Target Design)
6. `PYTHON-STYLE-GUIDE.md` (Naming Standards)

## Mandatory Development Gate

Before any implementation pass:
1. Verify the change against `NON-NEGOTIABLES.md`.
2. Restate the "No same-direction shared realized cells" invariant.
3. Orthogonal crossings (E/W ↔ N/S on the same cell) ARE allowed (drawn as `+` in ASCII).
4. Prove success using `tests/routing_invariants.py`.

## Key Implementation Files

| File | Purpose | Status |
|------|---------|--------|
| `src/signalflow/routing/fan_solver.py` | Corridor-aware peel column allocation | ✅ New, physics correct |
| `src/signalflow/routing/kernel_solver.py` | Atomic kernel solve (longitude peel) | ✅ Rewritten; 8/13 zone tests passing |
| `src/signalflow/routing/interconnect_solver.py` | Mega-kernel orchestrator | ✅ Fixed |
| `src/signalflow/routing/zone_solver.py` | Intra-zone solver | ✅ Shunt removed; routes via intraKernel |
| `src/signalflow/engine/debug.py` | REPL debug views | ✅ All __dir__ fixed; alias methods added |
| `tests/test_rearch_interconnect_solver.py` | Interconnect physics tests | ✅ 4/4 passing |
| `tests/test_rearch_debug_context.py` | Debug context / REPL tests | ✅ All passing (was 22 failed) |
| `tests/test_rearch_zone_solver.py` | Zone solver physics tests | ⚠️ 8/13 passing; 5 hub tests blocked |
| `tests/routing_invariants.py` | Shared-cell invariant helpers | ✅ Active |
