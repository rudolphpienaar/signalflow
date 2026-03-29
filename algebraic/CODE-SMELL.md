# Code Smell

This file tracks known code smell and architectural debt that is relevant to the symbolic kernel routing effort but is not on the immediate critical path.

## Current Placement Debt

The current board-like geometry is materially encoded by fixed formulas and numeric offsets in `src/signalflow/routing/placement.py`.

That means the routing substrate already exists, but it exists implicitly rather than as a first-class board model.

The symbolic effort is currently allowed to consume that substrate as quarantine input.

That substrate is not accepted as the long-term architecture.

## Why This Is Smell

The present placement logic mixes geometric realization with routing meaning.

Named symbolic objects such as channels, lanes, fan slots, and legal transitions are not primary domain objects in the placement layer.

Instead, those objects are inferred later from region rectangles that were built by fixed formulas.

This creates debt because board semantics are buried inside low-level placement arithmetic rather than being expressed directly.

## Specific Smells

- Channel placement is formula-driven rather than board-driven.
- Latitude and longitude corridors are positioned by fixed layout doctrine rather than an explicit board builder.
- Routing meaning is reconstructed after the fact from realized geometry areas.
- Changing board doctrine currently implies editing hard-coded geometric formulas.
- The current geometry is pre-solve and useful, but it is not yet an explicit symbolic board.
- Multiple sources of truth for the same geometry fact are a recurring failure mode and must be actively checked.
- Chip stacking, chip world frames, terminal world positions, route placement maps, and render placement must not each carry their own independent spacing doctrine.
- If a geometry fact can be derived from an upstream authoritative object, downstream code should derive it rather than re-encode it.
- REPL/debug surfaces should expose authoritative geometry queries first so mismatches can be detected without reaching into internals.

## Multiple Sources Of Truth Note

This branch already surfaced one concrete example: chip terminal world positions drifted away from visible chip frames because attach-point stacking and rendered chip stacking were encoded separately.

That specific bug was fixed by centralizing chip stack span/offset doctrine, but the broader smell remains important.

Whenever two paths can answer the same geometry question, they must be treated as suspect until proven to share one common upstream source.

## Centroid Note

The current placement path is not centroid-driven.

If centroid-based channel placement becomes part of the active doctrine, that work belongs in board construction rather than in the symbolic solver.

The solver must consume a board.

The solver must not relocate the board.

## Accepted Temporary State

For the current quarantine phase, the existing placement geometry is accepted as an upstream substrate.

That acceptance is temporary and pragmatic.

It does not mean the fixed-formula placement architecture is the desired end state.

## Intended Replacement

The intended direction is:

1. realized geometry areas exist upstream
2. a board builder derives explicit board objects from those areas
3. the symbolic solver solves against the board
4. a materializer turns symbolic paths into realized route geometry

When that replacement is mature, board semantics should no longer have to be reverse-engineered from placement formulas.
