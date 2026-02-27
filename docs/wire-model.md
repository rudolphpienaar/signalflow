# Wire Model

## Overview

signalFlow renders a recursive call tree as a 2D ASCII diagram. The wire is the
DFS traversal of the call tree unrolled left-to-right: forward calls go RIGHT,
returns go LEFT through the same horizontal channel.

---

## Border character vocabulary

The character at each wall point encodes the relationship between the chip and
the wire at that row.

### `┼` — pierce (both walls simultaneously active)

Used when **both the left wall and the right wall carry a wire on the same
row**. The call thread enters one wall and exits the other at the same
horizontal row — the chip is a true transit node for that segment.

```
──►┼──────────────────┼►──
   │   (chip body)    │
──◄┼──────────────────┼◄──
```

Occurs on the entry/return rows of non-root parent chips where the
incoming parent wire and the child-call wire are concurrent.

### `├` — single-wall connection (one wall active)

Used when **only one wall** has a wire at that row. The arm extends rightward;
the arrow shows direction:

| Notation | Meaning                                                          |
|----------|------------------------------------------------------------------|
| `├►`     | wire departs rightward — chip sends call signal to child         |
| `├◄`     | wire arrives from right — chip receives return signal from child |

Applies to all connections on the **root chip's right wall** (left wall is
never pierced).

### `╫` — module border crossing (horizontal)

Used when a horizontal wire (call or return) crosses a **vertical** module box
border (`║`).

### `╪` — module border crossing (vertical)

Used when a vertical stagger channel (call or return) crosses a **horizontal**
module box border (`═`). This typically occurs at the bottom of a module box
when a child is positioned significantly below its parent.

---

## Chip geometry

Chips are arranged in columns by call depth (root = col 0). Within a column,
siblings are stacked vertically.

All chip types share the same **header** (see `docs/function-chip.adoc`):

```
┌─────────────────────────────────┐   top border
│   <function_name>               │   func label
├─────────────────────────────────┤   separator
│  (wire-body rows)               │
└─────────────────────────────────┘
```

**No labels inside chips.** Signal labels are rendered only on the channel
wires in the horizontal space between chip columns. Inside the chip body,
only routing characters appear (`─ │ ┌ ┐ └ ┘`).

**Symmetric 4-Port Port Model.** Every port (entry or exit) is visually anchored
by a directional arrow flush against the wall and a signal label flush against
the arrow.

- **Exits (Parent Right Wall):** `►label` (call) or `label◄` (return)
- **Entries (Child Left Wall):** `label►` (call) or `◄label` (return)

**Wire-pair spacing.** The call and return of the same child are
**adjacent rows** with no blank between them — they look like a two-row
channel. One blank **wire-pair-space** row separates consecutive child pairs.
Each child therefore occupies **3 rows** in the wire body: call + return +
wire-pair-space (except the last child, which has no trailing space row).

**Return Row Logic.** For multi-child nodes, the node's own `return_row`
is aligned with the **last child's return row**, reflecting the completion
of the sequential thread.

---

### Leaf chip (`chip_h = BASE_LEAF = 6`)

The wire pierces the left wall going in, U-turns in a compact two-row arc
(`──┐` / `──┘`), then pierces the left wall again going out. Call and return
are adjacent — no intermediate row.

```
           ┌──────────────────┐   row y+0   top border
           │  func_label      │   row y+1   func label
           ├──────────────────┤   row y+2   separator
──label──►┼──┐               │   row y+3   call label; pierce left wall; U-turn arm
──label───◄┼──┘               │   row y+4   return label; pierce left wall; U-turn base
           └──────────────────┘   row y+5   bottom border
```

---

### Root parent chip (`chip_h = 3*N + 3`, N = number of children)

The root is the **origin and terminus** of the entire call thread. Its left
wall is never pierced. Every right-wall connection uses `├►` for
departing calls or `├◄` for arriving returns.

```
   ┌──────────────────────┐   row y+0    top border
   │  func_label          │   row y+1    func label
   ├──────────────────────┤   row y+2    separator
   │                      ├►label───<call_1>──  row y+3   child 1 call departs
   │                      ├◄label───<ret_1>───  row y+4   child 1 return arrives
   │                      │                     row y+5   wire-pair-space
   ...
   └──────────────────────┘   row y+h-1   bottom border
```

---

### Non-root parent chip (`chip_h = 3*N + 3`, N = number of children)

A non-root parent is a transit node. It is called from the left and
simultaneously dispatches its first child call to the right.

#### Multi-child threading

For `N > 1` children, return values are threaded sequentially. The return of
child `i` turns DOWN inside the chip to meet the call of child `i+1`. The final
return (from child `N`) flows all the way back to the left wall.

```
            ┌─────────────────────────────────────────┐
            │  func_label                             │   row y+1   func label
            ├─────────────────────────────────────────┤   row y+2   separator
──label──►┼─────────────────────────────────────────┼►label───<call_1>   row y+3
          │                                        ┌┼◄label───<ret_1>    row y+4 (thread start)
          │                                        ││                    row y+5
          │                                        └┼►label───<call_2>   row y+6 (thread end)
──label──◄┼─────────────────────────────────────────┼◄label───<ret_2>    row y+7 (final return)
            └─────────────────────────────────────────┘
```

---

## Module boxes

All chips sharing a module name are enclosed in a box drawn with double-line
box characters (`╔ ═ ╗ ║ ╚ ╝`).

**Piercing Rules:**
- **Side Walls (`║`):** Replaced by `╫` when horizontal wires cross.
- **Bottom Border (`═`):** Replaced by `╪` when vertical channels cross.

---

## Layout constants (`config.py`)

| Constant   | Default | Meaning                                          |
|------------|---------|--------------------------------------------------|
| CHANNEL_W  | 22      | Horizontal gap between chip columns              |
| ROW_GAP    | 6       | Blank rows between sibling subtrees              |
| CHIP_PAD   | 2       | Inner horizontal padding each side of chip       |
| MB_OUTER   | 2       | Cols from chip edge to module box wall           |
| MB_TOP     | 3       | Rows from module box top to chip top             |
| BASE_LEAF  | 6       | Leaf chip height                                 |
| UTURN_W    | 3       | Column width of U-turn arm inside leaf chip      |
