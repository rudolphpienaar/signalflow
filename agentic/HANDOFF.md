# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.10`
- Branch point commit: `07c46b4` (`Add papers and worldscale geometry notes`)

## What Just Happened

This arc focused on making board geometry correct as a precondition for
`extra` channel placement. All runtime changes are in
`src/signalflow/board/builders.py`. A new truth-surface snippet was added.

### Lint Cleanup (`builders.py`)

Pre-existing ruff errors resolved:

- `F821`: `RoutingZoneRegionSide` used but not imported — added to the
  `signalflow.models` import block
- `I001`: import sort fixed (`BoardChipDrawPlacement` before `BoardRegionId`,
  `from dataclasses import replace` moved above first-party imports)
- `E501 × 9`: long lines broken at natural points; two `for chipName,
  chipPlacement in substrateGeometry.chipDrawPlacementsByChip.items()` loops
  gained a local `chipDrawPlacements` binding

### Module Bounding Box (`_effectiveBoundaryFramesByModule_build`)

Padding is now computed asymmetrically by sense side:

```python
topPad    = 0 if moduleSide is BoardSide.SOUTH else pad
bottomPad = 0 if moduleSide is BoardSide.NORTH else pad
leftPad   = 0 if moduleSide is BoardSide.EAST  else pad
rightPad  = pad  # always
```

The interior-facing edge of each module side has no padding on the
routing-facing dimension. The outer three sides get full `pad` clearance.

### Flush Routing Region Geometry (`_effectiveGeometry_build`)

WTE/ETW branch: chip terminal and fan frames are now extended to cover the
full vertical union of all their module boundary frames.

- `westBoundaryTop/Bottom` = union of all WEST module boundary vertical extents
- `eastBoundaryTop/Bottom` = union of all EAST module boundary vertical extents
- `CHIP_TERMINAL WEST`: vertical span extended to `[min(frame.top,
  westBoundaryTop), max(frame.bottom, westBoundaryBottom)]`
- `INTRA_FAN WEST`: new case — same vertical extension. **Critical**: applied
  after the horizontal shift by `westEnvelopeGrowthColumns`. Placing this case
  before the shift caused the fan to land inside the expanded chip terminal zone
  (the horizontal shift is what moves the fan right of the expanded terminal).
- `INTRA_FAN EAST`: new case on the shifted frame, same vertical treatment
- `CHIP_TERMINAL EAST`: vertical span extended against `eastBoundaryTop/Bottom`

NTS/STN branch: symmetric treatment. `northBoundaryTop/Bottom` and
`southBoundaryTop/Bottom` as unions. NORTH and SOUTH chip terminal and fan
frames extended vertically. `southBoundary` single-frame variable removed
(superseded by the union).

### Longitude Band Sizing Decoupled From Centroid Shift
(`_wtePlacedTerminalAxisFrames_build`)

Previously the function had two early-return guards (`rawShiftRows == 0`,
`shiftRows == 0`) that prevented longitude band resizing when no centroid
shift was needed. This left the bands at substrate size — 1 row short of
the now-extended terminal frame extents.

Restructured:

- `terminalTopRow` / `terminalBottomRow` computed unconditionally from the
  (post-`_effectiveGeometry_build`) WEST/EAST chip terminal frames
- Centroid shift applied only when `shiftRows != 0`
- Longitude band resize to `[terminalTopRow, terminalBottomRow]` always runs
- NORTH/SOUTH dummy chip terminal and fan frames stacked outside longitude
  territory: fan placed adjacent to the band edge, chip terminal outermost

Stacking logic for NORTH dummies:
```
northFanStart         = terminalTopRow - northFanFrame.verticalSpan
northTerminalStart    = northFanStart  - northTerminalFrame.verticalSpan
```
For SOUTH:
```
southFanStart         = terminalBottomRow + 1
southTerminalStart    = southFanStart + southFanFrame.verticalSpan
```

### New Snippet

`snippets/algebraic/zone_1_1_geometry.py` — mirrors `hub_internal_geometry.py`
but rooted at `zones.zone_get(1, 1).kernel_get("intra")`. Dumps geometry text,
region frames, and exact terminal world positions.

## Verified Geometry (zone 1,1, `hub.yaml`)

```
row  1   north/chip_terminal       (1h)
row  2   north/fan                 (1h)
row  3   longitude upper begins    flush with Proxy.ts module box top
row  3..15   west/east longitude upper
row 16..25   north lat + transitions
row 26..35   south lat + transitions
row 36..46   west/east longitude lower
row 46   longitude lower ends      flush with Proxy.ts module box bottom
row 47   south/fan                 (1h)
row 48   south/chip_terminal       (1h)
```

West chip terminal and fan are flush with the App.ts module box vertically.
East chip terminal and fan are flush with the Proxy.ts module box vertically.

## The Most Important Current Runtime APIs

- `chip: BoardChip = chips.chip_get("Hub.ts", "process()")`
- `kernel: BoardKernel = chip.internalBoard_get()`
- `board: Board = kernel.board_get(chipPlacementPolicy=...)`
- `solver: BoardSolver = kernel.solver_get(board)`
- `solution: BoardSolution = solver.solution_get()`
- `materialized: BoardMaterializedSolution = solution.board_materialize(board, policy=...)`
- `zones.zone_get(1, 1).kernel_get("intra")` → `BoardKernel`

## Snippets

- `snippets/algebraic/hub_internal_geometry.py` — internal chip board geometry
- `snippets/algebraic/zone_1_1_geometry.py` — zone (1,1) intra board geometry
- `snippets/algebraic/hub_internal_wiring.py` — internal chip wiring + collisions

## Current Design Direction

Board geometry is now a correct substrate for `extra` channel placement.
Chip terminal, fan, and longitude bands are all flush with their respective
module bounding boxes. The module bounding box edge is now the natural attach
point for `extra` channels — no gap exists between `intra` lane edges and the
box boundary.

Next step: define the `extra` region families (`xwLong`, `xnLat`, `xeLong`,
`xsLat`) and the transfer regions that connect them to `intra`. See
`docs/worldscale_geometry.adoc`.

## Hard Problem Still Unresolved

Child-to-self routing. A route leaving `p4()` into `extra` must preserve
enough row/layer identity to return specifically to `p4()`, not to the
parent-facing side of the zone. Do not hand-wave this.

## What Not To Trust

Stale `agentic/` notes mentioning `rearch-zone-grid`, `566/0`, seam kernels
as the settled next milestone, or chip-internal kernel as the singular concern.

## Operating Discipline

- if you are guessing, say so
- if something is partial, say so
- if a property is claimed, point to the runtime path or snippet output
- if the user says `DNC`, do not code
