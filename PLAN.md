# Plan: ChipGeometry — Authoritative Geometry Consolidation

> Supersedes the previous VLSI Manifold Router Integration plan (all phases of
> which are complete).  This plan addresses the architectural debt that caused
> the v3.2.x velocity collapse: geometry computed redundantly in four files with
> subtly incompatible approximations, and no pre-render invariant enforcement.

---

## 0. Context Bootstrap — Files to Read Before Coding

Read these files **in order** before touching any code.  Each entry names the
file, what to extract from it, and why it matters for this plan.

### 0.1 Mandatory (read every session)

| # | File | Focus | Why |
|---|---|---|---|
| 1 | `PLAN.md` (this file) | Sections 1–9 | The contract; don't re-derive what's written here |
| 2 | `src/signalflow/config.py` | `Config` dataclass fields; `Wire` token constants | All geometry constants (`portVerticalSpacing`, `baseLeafHeight`, `passThroughAllowed`, `chipIoInputExplicit`) live here |
| 3 | `src/signalflow/models/node.py` | `Port` dataclass; `Node` fields (semantic vs layout); `node_fromDict` | Node is the unit of work; understand which fields are set at parse time vs layout time |
| 4 | `src/signalflow/lib/tree.py` | `ewTopOffset_get`, `chipH_precompute` | Both move into `ChipGeometry`; read carefully to understand the formulas being consolidated |
| 5 | `src/signalflow/lib/layout.py` | `layout_compute` (the pipeline stage order); `chipOw_compute` (especially the `_side` helper and `allStraight` logic) | `chipOw_compute` moves into `ChipGeometry`; `layout_compute` gets two new calls (`build_structural` then `resolve`) |
| 6 | `src/signalflow/lib/chips.py` | Sections 2.1–2.5 (geometry setup); section 2.4 (`portToX`); section 2.5.1 (`unitPorts`); section 2.6.5 (junction bus); section 2.9 (anchor labels); section 2.10 (DRC) | The geometry blocks in sections 2.1–2.5 move to `ChipGeometry.resolve()`; the rendering blocks (2.6–2.9) stay here and become reads from `node.geometry` |
| 7 | `src/signalflow/lib/wires.py` | `wireForward_render` lines 18–23 (`exitY` formula); `wireReturn_render` lines 120–124 (`parentRetY` formula) | These two formulas are the only things wires.py recomputes independently; they become `node.geometry.rightWallRows[port][idx]` reads |
| 8 | `src/signalflow/models/canvas.py` | `set()` (`modeMerge` flag); `vline()` (`pass_through` parameter, `flow` dead code); `hline_pierce()` (endpoint stub intents) | Understand what `modeMerge` does to glyph algebra; `flow` is confirmed dead code (both branches identical); `pass_through` is real |
| 9 | `src/signalflow/engine/render.py` | `diagram_render` (9 lines; the full pipeline) | Shows the stage order; `geometry_validate()` is inserted after `layout_compute` |
| 10 | `examples/hub.yaml` | The full YAML | Primary test fixture; 5 proxy chips → shared `process()` hub → 5 sinks; exercises every geometry case |

### 0.2 Secondary (read when working on specific phases)

| File | Read when | What to extract |
|---|---|---|
| `src/signalflow/lib/layout_joiner.py` | Phase 3 (chips.py migration) | `glyph_merge` bitmask algebra; N=1, S=2, E=4, W=8; how corners form from stub merges |
| `src/signalflow/engine/router/router.py` | Phase 3 | `route_lay`, `canvasCoords_resolve`; still used for W1–W5 point resolution |
| `src/signalflow/engine/router/models.py` | Phase 3 | `Terminal`, `Location`, `Track` types |
| `examples/passthrough.yaml` | Phase 0 testing | Pure pass-through topology; tests `passThroughAllowed` path |
| `docs/internalWiring.adoc` | Any | Zone/band geometry reference; §Band Boundaries table; §Rendering Bug Catalogue |

### 0.3 Mental Model (internalize before writing any code)

**Pipeline order** (must not be violated):
```
Parse (node_fromDict)
  → tree_flatten + col_assign
  → channelWidth_compute
  → layout_compute
      ├─ build_structural(node)   [sets chipH, chipOw, ewOff — before y]
      ├─ x/y assignment
      ├─ entryRows/returnRows assignment
      └─ resolve(node)            [sets wallRows, lCounts, anchorRows — after y]
  → geometry_validate             [NEW: fails loud before any drawing]
  → moduleBox_compute / canvas_create
  → chip_render × N              [pure renderer; reads node.geometry]
  → thread_render                [reads node.geometry.rightWallRows]
```

**Three horizontal zones** (top to bottom inside every manifold chip):
```
y0+3  .. y0+2+ewOff          E→W trunk zone   (return ribbons, westward)
y0+3+ewOff .. lastAnchorRow  Wall-port + anchor zone (terminals + fan stacks)
lastAnchorRow+1 .. y0+h-2   W→E trunk zone   (forward ribbons, eastward)
```

**Key invariant** (the one that caught us twice):
> `chipH` must satisfy `3 + ewOff + spacing*(n-1) + 2 + anchorDepth + weTrunkCount ≤ chipH`
> where `n = max(nLeft, nRight)` and all values are derived from `ewTopOffset_get`.

**Shared-node constraint**: `process()` appears as child of five proxy nodes.
It has one `(x, y)` position, one `chipH`, one `geometry` record.
`geometry.leftWallRows` stores *unique* rows only (sovereign centering collapses
five parents to one row per signal name).

**`modeMerge` contract**: must be `False` at the start of every `chip_render`
call and restored to `False` on every exit path (use `try/finally`).

**`pass_through` vs `flow`**: `pass_through=True` on `vline()` is real and
necessary (external wire channels must produce `┼` at crossings).  `flow=`
is dead code (both branches are byte-identical); it will be deleted in Phase 6c.

**`portSide_get` disambiguation rule**: when src and dst share the same name
(e.g. `"s1:s1"` pass-through), call `portSide_get(src)` without `prefer`
(→ "L") and `portSide_get(dst, prefer="R")` (→ "R").  The `prefer` arg breaks
the tie so same-name pairs resolve to opposite walls.

### 0.4 Which Tests to Run as a Sanity Check

```bash
# Quick smoke test (< 0.5 s)
python -m pytest tests/ -q

# Render the canonical hub topology
python -m signalflow examples/hub.yaml | head -60
```

Both must pass / produce clean output before starting any phase.

---

## 1. Problem Statement (Concrete)

### 1.1 The Four Independent `ewOff` Call-Sites

`ewTopOffset_get(node)` is called independently from four places, each making
slightly different assumptions about the result:

| Call-site | File | Use |
|---|---|---|
| `chipH_precompute` | `tree.py` | adds ewOff to lastWallReturnOffset |
| `layout_compute` | `layout.py` | shifts left-wall entryRows/returnRows |
| `chip_render` | `chips.py` | shifts right-wall base rows |
| `wireForward_render` / `wireReturn_render` | `wires.py` | computes exitY / parentRetY |

A change to the formula propagates to all four sites simultaneously.  There is
no single computed record that all four read from.

### 1.2 Three Approximations of "Straight-Through"

The straight-through predicate (a pair routed as a full-width hline, no
manifold) is implemented three times with progressively weaker conditions:

| Site | Conditions |
|---|---|
| `chips.py` | `srcCounts==1` AND `dstCounts==1` AND `sSide!=dSide` AND **`sRow==dRow`** |
| `layout.py / chipOw_compute` | `srcCounts==1` AND `dstCounts==1` AND `_side!=side` (no row check) |
| `tree.py / ewTopOffset_get` | `srcCounts==1` AND `dstCounts==1` (no side or row check) |

`chipOw_compute` can declare a chip "all straight-through" and return minimum
width for a chip that chips.py renders as a full manifold — producing a chip too
narrow for its own wiring.  Not yet triggered because current examples have
aligned rows, but not guaranteed.

### 1.3 `portSide_get` Duplicated

`chips.py` defines `portSide_get(name, prefer)`.  `layout.py` defines a
local `_side(name, prefer)` that is semantically identical but separately
maintained.  If one drifts, width computations diverge from rendering silently.

### 1.4 `lCounts` Computed Differently

`chips.py` builds `lCounts` from `wiringPairs` (the manifold subset, after
straight-through filtering).  `layout.py` builds `lCounts` from all pairs
before filtering.  `vLeft`/`vRight` in `chipOw_compute` therefore overcounts
longitude density, producing chips wider than necessary.

### 1.5 `rightBaseRows` Never Persisted

Right-wall port rows are computed inside `chip_render` and discarded.
`wires.py` independently recomputes them.  If `ewOff` or `pSpacing` selection
differs between chips.py and wires.py by even one row, wire exit-points and
chip port-rows are on different rows — a disconnect that produces no error.

### 1.6 Node Conflates Semantic and Layout State

`Node` carries both semantic fields (`module`, `func`, `input_ports`,
`internal_wiring`, …) set at parse time, and layout fields (`x`, `y`, `chipH`,
`entryRows`, …) zero-initialised and set later.  Nothing prevents `chip_render`
being called before `layout_compute`; the render proceeds silently on zero
geometry.

### 1.7 `entryRow`/`returnRow` Shims Lie for Shared Nodes

```python
n.entryRow = next(iter(n.entryRows.values()))  # first parent only
```

For `process()` with five parents this holds data for one caller only.  Any
code reaching for `node.entryRow` on a shared node is silently wrong for four
of its five callers.

### 1.8 `inputExplicit` Three-Valued Logic Not Resolved at the Node

`inputExplicit: bool | None` — `None` means "defer to global config".  Every
branch in the codebase checks `node.inputExplicit is False` directly.  If
`inputExplicit is None` and `config.chipIoInputExplicit = False`, the node
silently fails to apply sovereign centering.  There is no query property that
resolves `None → config`.

### 1.9 Silent Out-of-Bounds Writes

```python
# canvas.py
if not (0 <= y < self.rows and 0 <= x < self.cols):
    return   # silent no-op
```

The v3.2.7 trunk-overflow bug produced zero output.  Trunk rows were silently
dropped.  This turned a two-line formula error into a multi-session debugging
problem.

### 1.10 `modeMerge` Has No Guard Against Exception-Path Leak

`chip_render` sets `canvas.modeMerge = True` and resets it at exit.  The
post-render DRC assertion (section 2.10) sits between them.  If the assertion
fires, `modeMerge` is never reset.  All subsequent chips render in merge mode,
producing wrong glyph algebra that looks like a completely different bug.

### 1.11 `vline` `flow` Parameter Is Dead Code

Both branches of the `flow == "down"` / `else` condition in `canvas.vline()`
produce byte-for-byte identical intent assignments.  The parameter is accepted,
passed throughout `chips.py` with `flow="up"` and `flow="down"`, and does
nothing.  It creates false confidence that direction controls stub formation.

### 1.12 Latent Bug: `passThroughAllowed=False` Breaks `ewTopOffset_get`

When `passThroughAllowed=False`, `chips.py` routes all pairs through the
manifold (no unit-port bypass).  But `ewTopOffset_get` still excludes
`srcCounts==1 AND dstCounts==1` pairs as "straight-through candidates."  For a
proxy chip with `r1:r1`, `ewOff` would be 0 but the rendering would allocate a
trunk row — misaligning the E→W zone and the external leads.

### 1.13 Latent Bug: `list.index()` in `node_fromDict` Misbinds Repeated Children

```python
childIdx = d.get("calls", []).index(cDict)  # first occurrence always
```

If a parent calls the same child twice, both get `childIdx=0` and bind to the
same output port.  The second call is silently mis-wired.

---

## 2. Solution: `ChipGeometry`

A single authoritative dataclass, computed once per node, stored on `Node`,
read by all downstream pipeline stages.

### 2.1 Proposed API

```python
# src/signalflow/models/chip_geometry.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalflow.models.node import Node


@dataclass
class ChipGeometry:
    """Single authoritative source for all chip-interior geometry.

    Lifecycle
    ---------
    Stage 1  (pre-y, structural):
        ChipGeometry.build_structural(node) → sets ewOff, chipH, chipOw,
        leftNames, rightNames, approxStraight.  Called during layout_compute
        before y is assigned.  All fields are wiring-only; no canvas coords.

    Stage 2  (post-y, positional):
        geo.resolve(y0, entryRows, returnRows) → sets leftWallRows,
        rightWallRows, straightPairs, wiringPairs, lCounts, unitPorts,
        portToX, anchorFloor, interiorMax, allAnchorRows.  Called by
        layout_compute immediately after y is assigned.

    All rendering code (chips.py, wires.py) reads from the resolved geometry.
    No rendering code recomputes geometry from node fields.
    """

    # ── back-reference ────────────────────────────────────────────────────
    node: Node

    # ── Stage 1: structural (wiring-only) ─────────────────────────────────
    ewOff:        int = 0   # E→W trunk rows at top of chip interior
    chipH:        int = 0   # total chip height in rows
    chipOw:       int = 0   # outer width (border-to-border)
    leftNames:    set[str] = field(default_factory=set)   # input port names
    rightNames:   set[str] = field(default_factory=set)   # output port names
    isExplicit:   bool = True   # resolved inputExplicit (None → config)

    # ── Stage 2: positional (requires y0) ─────────────────────────────────
    resolved:       bool = False
    y0:             int  = 0

    leftWallRows:   dict[str, list[int]] = field(default_factory=dict)
    rightWallRows:  dict[str, list[int]] = field(default_factory=dict)

    # Post full 4-condition straight-through classification:
    straightPairs:  list[tuple[str, str]] = field(default_factory=list)
    wiringPairs:    list[tuple[str, str]] = field(default_factory=list)

    # Manifold-only longitude density (post straight-through filtering):
    lCounts:    dict[str, int] = field(default_factory=dict)
    unitPorts:  set[str]       = field(default_factory=set)

    # Longitude column assignment:
    portToX:    dict[str, int] = field(default_factory=dict)
    leftZoneInnerX:  int = 0
    rightZoneInnerX: int = 0

    anchorFloor:  int = 0   # y0 + 3 + ewOff
    interiorMax:  int = 0   # y0 + chipH - 2

    allAnchorRows: dict[str, list[int]] = field(default_factory=dict)

    # ── Stage 1 factory ───────────────────────────────────────────────────
    @classmethod
    def build_structural(cls, node: Node) -> ChipGeometry:
        """Compute wiring-only geometry before y is known."""
        ...

    # ── Stage 2 resolver ──────────────────────────────────────────────────
    def resolve(
        self,
        y0: int,
        entryRows: dict[int, int],
        returnRows: dict[int, int],
    ) -> None:
        """Compute all positional geometry once y is known."""
        ...

    # ── Canonical queries (replace portSide_get and _side) ────────────────
    def port_side(self, name: str, prefer: str | None = None) -> str | None:
        """Return 'L' or 'R' for a port name.  Single implementation."""
        ...

    def wall_row(self, name: str) -> int:
        """Return the absolute wall row for a manifold port name."""
        ...

    def is_signal(self, name: str) -> bool:
        """True if name is a forward signal (not a return)."""
        ...
```

### 2.2 What `build_structural` Computes

All values derivable from `node.internal_wiring`, `node.input_ports`,
`node.output_ports`, and `config` — without `node.y`:

1. `leftNames`, `rightNames` — from `input_ports`/`output_ports`
2. `isExplicit` — resolves `node.inputExplicit is None → config.chipIoInputExplicit`
3. `ewOff` — canonical formula: count E→W pairs excluding straight-through
   candidates (`srcCounts==1 AND dstCounts==1`), respecting
   `config.passThroughAllowed`
4. `chipH` — from `ewOff`, `spacing`, `n`, anchor depth, trunk count
5. `approxStraight` — 3-condition approximation (no row check; for chipOw only)
6. `chipOw` — from approxStraight, lCounts approx, label widths

### 2.3 What `resolve` Computes

All values that require `y0` (and therefore must follow column/row assignment):

1. `leftWallRows` — built from `entryRows`/`returnRows` (sovereign or explicit)
2. `rightWallRows` — `y0 + 3 + ewOff + spacing*i + offset`
3. `straightPairs` / `wiringPairs` — full 4-condition straight-through
   (`srcCounts==1 AND dstCounts==1 AND side!=side AND sRow==dRow`)
4. `lCounts` — manifold-only, from `wiringPairs` only
5. `unitPorts` — `lCounts[port]==1` when `passThroughAllowed`
6. `portToX`, `leftZoneInnerX`, `rightZoneInnerX` — longitude zone columns
7. `anchorFloor` = `y0 + 3 + ewOff`
8. `interiorMax` = `y0 + chipH - 2`
9. `allAnchorRows` — per-port anchor stacks (upward for signals, downward
   for returns), clamped to `[anchorFloor, interiorMax]`

### 2.4 Node Changes

```python
# node.py — add one field
geometry: ChipGeometry | None = None

# Add resolution property (replaces raw inputExplicit checks everywhere)
@property
def isInputExplicit(self) -> bool:
    if self.inputExplicit is None:
        return config.chipIoInputExplicit
    return self.inputExplicit
```

---

## 3. What Gets Eliminated

| Current code | Replaced by |
|---|---|
| `tree.py / ewTopOffset_get` | `ChipGeometry.ewOff` (Stage 1) |
| `tree.py / chipH_precompute` | `ChipGeometry.chipH` (Stage 1) |
| `layout.py / chipOw_compute` | `ChipGeometry.chipOw` (Stage 1) |
| `chips.py / portSide_get` (local) | `node.geometry.port_side()` |
| `layout.py / _side` (local) | `node.geometry.port_side()` |
| `chips.py` lCounts computation | `node.geometry.lCounts` |
| `layout.py` lCounts computation | `node.geometry.lCounts` |
| `chips.py` leftBaseRows / rightBaseRows | `node.geometry.leftWallRows / rightWallRows` |
| `chips.py` straight-through classification | `node.geometry.straightPairs / wiringPairs` |
| `chips.py` unitPorts computation | `node.geometry.unitPorts` |
| `chips.py` allAnchorRows computation | `node.geometry.allAnchorRows` |
| `chips.py` portToX computation | `node.geometry.portToX` |
| `wires.py` `ewTopOffset_get` import + exitY formula | `node.geometry.rightWallRows[port][idx]` |
| `canvas.vline` `flow` parameter | deleted (dead code) |
| `node.inputExplicit is False` checks (×3 files) | `node.isInputExplicit` |

---

## 4. Test Plan (TDD-First)

All tests in this section are written **before** the implementation phases.
They define the contract that `ChipGeometry` must satisfy.  Most will fail on
the current code — that is expected and intentional.

### 4.1 `tests/test_chip_geometry.py` — Geometry Invariants

These are the pre-render geometry contracts.  They do not test visual output.

```
TestEwOff
  test_no_wiring_returns_zero
      node with no internal_wiring → ewOff == 0
  test_straight_through_pair_excluded
      s1:s1 / r1:r1 proxy chip → ewOff == 0
  test_fan_in_all_counted
      hub process() with ret1..ret5:r1 (dstCounts["r1"]==5) → ewOff == 5
  test_mixed_straight_and_manifold
      chip with one straight-through E→W pair and one fan-in pair
      → ewOff counts only the fan-in pair
  test_pass_through_disabled_counts_all
      passThroughAllowed=False → even single-occurrence E→W pairs counted

TestChipH
  test_chipH_fits_all_right_wall_rows
      for every output port i: y0 + 3 + ewOff + spacing*i + 1 <= y0 + chipH - 2
  test_chipH_fits_we_trunk_rows
      lastAnchorRow + weTrunkCount <= y0 + chipH - 2
  test_chipH_not_less_than_base_leaf
      chipH >= config.baseLeafHeight always
  test_chipH_includes_ew_offset
      node with ewOff>0: chipH > same-node chipH with ewOff=0

TestChipOw
  test_straight_through_chip_minimum_width
      all-straight chip → chipOw == labelW + 2
  test_manifold_chip_wider_than_label
      manifold chip → chipOw >= 12 + leftLabel + rightLabel + 2*(vL+vR)
  test_chipOw_consistent_with_portToX
      portToX values lie within [x0+4+maxLeftLabel, rx-4-maxRightLabel]

TestStraightThrough
  test_four_condition_predicate
      srcCounts==1 AND dstCounts==1 AND side!=side AND sRow==dRow → straight
  test_row_mismatch_not_straight
      all conditions except sRow!=dRow → goes to wiringPairs, not straightPairs
  test_same_side_not_straight
      srcCounts==1, dstCounts==1, but both on same wall → wiringPairs
  test_chipOw_and_chips_agree_on_classification
      for every node: straightPairs from geometry == straightPairs used in chip_render

TestWallRows
  test_left_wall_rows_match_entry_rows
      leftWallRows[signal] == [entryRows[pid]] for each parent
  test_right_wall_rows_start_at_ew_offset
      rightWallRows for first output port → y0 + 3 + ewOff
  test_right_wall_rows_match_wires_exit_y
      for every parent→child: geometry.rightWallRows[signal][0]
      == exitY computed by wires.py (no recomputation)

TestAnchorRows
  test_anchor_floor_respected
      all anchor rows >= anchorFloor = y0 + 3 + ewOff
  test_interior_max_respected
      all anchor rows <= interiorMax = y0 + chipH - 2
  test_signal_anchors_above_wall_row
      signal port anchor stack: rows < wallRow (upward, unless flipped)
  test_return_anchors_below_wall_row
      return port anchor stack: rows > wallRow (downward, unless flipped)
  test_unit_port_anchor_equals_wall_row
      unitPort anchor row == wallRow exactly
  test_no_duplicate_anchor_rows
      len(set(allAnchorRows[port])) == len(allAnchorRows[port])
  test_anchor_count_matches_lcount
      len(allAnchorRows[port]) == lCounts[port]

TestZoneNonOverlap
  test_ew_zone_does_not_overlap_wall_terminals
      E→W trunk rows ∈ [y0+3, anchorFloor-1]
      wall terminal rows ∈ [anchorFloor, interiorMax]
      intersection must be empty
  test_we_zone_below_anchor_stack
      W→E trunk rows > all anchor rows > anchorFloor
  test_longitude_zones_fit_within_chip
      portToX values: leftLongStart <= x <= rightLongStart
      leftZoneInnerX <= rightZoneInnerX (latitude zone non-negative)
```

### 4.2 `tests/test_chip_geometry_integration.py` — Pipeline Consistency

```
TestConsistencyAcrossPipeline
  test_ewoff_same_in_all_callsites
      render hub.yaml; for each node verify:
        node.geometry.ewOff == ewTopOffset_get(node)  [regression guard]
  test_right_wall_rows_match_chip_render
      render hub.yaml; inspect canvas at rightWallRows positions;
      verify ├/┤/─ glyphs are present (port rows were actually drawn)
  test_right_wall_rows_match_wire_exit
      for each parent→child pair: geometry.rightWallRows[signal][0]
      matches the y-coordinate where the wire exits the parent chip wall
  test_chipH_no_canvas_overflow
      render hub.yaml; for each node verify chipH-derived rows
      all lie within canvas.rows
  test_chipOw_no_manifold_clip
      for all manifold nodes: portToX[rightmost] < rx-1
      (longitude columns fit within chip borders)

TestSharedNodeGeometry
  test_shared_node_single_geometry_record
      process() node has exactly one geometry object shared by all
      five proxy callers; geometry.ewOff, chipH, chipOw are consistent
  test_implicit_centering_geometry
      inputExplicit=False node: leftWallRows has exactly one unique row
      for all parents (sovereign centering)
```

### 4.3 `tests/test_invariants.py` — Pre-Render Assertion Harness

```
TestPreRenderInvariants
  test_all_nodes_have_resolved_geometry
      after layout_compute: every node.geometry is not None and resolved
  test_modeMerge_false_after_chip_render
      after chip_render for any node: canvas.modeMerge == False
  test_modeMerge_false_after_thread_render
      after thread_render: canvas.modeMerge == False
  test_canvas_no_silent_overflow
      render with deliberately undersized canvas; confirm ValueError raised
      (tests that out-of-bounds writes are not silently dropped in debug mode)
```

### 4.4 `tests/test_latent_bugs.py` — Regression Guards for Known Latent Issues

```
TestPassThroughDisabled
  test_proxy_chip_ewoff_with_pass_through_false
      passThroughAllowed=False; proxy chip r1:r1 → ewOff==1 (trunk needed)
  test_proxy_chip_chipH_with_pass_through_false
      chipH accounts for ewOff==1 when passThroughAllowed=False

TestInputExplicitResolution
  test_none_defers_to_config_false
      node.inputExplicit=None, config.chipIoInputExplicit=False
      → node.isInputExplicit == False
  test_none_defers_to_config_true
      node.inputExplicit=None, config.chipIoInputExplicit=True
      → node.isInputExplicit == True
  test_explicit_overrides_config
      node.inputExplicit=True, config.chipIoInputExplicit=False
      → node.isInputExplicit == True

TestVlineFlowDeadCode
  test_flow_up_identical_to_flow_down
      vline(..., flow="up") and vline(..., flow="down") produce identical
      intent masks — confirms dead code before removal
```

---

## 5. Migration Phases

All phases maintain a passing test suite throughout.  Never proceed to the next
phase with a failing test.

---

### Phase 0: Test Infrastructure [prerequisite]

Write all tests in §4.  Most will fail.  This is the contract.

- `tests/test_chip_geometry.py`
- `tests/test_chip_geometry_integration.py`
- `tests/test_invariants.py`
- `tests/test_latent_bugs.py`

Gate: tests exist and can be run (even failing is OK at this stage).

---

### Phase 1: `ChipGeometry` Skeleton + Stage 1

**New file**: `src/signalflow/models/chip_geometry.py`

Implement `build_structural(node)`:
- Consolidate `ewTopOffset_get` logic here (respecting `passThroughAllowed`)
- Consolidate `chipH_precompute` logic here
- Consolidate `chipOw_compute` logic here
- Implement `port_side`, `is_signal`, `wall_row` query methods

**`node.py`**:
- Add `geometry: ChipGeometry | None = field(default=None, init=False)`
- Add `isInputExplicit: bool` property (resolves `None → config`)

**`layout.py / layout_compute`** — replace:
```python
# Before
n.ow   = chipOw_compute(n)
n.chipH = chipH_precompute(n, isRoot=(n == root))
# After
n.geometry = ChipGeometry.build_structural(n)
n.ow   = n.geometry.chipOw
n.chipH = n.geometry.chipH
```

Keep `chipH_precompute`, `ewTopOffset_get`, `chipOw_compute` alive as thin
wrappers (delegate to `ChipGeometry`) until all call-sites are migrated.

Gate: all 95 existing tests still pass.  New `TestChipH`, `TestChipOw`,
`TestEwOff` in `test_chip_geometry.py` now pass.

---

### Phase 2: Stage 2 — `resolve()`

**`layout.py / layout_compute`** — after y assignment, call resolve:
```python
for n in nodes:
    n.geometry.resolve(
        y0=n.y,
        entryRows=n.entryRows,
        returnRows=n.returnRows,
    )
```

`resolve` computes: `leftWallRows`, `rightWallRows`, full straight-through
classification, `lCounts`, `unitPorts`, `portToX`, `anchorFloor`,
`interiorMax`, `allAnchorRows`.

Note: `entryRows`/`returnRows` must already be populated before `resolve` is
called.  The sovereign centering computation in `layout_compute` stays where it
is (it correctly sets `entryRows`/`returnRows` for `inputExplicit=False` nodes
before this call).

Gate: `TestWallRows`, `TestAnchorRows`, `TestZoneNonOverlap`,
`TestStraightThrough` tests pass.

---

### Phase 3: Migrate `chips.py`

`chip_render` is the largest consumer.  Replace each locally-computed block
with a read from `node.geometry`:

| Remove from `chip_render` | Read from instead |
|---|---|
| `portSide_get` inner function | `node.geometry.port_side()` |
| `leftBaseRows` / `rightBaseRows` computation | `node.geometry.leftWallRows / rightWallRows` |
| `_ewTopOffset_get(node)` call + `ewOff` | `node.geometry.ewOff` |
| straight-through classification block | `node.geometry.straightPairs / wiringPairs` |
| `lCounts` computation | `node.geometry.lCounts` |
| `portToX` computation | `node.geometry.portToX` |
| `unitPorts` computation | `node.geometry.unitPorts` |
| `allAnchorRows` computation | `node.geometry.allAnchorRows` |
| `anchorFloor` / `interiorMax` | `node.geometry.anchorFloor / interiorMax` |

`chip_render` becomes a pure renderer: it receives a node with fully-resolved
geometry and draws segments.  It computes nothing about chip interior layout.

Remove: `from signalflow.lib.tree import ewTopOffset_get as _ewTopOffset_get`

Fix `modeMerge` leak:
```python
# Wrap manifold rendering in try/finally
canvas.modeMerge = True
try:
    ...  # all manifold rendering
finally:
    canvas.modeMerge = False
```

Gate: all 95 existing tests pass.  `TestConsistencyAcrossPipeline` passes.

---

### Phase 4: Migrate `wires.py`

Replace the independent `exitY`/`parentRetY` recomputation:

```python
# Before
exitY = parent.y + 3 + ewTopOffset_get(parent) + pSpacing * idx
# After — read from geometry, no recomputation
exitY = parent.geometry.rightWallRows[pPort.signal][0]  # or [idx] for multi-lane
```

Similarly for `parentRetY` using `rightWallRows[pPort.ret]`.

Remove: `from signalflow.lib.tree import ewTopOffset_get`

Gate: all 95 existing tests pass.  `test_right_wall_rows_match_wire_exit` passes.

---

### Phase 5: Delete Redundant Code

With all call-sites migrated, delete:

- `tree.py`: `ewTopOffset_get`, `chipH_precompute`
- `layout.py`: `chipOw_compute`, `_side` local function, `ewTopOffset_get`
  import
- `chips.py`: `portSide_get` inner function, all locally-computed geometry
  blocks (already cleared in Phase 3)

If any test breaks, a call-site was missed.

Gate: all tests pass.  `grep -r "ewTopOffset_get" src/` returns zero results.

---

### Phase 6: Fix Latent Bugs

Each is independent; order doesn't matter.

**6a. `passThroughAllowed=False` / `ewOff` alignment**
`ChipGeometry.build_structural` now owns `ewOff` computation and has access to
`config.passThroughAllowed`.  When `False`, do not apply the
`srcCounts==1 AND dstCounts==1` exclusion.  Covered by `TestPassThroughDisabled`.

**6b. `node.isInputExplicit` property**
Already added in Phase 1.  Replace all `node.inputExplicit is False` checks in
`chips.py`, `tree.py` (remaining uses), and any other files.

**6c. Remove `vline` `flow` parameter**
Delete the `flow` parameter from `canvas.vline()`.  Remove all `flow=` keyword
args from callers.  The `pass_through` parameter remains (it does real work).

**6d. Fix `list.index()` in `node_fromDict`**
```python
# Before
childIdx = d.get("calls", []).index(cDict)
# After
for childIdx, cDict in enumerate(d.get("calls", [])):
    ...
```

**6e. Canvas out-of-bounds noise**
Add a debug-mode assertion:
```python
# canvas.py
if not (0 <= y < self.rows and 0 <= x < self.cols):
    if __debug__:
        raise IndexError(f"Canvas write out of bounds: ({x},{y}) in {self.cols}×{self.rows}")
    return
```
This converts the silent trunk-overflow class of bug into an immediate IndexError
pointing at the formula.

Gate: `TestLatentBugs`, `TestInputExplicitResolution` pass.

---

### Phase 7: Pre-Render Invariant Assertions

Add `geometry_validate(nodes)` in `src/signalflow/lib/geometry_validate.py`:

```python
def geometry_validate(nodes: list[Node]) -> None:
    """Assert all geometry invariants before rendering begins.

    Called by diagram_render() after layout_compute and resolve().
    Raises AssertionError with a precise diagnostic on the first violation.
    """
    for n in nodes:
        geo = n.geometry
        assert geo is not None and geo.resolved, f"{n.func}: geometry not resolved"

        # 1. chipH contains all right-wall rows
        for port, rows in geo.rightWallRows.items():
            for row in rows:
                assert geo.anchorFloor <= row <= geo.interiorMax, (
                    f"{n.func}: right wall row {row} for port {port!r} "
                    f"outside [{geo.anchorFloor}, {geo.interiorMax}]"
                )

        # 2. E→W trunk zone does not overlap wall terminals
        ew_zone = set(range(n.y + 3, geo.anchorFloor))
        terminal_rows = {r for rows in geo.rightWallRows.values() for r in rows}
        overlap = ew_zone & terminal_rows
        assert not overlap, (
            f"{n.func}: E→W zone {ew_zone} overlaps terminal rows {overlap}"
        )

        # 3. Anchor floors respected
        for port, rows in geo.allAnchorRows.items():
            for row in rows:
                assert geo.anchorFloor <= row <= geo.interiorMax, (
                    f"{n.func}: anchor row {row} for {port!r} outside bounds"
                )

        # 4. No duplicate anchor rows per port
        for port, rows in geo.allAnchorRows.items():
            assert len(set(rows)) == len(rows), (
                f"{n.func}: duplicate anchor rows for {port!r}: {rows}"
            )

        # 5. lCounts matches allAnchorRows
        for port, cnt in geo.lCounts.items():
            if port in geo.unitPorts:
                continue
            assert len(geo.allAnchorRows.get(port, [])) == cnt, (
                f"{n.func}: lCounts[{port!r}]={cnt} but "
                f"allAnchorRows has {len(geo.allAnchorRows.get(port, []))}"
            )
```

Call from `diagram_render`:
```python
layout_compute(root, cw)
geometry_validate(nodes)   # ← new: loud, early, precise
for box in boxes:
    moduleBox_render(canvas, box, nodes)
for n in nodes:
    chip_render(canvas, n)
```

Gate: `TestPreRenderInvariants` passes.

---

## 6. File Map After Completion

```
src/signalflow/
├── models/
│   ├── node.py              ← +geometry field, +isInputExplicit property
│   ├── chip_geometry.py     ← NEW: authoritative geometry class
│   └── canvas.py            ← -flow param from vline; +debug OOB assert
├── lib/
│   ├── layout.py            ← calls ChipGeometry.build_structural + resolve;
│   │                           removes chipOw_compute, _side, ewTopOffset import
│   ├── chips.py             ← reads from node.geometry; no local geometry;
│   │                           try/finally for modeMerge; pure renderer
│   ├── wires.py             ← reads rightWallRows; removes ewTopOffset import
│   ├── tree.py              ← removes ewTopOffset_get, chipH_precompute
│   └── geometry_validate.py ← NEW: pre-render invariant assertions
└── engine/
    └── render.py            ← calls geometry_validate after layout_compute
```

---

## 7. What Does NOT Change

- `VLSIRouter` / `canvasCoords_resolve` — still used for W1-W5 path resolution
- `OccupancyGrid` / `trackClear_check` — still available (currently unused)
- `LayoutJoiner` glyph algebra — unchanged
- `hline_pierce` / `hline_force` — unchanged
- `pass_through` parameter on `vline` — unchanged (it does real work)
- All manifold rendering logic (W1–W5 drawing segments) — unchanged
- Anchor label overlay (section 2.9) — unchanged
- Post-render DRC (section 2.10) — retained but becomes a redundant
  double-check (geometry_validate fires first with better diagnostics)
- All YAML parsing and Node construction — unchanged except the `list.index()` fix
- All existing tests — must continue to pass throughout

---

## 8. Risk Assessment

### What I am confident about

**Phases 0-2 (tests + Stage 1 + Stage 2):** High confidence.  `ChipGeometry`
consolidates logic that already exists; it's extraction, not invention.  The
formulas are known and correct.  The test suite provides a hard gate at each
phase.

**Phase 5 (deletion):** High confidence.  Deleting code that has been migrated
away is mechanical.  Test failures pinpoint missed call-sites.

**Phases 6-7 (latent bugs + invariants):** High confidence.  Each fix is
independent and well-scoped.  The invariant framework is the most valuable
deliverable for future velocity.

### Where the real risk lives

**Phase 3 (migrate `chips.py`):**  This is the hardest phase.  `chip_render`
is 600 lines with geometry computation interleaved with rendering.  Three
specific interaction risks:

1. **Manifold corner formation.**  `┌`/`┐`/`└`/`┘` corners emerge algebraically
   from `vline` endpoint stubs merging with `hline_pierce` endpoints.  This
   depends on the exact order of draws and the `modeMerge` state.  The geometry
   extraction must not reorder any draw operations.

2. **`portToX` / longitude zone columns.**  Currently computed mid-render.
   Moving this to `ChipGeometry.resolve()` is straightforward but the exact
   formula (including the `leftZoneInnerX`/`rightZoneInnerX` boundaries) must
   be reproduced identically.

3. **The `unitPorts` bypass paths** (section 2.6.5 and 2.9 `continue`
   statements).  These read from `unitPorts` during rendering.  If `unitPorts`
   in `ChipGeometry` differs by even one port from what `chip_render` computed
   locally, anchor buses and labels will be wrong for those ports.

**Mitigation**: The `TestConsistencyAcrossPipeline` and
`TestStraightThrough.test_chipOw_and_chips_agree_on_classification` tests
explicitly cross-check that `ChipGeometry` classifications match what
`chip_render` would have computed.  Phase 3 proceeds only after those tests
pass.

**Phase 4 (migrate `wires.py`):**  Medium risk.  The `exitY` formula in
`wires.py` currently indexes `parent.output_ports.keys()` to find port order.
`ChipGeometry.rightWallRows` must store rows in the same port-iteration order
that `chips.py` uses for `rightBaseRows`, or wire exit rows and chip port rows
will be off by one port.  Covered by `test_right_wall_rows_match_wire_exit`.

### Velocity risk

The TDD-first approach (Phase 0) is the critical enabler.  Without invariant
tests, Phase 3 is the same whack-a-mole situation as v3.2.x.  With them, any
regression is caught at the invariant level (which formula is wrong) rather
than the visual level (something looks wrong somewhere).

The single largest velocity risk is attempting Phase 3 without Phase 0
complete.  That must not happen.

### My overall assessment

This is achievable.  The refactor is large (~800 lines of new/changed code
across 7 files) but it is mechanically clear: extract, consolidate, verify,
delete.  Every phase has a concrete, testable gate.  The geometry is already
correct (v3.2.7 produces correct output) — we are not changing what is
computed, only where.

The outcome eliminates the entire class of "formula changed in one place,
three other places didn't know" bugs permanently.  Any future formula change
touches exactly one method in `ChipGeometry`; all rendering code reads the
result.  Invariant violations fail loudly before a single glyph is drawn.

---

## 9. Acceptance Criteria

1. `geometry_validate(nodes)` passes silently for all existing example YAML
   files (`show-cohort.yaml`, `hub.yaml`, `passthrough.yaml`, `explicit-hub.yaml`)
2. All 95 existing tests pass
3. All new tests in `test_chip_geometry.py`, `test_chip_geometry_integration.py`,
   `test_invariants.py`, `test_latent_bugs.py` pass
4. `grep -r "ewTopOffset_get" src/` → zero results
5. `grep -r "chipH_precompute" src/` → zero results
6. `grep -r "chipOw_compute" src/` → zero results
7. `grep -r "portSide_get\|def _side" src/` → zero results
8. `grep -r "inputExplicit is False" src/` → zero results (replaced by `isInputExplicit`)
9. `canvas.vline` has no `flow` parameter
10. Visual output of all example YAML files is byte-identical to v3.2.7 output
