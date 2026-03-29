# Naming

This file defines canonical symbolic naming for algebraic routing.

## Purpose

Every notation-participating object must have a canonical symbolic name.

Canonical names are first-class object properties, not ad hoc debug strings.

The symbolic solver, debugger, and materializer must all use the same canonical names.

## Naming Doctrine

Canonical names must be:

- stable
- short
- composable by scope
- unambiguous within their scope

Rendered prose labels may vary.

Canonical symbolic names may not.

## Scope Composition

Names compose from smaller scope to larger scope.

Examples:

- lane in channel
  - `nLat[3]`
- channel in kernel
  - `ki.nLat`
- lane in kernel
  - `ki.nLat[3]`
- lane in world
  - `z(1,1).ki.nLat[3]`

This means the name meaning does not change with scope.

Only qualification is added.

## Zone Names

Zone names are derived from world grid coordinates.

Canonical form:

```text
z(column,row)
```

Examples:

- `z(1,1)`
- `z(2,1)`
- `z(3,2)`

## Kernel Names

Kernel names are short symbolic names.

Current direction:

- `ki`
  - intra kernel
- `kw`
  - west kernel
- `ke`
  - east kernel
- `kn`
  - north kernel
- `ks`
  - south kernel

These names should be properties of kernel objects.

## Channel Names

Channel names encode:

- side family
- orientation

Current direction:

- `wLong`
- `eLong`
- `nLat`
- `sLat`

This naming is intentionally compact and algebra-friendly.

## Fan Names

Fan names are compact attachment-substrate names.

Current direction:

- `wf`
- `ef`
- later, if needed:
  - `nf`
  - `sf`

Fan indices are written like:

- `wf[0]`
- `ef[0]`

## Lane Names

Lanes are channel-local ordinals.

Canonical form:

```text
channel[index]
```

Examples:

- `wLong[1]`
- `nLat[6]`

Fully qualified examples:

- `ki.wLong[1]`
- `z(1,1).ki.nLat[6]`

## Wire Endpoint Names

Wire endpoints use canonical chip endpoint form:

```text
module.func.signal
```

Examples:

- `App.ts.main().s1`
- `Proxy.ts.p1().r1`

Wire identities are directional:

```text
App.ts.main().s1:Proxy.ts.p1().s1
```

## Reserved Principle

Do not create multiple symbolic naming systems for the same object class.

If a shorter debug alias exists, it must still reduce to one canonical symbolic name, not introduce a second naming doctrine.
