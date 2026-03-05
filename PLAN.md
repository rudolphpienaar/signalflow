# Execution Plan: VLSI Manifold Router Integration

This plan outlines the transition of the SignalFlow internal manifold synthesis to a deterministic VLSI-inspired Channel Routing model with explicit Internal Anchors.

## Phase 1: Fabric-to-Canvas Resolution [COMPLETED]
- [x] **Coordinate Mapper:** `VLSIRouter.canvas_coords_resolve` complete.
- [x] **Anchor Extension:** Resolver supports per-thread (x,y) waypoints via `port_to_x` / `thread_to_y` maps.

## Phase 2: Design Rule Check (DRC) Engine [COMPLETED]
- [x] **Occupancy Grid:** `OccupancyGrid` implemented in `src/signalflow/engine/router/occupancy.py`.
- [x] **Coincidence Guard:** `trackClear_check` implemented to mathematically prove zero coincidence.

## Phase 3: Core Library Integration (Strict Synthesis) [IN PROGRESS]

### Known Disconnects (from code audit vs. internalWiring.drawio spec)

**Disconnect 1 — ROOT CAUSE: No Internal Anchor Stacking** ← fix first
- `get_port_info(port_name)` in `chips.py` returns ONE physical wall row for a port name regardless of thread count.
- For `s2:out2`, `s2:out3`, `s2:out4`, `s2:out5` — all 4 share the same `src_y` → W1 segment drawn 4× on the same row = immediate horizontal coincidence.
- Fix: assign a unique `anchor_row` per thread instance using a per-port counter. Render stacked `s2` labels inside the west wall (one per thread). `src_y` must be per-thread, not per-port-name.

**Disconnect 2 — No Neutral Longitude Bus**
- No vertical color-neutral connector from the external wall terminal to its N stacked internal anchors.
- Fix: after assigning anchor rows, draw a neutral `vline` from the wall port row to span all anchor rows for that port.

**Disconnect 3 — Latitude Channels not grouped by signal name**
- `fabric_init` creates one `LatitudeChannel` per thread (`"s2:out2"`, `"s2:out3"`, …), each with 1 lane.
- Spec requires: one `"s2"` `LatitudeChannel` with N lanes (a contiguous horizontal band).
- Also: `base_id` in `route_lay` splits on `"_"` but signal_id has no `_` — grouping is a no-op.
- Fix: group `h_counts` by `src` signal name; change `base_id` to `signal_id.split(":")[0]`.

**Disconnect 4 — `port_to_x` column spacing causes Longitude Channel collisions**
- `v_track_l` increments by 1 per unique port, but a port with density=4 needs 4 columns reserved.
- `s2` (density 4) base at `x0+2`, `s3` base at `x0+4` — s3 lane 0 aliases s2 lane 1.
- Fix: increment `v_track_l` by `l_counts[port]`, not 1.

**Disconnect 5 — `thread_to_y` key / `h_chan_name` mismatch (latent)**
- Currently accidental consistency (`"s2:out2"` both sides). Once Disconnect 3 is fixed, `h_chan_name` must be `"s2"` and `thread_to_y["s2"]` holds the band's base y-row, with `h_lane` selecting within it.

**Disconnect 6 — Chip height not Density-Law-aware**
- `chip_h_precompute` uses `spacing * max(n_input, n_output) + 3`.
- For Hub with 5 inputs × portVerticalSpacing=10: height ≈ 53 rows — enough for wall ports, but the manifold trunk rows (one per wiring pair) may exceed this.
- Fix: after anchor assignment, assert `chip_h >= (max_anchor_row - y0 + bottom_pad)` and expand if needed.

**Regression Bug — Spurious `┼` on pX() straight-through chips**
- Proxy chips with `internal_wiring: ["s2:s2", "r2:r2"]` (pass-through, same signal name both sides) are rendering `┼` at wall points instead of `┼` being absent (or `─`).
- Root cause: `chips.py` now sets `canvas.mode_merge = True` before checking for `internal_wiring`, so the early-return guard `if not node.internal_wiring: return` is AFTER `mode_merge` is set to True. The `mode_merge = False` at the end is never reached for those chips — leaving merge mode active for subsequent chips that draw wires through that position.
- Actually: `mode_merge` is set to True, then `if not node.internal_wiring: return` — the `return` skips the `canvas.mode_merge = False` reset. This is the bug.
- Fix: move the `if not node.internal_wiring: return` guard BEFORE `canvas.mode_merge = True`, or ensure `mode_merge = False` is always reset (try/finally).

### Execution Tasks
- [x] **Bug fix:** Move `if not node.internal_wiring: return` guard before `canvas.mode_merge = True` in `chips.py`.
- [x] **Grouped Fabric:** Update `fabric_init` in `router.py`: group `h_counts` by `src`; fix `base_id` to split on `":"`.
- [x] **port_to_x spacing:** Increment `v_track_l/r` by `l_counts[port]` in `chips.py`.
- [x] **Internal Anchors:** Non-overlapping block allocation (`all_anchor_rows`) with per-port counter lookup in sections 2.6/2.8 of `chips.py`. Separate `left_anchor_used`/`right_anchor_used` sets ensure no same-wall collisions.
- [x] **Neutral Longitude Bus:** Bus spans from physical wall port row to last anchor row; fires for any port with span > 0 (section 2.8 of `chips.py`).
- [x] **Waterfall Rendering:** Per-thread anchor rows from `all_anchor_rows[port][idx]` wired into `Terminal.y` before `route_lay`.
- [x] **Sovereign Label Overlay:** `canvas.text(label_x, row, port)` at each anchor row (section 2.9), written after routing so labels punch through the wire grid.

## Phase 4: Geometry-Correct Manifold [OPEN — see REQUIREMENTS.md]

### Known Geometric Violations (current `chips.py` state)
- **Trunk/straight-through row collision:** `thread_to_y` allocates trunk rows starting from `y0+3` without excluding rows already occupied by straight-through pairs. The s1→out1 row carries multiple colors — direct coincidence violation.
- **Wrong anchor direction:** Input anchor stacks currently extend downward from the wall port row. Spec requires upward for inputs, downward for outputs only.
- **Spurious neutral bus:** A shared vertical `│` segment was drawn at `x0+1` connecting anchor rows for a port. This is a shared segment between distinct threads — prohibited. Must be removed.
- **W1/W5 uncolored:** Port-exit and port-entry segments are rendered neutral, making individual threads untraceable end-to-end.
- **`AttachmentSense` not implemented:** Lane allocation ignores the `fromStart`/`fromEnd` policy from `algorithm.pseudo.logic`. All lane assignment is currently positional only.

### Required Tasks
- [x] **Straight-through row exclusion:** `used_rows` seeded with straight-through rows AND all anchor rows before trunk allocation.
- [x] **Anchor direction fix:** Input anchors extend upward (Y−1, Y−2…); output anchors extend downward (Y+1, Y+2…). Interior-bounds clamp with direction-flip fallback.
- [x] **W3 bounded to latitude zone:** Replaced single full-width W3 `hline_pierce` with three segments: W2_ext (longitude left), W3 (latitude zone only), W4_ext (longitude right).
- [x] **`chip_ow_compute` per-side density:** Rewrote to compute per-port `l_counts` split by `left_names`/`right_names`; formula `manifold_min_ow = 8 + 2*(v_left+v_right)`.
- [ ] **Remove neutral bus:** The neutral bus at `x0+1` currently coexists with label overlay. With flush-wall labels at `x0+1`, the bus is implicitly overwritten — verify no ghost characters remain.
- [ ] **Color W1 and W5:** All five segments of every thread carry the thread's color.
- [ ] **Implement `AttachmentSense`:** Wire `lineAttachmentSense_determine` into longitude and latitude lane allocation.
- [ ] **Programmatic DRC scan:** After rendering, scan canvas for any row or column span carrying two distinct color codes. Assert zero violations before output.

### Known Remaining Issues (→ addressed in Phase 5)
- **"Shared bus at bottom" artifact:** With anchor rows seeded into `used_rows`, only one valid block survives for hub chip. All 7 remaining W→E pairs fall to the same fallback row → massive H-coincidence. Root cause: `chip_h_precompute` doesn't budget for trunk rows. Fix: dedicated top/bottom trunk zones (see Phase 5).
- **"Ladder" between chip wall and anchor labels:** Labels placed at `x0+2` leave bus column `x0+1` visible between wall and label. Fix: move labels to `x0+1` (flush-wall) and add directionality arrows (see Phase 5).

### Acceptance Criteria
See `REQUIREMENTS.md` — all 11 criteria must pass before Phase 4/5 is marked complete.

### Test Suite Status (post Phase 3/4 partial)
- 71 tests pass, 24 fail with expected reasons.
- 3 router unit tests (test_router.py) all pass.
- 24 failing tests are pre-existing TDD spec tests for `├`/`┼` wall-junction behavior — deliberate deferred work.

## Phase 5: Dedicated Trunk Zones + Flush-Wall Labels [OPEN]

This phase eliminates the structural root cause of trunk allocation overflow and fixes the flush-wall label rendering.

### Design: Dedicated Top/Bottom Trunk Zones

The chip interior is split into three horizontal bands (see `REQUIREMENTS.md` § Dedicated Trunk Zone Architecture):
- **Top zone** (`y0+3` … `y0+3+n_ew-1`): one row per E→W wiring pair (retX→rX)
- **Mid spacer** (2 rows): visual separation
- **Bottom zone** (`y0+h-2-n_we` … `y0+h-3`): one row per W→E wiring pair (sX→outX)

Trunk row = Anchor row. No separate latitude zone traversal. Neutral bus is the only wall-to-anchor connector (uncolored vline from wall port row to trunk/anchor row). W2/W4 doglegs collapse to zero length.

### Required Tasks

- [x] **`chip_h_precompute` update:** New formula `3 + wall_span + 2 + n_ew + n_we + 2`; counts W→E / E→W pairs from `node.internal_wiring` in `tree.py`.
- [x] **Trunk zone allocation in `chips.py`:** E→W trunks assigned to top-zone rows (`ew_zone_start + i`); W→E trunks to bottom-zone rows (`we_zone_start + i`). Each pair has a unique pre-assigned trunk row in `pair_trunk_row`.
- [x] **Flush-wall label placement:** Left-wall labels at `x0+1`; right-wall labels at `rx - len(label)`. No gap between wall border and label text.
- [x] **Directionality arrow:** `►` appended to left-wall labels (W→E src), prepended to right-wall labels (W→E dst); `◄` appended to left-wall labels (E→W dst), prepended to right-wall labels (E→W src). Arrow color = thread color.
- [x] **Neutral bus:** Drawn at `x0+1` (left) / `rx-1` (right) from `wall_port_row` to `max(port_trunk_rows)` — one bus per port spanning all its connections.
- [x] **Removed VLSIRouter from `chips.py`:** No longitude zones, no dogleg segments, no route_lay/canvas_coords_resolve needed. Dedicated zone model replaces full VLSI routing.
- [ ] **DRC scan:** Post-render scan for H/V span color collisions — deferred.

### Acceptance Criteria
See `REQUIREMENTS.md` § Acceptance Criteria items 1–11.

### Test Suite Status (achieved)
- 71 pass, 24 fail — same as pre-Phase-5 baseline. No regressions.
- Post-audit (section 2.10) fires during normal render; no assertion errors on explicit-hub.yaml, passthrough.yaml, show-cohort.yaml.
