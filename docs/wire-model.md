# Wire Model (Signal Flow Graph)

## Overview

signalFlow renders recursive call structure as a 2D ASCII **Signal Flow
Graph**. The wire represents a **Single-Thread Weave**: a continuous path
representing the execution thread as it unrolls through modular functional
units ("chips").

In the current architecture, canonical chips are not cloned per YAML
occurrence. A full earlier declaration defines the chip; later short
`module` + `func` forms reference that chip. Self-calls therefore become self
edges, and ancestor calls become back edges to existing chips.

---

## Border character vocabulary

The character at each wall point encodes the relationship between the chip and the wire at that row.

### `┼` — pierce (active port)
Used for all active entry and exit points on a chip wall. It denotes that a horizontal wire has physically intersected the functional boundary.

### `╫` — module border crossing (horizontal)
Used when a horizontal wire (call or return) crosses a **vertical** double-line module box border (`║`).

**Orphaned terminal**: a chip face stub (`◄─label`) where the visible terminal
appears detached from the route that should reach it. In `v6.0.21`, the known
world-scale orphan class was addressed by two complementary fixes: sftc emits
call-scoped parent-side labels so repeated call labels remain pairable, and
SignalFlow normalizes terminal landing/backtrack geometry before rendering. If a
new orphan appears, treat it as a regression in label pairing, terminal
geometry, or route realization ownership rather than as expected behavior.

### `╪` — module border crossing (vertical)
Used when a vertical stagger channel (call or return) crosses a **horizontal** double-line module box border (`═`).

---

## Chip geometry

Chips are arranged in columns by **graph depth** in the current simple regime.
Within a column, unique chips are stacked vertically. Each unique
`module:func` pair appears exactly once.

All chips share a consistent header structure:

```
┌─────────────────────────────────┐   top border
│   <function_name>               │   func label
├─────────────────────────────────┤   separator
│  (internal manifold rows)       │
└─────────────────────────────────┘
```

**Complexity-Aware Width.** The width of a chip scales automatically based on its label length and the number of vertical tracks required by its internal wiring manifold.

**Declared Port Model.** Every declared terminal is visually anchored by a directional arrow flush against the wall and a signal label flush against the arrow. A port with only `signal` is forward-only; it does not reserve a blank return row.

- **Exits (Right Wall):** `►label` (call) or `label◄` (return)
- **Entries (Left Wall):** `label►` (call) or `◄label` (return)
- **Omitted Return:** no `return` key means no return terminal, no return
  stub, and no reverse route for that edge.  `return: ""` (empty string) is
  invalid and rejected.

---

## Internal Wiring Manifold

Inside the chip body, the `internal_wiring` directive defines the point-to-point
connections between input and output signals. Version 5.0 accepts additive
orientation overrides such as `EW`, `WE`, `NS`, and `SN`, and explicit same-wall
handoffs reuse the same bracket/block continuity the implicit renderer used
before. When two routed endpoints share the same display label, the manifold
still keeps them distinct internally by wall-specific endpoint identity.

### Sequential Threading
A "stair-step" manifold connects return signals from child `i` to call signals for child `i+1`.

```
          ┌──────────────────────────┐
          │  process()               │
          ├──────────────────────────┤
──sig───►┼─────────────────────────┼►call_1
         │                        ┌┼◄ret_1 (step start)
         │                        ││
         │                        └┼►call_2 (step end)
──ret───◄┼─────────────────────────┼◄ret_2
          └──────────────────────────┘
```

### Aggregation / Distribution
Multiple wires can converge on or diverge from a single port row, using a staggered internal bus to prevent signal overlap.

```
          ┌──────────────────────────┐
          │  aggregator()            │
          ├──────────────────────────┤
──sig───►┼──┐                       │
         │  │                       │
         │  ├──────────────────────┼►out_1
         │  └──────────────────────┼►out_2
──ret───◄┼───┘                      │
          └──────────────────────────┘
```

---

## Snug Module Bounding

Chips sharing a module name are enclosed in a double-lined box (`╔═ ║ ═╝`). Boxes are **Snug**, only expanding to include vertical channels if they are intra-module. All piercings are **Reactive**, appearing only where a line physically intersects a border.
