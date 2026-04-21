# Parking Lot

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
