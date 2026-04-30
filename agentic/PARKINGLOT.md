# Parking Lot

## Full Board Overlap Integration

- All three overlap zones (`1,1`, `1,2`, `1,3`) now materialize correctly. Zone `1,3` collision resolved.
- The `1,2` / `1,3` seam now has shared chip-row vertical alignment in
  `world_zone_inspect.py`.
- Active world surfaces are `WorldGeometryResolver` and
  `BoardWorldMaterializedSolution`; remaining work is production context/YAML
  assembly above the snippet.
- Do not revive old seam/interconnect world rendering as the solution path.

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
