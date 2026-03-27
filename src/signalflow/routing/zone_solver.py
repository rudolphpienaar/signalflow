"""Zone-local routing solver for the new SignalFlow engine.

This module realizes `ZONE_LOCAL` call obligations against already planned
`RoutingZone` geometry.

Same-zone obligations do not all use the same substrate:

- west->east / north->south forward edges use the interior `INTRA` route family
- east->west / south->north backedges use the outer `INTER` perimeter family
- same-side self calls use a short local loop

Port identity and lane identity are intentionally separate. Multiple chips in
one zone can each have `childCallIndex == 0`, but they must still occupy
distinct route lanes inside the chosen geometry family.
"""
from __future__ import annotations

from signalflow.models import (
    CallRouteObligation,
    CallRouteObligationSet,
    ChipPlacement,
    ChipRef,
    CircuitDocument,
    KernelObligation,
    Result,
    RouteObligationScope,
    RoutingKernel,
    RoutingLaneAttachmentSense,
    RoutingLanePackingPolicy,
    RoutingOccupancyPolicy,
    RoutingZone,
    RoutingZoneAttachmentPolicy,
    RoutingZoneId,
    RoutingZoneLocalRouteSolveKind,
    RoutingZoneLocalSolvedRoute,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneRegion,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSet,
    RoutingZoneRegionSide,
    RoutingZoneRoutePoint,
    RoutingZoneSense,
    ZoneLocalGeometryKind,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneLocalSolvedRouteResult_build,
    routingZoneLocalSolvedRouteSetResult_build,
    routingZoneRegionByIdResult_get,
    routingZoneRegionForKindAndSideResult_get,
    routingZoneRegionSetAll_get,
    routingZoneRegionsForKindAndSide_get,
    routingZoneRoutePointResult_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.routing.kernel_solver import routingKernelSolvedRouteSetResult_build
from signalflow.routing.route import routePoints_realize
from signalflow.routing.track import TrackDirection


def routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneLocalSolvedRouteSet]:
    """Build solved zone-local routes from placed geometry and local obligations."""

    forwardRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    returnRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    laneIndexByObligationKey: dict[
        tuple[ChipRef, ChipRef, int],
        int,
    ] = _zoneLocalLaneIndexByObligationKey_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        callRouteObligationSet=callRouteObligationSet,
    )
    wteIntraObligationsByZoneId: dict[RoutingZoneId, list[CallRouteObligation]] = {}

    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.ZONE_LOCAL
        ):
            continue

        sourceZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            chipRef=callRouteObligation.sourceChipRef,
        )
        destinationZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            chipRef=callRouteObligation.destinationChipRef,
        )
        if not (
            result_isOkCheck(sourceZoneResult)
            and result_isOkCheck(destinationZoneResult)
        ):
            return resultErr_build()

        sourcePlacement = (
            sourceZoneResult.value.chipPlacementSet.placementForChipOrNone_get(
                callRouteObligation.sourceChipRef
            )
        )
        destinationPlacement = (
            sourceZoneResult.value.chipPlacementSet.placementForChipOrNone_get(
                callRouteObligation.destinationChipRef
            )
        )
        if sourcePlacement is None or destinationPlacement is None:
            return resultErr_build()

        sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
        destinationSide = (
            destinationPlacement.chipTerminalRegionId.routingZoneRegionSide
        )
        if (
            sourceZoneResult.value.routingZoneSense is RoutingZoneSense.WEST_TO_EAST
            and sourceZoneResult.value.routingZoneId
            == destinationZoneResult.value.routingZoneId
            and callRouteObligation.zoneLocalGeometryKind
            is not ZoneLocalGeometryKind.SAME_SIDE_LOCAL
            and callRouteObligation.zoneLocalGeometryKind
            is not ZoneLocalGeometryKind.INTER_PERIMETER_BACKEDGE
            and sourceSide is RoutingZoneRegionSide.WEST
            and destinationSide is RoutingZoneRegionSide.EAST
        ):
            wteIntraObligationsByZoneId.setdefault(
                sourceZoneResult.value.routingZoneId,
                [],
            ).append(callRouteObligation)
            continue

        obligationKey: tuple[ChipRef, ChipRef, int] = (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        )
        pairResult = _solvedRoutePairResult_buildFromObligation(
            circuitDocument=circuitDocument,
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            callRouteObligation=callRouteObligation,
            localLaneIndex=laneIndexByObligationKey[obligationKey],
        )
        if not result_isOkCheck(pairResult):
            return resultErr_build()

        forwardRoute, returnRoute = pairResult.value
        forwardRoutesMutable.append(forwardRoute)
        if returnRoute is not None:
            returnRoutesMutable.append(returnRoute)

    routingZoneId: RoutingZoneId
    groupedObligations: list[CallRouteObligation]
    for routingZoneId, groupedObligations in wteIntraObligationsByZoneId.items():
        zoneResult: Result[RoutingZone] = (
            placedRoutingZoneGrid.routingZoneSet.zoneResult_get(routingZoneId)
        )
        if not result_isOkCheck(zoneResult):
            return resultErr_build()
        zone: RoutingZone = zoneResult.value

        if zone.intraKernel is None:
            return resultErr_build()

        srcSideForGroup = None
        if groupedObligations:
            firstSrcPlacement = zone.chipPlacementSet.placementForChipOrNone_get(
                groupedObligations[0].sourceChipRef
            )
            if firstSrcPlacement is not None:
                srcSideForGroup = (
                    firstSrcPlacement.chipTerminalRegionId.routingZoneRegionSide
                )
        attachSense = (
            _attachmentSenseForSide_get(zone, srcSideForGroup)
            if srcSideForGroup is not None
            else RoutingLaneAttachmentSense.FROM_START
        )
        laneOrder = _laneIndicesInSenseOrder_build(
            laneCount=len(groupedObligations),
            laneSense=attachSense,
        )

        # Build per-destination port indices: rank of each obligation among
        # those sharing the same destinationChipRef (0-based, in obligation order).
        dstPortRankCounter: dict = {}
        dstPortIndices: list[int] = []
        for obligation in groupedObligations:
            dstKey = obligation.destinationChipRef.chipId
            rank = dstPortRankCounter.get(dstKey, 0)
            dstPortIndices.append(rank)
            dstPortRankCounter[dstKey] = rank + 1

        kernelObligations: list[KernelObligation] = []
        for obligation, laneIdx, dstPortIdx in zip(
            groupedObligations, laneOrder, dstPortIndices
        ):
            srcPlacementResult = zone.chipPlacementSet.placementForChipResult_get(
                obligation.sourceChipRef
            )
            dstPlacementResult = zone.chipPlacementSet.placementForChipResult_get(
                obligation.destinationChipRef
            )
            if not (
                result_isOkCheck(srcPlacementResult)
                and result_isOkCheck(dstPlacementResult)
            ):
                return resultErr_build()
            kernelObligations.append(
                KernelObligation(
                    callRouteObligation=obligation,
                    sourcePlacement=srcPlacementResult.value,
                    destinationPlacement=dstPlacementResult.value,
                    destinationPortIndex=dstPortIdx,
                    laneIndex=laneIdx,
                )
            )

        groupedRouteResult = routingKernelSolvedRouteSetResult_build(
            circuitDocument=circuitDocument,
            kernel=zone.intraKernel,
            obligations=kernelObligations,
        )
        if not result_isOkCheck(groupedRouteResult):
            return resultErr_build()
        forwardRoutesMutable.extend(groupedRouteResult.value[0])
        returnRoutesMutable.extend(groupedRouteResult.value[1])

    return routingZoneLocalSolvedRouteSetResult_build(
        routingZoneLocalSolvedRoutes=tuple(
            forwardRoutesMutable + returnRoutesMutable
        )
    )


def _zoneLocalLaneIndexByObligationKey_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> dict[tuple[ChipRef, ChipRef, int], int]:
    """Return stable per-zone lane indices for local obligations."""

    laneIndexByObligationKey: dict[tuple[ChipRef, ChipRef, int], int] = {}
    groupedObligationKeysByGroupKey: dict[
        tuple[RoutingZoneId, str, RoutingZoneRegionSide],
        list[tuple[ChipRef, ChipRef, int]],
    ] = {}
    laneSenseByGroupKey: dict[
        tuple[RoutingZoneId, str, RoutingZoneRegionSide],
        RoutingLaneAttachmentSense,
    ] = {}

    callRouteObligation: CallRouteObligation
    for callRouteObligation in callRouteObligationSet.callRouteObligations:
        if (
            callRouteObligation.routeObligationScope
            is not RouteObligationScope.ZONE_LOCAL
        ):
            continue

        sourceZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            chipRef=callRouteObligation.sourceChipRef,
        )
        destinationZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
            placedRoutingZoneGrid=placedRoutingZoneGrid,
            chipRef=callRouteObligation.destinationChipRef,
        )
        if not (
            result_isOkCheck(sourceZoneResult)
            and result_isOkCheck(destinationZoneResult)
        ):
            continue

        zone = sourceZoneResult.value
        sourcePlacement = zone.chipPlacementSet.placementForChipOrNone_get(
            callRouteObligation.sourceChipRef
        )
        destinationPlacement = zone.chipPlacementSet.placementForChipOrNone_get(
            callRouteObligation.destinationChipRef
        )
        if sourcePlacement is None or destinationPlacement is None:
            continue

        obligationKey: tuple[ChipRef, ChipRef, int] = (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        )
        if (
            callRouteObligation.zoneLocalGeometryKind
            is ZoneLocalGeometryKind.SAME_SIDE_LOCAL
        ):
            laneIndexByObligationKey[obligationKey] = (
                callRouteObligation.childCallIndex
            )
            continue

        if (
            callRouteObligation.zoneLocalGeometryKind
            is ZoneLocalGeometryKind.INTER_PERIMETER_BACKEDGE
        ):
            groupKey: tuple[RoutingZoneId, str, RoutingZoneRegionSide] = (
                zone.routingZoneId,
                "inter",
                sourcePlacement.chipTerminalRegionId.routingZoneRegionSide,
            )
            groupedObligationKeysByGroupKey.setdefault(groupKey, []).append(
                obligationKey
            )
            laneSenseByGroupKey[groupKey] = _attachmentSenseForSide_get(
                zone,
                sourcePlacement.chipTerminalRegionId.routingZoneRegionSide,
            )
            continue

        groupKey = (
            zone.routingZoneId,
            "intra",
            sourcePlacement.chipTerminalRegionId.routingZoneRegionSide,
        )
        groupedObligationKeysByGroupKey.setdefault(groupKey, []).append(obligationKey)
        laneSenseByGroupKey[groupKey] = _attachmentSenseForSide_get(
            zone,
            sourcePlacement.chipTerminalRegionId.routingZoneRegionSide,
        )

    groupKey: tuple[RoutingZoneId, str, RoutingZoneRegionSide]
    obligationKeys: list[tuple[ChipRef, ChipRef, int]]
    for groupKey, obligationKeys in groupedObligationKeysByGroupKey.items():
        laneOrder: tuple[int, ...] = _laneIndicesInSenseOrder_build(
            laneCount=len(obligationKeys),
            laneSense=laneSenseByGroupKey[groupKey],
        )
        obligationKey: tuple[ChipRef, ChipRef, int]
        laneIndex: int
        for obligationKey, laneIndex in zip(obligationKeys, laneOrder, strict=True):
            laneIndexByObligationKey[obligationKey] = laneIndex

    return laneIndexByObligationKey


def _laneIndicesInSenseOrder_build(
    laneCount: int,
    laneSense: RoutingLaneAttachmentSense,
) -> tuple[int, ...]:
    """Return deterministic lane indices in the requested pick-sense order."""

    if laneSense is RoutingLaneAttachmentSense.FROM_END:
        return tuple(range(laneCount - 1, -1, -1))
    return tuple(range(laneCount))


def _attachmentSenseForSide_get(
    zone: RoutingZone,
    routingZoneRegionSide: RoutingZoneRegionSide,
) -> RoutingLaneAttachmentSense:
    """Return the lane-pick sense for one source-side channel group."""

    if routingZoneRegionSide is RoutingZoneRegionSide.WEST:
        return zone.attachmentPolicy.westEdge
    if routingZoneRegionSide is RoutingZoneRegionSide.EAST:
        return zone.attachmentPolicy.eastEdge
    if routingZoneRegionSide is RoutingZoneRegionSide.NORTH:
        return zone.attachmentPolicy.northEdge
    return zone.attachmentPolicy.southEdge


def _regionForKindSideAndTagResult_get(
    zoneRegionSet,
    routingZoneRegionKind: RoutingZoneRegionKind,
    routingZoneRegionSide: RoutingZoneRegionSide,
    routingZoneRegionTag: str,
) -> Result[RoutingZoneRegion]:
    """Return one explicit region by kind, side, and tag."""

    routingZoneRegion: RoutingZoneRegion
    for routingZoneRegion in zoneRegionSet.routingZoneRegions:
        if (
            routingZoneRegion.routingZoneRegionId.routingZoneRegionKind
            is routingZoneRegionKind
            and routingZoneRegion.routingZoneRegionId.routingZoneRegionSide
            is routingZoneRegionSide
            and routingZoneRegion.routingZoneRegionId.routingZoneRegionTag
            == routingZoneRegionTag
        ):
            return resultOk_build(routingZoneRegion)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.zone.region.missing_kind_side_tag",
        message="Requested tagged RoutingZoneRegion is absent from the region set",
    )
    return resultErr_build()


def _directionsAreHorizontal(
    directions: frozenset[TrackDirection],
) -> bool:
    return directions <= {TrackDirection.EAST, TrackDirection.WEST}


def _directionsAreVertical(
    directions: frozenset[TrackDirection],
) -> bool:
    return directions <= {TrackDirection.NORTH, TrackDirection.SOUTH}


def _routeMayOccupyCellsCheck(
    occupiedDirectionsByCell: dict[tuple[int, int], frozenset[TrackDirection]],
    route: RoutingZoneLocalSolvedRoute,
) -> Result[bool]:
    """#OBSOLETE -- WTE intra machinery. Return whether one solved route is compatible with current occupancy."""

    realizedRouteResult = routePoints_realize(
        sourceChipRef=route.sourceChipRef,
        destinationChipRef=route.destinationChipRef,
        childCallIndex=route.childCallIndex,
        routePoints=route.routePoints,
    )
    if not result_isOkCheck(realizedRouteResult):
        return resultErr_build()

    for cell in realizedRouteResult.value.cells:
        key = (cell.worldRow, cell.worldCol)
        directions = cell.trackCell.directions
        if key not in occupiedDirectionsByCell:
            continue
        existingDirections = occupiedDirectionsByCell[key]
        crossingIsLegal = (
            _directionsAreHorizontal(existingDirections)
            and _directionsAreVertical(directions)
        ) or (
            _directionsAreVertical(existingDirections)
            and _directionsAreHorizontal(directions)
        )
        if not crossingIsLegal:
            return resultOk_build(False)
    return resultOk_build(True)


def _routeOccupancy_commit(
    occupiedDirectionsByCell: dict[tuple[int, int], frozenset[TrackDirection]],
    route: RoutingZoneLocalSolvedRoute,
) -> Result[None]:
    """#OBSOLETE -- WTE intra machinery. Commit one solved route's realized cells into the occupancy map."""

    realizedRouteResult = routePoints_realize(
        sourceChipRef=route.sourceChipRef,
        destinationChipRef=route.destinationChipRef,
        childCallIndex=route.childCallIndex,
        routePoints=route.routePoints,
    )
    if not result_isOkCheck(realizedRouteResult):
        return resultErr_build()

    for cell in realizedRouteResult.value.cells:
        key = (cell.worldRow, cell.worldCol)
        occupiedDirectionsByCell[key] = (
        occupiedDirectionsByCell.get(key, frozenset())
            | cell.trackCell.directions
        )
    return resultOk_build(None)


def _wteStripKeys_build(
    *,
    westLongLaneIndex: int,
    latLaneIndex: int,
    eastLongLaneIndex: int,
    isReturn: bool,
) -> frozenset[tuple[str, int]]:
    """#OBSOLETE -- WTE intra machinery. Build abstract strip reservations for one WTE route candidate."""

    latFamily: str = "south_lat" if isReturn else "north_lat"
    return frozenset(
        {
            ("west_long", westLongLaneIndex),
            (latFamily, latLaneIndex),
            ("east_long", eastLongLaneIndex),
        }
    )


def _laneTriplesInPackingOrder_build(
    firstLaneOrder: tuple[int, ...],
    latLaneOrder: tuple[int, ...],
    thirdLaneOrder: tuple[int, ...],
    packingPolicy: RoutingLanePackingPolicy,
) -> tuple[tuple[int, int, int], ...]:
    """#OBSOLETE -- WTE intra machinery. Build deterministic candidate lane triples for the requested policy."""

    return tuple(
        (firstLaneIndex, latLaneIndex, thirdLaneIndex)
        for firstLaneIndex in firstLaneOrder
        for latLaneIndex in latLaneOrder
        for thirdLaneIndex in thirdLaneOrder
    )


def _laneWindowsInSenseOrder_build(
    laneOrder: tuple[int, ...],
    windowSize: int,
) -> tuple[tuple[int, ...], ...]:
    """#OBSOLETE -- WTE intra machinery. Return contiguous lane windows in the requested sense order."""

    if windowSize > len(laneOrder):
        return ()
    return tuple(
        tuple(laneOrder[startIndex : startIndex + windowSize])
        for startIndex in range(len(laneOrder) - windowSize + 1)
    )


def _routeLengthScore_calculate(route: RoutingZoneLocalSolvedRoute) -> int:
    """#OBSOLETE -- WTE intra machinery. Calculate Manhattan route length from ordered route points."""

    totalLength: int = 0
    pointIndex: int
    for pointIndex in range(len(route.routePoints) - 1):
        currentPoint = route.routePoints[pointIndex]
        nextPoint = route.routePoints[pointIndex + 1]
        totalLength += abs(nextPoint.horizontalIndex - currentPoint.horizontalIndex)
        totalLength += abs(nextPoint.verticalIndex - currentPoint.verticalIndex)
    return totalLength


def _wteBundleWindowRoutesResult_build(
    *,
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligations: tuple[CallRouteObligation, ...],
    firstLaneWindow: tuple[int, ...],
    latLaneWindow: tuple[int, ...],
    thirdLaneWindow: tuple[int, ...],
    sourcePlacementByObligationKey: dict[tuple[ChipRef, ChipRef, int], ChipPlacement],
    destinationPlacementByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], ChipPlacement
    ],
    sourceTerminalRegionByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], RoutingZoneRegion
    ],
    destinationTerminalRegionByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], RoutingZoneRegion
    ],
    occupiedDirectionsByCell: dict[tuple[int, int], frozenset[TrackDirection]],
    occupiedStripKeys: set[tuple[str, int]],
    isReturn: bool,
) -> Result[
    tuple[
        tuple[RoutingZoneLocalSolvedRoute, ...],
        dict[tuple[int, int], frozenset[TrackDirection]],
        set[tuple[str, int]],
        int,
    ]
]:
    """#OBSOLETE -- WTE intra machinery. Build one WTE bundle against contiguous lane windows."""

    trialOccupiedDirectionsByCell = dict(occupiedDirectionsByCell)
    trialOccupiedStripKeys: set[tuple[str, int]] = set(occupiedStripKeys)
    routesMutable: list[RoutingZoneLocalSolvedRoute] = []

    obligationIndex: int
    obligation: CallRouteObligation
    for obligationIndex, obligation in enumerate(obligations):
        obligationKey = (
            obligation.sourceChipRef,
            obligation.destinationChipRef,
            obligation.childCallIndex,
        )
        firstLaneIndex: int = firstLaneWindow[obligationIndex]
        latLaneIndex: int = latLaneWindow[obligationIndex]
        thirdLaneIndex: int = thirdLaneWindow[obligationIndex]

        if isReturn:
            eastLongLaneIndex = firstLaneIndex
            southLatLaneIndex = latLaneIndex
            westLongLaneIndex = thirdLaneIndex
            candidateRouteResult = _wteIntraSolvedRouteResult_build(
                circuitDocument=circuitDocument,
                zone=zone,
                obligation=obligation,
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=southLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                sourcePlacement=sourcePlacementByObligationKey[obligationKey],
                destinationPlacement=destinationPlacementByObligationKey[
                    obligationKey
                ],
                sourceTerminalRegion=sourceTerminalRegionByObligationKey[
                    obligationKey
                ],
                destinationTerminalRegion=destinationTerminalRegionByObligationKey[
                    obligationKey
                ],
                isReturn=True,
            )
            if not result_isOkCheck(candidateRouteResult):
                return resultErr_build()
            candidateStripKeys = _wteStripKeys_build(
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=southLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                isReturn=True,
            )
        else:
            westLongLaneIndex = firstLaneIndex
            northLatLaneIndex = latLaneIndex
            eastLongLaneIndex = thirdLaneIndex
            candidateRouteResult = _wteIntraSolvedRouteResult_build(
                circuitDocument=circuitDocument,
                zone=zone,
                obligation=obligation,
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=northLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                sourcePlacement=sourcePlacementByObligationKey[obligationKey],
                destinationPlacement=destinationPlacementByObligationKey[
                    obligationKey
                ],
                sourceTerminalRegion=sourceTerminalRegionByObligationKey[
                    obligationKey
                ],
                destinationTerminalRegion=destinationTerminalRegionByObligationKey[
                    obligationKey
                ],
                isReturn=False,
            )
            if not result_isOkCheck(candidateRouteResult):
                return resultErr_build()
            candidateStripKeys = _wteStripKeys_build(
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=northLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                isReturn=False,
            )

        if (
            zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP
            and trialOccupiedStripKeys & candidateStripKeys
        ):
            return resultErr_build()

        routeMayOccupyResult = _routeMayOccupyCellsCheck(
            occupiedDirectionsByCell=trialOccupiedDirectionsByCell,
            route=candidateRouteResult.value,
        )
        if not result_isOkCheck(routeMayOccupyResult):
            return resultErr_build()
        if not routeMayOccupyResult.value:
            return resultErr_build()

        commitResult = _routeOccupancy_commit(
            occupiedDirectionsByCell=trialOccupiedDirectionsByCell,
            route=candidateRouteResult.value,
        )
        if not result_isOkCheck(commitResult):
            return resultErr_build()
        if zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP:
            trialOccupiedStripKeys |= candidateStripKeys
        routesMutable.append(candidateRouteResult.value)

    return resultOk_build(
        (
            tuple(routesMutable),
            trialOccupiedDirectionsByCell,
            trialOccupiedStripKeys,
            sum(_routeLengthScore_calculate(route) for route in routesMutable),
        )
    )


def _traversedRegionIdsForRealizedRouteResult_build(
    zone: RoutingZone,
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    routePoints,
    sourceTerminalRegionId: RoutingZoneRegionId,
    destinationTerminalRegionId: RoutingZoneRegionId,
) -> Result[tuple[RoutingZoneRegionId, ...]]:
    """Build ordered traversed region ids from realized route cells."""

    realizedRouteResult = routePoints_realize(
        sourceChipRef=sourceChipRef,
        destinationChipRef=destinationChipRef,
        childCallIndex=childCallIndex,
        routePoints=routePoints,
    )
    if not result_isOkCheck(realizedRouteResult):
        return resultErr_build()

    traversedIdsMutable: list[RoutingZoneRegionId] = [sourceTerminalRegionId]
    for cell in realizedRouteResult.value.cells:
        matchingIds = [
            region.routingZoneRegionId
            for region in routingZoneRegionSetAll_get(zone)
            if (
                region.routingZoneRegionFrame.horizontalStart
                <= cell.worldCol
                < region.routingZoneRegionFrame.horizontalEnd_calculate()
                and region.routingZoneRegionFrame.verticalStart
                <= cell.worldRow
                < region.routingZoneRegionFrame.verticalEnd_calculate()
            )
        ]
        if not matchingIds:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.cell_outside_regions",
                message="Realized route cell is outside all owned zone regions",
                context=(str(cell.worldCol), str(cell.worldRow)),
            )
            return resultErr_build()
        if len(matchingIds) != 1:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.cell_in_multiple_regions",
                message="Realized route cell lies in multiple owned zone regions",
                context=(str(cell.worldCol), str(cell.worldRow)),
            )
            return resultErr_build()
        regionId = matchingIds[0]
        if regionId != traversedIdsMutable[-1]:
            traversedIdsMutable.append(regionId)

    if traversedIdsMutable[-1] != destinationTerminalRegionId:
        traversedIdsMutable.append(destinationTerminalRegionId)

    return resultOk_build(tuple(traversedIdsMutable))


def _solvedRoutePairResult_buildFromObligation(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligation: CallRouteObligation,
    localLaneIndex: int,
) -> Result[tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]]:
    """Build (forward, return) solved route pair for one local obligation."""

    sourceZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        chipRef=callRouteObligation.sourceChipRef,
    )
    if not result_isOkCheck(sourceZoneResult):
        return resultErr_build()
    destinationZoneResult: Result[RoutingZone] = _zoneOwningChipResult_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        chipRef=callRouteObligation.destinationChipRef,
    )
    if not result_isOkCheck(destinationZoneResult):
        return resultErr_build()
    if (
        sourceZoneResult.value.routingZoneId
        != destinationZoneResult.value.routingZoneId
    ):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_solver.local_route.cross_zone_obligation",
            message="Zone-local route obligations must stay inside one routing zone",
        )
        return resultErr_build()

    zone = sourceZoneResult.value

    sourcePlacementResult: Result[ChipPlacement] = (
        zone.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.sourceChipRef
        )
    )
    if not result_isOkCheck(sourcePlacementResult):
        return resultErr_build()
    destinationPlacementResult: Result[ChipPlacement] = (
        zone.chipPlacementSet.placementForChipResult_get(
            callRouteObligation.destinationChipRef
        )
    )
    if not result_isOkCheck(destinationPlacementResult):
        return resultErr_build()

    sourceTerminalRegionResult: Result[RoutingZoneRegion] = (
        routingZoneRegionByIdResult_get(
            zone,
            sourcePlacementResult.value.chipTerminalRegionId,
        )
    )
    if not result_isOkCheck(sourceTerminalRegionResult):
        return resultErr_build()
    destinationTerminalRegionResult: Result[RoutingZoneRegion] = (
        routingZoneRegionByIdResult_get(
            zone,
            destinationPlacementResult.value.chipTerminalRegionId,
        )
    )
    if not result_isOkCheck(destinationTerminalRegionResult):
        return resultErr_build()

    sourceSide = sourcePlacementResult.value.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = (
        destinationPlacementResult.value.chipTerminalRegionId.routingZoneRegionSide
    )

    # Self-call: same chip on the same side — single same-side local route, no return.
    if sourceSide == destinationSide:
        sameResult = _sameSideLocalRouteResult_build(
            circuitDocument=circuitDocument,
            zone=zone,
            obligation=callRouteObligation,
            sourcePlacement=sourcePlacementResult.value,
            destinationPlacement=destinationPlacementResult.value,
            sourceTerminalRegion=sourceTerminalRegionResult.value,
            destinationTerminalRegion=destinationTerminalRegionResult.value,
        )
        if not result_isOkCheck(sameResult):
            return resultErr_build()
        return resultOk_build((sameResult.value, None))

    if zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return _wteRoutePairResult_build(
            circuitDocument=circuitDocument,
            zone=zone,
            obligation=callRouteObligation,
            localLaneIndex=localLaneIndex,
            sourcePlacement=sourcePlacementResult.value,
            destinationPlacement=destinationPlacementResult.value,
            sourceTerminalRegion=sourceTerminalRegionResult.value,
            destinationTerminalRegion=destinationTerminalRegionResult.value,
        )
    return _ntsRoutePairResult_build(
        circuitDocument=circuitDocument,
        zone=zone,
        obligation=callRouteObligation,
        localLaneIndex=localLaneIndex,
        sourcePlacement=sourcePlacementResult.value,
        destinationPlacement=destinationPlacementResult.value,
        sourceTerminalRegion=sourceTerminalRegionResult.value,
        destinationTerminalRegion=destinationTerminalRegionResult.value,
    )


# ---------------------------------------------------------------------------
# WTE solver
# ---------------------------------------------------------------------------


def _wteIntraSolvedRouteResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligation: CallRouteObligation,
    westLongLaneIndex: int,
    latLaneIndex: int,
    eastLongLaneIndex: int,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceTerminalRegion: RoutingZoneRegion,
    destinationTerminalRegion: RoutingZoneRegion,
    isReturn: bool,
) -> Result[RoutingZoneLocalSolvedRoute]:
    """#OBSOLETE -- WTE intra machinery. Build one WTE INTRA route using one candidate lane index."""

    fanW = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST
    )
    fanE = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST
    )
    latN = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH
    )
    latS = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH
    )
    northTransitionW = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet if zone.intraKernel else RoutingZoneRegionSet(),
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        RoutingZoneRegionSide.WEST,
        "north",
    )
    southTransitionW = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet if zone.intraKernel else RoutingZoneRegionSet(),
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        RoutingZoneRegionSide.WEST,
        "south",
    )
    northTransitionE = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet if zone.intraKernel else RoutingZoneRegionSet(),
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        RoutingZoneRegionSide.EAST,
        "north",
    )
    southTransitionE = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet if zone.intraKernel else RoutingZoneRegionSet(),
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        RoutingZoneRegionSide.EAST,
        "south",
    )
    longWRegions = routingZoneRegionsForKindAndSide_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionSide.WEST,
    ).routingZoneRegions
    longERegions = routingZoneRegionsForKindAndSide_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionSide.EAST,
    ).routingZoneRegions
    if not all(
        result_isOkCheck(r)
        for r in [
            fanW,
            fanE,
            latN,
            latS,
            northTransitionW,
            southTransitionW,
            northTransitionE,
            southTransitionE,
        ]
    ):
        return resultErr_build()
    if not longWRegions or not longERegions:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone_solver.local_route.missing_longitude_segments",
            message="WTE INTRA longitude segments are absent from the region set",
        )
        return resultErr_build()

    srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.destinationChipRef.chipId
    )
    if not (result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)):
        return resultErr_build()
    srcChipH: int = len(chipDrawLines_build(srcChipResult.value))
    dstChipH: int = len(chipDrawLines_build(dstChipResult.value))
    _HEADER: int = 3

    portIndex: int = obligation.childCallIndex
    fanW_col: int = fanW.value.routingZoneRegionFrame.horizontalStart
    fanE_col: int = fanE.value.routingZoneRegionFrame.horizontalStart
    longW_start: int = longWRegions[0].routingZoneRegionFrame.horizontalStart
    longE_start: int = longERegions[0].routingZoneRegionFrame.horizontalStart
    latN_start: int = latN.value.routingZoneRegionFrame.verticalStart
    latS_start: int = latS.value.routingZoneRegionFrame.verticalStart

    r_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipH + 2)
        + 1 + _HEADER + 2 * portIndex
    )
    r_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipH + 2)
        + 1 + _HEADER
    )
    r_src_ret: int = r_src + 1
    r_dst_ret: int = r_dst + 1

    if isReturn:
        lane_left: int = longW_start + westLongLaneIndex
        lane_right: int = longE_start + eastLongLaneIndex
        lane_bottom: int = latS_start + latLaneIndex
        pointsRaw: list[tuple[int, int]] = [
            (fanE_col, r_dst_ret),
            (lane_right, r_dst_ret),
            (lane_right, lane_bottom),
            (lane_left, lane_bottom),
            (lane_left, r_src_ret),
            (fanW_col, r_src_ret),
        ]
        sourceChipRef = obligation.destinationChipRef
        destinationChipRef = obligation.sourceChipRef
        solveKind = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
    else:
        lane_left = longW_start + westLongLaneIndex
        lane_top = latN_start + latLaneIndex
        lane_right = longE_start + eastLongLaneIndex
        pointsRaw = [
            (fanW_col, r_src),
            (lane_left, r_src),
            (lane_left, lane_top),
            (lane_right, lane_top),
            (lane_right, r_dst),
            (fanE_col, r_dst),
        ]
        sourceChipRef = obligation.sourceChipRef
        destinationChipRef = obligation.destinationChipRef
        solveKind = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD

    pointsResult = _routePoints_build(pointsRaw)
    if not result_isOkCheck(pointsResult):
        return resultErr_build()
    traversedRegionIdsResult = _traversedRegionIdsForRealizedRouteResult_build(
        zone=zone,
        sourceChipRef=sourceChipRef,
        destinationChipRef=destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        routePoints=pointsResult.value,
        sourceTerminalRegionId=sourceTerminalRegion.routingZoneRegionId,
        destinationTerminalRegionId=destinationTerminalRegion.routingZoneRegionId,
    )
    if not result_isOkCheck(traversedRegionIdsResult):
        return resultErr_build()

    return routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=sourceChipRef,
        destinationChipRef=destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKind,
        routePoints=pointsResult.value,
        traversedRegionIds=traversedRegionIdsResult.value,
    )


def _wteOccupancySolvedRoutesResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligations: tuple[CallRouteObligation, ...],
) -> Result[
    tuple[
        tuple[RoutingZoneLocalSolvedRoute, ...],
        tuple[RoutingZoneLocalSolvedRoute, ...],
    ]
]:
    """#OBSOLETE -- WTE intra machinery. Build WTE local routes by first legal occupancy rather than symbolic order."""

    occupiedDirectionsByCell: dict[tuple[int, int], frozenset[TrackDirection]] = {}
    occupiedStripKeys: set[tuple[str, int]] = set()
    forwardRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    returnRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []

    longWResult = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST
    )
    if not result_isOkCheck(longWResult):
        return resultErr_build()
    laneCount: int = longWResult.value.routingZoneRegionFrame.horizontalSpan

    sourcePlacementByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], ChipPlacement
    ] = {}
    destinationPlacementByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], ChipPlacement
    ] = {}
    sourceTerminalRegionByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], RoutingZoneRegion
    ] = {}
    destinationTerminalRegionByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], RoutingZoneRegion
    ] = {}

    obligation: CallRouteObligation
    for obligation in obligations:
        sourcePlacementResult = zone.chipPlacementSet.placementForChipResult_get(
            obligation.sourceChipRef
        )
        destinationPlacementResult = zone.chipPlacementSet.placementForChipResult_get(
            obligation.destinationChipRef
        )
        if not (
            result_isOkCheck(sourcePlacementResult)
            and result_isOkCheck(destinationPlacementResult)
        ):
            return resultErr_build()
        sourceTerminalRegionResult = routingZoneRegionByIdResult_get(
            zone,
            sourcePlacementResult.value.chipTerminalRegionId,
        )
        destinationTerminalRegionResult = routingZoneRegionByIdResult_get(
            zone,
            destinationPlacementResult.value.chipTerminalRegionId,
        )
        if not (
            result_isOkCheck(sourceTerminalRegionResult)
            and result_isOkCheck(destinationTerminalRegionResult)
        ):
            return resultErr_build()
        obligationKey = (
            obligation.sourceChipRef,
            obligation.destinationChipRef,
            obligation.childCallIndex,
        )
        sourcePlacementByObligationKey[obligationKey] = sourcePlacementResult.value
        destinationPlacementByObligationKey[obligationKey] = (
            destinationPlacementResult.value
        )
        sourceTerminalRegionByObligationKey[obligationKey] = (
            sourceTerminalRegionResult.value
        )
        destinationTerminalRegionByObligationKey[obligationKey] = (
            destinationTerminalRegionResult.value
        )

    obligations = tuple(
        sorted(obligations, key=lambda obligation: obligation.childCallIndex)
    )

    westForwardLaneOrder: tuple[int, ...] = _laneIndicesInSenseOrder_build(
        laneCount=laneCount,
        laneSense=zone.attachmentPolicy.westEdge,
    )
    northLatLaneOrder: tuple[int, ...] = _laneIndicesInSenseOrder_build(
        laneCount=laneCount,
        laneSense=zone.attachmentPolicy.northTransversalInChannel,
    )
    eastForwardLaneOrder: tuple[int, ...] = _laneIndicesInSenseOrder_build(
        laneCount=laneCount,
        laneSense=zone.attachmentPolicy.eastEdge,
    )
    eastReturnLaneOrder: tuple[int, ...] = _laneIndicesInSenseOrder_build(
        laneCount=laneCount,
        laneSense=zone.attachmentPolicy.eastEdge,
    )
    southLatLaneOrder: tuple[int, ...] = _laneIndicesInSenseOrder_build(
        laneCount=laneCount,
        laneSense=zone.attachmentPolicy.southTransversalInChannel,
    )
    westReturnLaneOrder: tuple[int, ...] = _laneIndicesInSenseOrder_build(
        laneCount=laneCount,
        laneSense=zone.attachmentPolicy.westEdge,
    )
    forwardLaneTriples: tuple[tuple[int, int, int], ...] = (
        _laneTriplesInPackingOrder_build(
            firstLaneOrder=westForwardLaneOrder,
            latLaneOrder=northLatLaneOrder,
            thirdLaneOrder=eastForwardLaneOrder,
            packingPolicy=RoutingLanePackingPolicy.FREE,
        )
    )
    returnLaneTriples: tuple[tuple[int, int, int], ...] = (
        _laneTriplesInPackingOrder_build(
            firstLaneOrder=eastReturnLaneOrder,
            latLaneOrder=southLatLaneOrder,
            thirdLaneOrder=westReturnLaneOrder,
            packingPolicy=RoutingLanePackingPolicy.FREE,
        )
    )

    if zone.packingPolicy is RoutingLanePackingPolicy.MONOTONE:
        obligationWindowSize: int = len(obligations)
        forwardFirstLaneWindows = _laneWindowsInSenseOrder_build(
            westForwardLaneOrder,
            obligationWindowSize,
        )
        forwardLatLaneWindows = _laneWindowsInSenseOrder_build(
            northLatLaneOrder,
            obligationWindowSize,
        )
        forwardThirdLaneWindows = _laneWindowsInSenseOrder_build(
            eastForwardLaneOrder,
            obligationWindowSize,
        )
        bestForwardRoutes: tuple[RoutingZoneLocalSolvedRoute, ...] | None = None
        bestForwardOccupiedDirectionsByCell: (
            dict[tuple[int, int], frozenset[TrackDirection]] | None
        ) = None
        bestForwardOccupiedStripKeys: set[tuple[str, int]] | None = None
        bestForwardScore: tuple[int, int, int, int] | None = None
        forwardFirstWindowIndex: int
        forwardLatWindowIndex: int
        forwardThirdWindowIndex: int
        forwardFirstLaneWindow: tuple[int, ...]
        forwardLatLaneWindow: tuple[int, ...]
        forwardThirdLaneWindow: tuple[int, ...]
        for forwardFirstWindowIndex, forwardFirstLaneWindow in enumerate(
            forwardFirstLaneWindows
        ):
            for forwardLatWindowIndex, forwardLatLaneWindow in enumerate(
                forwardLatLaneWindows
            ):
                for forwardThirdWindowIndex, forwardThirdLaneWindow in enumerate(
                    forwardThirdLaneWindows
                ):
                    forwardBundleResult = _wteBundleWindowRoutesResult_build(
                        circuitDocument=circuitDocument,
                        zone=zone,
                        obligations=obligations,
                        firstLaneWindow=forwardFirstLaneWindow,
                        latLaneWindow=forwardLatLaneWindow,
                        thirdLaneWindow=forwardThirdLaneWindow,
                        sourcePlacementByObligationKey=(
                            sourcePlacementByObligationKey
                        ),
                        destinationPlacementByObligationKey=(
                            destinationPlacementByObligationKey
                        ),
                        sourceTerminalRegionByObligationKey=(
                            sourceTerminalRegionByObligationKey
                        ),
                        destinationTerminalRegionByObligationKey=(
                            destinationTerminalRegionByObligationKey
                        ),
                        occupiedDirectionsByCell=occupiedDirectionsByCell,
                        occupiedStripKeys=occupiedStripKeys,
                        isReturn=False,
                    )
                    if not result_isOkCheck(forwardBundleResult):
                        continue
                    (
                        candidateForwardRoutes,
                        candidateForwardOccupiedDirectionsByCell,
                        candidateForwardOccupiedStripKeys,
                        candidateForwardLengthScore,
                    ) = forwardBundleResult.value
                    candidateForwardScore = (
                        candidateForwardLengthScore,
                        forwardFirstWindowIndex,
                        forwardLatWindowIndex,
                        forwardThirdWindowIndex,
                    )
                    if (
                        bestForwardScore is None
                        or candidateForwardScore < bestForwardScore
                    ):
                        bestForwardScore = candidateForwardScore
                        bestForwardRoutes = candidateForwardRoutes
                        bestForwardOccupiedDirectionsByCell = (
                            candidateForwardOccupiedDirectionsByCell
                        )
                        bestForwardOccupiedStripKeys = (
                            candidateForwardOccupiedStripKeys
                        )
        if (
            bestForwardRoutes is None
            or bestForwardOccupiedDirectionsByCell is None
            or bestForwardOccupiedStripKeys is None
        ):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.no_legal_forward_lane",
                message="No legal occupancy-free INTRA forward lane was found",
                context=(
                    obligations[0].sourceChipRef.chipId.moduleName,
                    obligations[0].destinationChipRef.chipId.moduleName,
                    "bundle",
                ),
            )
            return resultErr_build()
        occupiedDirectionsByCell = bestForwardOccupiedDirectionsByCell
        occupiedStripKeys = bestForwardOccupiedStripKeys
        forwardRoutesMutable.extend(bestForwardRoutes)

        returnFirstLaneWindows = _laneWindowsInSenseOrder_build(
            eastReturnLaneOrder,
            obligationWindowSize,
        )
        returnLatLaneWindows = _laneWindowsInSenseOrder_build(
            southLatLaneOrder,
            obligationWindowSize,
        )
        returnThirdLaneWindows = _laneWindowsInSenseOrder_build(
            westReturnLaneOrder,
            obligationWindowSize,
        )
        bestReturnRoutes: tuple[RoutingZoneLocalSolvedRoute, ...] | None = None
        bestReturnOccupiedDirectionsByCell: (
            dict[tuple[int, int], frozenset[TrackDirection]] | None
        ) = None
        bestReturnOccupiedStripKeys: set[tuple[str, int]] | None = None
        bestReturnScore: tuple[int, int, int, int] | None = None
        returnFirstWindowIndex: int
        returnLatWindowIndex: int
        returnThirdWindowIndex: int
        returnFirstLaneWindow: tuple[int, ...]
        returnLatLaneWindow: tuple[int, ...]
        returnThirdLaneWindow: tuple[int, ...]
        for returnFirstWindowIndex, returnFirstLaneWindow in enumerate(
            returnFirstLaneWindows
        ):
            for returnLatWindowIndex, returnLatLaneWindow in enumerate(
                returnLatLaneWindows
            ):
                for returnThirdWindowIndex, returnThirdLaneWindow in enumerate(
                    returnThirdLaneWindows
                ):
                    returnBundleResult = _wteBundleWindowRoutesResult_build(
                        circuitDocument=circuitDocument,
                        zone=zone,
                        obligations=obligations,
                        firstLaneWindow=returnFirstLaneWindow,
                        latLaneWindow=returnLatLaneWindow,
                        thirdLaneWindow=returnThirdLaneWindow,
                        sourcePlacementByObligationKey=(
                            sourcePlacementByObligationKey
                        ),
                        destinationPlacementByObligationKey=(
                            destinationPlacementByObligationKey
                        ),
                        sourceTerminalRegionByObligationKey=(
                            sourceTerminalRegionByObligationKey
                        ),
                        destinationTerminalRegionByObligationKey=(
                            destinationTerminalRegionByObligationKey
                        ),
                        occupiedDirectionsByCell=occupiedDirectionsByCell,
                        occupiedStripKeys=occupiedStripKeys,
                        isReturn=True,
                    )
                    if not result_isOkCheck(returnBundleResult):
                        continue
                    (
                        candidateReturnRoutes,
                        candidateReturnOccupiedDirectionsByCell,
                        candidateReturnOccupiedStripKeys,
                        candidateReturnLengthScore,
                    ) = returnBundleResult.value
                    candidateReturnScore = (
                        candidateReturnLengthScore,
                        returnFirstWindowIndex,
                        returnLatWindowIndex,
                        returnThirdWindowIndex,
                    )
                    if (
                        bestReturnScore is None
                        or candidateReturnScore < bestReturnScore
                    ):
                        bestReturnScore = candidateReturnScore
                        bestReturnRoutes = candidateReturnRoutes
                        bestReturnOccupiedDirectionsByCell = (
                            candidateReturnOccupiedDirectionsByCell
                        )
                        bestReturnOccupiedStripKeys = (
                            candidateReturnOccupiedStripKeys
                        )
        if (
            bestReturnRoutes is None
            or bestReturnOccupiedDirectionsByCell is None
            or bestReturnOccupiedStripKeys is None
        ):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.no_legal_return_lane",
                message="No legal occupancy-free INTRA return lane was found",
                context=(
                    obligations[0].sourceChipRef.chipId.moduleName,
                    obligations[0].destinationChipRef.chipId.moduleName,
                    "bundle",
                ),
            )
            return resultErr_build()
        occupiedDirectionsByCell = bestReturnOccupiedDirectionsByCell
        occupiedStripKeys = bestReturnOccupiedStripKeys
        returnRoutesMutable.extend(bestReturnRoutes)

        return resultOk_build(
            (tuple(forwardRoutesMutable), tuple(returnRoutesMutable))
        )

    for obligation in obligations:
        obligationKey = (
            obligation.sourceChipRef,
            obligation.destinationChipRef,
            obligation.childCallIndex,
        )
        chosenForwardRoute: RoutingZoneLocalSolvedRoute | None = None
        chosenForwardStripKeys: frozenset[tuple[str, int]] = frozenset()
        westLongLaneIndex: int
        northLatLaneIndex: int
        eastLongLaneIndex: int
        for (
            westLongLaneIndex,
            northLatLaneIndex,
            eastLongLaneIndex,
        ) in forwardLaneTriples:
            if chosenForwardRoute is not None:
                break
            candidateRouteResult = _wteIntraSolvedRouteResult_build(
                circuitDocument=circuitDocument,
                zone=zone,
                obligation=obligation,
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=northLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                sourcePlacement=sourcePlacementByObligationKey[obligationKey],
                destinationPlacement=destinationPlacementByObligationKey[
                    obligationKey
                ],
                sourceTerminalRegion=sourceTerminalRegionByObligationKey[
                    obligationKey
                ],
                destinationTerminalRegion=destinationTerminalRegionByObligationKey[
                    obligationKey
                ],
                isReturn=False,
            )
            if not result_isOkCheck(candidateRouteResult):
                return resultErr_build()
            candidateStripKeys = _wteStripKeys_build(
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=northLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                isReturn=False,
            )
            if (
                zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP
                and occupiedStripKeys & candidateStripKeys
            ):
                continue
            routeMayOccupyResult = _routeMayOccupyCellsCheck(
                occupiedDirectionsByCell=occupiedDirectionsByCell,
                route=candidateRouteResult.value,
            )
            if not result_isOkCheck(routeMayOccupyResult):
                return resultErr_build()
            if not routeMayOccupyResult.value:
                continue
            commitResult = _routeOccupancy_commit(
                occupiedDirectionsByCell=occupiedDirectionsByCell,
                route=candidateRouteResult.value,
            )
            if not result_isOkCheck(commitResult):
                return resultErr_build()
            if zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP:
                occupiedStripKeys |= candidateStripKeys
            chosenForwardRoute = candidateRouteResult.value
            chosenForwardStripKeys = candidateStripKeys
            break
        if chosenForwardRoute is None:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.no_legal_forward_lane",
                message="No legal occupancy-free INTRA forward lane was found",
                context=(
                    obligation.sourceChipRef.chipId.moduleName,
                    obligation.destinationChipRef.chipId.moduleName,
                    str(obligation.childCallIndex),
                ),
            )
            return resultErr_build()
        commitResult = _routeOccupancy_commit(
            occupiedDirectionsByCell=occupiedDirectionsByCell,
            route=chosenForwardRoute,
        )
        if not result_isOkCheck(commitResult):
            return resultErr_build()
        if zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP:
            occupiedStripKeys |= chosenForwardStripKeys
        forwardRoutesMutable.append(chosenForwardRoute)

    for obligation in obligations:
        obligationKey = (
            obligation.sourceChipRef,
            obligation.destinationChipRef,
            obligation.childCallIndex,
        )
        chosenReturnRoute: RoutingZoneLocalSolvedRoute | None = None
        chosenReturnStripKeys: frozenset[tuple[str, int]] = frozenset()
        for (
            eastLongLaneIndex,
            southLatLaneIndex,
            westLongLaneIndex,
        ) in returnLaneTriples:
            if chosenReturnRoute is not None:
                break
            candidateRouteResult = _wteIntraSolvedRouteResult_build(
                circuitDocument=circuitDocument,
                zone=zone,
                obligation=obligation,
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=southLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                sourcePlacement=sourcePlacementByObligationKey[obligationKey],
                destinationPlacement=destinationPlacementByObligationKey[
                    obligationKey
                ],
                sourceTerminalRegion=sourceTerminalRegionByObligationKey[
                    obligationKey
                ],
                destinationTerminalRegion=destinationTerminalRegionByObligationKey[
                    obligationKey
                ],
                isReturn=True,
            )
            if not result_isOkCheck(candidateRouteResult):
                return resultErr_build()
            candidateStripKeys = _wteStripKeys_build(
                westLongLaneIndex=westLongLaneIndex,
                latLaneIndex=southLatLaneIndex,
                eastLongLaneIndex=eastLongLaneIndex,
                isReturn=True,
            )
            if (
                zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP
                and occupiedStripKeys & candidateStripKeys
            ):
                continue
            routeMayOccupyResult = _routeMayOccupyCellsCheck(
                occupiedDirectionsByCell=occupiedDirectionsByCell,
                route=candidateRouteResult.value,
            )
            if not result_isOkCheck(routeMayOccupyResult):
                return resultErr_build()
            if not routeMayOccupyResult.value:
                continue
            commitResult = _routeOccupancy_commit(
                occupiedDirectionsByCell=occupiedDirectionsByCell,
                route=candidateRouteResult.value,
            )
            if not result_isOkCheck(commitResult):
                return resultErr_build()
            if zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP:
                occupiedStripKeys |= candidateStripKeys
            chosenReturnRoute = candidateRouteResult.value
            chosenReturnStripKeys = candidateStripKeys
            break
        if chosenReturnRoute is None:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.no_legal_return_lane",
                message="No legal occupancy-free INTRA return lane was found",
                context=(
                    obligation.sourceChipRef.chipId.moduleName,
                    obligation.destinationChipRef.chipId.moduleName,
                    str(obligation.childCallIndex),
                ),
            )
            return resultErr_build()
        commitResult = _routeOccupancy_commit(
            occupiedDirectionsByCell=occupiedDirectionsByCell,
            route=chosenReturnRoute,
        )
        if not result_isOkCheck(commitResult):
            return resultErr_build()
        if zone.occupancyPolicy is RoutingOccupancyPolicy.STRIP:
            occupiedStripKeys |= chosenReturnStripKeys
        returnRoutesMutable.append(chosenReturnRoute)

    return resultOk_build(
        (tuple(forwardRoutesMutable), tuple(returnRoutesMutable))
    )


def _wteRoutePairResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligation: CallRouteObligation,
    localLaneIndex: int,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceTerminalRegion: RoutingZoneRegion,
    destinationTerminalRegion: RoutingZoneRegion,
) -> Result[tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]]:
    """#OBSOLETE -- WTE intra machinery. Build forward + return solved route pair for one WTE ZONE_LOCAL obligation."""

    fanW = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.WEST
    )
    fanE = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.EAST
    )
    longW = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST
    )
    longE = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST
    )
    latN = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH
    )
    latS = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH
    )
    if not all(
        result_isOkCheck(r) for r in [fanW, fanE, longW, longE, latN, latS]
    ):
        return resultErr_build()

    # Look up chip heights so port rows can be computed from slot boundaries.
    srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.destinationChipRef.chipId
    )
    if not (result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)):
        return resultErr_build()
    srcChipH: int = len(chipDrawLines_build(srcChipResult.value))
    dstChipH: int = len(chipDrawLines_build(dstChipResult.value))

    # Chip body layout: top-border + title + separator = 3 header rows before ports.
    _HEADER: int = 3

    portIndex: int = obligation.childCallIndex
    fanW_col: int = fanW.value.routingZoneRegionFrame.horizontalStart
    fanE_col: int = fanE.value.routingZoneRegionFrame.horizontalStart
    longW_start: int = longW.value.routingZoneRegionFrame.horizontalStart
    longE_end: int = (
        longE.value.routingZoneRegionFrame.horizontalEnd_calculate() - 1
    )
    latN_end: int = latN.value.routingZoneRegionFrame.verticalEnd_calculate() - 1
    latS_start: int = latS.value.routingZoneRegionFrame.verticalStart

    # r_src / r_dst: the actual port rows inside the chip body.
    # Each chip slot = chipHeight + 2 rows (1 corridor above, body, 1 corridor below).
    # Port row = slotStart + 1 (corridor) + _HEADER + 2*k (signal) or 2*k+1 (return).
    # Each east terminal occupies 2 body rows: signal at 2k, return at 2k+1.
    # Source port index k = which call in the source chip's outgoing call list.
    # Destination port index = 0 (first input port of the destination chip).
    r_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipH + 2)
        + 1 + _HEADER + 2 * portIndex
    )
    r_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipH + 2)
        + 1 + _HEADER
    )
    r_src_ret: int = r_src + 1
    r_dst_ret: int = r_dst + 1

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = destinationPlacement.chipTerminalRegionId.routingZoneRegionSide

    if (
        sourceSide is RoutingZoneRegionSide.WEST
        and destinationSide is RoutingZoneRegionSide.EAST
    ):
        forwardLaneIndex: int = 2 * localLaneIndex
        returnLaneIndex: int = forwardLaneIndex + 1
        fwd_lane_left: int = longW_start + forwardLaneIndex
        fwd_lane_top: int = latN_end - forwardLaneIndex
        fwd_lane_right: int = longE_end - forwardLaneIndex
        ret_lane_left: int = longW_start + returnLaneIndex
        ret_lane_right: int = longE_end - returnLaneIndex
        ret_lane_bottom: int = latS_start + returnLaneIndex
        solveKindForward = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        # Forward: top half of clockwise INTRA rectangle (W→E).
        fwdPointsRaw: list[tuple[int, int]] = [
            (fanW_col,   r_src),
            (fwd_lane_left,  r_src),
            (fwd_lane_left,  fwd_lane_top),
            (fwd_lane_right, fwd_lane_top),
            (fwd_lane_right, r_dst),
            (fanE_col,   r_dst),
        ]
        retPointsRaw: list[tuple[int, int]] = [
            (fanE_col,    r_dst_ret),
            (ret_lane_right,  r_dst_ret),
            (ret_lane_right,  ret_lane_bottom),
            (ret_lane_left,   ret_lane_bottom),
            (ret_lane_left,   r_src_ret),
            (fanW_col,    r_src_ret),
        ]
        intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanW.value.routingZoneRegionId,
            longW.value.routingZoneRegionId,
            latN.value.routingZoneRegionId,
            longE.value.routingZoneRegionId,
            fanE.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds: tuple[RoutingZoneRegionId, ...] = (
            destinationTerminalRegion.routingZoneRegionId,
            fanE.value.routingZoneRegionId,
            longE.value.routingZoneRegionId,
            latS.value.routingZoneRegionId,
            longW.value.routingZoneRegionId,
            fanW.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )
    else:
        laneIndex: int = localLaneIndex
        interFanW = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.WEST,
        )
        interFanE = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.EAST,
        )
        interLongW = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        interLongE = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.EAST,
        )
        interLatN = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        interLatS = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.SOUTH,
        )
        if not all(
            result_isOkCheck(r)
            for r in [
                interFanW,
                interFanE,
                interLongW,
                interLongE,
                interLatN,
                interLatS,
            ]
        ):
            return resultErr_build()

        solveKindForward = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
        srcInterFanStart: int = (
            interFanE.value.routingZoneRegionFrame.horizontalStart
        )
        dstInterFanStart: int = (
            interFanW.value.routingZoneRegionFrame.horizontalStart
        )
        dstInterFanEnd: int = (
            interFanW.value.routingZoneRegionFrame.horizontalEnd_calculate() - 1
        )
        srcInterTravelCol: int = (
            interLongE.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        dstInterTravelCol: int = (
            interLongW.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        srcInterLaneCol: int = srcInterFanStart + 2 + laneIndex
        dstInterLaneCol: int = dstInterFanStart + laneIndex
        northPerimeterRow: int = (
            interLatN.value.routingZoneRegionFrame.verticalStart
        )
        southPerimeterRow: int = (
            interLatS.value.routingZoneRegionFrame.verticalStart
        )

        fwdPointsRaw = [
            (srcInterFanStart, r_src),
            (srcInterFanStart + 1, r_src),
            (srcInterLaneCol, r_src),
            (srcInterTravelCol, r_src),
            (srcInterTravelCol, northPerimeterRow),
            (dstInterTravelCol, northPerimeterRow),
            (dstInterTravelCol, r_dst),
            (dstInterLaneCol, r_dst),
            (dstInterFanEnd - 1, r_dst),
            (dstInterFanEnd, r_dst),
        ]
        retPointsRaw = [
            (dstInterFanEnd, r_dst_ret),
            (dstInterFanEnd - 1, r_dst_ret),
            (dstInterLaneCol, r_dst_ret),
            (dstInterTravelCol, r_dst_ret),
            (dstInterTravelCol, southPerimeterRow),
            (srcInterTravelCol, southPerimeterRow),
            (srcInterTravelCol, r_src_ret),
            (srcInterLaneCol, r_src_ret),
            (srcInterFanStart + 1, r_src_ret),
            (srcInterFanStart, r_src_ret),
        ]
        intraRegionIds = (
            sourceTerminalRegion.routingZoneRegionId,
            interFanE.value.routingZoneRegionId,
            interLongE.value.routingZoneRegionId,
            interLatN.value.routingZoneRegionId,
            interLongW.value.routingZoneRegionId,
            interFanW.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds = (
            destinationTerminalRegion.routingZoneRegionId,
            interFanW.value.routingZoneRegionId,
            interLongW.value.routingZoneRegionId,
            interLatS.value.routingZoneRegionId,
            interLongE.value.routingZoneRegionId,
            interFanE.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )

    fwdPtsResult = _routePoints_build(fwdPointsRaw)
    if not result_isOkCheck(fwdPtsResult):
        return resultErr_build()

    fwdRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindForward,
        routePoints=fwdPtsResult.value,
        traversedRegionIds=intraRegionIds,
    )
    if not result_isOkCheck(fwdRouteResult):
        return resultErr_build()

    retPtsResult = _routePoints_build(retPointsRaw)
    if not result_isOkCheck(retPtsResult):
        return resultErr_build()

    retRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.destinationChipRef,
        destinationChipRef=obligation.sourceChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindReturn,
        routePoints=retPtsResult.value,
        traversedRegionIds=retRegionIds,
    )
    if not result_isOkCheck(retRouteResult):
        return resultErr_build()

    return resultOk_build((fwdRouteResult.value, retRouteResult.value))


# ---------------------------------------------------------------------------
# NTS solver
# ---------------------------------------------------------------------------


def _ntsRoutePairResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligation: CallRouteObligation,
    localLaneIndex: int,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceTerminalRegion: RoutingZoneRegion,
    destinationTerminalRegion: RoutingZoneRegion,
) -> Result[tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]]:
    """Build forward + return solved route pair for one NTS ZONE_LOCAL obligation."""

    fanN = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.NORTH
    )
    fanS = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, RoutingZoneRegionSide.SOUTH
    )
    longW = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.WEST
    )
    longE = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, RoutingZoneRegionSide.EAST
    )
    latN = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.NORTH
    )
    latS = routingZoneRegionForKindAndSideResult_get(
        zone, RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, RoutingZoneRegionSide.SOUTH
    )
    if not all(
        result_isOkCheck(r) for r in [fanN, fanS, longW, longE, latN, latS]
    ):
        return resultErr_build()

    # Look up chip widths so port columns can be computed from slot boundaries.
    srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.destinationChipRef.chipId
    )
    if not (result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)):
        return resultErr_build()
    srcLines = chipDrawLines_build(srcChipResult.value)
    dstLines = chipDrawLines_build(dstChipResult.value)
    srcChipW: int = max((len(line) for line in srcLines), default=1)
    dstChipW: int = max((len(line) for line in dstLines), default=1)

    # For NTS chips stacked horizontally each slot = chipWidth + 2 cols
    # (1 corridor col left, chip body, 1 corridor col right).
    # Port col = slotStart + 1 + _HEADER + 2*portIndex.
    _HEADER: int = 3

    portIndex: int = obligation.childCallIndex
    fanN_row: int = fanN.value.routingZoneRegionFrame.verticalStart
    fanS_row: int = fanS.value.routingZoneRegionFrame.verticalStart
    longW_col: int = longW.value.routingZoneRegionFrame.horizontalStart
    longE_col: int = longE.value.routingZoneRegionFrame.horizontalStart
    latN_row: int = latN.value.routingZoneRegionFrame.verticalStart
    latS_row: int = latS.value.routingZoneRegionFrame.verticalStart

    c_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex * (srcChipW + 2)
        + 1 + _HEADER + 2 * portIndex
    )
    c_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.horizontalStart
        + destinationPlacement.orderIndex * (dstChipW + 2)
        + 1 + _HEADER
    )
    c_src_ret: int = c_src + 1
    c_dst_ret: int = c_dst + 1

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = destinationPlacement.chipTerminalRegionId.routingZoneRegionSide

    if (
        sourceSide is RoutingZoneRegionSide.NORTH
        and destinationSide is RoutingZoneRegionSide.SOUTH
    ):
        forwardLaneIndex: int = 2 * localLaneIndex
        returnLaneIndex: int = forwardLaneIndex + 1
        fwd_lane_top: int = latN_row - forwardLaneIndex
        # Peel columns step by 1 (not 2) so they stay east/west of all source-port
        # columns (which also step by 2, starting from X+4).  Using 2× spacing
        # caused peel(k) = c_src(N-1-k) for N≥3 — a same-axis collision.
        fwd_lane_right: int = longE_col - localLaneIndex
        fwd_lane_bottom: int = latS_row + forwardLaneIndex
        ret_lane_left: int = longW_col + localLaneIndex
        ret_lane_top: int = latN_row - returnLaneIndex
        ret_lane_bottom: int = latS_row + returnLaneIndex
        solveKindForward = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        fwdPointsRaw: list[tuple[int, int]] = [
            (c_src,       fanN_row),
            (c_src,       fwd_lane_top),
            (fwd_lane_right,  fwd_lane_top),
            (fwd_lane_right,  fwd_lane_bottom),
            (c_dst,       fwd_lane_bottom),
            (c_dst,       fanS_row),
        ]
        retPointsRaw: list[tuple[int, int]] = [
            (c_dst_ret,  fanS_row),
            (c_dst_ret,  ret_lane_bottom),
            (ret_lane_left,  ret_lane_bottom),
            (ret_lane_left,  ret_lane_top),
            (c_src_ret,  ret_lane_top),
            (c_src_ret,  fanN_row),
        ]
        intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanN.value.routingZoneRegionId,
            latN.value.routingZoneRegionId,
            longE.value.routingZoneRegionId,
            latS.value.routingZoneRegionId,
            fanS.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds: tuple[RoutingZoneRegionId, ...] = (
            destinationTerminalRegion.routingZoneRegionId,
            fanS.value.routingZoneRegionId,
            latS.value.routingZoneRegionId,
            longW.value.routingZoneRegionId,
            latN.value.routingZoneRegionId,
            fanN.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )
    else:
        laneIndex: int = localLaneIndex
        interFanN = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.NORTH,
        )
        interFanS = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionSide.SOUTH,
        )
        interLongW = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.WEST,
        )
        interLongE = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionSide.EAST,
        )
        interLatN = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.NORTH,
        )
        interLatS = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            RoutingZoneRegionSide.SOUTH,
        )
        if not all(
            result_isOkCheck(r)
            for r in [
                interFanN,
                interFanS,
                interLongW,
                interLongE,
                interLatN,
                interLatS,
            ]
        ):
            return resultErr_build()

        solveKindForward = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        solveKindReturn = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
        srcInterFanStart: int = (
            interFanS.value.routingZoneRegionFrame.verticalStart
        )
        dstInterFanStart: int = (
            interFanN.value.routingZoneRegionFrame.verticalStart
        )
        dstInterFanEnd: int = (
            interFanN.value.routingZoneRegionFrame.verticalEnd_calculate() - 1
        )
        southTravelRow: int = (
            interLatS.value.routingZoneRegionFrame.verticalStart + laneIndex
        )
        northTravelRow: int = (
            interLatN.value.routingZoneRegionFrame.verticalStart + laneIndex
        )
        westPerimeterCol: int = (
            interLongW.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        eastPerimeterCol: int = (
            interLongE.value.routingZoneRegionFrame.horizontalStart + laneIndex
        )
        srcInterLaneRow: int = srcInterFanStart + 2 + laneIndex
        dstInterLaneRow: int = dstInterFanStart + laneIndex

        fwdPointsRaw = [
            (c_src, srcInterFanStart),
            (c_src, srcInterFanStart + 1),
            (c_src, srcInterLaneRow),
            (c_src, southTravelRow),
            (westPerimeterCol, southTravelRow),
            (westPerimeterCol, northTravelRow),
            (c_dst, northTravelRow),
            (c_dst, dstInterLaneRow),
            (c_dst, dstInterFanEnd - 1),
            (c_dst, dstInterFanEnd),
        ]
        retPointsRaw = [
            (c_dst_ret, dstInterFanEnd),
            (c_dst_ret, dstInterFanEnd - 1),
            (c_dst_ret, dstInterLaneRow),
            (c_dst_ret, northTravelRow),
            (eastPerimeterCol, northTravelRow),
            (eastPerimeterCol, southTravelRow),
            (c_src_ret, southTravelRow),
            (c_src_ret, srcInterLaneRow),
            (c_src_ret, srcInterFanStart + 1),
            (c_src_ret, srcInterFanStart),
        ]
        intraRegionIds = (
            sourceTerminalRegion.routingZoneRegionId,
            interFanS.value.routingZoneRegionId,
            interLatS.value.routingZoneRegionId,
            interLongW.value.routingZoneRegionId,
            interLatN.value.routingZoneRegionId,
            interFanN.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds = (
            destinationTerminalRegion.routingZoneRegionId,
            interFanN.value.routingZoneRegionId,
            interLatN.value.routingZoneRegionId,
            interLongE.value.routingZoneRegionId,
            interLatS.value.routingZoneRegionId,
            interFanS.value.routingZoneRegionId,
            sourceTerminalRegion.routingZoneRegionId,
        )

    fwdPtsResult = _routePoints_build(fwdPointsRaw)
    if not result_isOkCheck(fwdPtsResult):
        return resultErr_build()

    fwdRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindForward,
        routePoints=fwdPtsResult.value,
        traversedRegionIds=intraRegionIds,
    )
    if not result_isOkCheck(fwdRouteResult):
        return resultErr_build()

    retPtsResult = _routePoints_build(retPointsRaw)
    if not result_isOkCheck(retPtsResult):
        return resultErr_build()

    retRouteResult = routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.destinationChipRef,
        destinationChipRef=obligation.sourceChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=solveKindReturn,
        routePoints=retPtsResult.value,
        traversedRegionIds=retRegionIds,
    )
    if not result_isOkCheck(retRouteResult):
        return resultErr_build()

    return resultOk_build((fwdRouteResult.value, retRouteResult.value))


# ---------------------------------------------------------------------------
# Same-side local (self-call)
# ---------------------------------------------------------------------------


def _sameSideLocalRouteResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligation: CallRouteObligation,
    sourcePlacement: ChipPlacement,
    destinationPlacement: ChipPlacement,
    sourceTerminalRegion: RoutingZoneRegion,
    destinationTerminalRegion: RoutingZoneRegion,
) -> Result[RoutingZoneLocalSolvedRoute]:
    """Build a same-side local loop for a self-call obligation."""

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    assert sourceSide is not None

    # Look up the chip so port offset can be computed from slot boundaries.
    chipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    if not result_isOkCheck(chipResult):
        return resultErr_build()
    chipLines = chipDrawLines_build(chipResult.value)
    _HEADER: int = 3

    if zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        fanResult = routingZoneRegionForKindAndSideResult_get(
            zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, sourceSide
        )
        longResult = routingZoneRegionForKindAndSideResult_get(
            zone, RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE, sourceSide
        )
        if not result_isOkCheck(fanResult) or not result_isOkCheck(longResult):
            return resultErr_build()

        chipH: int = len(chipLines)
        r = (
            sourceTerminalRegion.routingZoneRegionFrame.verticalStart
            + sourcePlacement.orderIndex * (chipH + 2)
            + 1 + _HEADER
        )
        chipCol = sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
        fanCol = fanResult.value.routingZoneRegionFrame.horizontalStart
        longCol = longResult.value.routingZoneRegionFrame.horizontalStart

        pointsRaw: list[tuple[int, int]] = [
            (chipCol, r),
            (fanCol,  r),
            (longCol, r),
            (fanCol,  r),
            (chipCol, r),
        ]
        traversedIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            longResult.value.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
    else:
        fanResult = routingZoneRegionForKindAndSideResult_get(
            zone, RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT, sourceSide
        )
        latResult = routingZoneRegionForKindAndSideResult_get(
            zone, RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE, sourceSide
        )
        if not result_isOkCheck(fanResult) or not result_isOkCheck(latResult):
            return resultErr_build()

        chipW: int = max((len(line) for line in chipLines), default=1)
        c = (
            sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
            + sourcePlacement.orderIndex * (chipW + 2)
            + 1 + _HEADER
        )
        chipRow = sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        fanRow = fanResult.value.routingZoneRegionFrame.verticalStart
        latRow = latResult.value.routingZoneRegionFrame.verticalStart

        pointsRaw = [
            (c, chipRow),
            (c, fanRow),
            (c, latRow),
            (c, fanRow),
            (c, chipRow),
        ]
        traversedIds = (
            sourceTerminalRegion.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            latResult.value.routingZoneRegionId,
            fanResult.value.routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )

    ptsResult = _routePoints_build(pointsRaw)
    if not result_isOkCheck(ptsResult):
        return resultErr_build()

    return routingZoneLocalSolvedRouteResult_build(
        owningRoutingZoneId=zone.routingZoneId,
        sourceChipRef=obligation.sourceChipRef,
        destinationChipRef=obligation.destinationChipRef,
        childCallIndex=obligation.childCallIndex,
        solveKind=RoutingZoneLocalRouteSolveKind.SAME_SIDE_LOCAL,
        routePoints=ptsResult.value,
        traversedRegionIds=traversedIds,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _routePoints_build(
    raw: list[tuple[int, int]],
) -> Result[tuple[RoutingZoneRoutePoint, ...]]:
    """Build a validated tuple of route points from (h, v) pairs."""

    pointsMutable: list[RoutingZoneRoutePoint] = []
    for h, v in raw:
        ptResult = routingZoneRoutePointResult_build(
            horizontalIndex=h, verticalIndex=v
        )
        if not result_isOkCheck(ptResult):
            return resultErr_build()
        pointsMutable.append(ptResult.value)
    return resultOk_build(tuple(pointsMutable))


def _zoneOwningChipResult_build(
    placedRoutingZoneGrid: RoutingZoneGrid,
    chipRef,
) -> Result[RoutingZone]:
    """Build the placed routing zone that owns one chip."""

    routingZone: RoutingZone
    for routingZone in placedRoutingZoneGrid.routingZoneSet.routingZones:
        placement = routingZone.chipPlacementSet.placementForChipOrNone_get(chipRef)
        if placement is not None:
            return resultOk_build(routingZone)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.zone_solver.missing_chip_zone",
        message="Placed RoutingZoneGrid does not contain the requested chip",
    )
    return resultErr_build()
