# Path Algebra

This file defines the symbolic route notation for algebraic kernel routing.

## Purpose

The symbolic solver does not emit world coordinates.

It emits an algebraic path.

That algebraic path is then materialized by the geometry layer.

## Path Form

Current path form is a directed token sequence:

```text
endpoint::step::step::step::endpoint
```

Example:

```text
App.ts.main().s1::wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]::Proxy.ts.p1().s1
```

This path is directional and unique once the board and packing doctrine are fixed.

## Token Classes

### Endpoint Tokens

Endpoint tokens identify chip-local wire endpoints.

Form:

```text
module.func.signal
```

Examples:

- `App.ts.main().s1`
- `Proxy.ts.p1().s1`
- `Proxy.ts.p1().r1`

### Fan Tokens

Fan tokens represent attachment slots in a fan substrate.

Examples:

- `wf[0]`
- `ef[0]`

Current doctrine:

- `[0]` means the terminal-aligned/default slot
- higher indices are reserved for future explicit fan-vane materialization

### Channel Tokens

Channel tokens represent indexed lanes in travel channels.

Examples:

- `wLong[1]`
- `nLat[1]`
- `eLong[10]`
- `sLat[6]`

## Example: Forward

Example forward path:

```text
App.ts.main().s1::wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]::Proxy.ts.p1().s1
```

Interpretation:

1. start at the source endpoint
2. attach through the west fan
3. enter lane 1 of the west longitude channel
4. transition into lane 1 of the north latitude channel
5. transition into lane 10 of the east longitude channel
6. attach through the east fan
7. terminate at the destination endpoint

## Example: Forward Shell Packing

For the next forward wire:

```text
App.ts.main().s2::wf[0]::wLong[2]::nLat[2]::eLong[9]::ef[0]::Proxy.ts.p2().s2
```

The shell has widened by one lane on each relevant channel according to the packing doctrine.

## Example: Return

Example return path:

```text
Proxy.ts.p1().r1::ef[0]::eLong[6]::sLat[6]::wLong[6]::wf[0]::App.ts.main().r1
```

Interpretation:

- the return path is a distinct directional wire
- it occupies a later shell after the forward shell has been packed
- lane choice follows the same board and packing doctrine, not a separate coordinate solver

## Packing Rule

The symbolic solver chooses channels and lane indices according to:

- board legality
- channel packing doctrine
- shell ordering
- forward/return routing doctrine

The symbolic solver must not invent bends geometrically.

## Materialization Rule

Once a symbolic path is chosen, the materializer converts adjacent token pairs into concrete route geometry.

Examples:

- `wf[0] -> wLong[1]`
- `wLong[1] -> nLat[1]`
- `nLat[1] -> eLong[10]`

Those adjacent transitions must have a unique legal realization on the board.

## Scope

The shortest notation assumes current scope.

Examples:

- kernel scope
  - `wLong[1]`
- zone scope
  - `ki.wLong[1]`
- world scope
  - `z(1,1).ki.wLong[1]`

The same algebra must remain valid across scopes by adding qualification, not changing semantics.

## Current REPL Implication

The current REPL already exposes the first symbolic substrate:

- `kernel.wiring_get()`
- `wiring.list_text()`
- `wiring.algebraic_text(endpointText)`

That is the seed surface for the full path algebra, not the final form.
