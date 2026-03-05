# Project Context: SignalFlow - Architectural Schematic Compiler

SignalFlow is a mathematically rigorous ASCII diagramming engine that synthesizes execution traces into high-fidelity schematics. It treats the canvas as a **VLSI Routing Fabric** governed by deterministic geometric laws.

## Mandatory Architectural Pillars

### 1. Geometric Terminator Algebra
The `LayoutJoiner` is the algebraic core. It uses 16-character bitmasks to resolve directional "intent" (N, S, E, W) into topological states. It handles both single-line and double-line (`║`, `═`) piercings reactively. Manual character-stamping is prohibited.

### 2. Physical Synthesis Paradigm (Silicon-on-ASCII)
The engine has moved from heuristic drawing to **Manifold Synthesis**. See `REQUIREMENTS.md` for the geometry-first implementation contract.
- **Internal Anchors:** Every logical thread MUST be rooted in an explicit internal label (e.g., `s2►`) written as a sovereign overlay **flush against the chip wall** (`x0+1` left, `rx-1-len` right). Anchor labels carry a `►`/`◄` directionality arrow on the interior-facing edge. Input anchors stack **upward** from the wall port row; output anchors stack **downward**.
- **Dedicated Trunk Zones:** E→W (return) trunks occupy the **top zone** (`y0+3` … `y0+3+n_ew-1`). W→E (forward) trunks occupy the **bottom zone** (`y0+h-2-n_we` … `y0+h-3`). Trunk row = Anchor row; W2/W4 doglegs are zero-length. A neutral bus connects the external wall port row to the trunk zone row.
- **Fully Colored Tracks:** All five waypoint segments (W1–W5) carry the thread's color. There are no neutral/colorless thread segments.
- **Exclusive Cell Ownership:** Every `(x,y)` cell on a thread's path is owned exclusively by that thread. Point crossings (`┼`) are the only permitted coincidences.
- **Trunk Row Isolation:** Trunk rows are pre-allocated into dedicated top/bottom zones before rendering. No W→E trunk may land in the E→W zone and vice versa. Straight-through wall port rows are seeded into `used_rows`.
- **Manhattan Grid:** Traces follow a wall→bus→trunk→bus→wall journey with `AttachmentSense`-governed lane allocation per `algorithm.pseudo.logic`.

### 3. Absolute Non-Coincidence
Zero horizontal or vertical segment coincidence is an ironclad mandate.
- **Monochromatic Traces:** Every colored segment must have exactly one color code. Color shifts mid-trace are a catastrophic failure.
- **DRC Engine:** The `OccupancyGrid` performs Design Rule Checks to prove 0 overlaps before output.

## Current System State
- **Stable:** 16-character algebra and reactive piercing engine.
- **Implemented:** `src/signalflow/engine/router/` containing the VLSI primitives and logic.
- **Partial (Phase 4):** `chips.py` has W3 bounded to latitude zone, per-side `chip_ow_compute`, anchor-row seeding in `used_rows`, and direction-correct anchor stacks. Known remaining issues: "shared bus at bottom" (trunk overflow), "ladder" artifact (labels at `x0+2` instead of flush `x0+1`), no directionality arrows.
- **In Focus (Phase 5):** Dedicated top/bottom trunk zones, flush-wall anchor labels with `►`/`◄` directionality arrows, and updated `chip_h_precompute` formula. See `PLAN.md` § Phase 5 and `REQUIREMENTS.md` for full contract.

## Core Module Map
- `src/signalflow/lib/layout_joiner.py`: The algebraic brain.
- `src/signalflow/engine/router/router.py`: The synthesis orchestrator.
- `src/signalflow/engine/router/occupancy.py`: The DRC engine.
- `docs/internalWiring.adoc`: The formal scientific specification of the framework.
- `docs/algorithm.pseudo.logic`: The lane/channel allocation pseudocode (`AttachmentSense`, `AttachmentPolicy`).
- `docs/InternalWiring.drawio`: The geometric aspiration — spatial model that must be reproduced.
- `REQUIREMENTS.md`: The geometry-first implementation contract (read before any manifold coding).
