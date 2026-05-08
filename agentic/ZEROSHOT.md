# Zero-Shot Handoff: `worldscale-extra-routing`

## Current Truth In One Screen

- Branch: `worldscale-extra-routing`
- Version: `6.0.19`
- Full symbolic tests: `195 passed`
- Recent-file ruff: clean
- Recent-file strict annotation lint (`ANN`): clean
- Per-zone overlap routing is stable for zones `1,1`, `1,2`, `1,3`.
- Multi-zone world inspect is stable for the key `1,2` / `1,3` seam.
- `signalflow file.yaml` renders the full harmonized world circuit by default.
- Seam chip vertical alignment is fixed.
- Forward-only omitted-return semantics are fixed.
- Wire-crossing at module box walls fixed; `wiring_sprint` direct-blit refactor done.
- Orphaned terminal partial fix landed (multiple-callers-to-same-chip case).
  `back-and-forth.yaml` is clean. Real-world sftc YAML still has orphaned terminals.
  Orphaned wiring NOT fully solved.
- Active work: split source modules from load-bearing geometry scopes. Call
  depth layers should become implicit geometry scopes; source modules stay
  source identity.

## Key Facts

- Use `signalflow file.yaml` as the default world render surface.
- Use `snippets/algebraic/world_zone_inspect.py` as the parity/debug surface.
- Core harmonization lives in `WorldGeometryResolver`.
- Core world materialization/rendering lives in
  `BoardWorldMaterializedSolution`.
- The old open issue "Phase 5c north-stack offset breaks seam chip alignment"
  is resolved.
- Correct vertical model: align shared seam chips by row.
- Correct north relaxation budget: include `Ne + Nt + Nfi`.
- Correct horizontal model: align terminal columns using `wOffset`.
- Correct port model: omitted `return` means no reverse terminal and no reverse
  route; `return: ""` is invalid.
- `mergedCellMap_get()` key is `(row, col)`.
- No seam chip override. No Wt position transplant.
- `ChipId.moduleName` is not a stack-depth layer.
- The current fake layer module names in neural-network examples are a
  workaround.
- New doctrine target: implicit call-depth geometry layers always exist,
  default non-drawable; source module/file boxes are optional overlays or
  explicitly promoted structural groups.
- `calling_stack.py` currently has module-banded depth behavior when multiple
  modules exist. Treat that as suspect for the next sprint.
- Target carrier name can be `BoardGeometryScope`:
  `scopeId`, `kind`, `label`, `chipRefs`, `drawable`.
- Scope ids should distinguish `layer/0` from `module/foo.c`; do not encode
  depth layers as fake module names.
- Keep `effectiveBoundaryFramesByName` only as a compatibility projection if
  needed.
- **Orphaned wiring is an open bug**. Partial fix in `routing/kernel_solver.py`
  (`_destinationPortDeclarationOrNone_get` clamp + `lastFound` fallback). Fixed
  `back-and-forth.yaml`; real-world sftc YAML still has cases. Root cause for
  remaining cases not yet identified.

## Fixture

`examples/simple-circuit/back-and-forth.yaml`

- `1,1`: `parent.ts` ↔ `child.ts`
- `1,2`: `child.ts` ↔ `grandchild.ts`
- `1,3`: `grandchild.ts` ↔ `greatgrandchild.ts`

Current seam evidence for `1,2;1,3`:

- Zone `1,2` `Et`: rows `25..48`
- Zone `1,3` `Wt`: rows `25..48`
- `grandchild.ts`: rows `25..48` on both sides
- Zone `1,3` `Ne`: rows `17..20`

Next acceptance fixture:

- Neural network with all chips in one real source module still lays out by
  call depth.
- Depth-layer scopes exist but are non-drawable by default.
- Source-module boxes are optional overlays or explicitly structural groups.

## First Commands

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

## Most Important Files

- `agentic/HANDOFF.md`
- `agentic/CONTEXT.md`
- `agentic/NON-NEGOTIABLES.md`
- `snippets/algebraic/world_zone_inspect.py`
- `src/signalflow/engine/world_render.py`
- `src/signalflow/__main__.py`
- `src/signalflow/board/geometry/world_resolver.py`
- `src/signalflow/board/world_runtime.py`
- `src/signalflow/models/calling_stack.py`
- `src/signalflow/models/assignment.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/board/geometry/georules.py`
- `src/signalflow/engine/inspect/zone_local.py`
- `src/signalflow/board/materialized_runtime.py`
- `tests_symbolic/test_georules.py`
- `tests_symbolic/test_symbolic_kernel_quarantine.py`
