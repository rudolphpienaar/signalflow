"""World-size policy helpers for implicit SignalFlow grids.

This module is the single source of truth for deriving the number of
occupied world zones required by a circuit calling depth under the
current implicit-world policy.

Current policy (overlapping / transition model):
    - each adjacent pair of depth layers (d, d+1) occupies one routing zone
    - depth d lands on the west terminal of zone d (as caller)
    - depth d+1 lands on the east terminal of zone d (as callee)
    - a circuit with N depth bands therefore requires N-1 zones

    For N=1: 1 zone (degenerate single-depth circuit).
    For N=4: 3 zones — one per transition: 0→1, 1→2, 2→3.

FUTURE UPDATES:
    - This helper currently models only the simple implicit single-row or
      single-column world regime.
    - It does not derive rectangular implicit world shapes.
    - It does not decide how sparsely occupied explicit rectangular
      grids should be normalized, visualized, or truncated.
    - If world-shape policy evolves beyond the overlapping transition model,
      update this module first and keep all callers delegated to it.
"""

from __future__ import annotations


def worldGridSize_calculate(callingDepth: int) -> int:
    """Calculate occupied world-zone count for one circuit calling depth.

    Uses the overlapping transition model: one zone per adjacent depth-band
    pair, so N depth bands require N-1 zones.

    Args:
        callingDepth: Number of depth layers in the validated circuit.

    Returns:
        Number of occupied routing zones required by the current implicit-world
        policy.
    """

    if callingDepth <= 1:
        return 1
    return callingDepth - 1
