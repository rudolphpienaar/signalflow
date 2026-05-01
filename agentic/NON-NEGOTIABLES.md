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

6. Manhattan gridding is invariant.
   Do not "fix" a collision by dragging longitude hops onto latitude rows or by letting a path shortcut through a region it does not own. Fix the transition or lane-realization doctrine instead.

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

4. One substrate owner.
   If the board layer is the active runtime, then board-owned geometry must be
   the authority for board solve/materialize behavior. Imported kernel region
   frames may be temporary inputs during migration, but they may not remain a
   vague second substrate truth once region-motion work begins.

5. The deprecated kernel cross is not the target architecture.
   `RoutingZone.intraKernel|westKernel|eastKernel|northKernel|southKernel`
   may exist temporarily as compatibility output, but no new work may deepen
   dependency on them as required runtime truth.

6. Seam/interconnect substrate is not the target architecture.
   `RoutingZoneInterconnect` may remain temporarily as compatibility or
   topology debt, but no new work may treat it as a required routed body once
   overlap is the chosen model.

7. Overlap is geometric, not an occupancy exception.
   Shared territory between adjacent zones is normalized by zone-local geometry.
   It does not authorize shared route cells and does not justify a separate
   seam substrate object.

8. Independent overlap zones are the current truth surface.
   Zone `1,1`, `1,2`, and `1,3` materialization for `back-and-forth.yaml` must be correct before any full-board overlap integration resumes.

9. Source modules are not geometry layers.
   `ChipId.moduleName` is source/module/file identity and part of canonical chip
   identity. Do not repurpose it as a call-stack-depth layer.

10. Geometry scope and drawable boundary are separate.
    A load-bearing geometry scope may exist without a rendered box. Rendering a
    box is policy, not proof that the geometry scope exists.

11. Call-depth layers are the next canonical geometry-scope source.
    If a layout needs layer separation, derive it from `CallingStack` depth or an
    explicit geometry grouping concept, not fake source module names.

## World Canvas / World Solving Doctrine

1. No seam chip override. Ever.
   Do not transplant Zb's Wt chip positions into Za's Et positions. This causes
   visual collisions when Wt chips land inside Zb's Em module frame.
   Use `wOffset` recurrence for world alignment instead.

2. World alignment uses the `wOffset` recurrence:
   `wOffset[zone_0] = 0`
   `wOffset[zone_{i+1}] = wOffset[zone_i] + (Za.Et_minCol − Zb.Wt_minCol)`
   Zone i+1's Wt chips land at zone i's Et world column by construction.

3. `mergedCellMap_get()` key is `(row, col)` — first element is **row**, not col.
   Swapping produces an over-tall, under-wide canvas with clipped routes.

4. Canvas sizing must cover all four sources: `regionFramesById`,
   `effectiveBoundaryFramesByName`, `chipDrawPlacementsByChip`, and route
   cells from `mergedCellMap_get()`. Missing any source causes truncation.

5. Each zone materializes at its natural local geometry — no override.

## REPL / Truth-Surface Doctrine

1. The REPL is not a toy layer. It is a collaborative truth surface.

2. Debug/runtime projection may clarify architecture but may not invent a separate one.

3. If the REPL says `chip`, `kernel`, `board`, `solution`, `materialized`, `geometry`,
   or `policy`, those names should correspond to real architectural objects or intended
   replacement objects in production design.

4. Snippet output counts as architectural evidence. Use it.

5. Canonical snippets are live contracts during substrate work.
   The following snippet surface must remain working throughout the migration
   unless a specific snippet is intentionally replaced in the same phase:
   - `snippets/algebraic/zone_geometry.py`
   - `snippets/algebraic/hub_kernel_solver.py`
   - `snippets/algebraic/hub_internal_wiring.py`
   - `snippets/algebraic/hub_internal_geometry.py`

6. No deferred snippet breakage.
   If a canonical snippet stops running or shows unexplained output changes, the
   phase is not done. Fix the snippet surface or add a compatibility adapter
   before proceeding.

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
6. Run the canonical snippet contract surface for the touched phase.

## Required Review Questions

Before calling a routing or geometry change done, answer:

1. Do any distinct routes share a realized cell?
2. Do any merged-route tee/cross glyphs remain?
3. Is any shared-looking fan/manifold actually shared occupancy?
4. Is any transfer region being used outside its declared geometry?
5. Is any architectural claim stronger than the implementation evidence?
6. Does `laneMap_get()` use channel capacity for REVERSE hops?
7. Are any `WiringSolution` instances being shared across solves?
8. Did any canonical snippet break or drift without explicit explanation?
9. Does the observed bug trace to a broader doctrinal or ownership issue?
10. If yes, was that doctrinal issue named explicitly before proposing any local-only fix?
11. Is symbolic topology being treated as the semantic owner where order,
    adjacency, or continuity are the real issue?
12. Is any source module/file name being used as a hidden stack-depth geometry
    layer?
13. Is any load-bearing boundary assumed to exist only because it is drawable?

If any answer is yes, the work is not done.
