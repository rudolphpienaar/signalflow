# SignalFlow Execution Plan: World-Scale `extra` Routing

**Date:** March 31, 2026
**Branch:** `worldscale-extra-routing`
**Version:** `5.9.12`
**Status:** `extra` perimeter frames + transfer regions placed and verified; sf1 route geometry is next

## Phase 1: Preserve Current Truth Surfaces ✓ COMPLETE

Goal: do not lose the executable surfaces that made the current arc tractable.

1. Keep the board-era runtime path authoritative:
   - `BoardChip`
   - `BoardKernel`
   - `Board`
   - `BoardSolution`
   - `BoardMaterializedSolution`
2. Keep the REPL/snippet path healthy.
3. Keep geometry/materialization inspectable.
4. Do not regress current policy surfaces:
   - chip placement
   - materialization relaxation

Deliverable: ✓

- `snippets/algebraic/hub_internal_geometry.py` — chip internal board geometry
- `snippets/algebraic/zone_1_1_geometry.py` — zone (1,1) intra geometry (new)
- both run clean against `examples/hub.yaml`

## Phase 1b: Board Geometry Flush Work ✓ COMPLETE

This phase was not originally planned but was a prerequisite for `extra` work.

`extra` channels must be placeable immediately adjacent to `intra` lane edges.
That required the `intra` substrate geometry to be flush with the module
bounding boxes — no gaps.

Work completed:

- module bounding box padding made asymmetric by sense side
  (interior-facing edge has zero padding; outer three sides have `pad`)
- chip terminal and fan frames extended to cover full module bounding box
  vertical extent in both WTE/ETW and NTS/STN branches
- longitude band sizing decoupled from centroid shift — bands always resize
  to match the extended terminal frame extents
- NORTH/SOUTH dummy chip terminal and fan frames stacked correctly outside
  the longitude territory

Verified against `zone_1_1_geometry.py`: longitude bands flush with module
box edges; north/south dummies correctly separated.

## Phase 2a: Zone Truth Surface Anchor ✓ COMPLETE

Goal: ground all subsequent geometry doctrine in verified snippet output,
not prose alone.

1. Run the zone geometry truth surface:
   ```
   python -m signalflow examples/hub.yaml --run-snippet snippets/algebraic/zone_1_1_geometry.py
   ```
2. Use that output to determine exact row/column positions for where
   `xwLong`, `xnLat`, `xeLong`, `xsLat` would live relative to the
   verified zone (1,1) geometry.
3. Extend `docs/worldscale_geometry.adoc` with:
   - an explicit geometry figure showing `extra` frame positions
   - exact row/column positions for each `extra` family
   - explicit transfer region shapes at each `intra ↔ extra` interface corner

Deliverable:

- `docs/worldscale_geometry.adoc` extended with verified `extra` frame geometry

Do not touch builder code until this is documented.

## Phase 2b: `BoardGeometrySpec` Design Doctrine (DNC) ✓ COMPLETE

Goal: design a first-class parameterization object that drives board
construction, so geometry is no longer an emergent product of builder
heuristics alone.

This is a doctrine-only phase. No builder code until Phase 5.

### Two-Phase Pipeline

**Phase 2b-i: Geometric Analyzer (chip-driven, produces minimums)**

A first-pass analyzer reads current chip geometry and derives hard lower
bounds. The spec cannot go below these without breaking physical fit.

Analyzer outputs (minimum constraints):

| Parameter | Source |
|---|---|
| `minWChipTerminalSpan` | chip west frame column width |
| `minEChipTerminalSpan` | chip east frame column width |
| `minWFanSpan` | intra west wire count (signal + return + spacing) |
| `minEFanSpan` | intra east wire count |
| `minWLongSpan` | intra west longitude capacity |
| `minELongSpan` | intra east longitude capacity |
| `minXwLongSpan` | extra west channel width (policy constant initially) |
| `minXeLongSpan` | extra east channel width (policy constant initially) |
| `latRows` | intra signal count — nLat = sLat = signal count, symmetric |

`latRows` is not overridable by the spec — it is fully determined by signal
count. North carries signals, south carries returns. Both row counts are
equal. A rendering flag may suppress drawing return lines but the geometry
always reserves the lanes.

**Phase 2b-ii: Spec Builder (zone config + analyzer minimums → concrete geometry)**

The zone config (or `BoardGeometrySpec` object) provides explicit span
values. The builder takes `max(explicit, minimum)` for each span.

### Spec Parameter Surface

Free user/config knobs (each subject to its analyzer minimum):

- `wChipTerminalSpan` — west chip terminal column width
- `eChipTerminalSpan` — east chip terminal column width
- `wFanSpan` — west fan in/out column width
- `eFanSpan` — east fan in/out column width
- `wLongSpan` — west intra longitude column width
- `eLongSpan` — east intra longitude column width
- `xwLongSpan` — west extra longitude column width
- `xeLongSpan` — east extra longitude column width
- `latLength` — total horizontal column span of the lat region
  (a single knob; controls both nLat and sLat, which are always equal)

Rendering flags (geometry reserved regardless of flag value):

- `renderReturnLines` (default True) — if False, south lat lines not drawn
  but row lanes still reserved

### Derived Quantities (not free parameters)

Transition zones are emergent from the overlap of lat and long regions. They
are not independently specified. Their column extent = `wLongSpan` on the
west and `eLongSpan` on the east. Their row extent = lat band height.

`innerCourtYardSpan` is a layout gap, not a named region. It is fully
determined by:

```
innerCourtYardSpan = latLength − wLongSpan − eLongSpan
```

`latLength` is the user-facing knob. The builder derives `innerCourtYardSpan`
internally. `innerCourtYardSpan` must be > 0; the minimum `latLength` is
therefore `wLongSpan + eLongSpan + 1` (degenerate) — a reasonable floor
should be enforced above that.

nLat column extent = sLat column extent = `latLength` (one knob, not two).

### Horizontal Stack And Cascade Arithmetic

Anchor: the west edge of `xwLong` is the fixed reference point.

Layout stack (west to east):

```
xwLong | wChipTerminal | wFan | wLong | innerCourtYard | eLong | eFan | eChipTerminal | xeLong
       ↑___________________________ lat spans ___________________________↑
                              (lat = wLong + courtyard + eLong)
```

Every region's `horizontalStart` is computed by accumulating spans rightward
from the `xwLong` anchor. Changing any span cascades through all regions to
its east. There are no gaps between adjacent regions in the stack.

### Open Questions For Phase 2b

- `xnLat` and `xsLat` spans — extra north/south lat families not yet
  discussed in detail; their row extents and horizontal spans need doctrine
- Demand-driven `extra` capacity expansion: when does `xwLongSpan` grow?
- Whether `latRows` ever needs asymmetry (e.g., more return rows for
  against-sense traffic) or whether symmetric is always correct

Deliverable:

- an explicit spec surface documented in `docs/worldscale_geometry.adoc`
  or a new `docs/boardgeometryspec.adoc`, ready to be backed by runtime

## Phase 2c: Formalize `extra` As Geometry Doctrine ✓ COMPLETE

Goal: move `extra` from design note into explicit geometric doctrine, using
the verified frame positions from Phase 2a and the spec model from Phase 2b.

1. Define the `extra` families for a WTE kernel:
   - `xwLong`
   - `xnLat`
   - `xeLong`
   - `xsLat`
2. Define transfer regions between `intra` and `extra` using the verified
   frame positions as the concrete anchor.
3. Decide whether transfer regions are new `RegionFamily` entries or
   special cases of existing transition doctrine.
4. Define what it means for `extra` capacity to expand demand-driven.

Deliverable:

- a concrete geometry proposal that can be represented in runtime objects

## Phase 3: Formalize Symbolic Algebra Across `intra` And `extra`

Goal: describe routes that leave `intra`, travel in `extra`, and re-enter.

1. Describe child-to-parent routing in `sfN`.
2. Describe child-to-self routing in `sfN`.
3. Describe world-scale long-haul routing in `sfN`.
4. Identify where row/layer identity must be preserved across the `extra` perimeter.

Deliverable:

- explicit route narratives that can later be compiled into solver obligations

## Phase 4: Reconcile `extra` With World Construction

Goal: determine how local kernels compose at world scale.

Open alternatives:

- retain current disjoint-zone model and add `extra`
- explore overlapping zones while still keeping `extra`
- hybridize the two if needed

The immediate priority is not to choose prematurely. The priority is to make the geometry and algebra of `extra` explicit enough that the trade can be evaluated honestly.

Deliverable:

- a world-construction doctrine note, or an extension to `docs/worldscale_geometry.adoc`

## Phase 5: Runtime Introduction

Goal: only after doctrine is explicit, introduce runtime changes.

Likely work:

- new board/routing doctrine enums if needed
- new region families in geometry
- new transfer-region builders
- extension of materialized geometry dumps
- extension of symbolic/wiring narratives

Deliverable:

- runtime changes that are backed by geometry and snippet evidence, not speculative prose

## Current Immediate Next Step

Board geometry is now correct. The module bounding box edge is the natural
attach point for `extra` channels.

Proceed to Phase 2. The first task:

- use `snippets/algebraic/zone_1_1_geometry.py` output as the concrete anchor
- sketch the minimal region frame additions for `xwLong`, `xnLat`, `xeLong`,
  `xsLat` relative to the verified geometry above
- document transfer region geometry before touching builders
