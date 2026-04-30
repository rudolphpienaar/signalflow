# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/CONTEXT.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `agentic/ZEROSHOT.md`

Current branch: `worldscale-extra-routing`.
Current package version: `6.0.3`.

## Immediate Focus

Keep the current snippet-proven world harmonization and materialization logic
inside production board code. The main objects are `WorldGeometryResolver` and
`BoardWorldMaterializedSolution`.

This is no longer a "fix chip alignment" task. Chip row alignment has been
fixed in the inspection truth surface.

## What To Preserve

- Vertical seam alignment comes from shared chip rows.
- North relaxation budget includes `Ne + Nt + Nfi`.
- Horizontal world alignment uses `wOffset`.
- No seam chip override.
- No Wt position transplant.
- `mergedCellMap_get()` key order is `(row, col)`.
- Default ruff and strict `ANN` lint stay clean for touched/recent files.

## Before You Start

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

Expected evidence:

- Zone `1,2` `Et` rows `25..48`.
- Zone `1,3` `Wt` rows `25..48`.
- `grandchild.ts` rows `25..48` on both sides.

## Primary Files For This Phase

- `snippets/algebraic/world_zone_inspect.py`
- `src/signalflow/board/geometry/world_resolver.py`
- `src/signalflow/board/world_runtime.py`
- `src/signalflow/engine/inspect/zone_local.py`
- `src/signalflow/board/geometry/georules.py`
- `src/signalflow/board/geometry/zones.py`
- `src/signalflow/board/materialized_runtime.py`
- `src/signalflow/board/render.py`
- `tests_symbolic/test_georules.py`
- `tests_symbolic/test_symbolic_kernel_quarantine.py`

## Things Not To Do

- Do not re-open solved seam-chip alignment as an unsolved design problem.
- Do not restore north-stack vertical Phase 5c offsets.
- Do not revive full-world seam/interconnect rendering as the solution path.
- Do not start Arc G symbolic topology/interpreter work before world resolver
  extraction lands.
