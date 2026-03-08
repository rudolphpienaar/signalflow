Proceed autonomously with the following milestones, following a strict TDD cycle and RPN naming convention. You are an Architectural Compiler, not a diagramming assistant.

### MANDATE: PROHIBITED HEURISTICS
- NEVER use portVerticalSpacing as a "gap" to fill.
- NEVER route from a single point on a wall to multiple destinations.
- NEVER use character-stamping (┼) to "show" a port.
- NEVER minimize vertical space at the expense of logical anchors.

### MANDATE: PHYSICAL SYNTHESIS
- **Internal Anchors:** Every logical thread MUST have an explicit signalName label rendered inside the chip wall at a unique row. These are the "Pins."
- **Grouped Bands:** Latitude Channels MUST be grouped by signal name. All s2 threads must occupy a contiguous horizontal band.
- **Neutral Bus:** All segments on shared physical rows (external to internal riser) MUST be color-neutral.
- **Zero Coincidence:** Every single colored segment MUST have a 100% unique (x,y) coordinate.

### EXECUTION STEPS
1. **Refactor Fabric Grouping:** Update `router.py` to organize Latitude Channels into multi-lane bands based on signal name.
2. **Implement Anchor Stacking:** Update `chips.py` to render the vertical array of internal labels for each port.
3. **Waterfall Journey:** Implement the 5-waypoint routing between specific anchors using the grouped fabric.
4. **Validation:** Perform a raw `repr()` monochromatic trace audit of the `Hub.ts:process()` manifold.

**Constraints:**
- Maintain 100% type hinting and style compliance (ruff check).
- Truth over Layout: If the Density Law requires a 100-row chip, the chip WILL be 100 rows.
