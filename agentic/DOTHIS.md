# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `docs/worldscale_geometry.adoc`
4. `papers/new_ways.adoc`

Current branch is `worldscale-extra-routing`. Current version is `5.9.8`.

## Immediate Task

Do not jump straight into solver code.

The next useful task is to make the proposed `extra` substrate geometrically explicit against the current WTE board geometry.

Before coding, inspect:

- `snippets/algebraic/hub_internal_geometry.py`
- `snippets/algebraic/hub_internal_wiring.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/routing/geometry.py`

## What To Produce First

Produce one of these before implementation:

- a concrete extension to `docs/worldscale_geometry.adoc` with more explicit transfer-region figures
- or a new design note showing exact region/frame additions for `xwLong`, `xnLat`, `xeLong`, `xsLat`

## Things Not To Do

- do not revive stale `rearch-zone-grid` milestone assumptions
- do not treat seams/interconnects as the settled next step
- do not overclaim that geometry is placement-derived unless you can show the builder path
- do not treat the REPL as a toy debug layer

## Current Design Pressure

The hard unresolved problem is not ordinary child-to-parent reverse routing. It is child-to-self routing while preserving enough local row/layer identity across the outer perimeter.
