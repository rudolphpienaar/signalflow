# Zero-Shot Handoff: `worldscale-extra-routing`

**Branch:** `worldscale-extra-routing`
**Version:** `5.9.27`

## Current Truth In One Screen

- 137 symbolic tests passing
- Intra routing: fully end-to-end (geometry → solve → materialize → render)
- Centroid spread (Ni/Si relaxation): fixed and working
- Em/Wm medial pillars: 2-col gaps reserved in intra substrate
- Extra ring geometry (We/Ee/Ne/Se/Wfe/Efe/Em/Wm and transitions): fully built
- Extra ring path topologies (WTE_EXTRA_TOPARENT/FROMPARENT, WTE_MEDIAL_EAST/WEST): defined
- **Gap**: `realizer.py` does not yet realize extra ring paths — they fall through to empty

## Actual Next Target

Extend `algebraicRouteRealization_buildFromPath` in `src/signalflow/board/realizer.py`
to dispatch on extra ring first/last hops and produce correct world-coordinate routes.

Four cases:
1. `Wfe`→`Efe` — extra forward (WTE_EXTRA_TOPARENT)
2. `Efe`→`Wfe` — extra return (WTE_EXTRA_FROMPARENT)
3. `Efe`→`Efi` — east medial U-turn (WTE_MEDIAL_EAST_FORWARD)
4. `Wfi`→`Wfe` — west medial U-turn (WTE_MEDIAL_WEST_FORWARD)

## Most Important Files

- `src/signalflow/board/realizer.py`        ← extend realization dispatch
- `src/signalflow/notation/path.py`         ← path topologies (lines ~472–537)
- `src/signalflow/notation/sfn.py`          ← region keys (`.region_key` property)
- `src/signalflow/routing/kernel_solver.py` ← WTE_EXTRA_CONTEXT

## Verification Surface

```bash
uv run pytest tests_symbolic/ -q   # 137 passed
```

## First Action For A New Agent

```bash
uv run pytest tests_symbolic/ -q
```

Then read `agentic/HANDOFF.md` — do not touch code before reading it.
