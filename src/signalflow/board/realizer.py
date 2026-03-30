"""Board-domain realization of algebraic routes onto board geometry.

This module is the canonical home for the realization step in the board-era
architecture.

The responsibilities here are intentionally narrow and strict:
- consume an already-solved algebraic route
- consume invariant board geometry
- realize the route onto that geometry as exact world-coordinate starts,
  spans, and occupied cells

This module does not solve routes. It does not choose channels. It does not
search for alternatives. It only maps an existing algebraic solution onto the
board substrate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from signalflow.board.doctrine import (
    BoardMaterializePolicy,
    BoardRelaxationSymmetry,
)
from signalflow.board.types import WorldPoint
from signalflow.models import RoutingZoneRegionFrame

RealizerRouteInput = tuple[str, WorldPoint, WorldPoint]


@dataclass(frozen=True)
class AlgebraicRouteRealization:
    """Realized world geometry for one algebraic route.

    Attributes:
        tokenStartPoints: Ordered world-coordinate start points for the
            non-endpoint algebraic tokens in the route.
        routePoints: Ordered orthogonal polyline points for the realized route.
        routeCells: Ordered adjacent world cells occupied by the realized route.
    """

    tokenStartPoints: tuple[WorldPoint, ...]
    routePoints: tuple[WorldPoint, ...]
    routeCells: tuple[WorldPoint, ...]


@dataclass(frozen=True)
class BoardRealizationPlan:
    """Board-wide realization result for a solved algebraic route set.

    Attributes:
        regionFramesByName: Possibly relaxed geometry used for realization.
        routeRealizationsByPathText: Per-path realized geometry keyed by the
            exact algebraic path text.
    """

    regionFramesByName: dict[str, RoutingZoneRegionFrame]
    routeRealizationsByPathText: dict[str, AlgebraicRouteRealization]


def regionFramesRelaxed_build(
    routeInputs: tuple[RealizerRouteInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    policy: BoardMaterializePolicy | None = None,
    maxIterations: int = 8,
) -> dict[str, RoutingZoneRegionFrame]:
    """Return a geometry variant relaxed against symbolic route pressure.

    The relaxation operates on a copied frame map. The caller's geometry is not
    mutated. This keeps board geometry as an input fact while still allowing the
    realization step to explore derived variants.
    """

    workingFrames = {
        regionName: RoutingZoneRegionFrame(
            horizontalStart=frame.horizontalStart,
            verticalStart=frame.verticalStart,
            horizontalSpan=frame.horizontalSpan,
            verticalSpan=frame.verticalSpan,
        )
        for regionName, frame in regionFramesByName.items()
    }
    bestFrames = dict(workingFrames)
    bestScore = _geometryPressureScore_calculate(routeInputs, bestFrames)
    currentScore = bestScore
    activePolicy = policy or BoardMaterializePolicy()

    for _ in range(maxIterations):
        if currentScore == 0:
            break
        nextFrames = _regionFramesShifted_build(
            workingFrames,
            routeInputs=routeInputs,
            policy=activePolicy,
        )
        if nextFrames is None:
            break
        nextScore = _geometryPressureScore_calculate(routeInputs, nextFrames)
        if nextScore > currentScore:
            break
        workingFrames = nextFrames
        currentScore = nextScore
        if nextScore <= bestScore:
            bestFrames = dict(nextFrames)
            bestScore = nextScore
    return bestFrames


def realizationPlan_build(
    routeInputs: tuple[RealizerRouteInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    policy: BoardMaterializePolicy | None = None,
) -> BoardRealizationPlan:
    """Build a board-wide realization plan from solved algebraic route inputs.

    This is the board-domain orchestration step for realization:
    - relax geometry if needed
    - realize each algebraic route against that geometry
    - return both the geometry variant and the per-route realizations
    """

    relaxedRegionFramesByName = regionFramesRelaxed_build(
        routeInputs=routeInputs,
        regionFramesByName=regionFramesByName,
        policy=policy,
    )
    routeRealizationsByPathText: dict[str, AlgebraicRouteRealization] = {}
    for algebraicPathText, sourceAttachPoint, destinationAttachPoint in routeInputs:
        routeRealizationsByPathText[algebraicPathText] = (
            algebraicRouteRealization_build(
                algebraicPathText=algebraicPathText,
                sourceAttachPoint=sourceAttachPoint,
                destinationAttachPoint=destinationAttachPoint,
                regionFramesByName=relaxedRegionFramesByName,
            )
        )
    return BoardRealizationPlan(
        regionFramesByName=relaxedRegionFramesByName,
        routeRealizationsByPathText=routeRealizationsByPathText,
    )


def algebraicRouteRealization_build(
    algebraicPathText: str,
    sourceAttachPoint: WorldPoint,
    destinationAttachPoint: WorldPoint,
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
) -> AlgebraicRouteRealization:
    """Realize one algebraic path directly onto invariant board geometry."""

    pathTokens = algebraicPathText.split("::")
    if len(pathTokens) != 7:
        return AlgebraicRouteRealization(
            tokenStartPoints=tuple(),
            routePoints=tuple(),
            routeCells=tuple(),
        )

    firstToken = pathTokens[1]
    firstChannelToken = pathTokens[2]
    middleChannelToken = pathTokens[3]
    thirdChannelToken = pathTokens[4]
    lastToken = pathTokens[5]

    firstChannelPoint = _channelStartPointOrNone_build(
        channelToken=firstChannelToken,
        regionFramesByName=regionFramesByName,
        referenceRowIndex=sourceAttachPoint[1],
    )
    middleChannelPoint = _channelStartPointOrNone_build(
        channelToken=middleChannelToken,
        regionFramesByName=regionFramesByName,
        referenceRowIndex=sourceAttachPoint[1],
    )
    thirdChannelPoint = _channelStartPointOrNone_build(
        channelToken=thirdChannelToken,
        regionFramesByName=regionFramesByName,
        referenceRowIndex=destinationAttachPoint[1],
    )
    if (
        firstChannelPoint is None
        or middleChannelPoint is None
        or thirdChannelPoint is None
    ):
        return AlgebraicRouteRealization(
            tokenStartPoints=tuple(),
            routePoints=tuple(),
            routeCells=tuple(),
        )

    westFanFrame = regionFramesByName.get("west/intra_routing_fan_in_out")
    eastFanFrame = regionFramesByName.get("east/intra_routing_fan_in_out")
    northLatFrame = regionFramesByName.get("north/intra_routing_latitude")
    southLatFrame = regionFramesByName.get("south/intra_routing_latitude")
    if (
        westFanFrame is None
        or eastFanFrame is None
        or northLatFrame is None
        or southLatFrame is None
    ):
        return AlgebraicRouteRealization(
            tokenStartPoints=tuple(),
            routePoints=tuple(),
            routeCells=tuple(),
        )

    isForward = firstToken == "wf[0]" and lastToken == "ef[0]"
    isReturn = firstToken == "ef[0]" and lastToken == "wf[0]"
    if not (isForward or isReturn):
        return AlgebraicRouteRealization(
            tokenStartPoints=tuple(),
            routePoints=tuple(),
            routeCells=tuple(),
        )

    if isForward:
        latitudeStartColumn = northLatFrame.horizontalStart
        if middleChannelToken.startswith("sLat"):
            latitudeStartColumn = southLatFrame.horizontalStart
        westFanExitColumn = westFanFrame.horizontalEnd_calculate()
        eastFanEntryColumn = eastFanFrame.horizontalStart
        tokenStartPoints = (
            sourceAttachPoint,
            firstChannelPoint,
            (latitudeStartColumn, middleChannelPoint[1]),
            (thirdChannelPoint[0], middleChannelPoint[1]),
            (eastFanEntryColumn, destinationAttachPoint[1]),
        )
        routePoints = _routePoints_build(
            sourceAttachPoint,
            (westFanExitColumn, sourceAttachPoint[1]),
            firstChannelPoint,
            (firstChannelPoint[0], middleChannelPoint[1]),
            (latitudeStartColumn, middleChannelPoint[1]),
            (thirdChannelPoint[0], middleChannelPoint[1]),
            (thirdChannelPoint[0], destinationAttachPoint[1]),
            (eastFanEntryColumn, destinationAttachPoint[1]),
            destinationAttachPoint,
        )
    else:
        latitudeEndColumn = southLatFrame.horizontalEnd_calculate() - 1
        if middleChannelToken.startswith("nLat"):
            latitudeEndColumn = northLatFrame.horizontalEnd_calculate() - 1
        eastFanEntryColumn = eastFanFrame.horizontalStart
        westFanExitColumn = westFanFrame.horizontalEnd_calculate()
        tokenStartPoints = (
            sourceAttachPoint,
            firstChannelPoint,
            (latitudeEndColumn, middleChannelPoint[1]),
            (thirdChannelPoint[0], middleChannelPoint[1]),
            (westFanExitColumn, destinationAttachPoint[1]),
        )
        routePoints = _routePoints_build(
            sourceAttachPoint,
            (eastFanEntryColumn, sourceAttachPoint[1]),
            firstChannelPoint,
            (firstChannelPoint[0], middleChannelPoint[1]),
            (latitudeEndColumn, middleChannelPoint[1]),
            (thirdChannelPoint[0], middleChannelPoint[1]),
            (thirdChannelPoint[0], destinationAttachPoint[1]),
            (westFanExitColumn, destinationAttachPoint[1]),
            destinationAttachPoint,
        )

    return AlgebraicRouteRealization(
        tokenStartPoints=tokenStartPoints,
        routePoints=routePoints,
        routeCells=_cellWalk_buildFromRoutePoints(routePoints),
    )


def _geometryPressureScore_calculate(
    routeInputs: tuple[RealizerRouteInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
) -> int:
    """Calculate realization pressure from top-latitude overlap risks.

    The board-era realization keeps the algebraic path fixed and is allowed to
    relax the north family upward when the top travel rows collide with rows
    already claimed by top-edge return peels or return-home destinations.
    """

    usedNorthLaneIndices: set[int] = set()
    returnSourceRows: set[int] = set()
    returnHomeRows: set[int] = set()
    for algebraicPathText, sourceAttachPoint, destinationAttachPoint in routeInputs:
        pathTokens = algebraicPathText.split("::")
        if len(pathTokens) != 7:
            continue
        middleToken = pathTokens[3]
        firstToken = pathTokens[1]
        laneMatch = re.fullmatch(r"nLat\[(\d+)\]", middleToken)
        if laneMatch is not None and firstToken == "wf[0]":
            usedNorthLaneIndices.add(int(laneMatch.group(1)))
        if firstToken == "ef[0]":
            returnSourceRows.add(sourceAttachPoint[1])
            returnHomeRows.add(destinationAttachPoint[1])

    northLatFrame = regionFramesByName.get("north/intra_routing_latitude")
    if northLatFrame is None:
        return 0

    usedNorthRows = {
        northLatFrame.verticalStart + laneIndex - 1
        for laneIndex in usedNorthLaneIndices
    }
    return len(
        usedNorthRows.intersection(returnHomeRows.union(returnSourceRows))
    )


def _regionFramesShifted_build(
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    routeInputs: tuple[RealizerRouteInput, ...],
    policy: BoardMaterializePolicy,
) -> dict[str, RoutingZoneRegionFrame] | None:
    """Return a copy with dominant north-lat geometry shifted north by one."""

    requiredRegionNames = (
        "north/intra_routing_fan_in_out",
        "north/intra_routing_latitude",
        "west/intra_routing_transition:north",
        "east/intra_routing_transition:north",
    )
    if not all(name in regionFramesByName for name in requiredRegionNames):
        return None

    northFanFrame = regionFramesByName["north/intra_routing_fan_in_out"]
    northLatFrame = regionFramesByName["north/intra_routing_latitude"]
    if northLatFrame.verticalStart <= northFanFrame.verticalEnd_calculate():
        return None

    shiftedFrames = dict(regionFramesByName)
    for regionName in requiredRegionNames:
        frame = regionFramesByName[regionName]
        shiftedFrames[regionName] = RoutingZoneRegionFrame(
            horizontalStart=frame.horizontalStart,
            verticalStart=frame.verticalStart - 1,
            horizontalSpan=frame.horizontalSpan,
            verticalSpan=frame.verticalSpan,
        )
    if (
        policy.relaxationSymmetry is BoardRelaxationSymmetry.SYMMETRIC
        and _pairedLatitudeAxisAlignedCheck(
            routeInputs=routeInputs,
            regionFramesByName=regionFramesByName,
        )
    ):
        symmetricRegionNames = (
            "south/intra_routing_fan_in_out",
            "south/intra_routing_latitude",
            "west/intra_routing_transition:south",
            "east/intra_routing_transition:south",
        )
        if all(name in regionFramesByName for name in symmetricRegionNames):
            for regionName in symmetricRegionNames:
                frame = regionFramesByName[regionName]
                shiftedFrames[regionName] = RoutingZoneRegionFrame(
                    horizontalStart=frame.horizontalStart,
                    verticalStart=frame.verticalStart + 1,
                    horizontalSpan=frame.horizontalSpan,
                    verticalSpan=frame.verticalSpan,
                )
    return shiftedFrames


def _pairedLatitudeAxisAlignedCheck(
    *,
    routeInputs: tuple[RealizerRouteInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    toleranceRows: int = 1,
) -> bool:
    """Return whether the board's latitude-pair axis matches live attach rows.

    Symmetric relaxation is only trustworthy when the current board geometry
    already exposes a believable north/south axis for the placed chips. The
    adapter-era board builder still imports substrate latitude bands from the
    legacy kernel, so some boards carry a stale axis after chip-placement
    policy shifts.

    This guard keeps `SYMMETRIC` from applying mirrored band motion around a
    geometry axis that is visibly unrelated to the placed chip terminals. When
    that axis is stale, the honest fallback is the minimal one-sided shift.

    Args:
        routeInputs: Solved route inputs with live source/destination attach
            rows.
        regionFramesByName: Current region geometry used for realization.
        toleranceRows: Maximum acceptable difference between the live attach-row
            centroid and the current latitude-pair centroid.

    Returns:
        `True` when the current latitude-pair axis is close enough to the live
        terminal centroid to support mirrored movement. Otherwise `False`.
    """

    northLatFrame = regionFramesByName.get("north/intra_routing_latitude")
    southLatFrame = regionFramesByName.get("south/intra_routing_latitude")
    if northLatFrame is None or southLatFrame is None:
        return False

    attachRows: list[int] = []
    for _, sourceAttachPoint, destinationAttachPoint in routeInputs:
        attachRows.append(sourceAttachPoint[1])
        attachRows.append(destinationAttachPoint[1])
    if not attachRows:
        return False

    liveAttachRowCentroid = sum(attachRows) / len(attachRows)
    northCentroid = (
        northLatFrame.verticalStart
        + (northLatFrame.verticalSpan - 1) / 2
    )
    southCentroid = (
        southLatFrame.verticalStart
        + (southLatFrame.verticalSpan - 1) / 2
    )
    pairedLatitudeCentroid = (northCentroid + southCentroid) / 2

    return abs(liveAttachRowCentroid - pairedLatitudeCentroid) <= toleranceRows


def _channelStartPointOrNone_build(
    *,
    channelToken: str,
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    referenceRowIndex: int,
) -> WorldPoint | None:
    """Return the start point of one symbolic channel token in world space."""

    laneMatch = re.fullmatch(r"([A-Za-z]+)\[(\d+)\]", channelToken)
    if laneMatch is None:
        return None

    channelName = laneMatch.group(1)
    laneIndex = int(laneMatch.group(2))

    if channelName == "wLong":
        frame = (
            regionFramesByName.get("west/intra_routing_longitude:upper")
            or regionFramesByName.get("west/intra_routing_longitude")
        )
        if frame is None:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)

    if channelName == "eLong":
        frame = (
            regionFramesByName.get("east/intra_routing_longitude:upper")
            or regionFramesByName.get("east/intra_routing_longitude")
        )
        if frame is None:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)

    if channelName == "nLat":
        frame = regionFramesByName.get("north/intra_routing_latitude")
        if frame is None:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)

    if channelName == "sLat":
        frame = regionFramesByName.get("south/intra_routing_latitude")
        if frame is None:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)

    return None


def _routePoints_build(*points: WorldPoint) -> tuple[WorldPoint, ...]:
    """Return a deduplicated ordered route-point tuple."""

    routePoints: list[WorldPoint] = []
    for point in points:
        if routePoints and routePoints[-1] == point:
            continue
        routePoints.append(point)
    return tuple(routePoints)


def _cellWalk_buildFromRoutePoints(
    routePoints: tuple[WorldPoint, ...],
) -> tuple[WorldPoint, ...]:
    """Rasterize orthogonal route segments into adjacent occupied cells."""

    if len(routePoints) < 2:
        return tuple()

    cells: list[WorldPoint] = []
    previousPoint: WorldPoint | None = None
    for point in routePoints:
        if previousPoint is None:
            cells.append(point)
            previousPoint = point
            continue

        column0, row0 = previousPoint
        column1, row1 = point
        if column0 != column1 and row0 != row1:
            return tuple()
        if column0 == column1:
            rowStep = 1 if row1 >= row0 else -1
            for rowIndex in range(row0 + rowStep, row1 + rowStep, rowStep):
                cells.append((column0, rowIndex))
        else:
            columnStep = 1 if column1 >= column0 else -1
            for columnIndex in range(
                column0 + columnStep,
                column1 + columnStep,
                columnStep,
            ):
                cells.append((columnIndex, row0))
        previousPoint = point
    return tuple(cells)
