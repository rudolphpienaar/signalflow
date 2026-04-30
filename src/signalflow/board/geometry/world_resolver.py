"""World-scale geometry harmonization for overlap-zone chains.

The production resolver follows the current `world_zone_inspect.py` truth
surface: zone-local geometry is harmonized first, shared seam chips are aligned
by row, and final world-column alignment is carried by a separate `wOffset`
recurrence.  It is not a global route re-solver.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from signalflow.board.geometry.georules import (
    GeoArgScalar,
    GeoChange,
    GeoOp,
    geometry_change,
)
from signalflow.board.geometry.mutation import boardRegionIdResult_fromSfN
from signalflow.board.geometry.zones import BoardGeometry, GeometryZone
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    TerminalPositionsByChip,
)
from signalflow.models import Result, RoutingZoneRegionFrame
from signalflow.models.result import result_isOkCheck
from signalflow.notation.sfn import sfN


@dataclass(frozen=True)
class SeamBudgets:
    """Compatibility carrier for older world-budget experiments.

    The active chain resolver does not use these full clearance budgets for
    final placement; it uses harmonized geometry plus `wOffset` terminal-column
    alignment.
    """

    horizontal: dict[tuple[int, int], int]
    vertical: dict[tuple[int, int], int]


@dataclass(frozen=True)
class WorldChainResolution:
    """Resolved geometry and offsets for one ordered overlap-zone chain."""

    geometryByIndex: dict[int, BoardGeometry]
    wOffsetsByIndex: dict[int, int]
    eastTerminalColumnByIndex: dict[int, int]
    westTerminalColumnByIndex: dict[int, int]

    def reoriginatedOffsets_get(
        self,
        originIndex: int,
    ) -> dict[int, int]:
        """Return offsets shifted so `originIndex` is column zero."""

        originShift: int = self.wOffsetsByIndex.get(originIndex, 0)
        return {
            index: offset - originShift
            for index, offset in self.wOffsetsByIndex.items()
        }


def _span_get(
    geometry: BoardGeometry,
    anchor: sfN,
    horizontal: bool,
) -> int:
    """Return horizontal or vertical span of one sfN region, 0 if absent."""

    ridResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(anchor)
    if result_isOkCheck(ridResult):
        rid: BoardRegionId = ridResult.value
        zone: GeometryZone | None = geometry.geometryZonesById.get(rid)
        if zone is not None:
            return (
                zone.frame.horizontalSpan
                if horizontal
                else zone.frame.verticalSpan
            )
    return 0


def _northRelaxationSpan_calculate(geometry: BoardGeometry) -> int:
    """Return the north-side relaxation span: Ne + Nt + Nfi."""

    return (
        _span_get(geometry, sfN.Ne, horizontal=False)
        + _span_get(geometry, sfN.Nt, horizontal=False)
        + _span_get(geometry, sfN.Nfi, horizontal=False)
    )


def _geometryFromParts_build(
    geometry: BoardGeometry,
    *,
    geometryZonesById: dict[BoardRegionId, GeometryZone],
    effectiveBoundaryFramesByName: dict[str, RoutingZoneRegionFrame],
) -> BoardGeometry:
    """Build a geometry while preserving orphan chip/terminal projections."""

    updated: BoardGeometry = BoardGeometry(
        geometryZonesById=geometryZonesById,
        effectiveBoundaryFramesByName=effectiveBoundaryFramesByName,
    )
    object.__setattr__(
        updated,
        "_orphanChipDrawPlacementsByChip",
        geometry._orphanChipDrawPlacementsByChip,
    )
    object.__setattr__(
        updated,
        "_orphanExactTerminalWorldPositionsByChip",
        geometry._orphanExactTerminalWorldPositionsByChip,
    )
    return updated


def _ridsForSfN_get(
    geometry: BoardGeometry,
    token: sfN,
) -> list[BoardRegionId]:
    """Resolve an sfN token to exact or wildcard-matching region IDs."""

    ridResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(token)
    if not result_isOkCheck(ridResult):
        return []
    rid: BoardRegionId = ridResult.value
    if rid in geometry.geometryZonesById:
        return [rid]
    return [
        candidateRid
        for candidateRid in geometry.geometryZonesById
        if candidateRid.family == rid.family
        and candidateRid.side == rid.side
        and rid.band is None
    ]


def _zoneTranslatedRows_build(
    zone: GeometryZone,
    deltaRows: int,
) -> GeometryZone:
    """Translate one geometry zone vertically with owned chips/terminals."""

    shiftedPlacements: dict[str, BoardChipDrawPlacement] = {
        chipName: replace(
            placement,
            drawTopLeft=(
                placement.drawTopLeft[0],
                placement.drawTopLeft[1] + deltaRows,
            ),
        )
        for chipName, placement in zone.chipDrawPlacementsByChip.items()
    }
    shiftedTerminals: TerminalPositionsByChip = {
        chipName: {
            terminalName: (position[0], position[1] + deltaRows)
            for terminalName, position in terminalPositions.items()
        }
        for chipName, terminalPositions in (
            zone.exactTerminalWorldPositionsByChip.items()
        )
    }
    return GeometryZone(
        regionId=zone.regionId,
        frame=replace(
            zone.frame,
            verticalStart=zone.frame.verticalStart + deltaRows,
        ),
        routingZoneRegionId=zone.routingZoneRegionId,
        chipDrawPlacementsByChip=shiftedPlacements,
        exactTerminalWorldPositionsByChip=shiftedTerminals,
    )


def _sideBundleTranslateRows_apply(
    geometry: BoardGeometry,
    tokens: tuple[sfN, ...],
    deltaRows: int,
    moduleNames: set[str],
) -> BoardGeometry:
    """Translate a side terminal/fan bundle and its module boundaries."""

    if deltaRows == 0:
        return geometry

    zonesById: dict[BoardRegionId, GeometryZone] = dict(
        geometry.geometryZonesById
    )
    for token in tokens:
        for rid in _ridsForSfN_get(geometry, token):
            zone: GeometryZone | None = zonesById.get(rid)
            if zone is not None:
                zonesById[rid] = _zoneTranslatedRows_build(zone, deltaRows)

    boundaryFramesByName: dict[str, RoutingZoneRegionFrame] = dict(
        geometry.effectiveBoundaryFramesByName
    )
    for moduleName in moduleNames:
        boundaryName: str = f"module/{moduleName}"
        boundaryFrame: RoutingZoneRegionFrame | None = (
            boundaryFramesByName.get(boundaryName)
        )
        if boundaryFrame is not None:
            boundaryFramesByName[boundaryName] = replace(
                boundaryFrame,
                verticalStart=boundaryFrame.verticalStart + deltaRows,
            )

    return _geometryFromParts_build(
        geometry,
        geometryZonesById=zonesById,
        effectiveBoundaryFramesByName=boundaryFramesByName,
    )


def _sharedModuleDeltaRows_get(
    zaGeometry: BoardGeometry,
    zbGeometry: BoardGeometry,
    etRid: BoardRegionId,
    wtRid: BoardRegionId,
) -> tuple[int, set[str]] | None:
    """Return row delta needed to align shared seam module tops."""

    etZone: GeometryZone | None = zaGeometry.geometryZonesById.get(etRid)
    wtZone: GeometryZone | None = zbGeometry.geometryZonesById.get(wtRid)
    if etZone is None or wtZone is None:
        return None

    sharedChipNames: set[str] = set(etZone.chipDrawPlacementsByChip) & set(
        wtZone.chipDrawPlacementsByChip
    )
    if not sharedChipNames:
        return None

    deltas: list[int] = []
    moduleNames: set[str] = set()
    for chipName in sharedChipNames:
        zaPlacement: BoardChipDrawPlacement = (
            etZone.chipDrawPlacementsByChip[chipName]
        )
        zbPlacement: BoardChipDrawPlacement = (
            wtZone.chipDrawPlacementsByChip[chipName]
        )
        zaBoundary: RoutingZoneRegionFrame | None = (
            zaGeometry.effectiveBoundaryFramesByName.get(
                f"module/{zaPlacement.moduleName}"
            )
        )
        zbBoundary: RoutingZoneRegionFrame | None = (
            zbGeometry.effectiveBoundaryFramesByName.get(
                f"module/{zbPlacement.moduleName}"
            )
        )
        zaTop: int = (
            zaBoundary.verticalStart
            if zaBoundary is not None
            else zaPlacement.drawTopLeft[1]
        )
        zbTop: int = (
            zbBoundary.verticalStart
            if zbBoundary is not None
            else zbPlacement.drawTopLeft[1]
        )
        deltas.append(zaTop - zbTop)
        moduleNames.add(zbPlacement.moduleName)

    if not deltas:
        return None

    deltaRows: int = sorted(deltas)[len(deltas) // 2]
    return deltaRows, moduleNames


def _sideBundleClampToBoundary_apply(
    geometry: BoardGeometry,
    tokens: tuple[sfN, ...],
    terminalToken: sfN,
) -> BoardGeometry:
    """Clamp side terminal/fan frames to owned effective module bounds."""

    terminalRids: list[BoardRegionId] = _ridsForSfN_get(
        geometry,
        terminalToken,
    )
    moduleNames: set[str] = set()
    for rid in terminalRids:
        zone: GeometryZone | None = geometry.geometryZonesById.get(rid)
        if zone is not None:
            moduleNames.update(
                placement.moduleName
                for placement in zone.chipDrawPlacementsByChip.values()
            )

    boundaryFrames: list[RoutingZoneRegionFrame] = [
        geometry.effectiveBoundaryFramesByName[f"module/{moduleName}"]
        for moduleName in moduleNames
        if f"module/{moduleName}" in geometry.effectiveBoundaryFramesByName
    ]
    if not boundaryFrames:
        return geometry

    top: int = min(frame.verticalStart for frame in boundaryFrames)
    bottomEx: int = max(
        frame.verticalEnd_calculate() for frame in boundaryFrames
    )
    zonesById: dict[BoardRegionId, GeometryZone] = dict(
        geometry.geometryZonesById
    )

    for token in tokens:
        for rid in _ridsForSfN_get(geometry, token):
            zone: GeometryZone | None = zonesById.get(rid)
            if zone is not None:
                zonesById[rid] = GeometryZone(
                    regionId=zone.regionId,
                    frame=replace(
                        zone.frame,
                        verticalStart=top,
                        verticalSpan=bottomEx - top,
                    ),
                    routingZoneRegionId=zone.routingZoneRegionId,
                    chipDrawPlacementsByChip=zone.chipDrawPlacementsByChip,
                    exactTerminalWorldPositionsByChip=(
                        zone.exactTerminalWorldPositionsByChip
                    ),
                )

    return _geometryFromParts_build(
        geometry,
        geometryZonesById=zonesById,
        effectiveBoundaryFramesByName=dict(
            geometry.effectiveBoundaryFramesByName
        ),
    )


def _terminalColumnsBySeam_calculate(
    geometriesByIndex: dict[int, BoardGeometry],
    activeIndexes: list[int],
    etRid: BoardRegionId,
    wtRid: BoardRegionId,
) -> tuple[dict[int, int], dict[int, int]]:
    """Return seam Et/Wt minimum terminal columns by zone index."""

    eastColumnsByIndex: dict[int, int] = {}
    westColumnsByIndex: dict[int, int] = {}

    for leftIndex, rightIndex in zip(
        activeIndexes,
        activeIndexes[1:],
        strict=False,
    ):
        leftGeometry: BoardGeometry = geometriesByIndex[leftIndex]
        rightGeometry: BoardGeometry = geometriesByIndex[rightIndex]
        etZone: GeometryZone | None = leftGeometry.geometryZonesById.get(
            etRid
        )
        wtZone: GeometryZone | None = rightGeometry.geometryZonesById.get(
            wtRid
        )
        if etZone is None or wtZone is None:
            continue

        sharedChipNames: list[str] = list(
            etZone.chipDrawPlacementsByChip.keys()
        )
        etColumns: list[int] = [
            position[0]
            for chipName in sharedChipNames
            for position in (
                etZone.exactTerminalWorldPositionsByChip.get(chipName) or {}
            ).values()
        ]
        wtColumns: list[int] = [
            position[0]
            for chipName in sharedChipNames
            for position in (
                wtZone.exactTerminalWorldPositionsByChip.get(chipName) or {}
            ).values()
        ]
        if etColumns:
            eastColumnsByIndex[leftIndex] = min(etColumns)
        if wtColumns:
            westColumnsByIndex[rightIndex] = min(wtColumns)

    return eastColumnsByIndex, westColumnsByIndex


def _wOffsets_calculate(
    activeIndexes: list[int],
    eastColumnsByIndex: dict[int, int],
    westColumnsByIndex: dict[int, int],
) -> dict[int, int]:
    """Calculate terminal-column world offsets for an ordered chain."""

    offsetsByIndex: dict[int, int] = {}
    if activeIndexes:
        offsetsByIndex[activeIndexes[0]] = 0

    for leftIndex, rightIndex in zip(
        activeIndexes,
        activeIndexes[1:],
        strict=False,
    ):
        leftColumn: int = eastColumnsByIndex.get(leftIndex, 0)
        rightColumn: int = westColumnsByIndex.get(rightIndex, 0)
        offsetsByIndex[rightIndex] = offsetsByIndex.get(
            leftIndex,
            0,
        ) + (leftColumn - rightColumn)

    return offsetsByIndex


class WorldGeometryResolver:
    """World geometry resolver for ordered overlap-zone chains."""

    _WEST_SIDE_BUNDLE: tuple[sfN, ...] = (sfN.Wt, sfN.Wfe, sfN.Wfi)
    _EAST_SIDE_BUNDLE: tuple[sfN, ...] = (sfN.Et, sfN.Efe, sfN.Efi)

    @staticmethod
    def northRelaxationSpan_calculate(geometry: BoardGeometry) -> int:
        """Return the active north relaxation span: Ne + Nt + Nfi."""

        return _northRelaxationSpan_calculate(geometry)

    @staticmethod
    def harmonized_chain_build(
        geometryByIndex: dict[int, BoardGeometry],
    ) -> WorldChainResolution:
        """Harmonize and offset an ordered WTE overlap-zone chain.

        Args:
            geometryByIndex: Per-zone local geometries keyed by sequential
                overlap-zone index.

        Returns:
            Harmonized geometries plus terminal-column world offsets.
        """

        activeIndexes: list[int] = sorted(geometryByIndex)
        geometriesByIndex: dict[int, BoardGeometry] = dict(geometryByIndex)

        etRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(
            sfN.Et
        )
        wtRidResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(
            sfN.Wt
        )
        if not result_isOkCheck(etRidResult) or not result_isOkCheck(
            wtRidResult
        ):
            return WorldChainResolution(
                geometryByIndex=geometriesByIndex,
                wOffsetsByIndex={},
                eastTerminalColumnByIndex={},
                westTerminalColumnByIndex={},
            )

        etRid: BoardRegionId = etRidResult.value
        wtRid: BoardRegionId = wtRidResult.value

        for leftIndex, rightIndex in zip(
            activeIndexes,
            activeIndexes[1:],
            strict=False,
        ):
            leftGeometry: BoardGeometry = geometriesByIndex[leftIndex]
            rightGeometry: BoardGeometry = geometriesByIndex[rightIndex]

            rightWestExtraSpan: int = _span_get(
                rightGeometry,
                sfN.We,
                horizontal=True,
            )
            rightNorthSpan: int = _northRelaxationSpan_calculate(
                rightGeometry
            )
            leftEastExtraSpan: int = _span_get(
                leftGeometry,
                sfN.Ee,
                horizontal=True,
            )

            leftChanges: list[GeoChange] = [
                (
                    sfN.Efi,
                    GeoArgScalar(rightWestExtraSpan),
                    GeoOp.DISPLACE,
                )
            ]
            if rightNorthSpan:
                leftChanges += [
                    (
                        sfN.Ne,
                        GeoArgScalar(-rightNorthSpan),
                        GeoOp.DISPLACE,
                    ),
                    (
                        sfN.Se,
                        GeoArgScalar(rightNorthSpan),
                        GeoOp.DISPLACE,
                    ),
                ]
            leftResult: Result[BoardGeometry] = geometry_change(
                leftChanges,
                leftGeometry,
            )
            if result_isOkCheck(leftResult):
                geometriesByIndex[leftIndex] = leftResult.value

            if leftEastExtraSpan:
                rightResult: Result[BoardGeometry] = geometry_change(
                    [
                        (
                            sfN.Wm,
                            GeoArgScalar(leftEastExtraSpan),
                            GeoOp.DISPLACE,
                        )
                    ],
                    rightGeometry,
                )
                if result_isOkCheck(rightResult):
                    geometriesByIndex[rightIndex] = rightResult.value

            for cascadeIndex in activeIndexes[
                activeIndexes.index(leftIndex) + 1 :
            ]:
                cascadeGeometry: BoardGeometry = geometriesByIndex[
                    cascadeIndex
                ]
                cascadeResult: Result[BoardGeometry] = geometry_change(
                    [
                        (
                            sfN.Z,
                            GeoArgScalar(rightWestExtraSpan),
                            GeoOp.DISPLACE,
                        )
                    ],
                    cascadeGeometry,
                )
                if result_isOkCheck(cascadeResult):
                    geometriesByIndex[cascadeIndex] = cascadeResult.value

            if leftEastExtraSpan:
                for cascadeIndex in activeIndexes[
                    activeIndexes.index(rightIndex) + 1 :
                ]:
                    cascadeGeometry = geometriesByIndex[cascadeIndex]
                    cascadeResult = geometry_change(
                        [
                            (
                                sfN.Z,
                                GeoArgScalar(leftEastExtraSpan),
                                GeoOp.DISPLACE,
                            )
                        ],
                        cascadeGeometry,
                    )
                    if result_isOkCheck(cascadeResult):
                        geometriesByIndex[cascadeIndex] = cascadeResult.value

        cumulativeRowOffset: int = 0
        for offsetIndex in range(1, len(activeIndexes)):
            leftIndex: int = activeIndexes[offsetIndex - 1]
            currentIndex: int = activeIndexes[offsetIndex]
            cumulativeRowOffset += _northRelaxationSpan_calculate(
                geometriesByIndex[leftIndex]
            )
            if cumulativeRowOffset == 0:
                continue
            rowResult: Result[BoardGeometry] = geometry_change(
                [
                    (
                        sfN.Z,
                        GeoArgScalar(cumulativeRowOffset),
                        GeoOp.DISPLACE_VERTICAL,
                    )
                ],
                geometriesByIndex[currentIndex],
            )
            if result_isOkCheck(rowResult):
                geometriesByIndex[currentIndex] = rowResult.value

        for leftIndex, rightIndex in zip(
            activeIndexes,
            activeIndexes[1:],
            strict=False,
        ):
            sharedDelta: tuple[int, set[str]] | None = (
                _sharedModuleDeltaRows_get(
                    geometriesByIndex[leftIndex],
                    geometriesByIndex[rightIndex],
                    etRid,
                    wtRid,
                )
            )
            if sharedDelta is None:
                continue
            deltaRows, moduleNames = sharedDelta
            geometriesByIndex[rightIndex] = _sideBundleTranslateRows_apply(
                geometriesByIndex[rightIndex],
                WorldGeometryResolver._WEST_SIDE_BUNDLE,
                deltaRows,
                moduleNames,
            )

        for index in activeIndexes:
            geometry: BoardGeometry = geometriesByIndex[index]
            geometry = _sideBundleClampToBoundary_apply(
                geometry,
                WorldGeometryResolver._WEST_SIDE_BUNDLE,
                sfN.Wt,
            )
            geometry = _sideBundleClampToBoundary_apply(
                geometry,
                WorldGeometryResolver._EAST_SIDE_BUNDLE,
                sfN.Et,
            )
            geometriesByIndex[index] = geometry

        eastColumnsByIndex, westColumnsByIndex = (
            _terminalColumnsBySeam_calculate(
                geometriesByIndex,
                activeIndexes,
                etRid,
                wtRid,
            )
        )
        offsetsByIndex: dict[int, int] = _wOffsets_calculate(
            activeIndexes,
            eastColumnsByIndex,
            westColumnsByIndex,
        )

        return WorldChainResolution(
            geometryByIndex=geometriesByIndex,
            wOffsetsByIndex=offsetsByIndex,
            eastTerminalColumnByIndex=eastColumnsByIndex,
            westTerminalColumnByIndex=westColumnsByIndex,
        )


__all__ = [
    "SeamBudgets",
    "WorldChainResolution",
    "WorldGeometryResolver",
]
