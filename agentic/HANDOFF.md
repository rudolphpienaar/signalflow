# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.27`

## Current Baseline

137 symbolic tests passing. All canonical snippets green.

The intra routing substrate is fully operational end-to-end:
- geometry construction → symbolic solve → lane assignment → board materialization → rendered display
- Ni/Si centroid spread (relaxation) now works correctly: shifts Ni northward and Si southward
  until collision score is zero or the Nfi/Sfi hard boundary is reached
- Em/Wm medial longitude pillars exist as 2-column-wide gaps in the intra substrate
- extra ring geometry (We, Ee, Ne, Se, Wfe, Efe, Nfe, Sfe) fully defined in board geometry
- intra↔extra transfer regions (NWx, NEx, SWx, SEx) defined in sfN and geometry
- path topologies for extra ring defined in `notation/path.py`

## What Just Changed (This Session)

Two bugs fixed and verified:

1. **Em/Wm gap reservation** (`_wteCoreRegionFrames_build`): opens 2-column gaps for the
   medial longitude pillars between Wfi↔Wi and Ei↔Efi. Tests updated for shifted coords.

2. **Centroid spread bug** (`regionFramesRelaxed_build`): `niFloor`/`siCeiling` guards
   were set to the current Ni/Si position — causing the loop to break on the first
   iteration without ever making progress. Removed the guards. `_regionFramesShifted_build`
   already enforces the real hard boundary (Ni may not overlap Nfi). Spread now runs until
   collision score = 0.

## What Exists In The Extra Ring

**Geometry** (fully realized in board builder):
- `We`, `Ee`, `Ne`, `Se` — extra ring longitudinal/latitudinal bands
- `Wfe`, `Efe`, `Nfe`, `Sfe` — extra ring fan regions
- `Em`, `Wm` — medial longitude pillars (same-side U-turn enablers)
- `NWe/NEe/SWe/SEe` — extra ring corner transitions
- `NWx/NEx/SWx/SEx` — intra↔extra transfer regions

**Path topologies** (`src/signalflow/notation/path.py`):
- `WTE_EXTRA_TOPARENT` — child→parent via outer ring: Wfe→We→Ne→Ee→Efe
- `WTE_EXTRA_FROMPARENT` — parent→child return: Efe→Ee→Se→We→Wfe
- `WTE_MEDIAL_EAST_FORWARD` — Et→Et same-side U-turn: Efe→Ee→Ne→Em→Efi
- `WTE_MEDIAL_WEST_FORWARD` — Wt→Wt same-side U-turn: Wfi→Wm→Ne→We→Wfe

**Solver context** (`src/signalflow/routing/kernel_solver.py`):
- `WTE_EXTRA_CONTEXT` — uses INTER_ROUTING family, East source, South lat forward
- `NTS_EXTRA_CONTEXT` — defined but not yet exercised

**Backedge routing** (`src/signalflow/routing/zone_solver.py`):
- backedge obligations classified as `INTER_PERIMETER_BACKEDGE`
- routed via `WTE_EXTRA_CONTEXT`

## What Is NOT Yet Done: The Missing Piece

**`src/signalflow/board/realizer.py` does not handle extra ring paths.**

`algebraicRouteRealization_buildFromPath` hardcodes two patterns:
- `isForward = firstHop.area is sfN.Wfi and lastHop.area is sfN.Efi` (WTE_INTRA_FORWARD)
- `isReturn = firstHop.area is sfN.Efi and lastHop.area is sfN.Wfi` (WTE_INTRA_RETURN)

All other path shapes — including WTE_EXTRA_TOPARENT, WTE_EXTRA_FROMPARENT, and the
medial paths — fall through to empty `AlgebraicRouteRealization` with no points.

This is the entire remaining gap for reverse/recursive wiring.

## Next Concrete Target

Extend `algebraicRouteRealization_buildFromPath` to recognize and realize extra ring paths:

1. **WTE_EXTRA_TOPARENT** (`Wfe→We→Ne→Ee→Efe`): structurally mirrors WTE_INTRA_FORWARD
   but uses `Wfe`/`We`/`Ne`/`Ee`/`Efe` frames. Attach-point geometry differs: fan frames
   are at the outer board edge, not adjacent to chip terminals.

2. **WTE_EXTRA_FROMPARENT** (`Efe→Ee→Se→We→Wfe`): mirrors WTE_INTRA_RETURN on the outer ring.

3. **WTE_MEDIAL_EAST_FORWARD** (`Efe→Ee→Ne→Em→Efi`): uses Em frame for the longitude column.
   This is the East-side U-turn path.

4. **WTE_MEDIAL_WEST_FORWARD** (`Wfi→Wm→Ne→We→Wfe`): uses Wm frame for the longitude column.

The approach: in `algebraicRouteRealization_buildFromPath`, detect the first/last hop area
and dispatch to a family-appropriate realization branch. Keep geometry lookup symmetric
with the intra branch already there.

## Important Files

| File | Role |
|------|------|
| `src/signalflow/board/realizer.py` | **Primary target** — add extra ring realization |
| `src/signalflow/notation/path.py` | Path topologies (WTE_EXTRA_*, WTE_MEDIAL_*) |
| `src/signalflow/routing/kernel_solver.py` | WTE_EXTRA_CONTEXT, WTE_INTRA_CONTEXT |
| `src/signalflow/routing/zone_solver.py` | Backedge dispatch to INTER_PERIMETER_BACKEDGE |
| `src/signalflow/notation/sfn.py` | All sfN region tokens and keys |
| `src/signalflow/board/geometry/topology.py` | Board geometry construction |
| `tests_symbolic/test_symbolic_kernel_quarantine.py` | 137 tests — must stay green |

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
uv run pytest tests_symbolic/ -q          # must be 137 passed
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

- Do not restart symbolic topology / interpreter work (that plan is in PLAN.md, still valid
  as a longer-term arc, but reverse wiring is the immediate unblocking item)
- Do not invent a separate solver species for extra ring routes
- Do not add ad hoc geometry patches before naming the doctrinal issue
- Do not add route cells to existing lane indices already owned by intra routes
