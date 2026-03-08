# Rendering Backlog

Known limitations and deferred improvements to the rendering engine.
Items are independent unless noted.

---

## BL-01 — chipH underestimates for n=1 manifold chips

**File**: `src/signalflow/models/chip_geometry.py / _chipH_compute`

When a manifold chip has `ewOff > 0` but `n = max(nLeft, nRight) = 1`, the
formula is `max(baseLeafHeight, 6 + ewOff)`.  This covers the E→W trunk row but
does not add the vertical space that the multi-port formula allocates for the
W→E trunk zone and anchor stacks (`maxPortDensity + wiringCount + 2`).  A chip
with complex wiring and exactly one external port pair may be rendered too short.

`geometry_validate` will catch any actual violation at render time before any
drawing occurs, so the failure mode is a loud `AssertionError` rather than a
silently wrong diagram.

**Fix**: extend `_chipH_compute` to run the full manifold formula for n=1
when `node.internal_wiring` is non-empty, rather than returning the
`6 + ewOff` shortcut.

---

## BL-02 — No vertical packing within columns

**File**: `src/signalflow/lib/layout.py / layout_compute`

Chips within a column are stacked strictly in BFS order with a fixed
`verticalChipPadding` gap between them.  For diagrams with many sibling chips in
the same column the canvas becomes very tall, often exceeding what can be
read in a single viewport.

**Fix**: a bin-packing or height-balancing pass that distributes chips across
virtual sub-columns, or a configurable multi-column layout for wide peer groups.
Requires extending the column-assignment model.

---

## BL-03 — Horizontal overflow for deep call trees

**File**: `src/signalflow/lib/layout.py / col_assign`, `channelWidth_compute`

Each column adds `max(chipOw) + channelWidth` characters.  A tree seven levels
deep with default settings produces a canvas approximately 200 columns wide,
exceeding the standard 80- and 120-column terminal widths that the ASCII medium
is intended to fit within.

**Fix**: a wrapping/folding mode that continues the diagram on a new set of
rows after a configurable max-width threshold, with visual connectors indicating
the fold point.  Alternatively, a `--width` CLI flag that scales
`channelWidth` and `chipPaddingX` automatically to fit a target terminal width.

---

## BL-04 — Single column assignment for shared nodes

**File**: `src/signalflow/lib/layout.py / col_assign`

A canonical shared node receives its column index from whichever parent is
visited first in the DFS traversal.  If a second parent calls the same chip
from a different depth, the wire from that parent jogs a long horizontal
distance.  There is no placement negotiation between competing callers.

**Fix**: a post-assignment pass that moves shared nodes to a column that
minimises the total wire-length cost across all their parents, or allows
explicit column hints in the YAML (`col: 3`).

---

## BL-05 — Canvas OOB on stagger overflow

**File**: `src/signalflow/lib/layout.py / channelWidth_compute`,
`src/signalflow/lib/wires.py / wireForward_render`

Canvas width is allocated from `channelWidth_compute` before any wire routing.
If a parent has many children whose Unified Staggering offsets require more
horizontal space than `channelWidth` provides, the vertical segment of a
staggered wire can land at a negative or out-of-bounds x-coordinate.  In debug
mode `canvas.set` raises `IndexError`; in optimised mode the write is silently
dropped.

The workaround is to increase `channelWidth` in the YAML config section.

**Fix**: `channelWidth_compute` should account for the maximum stagger offset
(`max(pIdx, cIdx)` × 2) when computing the minimum channel width, so the
allocated canvas is always wide enough for the actual wire routes.

---

## BL-06 — O(n) port index lookup in wire rendering

**File**: `src/signalflow/lib/wires.py / wireForward_render`,
`wireReturn_render`

`pIdx` is computed via `list(parent.output_ports.keys()).index(out_key)`, a
linear scan over the output port dict.  For typical call trees (2–10 children
per parent) this is negligible.  A parent with hundreds of output ports would
make this the dominant rendering cost.

**Fix**: store the port index alongside the `PortKey` in `Node.call_sequence`
as a fourth tuple element `(child, out_key, in_key, pIdx)`, making the lookup
O(1).  Requires updating `node_fromDict` and `thread_render`.

---

## BL-07 — Global call_index makes PortKey opaque for inspection

**File**: `src/signalflow/models/node.py / node_fromDict`

The `call_index` component of a `PortKey` is drawn from `portCounters`, a
global counter across all callers.  If `p1()` and `p2()` both call `process()`,
the keys in `process().input_ports` are `(id(p1), 0)` and `(id(p2), 1)` — not
both at index 0.  The index is therefore a global occurrence number rather than
a per-parent sequence number, which can be surprising when inspecting port dicts
directly.

**Fix**: replace the global `portCounters` with a per-parent counter so that
each parent's first call to any child always gets call_index 0.  The uniqueness
guarantee is preserved because the `node_id` component already distinguishes
parents.  Requires verifying that the `unbound_inputs` slot selection (which
currently uses the same `currentInIdx`) is updated to use a separate counter if
the two are decoupled.

---

## BL-08 — Long signal names widen manifold chips (partial mitigation in place)

**File**: `src/signalflow/models/chip_geometry.py / _chipOw_compute`,
`src/signalflow/lib/chips.py`

Anchor label widths (`"signalName►"`) directly drive the minimum chip width via
the longitude-zone formula `12 + maxLeftLabel + maxRightLabel + 2*(vL+vR)`.
Port names of 15–25 characters — common in TypeScript or Java codebases — can
make a hub chip 60–100 columns wide regardless of its actual wiring complexity.

**Partial mitigation**: `config.anchorLabelMaxWidth` (YAML key
`internal_wiring.anchorLabelWidth`) truncates anchor label strings to N
characters inside the chip while leaving the full name on external wires.

**Remaining gap**: the user must choose a truncation width manually.  A cleaner
long-term solution is Option B from the design discussion — a separate
`display:` field on `Port` that provides the external wire label independently
of the short alias used in `internal_wiring` and anchor rendering.  This lets
authors write descriptive port names on wires without paying any chip-width cost
for the length of those names.

---

## BL-09 — config bleed when diagram_render is called without prior globalConfig_load

**File**: `src/signalflow/engine/render.py / diagram_render`,
`src/signalflow/lib/global_config.py / globalConfig_reset`

`globalConfig_reset()` is a no-op when `globalConfig_load()` has not been
called (e.g. when `diagram_render` is used as a library rather than via the
CLI).  In that scenario, per-document `config:` changes accumulate on the
singleton across successive `diagram_render` calls.  The second document sees
the first document's config changes.

**Fix**: expose a `globalConfig_init()` function (or a context manager) that
library users can call to establish a clean baseline, and document the
call contract in the module docstring.
