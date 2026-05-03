# SignalFlow Execution Plan

**Date:** April 2026
**Branch:** `worldscale-extra-routing`
**Version:** `6.0.7`

## Current Gate

- `tests_symbolic/`: `179 passed`
- Recent Python `ruff check`: clean
- Recent Python `ruff check --select ANN`: clean
- Default world render:
  `signalflow examples/simple-circuit/back-and-forth.yaml`
- Forward-only fixture:
  `signalflow examples/simple-circuit/neural-network.yaml`
- Key parity/debug surfaces:
  `signalflow examples/simple-circuit/back-and-forth.yaml --zones '1,2;1,3' --geometry`
  `world_zone_inspect.py -- --zones '1,2;1,3'`

## Current Priority

Separate source modules from load-bearing geometry scopes.

Working target:

```text
CallingStack depth layers
Geometry scope / boundary ownership
Board effective boundary construction
WorldGeometryResolver boundary harmonization
```

This is still Arc R/R4-adjacent hardening because it fixes the structural reason
neural-network DAG layout currently needs fake layer module names.

## Depth-Layer Boundary Sprint

Doctrine:

1. `module` remains real source/module/file identity.
2. `module` must not be treated as stack-depth geometry.
3. Call-stack depth layers are the canonical implicit geometry scopes.
4. Geometry scopes exist even when they are not drawable.
5. Implicit depth scopes default to non-drawable.
6. Source module/file boxes are optional overlays or explicitly promoted
   structural groups.

Implementation sketch:

1. Audit all `module/*` assumptions in boundary construction, coupling,
   rendering, and world harmonization.
2. Remove module-banded depth as the default in `calling_stack.py`; call depth
   should own the layer model.
3. Introduce a typed geometry-scope/boundary carrier instead of string-only
   `module/*` interpretation.
4. Generate depth scopes from `CallingStack.levels`.
5. Teach rendering to draw only drawable scopes.
6. Add regressions:
   - neural-network in one real module lays out by depth
   - different source modules at the same depth share the same depth geometry
     layer unless explicitly grouped otherwise
   - existing `back-and-forth.yaml` world seam evidence does not regress

Proposed carrier:

```text
BoardGeometryScope
  scopeId: layer/0 | layer/1 | module/foo.c | group/name
  kind: depth_layer | source_module | user_group
  label: optional render/debug label
  chipRefs: canonical chip refs in the scope
  drawable: whether the scope renders as a boundary
```

Keep old `effectiveBoundaryFramesByName` as a compatibility projection only
while migrating. It should stop being the semantic owner.

## Arc R: Reverse / Recursive / World Wiring

### R0: Extra Ring Realization

Complete.

### R1: Collision Check Extension

Complete enough for current overlap-zone truth surfaces. Keep collision checks
honest while extracting world resolver.

### R2: Recursive Wiring End-To-End Demo

Complete. Zones `1,1`, `1,2`, and `1,3` materialize independently with correct
wiring.

### R3: Medial U-Turn Demo

Deferred. It is valid but not the current blocker.

### R4: World Geometry Resolver And Depth-Layer Scopes

Active for hardening. The next hardening target is depth-layer geometry scope
ownership.

What is now known:

1. Horizontal world alignment uses:
   `wOffset[i+1] = wOffset[i] + (Za.Et_minCol - Zb.Wt_minCol)`.
2. Vertical world alignment uses seam chip rows, not north-stack accumulation.
3. North relaxation budget includes `Ne + Nt + Nfi`.
4. No chip position transplant is allowed.
5. Materialized world geometry/wiring output is owned by
   `BoardWorldMaterializedSolution`, not the snippet.
6. `signalflow file.yaml` uses the world path by default.
7. Omitted `return` means a forward-only port with no blank reverse route.
8. Current `module/*` effective boundaries are migration machinery, not final
   geometry doctrine.

Extraction acceptance:

- Top-level CLI reproduces `world_zone_inspect.py` evidence for `1,2;1,3`.
- `grandchild.ts` remains row-aligned across the seam.
- `Ne`/`Se` four-lane spans remain four lanes where appropriate.
- Full `tests_symbolic/` remains green.
- Recent-file ruff and ANN remain green.
- Forward-only neural-network render remains free of `◄` return stubs.
- Neural-network layout no longer requires fake source modules to represent
  depth layers.

## Arc G: Symbolic Geometry Topology

Still valid. Do not resume until R4 extraction is stable.

Arc G target stack:

1. symbolic topology schema
2. coupling and constraint doctrine
3. local geometry interpreter
4. concrete metric realization

The key missing semantic layer is still symbolic topology for region order,
adjacency, continuity, and coupling. That is the next architectural axis after
the depth-layer geometry split and world resolver hardening.
