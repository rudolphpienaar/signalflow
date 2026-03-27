# Next Agent Instructions

Read `ZEROSHOT.md` first, then `KERNEL-ROUTING-VISION.md`. Branch is
`rearch-zone-grid`, suite is 566/0, version is v5.9.1.

The next task is **chip-internal kernel** (PLAN.md item 8): replace the route
realization in `_chipInternalRoutePointsResult_build`
(`src/signalflow/routing/route.py`) with a kernel solve over the chip's own region
geometry. Directive parsing in `chip_solver.py` stays — only the route output
changes.

Before writing any code, read these files in full:
- `src/signalflow/routing/chip_solver.py`
- `src/signalflow/routing/route.py` (find `_chipInternalRoutePointsResult_build`)
- `src/signalflow/routing/kernel_solver.py`
- `examples/hub.yaml` (process() chip with internal wiring)

The key open design question: how do you construct a `RoutingKernel` region bundle
from a chip's bounding box? That derivation must be worked out before any
implementation begins.
