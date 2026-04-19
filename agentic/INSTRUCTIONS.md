Read `agentic/ZEROSHOT.md`, `agentic/HANDOFF.md`, `agentic/NON-NEGOTIABLES.md`
in that order. Then run:

```bash
uv run pytest tests_symbolic/ -q
```

Confirm 137 passed before touching any file.

Then read these docs for context:

- `docs/wiringSolutions.adoc`
- `docs/worldscale_geometry.adoc`
- `docs/board.adoc`

Then inspect the realization path:

- `src/signalflow/board/realizer.py`       ← primary target
- `src/signalflow/notation/path.py`        ← path topology definitions
- `src/signalflow/notation/sfn.py`         ← region key lookups
- `src/signalflow/routing/kernel_solver.py` ← routing context definitions

The immediate job is:

- extend `algebraicRouteRealization_buildFromPath` to handle extra ring paths
- four new dispatch cases (extra forward, extra return, east medial, west medial)
- verify no intra tests regress

The first concrete scoped case is:

- add extra forward path realization (`Wfe → We → Ne → Ee → Efe`)
- verify `routePoints` are non-empty for that path shape
- then add extra return, east medial, west medial

Do not start symbolic topology / interpreter work (PLAN.md arc) before
extra ring realization is demonstrated end-to-end.

Use these truth surfaces throughout:

- `uv run pytest tests_symbolic/ -q`
- `snippets/algebraic/zone_geometry.py -- --zone 1,1`
- `snippets/algebraic/hub_internal_geometry.py`
