Read `agentic/ZEROSHOT.md`, `agentic/HANDOFF.md`, `agentic/NON-NEGOTIABLES.md`,
and `agentic/PLAN.md` in that order. Then run
`python -m pytest tests_symbolic/ -q` and confirm the current green baseline.

Then inspect the current board-substrate ownership path before coding:

- `src/signalflow/board/builders.py`
- `src/signalflow/board/invariants.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/engine/inspect/build.py`

The immediate job is no longer WiringSolution extension.

The immediate job is Phase `A0` from `agentic/PLAN.md`:

- audit where board-era substrate truth still comes from `RoutingZone.intraKernel`
  or other upstream placed-kernel facts
- classify those reads
- then proceed with the authoritative-board-substrate plan

Do not start pressure-driven region motion before the substrate authority cut is
clear.
