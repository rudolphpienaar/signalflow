Read `agentic/ZEROSHOT.md`, `agentic/HANDOFF.md`, `agentic/NON-NEGOTIABLES.md`
in that order. Then run:

```bash
uv run pytest tests_symbolic/ -q
```

Confirm 138 passed before touching any file.

Then read these docs for context:

- `docs/wiringSolutions.adoc`
- `docs/worldscale_geometry.adoc`
- `docs/board.adoc`

Then inspect the current occupancy / realization path:

- `src/signalflow/board/realizer.py`       ← current realization seam
- `src/signalflow/notation/path.py`        ← path topology definitions
- `src/signalflow/notation/sfn.py`         ← region key lookups
- `src/signalflow/routing/kernel_solver.py` ← routing context definitions

The immediate job is:

- extend collision / occupancy doctrine for outer-ring routes
- ensure outer arcs and same-side U-turns participate in pressure accounting
- verify no intra tests regress

The first concrete scoped case is:

- add explicit outer-route pressure / occupancy coverage
- verify realized outer-ring routes remain non-empty and non-overlapping
- then broaden to rendered reverse-routing demos

Do not start symbolic topology / interpreter work (PLAN.md arc) before
outer-route occupancy work is stable.

Use these truth surfaces throughout:

- `uv run pytest tests_symbolic/ -q`
- `snippets/algebraic/zone_geometry.py -- --zone 1,1`
- `snippets/algebraic/hub_internal_geometry.py`
