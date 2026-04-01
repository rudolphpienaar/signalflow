# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `docs/worldscale_geometry.adoc`
4. `papers/new_ways.adoc`

Current branch is `worldscale-extra-routing`. Current version is `5.9.13`.

## What Changed Last Arc

Phases 2a, 2b, 2c, and Phase 4 sf1 verification are complete:

- `docs/worldscale_geometry.adoc`: sf1 path verification section added
  (both bypass and full variants; full adjacency table)
- `src/signalflow/board/types.py`: `RegionBranch.EAST` / `WEST` added
- `src/signalflow/board/render.py`: `╠` and `╣` glyph entries added
- `src/signalflow/board/builders.py`: `╠` re-entry transfer at col 13..19,
  row 5..44 in `_extraGeometry_build`

Run this to see the current state:

```
uv run python -m signalflow examples/hub.yaml --run-snippet snippets/algebraic/zone_1_1_geometry.py
```

## Immediate Task (sf2 — Child To Self Route Geometry)

sf1 path geometry is verified. Next: express route class `sf2`
(child to self) as a concrete geometric path.

The hard part of sf2 is row/layer identity preservation. The route must
distinguish `p4` from its neighbours after returning via `extra`. Open
question: is the existing transfer geometry sufficient, or does xeLong need
a re-entry transfer to the east chip terminal face?

Note: `xeLong` starts at col 105. The east chip terminal ends at col 97.
There is a module right-pad gap (col 98..104) between them. Unlike the west
side (where xwLong directly abuts wChipTerminal at col 19), the east side
has no direct adjacency. This asymmetry is the design pressure for sf2.

1. Determine whether a `east/intra_extra_transfer:west` (╣) is needed
2. If so, place it and document the frame position
3. Trace the full sf2 path and verify adjacency

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
