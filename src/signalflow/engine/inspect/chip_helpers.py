"""Chip and zone helper builders for debug surfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

from signalflow.board import BoardChip
from signalflow.board.types import ChipTerminalPositions
from signalflow.models import (
    ChipDrawGeometry,
    ChipId,
    ChipPlacement,
    ChipTerminalSide,
    Result,
    RoutingZone,
    RoutingZoneId,
    chipDrawGeometry_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneRegionByIdResult_get,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.routing import (
    chipAttachPointSetResult_buildFromPlacedZone,
    chipLocalGeometrySetResult_buildFromChips,
)
from signalflow.routing.geometry import (
    chipCanvasPlacementGeometry_build,
    chipLocalGeometryResult_build,
)

from .context import ChipWorldFrame, SignalFlowContext
from .geometry import _chipStackOffsetOrNone_build, _textBlockSize_build
from .kernel_runtime import _chipInternalBoardKernelRuntime_build

if TYPE_CHECKING:
    from .surfaces import ZoneHandle


def _chipSummaryLines_build(
    *, debugContext: SignalFlowContext, chipId: ChipId, chip
) -> list[str]:
    placementResult = debugContext.placementForChipResult_get(chipId)
    zoneResult = debugContext.zoneOwningChipResult_get(chipId)
    chipInternalRoutes = debugContext.chipRoutesForChip_get(chipId)
    zoneLocalRoutes = debugContext.zoneLocalRoutesForChip_get(chipId)
    gridRoutes = debugContext.gridRoutesForChip_get(chipId)
    terminalCounts = debugContext.terminalCountsForChip_build(chipId)
    locations = debugContext.locationRecordsForChip_build(chipId)
    drawingLines = _chipDrawingLines_build(
        debugContext=debugContext, chipId=chipId
    )
    drawingWidth, drawingHeight = _textBlockSize_build(drawingLines)
    lines = [
        f"chip {_chipTitleText_build(chipId)}",
        f"  title: {_chipTitleText_build(chipId)}",
        f"  size: {drawingWidth}x{drawingHeight}",
        (
            "  terminals: "
            f"N={terminalCounts.get('north', 0)} "
            f"S={terminalCounts.get('south', 0)} "
            f"E={terminalCounts.get('east', 0)} "
            f"W={terminalCounts.get('west', 0)}"
        ),
        f"  input ports: {len(chip.inputPortDeclarationSet.portDeclarations)}",
        (
            "  output ports: "
            f"{len(chip.outputPortDeclarationSet.portDeclarations)}"
        ),
        (
            "  internal directives: "
            f"{len(chip.internalWiringDirectiveSet.directives)}"
        ),
        f"  internal solved routes: {len(chipInternalRoutes)}",
        f"  zone-local routes: {len(zoneLocalRoutes)}",
        f"  grid routes: {len(gridRoutes)}",
    ]
    lines.extend(
        _chipPlacementSummaryLines_build(
            placementResult=placementResult,
            zoneResult=zoneResult,
            locations=locations,
        )
    )
    lines.append("  draw:")
    lines.extend(f"    {drawingLine}" for drawingLine in drawingLines)
    return lines


def _chipPlacementSummaryLines_build(
    *,
    placementResult: Result[ChipPlacement],
    zoneResult: Result[RoutingZone],
    locations: tuple[dict[str, object], ...],
) -> list[str]:
    lines: list[str] = []
    if result_isOkCheck(zoneResult):
        lines.append(f"  zone: {zoneResult.value.routingZoneId.id}")
    if result_isOkCheck(placementResult):
        regionId = placementResult.value.chipTerminalRegionId
        regionSide = (
            regionId.routingZoneRegionSide.value
            if regionId is not None
            and regionId.routingZoneRegionSide is not None
            else "unknown"
        )
        lines.append(
            "  placement: "
            f"{regionSide} order={placementResult.value.orderIndex}"
        )
    if locations:
        locationRecord = locations[0]
        lines.append(
            "  location: "
            f"zone={locationRecord['zone']} "
            f"side={locationRecord['terminalSide']} "
            f"order={locationRecord['orderIndex']} "
            f"point={locationRecord['worldPoint']}"
        )
    return lines


def _chipSummaryText_build(
    debugContext: SignalFlowContext,
    chipId: ChipId,
) -> str:
    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        return (
            f"chip {chipId.moduleName}:{chipId.functionName}"
            "\n  status: missing"
        )
    return "\n".join(
        _chipSummaryLines_build(
            debugContext=debugContext, chipId=chipId, chip=chipResult.value
        )
    )


def _chipTitleText_build(chipId: ChipId) -> str:
    return f"{chipId.moduleName}:{chipId.functionName}"


def _chipTitleParts_build(chipTitle: str) -> tuple[str, str]:
    if chipTitle.count(":") != 1:
        raise ValueError(
            "Invalid chip title "
            f"{chipTitle!r}. Use 'moduleName:functionName', for example "
            "'App.ts:main()'. Run chips.names_get() to list valid titles."
        )
    moduleName, functionName = chipTitle.split(":", 1)
    if not moduleName or not functionName:
        raise ValueError(
            "Invalid chip title "
            f"{chipTitle!r}. Use 'moduleName:functionName', for example "
            "'App.ts:main()'. Run chips.names_get() to list valid titles."
        )
    return (moduleName, functionName)


def _chipHandle_build(
    debugContext: SignalFlowContext, chipId: ChipId
) -> BoardChip:
    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        raise KeyError(
            "Unknown chip "
            f"{_chipTitleText_build(chipId)!r}. "
            "Run chips.names_get() to list valid titles."
        )
    return BoardChip(
        chipId=chipId,
        rawProvider=lambda: debugContext.chipResult_get(chipId),
        titleProvider=lambda: _chipTitleText_build(chipId),
        geometryProvider=lambda: _chipGeometry_build(
            debugContext=debugContext, chipId=chipId
        ),
        sizeProvider=lambda: _textBlockSize_build(
            _chipGeometry_build(
                debugContext=debugContext, chipId=chipId
            ).drawLines
        ),
        terminalsProvider=lambda: debugContext.terminalCountsForChip_build(
            chipId
        ),
        localTerminalPositionsProvider=lambda wall: (
            _chipTerminalLocalPositions_build(
                debugContext=debugContext,
                chipId=chipId,
                wall=wall,
            )
        ),
        worldTerminalPositionsProvider=lambda wall: (
            _chipTerminalWorldPositions_build(
                debugContext=debugContext,
                chipId=chipId,
                wall=wall,
            )
        ),
        placementProvider=lambda: debugContext.placementForChipResult_get(
            chipId
        ),
        locationProvider=lambda: (
            debugContext.locationRecordsForChip_build(chipId)[0]
            if debugContext.locationRecordsForChip_build(chipId)
            else None
        ),
        locationsProvider=lambda: debugContext.locationRecordsForChip_build(
            chipId
        ),
        routesProvider=lambda: debugContext.chipRoutesForChip_get(chipId),
        internalBoardProvider=lambda: _chipInternalBoardKernelRuntime_build(
            debugContext=debugContext,
            chipId=chipId,
        ),
        worldFrameProvider=lambda: _chipWorldFrameOrNone_build(
            debugContext=debugContext, chipId=chipId
        ),
        childrenProvider=lambda: tuple(
            _chipHandle_build(
                debugContext=debugContext,
                chipId=circuitCall.destinationChipRef.chipId,
            )
            for circuitCall in (
                debugContext.circuitDocument.circuitCallSet.outgoingCallsForChip_get(
                    chipId
                )
            )
        ),
        schematicProvider=lambda: "\n".join(
            _chipGeometry_build(
                debugContext=debugContext, chipId=chipId
            ).drawLines
        ),
        summaryProvider=lambda: _chipSummaryText_build(
            debugContext=debugContext, chipId=chipId
        ),
    )


def _zoneHandle_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
) -> ZoneHandle:
    from .surfaces import ZoneHandle as _ZoneHandle

    zoneResult = debugContext.stagedZoneResult_get(routingZoneId)
    if not result_isOkCheck(zoneResult):
        raise KeyError(f"Unknown zone {routingZoneId.id!r}")
    return _ZoneHandle(debugContext=debugContext, routingZoneId=routingZoneId)


def _chipGeometry_build(
    debugContext: SignalFlowContext, chipId: ChipId
) -> ChipDrawGeometry:
    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        return ChipDrawGeometry(
            drawLines=("<missing chip>",),
            lineCount=1,
            lineWidth=len("<missing chip>"),
            boxTopLineOffset=0,
            boxBottomLineOffset=0,
            boxLeftColumnOffset=0,
            boxRightColumnOffset=len("<missing chip>") - 1,
            visibleTopLineOffset=0,
            visibleBottomLineOffset=0,
            visibleLeftColumnOffset=0,
            visibleRightColumnOffset=len("<missing chip>") - 1,
        )
    return chipDrawGeometry_build(chipResult.value)


def _chipDrawingLines_build(
    debugContext: SignalFlowContext, chipId: ChipId
) -> tuple[str, ...]:
    return _chipGeometry_build(
        debugContext=debugContext, chipId=chipId
    ).drawLines


def _chipWorldFrameOrNone_build(
    debugContext: SignalFlowContext,
    chipId: ChipId,
) -> ChipWorldFrame | None:
    chipResult = debugContext.chipResult_get(chipId)
    placementResult = debugContext.placementForChipResult_get(chipId)
    zoneResult = debugContext.zoneOwningChipResult_get(chipId)
    if not (
        result_isOkCheck(chipResult)
        and result_isOkCheck(placementResult)
        and result_isOkCheck(zoneResult)
    ):
        return None
    geometryResult = chipLocalGeometryResult_build(chipResult.value)
    if not result_isOkCheck(geometryResult):
        return None
    terminalRegionResult = routingZoneRegionByIdResult_get(
        zoneResult.value,
        placementResult.value.chipTerminalRegionId,
    )
    if not result_isOkCheck(terminalRegionResult):
        return None
    regionSide = (
        placementResult.value.chipTerminalRegionId.routingZoneRegionSide
    )
    if regionSide is None:
        return None
    placementGeometry = chipCanvasPlacementGeometry_build(
        chipLocalGeometry=geometryResult.value,
        routingZoneSense=zoneResult.value.routingZoneSense,
        regionSide=regionSide,
        terminalRegionVerticalStart=terminalRegionResult.value.routingZoneRegionFrame.verticalStart,
        terminalRegionHorizontalStart=terminalRegionResult.value.routingZoneRegionFrame.horizontalStart,
        stackOffset=_chipStackOffsetOrNone_build(
            debugContext=debugContext,
            zone=zoneResult.value,
            chipPlacement=placementResult.value,
        )
        or 0,
    )
    topLeft = (
        placementGeometry.drawWorldColumn,
        placementGeometry.drawWorldRow,
    )
    bottomRight = (
        placementGeometry.drawWorldColumn + geometryResult.value.lineWidth - 1,
        placementGeometry.drawWorldRow + geometryResult.value.lineCount - 1,
    )
    return ChipWorldFrame(
        topLeft=topLeft,
        bottomRight=bottomRight,
        widthColumns=geometryResult.value.lineWidth,
        heightRows=geometryResult.value.lineCount,
    )


def _chipTerminalSideResult_build(wall: str) -> Result[ChipTerminalSide]:
    wallNormalized = wall.strip().lower()
    wallToSide = {
        "north": ChipTerminalSide.NORTH,
        "south": ChipTerminalSide.SOUTH,
        "east": ChipTerminalSide.EAST,
        "west": ChipTerminalSide.WEST,
    }
    terminalSide = wallToSide.get(wallNormalized)
    if terminalSide is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="debug.chip.wall.invalid",
            message="Unknown chip wall requested for terminal positions",
            context=(wall,),
        )
        return resultErr_build()
    return resultOk_build(terminalSide)


def _chipTerminalLocalPositions_build(
    debugContext: SignalFlowContext,
    chipId: ChipId,
    wall: str,
) -> ChipTerminalPositions:
    terminalSideResult = _chipTerminalSideResult_build(wall)
    chipResult = debugContext.chipResult_get(chipId)
    if not (
        result_isOkCheck(terminalSideResult) and result_isOkCheck(chipResult)
    ):
        return {}
    geometryResult = chipLocalGeometryResult_build(chipResult.value)
    if not result_isOkCheck(geometryResult):
        return {}
    terminalSide = terminalSideResult.value
    geometry = geometryResult.value
    if terminalSide is ChipTerminalSide.WEST:
        terminalColumnIndex = geometry.boxLeftColumnOffset
    elif terminalSide is ChipTerminalSide.EAST:
        terminalColumnIndex = geometry.boxRightColumnOffset
    else:
        return {}
    terminalPositions: ChipTerminalPositions = {}
    for terminalOffset in geometry.terminalLineOffsets:
        if terminalOffset.chipTerminalRef.terminalSide is not terminalSide:
            continue
        terminalPositions[terminalOffset.terminalName] = (
            terminalColumnIndex,
            terminalOffset.lineOffset,
        )
    return terminalPositions


def _chipTerminalWorldPositions_build(
    debugContext: SignalFlowContext,
    chipId: ChipId,
    wall: str,
) -> ChipTerminalPositions:
    terminalSideResult = _chipTerminalSideResult_build(wall)
    zoneResult = debugContext.zoneOwningChipResult_get(chipId)
    chipResult = debugContext.chipResult_get(chipId)
    if not (
        result_isOkCheck(terminalSideResult)
        and result_isOkCheck(zoneResult)
        and result_isOkCheck(chipResult)
    ):
        return {}
    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        debugContext.circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(chipLocalGeometrySetResult):
        return {}
    attachPointSetResult = chipAttachPointSetResult_buildFromPlacedZone(
        zoneResult.value,
        chipLocalGeometrySetResult.value,
        debugContext.circuitDocument,
    )
    if not result_isOkCheck(attachPointSetResult):
        return {}
    chipRef = chipResult.value.chipRef_build()
    terminalSide = terminalSideResult.value
    terminalPositions: ChipTerminalPositions = {}
    for attachPoint in attachPointSetResult.value.attachPointsForChip_get(
        chipRef
    ):
        if attachPoint.terminalSide is not terminalSide:
            continue
        terminalPositions[attachPoint.terminalName] = (
            attachPoint.worldColumn,
            attachPoint.worldRow,
        )
    return terminalPositions
