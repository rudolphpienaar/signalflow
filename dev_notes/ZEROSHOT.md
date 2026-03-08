# Zero-Shot Quickstart: SignalFlow VLSI Synthesis

## 1. Topological Brain: `src/signalflow/lib/layout_joiner.py`
This module contains the **16-character Geometric Algebra**. 
- **Rule:** It resolves intersections based on directional intent (bitmasks).
- **Key:** `LayoutJoiner.MASK_TO_CHAR` maps bitmasks to glyphs (handling single and double lines).
- **Verification:** Never manual stamp; always use `canvas.hline_pierce` or `canvas.vline` with `mode_merge=True`.

## 2. Synthesis Core: `src/signalflow/engine/router/`
The router package implements the **Silicon-on-ASCII** fabric.
- **`models.py`**: Defines `Channel` (with `laneOccupancy` bitset) and `Waypoint`.
- **`router.py`**: Orchestrates density analysis (`fabric_init`) and 5-step Manhattan routing (`route_lay`).
- **`occupancy.py`**: High-resolution `OccupancyGrid` for collision detection.

## 3. Mandatory Verification: The Monochromatic Audit
To prove 0 horizontal coincidence (no color bleeding), run:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
python3 -m signalflow examples/explicit-hub.yaml > output.txt
# Scan output.txt for rows containing multiple unique ANSI color codes.
```

## 4. Architectural Target: `docs/internalWiring.adoc`
This is the **Ground Truth Specification**. Read it to understand:
- The **Internal Anchor** stacking requirement.
- The **Grouped Band** (Latitude Channel) logic.
- The **5-Step Manhattan Choreography**.

## 5. Critical Constraints
- **Zero Coincidence:** Two threads NEVER share a coordinate segment.
- **Strict RPN Naming:** `object_method` (e.g. `lane_allocate`, `canvas_coords_resolve`).
- **Typing:** 100% Python 3.11+ type hints.
