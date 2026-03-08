# Requirements: Internal Manifold Rendering — Geometry-First

## Context
You are working in `/home/rudolphpienaar/src/signalFlow`. Read `PLAN.md`, `docs/internalWiring.adoc`, `docs/algorithm.pseudo.logic`, and `docs/InternalWiring.drawio` before writing a single line of code. The drawio is the **geometric aspiration** — not pixel-perfect truth, but the spatial model you must reproduce. The spec (`internalWiring.adoc` + `algorithm.pseudo.logic`) states constraints that **cannot be violated**. Where they conflict or are ambiguous, the geometric model wins.

---

## The One Invariant You Must Enforce Before Anything Else
Every `(x, y)` cell inside the chip that belongs to thread T must belong **exclusively** to T. Point crossings (a single cell where one thread's vertical segment intersects another thread's horizontal segment, producing `┼`) are permitted. Shared *segments* of any length between two threads are **absolutely prohibited**. This is the only rule that matters. Every design decision flows from it.

Validate this invariant programmatically — scan the rendered canvas and assert that no row within the chip's interior contains two distinct ANSI color codes on the same horizontal span, and no column contains two distinct colors on the same vertical span.

---

## Invariant: Every Wiring Pair Gets an Internal Anchor

**Every** logical wiring pair in `node.internal_wiring` — including pairs that appear to share a wall row with their destination ("same-row" pairs) — MUST produce an explicit internal anchor label for both its source and destination port. There is **no straight-through bypass** that skips anchor materialization. The straight-through rendering path in the previous implementation is **abolished**.

Consequence: if a port has `N` wiring entries, it must have exactly `N` internal anchor labels rendered on the canvas.

---

## Internal Anchor Placement Rules (Non-Negotiable)

### 0. Single-Connection Pass-Through Ports Use Straight-Through Rendering

If a port appears exactly **once** as a source in the wiring list AND the paired destination appears exactly **once** as a destination, AND both ports are on **opposite walls** at the **same y row**, that pair is a **straight-through**: it is rendered as a single full-width colored `hline_pierce` with no internal anchor nodes at all.

This covers simple relay chips like `pX()` with `["s1:s1", "r1:r1"]` — every pair is 1:1, cross-wall, same-row, so the entire chip renders as a set of straight horizontal lines with zero internal node replication.

If **any** port in the wiring list has more than one connection as source or destination, that port and all its pairs enter the VLSI manifold (see below). Straight-through and manifold renderings may coexist in the same chip.

### 1. Anchor Labels Must Appear Flush Against the Chip Wall

Internal anchor labels are **flush** against the chip wall with **zero gap** between the wall border character and the label text. There is NO intermediate column — no blank space, no bus character visible between the wall and the label:

- **Left wall ports:** label starts at `x = x0 + 1` (immediately adjacent to the left border character at `x0`)
- **Right wall ports:** label ends at `x = rx - 1` (immediately adjacent to the right border character at `rx`), so label starts at `x = rx - 1 - len(label_with_arrow)`

The neutral longitude bus is drawn at `x0 + 1` for structural continuity, but the sovereign label overlay overwrites the bus character at every anchor row. The bus character is a non-anchor-row artifact only. At anchor rows, the label IS the occupant of that cell — no bus character shows through.

Do **not** place labels at `x0 + 2`. That is the old (incorrect) position. The correct position is `x0 + 1`, which produces visually flush wall-to-label rendering with no intervening column.

Do **not** use `port_to_x[port]` (the longitude channel column) as the label x. That column is for wire routing, not label placement.

### 2. Anchor Direction: Signal Ports Up, Return Ports Down

No anchor may be placed AT the external wall port row. Every anchor is displaced away from that row:

- **Signal ports** (`sX` on left, `outX` on right): anchor stack extends **UPWARD** (decreasing y) from the wall port row. Port at row `Y` → anchors at `Y-1, Y-2, Y-3, …`
- **Return ports** (`rX` on left, `retX` on right): anchor stack extends **DOWNWARD** (increasing y) from the wall port row. Port at row `Y` → anchors at `Y+1, Y+2, Y+3, …`

This ensures signal and return anchor stacks for the same logical port group never overlap in y, and both remain near their respective wall port rows (edge-adjacent).

### 3. Every Manifold Port With N Connections Has Exactly N Distinct Anchor Rows

No two anchors for the same port may occupy the same row. No anchor row may coincide with the wall port row.

### 4. All Manifold Signal Names are Materialized — No Exceptions

If `node.internal_wiring` contains `s2:out2`, `s2:out3`, `s2:out4`, `s2:out5`, then signal `s2` must have 4 distinct internal anchor rows, all rendered as `canvas.text` labels at `x0+1`. Similarly `out2`, `out3`, `out4`, `out5` must each have their own internal anchor rows at `rx - 1 - len(label)`. And `ret2`, `ret3`, `ret4`, `ret5` as source signals must each have their own downward anchor rows on the right wall, and the right-side `rX` ports as destinations must each have their own downward anchor rows on the left wall.

### 5. Directionality Arrow on Interior-Facing Label Edge

Every internal anchor label carries a single arrow character on its interior-facing edge indicating the propagation direction of the thread:

- **Left wall labels:** arrow is **appended** as the rightmost character (the edge that faces the chip interior)
- **Right wall labels:** arrow is **prepended** as the leftmost character (the edge that faces the chip interior)

Arrow direction follows thread propagation:

| Thread direction | Port   | Wall  | Label form  | Arrow |
|-----------------|--------|-------|-------------|-------|
| W→E (forward)   | `sX`   | Left  | `sX►`       | `►`   |
| W→E (forward)   | `outX` | Right | `►outX`     | `►`   |
| E→W (return)    | `retX` | Right | `◄retX`     | `◄`   |
| E→W (return)    | `rX`   | Left  | `rX◄`       | `◄`   |

The arrow is rendered in the same color as the anchor label. The arrow character counts toward label width for flush-wall x-coordinate computation:

```python
# Left wall: label starts at x0+1, total width = len(port_name) + 1 (for arrow)
label_text = f"{port_name}►"   # or ◄ for return ports
canvas.text(x0 + 1, anchor_row, label_text, color=thread_color)

# Right wall: label starts at rx - len(port_name) - 1 - 1 (port_name + arrow prepended)
label_text = f"►{port_name}"   # or ◄ for return ports
canvas.text(rx - len(label_text), anchor_row, label_text, color=thread_color)
```

---

## Neutral Longitude Bus (Wall-to-Anchor Connector)

A **neutral (uncolored) vertical bus** connects each external wall port row to the bottom-most (highest-y) anchor of its stack. This bus is rendered with `canvas.vline` with **no color argument** (neutral). It is a structural connector, not a thread segment. It must never carry a color code.

The colored thread begins at the internal anchor row, not at the wall port row.

---

## Dedicated Trunk Zone Architecture

The manifold interior is partitioned into **three horizontal bands** to guarantee structural isolation between W→E (forward) and E→W (return) thread classes:

```
┌────────────────────────────────────────┐
│  [header: chip name, top border]       │
├────────────────────────────────────────┤  ← y0 + 3
│  E→W TRUNK ZONE  (return threads)      │  n_ew rows, one per retX→rX pair
│    rX◄───────────────────────►retX     │
├────────────────────────────────────────┤
│  [mid spacer: 2 rows, empty]           │
├────────────────────────────────────────┤
│  W→E TRUNK ZONE  (forward threads)     │  n_we rows, one per sX→outX pair
│    sX►───────────────────────◄outX     │
└────────────────────────────────────────┘  ← y0 + h - 1
```

### Trunk Zone Rules

1. **E→W trunks** (return: `retX→rX`) are placed in the **top zone** only, starting at `y0 + 3`. One row per wiring pair.
2. **W→E trunks** (forward: `sX→outX`) are placed in the **bottom zone** only, ending at `y0 + h - 2`. One row per wiring pair, counting upward.
3. **Trunk row = Anchor row.** The anchor label for a wiring pair lives at the same row as its trunk. No separate latitude zone traversal; W2 and W4 doglegs are zero-length in this model.
4. **Neutral vertical bus** is the only wall-to-anchor connector. It is drawn as an uncolored `vline` from the external wall port row to the trunk/anchor row. The bus is overwritten at the anchor row by the sovereign colored label.
5. **Straight-through pairs** (1:1, same name, opposite walls, same wall-port row) bypass the trunk zone entirely. Their wall port row is seeded into `used_rows` to prevent any trunk from landing there.
6. **No trunk row may be shared.** Each wiring pair has exactly one unique trunk row. The zone sizes must accommodate all pairs without collision.

### Updated `chip_h_precompute` Formula

```python
n_we = sum(1 for src, dst in wiring_pairs if src in left_names and dst in right_names)
n_ew = sum(1 for src, dst in wiring_pairs if src in right_names and dst in left_names)
n_ports = max(len(node.input_ports), len(node.output_ports))
spacing = config.portVerticalSpacing

# chip_h must accommodate:
#   2  border rows (top + bottom)
#   2  header rows (func name + chip top padding)
#   n_ew  E→W trunk zone rows
#   2  mid spacer rows
#   n_we  W→E trunk zone rows
#   spacing * n_ports  wall-port stacking rows
chip_h = max(
    config.baseLeafHeight,
    2 + 2 + n_ew + 2 + n_we + spacing * n_ports + 2,
)
```

### Trunk Row Allocation

```python
# E→W trunks: top zone, rows y0+3 .. y0+3+n_ew-1
ew_trunk_rows = [y0 + 3 + i for i in range(n_ew)]

# W→E trunks: bottom zone, rows y0+h-2-n_we .. y0+h-3
we_trunk_rows = [y0 + h - 2 - n_we + i for i in range(n_we)]
```

Assign one trunk row from the appropriate zone list to each wiring pair in order. Seed `used_rows` with all trunk zone rows plus all straight-through wall-port rows before any further route allocation.

---

## Geometric Model (Primary Target)

The chip interior is divided into two zones:

**Longitude Zone** — thin vertical strips immediately inside each wall. One strip per port. Each strip is `l_counts[port]` columns wide. Input port strips are on the left; output port strips are on the right.

**Latitude Zone** — the remaining interior between the longitude zones. Contains one exclusive horizontal track per thread. No thread may share a track row with any other thread.

Each thread's path is exactly five segments:

```
W1: H  — from anchor (wall col, anchor_row) → to longitude column  [colored]
W2: V  — from longitude column → up/down to trunk row              [colored]
W3: H  — trunk row, full span across latitude zone                 [colored]
W4: V  — from trunk row → up/down to destination longitude column  [colored]
W5: H  — from destination longitude column → to destination anchor [colored]
```

**All five segments carry the thread's color.** There are no neutral/uncolored thread segments. W1 and W5 are short horizontal connectors, not shared carriers.

---

## Lane / Track Allocation Rules (from `algorithm.pseudo.logic`)

Before allocating trunk rows, **mark all rows used by straight-through pairs as occupied.** Trunk allocation must never land on a straight-through row.

Use the `AttachmentSense` logic from `algorithm.pseudo.logic` to determine lane assignment direction within each channel:

- `lineAttachmentSense_determine(src_label, dst_label, direction)` returns `fromStart` or `fromEnd`
- `fromStart` → allocate from the nearest end of the available lane list
- `fromEnd` → allocate from the far end
- Apply this for east-edge, west-edge, and both transversal (N/S) directions separately

The sense policy (`AttachmentPolicy`) governs: which end of a longitude channel a thread enters from, and which direction within a latitude channel a trunk is placed. Implement this correctly — it is what prevents the dogleg segments from crossing their own port's other threads.

---

## Mandatory Post-Audit (Inline, After Label Overlay)

After the sovereign label overlay (section 2.9), add a post-audit block that **immediately raises** if any of the following invariants are violated:

```python
# Post-audit: anchor materialization count check
for port, expected_count in l_counts.items():
    wall_row = _wall_row(port)
    actual_rows = all_anchor_rows.get(port, [])
    assert len(actual_rows) == expected_count, (
        f"PORT {port}: expected {expected_count} internal anchors, got {len(actual_rows)}"
    )
    for r in actual_rows:
        assert r != wall_row, (
            f"PORT {port}: anchor at row {r} coincides with wall port row {wall_row}"
        )
    assert len(set(actual_rows)) == len(actual_rows), (
        f"PORT {port}: duplicate anchor rows detected: {actual_rows}"
    )
```

This audit must fire during normal render; it is not a test-only assertion. A violation here means the geometry contract has been broken and the output is invalid.

---

## What Previous Attempts Got Wrong

1. **A shared vertical \"neutral bus\" was drawn at `x0+1` as a colored segment.** The bus must be uncolored (neutral). Colored buses are prohibited.
2. **All anchors extended in the same direction (all up or all down)**, causing signal and return anchor stacks to overlap in y when written to the same label column (x0+2).
3. **Anchor labels used `port_to_x[port]`** (the longitude channel column deep inside the chip) instead of x0+2 / rx-1-len. This scattered labels across the chip interior instead of keeping them edge-adjacent.
4. **The first anchor was placed AT the wall port row** (`wall_row - 0 = wall_row`). The wall port row must never be an anchor row. Signal anchors start at `wall_row - 1`, return anchors at `wall_row + 1`.
5. **The straight-through bypass** was removed entirely in a previous attempt, causing simple relay chips (pX()) and 1:1 hub connections (s1→out1) to receive unnecessary internal anchor replication and VLSI routing overhead.
6. **The straight-through bypass used `l_counts` (combined src+dst count)** to detect single-connection pairs, which double-counted ports like `s1:s1` (l_counts["s1"]=2 even though src_count=1, dst_count=1). Use `src_counts[src]==1 AND dst_counts[dst]==1` instead.
7. **`thread_to_y` trunk allocation started from `y0+3`** without seeding with straight-through rows, causing manifold trunks to land on the same row as straight-through signals.
8. **W2 and W4 vertical doglegs passed `color` as the `ch` positional argument** to `canvas.vline` instead of the `color` keyword argument, leaving all vertical segments uncolored.
9. **Anchor labels placed at `x0 + 2`** instead of `x0 + 1`. The extra column between the wall border and the label text creates a visible "ladder" artifact where the neutral bus `│` character appears as a repeating rung between anchor rows. Labels must be flush at `x0 + 1` — the neutral bus is overwritten by the sovereign label overlay at anchor rows.
10. **No directionality arrow on anchor labels.** Every anchor label must carry `►` (W→E) or `◄` (E→W) on its interior-facing edge. Without this the schematic has no visual cue for thread propagation direction at each anchor point.
11. **Trunk allocation with no dedicated zones causes a "shared bus at bottom" artifact.** Without top/bottom zone partitioning, when the available row budget is exhausted by anchor row seeding, all overflow trunks fall to the same fallback row (`y0+h-1-4`). This produces 7+ colored horizontal segments on the same 4 rows — a massive H-coincidence. The dedicated zone architecture eliminates this by structurally reserving exactly one row per wiring pair in the correct zone, computed in `chip_h_precompute` to guarantee no overflow.

---

## Acceptance Criteria (Check All Before Declaring Done)

1. Render `examples/explicit-hub.yaml`. Count internal anchor labels: for every port `p` with `N` wiring entries, exactly `N` instances of `p` appear inside the chip interior.
2. No anchor label appears at a y-coordinate equal to any wall port row.
3. All anchor rows for input ports have y < (wall port row). All anchor rows for output ports have y < (wall port row).
4. Strip ANSI. Confirm each row in the chip interior contains at most one thread's color.
5. Programmatic scan: no horizontal span shares two colors; no vertical span shares two colors.
6. Following any single color from left wall to right wall traces one unambiguous, unbroken path.
7. `python -m pytest tests/` — no new test failures beyond the pre-existing 24.
8. Render `examples/passthrough.yaml` and `examples/show-cohort.yaml` — no spurious `┼` on straight-through chips.
9. Render `examples/explicit-hub.yaml`. Confirm anchor labels appear visually flush against the chip walls — no blank column between the `│` wall border and the first character of any anchor label.
10. Confirm every anchor label carries a `►` or `◄` directionality arrow on its interior-facing edge, consistent with the thread's propagation direction (W→E = `►`, E→W = `◄`).
11. Render `examples/explicit-hub.yaml`. Confirm all W→E trunks are confined to the bottom zone and all E→W trunks are confined to the top zone. No trunk row appears in both zones. No two wiring pairs share a trunk row.

---

## Files to Modify

- `src/signalflow/lib/chips.py` — sections 2.1 through 2.9 (straight-through bypass removal, anchor allocation, bus, routing loop, label overlay, post-audit)
- Possibly `src/signalflow/engine/router/router.py` — if `AttachmentSense` logic needs to be wired into `route_lay`

Do not modify layout, tree, canvas, or wire rendering files unless a specific geometric failure requires it.
