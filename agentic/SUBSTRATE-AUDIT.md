# Geometry-Semantics Dependency Audit

**Date:** April 2026  
**Branch:** `worldscale-extra-routing`  
**Version:** `6.0.7`

**Checkpoint:** This audit was written at v5.9.19 and refreshed at v6.0.7.
All three overlap zones (`1,1`, `1,2`, `1,3`) materialize correctly, and the
key `1,2` / `1,3` seam now aligns shared chip rows. `WorldGeometryResolver`
and `BoardWorldMaterializedSolution` are the current board-owned world
surfaces; `signalflow file.yaml` now renders the full harmonized world circuit.
Forward-only omitted-return semantics are also core behavior: chip geometry and
route solving must follow declared terminals, not implicit signal/return row
pairs.
The next semantic correction is boundary ownership: source modules are not
stack-depth geometry layers. Call-depth layers should become implicit
load-bearing geometry scopes, with drawability controlled separately.
Use `agentic/HANDOFF.md` before treating any seam/interconnect language here as
active architecture.

## Purpose

This audit now answers a different question than the earlier overlap-only audit:

Where does the active geometry runtime still depend on implicit builder
arithmetic and raw frame inference instead of on explicit symbolic topology and
geometry doctrine?

Each item is classified as one of:

- `must_replace`
- `temporary_input`
- `acceptable_runtime_truth`

## Classification Rules

### `must_replace`

A semantic geometry relation still exists only as implicit arithmetic or ad hoc
frame inspection, and the new symbolic-topology direction should own it.

### `temporary_input`

The code still stages through the older representation, but the dependency is
bounded and can survive briefly during migration.

### `acceptable_runtime_truth`

The code is allowed to stay metric/concrete because it is execution-time
realization rather than semantic topology.

## Current Findings

| Classification | File / Symbol | Dependency | Why it matters |
| --- | --- | --- | --- |
| `must_replace` | `src/signalflow/board/builders.py` | region order and adjacency mostly encoded as builder arithmetic | The engine still learns too much semantic geometry from coordinate formulas instead of from explicit symbolic topology. |
| `must_replace` | `src/signalflow/models/calling_stack.py` | module-banded depth behavior when multiple modules exist | Source modules must not decide call-depth geometry. Call-stack depth should be the canonical implicit layer source. |
| `must_replace` | `effectiveBoundaryFramesByName` `module/*` assumptions | geometry scopes are represented as source-module boundary strings | The next sprint needs a typed geometry-scope/boundary carrier with separate kind and drawable policy. |
| `must_replace` | untyped boundary names | semantic kind inferred from string prefixes such as `module/` | Boundary/scope kind should be explicit so `layer/N`, `module/foo`, and future `group/name` scopes cannot be confused. |
| `must_replace` | `src/signalflow/board/geometry/coupling.py` | coupling families still lower primarily into concrete region-id rules | Coupling doctrine exists, but it still needs a stronger symbolic topology owner. |
| `must_replace` | local geometry continuity around `Ee` | extra-ring continuity is not yet expressed as a first-class operator and interpreted repair rule | The displacement test proves the need for continuity doctrine. |
| `temporary_input` | `src/signalflow/board/geometry/zones.py` | semantic order inferred from concrete `GeometryZone` frames | This is useful baseline truth, but not the intended long-term semantic layer. |
| `temporary_input` | `src/signalflow/board/geometry/overlap.py` | overlap resolution still begins from concrete metric geometry rather than symbolic topology | Acceptable for now, but not the final architecture. |
| `acceptable_runtime_truth` | `GeometryZone.frame` and concrete board geometry | metric realization | Concrete frames should remain the runtime realization layer even after symbolic topology becomes semantic owner. |

## What Has Already Been Reduced

The active geometry slice is materially cleaner than before:

- `GeometryZone` is canonical
- chip-terminal zones own chips and exact terminals
- coupling doctrine exists
- a pure `Ee` displacement test exists

These are good baseline gains. They make the symbolic-topology migration
possible.

## Immediate Implications

The next important replacement is not another isolated geometry-family patch.

It is now:

1. split source-module identity from geometry-boundary ownership
2. derive implicit depth-layer scopes from `CallingStack`
3. keep scope existence separate from drawable rendering
4. preserve world seam evidence and forward-only DAG behavior

Do this before broader Arc G symbolic topology work.

## Acceptance Gate

This audit is current enough when:

- the remaining semantic geometry gaps are localized
- the next replacement target is explicit
- the geometry snippet/test contract remains green
