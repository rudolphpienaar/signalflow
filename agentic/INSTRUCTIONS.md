# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `agentic/ZEROSHOT.md`

Current branch: `worldscale-extra-routing`. Current version: `5.9.33`.

## Immediate Focus

The intra and outer routing realization paths are now landed. The next short gap is broader full-world fixture coverage for reverse routes and cleanup of the remaining mismatch between formal collision reporting and the stricter merged-cell metric now used by centroid spread.

## What To Do

Inspect and extend collision / occupancy paths after realization:

- `_geometryPressureScore_calculate(...)`
- any occupancy/collision helpers that assume only `Ni/Si`
- rendered/materialized safety checks for outer-ring routes

The four path families already realized are:

1. **`Wfe` first, `Efe` last** → outer eastbound arc (`WTE_OUTER_EASTBOUND_ARC`)
   Path: `Wfe → We → Ne → Ee → Efe`

2. **`Efe` first, `Wfe` last** → outer westbound arc (`WTE_OUTER_WESTBOUND_ARC`)
   Path: `Efe → Ee → Se → We → Wfe`

3. **`Efe` first, `Efi` last** → east-side U-turn (`WTE_OUTER_EASTSIDE_UTURN`)
   Path: `Efe → Ee → Ne → Em → Efi`

4. **`Wfi` first, `Wfe` last** → west-side U-turn (`WTE_OUTER_WESTSIDE_UTURN`)
   Path: `Wfi → Wm → Ne → We → Wfe`

Use `sfN.*.region_key` to resolve geometry frame names where geometry lookup is
needed — never hardcode key strings.

## Before You Start

1. Run baseline:
   ```
   uv run pytest tests_symbolic/ -q
   ```
   Must show `145 passed`.

2. Read the path topology definitions in `src/signalflow/notation/path.py`
   (lines ~472–537).

3. Read the shared realization factory in `realizer.py` so follow-on work stays aligned with the current structured-path dispatch.

## Verification After Change

```bash
uv run pytest tests_symbolic/ -q
```

Add or extend tests in `tests_symbolic/test_symbolic_kernel_quarantine.py` so
outer-ring paths participate in occupancy / collision coverage as well as
materialization coverage.

## First Action

```bash
uv run pytest tests_symbolic/ -q
```

Then read `agentic/HANDOFF.md` for full context.

## Primary Files For This Phase

- `src/signalflow/board/realizer.py`           ← current realization seam
- `src/signalflow/notation/path.py`            ← path topologies
- `src/signalflow/notation/sfn.py`             ← region key lookups
- `src/signalflow/routing/obligations.py`      ← `CallingStack`-driven obligation direction
- `src/signalflow/board/solver.py`             ← final topology selection from concrete wire direction
- `tests_symbolic/test_symbolic_kernel_quarantine.py` ← test suite

## Things Not To Do

- Do not restart the symbolic topology / interpreter plan (PLAN.md); that is
  valid long-term work but outer-route occupancy work comes first
- Do not invent a separate solver for reverse routing
- Do not hardcode geometry key strings — use `sfN.*.region_key`
- Do not share lane indices with existing intra routes
- Do not break any of the 145 passing tests
