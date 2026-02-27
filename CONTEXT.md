# signalFlow — Agent Handover Context

## What This Project Is

ASCII call-thread wiring diagram renderer.  Converts a recursive YAML call
tree into a 2D ASCII diagram showing forward calls (left→right) and returns
(right→left) as wires passing through "function chips" grouped in double-line
module boxes.

**Tech:** Python ≥3.11, only external dep PyYAML ≥6.0.
**Tests:** pytest in `tests/`  — currently **90 tests, all passing**.
**Lint:** ruff, zero-tolerance (`ruff check src/`).
**Style:** `PYTHON-STYLE-GUIDE.md` — RPN `noun_verb()` naming, pervasive type
hints, Google-style docstrings, `from __future__ import annotations` at top of
every file.

---

## Repo Layout

```
src/signalflow/
  __main__.py            CLI entry point
  config.py              All geometry constants (single source of truth)
  engine/render.py       Top-level orchestrator: diagram_render()
  lib/
    canvas_factory.py    canvas_create() — allocates blank canvas
    chips.py             chip_render()   — draws one function chip
    boxes.py             moduleBox_compute(), moduleBox_render()
    layout.py            layout_compute(), innerWidth_get(), leftMargin_compute()
    tree.py              col_assign(), tree_flatten(), chip_h_precompute()
    wires.py             wire_forward_render(), wire_return_render(), thread_render()
  models/
    canvas.py            Canvas dataclass (2-D char grid + draw primitives)
    node.py              Node dataclass (one call in the tree)
    module_box.py        ModuleBox dataclass
    __init__.py
examples/
  leaf.yaml
  root-single-child.yaml          ← has return_signal: "result" on child
  root-single-child-no-return.yaml
  root-multi-child.yaml
  passthrough.yaml
  branch-linear.yaml
  branch-converging.yaml
  show-cohort.yaml
tests/
  test_canvas.py
  test_chips.py
  test_wires.py
  test_layout.py
  test_render.py
  test_wire_model.py    ← main spec-conformance suite (58 tests)
docs/
  wire-model.md
  module-chip.adoc
  function-chip.adoc
PYTHON-STYLE-GUIDE.md
```

---

## Pipeline (render.py: diagram_render)

```
YAML → Node.node_fromDict()
     → tree_flatten()        DFS list of all nodes
     → col_assign()          depth column per node
     → innerWidth_get()      uniform chip inner width
     → channelWidth_compute() horizontal channel width
     → layout_compute()      sets node.x, node.y, chip_h, entry_row, return_row
     → moduleBox_compute()   one ModuleBox per distinct module name
     → canvas_create()       blank Canvas sized to fit everything
     → moduleBox_render()    draw ╔═ double-line boxes
     → chip_render()         draw each function chip
     → thread_render()       draw all forward + return wires
     → canvas.lines_get()    strip trailing whitespace, return list[str]
```

---

## Key Constants (config.py)

```python
CHANNEL_W: int = 22   # min horizontal gap between chip columns
ROW_GAP:   int = 6    # blank rows between sibling subtrees
CHIP_PAD:  int = 2    # min padding cols left/right of func name (centered)
MB_OUTER:  int = 2    # cols from chip edge to module-box border
MB_INNER:  int = 4    # extra left-canvas margin for root chips
MB_TOP:    int = 3    # rows from module-box top to chip top
BASE_LEAF: int = 6    # leaf chip height (rows)
UTURN_W:   int = 3    # cols for U-turn arm inside leaf chip
```

---

## Node Dataclass (models/node.py)

```python
@dataclass
class Node:
    module:        str
    func:          str
    signal:        str | None       # label on forward/call wire (None = unlabeled)
    return_signal: str | None = None  # label on return wire (None = unlabeled)
    children:      list = field(default_factory=list)
    col:        int  = 0
    x:          int  = 0
    y:          int  = 0
    chip_h:     int  = BASE_LEAF
    is_root:    bool = False
    entry_row:  int  = 0
    return_row: int  = 0
```

`return_signal` was added in this session.  `node_fromDict` parses it with
`d.get('return_signal')`.

---

## Chip Geometry Spec

```
row y+0   ┌──────────────┐   top border
row y+1   │  func_name   │   func label — CENTERED (CHIP_PAD spaces each side)
row y+2   ├──────────────┤   separator
row y+3   wire entry row          (┼ on left wall for non-root; ├ on right for root)
row y+4   wire return row
...
row y+N   └──────────────┘   bottom border
```

**chip_h formula:**
- Leaf: `BASE_LEAF = 6`
- Any parent: `3 * N + 3`  where N = number of children

**Chip inner width** = `max(len(func) for all nodes) + 2 * CHIP_PAD`
(uniform across all chips; minimum per chip = `2*CHIP_PAD + len(func)`)

---

## Module Box

Single double-line box per distinct `module` field value:

```
╔═ ModuleName.ts ════╗
║                    ║
║   ┌────────────┐   ║
║   │  func()    │   ║
║   ├────────────┤   ║
║   ...              ║
╚════════════════════╝
```

Box left border = `chip.x - MB_OUTER`.
Box right border = `chip.x + ow + MB_OUTER - 1`.
Box top = `chip.y - MB_TOP`.
Box bottom = `chip.y + chip_h + MB_OUTER - 1`.

Stubs (root leaf only) pierce the left border: `║` → `╫` at crossing.

---

## Wire Semantics

**Forward wire** (left → right): drawn by `wire_forward_render`.
- Label = `child.signal` — placed in the channel starting at `parent_rx + 1`.
- Approach arrow `►` placed at `child.x - 1`.

**Return wire** (right → left): drawn by `wire_return_render`.
- Label = `child.return_signal` — **⚠️ NOT YET IMPLEMENTED (see below).**

**Root-leaf stubs** (chip_render, only when `node.is_root`):
- Dashes from col 0 to `chip.x - 2`, piercing `║` → `╫`.
- Forward label `node.signal` at col 2 (2 leading dashes), truncated to `x0-6`
  (guarantees 2 trailing dashes before the `╫`).
- Return label `node.return_signal` at col 2 on return row.

---

## ⚠️  THE OPEN BUG — fix this next

### Return-wire signal labels are never rendered for connected nodes

`wire_return_render` in `src/signalflow/lib/wires.py` draws the return wire
(dashes) but **never places the `child.return_signal` text label** on it.

Compare with `wire_forward_render` which has:
```python
    if child.signal:
        label_x   = parent_rx + 1
        max_label = max(1, entry_x - label_x - 1)
        canvas.text(label_x, exit_y, child.signal[:max_label])
```

`wire_return_render` has no equivalent block.

**Observed symptom:**
`examples/root-single-child.yaml` has `return_signal: "result"` on the child
`run()` node.  Running `signalflow examples/root-single-child.yaml` shows the
return wire but no "result" label on it.

### What the fix requires

In `wire_return_render`, after the wire is drawn, add the return-signal label
symmetrically to the forward case:

```python
    if child.return_signal:
        label_x   = parent_rx + 1
        max_label = max(1, child_lx - label_x - 1)
        canvas.text(label_x, child_ret_y, child.return_signal[:max_label])
```

The label should appear on `child_ret_y` (the child's return row) starting at
`parent_rx + 1` (just right of the parent chip's right wall), same horizontal
extent as the forward label — the full channel width.

### TDD approach

Before fixing, add a failing test to `tests/test_wire_model.py` or
`tests/test_wires.py`:

```python
def test_return_signal_label_in_channel(self):
    """Return-signal label appears on the return wire in the channel."""
    child = Node(module="M", func="c()", signal="arg",
                 return_signal="res", children=[])
    root  = _parent("r()", [child], is_root=True)
    canvas, nodes, ow = _full_render(root)
    c = next(n for n in nodes if n.func == "c()")
    row = ''.join(canvas.grid[c.return_row])
    assert 'res' in row
```

Confirm RED, implement fix, confirm GREEN, run full suite.

---

## Return-Signal Semantics (design decision reached this session)

| `return_signal` value | Meaning | Return wire |
|---|---|---|
| `"data"` | Returns named value | Drawn, labeled |
| `null` / omitted | Returns, value unnamed | Drawn, no label |
| *(future: `no_return: true`)* | Fire-and-forget / void | Not drawn |

The model currently always draws the return wire.  A `no_return` flag is
**not yet implemented** but was discussed as a future addition.

---

## Recent Session Changes (all merged, tests passing)

1. **`config.py`** — `PAD` renamed `CHIP_PAD = 2`; `MIN_IW` removed;
   comprehensive module docstring; `from __future__ import annotations`.

2. **`layout.py`** — `innerWidth_get(nodes: list[Node])` uses `CHIP_PAD * 2`,
   no `MIN_IW` floor; `leftMargin_compute(root)` computes dynamic LEFT_OFFSET
   for root-leaf stub labels; full Google docstrings; typed locals.

3. **`chips.py`** — func label now `node.func.center(iw)[:iw]` (was left-pad);
   `from __future__ import annotations`; full Google docstring on `chip_render`.

4. **`boxes.py`** — double-nested thin-line boxes replaced with single
   `╔═ label ═╗` double-line box; `ModuleBox` simplified (ix/iy fields removed);
   box uses only `MB_OUTER` padding (not `MB_INNER + MB_OUTER`).

5. **`models/node.py`** — `return_signal: str | None = None` field added;
   `node_fromDict` parses `d.get('return_signal')`.

6. **`chips.py` stubs** — root-leaf stubs start at col 0; pierce `║→╫`;
   label at col 2 with 2 leading + 2 trailing dashes guaranteed.

7. **`examples/leaf.yaml`** — updated with `return_signal: "output"`.

---

## Running Things

```bash
# Activate venv
source .venv/bin/activate

# Run all tests
pytest -v

# Lint
ruff check src/

# Render an example
signalflow examples/leaf.yaml
signalflow examples/root-single-child.yaml
signalflow examples/show-cohort.yaml
```

---

## Example Rankings (simplest → most complex)

1. `leaf.yaml` — 1 node, depth 0, 1 module, U-turn only
2. `root-single-child.yaml` — 2 nodes, depth 1, 1 module
3. `root-multi-child.yaml` — 4 nodes, depth 1, 1 module, flat fan-out N=3
4. `passthrough.yaml` — 3 nodes, depth 2, 3 modules, non-root parent
5. `branch-linear.yaml` — 5 nodes, depth 2, 4 modules, interior arm routing
6. `branch-converging.yaml` — 5 nodes, depth 2, 5 modules, ┴ junction
7. `show-cohort.yaml` — 6 nodes, depth 3, 4 modules, real-world topology
