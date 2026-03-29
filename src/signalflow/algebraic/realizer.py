"""Algebra-to-geometry realization for symbolic kernel routing.

This module intentionally does not solve routes. It consumes an existing
algebraic path plus invariant geometry and realizes that path onto the
substrate as exact world-coordinate spans and cells.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from signalflow.models import RoutingZoneRegionFrame


WorldPoint = tuple[int, int]
RealizerRouteInput = tuple[str, WorldPoint, WorldPoint]


@dataclass(frozen=True)
class AlgebraicRouteRealization:
    """Realized world geometry for one algebraic route.

    Attributes:
        tokenStartPoints: Ordered world-coordinate start points for the five
            non-endpoint algebraic tokens.
        routePoints: Ordered world-coordinate polyline points for the realized
            route spans.
        routeCells: Ordered adjacent world cells occupied by the realized
            route.
    """

    tokenStartPoints: tuple[WorldPoint, ...]
    routePoints: tuple[WorldPoint, ...]
    routeCells: tuple[WorldPoint, ...]


def regionFramesRelaxed_build(
    routeInputs: tuple[RealizerRouteInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    maxIterations: int = 8,
) -> dict[str, RoutingZoneRegionFrame]:
    """Return a geometry variant relaxed against symbolic route pressure.

    This operates only on a copied frame map. The original board geometry is
    never mutated.
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

    for _ in range(maxIterations):
        if currentScore == 0:
            break
        nextFrames = _regionFramesShifted_build(workingFrames)
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


def algebraicRouteRealization_build(
    algebraicPathText: str,
    sourceAttachPoint: WorldPoint,
    destinationAttachPoint: WorldPoint,
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
) -> AlgebraicRouteRealization:
    """Realize one algebraic path directly onto invariant geometry.

    Args:
        algebraicPathText: Canonical symbolic path text.
        sourceAttachPoint: World `(columnIndex, rowIndex)` source attach point.
        destinationAttachPoint: World `(columnIndex, rowIndex)` destination
            attach point.
        regionFramesByName: World geometry keyed by canonical region names.

    Returns:
        Exact realized token starts, route points, and route cells. Empty
        tuples are returned when the path or geometry cannot be realized.
    """

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
    """Calculate realization pressure from `nLat` vs return-home overlap."""

    usedNorthLaneIndices: set[int] = set()
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
            returnHomeRows.add(destinationAttachPoint[1])

    northLatFrame = regionFramesByName.get("north/intra_routing_latitude")
    if northLatFrame is None:
        return 0

    usedNorthRows = {
        northLatFrame.verticalStart + laneIndex - 1
        for laneIndex in usedNorthLaneIndices
    }
    return len(usedNorthRows.intersection(returnHomeRows))


def _regionFramesShifted_build(
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
) -> dict[str, RoutingZoneRegionFrame] | None:
    """Return a copy with dominant north-lat geometry shifted north by one."""

    requiredRegionNames = (
        "north/intra_routing_fan_in_out",
        "north/intra_routing_latitude",
        "west/intra_routing_transition:north",
        "east/intra_routing_transition:north",
    )
    if any(regionName not in regionFramesByName for regionName in requiredRegionNames):
        return None

    northFanFrame = regionFramesByName["north/intra_routing_fan_in_out"]
    northLatFrame = regionFramesByName["north/intra_routing_latitude"]
    if northLatFrame.verticalStart <= northFanFrame.verticalEnd_calculate():
        return None

    shiftedFrames = dict(regionFramesByName)
    for regionName in requiredRegionNames:
        frame = shiftedFrames[regionName]
        shiftedFrames[regionName] = RoutingZoneRegionFrame(
            horizontalStart=frame.horizontalStart,
            verticalStart=frame.verticalStart - 1,
            horizontalSpan=frame.horizontalSpan,
            verticalSpan=frame.verticalSpan,
        )
    return shiftedFrames




def _channelStartPointOrNone_build(
    channelToken: str,
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    referenceRowIndex: int,
) -> WorldPoint | None:
    """Return the world start point for one channel token.

    Args:
        channelToken: Channel token such as `wLong[3]` or `nLat[6]`.
        regionFramesByName: Geometry keyed by canonical region names.
        referenceRowIndex: Attach-point row used for longitude-token starts.

    Returns:
        World `(columnIndex, rowIndex)` token start when resolvable.
    """

    channelMatch = re.fullmatch(r"([a-zA-Z]+)\[(\d+)\]", channelToken)
    if channelMatch is None:
        return None

    channelName = channelMatch.group(1)
    laneIndex = int(channelMatch.group(2))

    if channelName == "wLong":
        frame = _firstRegionFrameOrNone_get(
            regionFramesByName,
            "west/intra_routing_longitude",
        )
        if frame is None or laneIndex > frame.horizontalSpan:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)
    if channelName == "eLong":
        frame = _firstRegionFrameOrNone_get(
            regionFramesByName,
            "east/intra_routing_longitude",
        )
        if frame is None or laneIndex > frame.horizontalSpan:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)
    if channelName == "nLat":
        frame = regionFramesByName.get("north/intra_routing_latitude")
        if frame is None or laneIndex > frame.verticalSpan:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)
    if channelName == "sLat":
        frame = regionFramesByName.get("south/intra_routing_latitude")
        if frame is None or laneIndex > frame.verticalSpan:
            return None
        return (frame.horizontalEnd_calculate() - 1, frame.verticalStart + laneIndex - 1)
    return None


def _firstRegionFrameOrNone_get(
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    baseName: str,
) -> RoutingZoneRegionFrame | None:
    """Return the first matching region frame for a base geometry key."""

    directFrame = regionFramesByName.get(baseName)
    if directFrame is not None:
        return directFrame
    for regionName in sorted(regionFramesByName):
        if regionName.startswith(f"{baseName}:"):
            return regionFramesByName[regionName]
    return None


def _routePoints_build(*points: WorldPoint) -> tuple[WorldPoint, ...]:
    """Return ordered route points with immediate duplicates removed."""

    routePointsMutable: list[WorldPoint] = []
    point: WorldPoint
    for point in points:
        if routePointsMutable and routePointsMutable[-1] == point:
            continue
        routePointsMutable.append(point)
    return tuple(routePointsMutable)


def _cellWalk_buildFromRoutePoints(
    routePoints: tuple[WorldPoint, ...],
) -> tuple[WorldPoint, ...]:
    """Expand route points into an adjacent world-cell walk."""

    if not routePoints:
        return tuple()

    cellWalkMutable: list[WorldPoint] = [routePoints[0]]
    point0: WorldPoint
    point1: WorldPoint
    for point0, point1 in zip(routePoints, routePoints[1:], strict=False):
        column0, row0 = point0
        column1, row1 = point1
        if column0 == column1 and row0 == row1:
            continue
        if column0 != column1 and row0 != row1:
            return tuple()
        if row0 == row1:
            step = 1 if column1 > column0 else -1
            for columnIndex in range(column0 + step, column1 + step, step):
                cellWalkMutable.append((columnIndex, row0))
        else:
            step = 1 if row1 > row0 else -1
            for rowIndex in range(row0 + step, row1 + step, step):
                cellWalkMutable.append((column0, rowIndex))
    return tuple(cellWalkMutable)
