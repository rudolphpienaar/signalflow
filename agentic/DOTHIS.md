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
# expect: 178 passed
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

Harden the new top-level world render path and keep it in parity with the
snippet truth surface.

Current core object:

```text
src/signalflow/board/geometry/world_resolver.py
```

Landed API:

```text
WorldGeometryResolver.harmonized_chain_build(...)
```

`signalflow file.yaml` now renders the full harmonized world circuit by
default. `world_zone_inspect.py` remains a thin caller and parity witness.

## What Is Already Fixed

Do not redo these as open design questions:

- Seam chip vertical differential is fixed in `world_zone_inspect.py`.
- Vertical world offsets are chip-row aligned, not north-stack accumulated.
- North relaxation budget includes `Ne + Nt + Nfi`.
- `Ne`/`Se` four-lane spans are preserved where the zone owns only four lanes.
- Zone `1,2` no longer shows `Et` extending outside the module boundary.
- `grandchild.ts` is row-aligned across the `1,2` / `1,3` seam.
- Forward-only omitted-return rendering is fixed: no blank reverse rows, no
  implicit return routes, and `return: ""` is rejected.

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

Main CLI controls:

1. `signalflow file.yaml` renders all active zones as wiring.
2. `--zone 2` or `--zone 1,2` filters output after full harmonization.
3. `--zones '1,2;1,3'` filters sequential zones after full harmonization.
4. `--geometry` shows relaxed per-zone geometry.
5. `--wiring` shows composed world wiring.

## Required Verification

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run signalflow \
  examples/simple-circuit/back-and-forth.yaml
```

Check:

- Output starts with `--- WORLD CIRCUIT ---`.
- Output includes `--- WORLD WIRING: (1,1)  (1,2)  (1,3) ---`.
- The full world render includes `grandchild.ts`.

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run signalflow \
  examples/simple-circuit/neural-network.yaml
```

Check:

- The render contains `x1w11` and `h3v32`.
- The render contains no `◄` return-arrow stubs.

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --zones '1,2;1,3' --geometry
```

Check:

- `zones: (1,2) off=0  (1,3) off=64`.
- Zone `1,2` `Et` rows `25..48`.
- Zone `1,3` `Wt` rows `25..48`.
- Both sides show `grandchild.ts` rows `25..48`.
- Zone `1,3` `Ne` rows `17..20`.

Legacy snippet parity check:

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --geometry
```

Check:

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
