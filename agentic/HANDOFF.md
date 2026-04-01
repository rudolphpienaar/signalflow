# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.12`
- Branch point commit: `07c46b4` (`Add papers and worldscale geometry notes`)

## What Just Happened

### v5.9.12 — `intra ↔ extra` transfer regions

Four explicit transfer regions placed at the corners where intra longitude
bands meet the extra latitude bands. Changes in `src/signalflow/board/`:

- `types.py`: added `RegionFamily.INTRA_EXTRA_TRANSFER`
- `render.py`: corner box-drawing glyphs — `╔` NW, `╗` NE, `╚` SW, `╝` SE
- `builders.py`: transfer computation in `_extraGeometry_build`; keyed by
  `(side=EAST|WEST, branch=NORTH|SOUTH)` — e.g. `east/intra_extra_transfer:north` = NE

#### Verified Transfer Frame Positions (zone 1,1)

| Region | col | row | span |
|---|---|---|---|
| west/intra_extra_transfer:north (NW) | 45..54 | −3..3  | 10w × 7h |
| east/intra_extra_transfer:north (NE) | 65..74 | −3..3  | 10w × 7h |
| west/intra_extra_transfer:south (SW) | 45..54 | 46..52 | 10w × 7h |
| east/intra_extra_transfer:south (SE) | 65..74 | 46..52 | 10w × 7h |

Each transfer spans from inside the extra latitude (rows −3..0 / 49..52)
to inside the intra longitude upper/lower band top/bottom row. This
provides explicit overlap with both regions, satisfying the doctrine that
transfer ownership must be first-class, not implied by adjacency.

Geometry ownership overlaps are intentional per NON-NEGOTIABLES:
"Geometry ownership may overlap; route occupancy may not."

### v5.9.11 — `extra` perimeter frame placement

The four `extra` region families are now live in the board geometry for
WTE/ETW kernels. All changes are in `src/signalflow/board/`:

- `types.py`: added `RegionFamily.EXTRA_LONGITUDE` and `RegionFamily.EXTRA_LATITUDE`
- `render.py`: added glyph assignments (`▏`/`▕` for extra longitude, `▔`/`▁` for extra latitude)
- `builders.py`: added `_extraGeometry_build` function; called from `board_buildFromKernel`
  after `_effectiveGeometry_build`

Also: `docs/worldscale_geometry.adoc` extended with:
- Verified intra frame table from `zone_1_1_geometry.py` snippet output
- Proposed `extra` frame positions (formulas + concrete numbers)
- Board expansion requirement doctrine
- `BoardGeometrySpec` design doctrine section
- All ASCII figures converted to Unicode box-drawing/arrow glyphs

#### Verified `extra` Frame Positions (zone 1,1, default spans 6/6/4/4)

| Region | col start | col end | row start | row end |
|---|---|---|---|---|
| west/extra_routing_longitude  |  13 |  18 | −3 | 52 |
| east/extra_routing_longitude  | 105 | 110 | −3 | 52 |
| north/extra_routing_latitude  |  13 | 110 | −3 |  0 |
| south/extra_routing_latitude  |  13 | 110 | 49 | 52 |

Key properties verified:
- All four families present and non-overlapping
- Longitude families span full outer perimeter height (includes xnLat/xsLat rows)
- Latitude families span full outer perimeter width (includes xwLong/xeLong cols)
- `xeLong` starts at col 105 — east of east module boundary (col 104), not east of chip terminal (col 97)
- Intra substrate completely untouched

#### Spans Are Hardcoded Defaults For Now

`xwLongSpan=6, xeLongSpan=6, xnLatSpan=4, xsLatSpan=4` are defaults in
`_extraGeometry_build`. When `BoardGeometrySpec` is implemented (Phase 2b
implementation, not yet started) these will be driven by the spec object.

### v5.9.10 — Board geometry flush + `extra` doctrine

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

The immediate next task is Phase 2a (see `agentic/PLAN.md`):

1. Run `snippets/algebraic/zone_1_1_geometry.py`
2. Use the output as the concrete anchor for `extra` frame positions
3. Extend `docs/worldscale_geometry.adoc` with an explicit geometry figure

Do not touch builder code until that documentation step is complete.

## `BoardGeometrySpec` Design (DNC — doctrine established, not yet coded)

A `BoardGeometrySpec` abstraction was designed in the previous session. It is
a first-class parameterization object that drives board construction. Nothing
is implemented; this is doctrine only.

### Two-Phase Pipeline

1. **Geometric analyzer** — reads chip geometry, derives hard minimum span
   constraints (not overridable below minimum).
2. **Spec builder** — takes zone config knobs + analyzer minimums, emits
   concrete geometry via `max(explicit, minimum)` per span.

### Free Spec Knobs

`wChipTerminalSpan`, `eChipTerminalSpan`, `wFanSpan`, `eFanSpan`,
`wLongSpan`, `eLongSpan`, `xwLongSpan`, `xeLongSpan`, `latLength`.

Each is subject to its analyzer-derived minimum.

### `latLength`

Single knob controlling both nLat and sLat horizontal extent (they are always
equal — one column range, not two). North carries signals, south carries
returns, symmetric row counts derived from signal count. A `renderReturnLines`
flag may suppress drawing return lines but geometry always reserves the lanes.

### Derived / Emergent Quantities

- `innerCourtYardSpan = latLength − wLongSpan − eLongSpan` — a layout gap,
  not a named region. Not a free parameter.
- Transition zones — emergent from lat/long overlap; not independently
  specified. No transition span term exists in the accumulation arithmetic.
- nLat column extent = sLat column extent = `latLength` (one knob).

### Horizontal Stack And Cascade Arithmetic

Anchor: west edge of `xwLong` is the fixed reference point. Spans accumulate
rightward. Changing any span cascades through all regions to its east.

```
xwLong | wChipTerminal | wFan | wLong | innerCourtYard | eLong | eFan | eChipTerminal | xeLong
       ↑________________________ lat spans __________________________↑
```

### Open Design Questions (not yet resolved)

- `xnLat` / `xsLat` extra north/south lat spans — not yet discussed
- Demand-driven extra capacity expansion policy
- Whether `latRows` ever needs asymmetry for against-sense traffic

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
