"""Adapters that build first-class board objects from existing engine inputs.

This module exists to keep the migration pragmatic. The current engine already
has working kernel geometry and attach-point computations. The board package
should reuse those as input facts while moving the canonical ownership of the
resulting board object into `signalflow.board`.
"""

from __future__ import annotations

from dataclasses import replace

from signalflow.board.board import Board
from signalflow.board.doctrine import (
    BoardChipPlacementPolicy,
    BoardDoctrine,
    BoardGeometrySpec,
    EffectiveBoundaryMode,
)
from signalflow.board.geometry import BoardGeometry, GeoOp, rules_apply
from signalflow.board.substrate import BoardSubstrate
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    BoardSense,
    BoardSide,
    RegionBand,
    RegionFamily,
    TerminalPositionsByChip,
    WorldFrame,
)
from signalflow.models import (
    CallingStack,
    ChipRef,
    CircuitDocument,
    Result,
    RoutingKernel,
    RoutingZone,
    RoutingZoneFrame,
    RoutingZoneId,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    callingStackResult_buildFromCircuitDocument,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneRegionByIdResult_get,
    routingZoneRegionSetAll_get,
)
from signalflow.models.chip import chipDrawGeometry_build
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.geometry_scope import (
    BoardGeometryScope,
    BoardGeometryScopeKind,
)
from signalflow.notation.sfn import sfN
from signalflow.routing.geometry import (
    ChipLocalGeometrySet,
    chipCanvasPlacementGeometry_build,
    chipLocalGeometrySetResult_buildFromChips,
    chipPlacementStackOffsetResult_build,
)

_DEFAULT_BOARD_GEOMETRY_SPEC = BoardGeometrySpec()


def _requiredRegionKey_get(area: sfN) -> str:
    regionKey = area.region_key
    assert regionKey is not None
    return regionKey


def board_buildFromKernel(
    *,
    routingZoneId: RoutingZoneId,
    side: str,
    routingZone: RoutingZone,
    kernel: RoutingKernel | None = None,
    circuitDocument: CircuitDocument,
    moduleBoundaryPaddingCells: int = 1,
    chipPlacementPolicy: BoardChipPlacementPolicy = (
        BoardChipPlacementPolicy.CENTROIDAL
    ),
    effectiveBoundaryMode: EffectiveBoundaryMode = (
        EffectiveBoundaryMode.LABEL_AWARE_MODULE_BOX
    ),
    geometrySpec: BoardGeometrySpec = _DEFAULT_BOARD_GEOMETRY_SPEC,
) -> Result[Board]:
    """Build a first-class board from placed-zone facts via the build pipeline.

    The full dependency graph lives in signalflow.board.pipeline.BOARD_BUILD_PIPELINE.
    Each stage declares its inputs by name; the executor resolves them from the
    context dict in declared order.  Adding a geometry modifier requires only
    updating the affected stage — all downstream stages re-run automatically.
    """

    from signalflow.board.pipeline import (  # lazy: avoids circular import
        BOARD_BUILD_PIPELINE,
        PipelineError,
        boardPipeline_run,
    )

    ctx = {
        "routingZoneId": routingZoneId,
        "side": side,
        "routingZone": routingZone,
        "circuitDocument": circuitDocument,
        "moduleBoundaryPaddingCells": moduleBoundaryPaddingCells,
        "chipPlacementPolicy": chipPlacementPolicy,
        "effectiveBoundaryMode": effectiveBoundaryMode,
        "geometrySpec": geometrySpec,
    }
    try:
        boardPipeline_run(BOARD_BUILD_PIPELINE, ctx)
    except PipelineError:
        return resultErr_build()
    return resultOk_build(ctx["board"])


def board_buildFromZoneAndSide(
    *,
    routingZoneId: RoutingZoneId,
    side: str,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    moduleBoundaryPaddingCells: int = 1,
    chipPlacementPolicy: BoardChipPlacementPolicy = (
        BoardChipPlacementPolicy.CENTROIDAL
    ),
    effectiveBoundaryMode: EffectiveBoundaryMode = (
        EffectiveBoundaryMode.LABEL_AWARE_MODULE_BOX
    ),
    geometrySpec: BoardGeometrySpec = _DEFAULT_BOARD_GEOMETRY_SPEC,
) -> Result[Board]:
    """Build a board from a zone-local substrate role.

    This is the preferred active entrypoint. It derives any transitional
    `RoutingKernel` seed internally from the zone's region set instead of
    requiring callers to thread a kernel-shaped object through the runtime.
    """

    return board_buildFromKernel(
        routingZoneId=routingZoneId,
        side=side,
        routingZone=routingZone,
        circuitDocument=circuitDocument,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
        chipPlacementPolicy=chipPlacementPolicy,
        effectiveBoundaryMode=effectiveBoundaryMode,
        geometrySpec=geometrySpec,
    )


def _boardWorldFrame_build(
    *,
    geometry: BoardGeometry,
    fallbackFrame: RoutingZoneFrame | RoutingZoneRegionFrame,
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

    for scope in geometry.geometryScopes:
        if scope.frame is None:
            continue
        leftColumns.append(scope.frame.horizontalStart)
        topRows.append(scope.frame.verticalStart)
        rightColumns.append(scope.frame.horizontalEnd_calculate() - 1)
        bottomRows.append(scope.frame.verticalEnd_calculate() - 1)

    for chipPlacement in geometry.chipDrawPlacementsByChip.values():
        chipFrame = chipPlacement.worldFrame_get()
        leftColumns.append(chipFrame.topLeft[0])
        topRows.append(chipFrame.topLeft[1])
        rightColumns.append(chipFrame.bottomRight[0])
        bottomRows.append(chipFrame.bottomRight[1])

    if not leftColumns:
        return WorldFrame(
            topLeft=(
                fallbackFrame.horizontalStart,
                fallbackFrame.verticalStart,
            ),
            bottomRight=(
                fallbackFrame.horizontalEnd_calculate() - 1,
                fallbackFrame.verticalEnd_calculate() - 1,
            ),
        )

    return WorldFrame(
        topLeft=(min(leftColumns), min(topRows)),
        bottomRight=(max(rightColumns), max(bottomRows)),
    )


def UNUSED_legacyRegionFramesFromZone_build(
    routingZone: RoutingZone,
) -> tuple[
    dict[BoardRegionId, RoutingZoneRegionFrame],
    dict[BoardRegionId, RoutingZoneRegionId],
]:
    """Return compatibility substrate copied from the zone-owned region set.

    This remains only as a fallback until every board sense is built natively
    from board-side geometry derivation.
    """

    from signalflow.board.types import (
        boardRegionId_buildFromRoutingZoneRegionId,
    )

    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = {}
    routingZoneRegionIdsById: dict[BoardRegionId, RoutingZoneRegionId] = {}
    for routingZoneRegion in routingZoneRegionSetAll_get(routingZone):
        regionId = routingZoneRegion.routingZoneRegionId
        boardRegionId = boardRegionId_buildFromRoutingZoneRegionId(regionId)
        regionFramesById[boardRegionId] = (
            routingZoneRegion.routingZoneRegionFrame
        )
        routingZoneRegionIdsById[boardRegionId] = regionId
    return regionFramesById, routingZoneRegionIdsById


def _wteCoreRegionFrames_build(
    *,
    routingZoneId: RoutingZoneId,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    geometrySpec: BoardGeometrySpec,
    moduleBoundaryPaddingCells: int,
    terminalPositionsByChip: TerminalPositionsByChip,
    chipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement],
) -> tuple[
    dict[BoardRegionId, RoutingZoneRegionFrame],
    dict[BoardRegionId, RoutingZoneRegionId],
]:
    """Build the WTE intra substrate from board-owned geometry inputs.

    The first clean-room cut still accepts temporary placed-zone facts for the
    west/east chip-terminal envelopes, but the rest of the intra substrate is
    derived here from board policy and live board inputs rather than copied
    from the kernel region set wholesale.
    """

    terminalFramesBySide = _terminalFramesBySide_build(routingZone)
    westTerminalFrame = terminalFramesBySide.get(BoardSide.WEST)
    eastTerminalFrame = terminalFramesBySide.get(BoardSide.EAST)
    if westTerminalFrame is None or eastTerminalFrame is None:
        return {}, {}

    wireDemand = _wireDemand_calculate(
        circuitDocument=circuitDocument,
        routingZone=routingZone,
    )
    intraLatitudeDemand = _intraParentToChildDemand_calculate(
        circuitDocument=circuitDocument,
        routingZone=routingZone,
    )
    channelSpan = max(1, wireDemand)
    latRows = max(1, intraLatitudeDemand)

    sideVisibleWidthBySide: dict[BoardSide, int] = {
        side: max(
            (
                visibleBounds[3]
                - visibleBounds[1]
                + 1
                for chipPlacement in chipDrawPlacementsByChip.values()
                if chipPlacement.side is side
                for visibleBounds in (
                    _visibleChipDrawBounds_build(
                        drawTopLeft=chipPlacement.drawTopLeft,
                        drawLines=chipPlacement.drawLines,
                    ),
                )
                if visibleBounds is not None
            ),
            default=0,
        )
        for side in (BoardSide.WEST, BoardSide.EAST)
    }
    westTerminalSpan = max(
        westTerminalFrame.horizontalSpan,
        sideVisibleWidthBySide[BoardSide.WEST]
        + (2 * moduleBoundaryPaddingCells),
    )
    eastTerminalSpan = max(
        eastTerminalFrame.horizontalSpan,
        sideVisibleWidthBySide[BoardSide.EAST]
        + (2 * moduleBoundaryPaddingCells),
    )
    westFanSpan = geometrySpec.intra.wFanSpan
    eastFanSpan = geometrySpec.intra.eFanSpan

    westTerminalLeft = westTerminalFrame.horizontalStart
    eastTerminalLeft = (
        eastTerminalFrame.horizontalStart
        + (westTerminalSpan - westTerminalFrame.horizontalSpan)
    )
    westFanLeft = westTerminalLeft + westTerminalSpan
    # Gap of _MEDIAL_SPAN between Wfi and Wi reserved for Wm pillar.
    _MEDIAL_SPAN = 2
    westLongLeft = westFanLeft + westFanSpan + _MEDIAL_SPAN
    eastFanLeft = eastTerminalLeft - eastFanSpan
    # Gap of _MEDIAL_SPAN between Ei and Efi reserved for Em pillar.
    eastLongLeft = eastFanLeft - _MEDIAL_SPAN - channelSpan
    courtyardLeft = westLongLeft + channelSpan
    courtyardSpan = eastLongLeft - courtyardLeft
    if courtyardSpan <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.LAYOUT,
            code="board.wte.courtyard_span_zero",
            message=(
                "courtyard span "
                f"{courtyardSpan} <= 0 for zone {routingZoneId} — "
                f"chip terminals too close together "
                f"(westLongLeft={westLongLeft}, eastLongLeft={eastLongLeft}, "
                "channelSpan="
                f"{channelSpan}). Apply a Wt displacement to widen the zone."
            ),
        )
        return {}, {}

    terminalTopRow = min(
        westTerminalFrame.verticalStart,
        eastTerminalFrame.verticalStart,
    )
    terminalBottomRow = max(
        westTerminalFrame.verticalEnd_calculate() - 1,
        eastTerminalFrame.verticalEnd_calculate() - 1,
    )
    northLatStart, southLatStart = _latitudeBandStarts_build(
        terminalTopRow=terminalTopRow,
        terminalBottomRow=terminalBottomRow,
        latRows=latRows,
        terminalPositionsByChip=terminalPositionsByChip,
    )
    northLatEnd = northLatStart + latRows - 1
    southLatEnd = southLatStart + latRows - 1

    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = {}
    routingZoneRegionIdsById: dict[BoardRegionId, RoutingZoneRegionId] = {}

    def _set_frame(
        regionId: BoardRegionId,
        *,
        horizontalStart: int,
        verticalStart: int,
        horizontalSpan: int,
        verticalSpan: int,
    ) -> None:
        if horizontalSpan <= 0 or verticalSpan <= 0:
            return
        regionFramesById[regionId] = RoutingZoneRegionFrame(
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            horizontalSpan=horizontalSpan,
            verticalSpan=verticalSpan,
        )
        routingZoneRegionIdsById[regionId] = (
            _routingZoneRegionIdFromBoardRegionId_build(
                routingZoneId=routingZoneId,
                regionId=regionId,
            )
        )

    _set_frame(
        BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.WEST,
        ),
        horizontalStart=westTerminalLeft,
        verticalStart=westTerminalFrame.verticalStart,
        horizontalSpan=westTerminalSpan,
        verticalSpan=westTerminalFrame.verticalSpan,
    )
    _set_frame(
        BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.EAST,
        ),
        horizontalStart=eastTerminalLeft,
        verticalStart=eastTerminalFrame.verticalStart,
        horizontalSpan=eastTerminalSpan,
        verticalSpan=eastTerminalFrame.verticalSpan,
    )
    _set_frame(
        BoardRegionId(family=RegionFamily.INTRA_FAN, side=BoardSide.WEST),
        horizontalStart=westFanLeft,
        verticalStart=westTerminalFrame.verticalStart,
        horizontalSpan=westFanSpan,
        verticalSpan=westTerminalFrame.verticalSpan,
    )
    _set_frame(
        BoardRegionId(family=RegionFamily.INTRA_FAN, side=BoardSide.EAST),
        horizontalStart=eastFanLeft,
        verticalStart=eastTerminalFrame.verticalStart,
        horizontalSpan=eastFanSpan,
        verticalSpan=eastTerminalFrame.verticalSpan,
    )

    for side, longLeft in (
        (BoardSide.WEST, westLongLeft),
        (BoardSide.EAST, eastLongLeft),
    ):
        _set_frame(
            BoardRegionId(
                family=RegionFamily.INTRA_LONGITUDE,
                side=side,
                band=RegionBand.UPPER,
            ),
            horizontalStart=longLeft,
            verticalStart=terminalTopRow,
            horizontalSpan=channelSpan,
            verticalSpan=northLatEnd - terminalTopRow + 1,
        )
        _set_frame(
            BoardRegionId(
                family=RegionFamily.INTRA_LONGITUDE,
                side=side,
                band=RegionBand.LOWER,
            ),
            horizontalStart=longLeft,
            verticalStart=southLatStart,
            horizontalSpan=channelSpan,
            verticalSpan=terminalBottomRow - southLatStart + 1,
        )

    _set_frame(
        BoardRegionId(
            family=RegionFamily.INTRA_LATITUDE,
            side=BoardSide.NORTH,
        ),
        horizontalStart=courtyardLeft,
        verticalStart=northLatStart,
        horizontalSpan=courtyardSpan,
        verticalSpan=latRows,
    )
    _set_frame(
        BoardRegionId(
            family=RegionFamily.INTRA_LATITUDE,
            side=BoardSide.SOUTH,
        ),
        horizontalStart=courtyardLeft,
        verticalStart=southLatStart,
        horizontalSpan=courtyardSpan,
        verticalSpan=latRows,
    )

    dummyHorizontalStart = westLongLeft
    dummyHorizontalSpan = channelSpan + courtyardSpan + channelSpan
    dummyNorthFanStart = northLatStart - 1
    dummyNorthTerminalStart = dummyNorthFanStart - 1
    dummySouthFanStart = southLatEnd + 1
    dummySouthTerminalStart = dummySouthFanStart + 1
    _set_frame(
        BoardRegionId(family=RegionFamily.INTRA_FAN, side=BoardSide.NORTH),
        horizontalStart=dummyHorizontalStart,
        verticalStart=dummyNorthFanStart,
        horizontalSpan=dummyHorizontalSpan,
        verticalSpan=1,
    )
    _set_frame(
        BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.NORTH,
        ),
        horizontalStart=dummyHorizontalStart,
        verticalStart=dummyNorthTerminalStart,
        horizontalSpan=dummyHorizontalSpan,
        verticalSpan=1,
    )
    _set_frame(
        BoardRegionId(family=RegionFamily.INTRA_FAN, side=BoardSide.SOUTH),
        horizontalStart=dummyHorizontalStart,
        verticalStart=dummySouthFanStart,
        horizontalSpan=dummyHorizontalSpan,
        verticalSpan=1,
    )
    _set_frame(
        BoardRegionId(
            family=RegionFamily.CHIP_TERMINAL,
            side=BoardSide.SOUTH,
        ),
        horizontalStart=dummyHorizontalStart,
        verticalStart=dummySouthTerminalStart,
        horizontalSpan=dummyHorizontalSpan,
        verticalSpan=1,
    )

    return regionFramesById, routingZoneRegionIdsById


def _terminalFramesBySide_build(
    routingZone: RoutingZone,
) -> dict[BoardSide, RoutingZoneRegionFrame]:
    """Return chip-terminal envelopes from the zone-owned region set."""

    result: dict[BoardSide, RoutingZoneRegionFrame] = {}
    for routingZoneRegion in routingZoneRegionSetAll_get(routingZone):
        regionId = routingZoneRegion.routingZoneRegionId
        if (
            regionId.routingZoneRegionKind
            is not RoutingZoneRegionKind.CHIP_TERMINAL
        ):
            continue
        regionSide = regionId.routingZoneRegionSide
        if regionSide is None:
            continue
        boardSide = BoardSide(regionSide.value)
        frame = routingZoneRegion.routingZoneRegionFrame
        existingFrame = result.get(boardSide)
        if existingFrame is None:
            result[boardSide] = frame
            continue
        left = min(existingFrame.horizontalStart, frame.horizontalStart)
        top = min(existingFrame.verticalStart, frame.verticalStart)
        right = max(
            existingFrame.horizontalEnd_calculate() - 1,
            frame.horizontalEnd_calculate() - 1,
        )
        bottom = max(
            existingFrame.verticalEnd_calculate() - 1,
            frame.verticalEnd_calculate() - 1,
        )
        result[boardSide] = RoutingZoneRegionFrame(
            horizontalStart=left,
            verticalStart=top,
            horizontalSpan=right - left + 1,
            verticalSpan=bottom - top + 1,
        )
    return result


def _wireDemand_calculate(
    *,
    circuitDocument: CircuitDocument,
    routingZone: RoutingZone,
) -> int:
    """Return the total directed local wire demand for one placed zone."""

    zoneChipIds = {
        chipPlacement.chipRef.chipId
        for chipPlacement in routingZone.chipPlacementSet.placements
    }
    wireDemand = 0
    for call in circuitDocument.circuitCallSet.circuitCalls:
        if (
            call.sourceChipRef.chipId in zoneChipIds
            and call.destinationChipRef.chipId in zoneChipIds
        ):
            wireDemand += 2
    return wireDemand


def _intraParentToChildDemand_calculate(
    *,
    circuitDocument: CircuitDocument,
    routingZone: RoutingZone,
) -> int:
    """Return the WTE intra-latitude demand for one placed zone.

    Only parent-to-child same-zone calls consume `Ni`/`Si` capacity. Outer
    arc and U-turn families should not widen the inner latitude bands.
    """

    callingStackResult: Result[CallingStack] = (
        callingStackResult_buildFromCircuitDocument(circuitDocument)
    )
    if not result_isOkCheck(callingStackResult):
        return 0

    zoneChipRefs = {
        chipPlacement.chipRef
        for chipPlacement in routingZone.chipPlacementSet.placements
    }
    intraDemand = 0
    for call in circuitDocument.circuitCallSet.circuitCalls:
        if (
            call.sourceChipRef not in zoneChipRefs
            or call.destinationChipRef not in zoneChipRefs
        ):
            continue
        depthDelta = callingStackResult.value.deltaOrNone_get(
            call.sourceChipRef,
            call.destinationChipRef,
        )
        if depthDelta is not None and depthDelta > 0:
            intraDemand += 1
    return intraDemand


def _outerDemand_calculate(
    *,
    circuitDocument: CircuitDocument,
    routingZone: RoutingZone,
) -> int:
    """Return the concrete WTE outer-ring lane demand for one placed zone.

    Outer demand counts directed wires, not just abstract call obligations.
    Each same-zone call that classifies to an outer family contributes one
    signal wire and one paired return wire, so it consumes two outer lanes.
    """

    callingStackResult: Result[CallingStack] = (
        callingStackResult_buildFromCircuitDocument(circuitDocument)
    )
    if not result_isOkCheck(callingStackResult):
        return 0

    zoneChipRefs = {
        chipPlacement.chipRef
        for chipPlacement in routingZone.chipPlacementSet.placements
    }
    outerDemand = 0
    for call in circuitDocument.circuitCallSet.circuitCalls:
        if (
            call.sourceChipRef not in zoneChipRefs
            or call.destinationChipRef not in zoneChipRefs
        ):
            continue
        depthDelta = callingStackResult.value.deltaOrNone_get(
            call.sourceChipRef,
            call.destinationChipRef,
        )
        if depthDelta is not None and depthDelta <= 0:
            outerDemand += 2
    return outerDemand


def _latitudeBandStarts_build(
    *,
    terminalTopRow: int,
    terminalBottomRow: int,
    latRows: int,
    terminalPositionsByChip: TerminalPositionsByChip,
) -> tuple[int, int]:
    """Return north/south latitude start rows centered on live terminals."""

    terminalRows = [
        worldRow
        for chipTerminalPositions in terminalPositionsByChip.values()
        for _, worldRow in chipTerminalPositions.values()
    ]
    if terminalRows:
        centroid = sum(terminalRows) / len(terminalRows)
    else:
        centroid = (terminalTopRow + terminalBottomRow) / 2

    northEnd = int(centroid // 1)
    northStart = northEnd - latRows + 1
    southStart = northEnd + 1
    southEnd = southStart + latRows - 1

    if northStart < terminalTopRow:
        shift = terminalTopRow - northStart
        northStart += shift
        southStart += shift
        southEnd += shift
    if southEnd > terminalBottomRow:
        shift = southEnd - terminalBottomRow
        northStart -= shift
        southStart -= shift

    northStart = max(terminalTopRow, northStart)
    southStart = max(northStart + latRows, southStart)
    maxSouthStart = terminalBottomRow - latRows + 1
    southStart = min(maxSouthStart, southStart)
    northStart = southStart - latRows
    return northStart, southStart


def _routingZoneRegionIdFromBoardRegionId_build(
    *,
    routingZoneId: RoutingZoneId,
    regionId: BoardRegionId,
) -> RoutingZoneRegionId:
    """Return a legacy-compatible region id for one core board region."""

    kindByFamily: dict[RegionFamily, RoutingZoneRegionKind] = {
        RegionFamily.CHIP_TERMINAL: RoutingZoneRegionKind.CHIP_TERMINAL,
        RegionFamily.INTRA_FAN: RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RegionFamily.INTRA_TRANSITION: (
            RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION
        ),
        RegionFamily.INTRA_LONGITUDE: (
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE
        ),
        RegionFamily.INTRA_LATITUDE: (
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE
        ),
    }
    side = None
    if regionId.side is not None:
        side = RoutingZoneRegionSide(regionId.side.value)
    tag = None
    if regionId.band is not None:
        tag = regionId.band.value
    elif regionId.branch is not None:
        tag = regionId.branch.value
    return RoutingZoneRegionId(
        routingZoneId=routingZoneId,
        routingZoneRegionKind=kindByFamily[regionId.family],
        routingZoneRegionSide=side,
        routingZoneRegionTag=tag,
    )


def _extraGeometry_build(
    *,
    effectiveGeometry: BoardGeometry,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    spec: BoardGeometrySpec = _DEFAULT_BOARD_GEOMETRY_SPEC,
) -> Result[BoardGeometry]:
    """Append extra perimeter region frames to the effective geometry.

    The four extra families — xwLong, xeLong, xnLat, xsLat — form a
    concentric ring outside the intra substrate. Spans are driven by the
    `BoardGeometrySpec` parameter (defaults to `BoardGeometrySpec()` which
    carries the canonical defaults as frozen field values).

    Only WTE/ETW sense is handled. NTS/STN returns the geometry unchanged.

    The extra longitude families span the full outer perimeter height,
    including the rows occupied by the extra latitude families. The extra
    latitude families span the full outer perimeter width, including the
    columns occupied by the extra longitude families.
    """
    outerDemand = _outerDemand_calculate(
        circuitDocument=circuitDocument,
        routingZone=routingZone,
    )
    outerSpan = max(
        2,
        outerDemand,
        spec.extra.wLongSpan,
        spec.extra.eLongSpan,
        spec.extra.nSpan,
        spec.extra.sSpan,
    )
    xwLongSpan = outerSpan
    xeLongSpan = outerSpan
    xnLatSpan = outerSpan
    xsLatSpan = outerSpan
    xwFanSpan = spec.extra.wFanSpan
    xeFanSpan = spec.extra.eFanSpan

    sense = _boardSense_build(routingZone)
    if sense not in (BoardSense.WEST_TO_EAST, BoardSense.EAST_TO_WEST):
        return resultOk_build(effectiveGeometry)

    regionFramesById = dict(effectiveGeometry.regionFramesById)
    geometryScopes = effectiveGeometry.geometryScopes

    westChipTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL, side=BoardSide.WEST
    )
    eastChipTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL, side=BoardSide.EAST
    )

    westChipTerminalFrame = regionFramesById.get(westChipTerminalId)
    eastChipTerminalFrame = regionFramesById.get(eastChipTerminalId)

    if westChipTerminalFrame is None:
        return resultErr_build()

    moduleSidesByName = _moduleSidesByName_build(routingZone)
    eastBoundaryFrames = [
        scope.frame
        for scope in geometryScopes
        if _scopeSide_get(scope, moduleSidesByName) is BoardSide.EAST
        and scope.frame is not None
    ]
    if eastBoundaryFrames:
        eastBoundaryRight = max(
            f.horizontalEnd_calculate() - 1 for f in eastBoundaryFrames
        )
    elif eastChipTerminalFrame is not None:
        eastBoundaryRight = eastChipTerminalFrame.horizontalEnd_calculate() - 1
    else:
        return resultErr_build()

    # Bounding box of the intra substrate: take the union across both chip
    # terminal faces. This ensures xnLat/xsLat have a constant lane count
    # (xnLatSpan / xsLatSpan rows) above/below every part of the substrate,
    # not just above the west face. N/S dummy frames are re-stacked outside
    # xnLat/xsLat after those are placed.
    chipTerminalTops = [westChipTerminalFrame.verticalStart]
    chipTerminalBottoms = [westChipTerminalFrame.verticalEnd_calculate() - 1]
    if eastChipTerminalFrame is not None:
        chipTerminalTops.append(eastChipTerminalFrame.verticalStart)
        chipTerminalBottoms.append(
            eastChipTerminalFrame.verticalEnd_calculate() - 1
        )
    intraNorthTop = min(chipTerminalTops)
    intraSouthBottom = max(chipTerminalBottoms)

    extraTop = intraNorthTop - xnLatSpan
    extraBottom = intraSouthBottom + xsLatSpan
    xwFanLeft = westChipTerminalFrame.horizontalStart - xwFanSpan
    xwLongLeft = xwFanLeft - xwLongSpan
    xeFanLeft = eastBoundaryRight + 1
    xeLongLeft = xeFanLeft + xeFanSpan
    extraWidth = (xeLongLeft + xeLongSpan - 1) - xwLongLeft + 1
    extraHeight = extraBottom - extraTop + 1

    regionFramesById[
        BoardRegionId(family=RegionFamily.EXTRA_LONGITUDE, side=BoardSide.WEST)
    ] = RoutingZoneRegionFrame(
        horizontalStart=xwLongLeft,
        verticalStart=extraTop,
        horizontalSpan=xwLongSpan,
        verticalSpan=extraHeight,
    )
    regionFramesById[
        BoardRegionId(family=RegionFamily.EXTRA_LONGITUDE, side=BoardSide.EAST)
    ] = RoutingZoneRegionFrame(
        horizontalStart=xeLongLeft,
        verticalStart=extraTop,
        horizontalSpan=xeLongSpan,
        verticalSpan=extraHeight,
    )
    regionFramesById[
        BoardRegionId(family=RegionFamily.EXTRA_LATITUDE, side=BoardSide.NORTH)
    ] = RoutingZoneRegionFrame(
        horizontalStart=xwLongLeft,
        verticalStart=extraTop,
        horizontalSpan=extraWidth,
        verticalSpan=xnLatSpan,
    )
    regionFramesById[
        BoardRegionId(family=RegionFamily.EXTRA_LATITUDE, side=BoardSide.SOUTH)
    ] = RoutingZoneRegionFrame(
        horizontalStart=xwLongLeft,
        verticalStart=intraSouthBottom + 1,
        horizontalSpan=extraWidth,
        verticalSpan=xsLatSpan,
    )

    # Extra fan regions between extra longitude and chip terminal faces.
    xFanVerticalStart = westChipTerminalFrame.verticalStart
    xFanVerticalSpan = westChipTerminalFrame.verticalSpan
    regionFramesById[
        BoardRegionId(family=RegionFamily.EXTRA_FAN, side=BoardSide.WEST)
    ] = RoutingZoneRegionFrame(
        horizontalStart=xwFanLeft,
        verticalStart=xFanVerticalStart,
        horizontalSpan=xwFanSpan,
        verticalSpan=xFanVerticalSpan,
    )
    regionFramesById[
        BoardRegionId(family=RegionFamily.EXTRA_FAN, side=BoardSide.EAST)
    ] = RoutingZoneRegionFrame(
        horizontalStart=xeFanLeft,
        verticalStart=(
            eastChipTerminalFrame.verticalStart
            if eastChipTerminalFrame is not None
            else xFanVerticalStart
        ),
        horizontalSpan=xeFanSpan,
        verticalSpan=(
            eastChipTerminalFrame.verticalSpan
            if eastChipTerminalFrame is not None
            else xFanVerticalSpan
        ),
    )

    # Medial longitude pillars (Wm/Em): derived from board geometry, not the
    # kernel zone. Kernel placement uses rough chip-width estimates that
    # diverge
    # from actual chip geometry. Anchor on Wfi (Wm flush east of Wfi) and Ei
    # (Em flush east of Ei). Vertical extent covers full extra band so transfer
    # corners can intersect Ne/Se latitude bands.
    routingZoneRegionIdsById = dict(effectiveGeometry.routingZoneRegionIdsById)
    _MEDIAL_SPAN = 2
    wfiFrame = regionFramesById.get(
        BoardRegionId(family=RegionFamily.INTRA_FAN, side=BoardSide.WEST)
    )
    eiFrame = regionFramesById.get(
        BoardRegionId(
            family=RegionFamily.INTRA_LONGITUDE,
            side=BoardSide.EAST,
            band=RegionBand.UPPER,
        )
    )
    if wfiFrame is not None:
        wmId = BoardRegionId(
            family=RegionFamily.MEDIAL_LONGITUDE,
            side=BoardSide.WEST,
        )
        regionFramesById[wmId] = RoutingZoneRegionFrame(
            horizontalStart=wfiFrame.horizontalStart + wfiFrame.horizontalSpan,
            verticalStart=extraTop,
            horizontalSpan=_MEDIAL_SPAN,
            verticalSpan=extraHeight,
        )
        routingZoneRegionIdsById[wmId] = RoutingZoneRegionId(
            routingZoneId=routingZone.routingZoneId,
            routingZoneRegionKind=RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE_MEDIAL,
            routingZoneRegionSide=RoutingZoneRegionSide.WEST,
            routingZoneRegionTag=None,
        )
    if eiFrame is not None:
        emId = BoardRegionId(
            family=RegionFamily.MEDIAL_LONGITUDE,
            side=BoardSide.EAST,
        )
        regionFramesById[emId] = RoutingZoneRegionFrame(
            horizontalStart=eiFrame.horizontalStart + eiFrame.horizontalSpan,
            verticalStart=extraTop,
            horizontalSpan=_MEDIAL_SPAN,
            verticalSpan=extraHeight,
        )
        routingZoneRegionIdsById[emId] = RoutingZoneRegionId(
            routingZoneId=routingZone.routingZoneId,
            routingZoneRegionKind=RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE_MEDIAL,
            routingZoneRegionSide=RoutingZoneRegionSide.EAST,
            routingZoneRegionTag=None,
        )

    # Re-stack N/S dummy chip-terminal and fan frames outside xnLat/xsLat so
    # the extra latitude bands connect directly to the intra longitude bands.
    xsLatBottom = intraSouthBottom + xsLatSpan
    northFanId = BoardRegionId(
        family=RegionFamily.INTRA_FAN, side=BoardSide.NORTH
    )
    northTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL, side=BoardSide.NORTH
    )
    southFanId = BoardRegionId(
        family=RegionFamily.INTRA_FAN, side=BoardSide.SOUTH
    )
    southTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL, side=BoardSide.SOUTH
    )
    northFanFrame = regionFramesById.get(northFanId)
    northTerminalFrame = regionFramesById.get(northTerminalId)
    southFanFrame = regionFramesById.get(southFanId)
    southTerminalFrame = regionFramesById.get(southTerminalId)
    if northFanFrame is not None:
        northFanStart = extraTop - northFanFrame.verticalSpan
        regionFramesById[northFanId] = RoutingZoneRegionFrame(
            horizontalStart=northFanFrame.horizontalStart,
            verticalStart=northFanStart,
            horizontalSpan=northFanFrame.horizontalSpan,
            verticalSpan=northFanFrame.verticalSpan,
        )
        if northTerminalFrame is not None:
            regionFramesById[northTerminalId] = RoutingZoneRegionFrame(
                horizontalStart=northTerminalFrame.horizontalStart,
                verticalStart=northFanStart - northTerminalFrame.verticalSpan,
                horizontalSpan=northTerminalFrame.horizontalSpan,
                verticalSpan=northTerminalFrame.verticalSpan,
            )
    elif northTerminalFrame is not None:
        regionFramesById[northTerminalId] = RoutingZoneRegionFrame(
            horizontalStart=northTerminalFrame.horizontalStart,
            verticalStart=extraTop - northTerminalFrame.verticalSpan,
            horizontalSpan=northTerminalFrame.horizontalSpan,
            verticalSpan=northTerminalFrame.verticalSpan,
        )
    if southFanFrame is not None:
        southFanStart = xsLatBottom + 1
        regionFramesById[southFanId] = RoutingZoneRegionFrame(
            horizontalStart=southFanFrame.horizontalStart,
            verticalStart=southFanStart,
            horizontalSpan=southFanFrame.horizontalSpan,
            verticalSpan=southFanFrame.verticalSpan,
        )
        if southTerminalFrame is not None:
            regionFramesById[southTerminalId] = RoutingZoneRegionFrame(
                horizontalStart=southTerminalFrame.horizontalStart,
                verticalStart=southFanStart + southFanFrame.verticalSpan,
                horizontalSpan=southTerminalFrame.horizontalSpan,
                verticalSpan=southTerminalFrame.verticalSpan,
            )
    elif southTerminalFrame is not None:
        regionFramesById[southTerminalId] = RoutingZoneRegionFrame(
            horizontalStart=southTerminalFrame.horizontalStart,
            verticalStart=xsLatBottom + 1,
            horizontalSpan=southTerminalFrame.horizontalSpan,
            verticalSpan=southTerminalFrame.verticalSpan,
        )

    return resultOk_build(
        BoardGeometry(
            regionFramesById=regionFramesById,
            routingZoneRegionIdsById=routingZoneRegionIdsById,
            geometryScopes=effectiveGeometry.geometryScopes,
            exactTerminalWorldPositionsByChip=(
                effectiveGeometry.exactTerminalWorldPositionsByChip
            ),
            chipDrawPlacementsByChip=effectiveGeometry.chipDrawPlacementsByChip,
        )
    )


def _effectiveGeometry_build(
    *,
    substrateGeometry: BoardGeometry,
    routingZone: RoutingZone,
    moduleBoundaryPaddingCells: int,
    chipPlacementPolicy: BoardChipPlacementPolicy,
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

    _ = chipPlacementPolicy
    regionFramesById = dict(substrateGeometry.regionFramesById)
    geometryScopes = substrateGeometry.geometryScopes
    if not regionFramesById or not geometryScopes:
        return substrateGeometry

    sense = _boardSense_build(routingZone)

    moduleSidesByName = _moduleSidesByName_build(routingZone)
    if sense in (BoardSense.WEST_TO_EAST, BoardSense.EAST_TO_WEST):
        sideVisibleBoundsBySide: dict[
            BoardSide, tuple[tuple[int, int, int, int], ...]
        ] = {
            side: tuple(
                bounds
                for chipPlacement in (
                    substrateGeometry.chipDrawPlacementsByChip.values()
                )
                if chipPlacement.side is side
                for bounds in (
                    _visibleChipDrawBounds_build(
                        drawTopLeft=chipPlacement.drawTopLeft,
                        drawLines=chipPlacement.drawLines,
                    ),
                )
                if bounds is not None
            )
            for side in (BoardSide.WEST, BoardSide.EAST)
        }
        sideVisibleWidthBySide: dict[BoardSide, int] = {
            side: max(
                (
                    bounds[3] - bounds[1] + 1
                    for bounds in sideVisibleBounds
                ),
                default=0,
            )
            for side, sideVisibleBounds in sideVisibleBoundsBySide.items()
        }
        westBoundaryFrames = [
            scope.frame
            for scope in geometryScopes
            if _scopeSide_get(scope, moduleSidesByName) == BoardSide.WEST
            and scope.frame is not None
        ]
        eastBoundaryFrames = [
            scope.frame
            for scope in geometryScopes
            if _scopeSide_get(scope, moduleSidesByName) == BoardSide.EAST
            and scope.frame is not None
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
        westBoundaryTop = min(f.verticalStart for f in westBoundaryFrames)
        westBoundaryBottom = max(
            f.verticalEnd_calculate() - 1 for f in westBoundaryFrames
        )
        eastBoundaryTop = min(f.verticalStart for f in eastBoundaryFrames)
        eastBoundaryBottom = max(
            f.verticalEnd_calculate() - 1 for f in eastBoundaryFrames
        )

        westFanId = BoardRegionId(
            family=RegionFamily.INTRA_FAN, side=BoardSide.WEST
        )
        eastFanId = BoardRegionId(
            family=RegionFamily.INTRA_FAN, side=BoardSide.EAST
        )

        westEnvelopeGrowthColumns = max(
            0,
            (westBoundary.horizontalEnd_calculate() - 1)
            - (westChipTerminalFrame.horizontalEnd_calculate() - 1),
        )
        transformedFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = {}
        for regionId, frame in regionFramesById.items():
            if regionId == westChipTerminalId:
                westTerminalStart = frame.horizontalStart
                westTerminalEnd = max(
                    frame.horizontalEnd_calculate() - 1,
                    westBoundary.horizontalEnd_calculate() - 1,
                    westTerminalStart
                    + sideVisibleWidthBySide[BoardSide.WEST]
                    + (2 * moduleBoundaryPaddingCells)
                    - 1,
                )
                westTop = min(frame.verticalStart, westBoundaryTop)
                westBottom = max(
                    frame.verticalEnd_calculate() - 1, westBoundaryBottom
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=westTerminalStart,
                    verticalStart=westTop,
                    horizontalSpan=westTerminalEnd - westTerminalStart + 1,
                    verticalSpan=westBottom - westTop + 1,
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
                    shiftedFrame.horizontalStart
                    + sideVisibleWidthBySide[BoardSide.EAST]
                    + (2 * moduleBoundaryPaddingCells)
                    - 1,
                )
                eastTop = min(shiftedFrame.verticalStart, eastBoundaryTop)
                eastBottom = max(
                    shiftedFrame.verticalEnd_calculate() - 1,
                    eastBoundaryBottom,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=eastTop,
                    horizontalSpan=eastTerminalEnd
                    - shiftedFrame.horizontalStart
                    + 1,
                    verticalSpan=eastBottom - eastTop + 1,
                )
                continue

            if regionId == westFanId:
                westTop = min(shiftedFrame.verticalStart, westBoundaryTop)
                westBottom = max(
                    shiftedFrame.verticalEnd_calculate() - 1,
                    westBoundaryBottom,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=westTop,
                    horizontalSpan=shiftedFrame.horizontalSpan,
                    verticalSpan=westBottom - westTop + 1,
                )
                continue

            if regionId == eastFanId:
                eastTop = min(shiftedFrame.verticalStart, eastBoundaryTop)
                eastBottom = max(
                    shiftedFrame.verticalEnd_calculate() - 1,
                    eastBoundaryBottom,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=eastTop,
                    horizontalSpan=shiftedFrame.horizontalSpan,
                    verticalSpan=eastBottom - eastTop + 1,
                )
                continue

            transformedFramesById[regionId] = shiftedFrame

        transformedWestChipTerminalFrame = transformedFramesById[
            westChipTerminalId
        ]
        transformedEastChipTerminalFrame = transformedFramesById[
            eastChipTerminalId
        ]

        shiftedGeometryScopesList: list[BoardGeometryScope] = []
        for scope in geometryScopes:
            if scope.frame is None:
                shiftedGeometryScopesList.append(scope)
                continue
            frame = scope.frame
            scopeSide = _scopeSide_get(scope, moduleSidesByName)
            if scopeSide is BoardSide.EAST:
                shiftedFrame = _frameShiftedHorizontally_build(
                    frame,
                    deltaColumns=westEnvelopeGrowthColumns,
                )
                shiftedRightEdge = shiftedFrame.horizontalEnd_calculate() - 1
                eastTerminalStart = (
                    transformedEastChipTerminalFrame.horizontalStart
                )
                shiftedGeometryScopesList.append(
                    replace(
                        scope,
                        frame=RoutingZoneRegionFrame(
                            horizontalStart=eastTerminalStart,
                            verticalStart=shiftedFrame.verticalStart,
                            horizontalSpan=shiftedRightEdge
                            - eastTerminalStart
                            + 1,
                            verticalSpan=shiftedFrame.verticalSpan,
                        ),
                    )
                )
            elif scopeSide is BoardSide.WEST:
                shiftedGeometryScopesList.append(
                    replace(
                        scope,
                        frame=RoutingZoneRegionFrame(
                            horizontalStart=frame.horizontalStart,
                            verticalStart=frame.verticalStart,
                            horizontalSpan=(
                                transformedWestChipTerminalFrame.horizontalEnd_calculate()
                                - frame.horizontalStart
                            ),
                            verticalSpan=frame.verticalSpan,
                        ),
                    )
                )
            else:
                shiftedGeometryScopesList.append(scope)

        shiftedTerminalPositionsByChip: TerminalPositionsByChip = {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                substrateGeometry.exactTerminalWorldPositionsByChip.items()
            )
        }
        chipDrawPlacements = substrateGeometry.chipDrawPlacementsByChip
        shiftedChipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = (
            dict(chipDrawPlacements)
        )
        for chipName, chipPlacement in chipDrawPlacements.items():
            terminalFrame = transformedFramesById.get(
                BoardRegionId(
                    family=RegionFamily.CHIP_TERMINAL,
                    side=chipPlacement.side,
                )
            )
            if terminalFrame is None:
                continue
            targetDrawColumn = (
                terminalFrame.horizontalStart + moduleBoundaryPaddingCells
            )
            drawShiftColumns = targetDrawColumn - chipPlacement.drawTopLeft[0]
            if drawShiftColumns == 0:
                continue
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
            chipTerminalPositions = shiftedTerminalPositionsByChip.get(
                chipName
            )
            if chipTerminalPositions is None:
                continue
            shiftedTerminalPositionsByChip[chipName] = {
                terminalName: (
                    worldColumn + drawShiftColumns,
                    worldRow,
                )
                for terminalName, (worldColumn, worldRow) in (
                    chipTerminalPositions.items()
                )
            }

        for i, scope in enumerate(shiftedGeometryScopesList):
            if _scopeSide_get(scope, moduleSidesByName) is not BoardSide.EAST:
                continue
            if scope.frame is None:
                continue
            boundaryFrame = scope.frame
            scopeChipNames = {
                _chipName_build(chipRef) for chipRef in scope.chipRefs
            }
            eastChipPlacements = tuple(
                chipPlacement
                for chipName, chipPlacement in (
                    shiftedChipDrawPlacementsByChip.items()
                )
                if chipName in scopeChipNames
                and chipPlacement.side is BoardSide.EAST
            )
            if not eastChipPlacements:
                continue
            visibleBoundsSeq = tuple(
                _visibleChipDrawBounds_build(
                    drawTopLeft=chipPlacement.drawTopLeft,
                    drawLines=chipPlacement.drawLines,
                )
                for chipPlacement in eastChipPlacements
            )
            visibleBoundsSeq = tuple(
                b for b in visibleBoundsSeq if b is not None
            )
            if not visibleBoundsSeq:
                continue
            rightEdge = (
                max(b[3] for b in visibleBoundsSeq)
                + moduleBoundaryPaddingCells
            )
            shiftedGeometryScopesList[i] = replace(
                scope,
                frame=RoutingZoneRegionFrame(
                    horizontalStart=boundaryFrame.horizontalStart,
                    verticalStart=boundaryFrame.verticalStart,
                    horizontalSpan=(
                        rightEdge - boundaryFrame.horizontalStart + 1
                    ),
                    verticalSpan=boundaryFrame.verticalSpan,
                ),
            )

        # Sync the east chip terminal's right edge to the final east boundary
        # right edge.  The initial expansion at eastChipTerminalId used the
        # substrate boundary right edge; the loop above may have pushed the
        # boundary further right based on actual chip draw extents after
        # repositioning.  Without this sync the terminal zone ends short of
        # the module box.
        syncedEastTerminalFrame: RoutingZoneRegionFrame | None = (
            transformedFramesById.get(eastChipTerminalId)
        )
        if syncedEastTerminalFrame is not None:
            finalEastBoundaryRight: int = max(
                (
                    scope.frame.horizontalEnd_calculate() - 1
                    for scope in shiftedGeometryScopesList
                    if _scopeSide_get(scope, moduleSidesByName)
                    is BoardSide.EAST
                    and scope.frame is not None
                ),
                default=syncedEastTerminalFrame.horizontalEnd_calculate() - 1,
            )
            if (
                finalEastBoundaryRight
                > syncedEastTerminalFrame.horizontalEnd_calculate() - 1
            ):
                transformedFramesById[eastChipTerminalId] = (
                    RoutingZoneRegionFrame(
                        horizontalStart=syncedEastTerminalFrame.horizontalStart,
                        verticalStart=syncedEastTerminalFrame.verticalStart,
                        horizontalSpan=finalEastBoundaryRight
                        - syncedEastTerminalFrame.horizontalStart
                        + 1,
                        verticalSpan=syncedEastTerminalFrame.verticalSpan,
                    )
                )

        transformedFramesById = _wtePlacedTerminalAxisFrames_build(
            regionFramesById=transformedFramesById,
            exactTerminalWorldPositionsByChip=shiftedTerminalPositionsByChip,
        )

        return BoardGeometry(
            regionFramesById=transformedFramesById,
            routingZoneRegionIdsById=substrateGeometry.routingZoneRegionIdsById,
            geometryScopes=tuple(shiftedGeometryScopesList),
            exactTerminalWorldPositionsByChip=shiftedTerminalPositionsByChip,
            chipDrawPlacementsByChip=shiftedChipDrawPlacementsByChip,
        )

    if sense in (BoardSense.NORTH_TO_SOUTH, BoardSense.SOUTH_TO_NORTH):
        northBoundaryFrames = [
            scope.frame
            for scope in geometryScopes
            if _scopeSide_get(scope, moduleSidesByName) == BoardSide.NORTH
            and scope.frame is not None
        ]
        southBoundaryFrames = [
            scope.frame
            for scope in geometryScopes
            if _scopeSide_get(scope, moduleSidesByName) == BoardSide.SOUTH
            and scope.frame is not None
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
        northBoundaryTop = min(f.verticalStart for f in northBoundaryFrames)
        northBoundaryBottom = max(
            f.verticalEnd_calculate() - 1 for f in northBoundaryFrames
        )
        southBoundaryTop = min(f.verticalStart for f in southBoundaryFrames)
        southBoundaryBottom = max(
            f.verticalEnd_calculate() - 1 for f in southBoundaryFrames
        )

        northFanId = BoardRegionId(
            family=RegionFamily.INTRA_FAN, side=BoardSide.NORTH
        )
        southFanId = BoardRegionId(
            family=RegionFamily.INTRA_FAN, side=BoardSide.SOUTH
        )

        northEnvelopeGrowthRows = max(
            0,
            (northBoundary.verticalEnd_calculate() - 1)
            - (northChipTerminalFrame.verticalEnd_calculate() - 1),
        )
        transformedFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = {}
        for regionId, frame in regionFramesById.items():
            if regionId == northChipTerminalId:
                northTop = min(frame.verticalStart, northBoundaryTop)
                northBottom = max(
                    frame.verticalEnd_calculate() - 1, northBoundaryBottom
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=frame.horizontalStart,
                    verticalStart=northTop,
                    horizontalSpan=frame.horizontalSpan,
                    verticalSpan=northBottom - northTop + 1,
                )
                continue

            if regionId == northFanId:
                northTop = min(frame.verticalStart, northBoundaryTop)
                northBottom = max(
                    frame.verticalEnd_calculate() - 1, northBoundaryBottom
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=frame.horizontalStart,
                    verticalStart=northTop,
                    horizontalSpan=frame.horizontalSpan,
                    verticalSpan=northBottom - northTop + 1,
                )
                continue

            shiftedFrame = _frameShiftedVertically_build(
                frame,
                deltaRows=northEnvelopeGrowthRows,
            )
            if regionId == southChipTerminalId:
                southTop = min(shiftedFrame.verticalStart, southBoundaryTop)
                southBottom = max(
                    shiftedFrame.verticalEnd_calculate() - 1,
                    southBoundaryBottom,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=southTop,
                    horizontalSpan=shiftedFrame.horizontalSpan,
                    verticalSpan=southBottom - southTop + 1,
                )
                continue

            if regionId == southFanId:
                southTop = min(shiftedFrame.verticalStart, southBoundaryTop)
                southBottom = max(
                    shiftedFrame.verticalEnd_calculate() - 1,
                    southBoundaryBottom,
                )
                transformedFramesById[regionId] = RoutingZoneRegionFrame(
                    horizontalStart=shiftedFrame.horizontalStart,
                    verticalStart=southTop,
                    horizontalSpan=shiftedFrame.horizontalSpan,
                    verticalSpan=southBottom - southTop + 1,
                )
                continue

            transformedFramesById[regionId] = shiftedFrame

        transformedNorthChipTerminalFrame = transformedFramesById[
            northChipTerminalId
        ]
        transformedSouthChipTerminalFrame = transformedFramesById[
            southChipTerminalId
        ]

        shiftedGeometryScopesList: list[BoardGeometryScope] = []
        for scope in geometryScopes:
            if scope.frame is None:
                shiftedGeometryScopesList.append(scope)
                continue
            frame = scope.frame
            scopeSide = _scopeSide_get(scope, moduleSidesByName)
            if scopeSide is BoardSide.SOUTH:
                shiftedFrame = _frameShiftedVertically_build(
                    frame,
                    deltaRows=northEnvelopeGrowthRows,
                )
                shiftedBottomEdge = shiftedFrame.verticalEnd_calculate() - 1
                southTerminalStart = (
                    transformedSouthChipTerminalFrame.verticalStart
                )
                shiftedGeometryScopesList.append(
                    replace(
                        scope,
                        frame=RoutingZoneRegionFrame(
                            horizontalStart=shiftedFrame.horizontalStart,
                            verticalStart=southTerminalStart,
                            horizontalSpan=shiftedFrame.horizontalSpan,
                            verticalSpan=shiftedBottomEdge
                            - southTerminalStart
                            + 1,
                        ),
                    )
                )
            elif scopeSide is BoardSide.NORTH:
                shiftedGeometryScopesList.append(
                    replace(
                        scope,
                        frame=RoutingZoneRegionFrame(
                            horizontalStart=frame.horizontalStart,
                            verticalStart=frame.verticalStart,
                            horizontalSpan=frame.horizontalSpan,
                            verticalSpan=(
                                transformedNorthChipTerminalFrame.verticalEnd_calculate()
                                - frame.verticalStart
                            ),
                        ),
                    )
                )
            else:
                shiftedGeometryScopesList.append(scope)

        shiftedTerminalPositionsByChip: TerminalPositionsByChip = {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                substrateGeometry.exactTerminalWorldPositionsByChip.items()
            )
        }
        chipDrawPlacements = substrateGeometry.chipDrawPlacementsByChip
        shiftedChipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = (
            dict(chipDrawPlacements)
        )
        for chipName, chipPlacement in chipDrawPlacements.items():
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
            chipTerminalPositions = shiftedTerminalPositionsByChip.get(
                chipName
            )
            if chipTerminalPositions is None:
                continue
            shiftedTerminalPositionsByChip[chipName] = {
                terminalName: (worldColumn, worldRow + northEnvelopeGrowthRows)
                for terminalName, (worldColumn, worldRow) in (
                    chipTerminalPositions.items()
                )
            }

        return BoardGeometry(
            regionFramesById=transformedFramesById,
            routingZoneRegionIdsById=substrateGeometry.routingZoneRegionIdsById,
            geometryScopes=tuple(shiftedGeometryScopesList),
            exactTerminalWorldPositionsByChip=shiftedTerminalPositionsByChip,
            chipDrawPlacementsByChip=shiftedChipDrawPlacementsByChip,
        )

    return substrateGeometry


def _wtePlacedTerminalAxisFrames_build(
    *,
    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame],
    exactTerminalWorldPositionsByChip: TerminalPositionsByChip,
) -> dict[BoardRegionId, RoutingZoneRegionFrame]:
    """Return WTE routing bands re-anchored to the live terminal centroid.

    The legacy placed kernel fixes the WTE latitude axis before chip placement
    policy is applied. Once board doctrine is allowed to reposition chip
    stacks, those imported latitude rows can become visibly stale. The board
    builder must therefore re-anchor the WTE routing axis from the placed
    terminal geometry before realization begins.

    Args:
        regionFramesById: Current board region frames.
        exactTerminalWorldPositionsByChip: Live placed terminal world points.

    Returns:
        A copied frame map whose north/south latitude pair, WTE transition
        regions, and split upper/lower longitude bands are aligned to the live
        terminal-row centroid.
    """

    northLatId = BoardRegionId(
        family=RegionFamily.INTRA_LATITUDE,
        side=BoardSide.NORTH,
    )
    southLatId = BoardRegionId(
        family=RegionFamily.INTRA_LATITUDE,
        side=BoardSide.SOUTH,
    )
    westTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL,
        side=BoardSide.WEST,
    )
    eastTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL,
        side=BoardSide.EAST,
    )

    northLatFrame = regionFramesById.get(northLatId)
    southLatFrame = regionFramesById.get(southLatId)
    westTerminalFrame = regionFramesById.get(westTerminalId)
    eastTerminalFrame = regionFramesById.get(eastTerminalId)
    if (
        northLatFrame is None
        or southLatFrame is None
        or westTerminalFrame is None
        or eastTerminalFrame is None
    ):
        return regionFramesById

    terminalRows = [
        worldRow
        for chipTerminalPositions in exactTerminalWorldPositionsByChip.values()
        for _, worldRow in chipTerminalPositions.values()
    ]
    if not terminalRows:
        return regionFramesById

    terminalTopRow = min(
        westTerminalFrame.verticalStart,
        eastTerminalFrame.verticalStart,
    )
    terminalBottomRow = max(
        westTerminalFrame.verticalEnd_calculate() - 1,
        eastTerminalFrame.verticalEnd_calculate() - 1,
    )

    # Centroid shift: realign lat rows to live terminal centroid.
    currentAxisCentroid = (
        (northLatFrame.verticalStart + (northLatFrame.verticalSpan - 1) / 2)
        + (southLatFrame.verticalStart + (southLatFrame.verticalSpan - 1) / 2)
    ) / 2
    liveTerminalCentroid = sum(terminalRows) / len(terminalRows)
    rawShiftRows = round(liveTerminalCentroid - currentAxisCentroid)
    maxNorthShiftRows = northLatFrame.verticalStart - terminalTopRow
    maxSouthShiftRows = terminalBottomRow - (
        southLatFrame.verticalEnd_calculate() - 1
    )
    shiftRows = max(
        -maxNorthShiftRows,
        min(rawShiftRows, maxSouthShiftRows),
    )

    shiftedFramesById = dict(regionFramesById)
    if shiftRows != 0:
        for regionId in (northLatId, southLatId):
            frame = shiftedFramesById.get(regionId)
            if frame is None:
                continue
            shiftedFramesById[regionId] = _frameShiftedVertically_build(
                frame,
                deltaRows=shiftRows,
            )

    shiftedNorthLatFrame = shiftedFramesById[northLatId]
    shiftedSouthLatFrame = shiftedFramesById[southLatId]

    # Push NORTH/SOUTH dummy chip-terminal and fan frames outside the
    # longitude band territory, stacked: fan adjacent to the band, chip
    # terminal outermost.
    northFanId = BoardRegionId(
        family=RegionFamily.INTRA_FAN, side=BoardSide.NORTH
    )
    northTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL, side=BoardSide.NORTH
    )
    southFanId = BoardRegionId(
        family=RegionFamily.INTRA_FAN, side=BoardSide.SOUTH
    )
    southTerminalId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL, side=BoardSide.SOUTH
    )
    northFanFrame = shiftedFramesById.get(northFanId)
    northTerminalFrame = shiftedFramesById.get(northTerminalId)
    southFanFrame = shiftedFramesById.get(southFanId)
    southTerminalFrame = shiftedFramesById.get(southTerminalId)
    if northFanFrame is not None:
        northFanStart = terminalTopRow - northFanFrame.verticalSpan
        shiftedFramesById[northFanId] = RoutingZoneRegionFrame(
            horizontalStart=northFanFrame.horizontalStart,
            verticalStart=northFanStart,
            horizontalSpan=northFanFrame.horizontalSpan,
            verticalSpan=northFanFrame.verticalSpan,
        )
        if northTerminalFrame is not None:
            shiftedFramesById[northTerminalId] = RoutingZoneRegionFrame(
                horizontalStart=northTerminalFrame.horizontalStart,
                verticalStart=northFanStart - northTerminalFrame.verticalSpan,
                horizontalSpan=northTerminalFrame.horizontalSpan,
                verticalSpan=northTerminalFrame.verticalSpan,
            )
    elif northTerminalFrame is not None:
        shiftedFramesById[northTerminalId] = RoutingZoneRegionFrame(
            horizontalStart=northTerminalFrame.horizontalStart,
            verticalStart=terminalTopRow - northTerminalFrame.verticalSpan,
            horizontalSpan=northTerminalFrame.horizontalSpan,
            verticalSpan=northTerminalFrame.verticalSpan,
        )
    if southFanFrame is not None:
        southFanStart = terminalBottomRow + 1
        shiftedFramesById[southFanId] = RoutingZoneRegionFrame(
            horizontalStart=southFanFrame.horizontalStart,
            verticalStart=southFanStart,
            horizontalSpan=southFanFrame.horizontalSpan,
            verticalSpan=southFanFrame.verticalSpan,
        )
        if southTerminalFrame is not None:
            shiftedFramesById[southTerminalId] = RoutingZoneRegionFrame(
                horizontalStart=southTerminalFrame.horizontalStart,
                verticalStart=southFanStart + southFanFrame.verticalSpan,
                horizontalSpan=southTerminalFrame.horizontalSpan,
                verticalSpan=southTerminalFrame.verticalSpan,
            )
    elif southTerminalFrame is not None:
        shiftedFramesById[southTerminalId] = RoutingZoneRegionFrame(
            horizontalStart=southTerminalFrame.horizontalStart,
            verticalStart=terminalBottomRow + 1,
            horizontalSpan=southTerminalFrame.horizontalSpan,
            verticalSpan=southTerminalFrame.verticalSpan,
        )

    # Resize longitude bands to the full terminal extents.
    for side in (BoardSide.WEST, BoardSide.EAST):
        upperId = BoardRegionId(
            family=RegionFamily.INTRA_LONGITUDE,
            side=side,
            band=RegionBand.UPPER,
        )
        lowerId = BoardRegionId(
            family=RegionFamily.INTRA_LONGITUDE,
            side=side,
            band=RegionBand.LOWER,
        )
        upperFrame = shiftedFramesById.get(upperId)
        lowerFrame = shiftedFramesById.get(lowerId)
        templateFrame = upperFrame or lowerFrame
        if templateFrame is None:
            continue

        upperStart = terminalTopRow
        upperEnd = shiftedNorthLatFrame.verticalEnd_calculate() - 1
        if upperEnd >= upperStart:
            shiftedFramesById[upperId] = RoutingZoneRegionFrame(
                horizontalStart=templateFrame.horizontalStart,
                verticalStart=upperStart,
                horizontalSpan=templateFrame.horizontalSpan,
                verticalSpan=upperEnd - upperStart + 1,
            )
        elif upperId in shiftedFramesById:
            del shiftedFramesById[upperId]

        lowerStart = shiftedSouthLatFrame.verticalStart
        lowerEnd = terminalBottomRow
        if lowerEnd >= lowerStart:
            shiftedFramesById[lowerId] = RoutingZoneRegionFrame(
                horizontalStart=templateFrame.horizontalStart,
                verticalStart=lowerStart,
                horizontalSpan=templateFrame.horizontalSpan,
                verticalSpan=lowerEnd - lowerStart + 1,
            )
        elif lowerId in shiftedFramesById:
            del shiftedFramesById[lowerId]

    return shiftedFramesById


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


def _boardGeometriesNormalizedToPositiveWorld_build(
    *,
    substrateGeometry: BoardGeometry,
    effectiveGeometry: BoardGeometry,
) -> tuple[BoardGeometry, BoardGeometry]:
    """Return both board geometries shifted into non-negative world space.

    The board builder may legitimately create negative coordinates while
    growing north/west chip-terminal or outer-ring geometry. The final built
    board, however, must live in positive world space. This normalization uses
    the existing georule translation engine (`sfN.Z`) so every zone, boundary,
    chip draw, and terminal attach point moves through one geometry path.
    """

    minimumColumn = min(
        _minimumGeometryColumn_calculate(substrateGeometry),
        _minimumGeometryColumn_calculate(effectiveGeometry),
    )
    minimumRow = min(
        _minimumGeometryRow_calculate(substrateGeometry),
        _minimumGeometryRow_calculate(effectiveGeometry),
    )
    deltaColumns = max(0, 1 - minimumColumn)
    deltaRows = max(0, 1 - minimumRow)
    if deltaColumns == 0 and deltaRows == 0:
        return substrateGeometry, effectiveGeometry
    normalizedSubstrate = rules_apply(
        sfN.Z,
        GeoOp.DISPLACE,
        deltaColumns,
        deltaRows,
        substrateGeometry,
    )
    normalizedEffective = rules_apply(
        sfN.Z,
        GeoOp.DISPLACE,
        deltaColumns,
        deltaRows,
        effectiveGeometry,
    )
    return normalizedSubstrate, normalizedEffective


def _minimumGeometryColumn_calculate(geometry: BoardGeometry) -> int:
    """Return the minimum occupied world column in one board geometry."""

    minimums: list[int] = [
        frame.horizontalStart for frame in geometry.regionFramesById.values()
    ]
    minimums.extend(
        scope.frame.horizontalStart
        for scope in geometry.geometryScopes
        if scope.frame is not None
    )
    minimums.extend(
        placement.drawTopLeft[0]
        for placement in geometry.chipDrawPlacementsByChip.values()
    )
    minimums.extend(
        worldColumn
        for chipTerminals in (
            geometry.exactTerminalWorldPositionsByChip.values()
        )
        for worldColumn, _worldRow in chipTerminals.values()
    )
    return min(minimums, default=1)


def _minimumGeometryRow_calculate(geometry: BoardGeometry) -> int:
    """Return the minimum occupied world row in one board geometry."""

    minimums: list[int] = [
        frame.verticalStart for frame in geometry.regionFramesById.values()
    ]
    minimums.extend(
        scope.frame.verticalStart
        for scope in geometry.geometryScopes
        if scope.frame is not None
    )
    minimums.extend(
        placement.drawTopLeft[1]
        for placement in geometry.chipDrawPlacementsByChip.values()
    )
    minimums.extend(
        worldRow
        for chipTerminals in (
            geometry.exactTerminalWorldPositionsByChip.values()
        )
        for _worldColumn, worldRow in chipTerminals.values()
    )
    return min(minimums, default=1)


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


def _scopeSide_get(
    scope: BoardGeometryScope,
    moduleSidesByName: dict[str, BoardSide],
) -> BoardSide | None:
    """Return the single board side for a depth-layer scope.

    Collects all distinct sides found for the scope's chip module names. When
    all chips agree on one side, returns that side. Mixed or unknown → None.

    Args:
        scope: Geometry scope whose chips define the side.
        moduleSidesByName: Module-name → board-side map from the routing zone.

    Returns:
        The unique ``BoardSide`` when all chips share one side, else ``None``.
    """

    sides = {
        moduleSidesByName[chipRef.chipId.moduleName]
        for chipRef in scope.chipRefs
        if chipRef.chipId.moduleName in moduleSidesByName
    }
    if len(sides) == 1:
        return next(iter(sides))
    return None


def _chipDrawPlacementsByChip_build(
    *,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    chipLocalGeometrySet: ChipLocalGeometrySet,
    chipPlacementPolicy: BoardChipPlacementPolicy,
    moduleBoundaryPaddingCells: int,
) -> dict[str, BoardChipDrawPlacement]:
    """Build board-owned chip draw placements from the placed zone."""

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
            terminalRegionSpan=(
                terminalRegionResult.value.routingZoneRegionFrame.verticalSpan
                if routingZone.routingZoneSense
                is RoutingZoneSense.WEST_TO_EAST
                or regionSide
                in {
                    RoutingZoneRegionSide.WEST,
                    RoutingZoneRegionSide.EAST,
                }
                else (
                    terminalRegionResult.value.routingZoneRegionFrame.horizontalSpan
                )
            ),
            chipPlacementPolicy=chipPlacementPolicy,
            interModulePadding=2 * moduleBoundaryPaddingCells + 1,
        )
        if not result_isOkCheck(stackOffsetResult):
            continue
        chipResult = circuitDocument.circuitChipSet.chipResult_get(
            chipPlacement.chipRef.chipId
        )
        if not result_isOkCheck(chipResult):
            continue
        chipDrawGeometry = chipDrawGeometry_build(chipResult.value)
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
            drawLines=chipDrawGeometry.drawLines,
            interiorHorizontalPadding=moduleBoundaryPaddingCells,
        )
        chipName = _chipName_build(chipPlacement.chipRef)
        chipDrawPlacementsByChip[chipName] = BoardChipDrawPlacement(
            chipName=chipName,
            moduleName=chipPlacement.chipRef.chipId.moduleName,
            side=BoardSide(regionSide.value),
            drawTopLeft=(
                placementGeometry.drawWorldColumn,
                placementGeometry.drawWorldRow,
            ),
            drawLines=chipDrawGeometry.drawLines,
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
    """Return the minimum cross-bar span implied by substrate geometry."""

    regionFramesByName = {
        regionId.label_build(): frame
        for regionId, frame in regionFramesById.items()
    }
    if sense in (BoardSense.WEST_TO_EAST, BoardSense.EAST_TO_WEST):
        northFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ni))
        southFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Si))
        candidates = [
            frame.horizontalSpan
            for frame in (northFrame, southFrame)
            if frame is not None
        ]
    else:
        westFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Wi))
        eastFrame = regionFramesByName.get(_requiredRegionKey_get(sfN.Ei))
        candidates = [
            frame.verticalSpan
            for frame in (westFrame, eastFrame)
            if frame is not None
        ]
    if not candidates:
        return 0
    return min(candidates)


def _moduleBoundaryClampedToTerminalZones_build(
    geometry: BoardGeometry,
    *,
    moduleBoundaryPaddingCells: int,
) -> BoardGeometry:
    """Return geometry with boundaries clamped to owning chip-terminal zones.

    Doctrine says the effective module boundary owns chip-terminal space and
    nothing beyond it. Fan and channel geometry must remain outside the module
    box. That means module boundaries should be derived from the chip-terminal
    zones, not from routing-clearance against surrounding geometry.
    """

    currentScopes = geometry.geometryScopes
    if not currentScopes:
        return geometry

    if not geometry.chipDrawPlacementsByChip:
        return geometry

    visibleBoundsByModuleName: dict[str, tuple[int, int, int, int]] = {}
    for chipPlacement in geometry.chipDrawPlacementsByChip.values():
        visibleBounds = _visibleChipDrawBounds_build(
            drawTopLeft=chipPlacement.drawTopLeft,
            drawLines=chipPlacement.drawLines,
        )
        if visibleBounds is None:
            continue
        moduleName = chipPlacement.moduleName
        existingBounds = visibleBoundsByModuleName.get(moduleName)
        if existingBounds is None:
            visibleBoundsByModuleName[moduleName] = visibleBounds
            continue
        visibleBoundsByModuleName[moduleName] = (
            min(existingBounds[0], visibleBounds[0]),
            min(existingBounds[1], visibleBounds[1]),
            max(existingBounds[2], visibleBounds[2]),
            max(existingBounds[3], visibleBounds[3]),
        )

    sidesByModuleName: dict[str, set[BoardSide]] = {}
    for chipPlacement in geometry.chipDrawPlacementsByChip.values():
        sidesByModuleName.setdefault(
            chipPlacement.moduleName, set()
        ).add(chipPlacement.side)

    pad = max(0, moduleBoundaryPaddingCells)
    updatedScopesList: list[BoardGeometryScope] = []
    changed = False
    for scope in currentScopes:
        if scope.frame is None:
            updatedScopesList.append(scope)
            continue
        frame = scope.frame
        scopeModuleNames = {
            chipRef.chipId.moduleName for chipRef in scope.chipRefs
        }
        moduleSides: set[BoardSide] = set()
        for mn in scopeModuleNames:
            sides = sidesByModuleName.get(mn)
            if sides:
                moduleSides.update(sides)
        scopeVisibleBounds: tuple[int, int, int, int] | None = None
        for mn in scopeModuleNames:
            mb = visibleBoundsByModuleName.get(mn)
            if mb is None:
                continue
            if scopeVisibleBounds is None:
                scopeVisibleBounds = mb
            else:
                scopeVisibleBounds = (
                    min(scopeVisibleBounds[0], mb[0]),
                    min(scopeVisibleBounds[1], mb[1]),
                    max(scopeVisibleBounds[2], mb[2]),
                    max(scopeVisibleBounds[3], mb[3]),
                )
        if not moduleSides or scopeVisibleBounds is None:
            updatedScopesList.append(scope)
            continue
        terminalFrames = tuple(
            terminalFrame
            for moduleSide in moduleSides
            for terminalFrame in (
                geometry.regionFramesById.get(
                    BoardRegionId(
                        family=RegionFamily.CHIP_TERMINAL,
                        side=moduleSide,
                    )
                ),
            )
            if terminalFrame is not None
        )
        if not terminalFrames:
            updatedScopesList.append(scope)
            continue

        visibleTop, _visibleLeft, visibleBottom, _visibleRight = (
            scopeVisibleBounds
        )
        terminalTop = min(
            terminalFrame.verticalStart for terminalFrame in terminalFrames
        )
        terminalBottom = max(
            terminalFrame.verticalEnd_calculate() - 1
            for terminalFrame in terminalFrames
        )
        nextTop = max(terminalTop, visibleTop - pad)
        nextBottom = min(terminalBottom, visibleBottom + pad)
        nextLeft = min(
            terminalFrame.horizontalStart for terminalFrame in terminalFrames
        )
        nextRight = max(
            terminalFrame.horizontalEnd_calculate() - 1
            for terminalFrame in terminalFrames
        )
        minimumInnerWidth = len("═ " + scope.label + " ")
        if nextRight - nextLeft - 1 < minimumInnerWidth:
            updatedScopesList.append(scope)
            continue
        clampedFrame = RoutingZoneRegionFrame(
            horizontalStart=nextLeft,
            verticalStart=nextTop,
            horizontalSpan=nextRight - nextLeft + 1,
            verticalSpan=nextBottom - nextTop + 1,
        )
        updatedScopesList.append(replace(scope, frame=clampedFrame))
        changed = changed or clampedFrame != frame

    if not changed:
        return geometry

    return BoardGeometry(
        geometryZonesById=geometry.geometryZonesById,
        geometryScopes=tuple(updatedScopesList),
    )


def boardGeometryBoundaryNormalized_build(
    geometry: BoardGeometry,
    *,
    moduleBoundaryPaddingCells: int,
) -> BoardGeometry:
    """Return geometry with module boundaries re-fit to terminal doctrine.

    This is the normalization pass needed after direct geometry mutations such
    as geo-rule displacements. Those mutations move owned zones, chip draws,
    and terminals, but they do not automatically recompute the effective
    module boundaries from the owning chip-terminal zones.

    Args:
        geometry: Mutated board geometry.
        moduleBoundaryPaddingCells: Configured module-box padding.

    Returns:
        Geometry with boundary frames clamped to the current chip-terminal
        zones while still containing the visible chip draw.
    """

    return _moduleBoundaryClampedToTerminalZones_build(
        geometry,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
    )


def _frameOverlap_check(
    leftFrame: RoutingZoneRegionFrame,
    rightFrame: RoutingZoneRegionFrame,
) -> bool:
    """Return whether two inclusive region frames overlap.

    Args:
        leftFrame: First frame to compare.
        rightFrame: Second frame to compare.

    Returns:
        `True` when the frames overlap in world space, otherwise `False`.
    """

    leftRight = leftFrame.horizontalEnd_calculate() - 1
    rightRight = rightFrame.horizontalEnd_calculate() - 1
    leftBottom = leftFrame.verticalEnd_calculate() - 1
    rightBottom = rightFrame.verticalEnd_calculate() - 1
    return not (
        leftRight < rightFrame.horizontalStart
        or rightRight < leftFrame.horizontalStart
        or leftBottom < rightFrame.verticalStart
        or rightBottom < leftFrame.verticalStart
    )


def _geometryScopes_build(
    *,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    callingStack: CallingStack,
    effectiveBoundaryMode: EffectiveBoundaryMode,
    moduleBoundaryPaddingCells: int,
    chipPlacementPolicy: BoardChipPlacementPolicy,
) -> tuple[BoardGeometryScope, ...]:
    """Build depth-layer geometry scopes for one board.

    Groups placed chips by call-depth index from the calling stack. Each depth
    band becomes one ``BoardGeometryScope`` with label ``layer/N``, chip
    membership, and a bounding frame derived from visible chip draw extents.
    """

    if effectiveBoundaryMode is EffectiveBoundaryMode.CONTENT_ONLY:
        return ()

    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(chipLocalGeometrySetResult):
        return ()
    chipLocalGeometrySet = chipLocalGeometrySetResult.value
    moduleSidesByName = _moduleSidesByName_build(routingZone)
    depthByChipRef = callingStack.depthByChipRef

    boundsByDepthMutable: dict[int, tuple[int, int, int, int]] = {}
    chipRefsByDepthMutable: dict[int, list[ChipRef]] = {}
    sideByDepthMutable: dict[int, BoardSide] = {}

    for chipPlacement in routingZone.chipPlacementSet.placements:
        chipRef = chipPlacement.chipRef
        depthIndex = depthByChipRef.get(chipRef)
        if depthIndex is None:
            continue
        geometryResult = (
            chipLocalGeometrySet.geometryForChipResult_get(chipRef)
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
            terminalRegionSpan=(
                terminalRegionResult.value.routingZoneRegionFrame.verticalSpan
                if routingZone.routingZoneSense
                is RoutingZoneSense.WEST_TO_EAST
                or regionSide
                in {
                    RoutingZoneRegionSide.WEST,
                    RoutingZoneRegionSide.EAST,
                }
                else (
                    terminalRegionResult.value.routingZoneRegionFrame.horizontalSpan
                )
            ),
            chipPlacementPolicy=chipPlacementPolicy,
            interModulePadding=2 * moduleBoundaryPaddingCells + 1,
        )
        if not result_isOkCheck(stackOffsetResult):
            continue
        chipResult = circuitDocument.circuitChipSet.chipResult_get(
            chipRef.chipId
        )
        if not result_isOkCheck(chipResult):
            continue
        chipDrawGeometry = chipDrawGeometry_build(chipResult.value)
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
            drawLines=chipDrawGeometry.drawLines,
            interiorHorizontalPadding=moduleBoundaryPaddingCells,
        )
        visibleBounds = _visibleChipDrawBoundsFromGeometry_build(
            drawTopLeft=(
                placementGeometry.drawWorldColumn,
                placementGeometry.drawWorldRow,
            ),
            chipDrawGeometry=chipDrawGeometry,
        )
        if visibleBounds is None:
            continue
        chipRefsByDepthMutable.setdefault(depthIndex, []).append(chipRef)
        moduleName = chipRef.chipId.moduleName
        sideByDepthMutable.setdefault(
            depthIndex,
            moduleSidesByName.get(moduleName, BoardSide.WEST),
        )
        depthSide = sideByDepthMutable[depthIndex]
        pad = moduleBoundaryPaddingCells
        drawRow0, drawCol0, drawRow1, drawCol1 = visibleBounds
        topPad = 0 if depthSide is BoardSide.SOUTH else pad
        bottomPad = 0 if depthSide is BoardSide.NORTH else pad
        chipBounds = (
            drawRow0 - topPad,
            drawCol0 - pad,
            drawRow1 + bottomPad,
            drawCol1 + pad,
        )
        existingBounds = boundsByDepthMutable.get(depthIndex)
        if existingBounds is None:
            boundsByDepthMutable[depthIndex] = chipBounds
        else:
            boundsByDepthMutable[depthIndex] = (
                min(existingBounds[0], chipBounds[0]),
                min(existingBounds[1], chipBounds[1]),
                max(existingBounds[2], chipBounds[2]),
                max(existingBounds[3], chipBounds[3]),
            )

    scopes: list[BoardGeometryScope] = []
    for depthIndex in sorted(boundsByDepthMutable):
        row0, col0, row1, col1 = boundsByDepthMutable[depthIndex]
        depthSide = sideByDepthMutable.get(depthIndex)
        scopeId = f"layer/{depthIndex}"
        label = scopeId
        innerWidth = col1 - col0 - 1
        minimumInnerWidth = len("═ " + label + " ")
        if innerWidth < minimumInnerWidth:
            if depthSide is BoardSide.WEST:
                col0 = col1 - 1 - minimumInnerWidth
            else:
                col1 = col0 + 1 + minimumInnerWidth
        frame = RoutingZoneRegionFrame(
            horizontalStart=col0,
            verticalStart=row0,
            horizontalSpan=col1 - col0 + 1,
            verticalSpan=row1 - row0 + 1,
        )
        chipRefs = tuple(chipRefsByDepthMutable.get(depthIndex, []))
        scopes.append(
            BoardGeometryScope(
                scopeId=scopeId,
                kind=BoardGeometryScopeKind.DEPTH_LAYER,
                label=label,
                chipRefs=chipRefs,
                drawable=True,
                frame=frame,
            )
        )
    return tuple(scopes)


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
        nonSpaceIndices = [
            index for index, character in enumerate(line) if character != " "
        ]
        if not nonSpaceIndices:
            continue
        rowIndex = worldRow0 + rowOffset
        topRow = rowIndex if topRow is None else min(topRow, rowIndex)
        bottomRow = rowIndex if bottomRow is None else max(bottomRow, rowIndex)
        lineLeft = worldCol0 + min(nonSpaceIndices)
        lineRight = worldCol0 + max(nonSpaceIndices)
        leftCol = lineLeft if leftCol is None else min(leftCol, lineLeft)
        rightCol = lineRight if rightCol is None else max(rightCol, lineRight)

    if (
        topRow is None
        or leftCol is None
        or bottomRow is None
        or rightCol is None
    ):
        return None
    return (topRow, leftCol, bottomRow, rightCol)


def _visibleChipDrawBoundsFromGeometry_build(
    *,
    drawTopLeft: tuple[int, int],
    chipDrawGeometry,
) -> tuple[int, int, int, int] | None:
    """Return visible chip bounds from semantic draw geometry."""

    worldCol0, worldRow0 = drawTopLeft
    if chipDrawGeometry.lineCount <= 0 or chipDrawGeometry.lineWidth <= 0:
        return None
    return (
        worldRow0 + chipDrawGeometry.visibleTopLineOffset,
        worldCol0 + chipDrawGeometry.visibleLeftColumnOffset,
        worldRow0 + chipDrawGeometry.visibleBottomLineOffset,
        worldCol0 + chipDrawGeometry.visibleRightColumnOffset,
    )
