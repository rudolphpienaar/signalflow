# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/CONTEXT.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `agentic/ZEROSHOT.md`

Current branch: `worldscale-extra-routing`.
Current package version: `6.0.7`.

## Immediate Focus

Next sprint: split source modules from load-bearing geometry scopes.

Current `module` must remain source identity / chip identity. It must not be
treated as a call-stack-depth layer. The next architecture target is an
implicit, always-present call-depth geometry scope system: depth layers exist in
geometry even when they are not drawn. Drawable boundaries become a separate
policy from geometric existence.

The main likely owner path is:

- `src/signalflow/models/calling_stack.py`
- `src/signalflow/models/assignment.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/board/geometry/world_resolver.py`
- `src/signalflow/board/render.py`
- `src/signalflow/engine/inspect/zone_local.py`

This is no longer a "fix chip alignment" task. Chip row alignment has been
fixed in the inspection truth surface.

Forward-only omitted-return semantics are also fixed. A port with `signal` and
no `return` has only one lane; do not recreate blank reverse rows or implicit
return routes. A present empty return label is invalid.

## What To Preserve

- Vertical seam alignment comes from shared chip rows.
- North relaxation budget includes `Ne + Nt + Nfi`.
- Horizontal world alignment uses `wOffset`.
- No seam chip override.
- No Wt position transplant.
- `mergedCellMap_get()` key order is `(row, col)`.
- Default ruff and strict `ANN` lint stay clean for touched/recent files.
- `examples/simple-circuit/neural-network.yaml` remains forward-only: its
  render should not contain `◄` return stubs.
- `ChipId.moduleName` remains source/module identity. Do not repurpose it as a
  layout layer.
- Call-stack depth layers are the new load-bearing geometry scope candidate.
- Implicit depth layers should exist geometrically by default and should be
  non-drawable by default.
- Real source module/file boxes should become optional drawable overlays unless
  explicitly promoted to structural geometry.

## Before You Start

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests_symbolic/ -q
# expect: 179 passed
```

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --geometry

env UV_CACHE_DIR=/tmp/uv-cache uv run signalflow \
  examples/simple-circuit/back-and-forth.yaml

env UV_CACHE_DIR=/tmp/uv-cache uv run signalflow \
  examples/simple-circuit/neural-network.yaml
```

Expected evidence:

- Zone `1,2` `Et` rows `25..48`.
- Zone `1,3` `Wt` rows `25..48`.
- `grandchild.ts` rows `25..48` on both sides.

## Primary Files For This Phase

- `snippets/algebraic/world_zone_inspect.py`
- `src/signalflow/__main__.py`
- `src/signalflow/engine/world_render.py`
- `src/signalflow/board/geometry/world_resolver.py`
- `src/signalflow/board/world_runtime.py`
- `src/signalflow/engine/inspect/zone_local.py`
- `src/signalflow/board/geometry/georules.py`
- `src/signalflow/board/geometry/zones.py`
- `src/signalflow/board/materialized_runtime.py`
- `src/signalflow/board/render.py`
- `src/signalflow/models/calling_stack.py`
- `src/signalflow/models/assignment.py`
- `tests_symbolic/test_georules.py`
- `tests_symbolic/test_symbolic_kernel_quarantine.py`

## Things Not To Do

- Do not rename or reinterpret real modules as stack-depth layers.
- Do not keep using fake modules such as `inputLayer.ts` as the final model for
  depth grouping.
- Do not make drawable boundaries the proof that geometry scopes exist.
- Do not re-open solved seam-chip alignment as an unsolved design problem.
- Do not restore north-stack vertical Phase 5c offsets.
- Do not revive full-world seam/interconnect rendering as the solution path.
- Do not start broad Arc G symbolic topology/interpreter work before the
  depth-layer geometry split is stable.
