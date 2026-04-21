# Project Context: `worldscale-extra-routing`

This file is the current architectural baseline for routing work on this branch.

## Current Architectural State

- Branch: `worldscale-extra-routing`
- Version: `5.9.29`
- Test baseline: 138 symbolic tests passing

## What Is Stable Now

- Board-owned geometry is the active geometry center
- `GeometryZone` is canonical
- Board geometry consolidated under `src/signalflow/board/geometry/`
- Intra routing fully end-to-end: geometry → symbolic solve → lane assignment → materialize → render
- Centroid spread (Ni/Si relaxation) works: shifts bands until collision score = 0
- Em/Wm medial longitude pillars: 2-col gaps reserved in intra substrate
- Extra ring geometry (We, Ee, Ne, Se, Wfe, Efe, Nfe, Sfe, Em, Wm, transfers) fully built
- Outer-ring path topologies defined in `notation/path.py`
- Backedge (INTER_PERIMETER) routing dispatch exists in `zone_solver.py`
- Symbolic geometry expression layer, coupling doctrine, georule system: stable

## Current Gap

Outer-ring path realization is now landed. The next gap is that collision and
occupancy logic still mostly reasons in intra terms.

That means reverse and recursive routes can now materialize, but the follow-on
physics work is to account for `We/Ee/Ne/Se` and medial pillars in pressure,
occupancy, and rendered safety checks.

## Next Immediate Task

Extend collision / occupancy accounting to handle:

1. Outer eastbound arc: `Wfe → We → Ne → Ee → Efe`
2. Outer westbound arc: `Efe → Ee → Se → We → Wfe`
3. East-side U-turn:    `Efe → Ee → Ne → Em → Efi`
4. West-side U-turn:    `Wfi → Wm → Ne → We → Wfe`

## Geometry Stack (Intended)

1. symbolic topology schema
2. coupling / constraint doctrine
3. local interpreter
4. concrete metric realization

The symbolic topology / interpreter arc (PLAN.md) remains valid long-term.
But the immediate blocking item is no longer outer-ring realization.
The next short arc is collision / occupancy extension before broader reverse
wiring demos.

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
uv run pytest tests_symbolic/ -q   # 138 passed
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
