# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `agentic/PLAN.md`

Current branch is `worldscale-extra-routing`. Current version is `5.9.19`.

## Immediate Focus

Do not restart old WiringSolution phases and do not restart the older
kernel-cross / interconnect-cleanup-first mindset.

The current major task is:

**make symbolic geometry topology the top-layer geometry model**

## First Step

Read the new geometry plan in `agentic/PLAN.md`.

Then inspect:

- `src/signalflow/board/geometry/zones.py`
- `src/signalflow/board/geometry/symbolic.py`
- `src/signalflow/board/geometry/expr.py`
- `src/signalflow/board/geometry/doctrine.py`
- `src/signalflow/board/geometry/coupling.py`
- `src/signalflow/board/builders.py`

## Next Execution Step

1. treat current frame geometry as migration baseline
2. treat symbolic topology as the intended new semantic owner
3. define one board topology schema
4. make `Ee` neighborhood and continuity membership queryable from that schema
5. only then build the first interpreter step

## Verification Surface

Before and after each meaningful change, use:

1. `python -m pytest tests_symbolic -q`
2. `snippets/algebraic/zone_geometry.py -- --zone 1,1`
3. `snippets/algebraic/hub_internal_geometry.py`
4. `snippets/algebraic/zone_geometry_bump.py -- --zone 1,1 --delta-cols 5`
5. `snippets/algebraic/zone_geometry_ee_displace.py -- --zone 1,1 --delta-cols 5`

## Primary Files For This Phase

- `src/signalflow/board/geometry/zones.py`
- `src/signalflow/board/geometry/symbolic.py`
- `src/signalflow/board/geometry/expr.py`
- `src/signalflow/board/geometry/doctrine.py`
- `src/signalflow/board/geometry/coupling.py`
- `src/signalflow/board/builders.py`

## Things Not To Do

- do not add another local geometry patch before naming the doctrinal issue
- do not start full world propagation yet
- do not treat concrete frames as the only semantic geometry definition
- do not restart a repo-wide hygiene pass

## Current Reality Check

The board geometry slice is stable enough to build on.
The missing architecture is symbolic topology plus a local interpreter, not one
more local displacement hack.
