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
from signalflow.notation import AlgebraicPath, LaneSense, PathHop, sfN

RealizerRouteInput = tuple[str, WorldPoint, WorldPoint]
RealizerPathInput = tuple[
    AlgebraicPath, dict[sfN, int], WorldPoint, WorldPoint
]


def _requiredRegionKey_get(area: sfN) -> str:
    regionKey = area.region_key
    assert regionKey is not None
    return regionKey


def _requiredChannelName_get(area: sfN) -> str:
    channelName = area.channel_name
    assert channelName is not None
    return channelName


@dataclass(frozen=True)
class AlgebraicRouteRealization:
    """Realized world geometry for one algebraic route.

    Attributes:
        tokenStartPoints: Ordered world-coordinate start points for the
            non-endpoint algebraic tokens in the route.
        routePoints: Ordered orthogonal polyline points for the
            realized route.
        routeCells: Ordered adjacent world cells occupied by the
            realized route.
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

    The relaxation operates on a copied frame map. The caller's geometry is
    not mutated. This keeps board geometry as an input fact while still
    allowing the realization step to explore derived variants.
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
    for (
        algebraicPathText,
        sourceAttachPoint,
        destinationAttachPoint,
    ) in routeInputs:
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


def realizationPlan_buildFromPaths(
    routeInputs: tuple[RealizerPathInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    policy: BoardMaterializePolicy | None = None,
) -> BoardRealizationPlan:
    """Build a board-wide realization plan from structured algebraic inputs."""

    relaxedRegionFramesByName = regionFramesRelaxed_build(
        routeInputs=tuple(
            (
                _algebraicPathText_build(algebraicPath, laneMap),
                sourceAttachPoint,
                destinationAttachPoint,
            )
            for (
                algebraicPath,
                laneMap,
                sourceAttachPoint,
                destinationAttachPoint,
            ) in routeInputs
        ),
        regionFramesByName=regionFramesByName,
        policy=policy,
    )
    routeRealizationsByPathText: dict[str, AlgebraicRouteRealization] = {}
    for (
        algebraicPath,
        laneMap,
        sourceAttachPoint,
        destinationAttachPoint,
    ) in routeInputs:
        algebraicPathText = _algebraicPathText_build(algebraicPath, laneMap)
        routeRealizationsByPathText[algebraicPathText] = (
            algebraicRouteRealization_buildFromPath(
                algebraicPath=algebraicPath,
                laneMap=laneMap,
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

    parsedPath = _algebraicPathAndLaneMapFromText_build(algebraicPathText)
    if parsedPath is None:
        return AlgebraicRouteRealization(
            tokenStartPoints=(),
            routePoints=(),
            routeCells=(),
        )
    algebraicPath, laneMap = parsedPath
    return algebraicRouteRealization_buildFromPath(
        algebraicPath=algebraicPath,
        laneMap=laneMap,
        sourceAttachPoint=sourceAttachPoint,
        destinationAttachPoint=destinationAttachPoint,
        regionFramesByName=regionFramesByName,
    )


def algebraicRouteRealization_buildFromPath(
    algebraicPath: AlgebraicPath,
    laneMap: dict[sfN, int],
    sourceAttachPoint: WorldPoint,
    destinationAttachPoint: WorldPoint,
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
) -> AlgebraicRouteRealization:
    """Realize one structured algebraic path onto invariant geometry."""

    hops = algebraicPath.hops
    if len(hops) != 5:
        return AlgebraicRouteRealization(
            tokenStartPoints=(),
            routePoints=(),
            routeCells=(),
        )

    if (
        hops[0].laneSense is not LaneSense.FIXED
        or hops[4].laneSense is not LaneSense.FIXED
        or hops[1].laneSense is LaneSense.FIXED
        or hops[2].laneSense is LaneSense.FIXED
        or hops[3].laneSense is LaneSense.FIXED
    ):
        return AlgebraicRouteRealization(
            tokenStartPoints=(),
            routePoints=(),
            routeCells=(),
        )

    firstHop, firstChannelHop, middleChannelHop, thirdChannelHop, lastHop = (
        hops
    )
    firstChannelPoint = _channelStartPointOrNone_buildFromArea(
        channelArea=firstChannelHop.area,
        laneIndex=laneMap.get(firstChannelHop.area, 0),
        regionFramesByName=regionFramesByName,
        referenceRowIndex=sourceAttachPoint[1],
    )
    middleChannelPoint = _channelStartPointOrNone_buildFromArea(
        channelArea=middleChannelHop.area,
        laneIndex=laneMap.get(middleChannelHop.area, 0),
        regionFramesByName=regionFramesByName,
        referenceRowIndex=sourceAttachPoint[1],
    )
    thirdChannelPoint = _channelStartPointOrNone_buildFromArea(
        channelArea=thirdChannelHop.area,
        laneIndex=laneMap.get(thirdChannelHop.area, 0),
        regionFramesByName=regionFramesByName,
        referenceRowIndex=destinationAttachPoint[1],
    )
    if (
        firstChannelPoint is None
        or middleChannelPoint is None
        or thirdChannelPoint is None
    ):
        return AlgebraicRouteRealization(
            tokenStartPoints=(),
            routePoints=(),
            routeCells=(),
        )

    westFanFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Wfi))
    eastFanFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Efi))
    northLatFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ni))
    southLatFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Si))
    if (
        westFanFrame is None
        or eastFanFrame is None
        or northLatFrame is None
        or southLatFrame is None
    ):
        return AlgebraicRouteRealization(
            tokenStartPoints=(),
            routePoints=(),
            routeCells=(),
        )

    isForward = firstHop.area is sfN.Wfi and lastHop.area is sfN.Efi
    isReturn = firstHop.area is sfN.Efi and lastHop.area is sfN.Wfi
    if not (isForward or isReturn):
        return AlgebraicRouteRealization(
            tokenStartPoints=(),
            routePoints=(),
            routeCells=(),
        )

    if isForward:
        latitudeStartColumn = northLatFrame.horizontalStart
        if middleChannelHop.area is sfN.Si:
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
        if middleChannelHop.area is sfN.Ni:
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
    for (
        algebraicPathText,
        sourceAttachPoint,
        destinationAttachPoint,
    ) in routeInputs:
        pathTokens = algebraicPathText.split("::")
        if len(pathTokens) != 7:
            continue
        middleToken = pathTokens[3]
        firstToken = pathTokens[1]
        laneMatch = re.fullmatch(
            rf"{_requiredChannelName_get(sfN.Ni)}\[(\d+)\]",
            middleToken,
        )
        if (
            laneMatch is not None
            and firstToken == f"{_requiredChannelName_get(sfN.Wfi)}[0]"
        ):
            usedNorthLaneIndices.add(int(laneMatch.group(1)))
        if firstToken == f"{_requiredChannelName_get(sfN.Efi)}[0]":
            returnSourceRows.add(sourceAttachPoint[1])
            returnHomeRows.add(destinationAttachPoint[1])

    northLatFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ni))
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
        _requiredRegionKey_get(sfN.Nfi),
        _requiredRegionKey_get(sfN.Ni),
        "west/intra_routing_transition:north",
        "east/intra_routing_transition:north",
    )
    if not all(name in regionFramesByName for name in requiredRegionNames):
        return None

    northFanFrame = regionFramesByName[_requiredRegionKey_get(sfN.Nfi)]
    northLatFrame = regionFramesByName[_requiredRegionKey_get(sfN.Ni)]
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
    if policy.relaxationSymmetry is BoardRelaxationSymmetry.SYMMETRIC:
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


def UNUSED_channelStartPointOrNone_build(
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
    member = sfN.from_channel_name(channelName)
    if member is None:
        return None
    return _channelStartPointOrNone_buildFromArea(
        channelArea=member,
        laneIndex=laneIndex,
        regionFramesByName=regionFramesByName,
        referenceRowIndex=referenceRowIndex,
    )


def _channelStartPointOrNone_buildFromArea(
    *,
    channelArea: sfN,
    laneIndex: int,
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    referenceRowIndex: int,
) -> WorldPoint | None:
    """Return the start point of one structured channel hop in world space."""

    if laneIndex < 1:
        return None

    if channelArea is sfN.Wi:
        frame = regionFramesByName.get(
            _requiredRegionKey_get(sfN.Wi) + ":upper"
        ) or regionFramesByName.get(_requiredRegionKey_get(sfN.Wi))
        if frame is None:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)

    if channelArea is sfN.Ei:
        frame = regionFramesByName.get(
            _requiredRegionKey_get(sfN.Ei) + ":upper"
        ) or regionFramesByName.get(_requiredRegionKey_get(sfN.Ei))
        if frame is None:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)

    if channelArea is sfN.Ni:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ni))
        if frame is None:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)

    if channelArea is sfN.Si:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Si))
        if frame is None:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)

    return None


def _algebraicPathAndLaneMapFromText_build(
    algebraicPathText: str,
) -> tuple[AlgebraicPath, dict[sfN, int]] | None:
    """Parse compatibility text into a structured path plus lane map."""

    tokens = algebraicPathText.split("::")
    if len(tokens) < 3:
        return None
    source = tokens[0]
    sink = tokens[-1]
    hops: list[PathHop] = []
    laneMap: dict[sfN, int] = {}
    for token in tokens[1:-1]:
        laneMatch = re.fullmatch(r"([A-Za-z]+)\[(\d+)\]", token)
        if laneMatch is None:
            continue
        member = sfN.from_channel_name(laneMatch.group(1))
        if member is None:
            continue
        laneIndex = int(laneMatch.group(2))
        if laneIndex == 0:
            hops.append(PathHop(area=member, laneSense=LaneSense.FIXED))
            continue
        hops.append(PathHop(area=member, laneSense=LaneSense.FORWARD))
        laneMap[member] = laneIndex
    if not hops:
        return None
    return (
        AlgebraicPath(
            source=source,
            hops=tuple(hops),
            sink=sink,
        ),
        laneMap,
    )


def _algebraicPathText_build(
    algebraicPath: AlgebraicPath,
    laneMap: dict[sfN, int],
) -> str:
    """Serialize one structured path plus lane map to compatibility text."""

    parts: list[str] = [algebraicPath.source]
    for hop in algebraicPath.hops:
        token = hop.area.channel_name or ""
        if hop.laneSense is LaneSense.FIXED:
            parts.append(f"{token}[0]")
            continue
        parts.append(f"{token}[{laneMap.get(hop.area, 0)}]")
    parts.append(algebraicPath.sink)
    return "::".join(parts)


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
        return ()

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
            return ()
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
