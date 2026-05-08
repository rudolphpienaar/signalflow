# Do This Next

Read in order:

1. `agentic/HANDOFF.md`
2. `agentic/CONTEXT.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `src/signalflow/models/calling_stack.py`
5. `src/signalflow/board/builders.py`
6. `src/signalflow/board/geometry/world_resolver.py`
7. `snippets/algebraic/world_zone_inspect.py`

## Baseline

```bash
python -m pytest -q
# expect: 195 passed
```

```bash
find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -mtime -7 -print \
  | sort \
  | xargs env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check

find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -mtime -7 -print \
  | sort \
  | xargs env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check --select ANN
```

## Active Jobs (Priority Order)

### 1. Finish fixing orphaned terminals (active bug)

Orphaned terminals (chip stub reaches module wall `║` without `╫` crossing)
are partially fixed. `back-and-forth.yaml` is clean after the May 2026
`kernel_solver.py` fix. Real-world sftc YAML still shows orphaned `narrowed`
terminal and possibly others.

The partial fix:
- `_destinationPortDeclarationOrNone_get`: clamp `destinationPortIndex` to last
  valid port when multiple callers exceed chip port count.
- `_terminalBodyRow_get`: `lastFound` fallback when `occurrenceBefore` exceeds
  available offsets.

Next: diagnose the `narrowed` orphan in sftc YAML — is it the same root cause
(multiple callers), a different canonical/display name mismatch, or a board
endpoint lookup failure?

### 2. Implement depth-layer geometry (next sprint)

Implement the next boundary doctrine: source modules stay source identity, while
call-stack depth layers become implicit load-bearing geometry scopes.

Current core object:

```text
src/signalflow/models/calling_stack.py
src/signalflow/board/builders.py
src/signalflow/board/geometry/world_resolver.py
```

Current trap:

```text
ChipId.moduleName is source identity. It is not a depth layer.
```

The geometry engine currently treats `module/*` boundaries as load-bearing
effective boundaries. That made fake layer modules (`inputLayer.ts`,
`hiddenLayer.ts`, `outputLayer.ts`) work, but it is not the final model.

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

Build a first-class geometry scope/boundary concept:

```text
depth layer scope: implicit, geometry-active, non-drawable by default
source module scope: real source identity, optional drawable overlay
```

Suggested carrier:

```python
@dataclass(frozen=True)
class BoardGeometryScope:
    scopeId: str
    kind: BoardGeometryScopeKind
    label: str
    chipRefs: tuple[ChipRef, ...]
    drawable: bool
```

Suggested scope ids:

- `layer/0`, `layer/1`, ... for implicit call-depth geometry scopes.
- `module/<source>` for source-module overlays or explicitly structural module
  groups.

Likely steps:

1. Audit where `effectiveBoundaryFramesByName` assumes `module/*`.
2. Remove or replace module-banded depth behavior in `calling_stack.py`.
3. Generate implicit depth-layer geometry scopes from `CallingStack.levels`.
4. Keep implicit depth layers non-drawable unless explicitly configured.
5. Preserve optional source-module/file boxes as overlays or explicit
   structural groups.
6. Update world harmonization so chip/boundary translation follows geometry
   scopes, not source module names.
7. Add regressions proving a neural network in one real source module still
   lays out by depth.

Acceptance fixture shape:

1. Copy or derive the explicit-pairs neural network so all chips use
   `module: neural-network.c` except the final `result.ts` sink if needed for
   source-identity coverage.
2. Confirm depth scopes still separate:
   `network()`, `x*()`, `h*()`, `y*()`, `output()`.
3. Confirm default render does not need to draw depth-layer boxes to be
   geometrically correct.
4. Confirm `back-and-forth.yaml --zones '1,2;1,3' --geometry` preserves the
   existing seam rows.

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

- Do not repurpose `module` as a depth layer.
- Do not make fake layer modules the permanent solution.
- Do not require a boundary to be drawable for it to exist geometrically.
- Do not restore the north-stack Phase 5c offset.
- Do not reintroduce Wt-only vertical chip override.
- Do not treat `RoutingZoneInterconnect` as the routed body.
- Do not start broad Arc G symbolic-topology interpreter work before the
  depth-layer geometry split has a stable gate.
