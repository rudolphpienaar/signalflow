# SignalFlow Routing Non-Negotiables

This file is the hard gate for routing work in this repository.

If code, tests, comments, or "plausible routing intuition" conflict with this
file, this file wins.

## Core Physics

1. No shared route cells. Ever.
   Two distinct wires may not occupy the same realized route cell.

2. Geometry ownership may overlap; route occupancy may not.
   A region may legally allow more than one directional species, but that does
   not permit multiple wires to share any realized cell inside that region.

3. Any `T`, `┬`, `┴`, `┼`, or equivalent merged-route junction glyph is a bug
   unless it has been explicitly approved by the user for that exact case.

4. Fan, manifold, spine, vane, transition, and overlap are geometry words, not
   occupancy words.
   They describe where turns and attachments may be realized. They do not
   authorize shared route cells.

5. A lane belongs to one wire.
   If a rendered solution suggests more than one wire occupies the same lane,
   the solution is wrong.

## Transition / Overlap Rules

1. `INTRA_ROUTING_TRANSITION` (`x`) exists only where `LONG` and `LAT`
   geometrically overlap.

2. There can never be an `x` in a cell/area where `LONG` and `LAT` do not
   intersect.

3. Transition zones permit direction changes. They do not permit coincident
   occupancy.

4. The same doctrine applies to `INTER_ROUTING_FAN_IN_OUT`:
   it is a place where reconfiguration may happen, not a place where wires may
   collapse into shared cells.

## Fan In / Fan Out

1. Chip walls expose only declared terminals.

2. Fan regions own expansion / contraction geometry.

3. In sparse-terminal cases, the wall terminals should be centered on the
   usable wall span.

4. A fan-in/out solution must still preserve one-wire-per-lane all the way
   through the fan geometry.

## Required Routing Pass Checklist

Before each routing design or implementation pass:

1. Read this file.
2. Restate the active invariant(s) in the working notes / commentary.
3. Identify the exact forbidden occupancy pattern being fixed.
4. Add or update an invariant test when the change affects routing behavior.
5. Verify the realized route cells after the change, not just the picture.

## Required Review Questions

Before calling a routing change "done", answer these questions:

1. Do any distinct routes share a realized cell?
2. Do any merged-route tee/cross glyphs remain?
3. Is any "shared manifold" actually shared occupancy?
4. Is any transition/overlap region being used outside its declared geometry?
5. Does the rendered solution preserve one-wire-per-lane everywhere?

If any answer is "yes", the routing solution is not acceptable.
