"""World-size policy helpers for implicit SignalFlow grids.

This module is the single source of truth for deriving the number of
occupied world zones required by a circuit calling depth under the
current implicit-world policy.

Current policy:
    - depth layers are paired into one routing zone
    - even depth lands on the entry terminal of that zone
    - odd depth lands on the exit terminal of that zone
    - implicit worlds therefore need one occupied zone per two depth layers

FUTURE UPDATES:
    - This helper currently models only the simple implicit single-row or
      single-column world regime.
    - It does not derive rectangular implicit world shapes.
    - It does not decide how sparsely occupied explicit rectangular
      grids should be normalized, visualized, or truncated.
    - If world-shape policy evolves beyond depth-paired implicit worlds, update
      this module first and keep all callers delegated to it.
"""

from __future__ import annotations


def worldGridSize_calculate(callingDepth: int) -> int:
    """Calculate occupied world-zone count for one circuit calling depth.

    Args:
        callingDepth: Number of depth layers in the validated circuit.

    Returns:
        Number of occupied routing zones required by the current implicit-world
        policy.
    """

    if callingDepth <= 1:
        return 1
    return (callingDepth + 1) // 2
