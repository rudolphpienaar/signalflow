"""Adapters that build first-class board objects from existing engine inputs.

This module exists to keep the migration pragmatic. The current engine already
has working kernel geometry and attach-point computations. The board package
should reuse those as input facts while moving the canonical ownership of the
resulting board object into `signalflow.board`.
"""
from __future__ import annotations

from signalflow.board.board import Board
from dataclasses import replace

from signalflow.board.doctrine import BoardDoctrine, EffectiveBoundaryMode
from signalflow.board.geometry import BoardGeometry
from signalflow.board.substrate import BoardSubstrate
from signalflow.board.types import (
    BoardRegionId,
    BoardChipDrawPlacement,
    BoardSense,
    BoardSide,
    RegionFamily,
    WorldFrame,
    boardRegionId_buildFromRoutingZoneRegionId,
)
from signalflow.models import (
    ChipRef,
    CircuitDocument,
    RoutingKernel,
    RoutingZone,
    RoutingZoneId,
    RoutingZoneRegionId,
    RoutingZoneSense,
    RoutingZoneRegionFrame,
    result_isOkCheck,
    routingZoneRegionByIdResult_get,
)
from signalflow.models.chip import chipDrawLines_build
from signalflow.routing import (
    chipAttachPointSetResult_buildFromPlacedZone,
    chipLocalGeometrySetResult_buildFromChips,
)
from signalflow.routing.geometry import (
    ChipLocalGeometrySet,
    chipCanvasPlacementGeometry_build,
    chipPlacementStackOffsetResult_build,
)


def board_buildFromKernel(
    *,
    routingZoneId: RoutingZoneId,
    side: str,
    routingZone: RoutingZone,
    kernel: RoutingKernel,
    circuitDocument: CircuitDocument,
    moduleBoundaryPaddingCells: int = 1,
    effectiveBoundaryMode: EffectiveBoundaryMode = (
        EffectiveBoundaryMode.LABEL_AWARE_MODULE_BOX
    ),
) -> Board:
    """Build a first-class board from an existing placed-zone kernel.

    This builder is intentionally adapter-shaped. It does not re-solve or
    reinterpret the board. It lifts the already-known region geometry and exact
    attach points into the new board-domain object model.
    """

    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = {}
    routingZoneRegionIdsById: dict[BoardRegionId, RoutingZoneRegionId] = {}
    for routingZoneRegion in kernel.routingZoneRegionSet.routingZoneRegions:
        regionId = routingZoneRegion.routingZoneRegionId
        boardRegionId = boardRegionId_buildFromRoutingZoneRegionId(regionId)
        regionFramesById[boardRegionId] = routingZoneRegion.routingZoneRegionFrame
        routingZoneRegionIdsById[boardRegionId] = regionId

    terminalPositionsByChip: dict[str, dict[str, tuple[int, int]]] = {}
    chipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = {}
    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        circuitDocument.circuitChipSet.chips
    )
    attachPointSetResult = None
    if result_isOkCheck(chipLocalGeometrySetResult):
        attachPointSetResult = chipAttachPointSetResult_buildFromPlacedZone(
            routingZone,
            chipLocalGeometrySetResult.value,
            circuitDocument,
        )
    if attachPointSetResult is not None and result_isOkCheck(attachPointSetResult):
        for attachPoint in attachPointSetResult.value.attachPoints:
            chipName = _chipName_build(attachPoint.chipRef)
            terminalPositionsByChip.setdefault(chipName, {})[
                attachPoint.terminalName
            ] = (attachPoint.worldColumn, attachPoint.worldRow)
    if result_isOkCheck(chipLocalGeometrySetResult):
        chipDrawPlacementsByChip = _chipDrawPlacementsByChip_build(
            routingZone=routingZone,
            circuitDocument=circuitDocument,
            chipLocalGeometrySet=chipLocalGeometrySetResult.value,
        )

    sense = _boardSense_build(routingZone)
    substrateGeometry = BoardGeometry(
        regionFramesById=regionFramesById,
        routingZoneRegionIdsById=routingZoneRegionIdsById,
        effectiveBoundaryFramesByName=_effectiveBoundaryFramesByModule_build(
            routingZone=routingZone,
            circuitDocument=circuitDocument,
            effectiveBoundaryMode=effectiveBoundaryMode,
            moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
        ),
        exactTerminalWorldPositionsByChip=terminalPositionsByChip,
        chipDrawPlacementsByChip=chipDrawPlacementsByChip,
    )
    effectiveGeometry = _effectiveGeometry_build(
        substrateGeometry=substrateGeometry,
        routingZone=routingZone,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
    )
    substrateWorldFrame = _boardWorldFrame_build(
        geometry=substrateGeometry,
        fallbackFrame=routingZone.routingZoneFrame,
    )
    effectiveWorldFrame = _boardWorldFrame_build(
        geometry=effectiveGeometry,
        fallbackFrame=routingZone.routingZoneFrame,
    )
    substrate = BoardSubstrate(
        sense=sense,
        regionFramesById=regionFramesById,
    )
    doctrine = BoardDoctrine(
        sense=sense,
        minimumCrossbarSpan=_minimumCrossbarSpan_calculate(regionFramesById, sense),
        effectiveBoundaryMode=effectiveBoundaryMode,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
    )
    effectiveBoard = Board(
        routingZoneId=routingZoneId,
        side=side,
        worldFrame=effectiveWorldFrame,
        doctrine=doctrine,
        substrate=substrate,
        geometry=effectiveGeometry,
    )
    substrateBoard = Board(
        routingZoneId=routingZoneId,
        side=side,
        worldFrame=substrateWorldFrame,
        doctrine=replace(
            doctrine,
            effectiveBoundaryMode=EffectiveBoundaryMode.CONTENT_ONLY,
            moduleBoundaryPaddingCells=0,
        ),
        substrate=substrate,
        geometry=replace(
            substrateGeometry,
            effectiveBoundaryFramesByName={},
        ),
    )
    object.__setattr__(effectiveBoard, "substrateBoard", substrateBoard)
    object.__setattr__(effectiveBoard, "effectiveBoard", effectiveBoard)
    object.__setattr__(substrateBoard, "substrateBoard", substrateBoard)
    object.__setattr__(substrateBoard, "effectiveBoard", effectiveBoard)
    return effectiveBoard


def _boardWorldFrame_build(
    *,
    geometry: BoardGeometry,
    fallbackFrame: RoutingZoneRegionFrame,
) -> WorldFrame:
    """Return the inclusive world frame required by one board geometry variant.

    The effective board can extend beyond the raw routing substrate once
    module boundaries and shifted chip placements are applied. The canvas frame
    therefore must be derived from all board-owned geometry, not only from the
    routing region bands.
    """

    leftColumns: list[int] = []
    topRows: list[int] = []
    rightColumns: list[int] = []
    bottomRows: list[int] = []

    for frame in geometry.regionFramesById.values():
        leftColumns.append(frame.horizontalStart)
        topRows.append(frame.verticalStart)
        rightColumns.append(frame.horizontalEnd_calculate() - 1)
        bottomRows.append(frame.verticalEnd_calculate() - 1)

    for frame in geometry.effectiveBoundaryFramesByName.values():
        leftColumns.append(frame.horizontalStart)
        topRows.append(frame.verticalStart)
        rightColumns.append(frame.horizontalEnd_calculate() - 1)
        bottomRows.append(frame.verticalEnd_calculate() - 1)

    for chipPlacement in geometry.chipDrawPlacementsByChip.values():
        chipFrame = chipPlacement.worldFrame_get()
        leftColumns.append(chipFrame.topLeft[0])
        topRows.append(chipFrame.topLeft[1])
        rightColumns.append(chipFrame.bottomRight[0])
        bottomRows.append(chipFrame.bottomRight[1])

    if not leftColumns:
        return WorldFrame(
            topLeft=(fallbackFrame.horizontalStart, fallbackFrame.verticalStart),
            bottomRight=(
                fallbackFrame.horizontalEnd_calculate() - 1,
                fallbackFrame.verticalEnd_calculate() - 1,
            ),
        )

    return WorldFrame(
        topLeft=(min(leftColumns), min(topRows)),
        bottomRight=(max(rightColumns), max(bottomRows)),
    )


def _effectiveGeometry_build(
    *,
    substrateGeometry: BoardGeometry,
    routingZone: RoutingZone,
    moduleBoundaryPaddingCells: int,
) -> BoardGeometry:
    """Derive effective board geometry from substrate geometry plus doctrine.

    The effective geometry widens chip-terminal envelopes to the first-class
    effective module boundaries and keeps the routing-core band widths
    invariant while allowing the whole core to translate outward when a
    terminal envelope grows.

    The same explicit doctrine padding drives both:
    - the module-boundary expansion beyond visible label/stub extents
    - the interior routing-facing inset between an effective module boundary
      and the first visible terminal label/stub glyph

    That keeps padding ownership in one place instead of relying on incidental
    whitespace inside chip draw lines.

    For WTE/ETW:
    - the west chip-terminal strip expands outward to the west module box
    - the west fan stays outside that envelope
    - the routing core shifts right by the west-envelope growth
    - the east-side chip/module placement shifts with the translated core

    For NTS/STN:
    - the north chip-terminal strip expands outward to the north module box
    - the north fan stays outside that envelope
    - the routing core shifts downward by the north-envelope growth
    - the south-side chip/module placement shifts with the translated core

    This preserves doctrinal symmetry: module envelopes own chip-terminal
    space, while fan rows/columns remain routing substrate outside those
    envelopes.
    """

    regionFramesById = dict(substrateGeometry.regionFramesById)
    boundaryFramesByName = dict(substrateGeometry.effectiveBoundaryFramesByName)
    if not regionFramesById or not boundaryFramesByName:
        return substrateGeometry

    sense = _boardSense_build(routingZone)

    moduleSidesByName = _moduleSidesByName_build(routingZone)
    if sense in (BoardSense.WEST_TO_EAST, BoardSense.EAST_TO_WEST):
        westBoundaryFrames = [
            frame
            for boundaryName, frame in boundaryFramesByName.items()
            if moduleSidesByName.get(boundaryName.removeprefix("module/")) == BoardSide.WEST
        ]
        eastBoundaryFrames = [
            frame
            for boundaryName, frame in boundaryFramesByName.items()
            if moduleSidesByName.get(boundaryName.removeprefix("module/")) == BoardSide.EAST
        ]
        if not westBoundaryFrames or not eastBoundaryFrames:
            return substrateGeometry

        westChipTerminalId = BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.WEST,
        )
        eastChipTerminalId = BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.EAST,
        )
        westChipTerminalFrame = regionFramesById.get(westChipTerminalId)
        eastChipTerminalFrame = regionFramesById.get(eastChipTerminalId)
        if westChipTerminalFrame is None or eastChipTerminalFrame is None:
            return substrateGeometry

        westBoundary = min(
            westBoundaryFrames,
            key=lambda frame: frame.horizontalStart,
        )
        eastBoundary = max(
            eastBoundaryFrames,
            key=lambda frame: frame.horizontalStart,
        )

        westEnvelopeGrowthColumns = max(
            0,
            (westBoundary.horizontalEnd_calculate() - 1)
            - (westChipTerminalFrame.horizontalEnd_calculate() - 1),
        )
        transformedFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = {}
        for regionId, frame in regionFramesById.items():
            if regionId == westChipTerminalId:
                westTerminalStart = min(frame.horizontalStart, westBoundary.horizontalStart)
                westTerminalEnd = max(
                    frame.horizontalEnd_calculate() - 1,
                    westBoundary.horizontalEnd_calculate() - 1,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=westTerminalStart,
                    verticalStart=frame.verticalStart,
                    horizontalSpan=westTerminalEnd - westTerminalStart + 1,
                    verticalSpan=frame.verticalSpan,
                )
                continue

            shiftedFrame = _frameShiftedHorizontally_build(
                frame,
                deltaColumns=westEnvelopeGrowthColumns,
            )
            if regionId == eastChipTerminalId:
                shiftedEastBoundary = _frameShiftedHorizontally_build(
                    eastBoundary,
                    deltaColumns=westEnvelopeGrowthColumns,
                )
                eastTerminalEnd = max(
                    shiftedFrame.horizontalEnd_calculate() - 1,
                    shiftedEastBoundary.horizontalEnd_calculate() - 1,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=shiftedFrame.verticalStart,
                    horizontalSpan=eastTerminalEnd - shiftedFrame.horizontalStart + 1,
                    verticalSpan=shiftedFrame.verticalSpan,
                )
                continue
            transformedFramesById[regionId] = shiftedFrame

        transformedWestChipTerminalFrame = transformedFramesById[westChipTerminalId]
        transformedEastChipTerminalFrame = transformedFramesById[eastChipTerminalId]

        shiftedBoundaryFramesByName: dict[str, RoutingZoneRegionFrame] = {}
        for boundaryName, frame in boundaryFramesByName.items():
            moduleSide = moduleSidesByName.get(boundaryName.removeprefix("module/"))
            if moduleSide is BoardSide.EAST:
                shiftedFrame = _frameShiftedHorizontally_build(
                    frame,
                    deltaColumns=westEnvelopeGrowthColumns,
                )
                shiftedRightEdge = shiftedFrame.horizontalEnd_calculate() - 1
                eastTerminalStart = transformedEastChipTerminalFrame.horizontalStart
                shiftedBoundaryFramesByName[boundaryName] = RoutingZoneRegionFrame(
                    horizontalStart=eastTerminalStart,
                    verticalStart=shiftedFrame.verticalStart,
                    horizontalSpan=shiftedRightEdge - eastTerminalStart + 1,
                    verticalSpan=shiftedFrame.verticalSpan,
                )
            elif moduleSide is BoardSide.WEST:
                shiftedBoundaryFramesByName[boundaryName] = RoutingZoneRegionFrame(
                    horizontalStart=frame.horizontalStart,
                    verticalStart=frame.verticalStart,
                    horizontalSpan=(
                        transformedWestChipTerminalFrame.horizontalEnd_calculate()
                        - frame.horizontalStart
                    ),
                    verticalSpan=frame.verticalSpan,
                )
            else:
                shiftedBoundaryFramesByName[boundaryName] = frame

        shiftedTerminalPositionsByChip: dict[str, dict[str, tuple[int, int]]] = {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                substrateGeometry.exactTerminalWorldPositionsByChip.items()
            )
        }
        shiftedChipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = dict(
            substrateGeometry.chipDrawPlacementsByChip
        )
        eastInteriorPadColumns = moduleBoundaryPaddingCells

        for chipName, chipPlacement in substrateGeometry.chipDrawPlacementsByChip.items():
            if chipPlacement.side is not BoardSide.EAST:
                continue
            moduleBoundary = shiftedBoundaryFramesByName.get(
                f"module/{chipPlacement.moduleName}"
            )
            if moduleBoundary is None:
                continue
            targetDrawColumn = moduleBoundary.horizontalStart + eastInteriorPadColumns
            drawShiftColumns = targetDrawColumn - chipPlacement.drawTopLeft[0]
            shiftedChipDrawPlacementsByChip[chipName] = BoardChipDrawPlacement(
                chipName=chipPlacement.chipName,
                moduleName=chipPlacement.moduleName,
                side=chipPlacement.side,
                drawTopLeft=(
                    targetDrawColumn,
                    chipPlacement.drawTopLeft[1],
                ),
                drawLines=chipPlacement.drawLines,
            )
            chipTerminalPositions = shiftedTerminalPositionsByChip.get(chipName)
            if chipTerminalPositions is None:
                continue
            shiftedTerminalPositionsByChip[chipName] = {
                terminalName: (
                    worldColumn + drawShiftColumns,
                    worldRow,
                )
                for terminalName, (worldColumn, worldRow) in chipTerminalPositions.items()
            }

        for boundaryName, boundaryFrame in list(shiftedBoundaryFramesByName.items()):
            moduleSide = moduleSidesByName.get(boundaryName.removeprefix("module/"))
            if moduleSide is not BoardSide.EAST:
                continue
            moduleName = boundaryName.removeprefix("module/")
            eastChipPlacements = tuple(
                chipPlacement
                for chipPlacement in shiftedChipDrawPlacementsByChip.values()
                if chipPlacement.moduleName == moduleName
                and chipPlacement.side is BoardSide.EAST
            )
            if not eastChipPlacements:
                continue
            visibleBounds = tuple(
                _visibleChipDrawBounds_build(
                    drawTopLeft=chipPlacement.drawTopLeft,
                    drawLines=chipPlacement.drawLines,
                )
                for chipPlacement in eastChipPlacements
            )
            visibleBounds = tuple(
                bounds for bounds in visibleBounds if bounds is not None
            )
            if not visibleBounds:
                continue
            rightEdge = max(bounds[3] for bounds in visibleBounds) + moduleBoundaryPaddingCells
            shiftedBoundaryFramesByName[boundaryName] = RoutingZoneRegionFrame(
                horizontalStart=boundaryFrame.horizontalStart,
                verticalStart=boundaryFrame.verticalStart,
                horizontalSpan=rightEdge - boundaryFrame.horizontalStart + 1,
                verticalSpan=boundaryFrame.verticalSpan,
            )

        return replace(
            substrateGeometry,
            regionFramesById=transformedFramesById,
            effectiveBoundaryFramesByName=shiftedBoundaryFramesByName,
            exactTerminalWorldPositionsByChip=shiftedTerminalPositionsByChip,
            chipDrawPlacementsByChip=shiftedChipDrawPlacementsByChip,
        )

    if sense in (BoardSense.NORTH_TO_SOUTH, BoardSense.SOUTH_TO_NORTH):
        northBoundaryFrames = [
            frame
            for boundaryName, frame in boundaryFramesByName.items()
            if moduleSidesByName.get(boundaryName.removeprefix("module/")) == BoardSide.NORTH
        ]
        southBoundaryFrames = [
            frame
            for boundaryName, frame in boundaryFramesByName.items()
            if moduleSidesByName.get(boundaryName.removeprefix("module/")) == BoardSide.SOUTH
        ]
        if not northBoundaryFrames or not southBoundaryFrames:
            return substrateGeometry

        northChipTerminalId = BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.NORTH,
        )
        southChipTerminalId = BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.SOUTH,
        )
        northChipTerminalFrame = regionFramesById.get(northChipTerminalId)
        southChipTerminalFrame = regionFramesById.get(southChipTerminalId)
        if northChipTerminalFrame is None or southChipTerminalFrame is None:
            return substrateGeometry

        northBoundary = min(
            northBoundaryFrames,
            key=lambda frame: frame.verticalStart,
        )
        southBoundary = max(
            southBoundaryFrames,
            key=lambda frame: frame.verticalStart,
        )

        northEnvelopeGrowthRows = max(
            0,
            (northBoundary.verticalEnd_calculate() - 1)
            - (northChipTerminalFrame.verticalEnd_calculate() - 1),
        )
        transformedFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = {}
        for regionId, frame in regionFramesById.items():
            if regionId == northChipTerminalId:
                northTerminalStart = min(frame.verticalStart, northBoundary.verticalStart)
                northTerminalEnd = max(
                    frame.verticalEnd_calculate() - 1,
                    northBoundary.verticalEnd_calculate() - 1,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=frame.horizontalStart,
                    verticalStart=northTerminalStart,
                    horizontalSpan=frame.horizontalSpan,
                    verticalSpan=northTerminalEnd - northTerminalStart + 1,
                )
                continue

            shiftedFrame = _frameShiftedVertically_build(
                frame,
                deltaRows=northEnvelopeGrowthRows,
            )
            if regionId == southChipTerminalId:
                shiftedSouthBoundary = _frameShiftedVertically_build(
                    southBoundary,
                    deltaRows=northEnvelopeGrowthRows,
                )
                southTerminalEnd = max(
                    shiftedFrame.verticalEnd_calculate() - 1,
                    shiftedSouthBoundary.verticalEnd_calculate() - 1,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=shiftedFrame.verticalStart,
                    horizontalSpan=shiftedFrame.horizontalSpan,
                    verticalSpan=southTerminalEnd - shiftedFrame.verticalStart + 1,
                )
                continue
            transformedFramesById[regionId] = shiftedFrame

        transformedNorthChipTerminalFrame = transformedFramesById[northChipTerminalId]
        transformedSouthChipTerminalFrame = transformedFramesById[southChipTerminalId]

        shiftedBoundaryFramesByName: dict[str, RoutingZoneRegionFrame] = {}
        for boundaryName, frame in boundaryFramesByName.items():
            moduleSide = moduleSidesByName.get(boundaryName.removeprefix("module/"))
            if moduleSide is BoardSide.SOUTH:
                shiftedFrame = _frameShiftedVertically_build(
                    frame,
                    deltaRows=northEnvelopeGrowthRows,
                )
                shiftedBottomEdge = shiftedFrame.verticalEnd_calculate() - 1
                southTerminalStart = transformedSouthChipTerminalFrame.verticalStart
                shiftedBoundaryFramesByName[boundaryName] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=southTerminalStart,
                    horizontalSpan=shiftedFrame.horizontalSpan,
                    verticalSpan=shiftedBottomEdge - southTerminalStart + 1,
                )
            elif moduleSide is BoardSide.NORTH:
                shiftedBoundaryFramesByName[boundaryName] = RoutingZoneRegionFrame(
                    horizontalStart=frame.horizontalStart,
                    verticalStart=frame.verticalStart,
                    horizontalSpan=frame.horizontalSpan,
                    verticalSpan=(
                        transformedNorthChipTerminalFrame.verticalEnd_calculate()
                        - frame.verticalStart
                    ),
                )
            else:
                shiftedBoundaryFramesByName[boundaryName] = frame

        shiftedTerminalPositionsByChip: dict[str, dict[str, tuple[int, int]]] = {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                substrateGeometry.exactTerminalWorldPositionsByChip.items()
            )
        }
        shiftedChipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = dict(
            substrateGeometry.chipDrawPlacementsByChip
        )
        for chipName, chipPlacement in substrateGeometry.chipDrawPlacementsByChip.items():
            if chipPlacement.side is not BoardSide.SOUTH:
                continue
            shiftedChipDrawPlacementsByChip[chipName] = BoardChipDrawPlacement(
                chipName=chipPlacement.chipName,
                moduleName=chipPlacement.moduleName,
                side=chipPlacement.side,
                drawTopLeft=(
                    chipPlacement.drawTopLeft[0],
                    chipPlacement.drawTopLeft[1] + northEnvelopeGrowthRows,
                ),
                drawLines=chipPlacement.drawLines,
            )
            chipTerminalPositions = shiftedTerminalPositionsByChip.get(chipName)
            if chipTerminalPositions is None:
                continue
            shiftedTerminalPositionsByChip[chipName] = {
                terminalName: (worldColumn, worldRow + northEnvelopeGrowthRows)
                for terminalName, (worldColumn, worldRow) in chipTerminalPositions.items()
            }

        return replace(
            substrateGeometry,
            regionFramesById=transformedFramesById,
            effectiveBoundaryFramesByName=shiftedBoundaryFramesByName,
            exactTerminalWorldPositionsByChip=shiftedTerminalPositionsByChip,
            chipDrawPlacementsByChip=shiftedChipDrawPlacementsByChip,
        )

    return substrateGeometry


def _frameShiftedHorizontally_build(
    frame: RoutingZoneRegionFrame,
    *,
    deltaColumns: int,
) -> RoutingZoneRegionFrame:
    """Return a copy of a region frame shifted horizontally."""

    if deltaColumns == 0:
        return frame
    return RoutingZoneRegionFrame(
        horizontalStart=frame.horizontalStart + deltaColumns,
        verticalStart=frame.verticalStart,
        horizontalSpan=frame.horizontalSpan,
        verticalSpan=frame.verticalSpan,
    )


def _frameShiftedVertically_build(
    frame: RoutingZoneRegionFrame,
    *,
    deltaRows: int,
) -> RoutingZoneRegionFrame:
    """Return a copy of a region frame shifted vertically."""

    if deltaRows == 0:
        return frame
    return RoutingZoneRegionFrame(
        horizontalStart=frame.horizontalStart,
        verticalStart=frame.verticalStart + deltaRows,
        horizontalSpan=frame.horizontalSpan,
        verticalSpan=frame.verticalSpan,
    )


def _moduleSidesByName_build(
    routingZone: RoutingZone,
) -> dict[str, BoardSide]:
    """Return stable module-side ownership for placed chips in one zone."""

    moduleSidesByName: dict[str, BoardSide] = {}
    for chipPlacement in routingZone.chipPlacementSet.placements:
        side = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
        if side is None:
            continue
        moduleSidesByName.setdefault(
            chipPlacement.chipRef.chipId.moduleName,
            BoardSide(side.value),
        )
    return moduleSidesByName


def _chipDrawPlacementsByChip_build(
    *,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    chipLocalGeometrySet: ChipLocalGeometrySet,
) -> dict[str, BoardChipDrawPlacement]:
    """Build board-owned canonical chip draw placements from the placed zone."""

    chipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = {}
    for chipPlacement in routingZone.chipPlacementSet.placements:
        geometryResult = chipLocalGeometrySet.geometryForChipResult_get(
            chipPlacement.chipRef
        )
        if not result_isOkCheck(geometryResult):
            continue
        terminalRegionResult = routingZoneRegionByIdResult_get(
            routingZone,
            chipPlacement.chipTerminalRegionId,
        )
        if not result_isOkCheck(terminalRegionResult):
            continue
        regionSide = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
        if regionSide is None:
            continue
        sidePlacements = routingZone.chipPlacementSet.placementsInRegion_build(
            chipPlacement.chipTerminalRegionId
        ).placements
        stackOffsetResult = chipPlacementStackOffsetResult_build(
            sidePlacements=sidePlacements,
            targetPlacement=chipPlacement,
            chipLocalGeometrySet=chipLocalGeometrySet,
            routingZoneSense=routingZone.routingZoneSense,
            regionSide=regionSide,
        )
        if not result_isOkCheck(stackOffsetResult):
            continue
        placementGeometry = chipCanvasPlacementGeometry_build(
            chipLocalGeometry=geometryResult.value,
            routingZoneSense=routingZone.routingZoneSense,
            regionSide=regionSide,
            terminalRegionVerticalStart=(
                terminalRegionResult.value.routingZoneRegionFrame.verticalStart
            ),
            terminalRegionHorizontalStart=(
                terminalRegionResult.value.routingZoneRegionFrame.horizontalStart
            ),
            stackOffset=stackOffsetResult.value,
        )
        chipResult = circuitDocument.circuitChipSet.chipResult_get(
            chipPlacement.chipRef.chipId
        )
        if not result_isOkCheck(chipResult):
            continue
        chipName = _chipName_build(chipPlacement.chipRef)
        chipDrawPlacementsByChip[chipName] = BoardChipDrawPlacement(
            chipName=chipName,
            moduleName=chipPlacement.chipRef.chipId.moduleName,
            side=BoardSide(regionSide.value),
            drawTopLeft=(
                placementGeometry.drawWorldColumn,
                placementGeometry.drawWorldRow,
            ),
            drawLines=chipDrawLines_build(chipResult.value),
        )
    return chipDrawPlacementsByChip


def _chipName_build(chipRef: ChipRef) -> str:
    """Build a stable debug-facing chip name from a chip reference."""

    return f"{chipRef.chipId.moduleName}.{chipRef.chipId.functionName}"


def _boardSense_build(routingZone: RoutingZone) -> BoardSense:
    """Map existing zone-axis doctrine onto the new board-sense vocabulary."""

    if routingZone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return BoardSense.WEST_TO_EAST
    return BoardSense.NORTH_TO_SOUTH


def _minimumCrossbarSpan_calculate(
    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame],
    sense: BoardSense,
) -> int:
    """Return the current minimum cross-bar span implied by substrate geometry."""

    regionFramesByName = {
        regionId.label_build(): frame for regionId, frame in regionFramesById.items()
    }
    if sense in (BoardSense.WEST_TO_EAST, BoardSense.EAST_TO_WEST):
        northFrame = regionFramesByName.get("north/intra_routing_latitude")
        southFrame = regionFramesByName.get("south/intra_routing_latitude")
        candidates = [
            frame.horizontalSpan
            for frame in (northFrame, southFrame)
            if frame is not None
        ]
    else:
        westFrame = regionFramesByName.get("west/intra_routing_longitude")
        eastFrame = regionFramesByName.get("east/intra_routing_longitude")
        candidates = [
            frame.verticalSpan for frame in (westFrame, eastFrame) if frame is not None
        ]
    if not candidates:
        return 0
    return min(candidates)


def _effectiveBoundaryFramesByModule_build(
    *,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    effectiveBoundaryMode: EffectiveBoundaryMode,
    moduleBoundaryPaddingCells: int,
) -> dict[str, RoutingZoneRegionFrame]:
    """Build first-class effective module boundaries for one board.

    The current compatibility baseline is the existing world-render module box:
    group placed chips by module name, use their full drawn extents, then add
    explicit padding and enough top width to fit the rendered module label.
    """

    if effectiveBoundaryMode is EffectiveBoundaryMode.CONTENT_ONLY:
        return {}

    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(chipLocalGeometrySetResult):
        return {}
    chipLocalGeometrySet = chipLocalGeometrySetResult.value
    moduleSidesByName = _moduleSidesByName_build(routingZone)

    boundsByModuleMutable: dict[str, tuple[int, int, int, int]] = {}
    for chipPlacement in routingZone.chipPlacementSet.placements:
        geometryResult = chipLocalGeometrySet.geometryForChipResult_get(
            chipPlacement.chipRef
        )
        if not result_isOkCheck(geometryResult):
            continue
        terminalRegionResult = routingZoneRegionByIdResult_get(
            routingZone,
            chipPlacement.chipTerminalRegionId,
        )
        if not result_isOkCheck(terminalRegionResult):
            continue
        regionSide = chipPlacement.chipTerminalRegionId.routingZoneRegionSide
        if regionSide is None:
            continue
        sidePlacements = routingZone.chipPlacementSet.placementsInRegion_build(
            chipPlacement.chipTerminalRegionId
        ).placements
        stackOffsetResult = chipPlacementStackOffsetResult_build(
            sidePlacements=sidePlacements,
            targetPlacement=chipPlacement,
            chipLocalGeometrySet=chipLocalGeometrySet,
            routingZoneSense=routingZone.routingZoneSense,
            regionSide=regionSide,
        )
        if not result_isOkCheck(stackOffsetResult):
            continue
        placementGeometry = chipCanvasPlacementGeometry_build(
            chipLocalGeometry=geometryResult.value,
            routingZoneSense=routingZone.routingZoneSense,
            regionSide=regionSide,
            terminalRegionVerticalStart=(
                terminalRegionResult.value.routingZoneRegionFrame.verticalStart
            ),
            terminalRegionHorizontalStart=(
                terminalRegionResult.value.routingZoneRegionFrame.horizontalStart
            ),
            stackOffset=stackOffsetResult.value,
        )
        chipResult = circuitDocument.circuitChipSet.chipResult_get(
            chipPlacement.chipRef.chipId
        )
        if not result_isOkCheck(chipResult):
            continue
        visibleBounds = _visibleChipDrawBounds_build(
            drawTopLeft=(
                placementGeometry.drawWorldColumn,
                placementGeometry.drawWorldRow,
            ),
            drawLines=chipDrawLines_build(chipResult.value),
        )
        if visibleBounds is None:
            continue
        drawRow0, drawCol0, drawRow1, drawCol1 = visibleBounds
        pad = moduleBoundaryPaddingCells
        moduleName = chipPlacement.chipRef.chipId.moduleName
        moduleSide = moduleSidesByName.get(moduleName)
        if moduleSide is BoardSide.WEST:
            leftPad = pad
            rightPad = pad
            topPad = pad
            bottomPad = pad
        elif moduleSide is BoardSide.EAST:
            leftPad = 0
            rightPad = pad
            topPad = pad
            bottomPad = pad
        elif moduleSide is BoardSide.NORTH:
            leftPad = pad
            rightPad = pad
            topPad = pad
            bottomPad = 0
        elif moduleSide is BoardSide.SOUTH:
            leftPad = pad
            rightPad = pad
            topPad = 0
            bottomPad = pad
        else:
            leftPad = pad
            rightPad = pad
            topPad = pad
            bottomPad = pad
        chipBounds = (
            drawRow0 - topPad,
            drawCol0 - leftPad,
            drawRow1 + bottomPad,
            drawCol1 + rightPad,
        )
        existingBounds = boundsByModuleMutable.get(moduleName)
        if existingBounds is None:
            boundsByModuleMutable[moduleName] = chipBounds
            continue
        boundsByModuleMutable[moduleName] = (
            min(existingBounds[0], chipBounds[0]),
            min(existingBounds[1], chipBounds[1]),
            max(existingBounds[2], chipBounds[2]),
            max(existingBounds[3], chipBounds[3]),
        )

    boundariesByName: dict[str, RoutingZoneRegionFrame] = {}
    for moduleName, (row0, col0, row1, col1) in boundsByModuleMutable.items():
        moduleSide = moduleSidesByName.get(moduleName)
        innerWidth = col1 - col0 - 1
        minimumInnerWidth = len("═ " + moduleName + " ")
        if innerWidth < minimumInnerWidth:
            if moduleSide is BoardSide.WEST:
                col0 = col1 - 1 - minimumInnerWidth
            else:
                col1 = col0 + 1 + minimumInnerWidth
        boundariesByName[f"module/{moduleName}"] = RoutingZoneRegionFrame(
            horizontalStart=col0,
            verticalStart=row0,
            horizontalSpan=col1 - col0 + 1,
            verticalSpan=row1 - row0 + 1,
        )
    return boundariesByName


def _visibleChipDrawBounds_build(
    *,
    drawTopLeft: tuple[int, int],
    drawLines: tuple[str, ...],
) -> tuple[int, int, int, int] | None:
    """Return the visible non-space bounds of one placed chip draw block."""

    worldCol0, worldRow0 = drawTopLeft
    topRow: int | None = None
    leftCol: int | None = None
    bottomRow: int | None = None
    rightCol: int | None = None

    for rowOffset, line in enumerate(drawLines):
        nonSpaceIndices = [index for index, character in enumerate(line) if character != " "]
        if not nonSpaceIndices:
            continue
        rowIndex = worldRow0 + rowOffset
        topRow = rowIndex if topRow is None else min(topRow, rowIndex)
        bottomRow = rowIndex if bottomRow is None else max(bottomRow, rowIndex)
        lineLeft = worldCol0 + min(nonSpaceIndices)
        lineRight = worldCol0 + max(nonSpaceIndices)
        leftCol = lineLeft if leftCol is None else min(leftCol, lineLeft)
        rightCol = lineRight if rightCol is None else max(rightCol, lineRight)

    if topRow is None or leftCol is None or bottomRow is None or rightCol is None:
        return None
    return (topRow, leftCol, bottomRow, rightCol)
