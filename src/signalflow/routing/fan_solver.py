"""Universal fan-out and terminal centering logic for SignalFlow.

This module provides the "Fan Intelligence" required to connect a tight
monotone ribbon (longitudes) to a sparse or non-sparse set of terminals
(the wall).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FanAssignment:
    """Explicit lane-to-row assignment for one side of a fan."""
    laneIndex: int
    rowIndex: int
    peelColumnIndex: int

def fanAssignments_build(
    terminalRows: Sequence[int],
    laneIndices: Sequence[int],
    fanColumnStart: int,
    fanColumnSpan: int,
    isWestSide: bool = True,
) -> tuple[FanAssignment, ...]:
    """Build a non-colliding set of fan assignments.

    Args:
        terminalRows: The target rows on the chip/boundary wall.
        laneIndices: The source lane indices in the longitude band.
        fanColumnStart: The horizontal start of the fan region.
        fanColumnSpan: The horizontal span of the fan region.
        isWestSide: True if we are on the west side of the travel band.

    Returns:
        Ordered assignments connecting lanes to rows.
    """
    if not terminalRows or not laneIndices:
        return ()

    assignments = []

    # PEEL COLUMN LOGIC:
    # To avoid routing under labels or along module boxes, peel columns
    # must be allocated from the "outer" edge of the fan region towards
    # the "inner" edge, ensuring they stay in the dedicated fan corridor.

    for i, (lane, row) in enumerate(zip(laneIndices, terminalRows)):
        # Calculate peel column.
        # On the West side (Chip is East of fan), peel columns are on the far left.
        # On the East side (Chip is West of fan), peel columns are on the far right.
        if isWestSide:
            # West fan: peel off from the outer edge (left)
            peel = fanColumnStart + i
        else:
            # East fan: peel off from the outer edge (right)
            # fanColumnStart + fanColumnSpan is the boundary.
            peel = fanColumnStart + (fanColumnSpan - 1 - i)

        assignments.append(FanAssignment(
            laneIndex=lane,
            rowIndex=row,
            peelColumnIndex=peel
        ))

    return tuple(assignments)

def sparseWallCenteringRows_calculate(
    totalWallRows: int,
    requiredCount: int,
    wallStartRow: int,
) -> tuple[int, ...]:
    """Calculate centered rows for a sparse wall (e.g. 10 wires into 50 rows)."""
    if requiredCount <= 0:
        return ()

    # Standard centering logic: find the middle of the wall and spread out.
    middle = wallStartRow + (totalWallRows // 2)
    start = middle - (requiredCount // 2)
    # Ensure signal/return pairs are kept together (even starting row)
    if start % 2 != 0:
        start += 1

    return tuple(range(start, start + requiredCount))
