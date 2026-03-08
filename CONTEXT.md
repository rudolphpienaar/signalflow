# Project Context: SignalFlow — ASCII Call-Thread Diagram Engine

SignalFlow converts recursive call-tree YAML into 2D ASCII diagrams showing
forward calls (left→right) and returns (right←left) as wires routed through
function chips grouped by module.

---

## Where We Are (Phases 0–5 complete)

The `ChipGeometry` consolidation plan is **halfway done**.  A single
authoritative geometry dataclass (`ChipGeometry`) now owns all chip-interior
geometry.  No rendering code recomputes geometry independently.

**Test baseline**: `python -m pytest tests/ -q` → **144 passed, 4 xfailed**

The 4 xfailed tests document two latent bugs that Phase 6 will fix:
- §1.12 (`passThroughAllowed=False` breaks `ewOff`) — 3 xfail tests
- §1.13 (`list.index()` misbinds repeated children) — 1 xfail test

**Next task**: Phase 6 (fix latent bugs) — read `PLAN.md §Phase 6` for specs.

---

## Architecture: Two-Stage Geometry Pipeline

```
Parse (node_fromDict)
  → tree_flatten + col_assign
  → channelWidth_compute
  → layout_compute
      ├─ ChipGeometry.build_structural(node)   [Stage 1: chipH, chipOw, ewOff]
      ├─ x/y assignment
      ├─ entryRows/returnRows assignment
      └─ geo.resolve(node, y, entryRows, returnRows)  [Stage 2: wallRows, anchors]
  → chip_render × N    [pure renderer; reads node.geometry]
  → thread_render      [reads node.geometry.ewOff]
  → ASCII output
```

**ChipGeometry lifecycle**:
- **Stage 1** (`build_structural`): wiring-only fields set before `y` is known.
  Fields: `ewOff`, `chipH`, `chipOw`, `leftNames`, `rightNames`, `signalNames`,
  `isExplicit`.
- **Stage 2** (`resolve`): positional fields set after `y` and wall-rows are
  known.  Fields: `leftWallRows`, `rightWallRows`, `straightPairs`,
  `wiringPairs`, `lCounts`, `unitPorts`, `portToX`, `leftZoneInnerX`,
  `rightZoneInnerX`, `anchorFloor`, `interiorMax`, `allAnchorRows`.

---

## Key Invariants (must not be violated)

1. **`chipH` contract**: `3 + ewOff + portVerticalSpacing*(n-1) + 1 ≤ chipH - 2`
   where `n = max(nLeft, nRight)` and all values come from `node.geometry`.
2. **E→W trunk zone**: rows `[y+3, anchorFloor)` must not overlap right-wall
   terminal rows `[anchorFloor, interiorMax]`.
3. **`modeMerge` contract**: `canvas.modeMerge` must be `False` at the start
   and end of every `chip_render` call (enforced by `try/finally`).
4. **Single geometry record**: a shared node (e.g. `process()` called by 5
   proxies) has exactly one `geometry` object.  `leftWallRows` stores unique
   rows only (sovereign centering collapses N parents to one row per name).

---

## Core Module Map

| File | Role | Status |
|---|---|---|
| `src/signalflow/models/chip_geometry.py` | Authoritative geometry — Stage 1 + Stage 2 | ✅ complete |
| `src/signalflow/models/node.py` | Node dataclass; `isInputExplicit` property | ✅ complete |
| `src/signalflow/models/canvas.py` | 2D grid; `modeMerge`; `vline` (has dead `flow=` param) | 🔲 Phase 6c |
| `src/signalflow/lib/layout.py` | Pipeline orchestrator; calls build_structural + resolve | ✅ complete |
| `src/signalflow/lib/chips.py` | Pure chip renderer; reads `node.geometry` | ✅ complete |
| `src/signalflow/lib/wires.py` | Wire renderer; reads `parent.geometry.ewOff` | ✅ complete |
| `src/signalflow/lib/tree.py` | `tree_flatten`, `tree_depth`, `subtreeCanvasH_calculate` | ✅ complete |
| `src/signalflow/config.py` | All geometry constants (`Config` singleton) | unchanged |
| `src/signalflow/engine/render.py` | Top-level pipeline (`diagram_render`) | 🔲 Phase 7 hook |
| `src/signalflow/engine/router/router.py` | VLSIRouter — W1–W5 path synthesis | unchanged |
| `src/signalflow/lib/layout_joiner.py` | Glyph algebra (bitmask N/S/E/W merge) | unchanged |

---

## What Was Eliminated (Phases 1–5)

| Deleted | Replaced by |
|---|---|
| `tree.py / ewTopOffset_get` | `node.geometry.ewOff` |
| `tree.py / chipH_precompute` | `node.geometry.chipH` |
| `layout.py / chipOw_compute` | `node.geometry.chipOw` |
| `chips.py / portSide_get` (local fn) | `node.geometry.port_side()` |
| `layout.py / _side` (local fn) | `node.geometry.port_side()` |
| All local geometry blocks in `chips.py` | `node.geometry.*` reads |
| `ewTopOffset_get` import in `wires.py` | `parent.geometry.ewOff` in formula |

---

## What Remains (Phases 6–7)

**Phase 6** — Fix latent bugs (see `PLAN.md §Phase 6` for exact code):

| Sub-phase | File | Bug | Xfail guard |
|---|---|---|---|
| 6a | `chip_geometry.py / _ewOff_compute` | Ignores `passThroughAllowed=False` | 3 tests in `test_chip_geometry.py` + `test_latent_bugs.py` |
| 6c | `canvas.py / vline()` | `flow=` parameter is dead code | `TestVlineFlowConfirmedDead` |
| 6d | `node.py / node_fromDict` | `list.index()` misbinds repeated children | `TestRepeatedChildPortBinding` |
| 6e | `canvas.py` | Silent OOB writes mask formula bugs | no xfail (add assert) |

**Phase 7** — `geometry_validate()` pre-render assertions:
- New file: `src/signalflow/lib/geometry_validate.py`
- Called from `engine/render.py` after `layout_compute`
- Spec in `PLAN.md §Phase 7`

---

## Quick Sanity Check

```bash
# Must show 144 passed, 4 xfailed before starting any Phase 6 work
python -m pytest tests/ -q

# Render the canonical hub topology
python -m signalflow examples/hub.yaml | head -60
```
