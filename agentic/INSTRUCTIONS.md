Read `agentic/ZEROSHOT.md`, `agentic/HANDOFF.md`, `agentic/NON-NEGOTIABLES.md`,
and `agentic/PLAN.md` in that order. Then run `python -m pytest tests_symbolic/ -q`
and confirm the green baseline.

Then read these geometry docs before coding:

- `docs/geometry_symbolic_topology.adoc`
- `docs/zoneInterconnect_geometry.adoc`
- `docs/board.adoc`

Then inspect the current geometry-topology path before coding:

- `src/signalflow/board/geometry/zones.py`
- `src/signalflow/board/geometry/symbolic.py`
- `src/signalflow/board/geometry/expr.py`
- `src/signalflow/board/geometry/doctrine.py`
- `src/signalflow/board/geometry/coupling.py`
- `src/signalflow/board/builders.py`

The immediate job is no longer old WiringSolution work and no longer primarily
"remove more kernel/interconnect debt."

The immediate job is:

- define symbolic topology for one board
- make order / adjacency / continuity explicit
- move coupling doctrine onto that topology
- prepare the local interpreter for the first `Ee` continuity case

The first concrete scoped case is:

- move only `Ee`
- keep `Efe` fixed
- show that extra-ring continuity is now a first-class doctrinal problem
- make that continuity queryable from symbolic topology before repairing it

Do not start broad interpreter work before the symbolic topology owner is
clearly defined.

Use these truth surfaces during the phase:

- `snippets/algebraic/zone_geometry.py -- --zone 1,1`
- `snippets/algebraic/zone_geometry_bump.py -- --zone 1,1 --delta-cols 5`
- `snippets/algebraic/zone_geometry_ee_displace.py -- --zone 1,1 --delta-cols 5`
