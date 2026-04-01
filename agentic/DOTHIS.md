# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `docs/worldscale_geometry.adoc`
4. `papers/new_ways.adoc`

Current branch is `worldscale-extra-routing`. Current version is `5.9.11`.

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

## Immediate Task (Phase 3 — Transfer Regions)

The `extra` perimeter frames exist but are not connected to `intra`. The next
step is to define the transfer regions at each `intra ↔ extra` interface
corner. Read `docs/worldscale_geometry.adoc` sections "Transfer Regions" and
"Open Questions" before starting.

Key decisions still open:
- Are transfer regions a new `RegionFamily` or an ownership rule on existing
  transition regions?
- Corner ownership: longitude families currently own the corners (they span
  the full outer height). Is that the right convention?

Express route class `sf1` (child to parent) geometrically first. That means
one concrete transfer path from `eLong` outward to `xnLat`.

## Things Not To Do

- do not revive stale `rearch-zone-grid` milestone assumptions
- do not treat seams/interconnects as the settled next step
- do not overclaim geometry is placement-derived unless you can show the builder path
- do not treat the REPL as a toy debug layer
- do not start `BoardGeometrySpec` implementation until transfer regions are settled

## Current Design Pressure

The hard unresolved problem is not ordinary child-to-parent reverse routing.
It is child-to-self routing while preserving enough local row/layer identity
across the outer perimeter.
