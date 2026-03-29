# Board

This file defines the routing board used by symbolic kernel routing.

## Purpose

The board is the fixed legal routing substrate on which the symbolic solver operates.

The board is not a route result.
The board is not a wire list.
The board is not a rendered picture.

The board is the geometry-derived legal move space.

## Board Builder

The board is built from realized routing geometry.

That means the board builder consumes:

- zone geometry
- kernel geometry
- channel geometry
- fan geometry
- legal adjacency between those geometries

The solver must not redefine that substrate.

## Board Contents

At minimum, the board must expose:

- the owning scope
- canonical object names
- channels
- lane counts per channel
- lane ordering per channel
- fan slots
- legal transitions between adjacent substrates

Owning scope may be:

- kernel
- zone
- world

## Core Objects

### Kernel

A kernel is the smallest independently solvable routing board.

Kernel examples:

- `ki`
- `kw`
- `ke`
- `kn`
- `ks`

Kernel-local notation assumes the kernel context is already known.

### Channel

A channel is one routable corridor with a travel orientation and many lanes.

Swimming-pool analogy:

- the pool is the channel
- the lane markers are the lanes

Examples:

- `wLong`
- `eLong`
- `nLat`
- `sLat`

A channel has:

- canonical name
- orientation
- lane count
- lane ordering
- legal neighbors

### Lane

A lane is one indexed subtrack inside a channel.

Lanes are numbered per channel.

The board must expose:

- lane count
- lane index ordering
- lane-to-world realization rule

### Fan

A fan is not a travel channel.

A fan is an attachment substrate between a terminal and the travel channels.

Examples:

- `wf`
- `ef`

Fan indexing is slot indexing, not travel-lane indexing.

Examples:

- `wf[0]`
- `ef[0]`

## Coordinate Doctrine

Lane ordering is defined by global world coordinates.

Global coordinate rule:

- origin is top-left
- `x` increases right
- `y` increases down

Therefore:

- vertical-channel lanes increase west-to-east
- horizontal-channel lanes increase north-to-south

Lane numbering is geometric, not directional.

## Transitions

The board must encode legal transitions explicitly.

Examples:

- terminal -> fan
- fan -> channel
- channel -> channel

If a symbolic step says:

```text
wLong[1]::nLat[1]
```

then the board must guarantee there is one legal transition realization for that adjacent pair.

That uniqueness is a board invariant, not a solver guess.

## Uniqueness Rule

The symbolic solver is allowed to stay simple because the board is required to make legal bends and transitions unique once the symbolic sequence is chosen.

If a symbolic path step does not map to one legal realization, the board is not fully specified yet.

## Scope

The same board doctrine must scale across scopes:

- kernel board
- zone board
- world board

The object model can grow, but the meaning of kernel, channel, lane, and fan must not change by scope.
