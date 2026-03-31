# Project Context: SignalFlow — Board-Era Runtime And World-Scale Routing

This file is the current architectural baseline for agent work on this branch.

## Current Architectural State

- Branch: `worldscale-extra-routing`
- Version: `5.9.8`
- Base commit on this branch: `07c46b4`
- Current major runtime path is the board-era path, not the older `rearch-zone-grid` kernel-only path documented in stale notes.

## What Is Current Truth

- `chips.chip_get(...)` returns a real `BoardChip`.
- `chip.internalBoard_get()` returns a real `BoardKernel`.
- `kernel.board_get(...)` constructs a `Board`.
- `kernel.board_get(chipPlacementPolicy=...)` supports placement policy at board-construction time.
- `solution.board_materialize(board, policy=...)` is the canonical realization/materialization API.
- `BoardMaterializePolicy` and `BoardRelaxationSymmetry` are real runtime policy surfaces.
- `BoardChipPlacementPolicy` is a real runtime policy surface.
- The REPL and snippets are part of the architecture. They are not convenience-only tooling.

## What Was Recently Stabilized

- Internal chip routing now flows through a real board/kernel solve/materialize path.
- WTE board geometry is re-anchored from live placed terminal centroids before realization.
- Symmetric relaxation is only meaningful once the board geometry has a valid live axis.
- `docs/worldscale_geometry.adoc` captures the current thinking for the next macro step.
- `papers/new_ways.adoc` explains the collaboration method that produced the current runtime and REPL truth surfaces.

## Important Runtime APIs

- `chip.geometry_get()`
- `chip.geometry_text()`
- `chip.internalBoard_get()`
- `kernel.board_get(chipPlacementPolicy=...)`
- `board.chipPlacementPolicy_set(...)`
- `kernel.solver_get(board)`
- `solver.solution_get()`
- `solution.board_materialize(board, policy=...)`

## Important Snippets

- `snippets/algebraic/hub_internal_wiring.py`
  - prints internal-board geometry, wiring, collisions
- `snippets/algebraic/hub_internal_geometry.py`
  - prints board geometry text, region frames, terminal world positions

These are truth surfaces. Use them before making architectural claims.

## Current Macro Design Direction

The next major work is not a local polish pass. It is a world-scale routing rethink.

The strongest current synthesis is:

- one local kernel owns an inner `intra` routing substrate
- the same kernel also owns an outer `extra` routing substrate
- `extra` is concentric perimeter routing, not a new seam object and not a new placed kernel
- `intra` and `extra` must connect through explicit transfer regions

This direction is described in:

- `docs/worldscale_geometry.adoc`

## What Is No Longer Current

Treat these as historical unless explicitly reconciled with current board-era code:

- branch assumptions in old `rearch-zone-grid` notes
- old milestone counts like `566/0`
- seam-kernel plans as the primary next step
- chip-internal routing as the singular next architectural concern

The branch has moved past that. The next macro concern is world-scale geometry.

## Document Precedence

When there is tension between files, use this order:

1. `agentic/HANDOFF.md`
2. `agentic/ZEROSHOT.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `docs/worldscale_geometry.adoc`
5. `papers/new_ways.adoc`
6. `docs/ideas.adoc`
7. `docs/architecture.adoc`

## Mandatory Operating Rule

Do not claim an architectural property unless you can point to at least one of:

- the owning runtime API
- the file/function implementing it
- snippet output
- rendered geometry
- a test assertion

If the implementation is partial, say it is partial.
