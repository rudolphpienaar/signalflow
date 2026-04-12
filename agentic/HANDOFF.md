# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.19`

## Current Baseline

The board geometry refactor is far enough along to change the next target:

- geometry is consolidated under `src/signalflow/board/geometry/`
- `GeometryZone` is the canonical geometry unit
- symbolic geometry expressions exist
- coupling doctrine exists
- overlap and displacement demos/tests exist

## What Just Changed Strategically

The next architectural target is now:

- symbolic geometry topology as the top geometry layer

not merely:

- more cleanup of kernel-cross / seam debt

That older cleanup still matters, but it is no longer the next best center of
gravity for architecture work.

## Current Reality

The code can now:

- reason about geometry zones as first-class objects
- express symbolic geometry mutations
- express first-order coupling rules
- demonstrate local displacement such as moving only `Ee`

But it still does **not** have:

- a first-class symbolic topology schema for one board
- a local interpreter that can chain geometry reactions by rule
- an explicit continuity operator for the extra ring

## Most Important Current Conclusion

The next work should be framed as:

1. define symbolic topology
2. attach doctrine to that topology
3. build the local interpreter
4. solve the first continuity case (`Ee`)

Do not resume work as if the branch were still only about:

- kernel-cross removal
- interconnect removal

Those are still real architectural debts, but the new geometry direction is now
the stronger organizing target.

## Immediate Next Target

The next concrete scoped case is:

- move `Ee`
- keep `Efe` fixed
- detect that the extra ring continuity is now broken
- repair it through explicit doctrine and interpretation

That is the first interpreter-worthy geometry case.

## Important Files

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

Use snippet output as evidence, not prose alone.

## Verification Baseline

At this handoff update:

- `python -m pytest tests_symbolic -q` is green
- `tests_symbolic/test_geometry_displacement.py` is green
- the canonical geometry snippets are green

## What Not To Trust

- any doc that still implies builder arithmetic alone is the right semantic
  home of geometry order and adjacency
- any suggestion that continuity repair for `Ee` should be solved by a one-off
  patch before topology doctrine exists
- any statement that symbolic topology is only optional polish

## Operating Discipline

- doctrine first
- symbolic topology before broad interpreter work
- tests and snippets stay green throughout
