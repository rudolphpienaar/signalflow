# Zero-Shot Handoff: SignalFlow Board Runtime And `extra` Routing

**Branch:** `worldscale-extra-routing`
**Version:** `5.9.16`

## Current Truth In One Screen

- The main active runtime is the board-era runtime, not the old kernel-only rearch notes.
- `chips.chip_get(...)` returns `BoardChip`.
- `chip.internalBoard_get()` returns `BoardKernel`.
- `kernel.board_get(chipPlacementPolicy=...)` returns `Board`.
- `solution.board_materialize(board, policy=...)` is the current materialization API.
- WTE board geometry is re-anchored from live placed terminal centroids before realization.
- `docs/worldscale_geometry.adoc` contains the next macro design direction.
- Geometry centralization is complete: `BoardGeometrySpec`, `ZoneSymbolicInvariants`,
  and `boardGeometryConfig` singleton are all live.

## Most Important Current Files

- `docs/worldscale_geometry.adoc`
- `papers/new_ways.adoc`
- `src/signalflow/board/doctrine.py` — `BoardGeometrySpec`, `RingGeometrySpec`
- `src/signalflow/board/invariants.py` — `ZoneSymbolicInvariants`
- `src/signalflow/config/board_defaults.py` — `boardGeometryConfig` singleton
- `src/signalflow/board/builders.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/routing/placement.py`
- `src/signalflow/routing/geometry.py`

## Key Snippets

- `snippets/algebraic/zone_invariants.py` — full geometry pipeline (CLI, `--zone`)
- `snippets/algebraic/zone_geometry.py` — zone geometry standalone (CLI, `--zone`)
- `snippets/algebraic/hub_internal_geometry.py` — chip internal board geometry
- `snippets/algebraic/hub_internal_wiring.py` — internal chip wiring + collisions

## Current Design Direction

The next big idea is:

- keep `intra` as the inner local kernel substrate
- add concentric outer `extra` routing families
- connect `intra` and `extra` through explicit transfer regions

Do not reduce this to:

- seam objects
- extra placed kernels
- hand-wavy virtual-kernel prose

The unresolved hard case is child-to-self routing through `extra` while
preserving enough local row/layer identity.

## First Action For A New Agent

Run:

```
uv run python -m signalflow examples/hub.yaml \
    --run-snippet snippets/algebraic/zone_invariants.py -- --zone 1,1
```

Then read `docs/worldscale_geometry.adoc` before modifying any solver code.
