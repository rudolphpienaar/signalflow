"""Board-domain invariant checks.

The board package needs a place where we can codify what counts as internally
coherent board geometry. The checks here are intentionally modest at first, but
they already protect two important principles:
- geometry ids and frames should line up by canonical region name
- exact terminal attach points should stay inside the board's overall frame
"""

from __future__ import annotations

from signalflow.board.board import Board


def boardProblems_get(board: Board) -> tuple[str, ...]:
    """Return human-readable invariant problems for one board.

    An empty tuple means the board passed the currently defined invariants.
    """

    problems: list[str] = []

    geometry = board.geometry
    regionFrameIds = set(geometry.regionFramesById.keys())
    regionIdIds = set(geometry.routingZoneRegionIdsById.keys())
    # Extra-geometry regions (EXTRA_LONGITUDE, EXTRA_LATITUDE, EXTRA_FAN,
    # EXTRA_TRANSITION, INTRA_EXTRA_TRANSFER) are board-domain constructs with
    # no kernel RoutingZoneRegionId counterpart. Only check the one-directional
    # invariant: every ID that has been registered must also have a frame.
    missingFrames = sorted(
        regionId.label_build() for regionId in (regionIdIds - regionFrameIds)
    )
    if missingFrames:
        problems.append(
            "Region ids missing frames for: " + ", ".join(missingFrames)
        )

    boardFrame = board.worldFrame
    minColumn, minRow = boardFrame.topLeft
    maxColumn, maxRow = boardFrame.bottomRight
    for (
        chipName,
        terminalPositions,
    ) in geometry.exactTerminalWorldPositionsByChip.items():
        for terminalName, (columnIndex, rowIndex) in terminalPositions.items():
            if not (
                minColumn <= columnIndex <= maxColumn
                and minRow <= rowIndex <= maxRow
            ):
                problems.append(
                    f"Terminal {chipName}.{terminalName} at ({columnIndex},{rowIndex}) "
                    "falls outside the board world frame"
                )

    return tuple(problems)
