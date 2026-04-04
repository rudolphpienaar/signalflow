# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `docs/worldscale_geometry.adoc`
4. `papers/new_ways.adoc`

Current branch is `worldscale-extra-routing`. Current version is `5.9.16`.

## What Changed Last Arc

Geometry centralization — single source of truth for all zone spans:

- `config/board_defaults.py`: `BoardGeometryConfig` singleton, loaded from XDG
  user config + project `.signalflow.yaml` at CLI startup
- `board/doctrine.py`: `RingGeometrySpec` + `BoardGeometrySpec` + `with_invariants()`
- `board/invariants.py`: `ZoneSymbolicInvariants` — circuit-derived and
  placement-lifted per-zone geometry constraints
- `routing/placement.py`: all intra fan and terminal width floors now read from
  `boardGeometryConfig` at call time; module-level constants removed
- `snippets/algebraic/zone_invariants.py`: demonstrates full pipeline

Run this to see the current state:

```
uv run python -m signalflow examples/hub.yaml \
    --run-snippet snippets/algebraic/zone_invariants.py -- --zone 1,1
```

## Immediate Task

Phase 3: Symbolic algebra across `intra` and `extra`.

The geometry and transfer regions are established. The unresolved question is
how routes are described symbolically when they leave `intra`, travel `extra`,
and re-enter — and whether row/layer identity can survive that transition.

Start here:

1. Read `docs/worldscale_geometry.adoc` for the current geometry doctrine.
2. Read `algebraic/DOCTRINE.md` for the canonical naming scheme.
3. Sketch one concrete route narrative that crosses the `intra ↔ extra`
   boundary — use zone (1,1) from `zone_invariants.py` output as the
   geometric anchor.
4. Identify where `sfN` algebra must be extended to express cross-ring
   paths.

Do not start builder or solver code until the route narrative is explicit.

## Hard Problem Still Unresolved

Child-to-self routing. A route leaving `p4()` into `extra` must preserve
enough row/layer identity to return specifically to `p4()`, not to the
parent-facing side of the zone. Do not hand-wave this.

## Things Not To Do

- do not revive stale `rearch-zone-grid` milestone assumptions
- do not treat seams/interconnects as the settled next step
- do not overclaim geometry is placement-derived unless you can show the builder path
- do not use broad LLM rewrites — surgical changes only
- do not start new routing algebra before the route narrative is documented
