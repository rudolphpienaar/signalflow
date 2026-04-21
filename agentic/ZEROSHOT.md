# Zero-Shot Handoff: `worldscale-extra-routing`

**Branch:** `worldscale-extra-routing`
**Version:** `5.9.29`

## Current Truth In One Screen

- 138 symbolic tests passing
- Intra routing: fully end-to-end (geometry → solve → materialize → render)
- Centroid spread (Ni/Si relaxation): fixed and working
- Em/Wm medial pillars: 2-col gaps reserved in intra substrate
- Extra ring geometry (We/Ee/Ne/Se/Wfe/Efe/Em/Wm and transitions): fully built
- Outer-ring path topologies (`WTE_OUTER_EASTBOUND_ARC`,
  `WTE_OUTER_WESTBOUND_ARC`, `WTE_OUTER_EASTSIDE_UTURN`,
  `WTE_OUTER_WESTSIDE_UTURN`): defined and realized
- **Gap**: collision / occupancy extension for outer-ring routes still needs work

## Actual Next Target

Extend collision / occupancy doctrine so outer-ring routes participate in
pressure and safety checks the same way intra routes do.

Four cases:
1. `Wfe`→`Efe` — outer eastbound arc (`WTE_OUTER_EASTBOUND_ARC`)
2. `Efe`→`Wfe` — outer westbound arc (`WTE_OUTER_WESTBOUND_ARC`)
3. `Efe`→`Efi` — east-side U-turn (`WTE_OUTER_EASTSIDE_UTURN`)
4. `Wfi`→`Wfe` — west-side U-turn (`WTE_OUTER_WESTSIDE_UTURN`)

## Most Important Files

- `src/signalflow/board/realizer.py`        ← current shared realization factory
- `src/signalflow/notation/path.py`         ← path topologies (lines ~472–537)
- `src/signalflow/notation/sfn.py`          ← region keys (`.region_key` property)
- `src/signalflow/routing/kernel_solver.py` ← `WTE_EXTRA_CONTEXT`

## Verification Surface

```bash
uv run pytest tests_symbolic/ -q   # 138 passed
```

## First Action For A New Agent

```bash
uv run pytest tests_symbolic/ -q
```

Then read `agentic/HANDOFF.md` — do not touch code before reading it.
