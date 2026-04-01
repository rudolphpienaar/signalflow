# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `docs/worldscale_geometry.adoc`
4. `papers/new_ways.adoc`

Current branch is `worldscale-extra-routing`. Current version is `5.9.12`.

## What Changed Last Arc

Phases 2a, 2b, and 2c are complete:

- `docs/worldscale_geometry.adoc`: verified frame table, `extra` position
  formulas, board expansion doctrine, `BoardGeometrySpec` design section,
  Unicode figures throughout
- `src/signalflow/board/types.py`: `EXTRA_LONGITUDE`, `EXTRA_LATITUDE` added
- `src/signalflow/board/render.py`: glyphs for extra families
- `src/signalflow/board/builders.py`: `_extraGeometry_build` places all four
  extra frames; called from `board_buildFromKernel`

Run this to see the current state:

```
uv run python -m signalflow examples/hub.yaml --run-snippet snippets/algebraic/zone_1_1_geometry.py
```

## Immediate Task (Phase 4 — sf1 Route Geometry)

Transfer regions are placed and verified. The geometry now has:
- `extra` perimeter (`xwLong`, `xeLong`, `xnLat`, `xsLat`)
- Four `intra_extra_transfer` corners (`╔ ╗ ╚ ╝`)

Next step: express route class `sf1` (child to parent) as a concrete
geometric path through the substrate. This means:

1. Trace the sf1 path through existing region frames:
   `eFan → eLong:upper → xfer:NE → xnLat → xwLong → xfer:NW → wFan → wChipTerminal`
2. Verify no cells that the path requires are unowned or blocked
3. Identify what solver/realizer changes are needed to express this route

Run the snippet first and inspect the region frames to confirm path
continuity before touching solver code.

## Things Not To Do

- do not revive stale `rearch-zone-grid` milestone assumptions
- do not treat seams/interconnects as the settled next step
- do not overclaim geometry is placement-derived unless you can show the builder path
- do not treat the REPL as a toy debug layer
- do not start `BoardGeometrySpec` implementation — geometry substrate is the priority

## Current Design Pressure

The hard unresolved problem is not ordinary child-to-parent reverse routing.
It is child-to-self routing while preserving enough local row/layer identity
across the outer perimeter.
