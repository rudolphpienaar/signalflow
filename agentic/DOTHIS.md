# Do This Next

Read in order:

1. `agentic/HANDOFF.md`
2. `agentic/CONTEXT.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `src/signalflow/board/geometry/world_resolver.py`
5. `snippets/algebraic/world_zone_inspect.py`

## Baseline

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests_symbolic/ -q
# expect: 173 passed
```

```bash
find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -mtime -7 -print \
  | sort \
  | xargs env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check

find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -mtime -7 -print \
  | sort \
  | xargs env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check --select ANN
```

## Active Job

Integrate the extracted world harmonization model into the production call
path above the snippet.

Current core object:

```text
src/signalflow/board/geometry/world_resolver.py
```

Landed API:

```text
WorldGeometryResolver.harmonized_chain_build(...)
```

`world_zone_inspect.py` is now a thin caller: it builds overlap-zone contexts,
calls the resolver, builds `BoardWorldMaterializedSolution`, and prints that
aggregate's geometry/wiring surfaces.

## What Is Already Fixed

Do not redo these as open design questions:

- Seam chip vertical differential is fixed in `world_zone_inspect.py`.
- Vertical world offsets are chip-row aligned, not north-stack accumulated.
- North relaxation budget includes `Ne + Nt + Nfi`.
- `Ne`/`Se` four-lane spans are preserved where the zone owns only four lanes.
- Zone `1,2` no longer shows `Et` extending outside the module boundary.
- `grandchild.ts` is row-aligned across the `1,2` / `1,3` seam.

## Current Integration Target

The reusable production surface now exists:

```text
src/signalflow/board/world_runtime.py
BoardWorldMaterializedSolution
```

It owns:

1. Build active overlap-zone contexts.
2. Call `WorldGeometryResolver.harmonized_chain_build(...)`.
3. Materialize each zone with its harmonized geometry via
   `BoardWorldMaterializedSolution.fromResolvedChain_build(...)`.
4. Emit composable `geometry_sprint(...)` and `wiring_sprint(...)` surfaces.

Keep the snippet as a truth surface, but it should remain thin: context/YAML
setup outside, resolver + world aggregate inside core board code.

## Required Verification

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --geometry
```

Check:

- Zone `1,2` `Et` rows `25..48`.
- Zone `1,3` `Wt` rows `25..48`.
- Both sides show `grandchild.ts` rows `25..48`.
- Zone `1,3` `Ne` rows `17..20`.
- No resurrected `Ne` ghost span.

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --wiring
```

Check:

- Seam routes remain visible.
- No clipping from `(row, col)` confusion.
- No chip-position transplant appears in code or output.

## Do Not Do

- Do not restore the north-stack Phase 5c offset.
- Do not reintroduce Wt-only vertical chip override.
- Do not treat `RoutingZoneInterconnect` as the routed body.
- Do not start Arc G symbolic-topology interpreter work before resolver
  extraction has a stable gate.
