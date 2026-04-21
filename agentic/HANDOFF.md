# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.29`

## Current Baseline

138 symbolic tests passing. All canonical snippets green.

The intra routing substrate is fully operational end-to-end:
- geometry construction → symbolic solve → lane assignment → board materialization → rendered display
- Ni/Si centroid spread (relaxation) now works correctly: shifts Ni northward and Si southward
  until collision score is zero or the Nfi/Sfi hard boundary is reached
- Em/Wm medial longitude pillars exist as 2-column-wide gaps in the intra substrate
- extra ring geometry (We, Ee, Ne, Se, Wfe, Efe, Nfe, Sfe) fully defined in board geometry
- intra↔extra transfer regions (NWx, NEx, SWx, SEx) defined in sfN and geometry
- outer-ring path topologies defined in `notation/path.py`

## What Just Changed (This Session)

1. **Em/Wm gap reservation** (`_wteCoreRegionFrames_build`): opens 2-column gaps for the
   medial longitude pillars between Wfi↔Wi and Ei↔Efi. Tests updated for shifted coords.

2. **Centroid spread bug** (`regionFramesRelaxed_build`): `niFloor`/`siCeiling` guards
   were set to the current Ni/Si position — causing the loop to break on the first
   iteration without ever making progress. Removed the guards. `_regionFramesShifted_build`
   already enforces the real hard boundary (Ni may not overlap Nfi). Spread now runs until
   collision score = 0.

3. **Outer-ring realization landed** (`src/signalflow/board/realizer.py`):
   structured realization now routes through a shared factory/helper rather
   than one duplicated branch per path family. Intra, outer-arc, and same-side
   U-turn path families now materialize to non-empty world-coordinate routes.

4. **Outer-ring naming cleanup** (`src/signalflow/notation/path.py`):
   old semantic names were replaced with geometry-first names:
   `WTE_OUTER_EASTBOUND_ARC`, `WTE_OUTER_WESTBOUND_ARC`,
   `WTE_OUTER_EASTSIDE_UTURN`, `WTE_OUTER_WESTSIDE_UTURN`.

## What Exists In The Extra Ring

**Geometry** (fully realized in board builder):
- `We`, `Ee`, `Ne`, `Se` — extra ring longitudinal/latitudinal bands
- `Wfe`, `Efe`, `Nfe`, `Sfe` — extra ring fan regions
- `Em`, `Wm` — medial longitude pillars (same-side U-turn enablers)
- `NWe/NEe/SWe/SEe` — extra ring corner transitions
- `NWx/NEx/SWx/SEx` — intra↔extra transfer regions

**Path topologies** (`src/signalflow/notation/path.py`):
- `WTE_OUTER_EASTBOUND_ARC` — Wfe→We→Ne→Ee→Efe
- `WTE_OUTER_WESTBOUND_ARC` — Efe→Ee→Se→We→Wfe
- `WTE_OUTER_EASTSIDE_UTURN` — Efe→Ee→Ne→Em→Efi
- `WTE_OUTER_WESTSIDE_UTURN` — Wfi→Wm→Ne→We→Wfe

**Solver context** (`src/signalflow/routing/kernel_solver.py`):
- `WTE_EXTRA_CONTEXT` — uses INTER_ROUTING family, East source, South lat forward
- `NTS_EXTRA_CONTEXT` — defined but not yet exercised

**Backedge routing** (`src/signalflow/routing/zone_solver.py`):
- backedge obligations classified as `INTER_PERIMETER_BACKEDGE`
- routed via `WTE_EXTRA_CONTEXT`

## What Is NOT Yet Done: The Next Gap

The next short gap is not path realization. It is collision / occupancy
extension for outer-ring routes.

`_geometryPressureScore_calculate` and related safety checks still mostly think
in intra terms. Outer-ring routes can now realize, but their pressure and
occupancy doctrine needs the same explicit accounting.

## Next Concrete Target

Extend collision / occupancy logic to account for:

1. **`WTE_OUTER_EASTBOUND_ARC`** (`Wfe→We→Ne→Ee→Efe`)
2. **`WTE_OUTER_WESTBOUND_ARC`** (`Efe→Ee→Se→We→Wfe`)
3. **`WTE_OUTER_EASTSIDE_UTURN`** (`Efe→Ee→Ne→Em→Efi`)
4. **`WTE_OUTER_WESTSIDE_UTURN`** (`Wfi→Wm→Ne→We→Wfe`)

## Important Files

| File | Role |
|------|------|
| `src/signalflow/board/realizer.py` | Shared realization factory for intra + outer paths |
| `src/signalflow/notation/path.py` | Path topologies (`WTE_OUTER_*` family) |
| `src/signalflow/routing/kernel_solver.py` | `WTE_EXTRA_CONTEXT`, `WTE_INTRA_CONTEXT` |
| `src/signalflow/routing/zone_solver.py` | Backedge dispatch to `INTER_PERIMETER_BACKEDGE` |
| `src/signalflow/notation/sfn.py` | All sfN region tokens and keys |
| `src/signalflow/board/geometry/topology.py` | Board geometry construction |
| `tests_symbolic/test_symbolic_kernel_quarantine.py` | 138 tests — must stay green |

## Key Geometry Key Lookups

Region keys for extra ring (via `sfN.*.region_key`):

```
sfN.We  → "west/extra_routing_longitude"
sfN.Ee  → "east/extra_routing_longitude"
sfN.Ne  → "north/extra_routing_latitude"
sfN.Se  → "south/extra_routing_latitude"
sfN.Wfe → "west/extra_routing_fan_in_out"
sfN.Efe → "east/extra_routing_fan_in_out"
sfN.Nfe → "north/extra_routing_fan_in_out"
sfN.Sfe → "south/extra_routing_fan_in_out"
sfN.Em  → "east/medial_routing_longitude"
sfN.Wm  → "west/medial_routing_longitude"
```

## Verification Baseline

Before and after any change:

```
uv run pytest tests_symbolic/ -q          # must be 138 passed
```

Snippet surface (must stay green):
- `snippets/algebraic/zone_geometry.py -- --zone 1,1`
- `snippets/algebraic/hub_kernel_solver.py -- --zone 1,1`
- `snippets/algebraic/hub_internal_wiring.py`
- `snippets/algebraic/hub_internal_geometry.py`

## Non-Negotiables

Read `agentic/NON-NEGOTIABLES.md` before any routing change. Key:
- No shared route cells
- `laneMap_get()` for REVERSE hops uses channel capacity, not bundle size
- `WiringSolution` instances are per-solve, not singletons
- No closed information loops (no struct→string→re-parse)
- Naming convention: `<camelCaseNoun>_<verb>()` strictly

## What Not To Do

- Do not restart symbolic topology / interpreter work (that plan is in PLAN.md,
  still valid as a longer-term arc, but outer-route occupancy work is the
  immediate short follow-on)
- Do not invent a separate solver species for extra ring routes
- Do not add ad hoc geometry patches before naming the doctrinal issue
- Do not add route cells to existing lane indices already owned by intra routes
