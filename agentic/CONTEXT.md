# Project Context: `worldscale-extra-routing`

This file is the current routing/geometry baseline for this branch.

## Snapshot

- Branch: `worldscale-extra-routing`
- Package version: `6.0.5`
- Full symbolic suite: `178 passed`
- Recent-file lint:
  - default `ruff check`: clean
  - `ruff check --select ANN`: clean
- Canonical fixture: `examples/simple-circuit/back-and-forth.yaml`

## Stable Architecture

- Board-owned geometry is the active geometry center:
  `GeometryZone`, `BoardGeometry`, and board materialization own concrete
  frames and exact terminals.
- Overlap zones are the current truth surface for world-scale routing:
  `1,1`, `1,2`, and `1,3`.
- Per-zone solve/materialize/render is stable.
- Extra-ring geometry and medial pillars exist and are rendered.
- `WorldGeometryResolver` owns active world chain harmonization.
- `BoardWorldMaterializedSolution` owns materialized world geometry/wiring
  render surfaces.
- `signalflow file.yaml` is the default full-world render surface.
- `world_zone_inspect.py` is the multi-zone parity/debug surface and should
  stay a thin caller.
- `world_zone_overlap_materialize.py` remains useful but is not the newest
  evidence for vertical chip alignment.
- Forward-only omitted-return semantics are core behavior. A missing `return`
  key means one signal lane only; the engine must not synthesize blank return
  stubs or reverse routes.

## Geo-Displacement Algebra

Engine: `geometry_change(changes, geometry)` in
`src/signalflow/board/geometry/georules.py`.

| Anchor | Op | Effect |
| --- | --- | --- |
| `sfN.Z` | `DISPLACE` | translate all zones horizontally |
| `sfN.Z` | `DISPLACE_VERTICAL` | translate all zones vertically |
| `sfN.Ne` | `DISPLACE(-n)` | keep Ne fixed, sink Z/chips south, stretch north channels |
| `sfN.Se` | `DISPLACE(+n)` | move south bands south, stretch south channels |
| `sfN.Efi` | `DISPLACE(+n)` | move east fan/terminal/extra block east |
| `sfN.Wm` | `DISPLACE(+n)` | shift Z east while west chip cluster holds |
| `sfN.Wt` | `DISPLACE_VERTICAL(n)` | surgical Wt-only move; avoid for world alignment |

## Current World Harmonization Model

### North Relaxation Budget

North overlap pressure is not just the neighbor's `Ne`. It also includes the
neighbor's `Nt` and `Nfi` bands. Missing those two bands caused the observed
two-row count error.

Current doctrine:

```text
north_relaxation_span(zone) = Ne.span + Nt.span + Nfi.span
```

`Ne` and `Se` remain actual four-lane spans where the geometry says they are
four lanes. Do not resurrect the old ghost `Ne` span.

### Horizontal Alignment

World horizontal offset still uses seam terminal columns:

```text
wOffset[zone_0] = 0
wOffset[zone_i+1] = wOffset[zone_i] + (Za.Et_minCol - Zb.Wt_minCol)
```

This aligns Zb's Wt chip columns to Za's Et chip columns without transplanting
chip positions.

### Vertical Alignment

Vertical world-origin alignment is chip-row driven, not north-stack driven.

For a seam `(Za, Zb)`, derive Zb's row offset from shared seam chip terminals:

```text
rowOffset(Zb) = Za.Et_world_row - Zb.Wt_local_row
```

This is the hard constraint because the seam chip is the same physical chip in
the overlap model. North-ring accommodation then follows from geometry
relaxation; it is not the primary offset source.

## Current Evidence

Command:

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python -m signalflow \
  examples/simple-circuit/back-and-forth.yaml \
  --run-snippet snippets/algebraic/world_zone_inspect.py \
  -- --zones '1,2;1,3' --geometry
```

Default CLI:

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run signalflow \
  examples/simple-circuit/back-and-forth.yaml
```

Observed:

- `zones: (1,2) off=0  (1,3) off=64`
- Zone `1,2`:
  - `Et` rows `25..48`
  - `module/grandchild.ts` rows `25..48`
  - `Ne` rows `11..14`
- Zone `1,3`:
  - `Wt` rows `25..48`
  - `module/grandchild.ts` rows `25..48`
  - `Ne` rows `17..20`

This resolves the previous seam differential where `grandchild.ts` was
`23..46` on one side and `25..48` on the other.

## World Canvas Doctrine

- Each zone materializes at its natural local geometry.
- No seam chip override.
- No Wt position transplant.
- Horizontal alignment uses `wOffset`.
- Vertical alignment uses seam chip rows.
- `mergedCellMap_get()` returns keys as `(row, col)`.
- Canvas sizing must include region frames, effective boundaries, chip draw
  placements, and route cells.

## Port Doctrine

- `{signal: "x"}` is forward-only.
- `{signal: "x", return: "rx"}` declares a paired return lane.
- `return: ""` is invalid.
- Chip geometry rows and solver route endpoints come from declared terminals,
  not from `2 * portIndex` signal/return pairing.
- `examples/simple-circuit/neural-network.yaml` is the current regression
  fixture for forward-only fan-out.

## Primary Files

| File | Role |
| --- | --- |
| `src/signalflow/engine/world_render.py` | top-level world render assembly |
| `src/signalflow/__main__.py` | CLI flags for world render filters |
| `snippets/algebraic/world_zone_inspect.py` | parity/debug world inspect surface |
| `snippets/algebraic/world_zone_overlap_materialize.py` | older world materialization prototype |
| `src/signalflow/board/geometry/georules.py` | geometry displacement algebra |
| `src/signalflow/board/geometry/zones.py` | `BoardGeometry`, `GeometryZone` |
| `src/signalflow/board/materialized_runtime.py` | board solution materialization |
| `src/signalflow/board/render.py` | board canvas render |
| `src/signalflow/engine/inspect/zone_local.py` | per-zone overlap context builder |

## Document Precedence

1. `agentic/HANDOFF.md`
2. `agentic/CONTEXT.md`
3. `agentic/NON-NEGOTIABLES.md`
4. live snippet/test output
5. `agentic/PLAN.md`
