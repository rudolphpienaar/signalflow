# Plan: §1.13 — Repeated-Child Port Binding Redesign

> The ChipGeometry consolidation plan (Phases 0–7) is complete as of v4.0.0.
> This plan addresses the one remaining architectural limitation: the port
> model cannot correctly represent a parent calling the same child function
> more than once.

## Current Status

| Phase | Title | Status |
|---|---|---|
| 0 | TDD — xfail guard + new test cases | 🔲 NEXT |
| 1 | PortKey type alias + Node field changes + node_fromDict | 🔲 |
| 2 | layout_compute — port row assignment | 🔲 |
| 3 | chip_geometry.resolve() — leftWallRows loop | 🔲 |
| 4 | wires.py — wire render signatures + thread_render | 🔲 |
| 5 | layout.py — channelWidth_compute label scans | 🔲 |
| 6 | Delete xfail guard; verify test suite | 🔲 |

**Current baseline**: 145 passed, 1 xfailed
(`TestRepeatedChildPortBinding.test_repeated_child_gets_distinct_output_ports`)

---

## 0. Context Bootstrap

Read these files before touching any code.

| File | Focus |
|---|---|
| `PLAN.md` (this file) | Full specification; do not re-derive |
| `src/signalflow/models/node.py` | `Node` dataclass fields; `node_fromDict` — the primary change site |
| `src/signalflow/lib/layout.py` | `layout_compute` step 4 (port row assignment); `channelWidth_compute` (label scans) |
| `src/signalflow/lib/wires.py` | `wireForward_render`, `wireReturn_render`, `thread_render` |
| `src/signalflow/models/chip_geometry.py` | `resolve()` — `leftWallRows` loop reads `input_ports.items()` |
| `tests/test_latent_bugs.py` | The xfail guard being promoted |

---

## 1. Problem Statement

### 1.1 Node Canonicalization

Every node in the graph is identified by the string `"{module}:{func}"` and
stored in a registry.  When the parser encounters a `calls` entry, it looks
up the registry first.  If the `(module, func)` pair was already seen, the
existing `Node` object is returned rather than creating a new one.  This
is what allows Hub chips to appear once on the canvas while being referenced
by multiple parents.

### 1.2 The Collision

`output_ports`, `input_ports`, `entryRows`, and `returnRows` are all
`dict[int, ...]` keyed by `id(child)` or `id(parent)`.  CPython's `id()`
returns the runtime identity of an object — the memory address.  For a
canonical node, this identity is fixed and unique.

When a parent calls the same child function twice, both calls return the
**same** `Node` object from the registry.  Both calls therefore produce the
same `id(child)`.  The second write into `output_ports[id(child)]`
silently overwrites the first:

```
parent calls work() twice — port declarations:
  call 1: output_ports[id(work)] = Port(signal="encode", ret="result")
  call 2: output_ports[id(work)] = Port(signal="decode", ret="response")
          ↑ overwrites — "encode"/"result" are gone
```

The same collision happens on the child's side:

```
work().input_ports[id(parent)] written twice from the same parent.
Second write overwrites the first.
```

And in `entryRows`/`returnRows` on the child, which are also keyed by
`id(parent)`.

The net effect: only the **last** call's port is retained.  All previous
connections to the same child from the same parent are silently discarded.
The rendered diagram shows one wire where two (or more) should appear.

### 1.3 Why the enumerate Fix Was Insufficient

Phase 6d changed `childIdx = d.get("calls", []).index(cDict)` to
`for childIdx, cDict in enumerate(d.get("calls", []))`.  This fixed the
wrong `unbound_outputs` slot being selected, but the collision was in the
dict key — `id(child)` — not in the slot index.  Selecting the right port
definition and writing it to the wrong key are independent bugs; Phase 6d
fixed the former, this plan fixes the latter.

### 1.4 Concrete Example

```yaml
tree:
  module: App
  func: "main()"
  output_ports:
    - {signal: "encode_req", return: "encode_resp"}
    - {signal: "decode_req", return: "decode_resp"}
  calls:
    - module: Codec
      func: "transform()"
      input_ports: [{signal: "encode_req", return: "encode_resp"}]
    - module: Codec
      func: "transform()"          # same chip, second call
      input_ports: [{signal: "decode_req", return: "decode_resp"}]
```

**What the diagram should show**:
```
┌─ main() ─┐         ┌─ transform() ─┐
│          ├encode_req►─────────────►│
│          ◄encode_resp◄─────────────┤
│          │         │               │
│          ├decode_req►─────────────►│
│          ◄decode_resp◄─────────────┤
└──────────┘         └───────────────┘
```

**What currently happens**:  only `decode_req`/`decode_resp` wires appear;
`encode_req`/`encode_resp` are lost.

---

## 2. Solution Architecture

### 2.1 The Port Key

Replace the `int` key type across all four port/row dicts with a two-element
tuple:

```python
PortKey = tuple[int, int]   # (node_id, call_index)
```

`node_id` is `id(child)` (for output_ports) or `id(parent)` (for
input_ports).  `call_index` is the value of `portCounters[cKey]` at the
moment the binding is created — the sequential count of how many times any
parent has ever bound a port on this child.  This counter already exists in
`node_fromDict` as `currentInIdx`; it is now also used as the output port
call index.

For a child called once by a single parent, the key is `(id(other_node), 0)`
— identical in structure to the old `id(other_node)` but wrapped in a tuple.
No existing single-call topology changes behaviour.

For a child called twice by the same parent:
```
  First call:   portCounters[cKey] == 0
    child.input_ports[(id(parent), 0)]  = Port(signal="encode_req", ...)
    parent.output_ports[(id(child), 0)] = Port(signal="encode_req", ...)

  Second call:  portCounters[cKey] == 1
    child.input_ports[(id(parent), 1)]  = Port(signal="decode_req", ...)
    parent.output_ports[(id(child), 1)] = Port(signal="decode_req", ...)
```

Two distinct keys; no collision.

### 2.2 The Call Sequence

Wire rendering (thread_render → wireForward_render / wireReturn_render)
needs to iterate over all calls in their original YAML order, including
duplicates.  The existing `node.children` list is de-duplicated (each unique
child appears once) and is used for layout and chip-position purposes.  A
second field, `call_sequence`, carries the full ordered call list:

```python
call_sequence: list[tuple[Node, PortKey, PortKey]]
```

Each entry is `(child, out_key, in_key)` where `out_key` is the key in
`parent.output_ports` for this call occurrence, and `in_key` is the
corresponding key in `child.input_ports`.

`thread_render` iterates `call_sequence` instead of `children`.  The
canonical DFS recursion into a child's subtree is guarded by a `seen` set
so each child's internal wires are drawn exactly once regardless of how
many times it appears in the call sequence.

### 2.3 children Remains De-duplicated

`node.children` continues to hold each unique child `Node` object at most
once.  It is used by `tree_flatten`, `col_assign`, `subtreeCanvasH_calculate`,
`channelWidth_compute`, and `chip_render` — all of which need the unique
chip list, not the full call sequence.  Nothing in this plan changes the
de-duplication guard.

### 2.4 Wire Render Signature Change

`wireForward_render` and `wireReturn_render` currently receive `(canvas,
parent, child)` and derive everything from `id(child)` / `id(parent)`.
With multiple calls to the same child, that derivation is ambiguous.  The
new signature passes the pre-resolved keys explicitly:

```python
def wireForward_render(
    canvas: Canvas,
    parent: Node,
    child:  Node,
    out_key: PortKey,   # parent.output_ports key for this call
    in_key:  PortKey,   # child.input_ports  key for this call
    color: str | None = None,
) -> None: ...

def wireReturn_render(
    canvas: Canvas,
    parent: Node,
    child:  Node,
    out_key: PortKey,
    in_key:  PortKey,
    color: str | None = None,
) -> None: ...
```

No other part of the call signature changes.

---

## 3. New Data Model

### 3.1 Type Alias

Add at the top of `node.py`:

```python
PortKey = tuple[int, int]   # (id(node), call_index)
```

Export it from `signalflow.models` for downstream use.

### 3.2 Node Field Changes

```python
# Before                           # After
input_ports:  dict[int, Port]      input_ports:  dict[PortKey, Port]
output_ports: dict[int, Port]      output_ports: dict[PortKey, Port]
entryRows:    dict[int, int]       entryRows:    dict[PortKey, int]
returnRows:   dict[int, int]       returnRows:   dict[PortKey, int]
                                   call_sequence: list[tuple[Node, PortKey, PortKey]]
```

`children: list[Node]` is unchanged.

`call_sequence` must be a `field(default_factory=list)` dataclass field.
It is populated by `node_fromDict` and consumed only by `thread_render`.

The `isRoot` property (`not self.input_ports`) continues to work unchanged —
it only checks emptiness.

The `entryRow` / `returnRow` backward-compat shims are unchanged — they read
`next(iter(self.entryRows.values()))` which does not depend on key type.

---

## 4. File-by-File Change Map

### 4.1 `src/signalflow/models/node.py`

**Add type alias** at module level (before the dataclass):

```python
PortKey = tuple[int, int]   # (id(node), call_index)
```

**Update Node field annotations** (four dicts + one new list):

```python
input_ports:   dict[PortKey, Port]                      = field(default_factory=dict)
output_ports:  dict[PortKey, Port]                      = field(default_factory=dict)
entryRows:     dict[PortKey, int]                       = field(default_factory=dict)
returnRows:    dict[PortKey, int]                       = field(default_factory=dict)
call_sequence: list[tuple[Node, PortKey, PortKey]]      = field(default_factory=list)
```

**`node_fromDict` — port binding block** (the primary fix):

```python
# BEFORE (lines 166–185):
localInputs = _get_ports(cDict, "input")
if localInputs:
    child.input_ports[id(node)] = localInputs[0]
elif currentInIdx < len(child.unbound_inputs):
    child.input_ports[id(node)] = child.unbound_inputs[currentInIdx]
elif id(node) not in child.input_ports:
    child.input_ports[id(node)] = Port()

portCounters[cKey] = currentInIdx + 1

if childIdx < len(node.unbound_outputs):
    node.output_ports[id(child)] = node.unbound_outputs[childIdx]
else:
    node.output_ports[id(child)] = Port()

# AFTER:
in_key:  PortKey = (id(node),  currentInIdx)
out_key: PortKey = (id(child), currentInIdx)

localInputs = _get_ports(cDict, "input")
if localInputs:
    child.input_ports[in_key] = localInputs[0]
elif currentInIdx < len(child.unbound_inputs):
    child.input_ports[in_key] = child.unbound_inputs[currentInIdx]
else:
    child.input_ports[in_key] = Port()

portCounters[cKey] = currentInIdx + 1

if currentInIdx < len(node.unbound_outputs):
    node.output_ports[out_key] = node.unbound_outputs[currentInIdx]
else:
    node.output_ports[out_key] = Port()

node.call_sequence.append((child, out_key, in_key))
```

Note: the output port slot selection switches from `childIdx` (position in
the YAML calls list) to `currentInIdx` (count of calls to this specific
child from any parent).  For trees where each child appears at most once,
`currentInIdx` and `childIdx` are equal for that child's position, so the
slot selection is identical to before.

**Remove the now-unnecessary guard** on `child.input_ports`:

```python
# REMOVE:
elif id(node) not in child.input_ports:
    child.input_ports[id(node)] = Port()

# The plain `else` branch covers this case with the new key.
```

The de-duplication guard on `children` is **kept unchanged**:
```python
if child not in node.children:
    node.children.append(child)
```

### 4.2 `src/signalflow/lib/layout.py`

**`channelWidth_compute` — child label scan** (lines 39–44):

```python
# BEFORE:
for child in node.children:
    localP: Node.Port | None = child.input_ports.get(id(node))
    if localP:
        lblF = len(localP.signal) if localP.signal else 0
        lblR = len(localP.ret)    if localP.ret    else 0
        maxChildLbl = max(maxChildLbl, lblF, lblR)

# AFTER:
for child in node.children:
    for key, port in child.input_ports.items():
        if key[0] == id(node):   # only ports from this parent
            lblF = len(port.signal) if port.signal else 0
            lblR = len(port.ret)    if port.ret    else 0
            maxChildLbl = max(maxChildLbl, lblF, lblR)
```

**`channelWidth_compute` — parent label scan** (lines 48–53):

```python
# BEFORE:
for child in node.children:
    pPort: Node.Port | None = node.output_ports.get(id(child))
    if pPort:
        lblFP = len(pPort.signal) if pPort.signal else 0
        lblRP = len(pPort.ret)    if pPort.ret    else 0
        maxParentLbl = max(maxParentLbl, lblFP, lblRP)

# AFTER:
for child in node.children:
    for key, port in node.output_ports.items():
        if key[0] == id(child):   # only ports for this child
            lblFP = len(port.signal) if port.signal else 0
            lblRP = len(port.ret)    if port.ret    else 0
            maxParentLbl = max(maxParentLbl, lblFP, lblRP)
```

**`channelWidth_compute` — bus width** (line 57):

```python
# BEFORE:
busW: int = 2 * nCh   # nCh = len(node.children) = unique children

# AFTER — use call_sequence length for the wire count, not unique child count:
busW: int = 2 * len(node.call_sequence)
```

**`layout_compute` step 4 — port row assignment** (lines 174–194):

The loop iterates `n.input_ports` whose keys are now `PortKey`.
The annotation on `pid` changes; the rest of the logic is identical
because `n.entryRows[pid]` and `n.returnRows[pid]` accept `PortKey` keys:

```python
# BEFORE:
parent_id: int
for parent_id in n.input_ports:
    n.entryRows[parent_id] = centeredEntry
    n.returnRows[parent_id] = centeredReturn

pid: int
for i, pid in enumerate(n.input_ports):
    n.entryRows[pid] = n.y + 3 + ewOff + spacing * i
    n.returnRows[pid] = n.y + 4 + ewOff + spacing * i

# AFTER — change type annotations only; logic unchanged:
parent_key: PortKey
for parent_key in n.input_ports:
    n.entryRows[parent_key] = centeredEntry
    n.returnRows[parent_key] = centeredReturn

pkey: PortKey
for i, pkey in enumerate(n.input_ports):
    n.entryRows[pkey] = n.y + 3 + ewOff + spacing * i
    n.returnRows[pkey] = n.y + 4 + ewOff + spacing * i
```

### 4.3 `src/signalflow/models/chip_geometry.py`

**`resolve()` — leftWallRows loop** (lines 298–312):

The loop iterates `node.input_ports.items()`.  `parentId` was `int`; now it
is `PortKey`.  The dict lookups into `entryRows`/`returnRows` use `parentId`
as the key — these dicts now also carry `PortKey` keys, so no logic changes:

```python
# BEFORE annotation:
parentId: int

# AFTER annotation:
parentId: PortKey   # (id(parent), call_index)
```

Everything else in `resolve()` — `rightWallRows`, straight-through
classification, `lCounts`, `portToX`, `allAnchorRows` — reads only from
`node.output_ports.values()` and `node.internal_wiring`, neither of which
is key-type-dependent.  No other changes needed here.

### 4.4 `src/signalflow/lib/wires.py`

This is the most structurally changed file.

**`wireForward_render` signature and key lookups**:

```python
# BEFORE:
def wireForward_render(
    canvas: Canvas, parent: Node, child: Node, color: str | None = None
) -> None:
    pSpacing: int = ...
    pIdx: int = list(parent.output_ports.keys()).index(id(child))
    exitY: int = parent.y + 3 + parent.geometry.ewOff + pSpacing * pIdx
    entryY: int = child.entryRows[id(parent)]
    ...
    # in the stagger branch:
    pIdx = list(parent.output_ports.keys()).index(id(child))
    cIdx = list(child.input_ports.keys()).index(id(parent))
    ...
    # label section:
    pPort: Node.Port | None = parent.output_ports.get(id(child))
    cPort: Node.Port | None = child.input_ports.get(id(parent))

# AFTER:
def wireForward_render(
    canvas: Canvas, parent: Node, child: Node,
    out_key: PortKey, in_key: PortKey,
    color: str | None = None,
) -> None:
    pSpacing: int = ...
    pIdx: int = list(parent.output_ports.keys()).index(out_key)
    exitY: int = parent.y + 3 + parent.geometry.ewOff + pSpacing * pIdx
    entryY: int = child.entryRows[in_key]
    ...
    # in the stagger branch:
    pIdx = list(parent.output_ports.keys()).index(out_key)
    cIdx = list(child.input_ports.keys()).index(in_key)
    ...
    # label section:
    pPort: Node.Port | None = parent.output_ports.get(out_key)
    cPort: Node.Port | None = child.input_ports.get(in_key)
```

**`wireReturn_render` signature and key lookups**:

```python
# BEFORE:
def wireReturn_render(
    canvas: Canvas, parent: Node, child: Node, color: str | None = None
) -> None:
    pIdx: int = list(parent.output_ports.keys()).index(id(child))
    childRetY: int = child.returnRows[id(parent)]
    parentRetY: int = parent.y + 4 + parent.geometry.ewOff + pSpacing * pIdx
    ...
    pIdx = list(parent.output_ports.keys()).index(id(child))
    cIdx = list(child.input_ports.keys()).index(id(parent))
    ...
    pPort: Node.Port | None = parent.output_ports.get(id(child))
    cPort: Node.Port | None = child.input_ports.get(id(parent))

# AFTER:
def wireReturn_render(
    canvas: Canvas, parent: Node, child: Node,
    out_key: PortKey, in_key: PortKey,
    color: str | None = None,
) -> None:
    pIdx: int = list(parent.output_ports.keys()).index(out_key)
    childRetY: int = child.returnRows[in_key]
    parentRetY: int = parent.y + 4 + parent.geometry.ewOff + pSpacing * pIdx
    ...
    pIdx = list(parent.output_ports.keys()).index(out_key)
    cIdx = list(child.input_ports.keys()).index(in_key)
    ...
    pPort: Node.Port | None = parent.output_ports.get(out_key)
    cPort: Node.Port | None = child.input_ports.get(in_key)
```

**`thread_render` — iterate `call_sequence`; guard recursion**:

```python
# BEFORE:
def thread_render(canvas: Canvas, root: Node) -> None:
    def _wire(node: Node) -> None:
        for child in node.children:
            wireForward_render(canvas, node, child)
            _wire(child)
            wireReturn_render(canvas, node, child)
    _wire(root)

# AFTER:
def thread_render(canvas: Canvas, root: Node) -> None:
    def _wire(node: Node) -> None:
        recursed: set[int] = set()
        child: Node
        out_key: PortKey
        in_key:  PortKey
        for child, out_key, in_key in node.call_sequence:
            wireForward_render(canvas, node, child, out_key, in_key)
            if id(child) not in recursed:
                _wire(child)
                recursed.add(id(child))
            wireReturn_render(canvas, node, child, out_key, in_key)
    _wire(root)
```

The `recursed` guard ensures a canonical child's internal wires are drawn
exactly once even when the child appears multiple times in `call_sequence`.

### 4.5 Test Files

Every test that constructs a `Node` manually and accesses its port dicts
by key must be updated.  The pattern is mechanical: `id(x)` → `(id(x), 0)`
for the first (and usually only) call.

Affected test files and the pattern to find call sites:

```bash
grep -n "\.input_ports\[id\|\.output_ports\[id\|entryRows\[id\|returnRows\[id" tests/
grep -n "\.input_ports\.get(id\|\.output_ports\.get(id" tests/
```

Every `child.input_ports[id(parent)]` → `child.input_ports[(id(parent), 0)]`
Every `parent.output_ports[id(child)]` → `parent.output_ports[(id(child), 0)]`
Every `child.entryRows[id(parent)]` → `child.entryRows[(id(parent), 0)]`
Every `child.returnRows[id(parent)]` → `child.returnRows[(id(parent), 0)]`

The `_geo_resolve` helper in `test_chip_geometry.py` builds `entryRows` and
`returnRows` manually — these must also use `PortKey` keys.

---

## 5. Migration Phases

All phases maintain a green test suite.  Never proceed with a failing test.

---

### Phase 0: TDD — Extend the xfail guard and add coverage [🔲]

Extend `TestRepeatedChildPortBinding` in `tests/test_latent_bugs.py` with
additional tests that will become the regression suite once the fix lands:

```python
@pytest.mark.xfail(reason="§1.13: id(child) key collision", strict=True)
def test_repeated_child_gets_distinct_output_ports(self):
    # existing test — unchanged

@pytest.mark.xfail(reason="§1.13: id(child) key collision", strict=True)
def test_repeated_child_both_wires_have_distinct_entry_rows(self):
    """After layout, the two calls must produce two distinct entryRow values."""
    root = Node.node_fromDict(tree_dict_with_repeated_child())
    cw = channelWidth_compute(root)
    layout_compute(root, cw)
    child = next(n for n in tree_flatten(root) if n.func == "work()")
    assert len(child.entryRows) == 2, (
        f"Expected 2 entryRows (one per call), got {child.entryRows}"
    )
    rows = list(child.entryRows.values())
    assert rows[0] != rows[1], f"entryRows must be distinct, got {rows}"

@pytest.mark.xfail(reason="§1.13: id(child) key collision", strict=True)
def test_repeated_child_both_wires_render_without_exception(self):
    """Full render must not raise and must produce non-empty output."""
    from signalflow.engine.render import diagram_render
    lines = diagram_render("test", tree_dict_with_repeated_child_raw())
    assert any(lines), "render produced no output"
```

Add a helper `tree_dict_with_repeated_child()` that builds the Node graph
from the YAML example in Section 1.4, and `tree_dict_with_repeated_child_raw()`
that returns the raw YAML dict for end-to-end rendering.

Gate: new xfail tests exist and fail with `strict=True`.

---

### Phase 1: PortKey + Node fields + node_fromDict [🔲]

Apply the changes described in Section 4.1 exactly.

Specific implementation notes:
- The `PortKey` type alias must be exported from `signalflow/models/__init__.py`
  so that `layout.py` and `wires.py` can import it cleanly.
- In `node_fromDict`, the output slot selection changes from `childIdx` to
  `currentInIdx`.  Verify with `hub.yaml` that the hub topology is
  unaffected: each proxy calls `process()` once, so `currentInIdx` equals
  the sequential counter across all proxies, which is exactly what the current
  code achieves.  The slot from `unbound_outputs` is now selected by
  `currentInIdx` rather than `childIdx` — for hub.yaml these are identical
  because each child appears exactly once.
- Add `call_sequence` field to Node; populate it in `node_fromDict`.
- Run `python -m pytest tests/ -q` after this phase.  The four dicts now
  carry `PortKey` keys; every test that accesses them by `int` key will fail.
  That failure list defines the test update work for this phase.
- Fix all test failures produced by this phase before proceeding.

Gate: 145 passed (xfailed count unchanged — new xfails may become xpass at
this point if the port dict now has two entries for the repeated child).

---

### Phase 2: layout_compute — port row assignment [🔲]

Apply the changes described in Section 4.2 (both `channelWidth_compute` and
`layout_compute` step 4).  The type annotation changes in step 4 are the
only thing needed — the dict operations are key-type-agnostic.

Gate: tests pass; `geometry_validate` does not raise on `hub.yaml`.

---

### Phase 3: chip_geometry.resolve() [🔲]

Apply the annotation-only change in Section 4.3.  Verify that
`leftWallRows` for the repeated-child topology contains two distinct rows
for the two call occurrences by running the Phase 0 test
`test_repeated_child_both_wires_have_distinct_entry_rows` — it should
XPASS after this phase.

Gate: tests pass.

---

### Phase 4: wires.py [🔲]

Apply the changes described in Section 4.4 exactly.  This is the most
structurally significant phase.

Specific notes:
- Every `id(child)` and `id(parent)` key lookup in both wire render
  functions must be replaced with `out_key` or `in_key` respectively.
  There are no exceptions — do a search for any remaining `id(child)` or
  `id(parent)` in wires.py after the edit.
- `thread_render` now drives `node.call_sequence`; the `recursed` guard
  is essential for correctness.  Verify by running the full render on
  `hub.yaml` and confirming visual output is unchanged.
- Run `python -m signalflow examples/hub.yaml` and diff against the
  expected output.

Gate: tests pass; hub.yaml output byte-identical to pre-phase output.

---

### Phase 5: layout.py channelWidth_compute [🔲]

Apply the label scan changes in Section 4.2.  The bus-width formula changes
from `2 * len(node.children)` to `2 * len(node.call_sequence)`.  For
existing topologies these are equal; for repeated-child topologies the
channel will be correctly widened to accommodate the additional wire pair.

Gate: tests pass.

---

### Phase 6: Promote xfail tests [🔲]

All xfail tests in `TestRepeatedChildPortBinding` should now XPASS.  Remove
the `@pytest.mark.xfail` decorators.  Run the full suite.

Gate: **146 passed, 0 xfailed** (145 existing + 1 promoted from xfail;
new Phase 0 tests add to the count).

---

## 6. Acceptance Criteria

```
python -m pytest tests/ -q                          → N passed, 0 xfailed
python -m signalflow examples/hub.yaml              → output unchanged
python -m signalflow <repeated-child-yaml>          → two wires rendered
grep -n "id(child)" src/signalflow/lib/wires.py     → 0 results
grep -n "id(parent)" src/signalflow/lib/wires.py    → 0 results
grep -n "\.input_ports\[id" src/                    → 0 results
grep -n "\.output_ports\[id" src/                   → 0 results
```

The last four greps confirm no code site is still using the old raw-int
key.  Any remaining `id(x)` call in a port-dict context is a bug.

---

## 7. Risk Assessment

The key-type change from `int` to `tuple[int, int]` is a mechanical
substitution throughout.  Python dicts are key-type-agnostic; adding a
second int to the key does not change any of the underlying dict semantics.
The only sources of risk are:

**Missed call sites**.  Any code that constructs or accesses a port dict
using a raw `id(x)` int without updating to a `PortKey` tuple will raise
a `KeyError` at runtime (since the key will not be found).  The acceptance-
criteria greps are the definitive completeness check.

**Slot selection change**.  Switching the output port slot from `childIdx`
to `currentInIdx` is correct for the repeated-child case.  For the
single-call case, `currentInIdx` equals the position-among-calls-to-this-child,
which for a hub topology (many parents, one child) counts upward across all
callers and correctly selects successive `unbound_outputs` slots.  Verify
with the hub topology end-to-end render.

**Bus width for repeated-child parent**.  Changing `2 * nCh` to
`2 * len(node.call_sequence)` widens the channel for repeated-call parents.
This is correct but will shift X coordinates rightward for those chips,
potentially changing the visual output in a non-identical way for diagrams
that exercise this path.  This is expected and correct, not a regression.

**thread_render recursion guard**.  The `recursed` set prevents double-wiring
of a shared child's subtree.  Verify that a canonical Hub chip whose
subtree includes five Sink chips is wired exactly once even if the Hub is
called by five Proxies — this is the existing hub.yaml topology and will
exercise the guard on every run.
