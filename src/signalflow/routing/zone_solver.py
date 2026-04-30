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
    RoutingLaneAttachmentSense,
    RoutingLanePackingPolicy,
    RoutingOccupancyPolicy,
    RoutingZone,
    RoutingZoneGrid,
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
from signalflow.routing.kernel_solver import (
    WTE_EXTRA_CONTEXT,
    routingKernelSolvedRouteSetResult_build,
)
from signalflow.routing.route import routePoints_realize
from signalflow.routing.track import TrackDirection


def zoneLocalSolvedRoutesResult_build(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneLocalSolvedRouteSet]:
    """Build solved zone-local routes from placed local geometry."""

    return (
        routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
            circuitDocument,
            placedRoutingZoneGrid,
            callRouteObligationSet,
        )
    )


def routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations(
    circuitDocument: CircuitDocument,
    placedRoutingZoneGrid: RoutingZoneGrid,
    callRouteObligationSet: CallRouteObligationSet,
) -> Result[RoutingZoneLocalSolvedRouteSet]:
    """Build solved zone-local routes from geometry and obligations."""

    forwardRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    returnRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    laneIndexByObligationKey: dict[
        tuple[ChipRef, ChipRef, int],
        int,
    ] = _zoneLocalLaneIndexByObligationKey_build(
        placedRoutingZoneGrid=placedRoutingZoneGrid,
        callRouteObligationSet=callRouteObligationSet,
    )
    wteIntraObligationsByZoneId: dict[
        RoutingZoneId, list[CallRouteObligation]
    ] = {}
    wteExtraObligationsByZoneId: dict[
        RoutingZoneId, list[CallRouteObligation]
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
        destinationZoneResult: Result[RoutingZone] = (
            _zoneOwningChipResult_build(
                placedRoutingZoneGrid=placedRoutingZoneGrid,
                chipRef=callRouteObligation.destinationChipRef,
            )
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
            sourceZoneResult.value.routingZoneSense
            is RoutingZoneSense.WEST_TO_EAST
            and sourceZoneResult.value.routingZoneId
            == destinationZoneResult.value.routingZoneId
            and callRouteObligation.zoneLocalGeometryKind
            is ZoneLocalGeometryKind.INTRA_PARENT_TOCHILD
            and sourceSide is RoutingZoneRegionSide.WEST
            and destinationSide is RoutingZoneRegionSide.EAST
        ):
            wteIntraObligationsByZoneId.setdefault(
                sourceZoneResult.value.routingZoneId,
                [],
            ).append(callRouteObligation)
            continue

        if (
            sourceZoneResult.value.routingZoneSense
            is RoutingZoneSense.WEST_TO_EAST
            and sourceZoneResult.value.routingZoneId
            == destinationZoneResult.value.routingZoneId
            and callRouteObligation.zoneLocalGeometryKind
            in {
                ZoneLocalGeometryKind.OUTER_CHILD_TOPARENT,
                ZoneLocalGeometryKind.OUTER_CHILD_UTURN,
                ZoneLocalGeometryKind.OUTER_PARENT_UTURN,
            }
            and (
                (
                    callRouteObligation.zoneLocalGeometryKind
                    is ZoneLocalGeometryKind.OUTER_CHILD_TOPARENT
                    and sourceSide is RoutingZoneRegionSide.EAST
                    and destinationSide is RoutingZoneRegionSide.WEST
                )
                or (
                    callRouteObligation.zoneLocalGeometryKind
                    is ZoneLocalGeometryKind.OUTER_CHILD_UTURN
                    and sourceSide is RoutingZoneRegionSide.EAST
                    and destinationSide is RoutingZoneRegionSide.EAST
                )
                or (
                    callRouteObligation.zoneLocalGeometryKind
                    is ZoneLocalGeometryKind.OUTER_PARENT_UTURN
                    and sourceSide is RoutingZoneRegionSide.WEST
                    and destinationSide is RoutingZoneRegionSide.WEST
                )
            )
        ):
            wteExtraObligationsByZoneId.setdefault(
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
    for (
        routingZoneId,
        groupedObligations,
    ) in wteIntraObligationsByZoneId.items():
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
            firstSrcPlacement = (
                zone.chipPlacementSet.placementForChipOrNone_get(
                    groupedObligations[0].sourceChipRef
                )
            )
            if firstSrcPlacement is not None:
                regionId = firstSrcPlacement.chipTerminalRegionId
                srcSideForGroup = regionId.routingZoneRegionSide
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
        # those sharing the same destinationChipRef.
        dstPortRankCounter: dict = {}
        dstPortIndices: list[int] = []
        for obligation in groupedObligations:
            dstKey = obligation.destinationChipRef.chipId
            rank = dstPortRankCounter.get(dstKey, 0)
            dstPortIndices.append(rank)
            dstPortRankCounter[dstKey] = rank + 1

        kernelObligations: list[KernelObligation] = []
        for obligation, laneIdx, dstPortIdx in zip(
            groupedObligations, laneOrder, dstPortIndices, strict=False
        ):
            srcPlacementResult = (
                zone.chipPlacementSet.placementForChipResult_get(
                    obligation.sourceChipRef
                )
            )
            dstPlacementResult = (
                zone.chipPlacementSet.placementForChipResult_get(
                    obligation.destinationChipRef
                )
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

    for (
        routingZoneId,
        groupedObligations,
    ) in wteExtraObligationsByZoneId.items():
        zoneResult = placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
        if not result_isOkCheck(zoneResult):
            return resultErr_build()
        zone = zoneResult.value

        if zone.intraKernel is None:
            return resultErr_build()

        srcSideForGroup = None
        if groupedObligations:
            firstSrcPlacement = (
                zone.chipPlacementSet.placementForChipOrNone_get(
                    groupedObligations[0].sourceChipRef
                )
            )
            if firstSrcPlacement is not None:
                regionId = firstSrcPlacement.chipTerminalRegionId
                srcSideForGroup = regionId.routingZoneRegionSide
        attachSense = (
            _attachmentSenseForSide_get(zone, srcSideForGroup)
            if srcSideForGroup is not None
            else RoutingLaneAttachmentSense.FROM_START
        )
        laneOrder = _laneIndicesInSenseOrder_build(
            laneCount=len(groupedObligations),
            laneSense=attachSense,
        )

        dstPortRankCounter: dict = {}
        dstPortIndices: list[int] = []
        for obligation in groupedObligations:
            dstKey = obligation.destinationChipRef.chipId
            rank = dstPortRankCounter.get(dstKey, 0)
            dstPortIndices.append(rank)
            dstPortRankCounter[dstKey] = rank + 1

        kernelObligations_extra: list[KernelObligation] = []
        for obligation, laneIdx, dstPortIdx in zip(
            groupedObligations, laneOrder, dstPortIndices, strict=False
        ):
            srcPlacementResult = (
                zone.chipPlacementSet.placementForChipResult_get(
                    obligation.sourceChipRef
                )
            )
            dstPlacementResult = (
                zone.chipPlacementSet.placementForChipResult_get(
                    obligation.destinationChipRef
                )
            )
            if not (
                result_isOkCheck(srcPlacementResult)
                and result_isOkCheck(dstPlacementResult)
            ):
                return resultErr_build()
            kernelObligations_extra.append(
                KernelObligation(
                    callRouteObligation=obligation,
                    sourcePlacement=srcPlacementResult.value,
                    destinationPlacement=dstPlacementResult.value,
                    destinationPortIndex=dstPortIdx,
                    laneIndex=laneIdx,
                )
            )

        extraRouteResult = routingKernelSolvedRouteSetResult_build(
            circuitDocument=circuitDocument,
            kernel=zone.intraKernel,
            obligations=kernelObligations_extra,
            context=WTE_EXTRA_CONTEXT,
        )
        if not result_isOkCheck(extraRouteResult):
            return resultErr_build()
        forwardRoutesMutable.extend(extraRouteResult.value[0])
        returnRoutesMutable.extend(extraRouteResult.value[1])

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
        destinationZoneResult: Result[RoutingZone] = (
            _zoneOwningChipResult_build(
                placedRoutingZoneGrid=placedRoutingZoneGrid,
                chipRef=callRouteObligation.destinationChipRef,
            )
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
        destinationPlacement = (
            zone.chipPlacementSet.placementForChipOrNone_get(
                callRouteObligation.destinationChipRef
            )
        )
        if sourcePlacement is None or destinationPlacement is None:
            continue

        obligationKey: tuple[ChipRef, ChipRef, int] = (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        )
        sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
        if sourceSide is None:
            continue

        if callRouteObligation.zoneLocalGeometryKind in {
            ZoneLocalGeometryKind.OUTER_CHILD_TOPARENT,
            ZoneLocalGeometryKind.OUTER_CHILD_UTURN,
            ZoneLocalGeometryKind.OUTER_PARENT_UTURN,
        }:
            groupKey: tuple[RoutingZoneId, str, RoutingZoneRegionSide] = (
                zone.routingZoneId,
                "inter",
                sourceSide,
            )
            groupedObligationKeysByGroupKey.setdefault(groupKey, []).append(
                obligationKey
            )
            laneSenseByGroupKey[groupKey] = _attachmentSenseForSide_get(
                zone,
                sourceSide,
            )
            continue

        groupKey = (
            zone.routingZoneId,
            "intra",
            sourceSide,
        )
        groupedObligationKeysByGroupKey.setdefault(groupKey, []).append(
            obligationKey
        )
        laneSenseByGroupKey[groupKey] = _attachmentSenseForSide_get(
            zone,
            sourceSide,
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
        for obligationKey, laneIndex in zip(
            obligationKeys, laneOrder, strict=True
        ):
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
    zoneRegionSet: RoutingZoneRegionSet,
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
        message="Requested tagged RoutingZoneRegion is absent",
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
    """Return whether route is compatible with WTE occupancy."""

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
    """Commit one WTE route's realized cells into occupancy map."""

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
    """Build abstract strip reservations for one WTE candidate."""

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
    """Build deterministic candidate lane triples for policy."""

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
    """Return contiguous lane windows in requested sense order."""

    if windowSize > len(laneOrder):
        return ()
    return tuple(
        tuple(laneOrder[startIndex : startIndex + windowSize])
        for startIndex in range(len(laneOrder) - windowSize + 1)
    )


def _routeLengthScore_calculate(route: RoutingZoneLocalSolvedRoute) -> int:
    """Calculate Manhattan route length from ordered route points."""

    totalLength: int = 0
    pointIndex: int
    for pointIndex in range(len(route.routePoints) - 1):
        currentPoint = route.routePoints[pointIndex]
        nextPoint = route.routePoints[pointIndex + 1]
        totalLength += abs(
            nextPoint.horizontalIndex - currentPoint.horizontalIndex
        )
        totalLength += abs(
            nextPoint.verticalIndex - currentPoint.verticalIndex
        )
    return totalLength


def _wteBundleWindowRoutesResult_build(
    *,
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligations: tuple[CallRouteObligation, ...],
    firstLaneWindow: tuple[int, ...],
    latLaneWindow: tuple[int, ...],
    thirdLaneWindow: tuple[int, ...],
    sourcePlacementByObligationKey: dict[
        tuple[ChipRef, ChipRef, int], ChipPlacement
    ],
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
    """Build one WTE bundle against contiguous lane windows."""

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
    routePoints: tuple[RoutingZoneRoutePoint, ...],
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
                message="Realized route cell is outside owned regions",
                context=(str(cell.worldCol), str(cell.worldRow)),
            )
            return resultErr_build()
        if len(matchingIds) != 1:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone_solver.local_route.cell_in_multiple_regions",
                message="Realized route cell lies in multiple owned regions",
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
) -> Result[
    tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]
]:
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
            message="Zone-local obligations must stay inside one routing zone",
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
    """Build one WTE INTRA route using candidate lane index."""

    fanW = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RoutingZoneRegionSide.WEST,
    )
    fanE = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RoutingZoneRegionSide.EAST,
    )
    latN = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        RoutingZoneRegionSide.NORTH,
    )
    latS = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        RoutingZoneRegionSide.SOUTH,
    )
    northTransitionW = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet
        if zone.intraKernel
        else RoutingZoneRegionSet(),
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        RoutingZoneRegionSide.WEST,
        "north",
    )
    southTransitionW = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet
        if zone.intraKernel
        else RoutingZoneRegionSet(),
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        RoutingZoneRegionSide.WEST,
        "south",
    )
    northTransitionE = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet
        if zone.intraKernel
        else RoutingZoneRegionSet(),
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        RoutingZoneRegionSide.EAST,
        "north",
    )
    southTransitionE = _regionForKindSideAndTagResult_get(
        zone.intraKernel.routingZoneRegionSet
        if zone.intraKernel
        else RoutingZoneRegionSet(),
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
            message="WTE INTRA longitude segments are absent",
        )
        return resultErr_build()

    srcChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.sourceChipRef.chipId
    )
    dstChipResult = circuitDocument.circuitChipSet.chipResult_get(
        obligation.destinationChipRef.chipId
    )
    if not (
        result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)
    ):
        return resultErr_build()
    srcChipH: int = len(chipDrawLines_build(srcChipResult.value))
    dstChipH: int = len(chipDrawLines_build(dstChipResult.value))
    _HEADER: int = 3

    portIndex: int = obligation.childCallIndex
    fanW_col: int = fanW.unwrap().routingZoneRegionFrame.horizontalStart
    fanE_col: int = fanE.unwrap().routingZoneRegionFrame.horizontalStart
    longW_start: int = longWRegions[0].routingZoneRegionFrame.horizontalStart
    longE_start: int = longERegions[0].routingZoneRegionFrame.horizontalStart
    latN_start: int = latN.unwrap().routingZoneRegionFrame.verticalStart
    latS_start: int = latS.unwrap().routingZoneRegionFrame.verticalStart

    r_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipH + 2)
        + 1
        + _HEADER
        + 2 * portIndex
    )
    r_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipH + 2)
        + 1
        + _HEADER
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


def UNUSED_wteOccupancySolvedRoutesResult_build(
    circuitDocument: CircuitDocument,
    zone: RoutingZone,
    obligations: tuple[CallRouteObligation, ...],
) -> Result[
    tuple[
        tuple[RoutingZoneLocalSolvedRoute, ...],
        tuple[RoutingZoneLocalSolvedRoute, ...],
    ]
]:
    """Build WTE routes by first legal occupancy."""

    occupiedDirectionsByCell: dict[
        tuple[int, int], frozenset[TrackDirection]
    ] = {}
    occupiedStripKeys: set[tuple[str, int]] = set()
    forwardRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []
    returnRoutesMutable: list[RoutingZoneLocalSolvedRoute] = []

    longWResult = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionSide.WEST,
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
        sourcePlacementResult = (
            zone.chipPlacementSet.placementForChipResult_get(
                obligation.sourceChipRef
            )
        )
        destinationPlacementResult = (
            zone.chipPlacementSet.placementForChipResult_get(
                obligation.destinationChipRef
            )
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
        sourcePlacementByObligationKey[obligationKey] = (
            sourcePlacementResult.value
        )
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
        bestForwardRoutes: tuple[RoutingZoneLocalSolvedRoute, ...] | None = (
            None
        )
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
                for (
                    forwardThirdWindowIndex,
                    forwardThirdLaneWindow,
                ) in enumerate(forwardThirdLaneWindows):
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
) -> Result[
    tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]
]:
    """Build forward + return route pair for WTE obligation."""

    fanW = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RoutingZoneRegionSide.WEST,
    )
    fanE = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RoutingZoneRegionSide.EAST,
    )
    longW = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionSide.WEST,
    )
    longE = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionSide.EAST,
    )
    latN = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        RoutingZoneRegionSide.NORTH,
    )
    latS = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        RoutingZoneRegionSide.SOUTH,
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
    if not (
        result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)
    ):
        return resultErr_build()
    srcChipH: int = len(chipDrawLines_build(srcChipResult.value))
    dstChipH: int = len(chipDrawLines_build(dstChipResult.value))

    # Chip body layout has 3 header rows before ports.
    _HEADER: int = 3

    portIndex: int = obligation.childCallIndex
    fanW_col: int = fanW.unwrap().routingZoneRegionFrame.horizontalStart
    fanE_col: int = fanE.unwrap().routingZoneRegionFrame.horizontalStart
    longW_start: int = longW.unwrap().routingZoneRegionFrame.horizontalStart
    longE_end: int = (
        longE.unwrap().routingZoneRegionFrame.horizontalEnd_calculate() - 1
    )
    latN_end: int = (
        latN.unwrap().routingZoneRegionFrame.verticalEnd_calculate() - 1
    )
    latS_start: int = latS.unwrap().routingZoneRegionFrame.verticalStart

    # r_src / r_dst: the actual port rows inside the chip body.
    # Each chip slot = chipHeight + 2 rows.
    # Port row = slotStart + 1 + _HEADER + port offset.
    # Each east terminal occupies 2 body rows: signal at 2k, return at 2k+1.
    # Source port index k = which call in the source chip's outgoing call list.
    # Destination port index = 0 (first input port of the destination chip).
    r_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.verticalStart
        + sourcePlacement.orderIndex * (srcChipH + 2)
        + 1
        + _HEADER
        + 2 * portIndex
    )
    r_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.verticalStart
        + destinationPlacement.orderIndex * (dstChipH + 2)
        + 1
        + _HEADER
    )
    r_src_ret: int = r_src + 1
    r_dst_ret: int = r_dst + 1

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = (
        destinationPlacement.chipTerminalRegionId.routingZoneRegionSide
    )

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
        solveKindForward = (
            RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        )
        solveKindReturn = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        # Forward: top half of clockwise INTRA rectangle (W→E).
        fwdPointsRaw: list[tuple[int, int]] = [
            (fanW_col, r_src),
            (fwd_lane_left, r_src),
            (fwd_lane_left, fwd_lane_top),
            (fwd_lane_right, fwd_lane_top),
            (fwd_lane_right, r_dst),
            (fanE_col, r_dst),
        ]
        retPointsRaw: list[tuple[int, int]] = [
            (fanE_col, r_dst_ret),
            (ret_lane_right, r_dst_ret),
            (ret_lane_right, ret_lane_bottom),
            (ret_lane_left, ret_lane_bottom),
            (ret_lane_left, r_src_ret),
            (fanW_col, r_src_ret),
        ]
        intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanW.unwrap().routingZoneRegionId,
            longW.unwrap().routingZoneRegionId,
            latN.unwrap().routingZoneRegionId,
            longE.unwrap().routingZoneRegionId,
            fanE.unwrap().routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds: tuple[RoutingZoneRegionId, ...] = (
            destinationTerminalRegion.routingZoneRegionId,
            fanE.unwrap().routingZoneRegionId,
            longE.unwrap().routingZoneRegionId,
            latS.unwrap().routingZoneRegionId,
            longW.unwrap().routingZoneRegionId,
            fanW.unwrap().routingZoneRegionId,
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

        solveKindForward = (
            RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        )
        solveKindReturn = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
        srcInterFanStart: int = (
            interFanE.unwrap().routingZoneRegionFrame.horizontalStart
        )
        dstInterFanStart: int = (
            interFanW.unwrap().routingZoneRegionFrame.horizontalStart
        )
        dstInterFanEnd: int = (
            interFanW.unwrap().routingZoneRegionFrame.horizontalEnd_calculate()
            - 1
        )
        srcInterTravelCol: int = (
            interLongE.unwrap().routingZoneRegionFrame.horizontalStart
            + laneIndex
        )
        dstInterTravelCol: int = (
            interLongW.unwrap().routingZoneRegionFrame.horizontalStart
            + laneIndex
        )
        srcInterLaneCol: int = srcInterFanStart + 2 + laneIndex
        dstInterLaneCol: int = dstInterFanStart + laneIndex
        northPerimeterRow: int = (
            interLatN.unwrap().routingZoneRegionFrame.verticalStart
        )
        southPerimeterRow: int = (
            interLatS.unwrap().routingZoneRegionFrame.verticalStart
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
            interFanE.unwrap().routingZoneRegionId,
            interLongE.unwrap().routingZoneRegionId,
            interLatN.unwrap().routingZoneRegionId,
            interLongW.unwrap().routingZoneRegionId,
            interFanW.unwrap().routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds = (
            destinationTerminalRegion.routingZoneRegionId,
            interFanW.unwrap().routingZoneRegionId,
            interLongW.unwrap().routingZoneRegionId,
            interLatS.unwrap().routingZoneRegionId,
            interLongE.unwrap().routingZoneRegionId,
            interFanE.unwrap().routingZoneRegionId,
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
) -> Result[
    tuple[RoutingZoneLocalSolvedRoute, RoutingZoneLocalSolvedRoute | None]
]:
    """Build forward + return route pair for NTS obligation."""

    fanN = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RoutingZoneRegionSide.NORTH,
    )
    fanS = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RoutingZoneRegionSide.SOUTH,
    )
    longW = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionSide.WEST,
    )
    longE = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionSide.EAST,
    )
    latN = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        RoutingZoneRegionSide.NORTH,
    )
    latS = routingZoneRegionForKindAndSideResult_get(
        zone,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        RoutingZoneRegionSide.SOUTH,
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
    if not (
        result_isOkCheck(srcChipResult) and result_isOkCheck(dstChipResult)
    ):
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
    fanN_row: int = fanN.unwrap().routingZoneRegionFrame.verticalStart
    fanS_row: int = fanS.unwrap().routingZoneRegionFrame.verticalStart
    longW_col: int = longW.unwrap().routingZoneRegionFrame.horizontalStart
    longE_col: int = longE.unwrap().routingZoneRegionFrame.horizontalStart
    latN_row: int = latN.unwrap().routingZoneRegionFrame.verticalStart
    latS_row: int = latS.unwrap().routingZoneRegionFrame.verticalStart

    c_src: int = (
        sourceTerminalRegion.routingZoneRegionFrame.horizontalStart
        + sourcePlacement.orderIndex * (srcChipW + 2)
        + 1
        + _HEADER
        + 2 * portIndex
    )
    c_dst: int = (
        destinationTerminalRegion.routingZoneRegionFrame.horizontalStart
        + destinationPlacement.orderIndex * (dstChipW + 2)
        + 1
        + _HEADER
    )
    c_src_ret: int = c_src + 1
    c_dst_ret: int = c_dst + 1

    sourceSide = sourcePlacement.chipTerminalRegionId.routingZoneRegionSide
    destinationSide = (
        destinationPlacement.chipTerminalRegionId.routingZoneRegionSide
    )

    if (
        sourceSide is RoutingZoneRegionSide.NORTH
        and destinationSide is RoutingZoneRegionSide.SOUTH
    ):
        forwardLaneIndex: int = 2 * localLaneIndex
        returnLaneIndex: int = forwardLaneIndex + 1
        fwd_lane_top: int = latN_row - forwardLaneIndex
        # Peel columns step by 1 to stay outside source-port columns.
        # Using 2x spacing caused same-axis collision for N>=3.
        fwd_lane_right: int = longE_col - localLaneIndex
        fwd_lane_bottom: int = latS_row + forwardLaneIndex
        ret_lane_left: int = longW_col + localLaneIndex
        ret_lane_top: int = latN_row - returnLaneIndex
        ret_lane_bottom: int = latS_row + returnLaneIndex
        solveKindForward = (
            RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_FORWARD
        )
        solveKindReturn = RoutingZoneLocalRouteSolveKind.CLOCKWISE_INTRA_RETURN
        fwdPointsRaw: list[tuple[int, int]] = [
            (c_src, fanN_row),
            (c_src, fwd_lane_top),
            (fwd_lane_right, fwd_lane_top),
            (fwd_lane_right, fwd_lane_bottom),
            (c_dst, fwd_lane_bottom),
            (c_dst, fanS_row),
        ]
        retPointsRaw: list[tuple[int, int]] = [
            (c_dst_ret, fanS_row),
            (c_dst_ret, ret_lane_bottom),
            (ret_lane_left, ret_lane_bottom),
            (ret_lane_left, ret_lane_top),
            (c_src_ret, ret_lane_top),
            (c_src_ret, fanN_row),
        ]
        intraRegionIds: tuple[RoutingZoneRegionId, ...] = (
            sourceTerminalRegion.routingZoneRegionId,
            fanN.unwrap().routingZoneRegionId,
            latN.unwrap().routingZoneRegionId,
            longE.unwrap().routingZoneRegionId,
            latS.unwrap().routingZoneRegionId,
            fanS.unwrap().routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds: tuple[RoutingZoneRegionId, ...] = (
            destinationTerminalRegion.routingZoneRegionId,
            fanS.unwrap().routingZoneRegionId,
            latS.unwrap().routingZoneRegionId,
            longW.unwrap().routingZoneRegionId,
            latN.unwrap().routingZoneRegionId,
            fanN.unwrap().routingZoneRegionId,
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

        solveKindForward = (
            RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_FORWARD
        )
        solveKindReturn = RoutingZoneLocalRouteSolveKind.INTER_PERIMETER_RETURN
        srcInterFanStart: int = (
            interFanS.unwrap().routingZoneRegionFrame.verticalStart
        )
        dstInterFanStart: int = (
            interFanN.unwrap().routingZoneRegionFrame.verticalStart
        )
        dstInterFanEnd: int = (
            interFanN.unwrap().routingZoneRegionFrame.verticalEnd_calculate()
            - 1
        )
        southTravelRow: int = (
            interLatS.unwrap().routingZoneRegionFrame.verticalStart + laneIndex
        )
        northTravelRow: int = (
            interLatN.unwrap().routingZoneRegionFrame.verticalStart + laneIndex
        )
        westPerimeterCol: int = (
            interLongW.unwrap().routingZoneRegionFrame.horizontalStart
            + laneIndex
        )
        eastPerimeterCol: int = (
            interLongE.unwrap().routingZoneRegionFrame.horizontalStart
            + laneIndex
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
            interFanS.unwrap().routingZoneRegionId,
            interLatS.unwrap().routingZoneRegionId,
            interLongW.unwrap().routingZoneRegionId,
            interLatN.unwrap().routingZoneRegionId,
            interFanN.unwrap().routingZoneRegionId,
            destinationTerminalRegion.routingZoneRegionId,
        )
        retRegionIds = (
            destinationTerminalRegion.routingZoneRegionId,
            interFanN.unwrap().routingZoneRegionId,
            interLatN.unwrap().routingZoneRegionId,
            interLongE.unwrap().routingZoneRegionId,
            interLatS.unwrap().routingZoneRegionId,
            interFanS.unwrap().routingZoneRegionId,
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
    chipRef: ChipRef,
) -> Result[RoutingZone]:
    """Build the placed routing zone that owns one chip."""

    routingZone: RoutingZone
    for routingZone in placedRoutingZoneGrid.routingZoneSet.routingZones:
        placement = routingZone.chipPlacementSet.placementForChipOrNone_get(
            chipRef
        )
        if placement is not None:
            return resultOk_build(routingZone)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.zone_solver.missing_chip_zone",
        message="Placed RoutingZoneGrid does not contain the requested chip",
    )
    return resultErr_build()
