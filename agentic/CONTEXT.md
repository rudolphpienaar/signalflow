# Project Context: SignalFlow Symbolic Geometry Topology Work

This file is the current architectural baseline for geometry work on this
branch.

## Current Architectural State

- Branch: `worldscale-extra-routing`
- Version: `5.9.19`

## What Is Stable Now

- board-owned geometry is the active geometry center
- `GeometryZone` is canonical
- board geometry is consolidated under `src/signalflow/board/geometry/`
- the symbolic geometry expression layer exists
- the first coupling doctrine exists
- displacement and coupling tests exist and are green

## What Changed Strategically

The target is no longer merely:

- board ownership while deleting kernel/interconnect debt

The target is now:

- symbolic topology as the top-layer geometry definition
- concrete frames as metric realization of that topology
- coupling doctrine attached to symbolic geometry
- a local interpreter that can react to geometry mutations by rule

## Actual Geometry Stack

The intended stack is:

1. symbolic topology schema
2. coupling / constraint doctrine
3. local interpreter
4. concrete metric realization

This is the new center of gravity for the branch.

## What Is Already In Place

- `src/signalflow/board/geometry/zones.py`
  - `GeometryZone`
  - `BoardGeometry`
- `src/signalflow/board/geometry/symbolic.py`
  - symbolic geometry operands and tuple expressions
- `src/signalflow/board/geometry/expr.py`
  - normalized symbolic geometry expression forms
- `src/signalflow/board/geometry/doctrine.py`
  - overlap expression banks
- `src/signalflow/board/geometry/coupling.py`
  - coupling operators and first concrete coupling families
- `src/signalflow/board/geometry/overlap.py`
  - first overlap resolution/apply path

## What Is Missing

The codebase still does not have a first-class symbolic topology schema that
answers:

- what is east of `Ee`
- what regions are in the east extra family
- what continuity obligations exist around `Ee`
- what local move should trigger what secondary geometry reaction

That knowledge still lives too much in builder arithmetic and inferred frame
relationships.

## Immediate Consequence

The next major task is not another local displacement patch.

It is:

- define symbolic topology for one board
- then use it to drive coupling and interpretation

## Important Runtime Truth

Current frame geometry remains authoritative for execution today.

But current frame geometry is **not** the ideal semantic top layer. The branch
is now trying to make symbolic topology that semantic top layer while keeping
the executable frame model green throughout the migration.

## Important Files For The New Focus

- `src/signalflow/board/geometry/zones.py`
- `src/signalflow/board/geometry/symbolic.py`
- `src/signalflow/board/geometry/expr.py`
- `src/signalflow/board/geometry/doctrine.py`
- `src/signalflow/board/geometry/coupling.py`
- `src/signalflow/board/geometry/overlap.py`
- `src/signalflow/board/builders.py`

## Important Snippets

- `snippets/algebraic/zone_geometry.py`
- `snippets/algebraic/hub_internal_geometry.py`
- `snippets/algebraic/zone_geometry_bump.py`
- `snippets/algebraic/zone_geometry_ee_displace.py`

These are truth surfaces and must remain working.

## Current Verification Baseline

At this context update:

- `python -m pytest tests_symbolic -q` is green
- `tests_symbolic/test_geometry_displacement.py` is green
- the canonical geometry snippets are green

## Document Precedence

When files disagree, prefer:

1. `agentic/HANDOFF.md`
2. `agentic/DOTHIS.md`
3. `agentic/NON-NEGOTIABLES.md`
4. `agentic/PLAN.md`
5. runtime/snippet evidence

## Mandatory Operating Rule

Do not treat symbolic topology as optional future cleanup.

It is now the intended top-layer geometry direction for this branch.
