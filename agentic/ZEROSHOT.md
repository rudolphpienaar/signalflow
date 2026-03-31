# Zero-Shot Handoff: SignalFlow Board Runtime And `extra` Routing

**Branch:** `worldscale-extra-routing`
**Commit:** `07c46b4`
**Version:** `5.9.8`

## Current Truth In One Screen

- The main active runtime is the board-era runtime, not the old kernel-only rearch notes.
- `chips.chip_get(...)` returns `BoardChip`.
- `chip.internalBoard_get()` returns `BoardKernel`.
- `kernel.board_get(chipPlacementPolicy=...)` returns `Board`.
- `solution.board_materialize(board, policy=...)` is the current materialization API.
- WTE board geometry is re-anchored from live placed terminal centroids before realization.
- `docs/worldscale_geometry.adoc` contains the next macro design direction.

## Most Important Current Files

- `docs/worldscale_geometry.adoc`
- `papers/new_ways.adoc`
- `snippets/algebraic/hub_internal_geometry.py`
- `snippets/algebraic/hub_internal_wiring.py`
- `src/signalflow/board/builders.py`
- `src/signalflow/board/realizer.py`
- `src/signalflow/routing/geometry.py`

## Current Design Direction

The next big idea is:

- keep `intra` as the inner local kernel substrate
- add concentric outer `extra` routing families
- connect `intra` and `extra` through explicit transfer regions

Do not reduce this to:

- seam objects
- extra placed kernels
- hand-wavy virtual-kernel prose

The unresolved hard case is child-to-self routing through `extra` while preserving enough local row/layer identity.

## First Action For A New Agent

Run or inspect:

- `snippets/algebraic/hub_internal_geometry.py`
- `snippets/algebraic/hub_internal_wiring.py`

Then continue `docs/worldscale_geometry.adoc` before modifying solver code.
