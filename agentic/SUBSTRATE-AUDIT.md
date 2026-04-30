# Geometry-Semantics Dependency Audit

**Date:** April 2026  
**Branch:** `worldscale-extra-routing`  
**Version:** `6.0.3`

**Checkpoint:** This audit was written at v5.9.19 and refreshed at v6.0.3.
All three overlap zones (`1,1`, `1,2`, `1,3`) materialize correctly, and the
key `1,2` / `1,3` seam now aligns shared chip rows. `WorldGeometryResolver`
and `BoardWorldMaterializedSolution` are the current board-owned world
surfaces; active work is production context/YAML assembly above the snippet.
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

It remains:

1. define symbolic topology for one board
2. make `Ee` continuity and family membership queryable from that topology
3. then interpret continuity repair from explicit doctrine

Do this after world resolver extraction, not before.

## Acceptance Gate

This audit is current enough when:

- the remaining semantic geometry gaps are localized
- the next replacement target is explicit
- the geometry snippet/test contract remains green
