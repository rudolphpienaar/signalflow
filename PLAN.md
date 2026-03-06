# Execution Plan: VLSI Manifold Router Integration

This plan outlines the transition of the SignalFlow internal manifold synthesis to a deterministic VLSI-inspired Channel Routing model with explicit Internal Anchors.

## Phase 1: Fabric-to-Canvas Resolution [COMPLETED]
- [x] **Coordinate Mapper:** `VLSIRouter.canvasCoords_resolve` complete.
- [x] **Anchor Extension:** Resolver supports per-thread (x,y) waypoints via `portToX` / `threadToY` maps.

## Phase 2: Design Rule Check (DRC) Engine [COMPLETED]
- [x] **Occupancy Grid:** `OccupancyGrid` implemented in `src/signalflow/engine/router/occupancy.py`.
- [x] **Coincidence Guard:** `trackClear_check` implemented to mathematically prove zero coincidence.

## Phase 3: Core Library Integration (Strict Synthesis) [COMPLETED]
- [x] **RPN / Style Audit:** 100% codebase compliance with strict RPN naming and camelCase variables (v3.2.1).
- [x] **Registry & Port Binding:** `node_fromDict` canonicalizes chips and binds ports across recursive call-trees.
- [x] **Baseline Stability:** 95/95 tests passing against Phase 5 geometric assertions (v3.2.2).

## Phase 4: Geometry-Correct Manifold [IN PROGRESS]

### Known Geometric Violations (current `chips.py` state)
- [x] **Straight-through row exclusion:** `usedRows` seeded with straight-through rows AND all anchor rows before trunk allocation.
- [x] **Anchor direction fix:** Input anchors extend upward (Y−1, Y−2…); output anchors extend downward (Y+1, Y+2…). Interior-bounds clamp with direction-flip fallback.
- [x] **W3 bounded to latitude zone:** Replaced single full-width W3 `hline_pierce` with three segments: W2_ext (longitude left), W3 (latitude zone only), W4_ext (longitude right).
- [x] **`chipOw_compute` per-side density:** Rewrote to compute per-port `lCounts` split by `leftNames`/`rightNames`; formula `manifoldMinOw = 8 + 2*(vLeft+vRight)`.
- [ ] **Color W1 and W5:** All five segments of every thread carry the thread's color.
- [ ] **Implement `AttachmentSense`:** Wire `lineAttachmentSense_determine` into longitude and latitude lane allocation.
- [ ] **Programmatic DRC scan:** After rendering, scan canvas for any row or column span carrying two distinct color codes. Assert zero violations before output.

## Phase 5: Function Contract Synthesis (Sovereign Interface) [IN FOCUS]

This phase eliminates the structural root cause of trunk allocation overflow and implements the "Snippet 2" Structured Bus.

### Required Tasks
- [x] **Config Infrastructure:** Added `chip_io.input.explicit` support to global `Config` and per-node YAML overrides (v3.2.3).
- [ ] **Sovereign Layout (Centering):** Centered Many-to-One physical port convergence when `explicit: false`.
- [x] **Structured Junction Bus:** Implementation of Snippet 2 (┌─, ├─, └─) for unambiguous multiplexed fanning. Replaces previous "Neutral Bus" concept (v3.2.4).
- [ ] **Straight-Through Heuristic:** Collapse `Proxy` chip widths when 100% of internal wiring is 1:1 row-aligned pass-through.
- [ ] **Tightened Budgeting:** Update `chipH_precompute` with formula `3 + portSpan + wiringCount + 4` to prevent oversized chips.
- [ ] **Flush-wall label placement:** Left-wall labels at `x0+1`; right-wall labels at `rx - len(label)`.
- [ ] **Directionality arrow:** `►` / `◄` color-coded directionality indicators on internal labels.


### Acceptance Criteria
See `REQUIREMENTS.md` § Acceptance Criteria items 1–11.

### Test Suite Status (v3.2.2+)
- 95 pass, 0 fail. Full alignment with Phase 5 reactive piercing geometry.
