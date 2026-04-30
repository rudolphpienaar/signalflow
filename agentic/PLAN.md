# SignalFlow Execution Plan

**Date:** April 2026
**Branch:** `worldscale-extra-routing`
**Version:** `6.0.5`

## Current Gate

- `tests_symbolic/`: `178 passed`
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

Harden the top-level world render path while keeping the current world
harmonization and materialized render surfaces in production board code.

Working target:

```text
WorldGeometryResolver
BoardWorldMaterializedSolution
WorldRenderOptions
```

This is the completion work for Arc R before Arc G resumes.

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

### R4: World Geometry Resolver

Active for hardening.

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

Extraction acceptance:

- Top-level CLI reproduces `world_zone_inspect.py` evidence for `1,2;1,3`.
- `grandchild.ts` remains row-aligned across the seam.
- `Ne`/`Se` four-lane spans remain four lanes where appropriate.
- Full `tests_symbolic/` remains green.
- Recent-file ruff and ANN remain green.
- Forward-only neural-network render remains free of `◄` return stubs.

## Arc G: Symbolic Geometry Topology

Still valid. Do not resume until R4 extraction is stable.

Arc G target stack:

1. symbolic topology schema
2. coupling and constraint doctrine
3. local geometry interpreter
4. concrete metric realization

The key missing semantic layer is still symbolic topology for region order,
adjacency, continuity, and coupling. That is the next architectural axis after
world resolver extraction.
