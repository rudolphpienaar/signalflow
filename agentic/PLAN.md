# SignalFlow Execution Plan: World-Scale `extra` Routing

**Date:** March 31, 2026
**Branch:** `worldscale-extra-routing`
**Version:** `5.9.10`
**Status:** board geometry flush work complete; `extra` region definition is next

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

## Phase 2: Formalize `extra` As Geometry Doctrine

Goal: move `extra` from design note into explicit geometric doctrine.

1. Define the `extra` families for a WTE kernel:
   - `xwLong`
   - `xnLat`
   - `xeLong`
   - `xsLat`
2. Define the transfer regions between `intra` and `extra`.
3. Define whether the transfer regions are new region families or special cases of existing transition doctrine.
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
