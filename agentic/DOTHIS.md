# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `agentic/ZEROSHOT.md`

Current branch: `worldscale-extra-routing`. Current version: `5.9.27`.

## Immediate Focus

The intra routing path is fully end-to-end. The extra ring geometry exists.
The missing step is **realizing extra ring paths** in `realizer.py`.

## What To Do

Extend `algebraicRouteRealization_buildFromPath` in:

```
src/signalflow/board/realizer.py
```

Currently it recognizes two patterns:
- `Wfi` first, `Efi` last → intra forward
- `Efi` first, `Wfi` last → intra return

You must add recognition for:

1. **`Wfe` first, `Efe` last** → extra ring forward (WTE_EXTRA_TOPARENT)
   Path: `Wfe → We → Ne → Ee → Efe`
   Geometry keys: `sfN.Wfe/We/Ne/Ee/Efe` via `.region_key`

2. **`Efe` first, `Wfe` last** → extra ring return (WTE_EXTRA_FROMPARENT)
   Path: `Efe → Ee → Se → We → Wfe`

3. **`Efe` first, `Efi` last** → east medial U-turn (WTE_MEDIAL_EAST_FORWARD)
   Path: `Efe → Ee → Ne → Em → Efi`

4. **`Wfi` first, `Wfe` last** → west medial U-turn (WTE_MEDIAL_WEST_FORWARD)
   Path: `Wfi → Wm → Ne → We → Wfe`

Use `sfN.*.region_key` to resolve geometry frame names — never hardcode key strings.

## Before You Start

1. Run baseline:
   ```
   uv run pytest tests_symbolic/ -q
   ```
   Must show `137 passed`.

2. Read the path topology definitions in `src/signalflow/notation/path.py` (lines ~472–537).

3. Read `algebraicRouteRealization_buildFromPath` (lines ~238–378 in `realizer.py`) —
   understand the intra dispatch pattern before extending it.

## Verification After Change

```
uv run pytest tests_symbolic/ -q
```

Add a test in `tests_symbolic/test_symbolic_kernel_quarantine.py` for at least one
extra ring path materialization — it should produce non-empty `routePoints`.

## First Action

```bash
uv run pytest tests_symbolic/ -q
```

Then read `agentic/HANDOFF.md` for full context.

## Primary Files For This Phase

- `src/signalflow/board/realizer.py`           ← primary target
- `src/signalflow/notation/path.py`            ← path topologies
- `src/signalflow/notation/sfn.py`             ← region key lookups
- `src/signalflow/routing/kernel_solver.py`    ← WTE_EXTRA_CONTEXT definition
- `tests_symbolic/test_symbolic_kernel_quarantine.py` ← test suite

## Things Not To Do

- Do not restart the symbolic topology / interpreter plan (PLAN.md); that is valid
  long-term work but reverse wiring must come first
- Do not invent a separate solver for reverse routing
- Do not hardcode geometry key strings — use `sfN.*.region_key`
- Do not share lane indices with existing intra routes
- Do not break any of the 137 passing tests
