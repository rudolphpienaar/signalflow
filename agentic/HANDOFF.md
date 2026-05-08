# Handoff: `worldscale-extra-routing`

## Snapshot

- Branch: `worldscale-extra-routing`
- Package version: `6.0.19`
- Date: May 2026
- Full symbolic suite: `195 passed`
- Recent Python lint gates:
  - `ruff check` on Python files changed in the last week: clean
  - `ruff check --select ANN` on Python files changed in the last week: clean
- Focused regression suite:
  - `tests_symbolic/test_board_module_contract.py`
  - `tests_symbolic/test_symbolic_kernel_quarantine.py`
  - forward-only port regressions passed
  - neural-network DAG fixture regressions passed
  - semantic wiring invariant tests passed (added this sprint)

## Current Truth

### World Geometry

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

### Forward-Only Ports

Forward-only port semantics are resolved:

- Omitting `return` means a single forward signal lane.
- `return: ""` is invalid.
- Chip geometry does not allocate blank return rows.
- Kernel and seam solvers emit reverse routes only when both endpoints declare
  non-empty return labels.
- `examples/simple-circuit/neural-network.yaml` is the canonical forward-only
  fan-out fixture.
- `examples/simple-circuit/neural-network-explicit-pairs.yaml` demonstrates
  explicit per-edge destination input ports for DAG-style fan-in and now ends
  in `result.ts:output()` with `y1` and `y2` inputs.

### Module Boundary Rendering

Recent sprint hardened wire-crossing algebra and module box rendering:

- `wiring_sprint` refactored to direct world-grid blit (killed two-layer
  compositing).
- Module box frames and depth box frames are now flag-invariant.
- Wire-crossing at module box walls corrected using `MODULE_BOX` scope kind.
- Inter-module padding and wire-crossing algebra fixed.
- Semantic wiring invariant tests added (`tests_symbolic/test_wiring_invariants.py`
  or equivalent).

### Orphaned Terminal Fix (Partial)

Root cause identified and partially fixed in `routing/kernel_solver.py`:

- **Problem**: when multiple callers target the same callee chip, `destinationPortIndex`
  increments per grouped-obligation batch. When it exceeds the callee's actual
  port count, `_destinationPortDeclarationOrNone_get` returned `None`, causing
  `_obligationHasReturn_check` to return `False` → no return route computed →
  orphaned terminal.
- **Fix 1**: `_destinationPortDeclarationOrNone_get` now clamps
  `destinationPortIndex` to `len(inputPortDeclarations) - 1` instead of
  returning `None`.
- **Fix 2**: `_terminalBodyRow_get` now tracks `lastFound` so when
  `occurrenceBefore` exceeds available offsets, it returns the last matching
  terminal row instead of the wrong fallback formula.
- **Verified fixed**: `gc2().ggc2ret` in `back-and-forth.yaml` now shows `╫`
  crossing. Not a regression — structural gap never previously exercised by a
  test fixture.
- **Still open**: `narrowed` terminal orphan visible in real-world sftc-generated
  YAML. Other orphan cases may exist. Orphaned wiring problem is NOT fully solved.

### Neural-Network Layer Examples

Current neural-network layer examples still use structural module boundaries as
a workaround:

- `inputLayer.ts`, `hiddenLayer.ts`, and `outputLayer.ts` are real geometric
  envelopes, not just labels.
- Without those boundaries, the engine still knows call-stack depth, but it
  does not yet synthesize depth-derived layer envelopes as a fallback.
- This is not the final doctrine. Real `module` names must remain source
  identity, not stack-depth identity.

## Next Sprint: Depth-Layer Geometry

The next work is to separate three concepts that are currently conflated:

- Source identity: `ChipId(moduleName, functionName)` remains the source/file
  identity and canonical chip key.
- Geometry scope: call-stack depth layers become implicit load-bearing geometry
  groups, always present even when not drawn.
- Drawable boundary: rendering a box is a policy flag, not proof that a
  geometry scope exists.

Important code fact: `src/signalflow/models/calling_stack.py` currently switches
to module-banded depth when more than one module exists. That is now suspect.
The next sprint should make call depth the canonical layer source and stop
letting module names decide depth-layer geometry.

Recommended implementation direction:

1. Introduce a first-class geometry-boundary/scope model with at least
   `kind`, stable id/name, owning chip refs, and `drawable`.
2. Generate implicit depth-layer scopes from `CallingStack.levels`.
3. Keep implicit depth-layer scopes non-drawable by default.
4. Treat source module/file boundaries as optional overlays or explicit
   structural groups, not the default load-bearing geometry primitive.
5. Retarget boundary normalization, coupling, and world harmonization from
   `module/*` assumptions toward the new geometry-scope owner.
6. Add regressions where all neural-network chips share one real source module
   and still lay out correctly by depth.

Concrete target shape:

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
- `module/neural-network.c`, `module/result.ts`, ... for source-module
  overlays or explicitly promoted structural groups.

Transition rule: keep `effectiveBoundaryFramesByName` as a compatibility
projection if needed, but do not let string keys like `module/*` remain the
semantic owner.

Acceptance examples:

- A neural-network fixture with every chip in `module: neural-network.c` still
  lays out as input, hidden, output, and result depth layers.
- Different real source modules at the same call depth share one depth-layer
  geometry scope by default.
- Depth-layer scopes are geometry-active by default but do not draw boxes unless
  configured drawable.
- Existing `back-and-forth.yaml` seam evidence does not regress.

## Active Open Bug: Orphaned Wiring

Orphaned terminals (chip stub reaches module wall `║` without `╫` crossing)
remain an open bug in general. The `kernel_solver.py` fix addresses the
multiple-callers-to-same-chip case, but other cases remain:

- `narrowed` terminal orphan in real-world sftc-generated YAML confirms more
  cases exist.
- General class: any case where the routing kernel does not emit a return route
  or emits a route that fails the board attach-point lookup.
- `back-and-forth.yaml` fixture appears clean after the fix. Real-world YAML
  from sftc is not clean.

Investigation should continue in parallel with depth-layer geometry work.

## What Changed This Session (May 2026)

### Orphaned Terminal Fix

- `_destinationPortDeclarationOrNone_get` in `routing/kernel_solver.py`: clamp
  index to last valid port when multiple callers exceed chip port count.
- `_terminalBodyRow_get` in `routing/kernel_solver.py`: `lastFound` fallback so
  callers beyond chip port count still resolve to the correct terminal row.
- `examples/simple-circuit/back-and-forth.yaml`: `gc2().ggc2ret` confirmed fixed.

### Wire-Crossing and Module Box Rendering (Earlier This Sprint)

- Refactored `wiring_sprint` to direct world-grid blit.
- Made module and depth box frames flag-invariant.
- Fixed wire-crossing at module box walls (`MODULE_BOX` scope kind).
- Fixed inter-module padding and wire-crossing algebra.
- Added semantic wiring invariant tests.

### Previous Sprint (Geometry/Harmonization)

- Relaxation span accounting includes `Ne`, `Nt`, and `Nfi`.
- Vertical chip overlap differential solved by seam-chip row alignment.
- `sfN.Z DISPLACE_VERTICAL` exists in `georules.py` for whole-zone vertical
  displacement.
- Forward-only ports: compact declared terminal rows, no blank return stubs.
- Ruff and ANN lint clean over touched files.

## Active Code/Truth Surface

`src/signalflow/board/geometry/world_resolver.py` owns the active
chain-harmonization logic. `src/signalflow/board/world_runtime.py` owns the
materialized world aggregate and geometry/wiring text surfaces.
`signalflow file.yaml` renders the full harmonized world circuit by default.
`snippets/algebraic/world_zone_inspect.py` is the current canonical inspection
surface, but it is now a thin CLI-style caller.

Current phase shape:

| Phase | Role | Current Status |
| --- | --- | --- |
| 4a | Core `WorldGeometryResolver.harmonized_chain_build()` | active |
| 4b | Core `BoardWorldMaterializedSolution` aggregate | active |
| 5 | Re-origin requested-zone output from resolver `wOffsets` | active in aggregate |
| 6 | Geometry/wiring render output | active in aggregate |
| 7 | Top-level `signalflow file.yaml` world render | active |

## Verification Commands

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

```bash
python -m signalflow examples/simple-circuit/back-and-forth.yaml

python -m signalflow examples/simple-circuit/neural-network.yaml
# expect: no return-arrow stubs (`◄`) in the forward-only render

python -m signalflow examples/simple-circuit/neural-network-explicit-pairs.yaml \
  --zones '1,2;1,3' --wiring
# expect: explicit labels such as x1w11 -> h1:x1w11 and h2v21 -> y1:h2v21

python -m signalflow examples/simple-circuit/back-and-forth.yaml \
  --zones '1,2;1,3' --geometry
```

## Fixture Shape

`examples/simple-circuit/back-and-forth.yaml` remains the canonical fixture.

- Zone `1,1`: `parent.ts` ↔ `child.ts`
- Zone `1,2`: `child.ts` ↔ `grandchild.ts`
- Zone `1,3`: `grandchild.ts` ↔ `greatgrandchild.ts`

The important seam for the current work is `1,2` ↔ `1,3`, because
`grandchild.ts` is present on both sides and falsifies row-origin drift.

## Next Work

1. Fix remaining orphaned terminal cases (real-world sftc YAML, `narrowed`
   terminal and similar). Diagnose whether root cause is kernel_solver, chip
   geometry, or board endpoint lookup.
2. Design and implement depth-layer geometry scopes without repurposing
   `module`.
3. Preserve `WorldGeometryResolver`, `BoardWorldMaterializedSolution`, and
   top-level `signalflow` parity while changing boundary ownership.
4. Add neural-network regressions that no longer require fake layer module
   names.
5. Only after depth-layer geometry is stable, resume Arc G symbolic
   topology/interpreter work.

## Non-Negotiables

- Do not reintroduce seam chip override or chip position transplant.
- Do not use north-stack accumulation as the vertical world-origin rule.
- Do not treat overlap as an occupancy exception.
- `mergedCellMap_get()` key is `(row, col)`.
- Use `sfN.*.region_key` / first-class region IDs, not hardcoded region strings.
- Do not conflate source modules with call-depth geometry scopes.
- Drawable boundary and geometry scope are separate concepts.
- Keep `ruff`, `ruff --select ANN`, and symbolic tests green for touched scope.
