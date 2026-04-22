# Zero-Shot Handoff: `worldscale-extra-routing`

**Branch:** `worldscale-extra-routing`
**Version:** `5.9.32`

## Current Truth In One Screen

- 145 symbolic tests passing
- Intra routing: fully end-to-end (geometry → solve → materialize → render)
- Centroid spread (Ni/Si relaxation): fixed and working
- Em/Wm medial pillars: 2-col gaps reserved in intra substrate
- Extra ring geometry (We/Ee/Ne/Se/Wfe/Efe/Em/Wm and transitions): fully built
- Outer-ring path topologies (`WTE_OUTER_EASTBOUND_ARC`,
  `WTE_OUTER_WESTBOUND_ARC`, `WTE_OUTER_EASTSIDE_UTURN`,
  `WTE_OUTER_WESTSIDE_UTURN`): defined and realized
- **Gap**: add fuller real-fixture reverse-route coverage and align formal collision reporting with the stricter merged-cell metric now used by centroid spread

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
- `src/signalflow/routing/obligations.py`   ← `CallingStack`-driven route direction
- `src/signalflow/board/solver.py`          ← final topology selection

## Verification Surface

```bash
uv run pytest tests_symbolic/ -q   # 145 passed
```

## First Action For A New Agent

```bash
uv run pytest tests_symbolic/ -q
```

Then read `agentic/HANDOFF.md` — do not touch code before reading it.
