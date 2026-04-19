# Project Context: `worldscale-extra-routing`

This file is the current architectural baseline for routing work on this branch.

## Current Architectural State

- Branch: `worldscale-extra-routing`
- Version: `5.9.27`
- Test baseline: 137 symbolic tests passing

## What Is Stable Now

- Board-owned geometry is the active geometry center
- `GeometryZone` is canonical
- Board geometry consolidated under `src/signalflow/board/geometry/`
- Intra routing fully end-to-end: geometry → symbolic solve → lane assignment → materialize → render
- Centroid spread (Ni/Si relaxation) works: shifts bands until collision score = 0
- Em/Wm medial longitude pillars: 2-col gaps reserved in intra substrate
- Extra ring geometry (We, Ee, Ne, Se, Wfe, Efe, Nfe, Sfe, Em, Wm, transfers) fully built
- Extra ring path topologies defined in `notation/path.py`
- Backedge (INTER_PERIMETER) routing dispatch exists in `zone_solver.py`
- Symbolic geometry expression layer, coupling doctrine, georule system: stable

## Current Gap

`src/signalflow/board/realizer.py` (`algebraicRouteRealization_buildFromPath`) only
handles two path shapes:

- intra forward: `Wfi → Wi → Ni → Ei → Efi`
- intra return:  `Efi → Ei → Si → Wi → Wfi`

All extra ring path shapes fall through to empty realization. This is the missing
piece for reverse and recursive wiring.

## Next Immediate Task

Extend `algebraicRouteRealization_buildFromPath` to handle:

1. Extra forward: `Wfe → We → Ne → Ee → Efe`
2. Extra return:  `Efe → Ee → Se → We → Wfe`
3. East medial:   `Efe → Ee → Ne → Em → Efi`
4. West medial:   `Wfi → Wm → Ne → We → Wfe`

## Geometry Stack (Intended)

1. symbolic topology schema
2. coupling / constraint doctrine
3. local interpreter
4. concrete metric realization

The symbolic topology / interpreter arc (PLAN.md) remains valid long-term.
But the immediate blocking item is extra ring realization — it must land before
recursive wiring can be demonstrated end-to-end.

## What Is In Place

- `src/signalflow/board/geometry/zones.py` — `GeometryZone`, `BoardGeometry`
- `src/signalflow/board/geometry/symbolic.py` — symbolic operands and expressions
- `src/signalflow/board/geometry/expr.py` — normalized symbolic forms
- `src/signalflow/board/geometry/doctrine.py` — overlap expression banks
- `src/signalflow/board/geometry/coupling.py` — coupling operators and families
- `src/signalflow/board/geometry/topology.py` — board geometry construction
- `src/signalflow/notation/sfn.py` — canonical region tokens (`region_key` property)
- `src/signalflow/notation/path.py` — path topologies for all four routing families

## Verification Baseline

```bash
uv run pytest tests_symbolic/ -q   # 137 passed
```

Canonical snippet surface must remain green:
- `snippets/algebraic/zone_geometry.py -- --zone 1,1`
- `snippets/algebraic/hub_kernel_solver.py -- --zone 1,1`
- `snippets/algebraic/hub_internal_wiring.py`
- `snippets/algebraic/hub_internal_geometry.py`

## Document Precedence

When files disagree:

1. `agentic/HANDOFF.md`
2. `agentic/DOTHIS.md`
3. `agentic/NON-NEGOTIABLES.md`
4. runtime/snippet evidence
5. `agentic/PLAN.md`
