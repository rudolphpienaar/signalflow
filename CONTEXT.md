# Project Context: SignalFlow — ASCII Call-Thread Diagram Engine

SignalFlow converts recursive call-tree YAML into 2D ASCII diagrams showing
forward calls (left→right) and returns (right←left) as wires routed through
function chips grouped by module.

---

## Where We Are (v5.1.1)

All architectural work and the computation-block visual vocabulary are complete.
The current release keeps the v5 internal-wiring and per-gap layout work, and
adds two renderer stability fixes:
- canonical/shared recursive nodes are traversed safely without infinite
  recursion during layout or wire rendering
- module boxes now participate in layout, remain non-overlapping, and always fit
  their title text

**Test baseline**: `python -m pytest tests/ -q` → **197 passed, 0 xfailed**

### Computation Block Visual Vocabulary (v5.0)

Three-state closed visual language:
- `▬` on a horizontal hline: pass-through with computation (default for `s1:s1`)
- `█` in vertical bracket / U-turn gap: computation between calls or in leaf
- Clean hline: pure relay — declared explicitly with `:pure` suffix (`s1:s1:pure`)
- No connection: ports not related in this diagram

Config: `implicitThread: "block"` (default) | `"none"` (legacy, no blocks).

Leaf chip geometry: 7 rows (was 6) — gap row at y+4 between entry (y+3) and
return (y+5).  Multi-call bracket: `┌──/█/└──` at `rx - uTurnWidth` on right
wall between consecutive call-return pairs, mirroring the leaf U-turn structure.

The `▬`/`█` characters are grounded in the IEC resistor symbol and in Mason SFG
non-unity branch gain semantics.  See `docs/architecture.adoc §The Visual Vocabulary`.

### Internal Wiring Semantics (v5.0)

Three routing changes are now part of the stable contract:
- Explicit same-wall right-wall return→signal handoffs reuse the old implicit
  bracket/block continuity rather than being forced through the manifold.
- `internal_wiring` accepts optional ordered orientation tokens
  `EW`, `WE`, `NS`, `SN`, with optional `:pure`.
- True manifold routing keys anchors and longitude columns by endpoint identity
  `(side, kind, label)` rather than by bare display label, so same-name pairs
  such as `constructedDecl:constructedDecl:EW` remain disambiguated all the way
  through the router.

Default input policy is now sovereign:
- `chipIoInputExplicit = false` by default
- chips only use per-caller west-side rows when explicitly opted into
- simple single-input chips still keep their standard local geometry

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
      └─ geo.resolve(node, y, entryRows, returnRows)  [Stage 2: wallRows, directives, anchors]
  → chip_render × N    [pure renderer; reads node.geometry]
  → thread_render      [reads node.geometry.ewOff]
  → ASCII output
```

**ChipGeometry lifecycle**:
- **Stage 1** (`build_structural`): wiring-only fields set before `y` is known.
  Fields: `ewOff`, `chipH`, `chipOw`, `leftNames`, `rightNames`, `signalNames`,
  `isExplicit`.
- **Stage 2** (`resolve`): positional fields set after `y` and wall-rows are
  known.  Fields: `leftSignalRows`, `leftReturnRows`, `rightSignalRows`,
  `rightReturnRows`, `leftWallRows`, `rightWallRows`, `straightDirectives`,
  `wiringDirectives`, `wallContinuities`, `lCounts`, `unitPorts`, `portToX`,
  `leftZoneInnerX`, `rightZoneInnerX`, `anchorFloor`, `interiorMax`,
  `allAnchorRows`.  The manifold-only maps are keyed by endpoint identity, not
  bare label.

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

The core architecture work is complete:

- ChipGeometry consolidation (Phases 0–7) — ✅
- Latent bug fixes (§1.12, §1.13, §1.8, dead-code removal, OOB assertion) — ✅
- Pre-render invariant harness (`geometry_validate`) — ✅
- Repeated-child port binding (`PortKey` model, `call_sequence`) — ✅

Possible future directions:
- Vertical packing / layout optimisation for very deep trees
- Column-width equalisation across rows
- Interactive diagram exploration (outside the current scope)
- See `dev_notes/BACKLOG_RENDERING.md` for deferred rendering work.

---

## Quick Sanity Check

```bash
# Current full-suite baseline
python -m pytest tests/ -q

# Render the canonical hub topology
python -m signalflow examples/hub.yaml | head -60
```
