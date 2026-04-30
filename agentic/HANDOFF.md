# Handoff: `worldscale-extra-routing`

## Snapshot

- Branch: `worldscale-extra-routing`
- Package version: `6.0.3`
- Date: April 29, 2026
- Full symbolic suite: `173 passed`
- Recent Python lint gates:
  - `ruff check` on Python files changed in the last week: clean
  - `ruff check --select ANN` on Python files changed in the last week: clean
- Focused regression suite:
  - `tests_symbolic/test_georules.py`
  - `tests_symbolic/test_symbolic_kernel_quarantine.py`
  - `120 passed`

## Current Truth

The old north-stack Phase 5c problem is resolved in the snippet truth surface.
World vertical placement is now chip-alignment driven: adjacent overlap zones
line up shared seam chips by their chip terminal rows, while Ne/Se stay bounded
to their actual four-lane spans where appropriate.

Verified current fixture behavior:

- Zones `1,2` and `1,3` render together with `grandchild.ts` aligned across the
  seam.
- `grandchild.ts` is bounded at rows `25..48` on both seam sides.
- Zone `1,2` no longer shows `Et` escaping above/below its module boundary.
- Zone `1,3` has `Ne` rows `17..20`.
- Zone `1,2` has `Ne` rows `11..14` in the current harmonized two-zone view.
- `Ne` / `Se` keep four-lane span for the relevant edge zones; the previous
  eight-row/ghost-span error is gone.

## What Changed This Session

### Geometry/Harmonization

- Relaxation span accounting includes `Ne`, `Nt`, and `Nfi`, so north-band row
  budgets include the chip-terminal and fan-in/out bands that previously caused
  a two-row count error.
- Vertical chip overlap differential is solved by seam-chip row alignment,
  not north-stack accumulation.
- The old surgical chip-terminal vertical override remains forbidden. The
  current path keeps each zone materialized against its own geometry and derives
  world offsets from geometry/chip rows.
- `sfN.Z DISPLACE_VERTICAL` exists in `georules.py` for whole-zone vertical
  displacement.

### Style/Lint

- All recent Python files were formatted.
- Default ruff is clean over the recent-file sweep.
- Strict annotation lint (`ANN`) is clean over the recent-file sweep.
- Obvious untyped mutable locals were annotated.
- Long RPN compatibility names have documented `# noqa: E501` only where the
  RPN/public name itself is the reason the line cannot reasonably wrap.

## Active Code/Truth Surface

`src/signalflow/board/geometry/world_resolver.py` now owns the active
chain-harmonization logic. `src/signalflow/board/world_runtime.py` now owns the
materialized world aggregate and geometry/wiring text surfaces.
`snippets/algebraic/world_zone_inspect.py` is the current canonical inspection
surface, but it is now a thin CLI-style caller.

Current phase shape:

| Phase | Role | Current Status |
| --- | --- | --- |
| 4a | Core `WorldGeometryResolver.harmonized_chain_build()` | active |
| 4b | Core `BoardWorldMaterializedSolution` aggregate | active |
| 5 | Re-origin requested-zone output from resolver `wOffsets` | active in aggregate |
| 6 | Geometry/wiring render output | active in aggregate |

## Verification Commands

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests_symbolic/ -q
# expect: 173 passed

find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -mtime -7 -print \
  | sort \
  | xargs env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check

find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -mtime -7 -print \
  | sort \
  | xargs env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check --select ANN
```

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --geometry

env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --wiring
```

## Fixture Shape

`examples/simple-circuit/back-and-forth.yaml` remains the canonical fixture.

- Zone `1,1`: `parent.ts` ↔ `child.ts`
- Zone `1,2`: `child.ts` ↔ `grandchild.ts`
- Zone `1,3`: `grandchild.ts` ↔ `greatgrandchild.ts`

The important seam for the current work is `1,2` ↔ `1,3`, because
`grandchild.ts` is present on both sides and falsifies row-origin drift.

## Next Work

1. Keep `WorldGeometryResolver`, `BoardWorldMaterializedSolution`, and
   `world_zone_inspect.py` in parity.
2. Move context/YAML assembly into a production call path when ready; the
   snippet should not regain materialization or render algebra.
3. Only after this production integration is stable, resume Arc G symbolic
   topology/interpreter work.

## Non-Negotiables

- Do not reintroduce seam chip override or chip position transplant.
- Do not use north-stack accumulation as the vertical world-origin rule.
- Do not treat overlap as an occupancy exception.
- `mergedCellMap_get()` key is `(row, col)`.
- Use `sfN.*.region_key` / first-class region IDs, not hardcoded region strings.
- Keep `ruff`, `ruff --select ANN`, and symbolic tests green for touched scope.
