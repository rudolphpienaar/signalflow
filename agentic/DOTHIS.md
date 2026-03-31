# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `docs/worldscale_geometry.adoc`
4. `papers/new_ways.adoc`

Current branch is `worldscale-extra-routing`. Current version is `5.9.10`.

## What Changed Last Arc

Board geometry is now flush. Module bounding box edges are the natural attach
points for `extra` channels. See `agentic/HANDOFF.md` for full details.

## Immediate Task

Do not jump straight into solver code.

Run the zone geometry truth surface first:

```
python -m signalflow examples/hub.yaml --run-snippet snippets/algebraic/zone_1_1_geometry.py
```

Use that output as the concrete anchor for sketching where `xwLong`, `xnLat`,
`xeLong`, `xsLat` would live relative to existing region frames.

Then extend `docs/worldscale_geometry.adoc` with an explicit geometry figure
showing `extra` frame positions before touching any builder code.

## What To Produce First

A concrete extension to `docs/worldscale_geometry.adoc` with:

- exact row/column positions for each `extra` family relative to the verified
  zone (1,1) geometry
- explicit transfer region shapes at each `intra ↔ extra` interface corner

## Things Not To Do

- do not revive stale `rearch-zone-grid` milestone assumptions
- do not treat seams/interconnects as the settled next step
- do not overclaim that geometry is placement-derived unless you can show the builder path
- do not treat the REPL as a toy debug layer

## Current Design Pressure

The hard unresolved problem is not ordinary child-to-parent reverse routing. It is child-to-self routing while preserving enough local row/layer identity across the outer perimeter.
