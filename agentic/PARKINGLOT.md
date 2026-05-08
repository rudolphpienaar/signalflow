# Parking Lot

## Full Board Overlap Integration

- All three overlap zones (`1,1`, `1,2`, `1,3`) now materialize correctly. Zone `1,3` collision resolved.
- The `1,2` / `1,3` seam now has shared chip-row vertical alignment in
  `world_zone_inspect.py`.
- Active world surfaces are `WorldGeometryResolver` and
  `BoardWorldMaterializedSolution`; `signalflow file.yaml` is the default
  full-world render path.
- Do not revive old seam/interconnect world rendering as the solution path.

## Module Boundary Conflation

- Current world geometry treats `module` ownership as a real layout envelope,
  not just source identity. That conflates source modules with geometry scopes.
- Example: the neural-network YAML with every chip in `neural-network.c` looked
  wrong because the engine had only one module boundary. Splitting ownership
  into `inputLayer.ts`, `hiddenLayer.ts`, and `outputLayer.ts` gave the
  harmonizer the intended geometric compartments.
- Correct doctrine:
  - `module` remains source/file identity.
  - call-stack depth layers become implicit geometry scopes.
  - geometry scopes can be non-drawable.
  - source module/file boxes become optional overlays or explicitly promoted
    structural groups.
- Next sprint should move this out of parking lot and into implementation.

## LLM Design Anchoring Failure Mode

- Recent miss: the engine already knows call-stack layers, but the proposed fix
  initially stayed anchored to explicit module boundaries.
- The intuitive leap is that call-stack depth can supply synthetic geometric
  boundaries for DAG/layer layouts when module boundaries are missing or too
  coarse.
- Corrected doctrine: do not reinterpret modules as depth layers. Add separate
  depth-layer geometry scopes instead.
- This belongs in the paper as an example where implementation-local doctrine
  suppressed a nearby topology-derived design inference.

## Relaxation Policy Semantics

- Current state: `BoardRelaxationSymmetry.MINIMAL` and
  `BoardRelaxationSymmetry.SYMMETRIC` are behaviorally identical for centroid
  spread.
- Why: centroid spread is now doctrinally paired and runs to completion, so
  `Ni` and `Si` always move together until zero merged-cell collisions or hard
  bounds.
- Revisit later:
  - decide whether `MINIMAL` should be removed
  - or repurposed to mean something else non-conflicting
  - update docs/runtime naming to match final doctrine

## Orphaned Terminal Remaining Cases

Partial fix landed in `routing/kernel_solver.py` (May 2026):
- `_destinationPortDeclarationOrNone_get` clamps `destinationPortIndex` to last
  valid port; prevents `None` return when multiple callers exceed chip port count.
- `_terminalBodyRow_get` uses `lastFound` fallback when `occurrenceBefore`
  exceeds available offsets.

Root cause addressed: multiple callers to same callee chip, `destinationPortIndex`
increments beyond chip's port count → `_obligationHasReturn_check` returned
`False` → no return route computed → orphaned stub.

Fixed in `back-and-forth.yaml`: `gc2().ggc2ret` now shows `╫` crossing.

**Still open**: `narrowed` orphan in real-world sftc-generated YAML. Other
cases may exist. Investigation needed:
- Is `narrowed` also a multiple-callers case?
- Or a canonical/display name mismatch in `destinationEndpointText`?
- Or a board endpoint attach-point lookup failure?

Do not close this item until sftc-generated YAML renders cleanly.

## Outer Routes Invisible To Centroid Solver

- Extra-ring fan regions (`Efe`, `Wfe`, `Nfe`, `Sfe`) have no `channel_name`
  in `_CHANNEL_NAMES` (sfn.py). Serialized as `[0]` → text parser rejects →
  empty realization → outer routes contribute zero cells to relaxation
  collision counting.
- Fix: add channel names (`"xef"`, `"xwf"`, `"xnf"`, `"xsf"`) so
  `_algebraicPathAndLaneMapFromText_build` can round-trip outer paths.
- Not the active blocker for the current world seam work; `world_zone_inspect.py`
  now shows the key `1,2` / `1,3` seam aligned by shared chip rows. This may
  still matter once outer route density increases.

## Intra Return South-Lane Semantics

- Investigate the impact of changing `WTE_INTRA_RETURN` `Si` `LaneSense`.
- Focus area:
  - possible collision or coupling effects against extra-band routes
  - especially where south intra return behavior may interact with outer
    south-band occupancy and realization order
- Revisit later before further return-lane doctrine changes.
