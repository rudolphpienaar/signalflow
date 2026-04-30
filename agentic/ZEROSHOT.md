# Zero-Shot Handoff: `worldscale-extra-routing`

## Current Truth In One Screen

- Branch: `worldscale-extra-routing`
- Version: `6.0.3`
- Full symbolic tests: `173 passed`
- Recent-file ruff: clean
- Recent-file strict annotation lint (`ANN`): clean
- Per-zone overlap routing is stable for zones `1,1`, `1,2`, `1,3`.
- Multi-zone world inspect is stable for the key `1,2` / `1,3` seam.
- Seam chip vertical alignment is fixed.
- Active work: keep snippet-proven world harmonization/materialization in
  production board code.

## Key Facts

- Use `snippets/algebraic/world_zone_inspect.py` as the current truth surface.
- Core harmonization lives in `WorldGeometryResolver`.
- Core world materialization/rendering lives in
  `BoardWorldMaterializedSolution`.
- The old open issue "Phase 5c north-stack offset breaks seam chip alignment"
  is resolved.
- Correct vertical model: align shared seam chips by row.
- Correct north relaxation budget: include `Ne + Nt + Nfi`.
- Correct horizontal model: align terminal columns using `wOffset`.
- `mergedCellMap_get()` key is `(row, col)`.
- No seam chip override. No Wt position transplant.

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

## First Commands

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests_symbolic/ -q
# expect: 173 passed
```

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --geometry
```

## Most Important Files

- `agentic/HANDOFF.md`
- `agentic/CONTEXT.md`
- `agentic/NON-NEGOTIABLES.md`
- `snippets/algebraic/world_zone_inspect.py`
- `src/signalflow/board/geometry/world_resolver.py`
- `src/signalflow/board/world_runtime.py`
- `src/signalflow/board/geometry/georules.py`
- `src/signalflow/engine/inspect/zone_local.py`
- `src/signalflow/board/materialized_runtime.py`
- `tests_symbolic/test_georules.py`
- `tests_symbolic/test_symbolic_kernel_quarantine.py`
