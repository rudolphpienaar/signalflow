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

from signalflow.board.doctrine import BoardMaterializePolicy
from signalflow.board.geometry.expr import GeometryAxis
from signalflow.board.types import WorldPoint
from signalflow.models import RoutingZoneRegionFrame, result_isOkCheck
from signalflow.models.zone_route import RoutingZoneRoutePoint
from signalflow.notation import AlgebraicPath, LaneSense, PathHop, sfN
from signalflow.routing.route import RealizedRouteSet, routePoints_realize

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


class AlgebraicRouteRealizationFactory:
    """Shared structured-path realizer for board-domain route families.

    This factory owns the path-shape validation and the geometry-derived
    dispatch needed to realize intra, extra, and medial five-hop routes
    without duplicating one branch per named topology.
    """

    @classmethod
    def realization_build(
        cls,
        *,
        algebraicPath: AlgebraicPath,
        laneMap: dict[sfN, int],
        sourceAttachPoint: WorldPoint,
        destinationAttachPoint: WorldPoint,
        regionFramesByName: dict[str, RoutingZoneRegionFrame],
    ) -> AlgebraicRouteRealization:
        """Build one route realization from a structured five-hop path."""

        hops = algebraicPath.hops
        if not cls._supportedPath_isCheck(hops):
            return cls._empty_build()

        (
            firstHop,
            firstChannelHop,
            middleChannelHop,
            thirdChannelHop,
            lastHop,
        ) = hops
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
        sourceFanFrame = cls._fanFrameOrNone_get(
            fanArea=firstHop.area,
            regionFramesByName=regionFramesByName,
        )
        destinationFanFrame = cls._fanFrameOrNone_get(
            fanArea=lastHop.area,
            regionFramesByName=regionFramesByName,
        )
        latitudeFrame = regionFramesByName.get(
            _requiredRegionKey_get(middleChannelHop.area)
        )
        if (
            firstChannelPoint is None
            or middleChannelPoint is None
            or thirdChannelPoint is None
            or sourceFanFrame is None
            or destinationFanFrame is None
            or latitudeFrame is None
        ):
            return cls._empty_build()

        sourceFanBoundaryColumn = cls._fanBoundaryColumn_get(
            fanFrame=sourceFanFrame,
            channelPoint=firstChannelPoint,
        )
        destinationFanBoundaryColumn = cls._fanBoundaryColumn_get(
            fanFrame=destinationFanFrame,
            channelPoint=thirdChannelPoint,
        )
        latitudeBoundaryColumn = cls._latitudeBoundaryColumn_get(
            latitudeArea=middleChannelHop.area,
            latitudeFrame=latitudeFrame,
            firstChannelPoint=firstChannelPoint,
            thirdChannelPoint=thirdChannelPoint,
        )

        tokenStartPoints = (
            sourceAttachPoint,
            firstChannelPoint,
            (latitudeBoundaryColumn, middleChannelPoint[1]),
            (thirdChannelPoint[0], middleChannelPoint[1]),
            (destinationFanBoundaryColumn, destinationAttachPoint[1]),
        )
        routePoints = _routePoints_build(
            sourceAttachPoint,
            (sourceFanBoundaryColumn, sourceAttachPoint[1]),
            firstChannelPoint,
            (firstChannelPoint[0], middleChannelPoint[1]),
            (latitudeBoundaryColumn, middleChannelPoint[1]),
            (thirdChannelPoint[0], middleChannelPoint[1]),
            (thirdChannelPoint[0], destinationAttachPoint[1]),
            (destinationFanBoundaryColumn, destinationAttachPoint[1]),
            destinationAttachPoint,
        )
        return AlgebraicRouteRealization(
            tokenStartPoints=tokenStartPoints,
            routePoints=routePoints,
            routeCells=_cellWalk_buildFromRoutePoints(routePoints),
        )

    @staticmethod
    def _empty_build() -> AlgebraicRouteRealization:
        """Return the canonical empty realization."""

        return AlgebraicRouteRealization(
            tokenStartPoints=(),
            routePoints=(),
            routeCells=(),
        )

    @staticmethod
    def _supportedPath_isCheck(hops: tuple[PathHop, ...]) -> bool:
        """Return whether the hop tuple matches supported five-hop doctrine."""

        if len(hops) != 5:
            return False
        return (
            hops[0].laneSense is LaneSense.FIXED
            and hops[4].laneSense is LaneSense.FIXED
            and hops[1].laneSense is not LaneSense.FIXED
            and hops[2].laneSense is not LaneSense.FIXED
            and hops[3].laneSense is not LaneSense.FIXED
            and hops[0].area.region_key is not None
            and hops[4].area.region_key is not None
            and hops[2].area.axis_get() is GeometryAxis.VERTICAL
        )

    @staticmethod
    def _fanFrameOrNone_get(
        *,
        fanArea: sfN,
        regionFramesByName: dict[str, RoutingZoneRegionFrame],
    ) -> RoutingZoneRegionFrame | None:
        """Return the explicit fan frame for a fixed first/last hop."""

        regionKey = fanArea.region_key
        if regionKey is None:
            return None
        return regionFramesByName.get(regionKey)

    @staticmethod
    def _fanBoundaryColumn_get(
        *,
        fanFrame: RoutingZoneRegionFrame,
        channelPoint: WorldPoint,
    ) -> int:
        """Return the fan/channel boundary column nearest one channel point."""

        if channelPoint[0] < fanFrame.horizontalStart:
            return fanFrame.horizontalStart
        return fanFrame.horizontalEnd_calculate()

    @staticmethod
    def _latitudeBoundaryColumn_get(
        *,
        latitudeArea: sfN,
        latitudeFrame: RoutingZoneRegionFrame,
        firstChannelPoint: WorldPoint,
        thirdChannelPoint: WorldPoint,
    ) -> int:
        """Return the latitude-entry column matching route travel direction."""

        if (
            latitudeArea in {sfN.Ne, sfN.Se}
        ):
            return firstChannelPoint[0]
        if thirdChannelPoint[0] >= firstChannelPoint[0]:
            return latitudeFrame.horizontalStart
        return latitudeFrame.horizontalEnd_calculate() - 1


def regionFramesRelaxed_build(
    routeInputs: tuple[RealizerRouteInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    policy: BoardMaterializePolicy | None = None,
    maxIterations: int = 128,
) -> dict[str, RoutingZoneRegionFrame]:
    """Return a geometry variant relaxed against realized route collisions.

    The relaxation operates on a copied frame map. The caller's geometry is
    not mutated. This keeps board geometry as an input fact while still
    allowing the realization step to explore derived variants.

    Centroid spread is paired and runs to completion:
    - `Ni` moves north while `Si` moves south
    - the corresponding W/E transition bands move with them
    - `Nfi` / `Sfi` remain fixed and therefore define the hard boundaries
    - the loop continues until realized collisions reach zero or no further
      legal paired spread remains
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
    bestScore = _realizedCollisionCount_calculate(routeInputs, bestFrames)
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
        nextScore = _realizedCollisionCount_calculate(routeInputs, nextFrames)
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
    return AlgebraicRouteRealizationFactory.realization_build(
        algebraicPath=algebraicPath,
        laneMap=laneMap,
        sourceAttachPoint=sourceAttachPoint,
        destinationAttachPoint=destinationAttachPoint,
        regionFramesByName=regionFramesByName,
    )


def _realizedCollisionCount_calculate(
    routeInputs: tuple[RealizerRouteInput, ...],
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
) -> int:
    """Return the count of realized shared cells with 3+ track directions.

    This intentionally measures the visible merged-cell congestion that the
    user sees in the rendered board, including transition-region tees/crosses.
    Fan regions are exempt because fan sharing is expected bundle behavior.
    """

    realizedRoutes = []
    routeIndex: int
    for routeIndex, (
        algebraicPathText,
        sourceAttachPoint,
        destinationAttachPoint,
    ) in enumerate(routeInputs):
        realization = algebraicRouteRealization_build(
            algebraicPathText=algebraicPathText,
            sourceAttachPoint=sourceAttachPoint,
            destinationAttachPoint=destinationAttachPoint,
            regionFramesByName=regionFramesByName,
        )
        routePoints = tuple(
            RoutingZoneRoutePoint(
                horizontalIndex=columnIndex,
                verticalIndex=rowIndex,
            )
            for columnIndex, rowIndex in realization.routePoints
        )
        if len(routePoints) < 2:
            continue
        realizedRouteResult = routePoints_realize(
            sourceChipRef=_syntheticChipRef_build(routeIndex, "src"),
            destinationChipRef=_syntheticChipRef_build(routeIndex, "dst"),
            childCallIndex=routeIndex,
            routePoints=routePoints,
        )
        if not result_isOkCheck(realizedRouteResult):
            continue
        realizedRoutes.append(realizedRouteResult.value)

    mergedCellMap = RealizedRouteSet(
        realizedRoutes=tuple(realizedRoutes)
    ).mergedCellMap_get()
    collisionCount = 0
    for (rowIndex, columnIndex), trackCell in mergedCellMap.items():
        if len(trackCell.directions) <= 2:
            continue
        if _fanCell_isCheck(
            columnIndex=columnIndex,
            rowIndex=rowIndex,
            regionFramesByName=regionFramesByName,
        ):
            continue
        collisionCount += 1
    return collisionCount


def _fanCell_isCheck(
    *,
    columnIndex: int,
    rowIndex: int,
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
) -> bool:
    """Return whether a world cell lies inside any fan-in/out region."""

    for regionName, frame in regionFramesByName.items():
        if "fan_in_out" not in regionName:
            continue
        if (
            frame.horizontalStart
            <= columnIndex
            < frame.horizontalEnd_calculate()
            and frame.verticalStart
            <= rowIndex
            < frame.verticalEnd_calculate()
        ):
            return True
    return False


def _syntheticChipRef_build(
    routeIndex: int,
    suffix: str,
):
    """Return a stable placeholder chip ref for temporary route realization."""

    from signalflow.models.chip import ChipId, ChipRef

    return ChipRef(
        chipId=ChipId(
            moduleName=f"relax_{routeIndex}_{suffix}",
            functionName="tmp",
        )
    )


def _regionFramesShifted_build(
    regionFramesByName: dict[str, RoutingZoneRegionFrame],
    routeInputs: tuple[RealizerRouteInput, ...],
    policy: BoardMaterializePolicy,
) -> dict[str, RoutingZoneRegionFrame] | None:
    """Return a copy with one paired centroid spread step applied."""

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
    southFanFrame = regionFramesByName["south/intra_routing_fan_in_out"]
    southLatFrame = regionFramesByName[_requiredRegionKey_get(sfN.Si)]
    if northLatFrame.verticalStart <= northFanFrame.verticalEnd_calculate():
        return None
    if southLatFrame.verticalEnd_calculate() >= southFanFrame.verticalStart:
        return None

    shiftedFrames = dict(regionFramesByName)
    northShiftRegionNames = (
        _requiredRegionKey_get(sfN.Ni),
        "west/intra_routing_transition:north",
        "east/intra_routing_transition:north",
    )
    for regionName in northShiftRegionNames:
        frame = regionFramesByName[regionName]
        shiftedFrames[regionName] = RoutingZoneRegionFrame(
            horizontalStart=frame.horizontalStart,
            verticalStart=frame.verticalStart - 1,
            horizontalSpan=frame.horizontalSpan,
            verticalSpan=frame.verticalSpan,
        )
    _ = routeInputs
    _ = policy
    southShiftRegionNames = (
        _requiredRegionKey_get(sfN.Si),
        "west/intra_routing_transition:south",
        "east/intra_routing_transition:south",
    )
    for regionName in southShiftRegionNames:
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

    if channelArea is sfN.We:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.We))
        if frame is None:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)

    if channelArea is sfN.Wm:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Wm))
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

    if channelArea is sfN.Ee:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ee))
        if frame is None:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)

    if channelArea is sfN.Em:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Em))
        if frame is None:
            return None
        return (frame.horizontalStart + laneIndex - 1, referenceRowIndex)

    if channelArea is sfN.Ni:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ni))
        if frame is None:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)

    if channelArea is sfN.Ne:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ne))
        if frame is None:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)

    if channelArea is sfN.Si:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Si))
        if frame is None:
            return None
        return (frame.horizontalStart, frame.verticalStart + laneIndex - 1)

    if channelArea is sfN.Se:
        frame = regionFramesByName.get(_requiredRegionKey_get(sfN.Se))
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
