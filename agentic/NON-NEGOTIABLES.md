# SignalFlow Routing Non-Negotiables

This file is the hard gate for routing and geometry work on this branch.

## Core Physics

1. No shared route cells. Ever.
   Two distinct wires may not occupy the same realized route cell.

2. Geometry ownership may overlap; route occupancy may not.
   A region may legally allow more than one directional species, but that does not permit
   multiple wires to share any realized cell inside that region.

3. Any `T`, `┬`, `┴`, `┼`, or equivalent merged-route junction glyph is a bug unless
   explicitly approved for that exact case.

4. Fan, manifold, spine, vane, transition, overlap, `intra`, and `extra` are geometry words,
   not occupancy words. They describe where turns, transfers, or attachments may be realized.
   They do not authorize shared route cells.

5. A lane belongs to one wire.
   If a rendered solution suggests more than one wire occupies the same lane, the solution is wrong.

## Transfer / Overlap Rules

1. A transfer region exists only where its contributing routing families geometrically meet.

2. A transfer region permits direction or substrate change.
   It does not permit coincident occupancy.

3. The same doctrine applies to any future `intra → extra` transfer geometry.

4. If `extra` is added, `extra` must remain continuous enough to explain real routes and
   constrained enough to avoid becoming a freeform excuse for ad hoc pathfinding.

## Lane Assignment Non-Negotiables

1. Lane integers do NOT belong on `PathHop` or `AlgebraicPath`.
   `AlgebraicPath` is a pure topology descriptor. Lane integers are owned by `WiringSolution`.

2. `WiringSolution` must receive `channelLaneCounts` from the board at construction time.
   `laneMap_get()` for `REVERSE` hops must use channel capacity, not bundle size.
   The tests assert `eLong[10]` for wire 0 of a 5-wire bundle on a 10-lane board.
   Using bundle size silently produces wrong lane indices.

3. `WiringSolution` instances are per-solve, not module-level singletons.
   Shared mutable instances cause test-order failures.

4. The `algebraicPathText` string format is a public output.
   Tests assert exact string forms. The property shim must reproduce them precisely.

## Information Architecture Non-Negotiables

1. No closed information loops.
   Structured data must not be converted to a string so that downstream code can parse
   the string to recover the structure. If you see this pattern, it is a bug in the
   architecture, not a valid implementation technique.

2. No ghost fields.
   If a field defaults to 0 and is never meaningfully set, it is a sign that the concept
   was partially anticipated but implemented elsewhere. Either use it or remove it.

3. No parallel type hierarchies without explicit reconciliation.
   If `engine/debug.py` and `board/solver_runtime.py` both have a `SolvedWire` concept,
   one should derive from the other or they should share a base. Do not add a third.

## REPL / Truth-Surface Doctrine

1. The REPL is not a toy layer. It is a collaborative truth surface.

2. Debug/runtime projection may clarify architecture but may not invent a separate one.

3. If the REPL says `chip`, `kernel`, `board`, `solution`, `materialized`, `geometry`,
   or `policy`, those names should correspond to real architectural objects or intended
   replacement objects in production design.

4. Snippet output counts as architectural evidence. Use it.

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
6. Does `laneMap_get()` use channel capacity for REVERSE hops?
7. Are any `WiringSolution` instances being shared across solves?

If any answer is yes, the work is not done.
