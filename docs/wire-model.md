# Wire Model (Signal Flow Graph)

## Overview

signalFlow renders a recursive call tree as a 2D ASCII **Signal Flow Graph**. The wire represents a **Single-Thread Weave**: a continuous path representing the execution thread as it unrolls through modular functional units ("chips").

---

## Border character vocabulary

The character at each wall point encodes the relationship between the chip and the wire at that row.

### `┼` — pierce (active port)
Used for all active entry and exit points on a chip wall. It denotes that a horizontal wire has physically intersected the functional boundary.

### `╫` — module border crossing (horizontal)
Used when a horizontal wire (call or return) crosses a **vertical** double-line module box border (`║`).

### `╪` — module border crossing (vertical)
Used when a vertical stagger channel (call or return) crosses a **horizontal** double-line module box border (`═`).

---

## Chip geometry

Chips are arranged in columns by **max call depth**. Within a column, unique chips are stacked vertically. Each unique `module:func` pair appears exactly once.

All chips share a consistent header structure:

```
┌─────────────────────────────────┐   top border
│   <function_name>               │   func label
├─────────────────────────────────┤   separator
│  (internal manifold rows)       │
└─────────────────────────────────┘
```

**Complexity-Aware Width.** The width of a chip scales automatically based on its label length and the number of vertical tracks required by its internal wiring manifold.

**Symmetric 4-Port Model.** Every port is visually anchored by a directional arrow flush against the wall and a signal label flush against the arrow.

- **Exits (Right Wall):** `►label` (call) or `label◄` (return)
- **Entries (Left Wall):** `label►` (call) or `◄label` (return)

---

## Internal Wiring Manifold

Inside the chip body, the `internal_wiring` directive defines the point-to-point connections between input and output signals.

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
