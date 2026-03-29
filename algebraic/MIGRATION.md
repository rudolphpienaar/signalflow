# Migration

This file defines the replacement plan for symbolic kernel routing.

## Goal

Replace direct coordinate-centric kernel solving with a symbolic routing stack that:

1. derives a board from geometry
2. solves symbolically on that board
3. materializes the symbolic result into route geometry

## Active Branch Contract

This branch is intentionally not governed by the archived legacy test suite.

Current default test authority lives under:

- `tests_symbolic/`

Historical tests have been moved to:

- `tests_legacy/`

Those tests remain available for reference, but they are not the default source of truth for the symbolic effort.

## Anti-Zombie Rule

The main architectural risk is codebase coexistence between:

- the old direct-geometry solver
- the new symbolic solver

That coexistence creates debt, duplicated abstractions, and tests that defend the wrong system.

So the migration rule is:

- replace responsibilities cleanly
- delete dead legacy code as soon as the symbolic replacement owns that job
- do not keep legacy pathways alive merely to preserve historical tests

## Planned Phases

### 1. Board Model

Build explicit board objects from kernel geometry.

This phase defines:

- canonical names
- kernels
- channels
- lanes
- fan slots
- legal transitions

### 2. Symbolic Path Model

Build explicit symbolic routing objects.

This phase defines:

- wires
- channel and lane references
- algebraic path records
- REPL/debug surfaces for symbolic routing

### 3. Solver Replacement

Replace direct coordinate solving in the kernel solver with symbolic path generation.

The materializer then converts symbolic paths into realized route points.

### 4. Legacy Deletion

Delete or privatize dead direct-geometry helpers, obsolete lane arithmetic, and stale debug/reporting helpers that only existed to support the old model.

## Required Test Focus

The symbolic suite should primarily verify:

- board construction
- canonical naming
- channel and lane ordering
- symbolic path generation
- materialization from symbolic path
- occupancy and non-overlap invariants

Tests should not preserve legacy helper structure as a branch constraint.
