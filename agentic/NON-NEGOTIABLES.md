# SignalFlow Routing Non-Negotiables

This file is the hard gate for routing and geometry work on this branch.

## Core Physics

1. No shared route cells. Ever.
   Two distinct wires may not occupy the same realized route cell.

2. Geometry ownership may overlap; route occupancy may not.
   A region may legally allow more than one directional species, but that does not permit multiple wires to share any realized cell inside that region.

3. Any `T`, `┬`, `┴`, `┼`, or equivalent merged-route junction glyph is a bug unless explicitly approved for that exact case.

4. Fan, manifold, spine, vane, transition, overlap, `intra`, and `extra` are geometry words, not occupancy words.
   They describe where turns, transfers, or attachments may be realized. They do not authorize shared route cells.

5. A lane belongs to one wire.
   If a rendered solution suggests more than one wire occupies the same lane, the solution is wrong.

## Transfer / Overlap Rules

1. A transfer region exists only where its contributing routing families geometrically meet.

2. A transfer region permits direction or substrate change.
   It does not permit coincident occupancy.

3. The same doctrine applies to any future `intra -> extra` transfer geometry.

4. If `extra` is added, `extra` must remain continuous enough to explain real routes and constrained enough to avoid becoming a freeform excuse for ad hoc pathfinding.

## REPL / Truth-Surface Doctrine

1. The REPL is not a toy layer.
   It is a collaborative truth surface.

2. Debug/runtime projection may clarify architecture but may not invent a separate one.

3. If the REPL says `chip`, `kernel`, `board`, `solution`, `materialized`, `geometry`, or `policy`, those names should correspond to real architectural objects or intended replacement objects in production design.

4. Snippet output counts as architectural evidence.
   Use it.

## Anti-Slop / Anti-Overclaim Rule

1. Do not claim that something is implemented if it is only approximated.

2. Do not claim a geometry property unless you can point to:
   - the builder path,
   - the runtime object,
   - or the snippet/render output that demonstrates it.

3. If a change is a bounded fix rather than the full architectural correction, say so explicitly.

## Required Pass Checklist

Before each routing or geometry design pass:

1. Read this file.
2. Identify the exact forbidden occupancy or false-geometry pattern under discussion.
3. Identify the owning runtime path.
4. Decide whether the change belongs in:
   - board construction,
   - symbolic solve,
   - realization/materialization,
   - or documentation only.
5. Verify with snippet output, not prose alone.

## Required Review Questions

Before calling a routing or geometry change done, answer:

1. Do any distinct routes share a realized cell?
2. Do any merged-route tee/cross glyphs remain?
3. Is any shared-looking fan/manifold actually shared occupancy?
4. Is any transfer region being used outside its declared geometry?
5. Is any architectural claim stronger than the implementation evidence?

If any answer is yes, the work is not done.
