# Project Context: SignalFlow — ASCII Call-Thread Diagram Engine

SignalFlow converts recursive call-tree YAML into 2D ASCII diagrams showing
forward calls (left→right) and returns (right←left) as wires routed through
function chips grouped by module.

---

## Where We Are — All known bugs fixed (v4.1.0)

All architectural work is complete.  The engine is correct for all call-tree
topologies, including parents that call the same child function more than once.

**Test baseline**: `python -m pytest tests/ -q` → **150 passed, 0 xfailed**

There are no open xfailed tests and no known outstanding bugs.  The next
work would be new features or the scaling limitations described in
`docs/architecture.adoc §Known Limitations`.

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
| `src/signalflow/models/node.py` | Node; `PortKey` type alias; `call_sequence` field; `isInputExplicit` | ✅ complete |
| `src/signalflow/models/canvas.py` | 2D grid; `modeMerge`; `vline`; OOB assert | ✅ complete |
| `src/signalflow/models/__init__.py` | Exports `Node`, `Canvas`, `ModuleBox`, `PortKey` | ✅ complete |
| `src/signalflow/lib/layout.py` | Pipeline orchestrator; PortKey-keyed port rows | ✅ complete |
| `src/signalflow/lib/chips.py` | Pure chip renderer; reads `node.geometry` | ✅ complete |
| `src/signalflow/lib/wires.py` | Wire renderer; `out_key`/`in_key` params; `call_sequence` traversal | ✅ complete |
| `src/signalflow/lib/geometry_validate.py` | Pre-render invariant harness | ✅ complete |
| `src/signalflow/lib/tree.py` | `tree_flatten`, `tree_depth`, `subtreeCanvasH_calculate` | ✅ complete |
| `src/signalflow/config.py` | All geometry constants (`Config` singleton) | unchanged |
| `src/signalflow/engine/render.py` | Top-level pipeline; calls `geometry_validate` | ✅ complete |
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

## What Remains

No open bugs.  All originally planned work is complete:

- ChipGeometry consolidation (Phases 0–7) — ✅
- Latent bug fixes (§1.12, §1.13, §1.8, dead-code removal, OOB assertion) — ✅
- Pre-render invariant harness (`geometry_validate`) — ✅
- Repeated-child port binding (`PortKey` model, `call_sequence`) — ✅

Possible future directions:
- Vertical packing / layout optimisation for very deep trees
- Column-width equalisation across rows
- Interactive diagram exploration (outside the current scope)

---

## Quick Sanity Check

```bash
# Must show 144 passed, 4 xfailed before starting any Phase 6 work
python -m pytest tests/ -q

# Render the canonical hub topology
python -m signalflow examples/hub.yaml | head -60
```
