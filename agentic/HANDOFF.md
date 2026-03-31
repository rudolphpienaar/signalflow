# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.8`
- Branch point commit: `07c46b4` (`Add papers and worldscale geometry notes`)

## What Just Happened

The previous arc stabilized a board-era runtime path and turned the REPL/snippet surface into an architectural truth surface. This included:

- real runtime types such as `BoardChip`, `BoardKernel`, `Board`, `BoardSolution`, and `BoardMaterializedSolution`
- chip-internal boards solved through the same board/kernel infrastructure
- chip placement policy at `kernel.board_get(...)`
- realization/materialization policy at `solution.board_materialize(...)`
- WTE board geometry re-anchored from live placed terminal centroids before realization

This arc also produced two important documents:

- `docs/worldscale_geometry.adoc`
- `papers/new_ways.adoc`

## The Most Important Current Runtime APIs

These are real and should be treated as the authoritative interactive surface:

- `chip: BoardChip = chips.chip_get("Hub.ts", "process()")`
- `kernel: BoardKernel = chip.internalBoard_get()`
- `board: Board = kernel.board_get(chipPlacementPolicy=...)`
- `solver: BoardSolver = kernel.solver_get(board)`
- `solution: BoardSolution = solver.solution_get()`
- `materialized: BoardMaterializedSolution = solution.board_materialize(board, policy=...)`

There is also:

- `chip.geometry_get()`
- `chip.geometry_text()`

## Snippets You Should Use Immediately

1. `snippets/algebraic/hub_internal_wiring.py`

Purpose:

- show current internal-board render
- show wiring text
- show collisions

2. `snippets/algebraic/hub_internal_geometry.py`

Purpose:

- show current board geometry text
- dump region frames
- dump exact terminal world positions

These snippets are not optional niceties. They are how you falsify or support architectural claims.

## Current Design Direction

The next major work item is a world-scale routing rethink.

Current best synthesis:

- keep local kernel routing as `intra`
- add outer concentric perimeter routing families called `extra`
- connect `intra` and `extra` through explicit transfer regions

For WTE, the proposed symbolic `extra` families are:

- `xwLong`
- `xnLat`
- `xeLong`
- `xsLat`

The important claim is:

- `extra` is not a seam object
- `extra` is not another placed kernel
- `extra` is the same kernel's outer routing substrate

Read `docs/worldscale_geometry.adoc` before touching code.

## Hard Problem Still Unresolved

The easy story is child-to-parent reverse routing.

The hard story is child-to-self routing.

Why it is hard:

- the source child may be interior to a stacked column, such as `p4()`
- a route leaving that child into `extra` must preserve enough local row/layer identity to return to that same child
- naive west-side re-entry stories collapse to the parent-facing side, which is wrong for child-to-self

Do not hand-wave this. If you talk about child-to-self, make the row/layer preservation story explicit.

## What Not To Trust

Do not trust stale `agentic/` notes from older branches if they mention:

- `rearch-zone-grid`
- `566/0`
- seam kernels as the settled next milestone
- chip-internal kernel as the singular next work item

Those notes described an older arc. This branch is beyond that.

## Likely Next Work

The next good move is documentation-first, not solver-first.

Concretely:

1. Extend `docs/worldscale_geometry.adoc` with more explicit transfer-region figures.
2. Use the current WTE board geometry from `hub_internal_geometry.py` to sketch exactly where `extra` would live relative to:
   - west/east terminal regions
   - intra north/south latitudes
   - upper/lower longitudes
3. Decide whether transfer regions become:
   - new region families,
   - or a disciplined extension of current transition doctrine.
4. Only after that, touch runtime geometry builders.

## Operating Discipline

The user is highly sensitive to overclaiming and "AI slop."

This means:

- if you are guessing, say you are guessing
- if something is partial, say it is partial
- if a property is claimed, support it with code path or snippet evidence
- if the user says `DNC`, do not code

The fastest way to lose trust here is to sound coherent without being anchored in the runtime truth surface.
