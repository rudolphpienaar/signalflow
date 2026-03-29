# Doctrine

This file defines the active doctrine for symbolic kernel routing.

## Core Split

The routing stack is split into three responsibilities:

1. geometry builds the board
2. the symbolic solver builds the algebraic path
3. the materializer converts the algebraic path into route geometry

The solver must not directly invent world coordinates.

This split also sits inside a broader substrate/operator doctrine documented in `SUBSTRATE-AND-OPERATORS.md`.

## Board

The board is the fixed legal routing substrate derived from realized geometry.

The board defines:

- the canonical kernels in a zone
- the canonical channels in a kernel
- the lane counts and lane ordering inside each channel
- the legal transitions between adjacent substrates

Once the board is built, bends and transitions are unique consequences of the board, not independent solver choices.

## Canonical Names

Every notation-participating object must have a canonical symbolic name.

Current direction:

- zone
  - `z(1,1)`
- kernel
  - `ki`, `kw`, `ke`, `kn`, `ks`
- channel
  - `wLong`, `eLong`, `nLat`, `sLat`
- lane
  - `[1]`, `[2]`, ...
- fan slot
  - `wf[0]`, `ef[0]`, and later higher vane slots

Canonical names compose by scope:

- kernel-local
  - `nLat[3]`
- zone-local
  - `ki.nLat[3]`
- world-local
  - `z(1,1).ki.nLat[3]`

## Lane Doctrine

Lanes are indexed per channel.

Lane ordering follows global world coordinates:

- origin is top-left
- `x` increases to the right
- `y` increases downward
- vertical-channel lanes increase west-to-east
- horizontal-channel lanes increase north-to-south

Lane numbering is geometric, not directional.

## Fan Doctrine

Fan slots are not travel lanes.

Examples:

- `wf[0]`
- `ef[0]`

`[0]` currently means the terminal-aligned/default slot.

Higher indices are reserved for future fan-vane materialization when multiple wires must converge through an explicit fan structure.

## Algebraic Path Doctrine

The symbolic path is the authoritative solver output.

Example:

```text
App.ts.main().s1::wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]::Proxy.ts.p1().s1
```

The solver chooses the path symbolically according to packing rules and board legality.

The materializer then realizes it geometrically.

## Replacement Doctrine

Direct geometry-solving logic is legacy.

The target architecture is:

- board builder
- symbolic solver
- materializer

The symbolic effort is a replacement architecture, not a long-term coexistence plan with the legacy direct-coordinate solver.
