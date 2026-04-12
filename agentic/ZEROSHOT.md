# Zero-Shot Handoff: SignalFlow Symbolic Geometry Topology Work

**Branch:** `worldscale-extra-routing`  
**Version:** `5.9.19`

## Current Truth In One Screen

- the board geometry slice is real
- `GeometryZone` is canonical
- symbolic geometry expressions exist
- first-order coupling doctrine exists
- local displacement demos/tests exist
- the next architectural problem is symbolic topology, not just more local
  frame mutation work

## Actual Target

- symbolic topology as top-layer geometry definition
- coupling doctrine attached to symbolic regions
- local interpreter for geometry reactions
- concrete frames as realization of that topology

## Immediate Job

Follow `agentic/PLAN.md` from Phase `G0` onward.

Do not restart the old phase framing.
Do not deepen dependency on ad hoc frame inference as the only semantic source
of order and adjacency.

## Most Important Files

- `src/signalflow/board/geometry/zones.py`
- `src/signalflow/board/geometry/symbolic.py`
- `src/signalflow/board/geometry/expr.py`
- `src/signalflow/board/geometry/doctrine.py`
- `src/signalflow/board/geometry/coupling.py`
- `src/signalflow/board/builders.py`

## Most Important Snippets

- `snippets/algebraic/zone_geometry.py`
- `snippets/algebraic/hub_internal_geometry.py`
- `snippets/algebraic/zone_geometry_bump.py`
- `snippets/algebraic/zone_geometry_ee_displace.py`

## First Action For A New Agent

```bash
python -m pytest tests_symbolic/ -q
```

Then read `agentic/HANDOFF.md` and `agentic/PLAN.md` before modifying any file.
