# Project Context: `worldscale-extra-routing`

This file is the current architectural baseline for routing work on this branch.

## Current Architectural State

- Branch: `worldscale-extra-routing`
- Version: `5.9.30`
- Test baseline: 145 symbolic tests passing

## What Is Stable Now

- Board-owned geometry is the active geometry center
- `GeometryZone` is canonical
- Board geometry consolidated under `src/signalflow/board/geometry/`
- Intra routing fully end-to-end: geometry → symbolic solve → lane assignment → materialize → render
- Centroid spread (Ni/Si relaxation) works: shifts bands as a paired move until realized merged-cell congestion is cleared or hard bounds are reached
- Em/Wm medial longitude pillars: 2-col gaps reserved in intra substrate
- Extra ring geometry (We, Ee, Ne, Se, Wfe, Efe, Nfe, Sfe, Em, Wm, transfers) fully built
- Outer-ring path topologies defined in `notation/path.py`
- `CallingStack`-driven route direction classification exists in `routing/obligations.py`
- final concrete topology selection exists in `board/solver.py`
- Symbolic geometry expression layer, coupling doctrine, georule system: stable

## Current Gap

Outer-ring path realization is landed. The next gap is broader end-to-end reverse-route fixture coverage and cleanup of the mismatch between formal collision reporting and the stricter merged-cell metric already used by centroid spread.

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
The next short arc is broader reverse-routing fixture coverage and reporting cleanup before symbolic-topology work resumes.

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
uv run pytest tests_symbolic/ -q   # 145 passed
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
