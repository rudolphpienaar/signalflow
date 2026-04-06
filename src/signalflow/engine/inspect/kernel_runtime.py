"""Kernel and board runtime helpers for debug surfaces."""

from __future__ import annotations

import re

import yaml

from signalflow.board import (
    Board as DomainBoard,
)
from signalflow.board import (
    BoardChipPlacementPolicy,
    BoardKernel,
    BoardKernelWire,
    BoardMaterializedSolution,
    BoardMaterializePolicy,
    BoardSolution,
    BoardWiring,
    BoardZone,
    board_buildFromKernel,
    boardChannelLaneCounts_build,
    chipInternalPlacedKernelArtifacts_build,
)
from signalflow.models import (
    CallRouteObligation,
    ChipId,
    ChipPortDeclaration,
    ChipRef,
    ChipTerminalSide,
    RoutingKernel,
    RoutingZoneId,
    RoutingZoneInterconnectSolvedRoute,
    RoutingZoneLocalSolvedRoute,
    RoutingZoneRegionFrame,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    result_isOkCheck,
    routingZoneDrawLines_build,
)
from signalflow.notation import sfN
from signalflow.routing import (
    RealizedRoute,
    RealizedRouteCell,
    RouteSense,
    chipAttachPointSetResult_buildFromPlacedZone,
    chipLocalGeometrySetResult_buildFromChips,
)
from signalflow.routing.track import TrackDirection, trackCell_build

from .backend import boardBackend_get
from .context import SignalFlowContext
from .geometry import (
    _zoneDrawingLines_build,
    _zoneRoutesText_build,
    _zoneSummaryText_build,
    _zoneWorldCanvasText_build,
)
from .primitives import (
    KernelBoardHandle,
    KernelChannelHandle,
    KernelChannelsHandle,
    KernelWire,
    ZoneRegionHandle,
    ZoneRegionSetHandle,
)


def _kernelSolvedRoutes_get(
    debugContext: SignalFlowContext,
    kernel: RoutingKernel,
) -> tuple[
    RoutingZoneLocalSolvedRoute | RoutingZoneInterconnectSolvedRoute, ...
]:
    allSolvedRoutes = (
        debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        + (
            debugContext.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes
        )
    )
    kernelRegionIds = {
        routingZoneRegion.routingZoneRegionId
        for routingZoneRegion in kernel.routingZoneRegionSet.routingZoneRegions
    }
    return tuple(
        solvedRoute
        for solvedRoute in allSolvedRoutes
        if any(
            traversedRegionId in kernelRegionIds
            for traversedRegionId in solvedRoute.traversedRegionIds
        )
    )


def _chipEndpointText_build(chipRef: ChipRef, terminalName: str) -> str:
    chipId = chipRef.chipId
    return f"{chipId.moduleName}.{chipId.functionName}.{terminalName}"


def _destinationPortDeclarationOrNone_get(
    circuitDocument,
    callRouteObligation: CallRouteObligation,
) -> ChipPortDeclaration | None:
    destinationChipResult = circuitDocument.circuitChipSet.chipResult_get(
        callRouteObligation.destinationChipRef.chipId
    )
    if not result_isOkCheck(destinationChipResult):
        return None
    inputPortDeclarations = (
        destinationChipResult.value.inputPortDeclarationSet.portDeclarations
    )
    if not inputPortDeclarations:
        return None
    if callRouteObligation.sourcePortDeclaration is not None:
        for portDeclaration in inputPortDeclarations:
            if portDeclaration == callRouteObligation.sourcePortDeclaration:
                return portDeclaration
    if len(inputPortDeclarations) == 1:
        return inputPortDeclarations[0]
    return None


def _terminalSideOrNone_get(
    circuitDocument,
    chipRef: ChipRef,
    terminalName: str,
) -> ChipTerminalSide | None:
    chipResult = circuitDocument.circuitChipSet.chipResult_get(chipRef.chipId)
    if not result_isOkCheck(chipResult):
        return None
    for (
        portDeclaration
    ) in chipResult.value.inputPortDeclarationSet.portDeclarations:
        if terminalName in {
            portDeclaration.signalName,
            portDeclaration.returnName,
        }:
            return ChipTerminalSide.WEST
    for (
        portDeclaration
    ) in chipResult.value.outputPortDeclarationSet.portDeclarations:
        if terminalName in {
            portDeclaration.signalName,
            portDeclaration.returnName,
        }:
            return ChipTerminalSide.EAST
    return None


def _kernelWire_build(
    circuitDocument,
    callRouteObligation: CallRouteObligation,
    solvedRoute: RoutingZoneLocalSolvedRoute
    | RoutingZoneInterconnectSolvedRoute,
) -> KernelWire:
    sourcePortDeclaration = callRouteObligation.sourcePortDeclaration
    destinationPortDeclaration = _destinationPortDeclarationOrNone_get(
        circuitDocument=circuitDocument,
        callRouteObligation=callRouteObligation,
    )
    isReturnRoute = solvedRoute.solveKind.value.endswith("_return")
    if isReturnRoute:
        destinationTerminalName = (
            sourcePortDeclaration.returnName
            if sourcePortDeclaration is not None
            and sourcePortDeclaration.returnName is not None
            else "<missing_return>"
        )
        sourceTerminalName = (
            destinationPortDeclaration.returnName
            if destinationPortDeclaration is not None
            and destinationPortDeclaration.returnName is not None
            else "<missing_return>"
        )
        return KernelWire(
            sourceEndpointText=_chipEndpointText_build(
                chipRef=callRouteObligation.destinationChipRef,
                terminalName=sourceTerminalName,
            ),
            destinationEndpointText=_chipEndpointText_build(
                chipRef=callRouteObligation.sourceChipRef,
                terminalName=destinationTerminalName,
            ),
            sourceChipRef=callRouteObligation.destinationChipRef,
            destinationChipRef=callRouteObligation.sourceChipRef,
            sourceTerminalName=sourceTerminalName,
            destinationTerminalName=destinationTerminalName,
            sourceTerminalSide=_terminalSideOrNone_get(
                circuitDocument=circuitDocument,
                chipRef=callRouteObligation.destinationChipRef,
                terminalName=sourceTerminalName,
            )
            or ChipTerminalSide.WEST,
            destinationTerminalSide=_terminalSideOrNone_get(
                circuitDocument=circuitDocument,
                chipRef=callRouteObligation.sourceChipRef,
                terminalName=destinationTerminalName,
            )
            or ChipTerminalSide.WEST,
            isReturn=True,
        )
    sourceTerminalName = (
        sourcePortDeclaration.signalName
        if sourcePortDeclaration is not None
        and sourcePortDeclaration.signalName is not None
        else "<missing_signal>"
    )
    destinationTerminalName = (
        destinationPortDeclaration.signalName
        if destinationPortDeclaration is not None
        and destinationPortDeclaration.signalName is not None
        else "<missing_signal>"
    )
    return KernelWire(
        sourceEndpointText=_chipEndpointText_build(
            chipRef=callRouteObligation.sourceChipRef,
            terminalName=sourceTerminalName,
        ),
        destinationEndpointText=_chipEndpointText_build(
            chipRef=callRouteObligation.destinationChipRef,
            terminalName=destinationTerminalName,
        ),
        sourceChipRef=callRouteObligation.sourceChipRef,
        destinationChipRef=callRouteObligation.destinationChipRef,
        sourceTerminalName=sourceTerminalName,
        destinationTerminalName=destinationTerminalName,
        sourceTerminalSide=_terminalSideOrNone_get(
            circuitDocument=circuitDocument,
            chipRef=callRouteObligation.sourceChipRef,
            terminalName=sourceTerminalName,
        )
        or ChipTerminalSide.WEST,
        destinationTerminalSide=_terminalSideOrNone_get(
            circuitDocument=circuitDocument,
            chipRef=callRouteObligation.destinationChipRef,
            terminalName=destinationTerminalName,
        )
        or ChipTerminalSide.EAST,
        isReturn=False,
    )


def _kernelChannels_build(kernel: RoutingKernel) -> KernelChannelsHandle:
    laneCountByChannelName: dict[str, int] = {}
    for routingZoneRegion in kernel.routingZoneRegionSet.routingZoneRegions:
        regionKind = (
            routingZoneRegion.routingZoneRegionId.routingZoneRegionKind
        )
        regionSide = (
            routingZoneRegion.routingZoneRegionId.routingZoneRegionSide
        )
        if regionKind not in (
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
        ):
            continue
        if regionSide is None:
            continue
        prefixBySide = {
            RoutingZoneRegionSide.WEST: "w",
            RoutingZoneRegionSide.EAST: "e",
            RoutingZoneRegionSide.NORTH: "n",
            RoutingZoneRegionSide.SOUTH: "s",
        }
        prefix = prefixBySide.get(regionSide)
        if prefix is None:
            continue
        if regionKind in (
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
        ):
            channelName = f"{prefix}Long"
            laneCount = routingZoneRegion.routingZoneRegionFrame.horizontalSpan
        else:
            channelName = f"{prefix}Lat"
            laneCount = routingZoneRegion.routingZoneRegionFrame.verticalSpan
        laneCountByChannelName[channelName] = max(
            laneCountByChannelName.get(channelName, 0), laneCount
        )
    preferredChannelOrder = (
        "wLong",
        "nLat",
        "eLong",
        "sLat",
        "wLat",
        "nLong",
        "eLat",
        "sLong",
    )
    orderedChannelsByName: dict[str, KernelChannelHandle] = {}
    for channelName in preferredChannelOrder:
        laneCount = laneCountByChannelName.get(channelName)
        if laneCount is not None:
            orderedChannelsByName[channelName] = KernelChannelHandle(
                channelName=channelName,
                laneCount=laneCount,
            )
    for channelName in sorted(laneCountByChannelName):
        if channelName not in orderedChannelsByName:
            orderedChannelsByName[channelName] = KernelChannelHandle(
                channelName=channelName,
                laneCount=laneCountByChannelName[channelName],
            )
    return KernelChannelsHandle(_channelsByName=orderedChannelsByName)


def _kernelChannelsFromBoard_build(
    boardModel: DomainBoard,
) -> KernelChannelsHandle:
    laneCountByChannelName = boardChannelLaneCounts_build(boardModel)
    preferredChannelOrder = (
        "wLong",
        "nLat",
        "eLong",
        "sLat",
        "wLat",
        "nLong",
        "eLat",
        "sLong",
    )
    orderedChannelsByName: dict[str, KernelChannelHandle] = {}
    for channelName in preferredChannelOrder:
        laneCount = laneCountByChannelName.get(channelName)
        if laneCount is not None:
            orderedChannelsByName[channelName] = KernelChannelHandle(
                channelName=channelName,
                laneCount=laneCount,
            )
    for channelName in sorted(laneCountByChannelName):
        if channelName not in orderedChannelsByName:
            orderedChannelsByName[channelName] = KernelChannelHandle(
                channelName=channelName,
                laneCount=laneCountByChannelName[channelName],
            )
    return KernelChannelsHandle(_channelsByName=orderedChannelsByName)


def _kernelBoard_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
    side: str,
    kernel: RoutingKernel,
) -> KernelBoardHandle:
    zoneResult = (
        debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
    )
    if not result_isOkCheck(zoneResult):
        raise RuntimeError(
            f"Could not build board for missing zone {routingZoneId}"
        )
    boardModel = board_buildFromKernel(
        routingZoneId=routingZoneId,
        side=side,
        routingZone=zoneResult.value,
        kernel=kernel,
        circuitDocument=debugContext.circuitDocument,
        moduleBoundaryPaddingCells=debugContext.placedRoutingZoneGrid.moduleBoxPadding,
    )
    return KernelBoardHandle(
        routingZoneId=routingZoneId,
        side=side,
        kernel=kernel,
        boardBackend=boardBackend_get(),
        boardModel=boardModel,
        channels=_kernelChannelsFromBoard_build(boardModel),
    )


def _boardWiringRuntime_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
    side: str,
    kernel: RoutingKernel,
    boardModel: DomainBoard,
) -> BoardWiring:
    callRouteObligationByKey = {
        (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        ): callRouteObligation
        for callRouteObligation in (
            debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations
        )
    }
    runtimeWiresMutable: list[BoardKernelWire] = []
    for solvedRoute in _kernelSolvedRoutes_get(
        debugContext=debugContext, kernel=kernel
    ):
        routeKey = (
            solvedRoute.sourceChipRef,
            solvedRoute.destinationChipRef,
            solvedRoute.childCallIndex,
        )
        reverseRouteKey = (
            solvedRoute.destinationChipRef,
            solvedRoute.sourceChipRef,
            solvedRoute.childCallIndex,
        )
        callRouteObligation = callRouteObligationByKey.get(routeKey)
        if callRouteObligation is None:
            callRouteObligation = callRouteObligationByKey.get(reverseRouteKey)
        if callRouteObligation is None:
            continue
        debugWire = _kernelWire_build(
            circuitDocument=debugContext.circuitDocument,
            callRouteObligation=callRouteObligation,
            solvedRoute=solvedRoute,
        )
        runtimeWiresMutable.append(
            BoardKernelWire(
                sourceEndpointText=debugWire.sourceEndpointText,
                destinationEndpointText=debugWire.destinationEndpointText,
                sourceChipRef=debugWire.sourceChipRef,
                destinationChipRef=debugWire.destinationChipRef,
                sourceTerminalName=debugWire.sourceTerminalName,
                destinationTerminalName=debugWire.destinationTerminalName,
                sourceTerminalSide=debugWire.sourceTerminalSide,
                destinationTerminalSide=debugWire.destinationTerminalSide,
                isReturn=debugWire.isReturn,
            )
        )
    return BoardWiring(board=boardModel, _wires=tuple(runtimeWiresMutable))


def _boardKernelRuntime_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
    side: str,
    kernel: RoutingKernel,
) -> BoardKernel:
    from .surfaces import KernelHandle

    zoneResult = (
        debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
    )
    if not result_isOkCheck(zoneResult):
        raise RuntimeError(
            f"Could not build board for missing zone {routingZoneId}"
        )

    def _boardModel_build(
        chipPlacementPolicy: BoardChipPlacementPolicy = (
            BoardChipPlacementPolicy.CENTROIDAL
        ),
    ) -> DomainBoard:
        return board_buildFromKernel(
            routingZoneId=routingZoneId,
            side=side,
            routingZone=zoneResult.value,
            kernel=kernel,
            circuitDocument=debugContext.circuitDocument,
            moduleBoundaryPaddingCells=debugContext.placedRoutingZoneGrid.moduleBoxPadding,
            chipPlacementPolicy=chipPlacementPolicy,
        )

    boardModel = _boardModel_build()
    wiring = _boardWiringRuntime_build(
        debugContext=debugContext,
        routingZoneId=routingZoneId,
        side=side,
        kernel=kernel,
        boardModel=boardModel,
    )
    return BoardKernel(
        routingZoneId=routingZoneId,
        side=side,
        kernel=kernel,
        board=boardModel,
        wiring=wiring,
        areasProvider=lambda: ZoneRegionSetHandle(
            _regions=tuple(
                ZoneRegionHandle(
                    routingZoneRegionId=region.routingZoneRegionId,
                    routingZoneRegionFrame=region.routingZoneRegionFrame,
                )
                for region in kernel.routingZoneRegionSet.routingZoneRegions
            )
        ),
        schematicProvider=lambda: KernelHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
            side=side,
            kernel=kernel,
        ).schematic_sprint(),
        routesProvider=lambda: KernelHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
            side=side,
            kernel=kernel,
        ).routes_sprint(),
        yamlProvider=lambda: yaml.safe_dump(
            debugContext.documentDict, sort_keys=False
        ).rstrip(),
        boardProvider=_boardModel_build,
    )


def _boardZoneRuntime_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
) -> BoardZone:
    from .surfaces import ZoneHandle

    def _kernelRuntime_get(side: str) -> BoardKernel | None:
        return ZoneHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        )._routingKernel_get(side)

    def _kernelsRuntime_get() -> dict[str, BoardKernel]:
        kernelBySide: dict[str, BoardKernel] = {}
        for side in ("north", "south", "east", "west", "intra"):
            kernel = _kernelRuntime_get(side)
            if kernel is not None:
                kernelBySide[side] = kernel
        return kernelBySide

    return BoardZone(
        routingZoneId=routingZoneId,
        rawProvider=lambda: (
            debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
                routingZoneId
            )
        ),
        areasProvider=lambda: ZoneHandle(
            debugContext=debugContext, routingZoneId=routingZoneId
        ).areas_get(),
        areaProvider=lambda kindOrKey, side: ZoneHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ).area_get(kindOrKey, side),
        idProvider=lambda: routingZoneId,
        senseProvider=lambda: ZoneHandle(
            debugContext=debugContext,
            routingZoneId=routingZoneId,
        ).sense_get(),
        placementsProvider=lambda: debugContext.placementsForZone_get(
            routingZoneId
        ),
        routesProvider=lambda: debugContext.zoneLocalRoutesForZone_get(
            routingZoneId
        ),
        routesTextProvider=lambda: _zoneRoutesText_build(
            debugContext=debugContext, routingZoneId=routingZoneId
        ),
        schematicProvider=lambda: _zoneDrawingLines_build(
            debugContext=debugContext, routingZoneId=routingZoneId
        ),
        worldProvider=lambda: _zoneWorldCanvasText_build(
            debugContext=debugContext, routingZoneId=routingZoneId
        ),
        kernelsProvider=_kernelsRuntime_get,
        kernelProvider=_kernelRuntime_get,
        summaryProvider=lambda: _zoneSummaryText_build(
            debugContext=debugContext, routingZoneId=routingZoneId
        ),
    )


def _chipInternalBoardKernelRuntime_build(
    debugContext: SignalFlowContext,
    chipId: ChipId,
) -> BoardKernel:
    chipResult = debugContext.chipResult_get(chipId)
    if not result_isOkCheck(chipResult):
        raise RuntimeError(
            f"Missing chip {chipId.moduleName}.{chipId.functionName}"
        )
    chip = chipResult.value
    artifacts = chipInternalPlacedKernelArtifacts_build(
        chip,
        moduleBoundaryPaddingCells=debugContext.placedRoutingZoneGrid.moduleBoxPadding,
    )
    board = board_buildFromKernel(
        routingZoneId=artifacts.routingZone.routingZoneId,
        side="internal",
        routingZone=artifacts.routingZone,
        kernel=artifacts.kernel,
        circuitDocument=artifacts.circuitDocument,
        moduleBoundaryPaddingCells=artifacts.routingZoneGrid.moduleBoxPadding,
    )
    runtimeWiresMutable: list[BoardKernelWire] = []
    for circuitCall in artifacts.circuitDocument.circuitCallSet.circuitCalls:
        sourceChipResult = (
            artifacts.circuitDocument.circuitChipSet.chipResult_get(
                circuitCall.sourceChipRef.chipId
            )
        )
        destinationChipResult = (
            artifacts.circuitDocument.circuitChipSet.chipResult_get(
                circuitCall.destinationChipRef.chipId
            )
        )
        if not result_isOkCheck(sourceChipResult) or not result_isOkCheck(
            destinationChipResult
        ):
            continue
        sourceChip = sourceChipResult.value
        destinationChip = destinationChipResult.value
        sourcePortDeclaration = circuitCall.sourcePortDeclaration
        if sourcePortDeclaration is None:
            if circuitCall.callIndex >= len(
                sourceChip.outputPortDeclarationSet.portDeclarations
            ):
                continue
            sourcePortDeclaration = (
                sourceChip.outputPortDeclarationSet.portDeclarations[
                    circuitCall.callIndex
                ]
            )
        if not destinationChip.inputPortDeclarationSet.portDeclarations:
            continue
        destinationPortDeclaration = (
            destinationChip.inputPortDeclarationSet.portDeclarations[0]
        )
        if (
            sourcePortDeclaration.signalName is not None
            and destinationPortDeclaration.signalName is not None
        ):
            runtimeWiresMutable.append(
                BoardKernelWire(
                    sourceEndpointText=_chipEndpointText_build(
                        circuitCall.sourceChipRef,
                        sourcePortDeclaration.signalName,
                    ),
                    destinationEndpointText=_chipEndpointText_build(
                        circuitCall.destinationChipRef,
                        destinationPortDeclaration.signalName,
                    ),
                    sourceChipRef=circuitCall.sourceChipRef,
                    destinationChipRef=circuitCall.destinationChipRef,
                    sourceTerminalName=sourcePortDeclaration.signalName,
                    destinationTerminalName=destinationPortDeclaration.signalName,
                    sourceTerminalSide=_terminalSideOrNone_get(
                        artifacts.circuitDocument,
                        circuitCall.sourceChipRef,
                        sourcePortDeclaration.signalName,
                    )
                    or ChipTerminalSide.EAST,
                    destinationTerminalSide=_terminalSideOrNone_get(
                        artifacts.circuitDocument,
                        circuitCall.destinationChipRef,
                        destinationPortDeclaration.signalName,
                    )
                    or ChipTerminalSide.WEST,
                    isReturn=False,
                )
            )
        if (
            destinationPortDeclaration.returnName is not None
            and sourcePortDeclaration.returnName is not None
        ):
            runtimeWiresMutable.append(
                BoardKernelWire(
                    sourceEndpointText=_chipEndpointText_build(
                        circuitCall.destinationChipRef,
                        destinationPortDeclaration.returnName,
                    ),
                    destinationEndpointText=_chipEndpointText_build(
                        circuitCall.sourceChipRef,
                        sourcePortDeclaration.returnName,
                    ),
                    sourceChipRef=circuitCall.destinationChipRef,
                    destinationChipRef=circuitCall.sourceChipRef,
                    sourceTerminalName=destinationPortDeclaration.returnName,
                    destinationTerminalName=sourcePortDeclaration.returnName,
                    sourceTerminalSide=_terminalSideOrNone_get(
                        artifacts.circuitDocument,
                        circuitCall.destinationChipRef,
                        destinationPortDeclaration.returnName,
                    )
                    or ChipTerminalSide.EAST,
                    destinationTerminalSide=_terminalSideOrNone_get(
                        artifacts.circuitDocument,
                        circuitCall.sourceChipRef,
                        sourcePortDeclaration.returnName,
                    )
                    or ChipTerminalSide.WEST,
                    isReturn=True,
                )
            )
    wiring = BoardWiring(board=board, _wires=tuple(runtimeWiresMutable))
    return BoardKernel(
        routingZoneId=artifacts.routingZone.routingZoneId,
        side="internal",
        kernel=artifacts.kernel,
        board=board,
        wiring=wiring,
        areasProvider=lambda: ZoneRegionSetHandle(
            _regions=tuple(
                ZoneRegionHandle(
                    routingZoneRegionId=region.routingZoneRegionId,
                    routingZoneRegionFrame=region.routingZoneRegionFrame,
                )
                for region in (
                    artifacts.kernel.routingZoneRegionSet.routingZoneRegions
                )
            )
        ),
        schematicProvider=lambda: "\n".join(
            routingZoneDrawLines_build(artifacts.routingZone)
        ),
        routesProvider=lambda: "\n".join(
            wire.wiringDeclaration for wire in artifacts.schema.wires
        )
        if artifacts.schema.wires
        else "<kernel routes unavailable>",
        yamlProvider=lambda: yaml.safe_dump(
            artifacts.syntheticDocumentDict, sort_keys=False
        ).rstrip(),
        boardProvider=lambda chipPlacementPolicy: board_buildFromKernel(
            routingZoneId=artifacts.routingZone.routingZoneId,
            side="internal",
            routingZone=artifacts.routingZone,
            kernel=artifacts.kernel,
            circuitDocument=artifacts.circuitDocument,
            moduleBoundaryPaddingCells=artifacts.routingZoneGrid.moduleBoxPadding,
            chipPlacementPolicy=chipPlacementPolicy,
        ),
    )


def solution_realize(
    board: DomainBoard,
    solution: BoardSolution,
    policy: BoardMaterializePolicy | None = None,
) -> BoardMaterializedSolution:
    return solution.board_materialize(board, policy=policy)


def solution_materialize(
    board: DomainBoard,
    solution: BoardSolution,
    policy: BoardMaterializePolicy | None = None,
) -> BoardMaterializedSolution:
    return solution_realize(board=board, solution=solution, policy=policy)


def _boardEndpointAttachPoint_build(
    *, board: KernelBoardHandle, endpointText: str
) -> tuple[int, int] | None:
    endpointParts = endpointText.split(".")
    if len(endpointParts) < 3:
        return None
    terminalName = endpointParts[-1]
    chipName = ".".join(endpointParts[:-1])
    return board.terminal_get(chipName, terminalName)


def _regionByTaggedNameOrNone_get(
    geometry: ZoneRegionSetHandle,
    taggedName: str,
) -> ZoneRegionHandle | None:
    for regionHandle in geometry.all_get():
        if regionHandle._tagged_name == taggedName:
            return regionHandle
    return None


def _regionTaggedNamesForWorldCell_build(
    geometry: ZoneRegionSetHandle,
    columnIndex: int,
    rowIndex: int,
) -> tuple[str, ...]:
    taggedNamesMutable: list[str] = []
    for regionHandle in geometry.all_get():
        frame = regionHandle.routingZoneRegionFrame
        if (
            frame.horizontalStart
            <= columnIndex
            < frame.horizontalEnd_calculate()
            and frame.verticalStart <= rowIndex < frame.verticalEnd_calculate()
        ):
            taggedNamesMutable.append(regionHandle._tagged_name)
    return tuple(sorted(taggedNamesMutable))


def _frameBorderCells_build(
    frame: RoutingZoneRegionFrame,
) -> set[tuple[int, int]]:
    horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
    verticalEndInclusive = frame.verticalEnd_calculate() - 1
    cells: set[tuple[int, int]] = set()
    for columnIndex in range(
        frame.horizontalStart, horizontalEndInclusive + 1
    ):
        cells.add((columnIndex, frame.verticalStart))
        cells.add((columnIndex, verticalEndInclusive))
    for rowIndex in range(frame.verticalStart, verticalEndInclusive + 1):
        cells.add((frame.horizontalStart, rowIndex))
        cells.add((horizontalEndInclusive, rowIndex))
    return cells


def _frameInteriorCells_build(
    frame: RoutingZoneRegionFrame,
) -> set[tuple[int, int]]:
    horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
    verticalEndInclusive = frame.verticalEnd_calculate() - 1
    if (
        horizontalEndInclusive - frame.horizontalStart < 2
        or verticalEndInclusive - frame.verticalStart < 2
    ):
        return set()
    return {
        (columnIndex, rowIndex)
        for columnIndex in range(
            frame.horizontalStart + 1, horizontalEndInclusive
        )
        for rowIndex in range(frame.verticalStart + 1, verticalEndInclusive)
    }


def _cellWalk_buildFromRoutePoints(
    routePoints: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    if not routePoints:
        return ()
    cellWalkMutable: list[tuple[int, int]] = [routePoints[0]]
    for (column0, row0), (column1, row1) in zip(
        routePoints, routePoints[1:], strict=False
    ):
        if column0 == column1 and row0 == row1:
            continue
        if column0 != column1 and row0 != row1:
            return ()
        if row0 == row1:
            step = 1 if column1 > column0 else -1
            for columnIndex in range(column0 + step, column1 + step, step):
                cellWalkMutable.append((columnIndex, row0))
        else:
            step = 1 if row1 > row0 else -1
            for rowIndex in range(row0 + step, row1 + step, step):
                cellWalkMutable.append((column0, rowIndex))
    return tuple(cellWalkMutable)


def _realizedRoute_buildFromCellWalk(
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    cellWalk: tuple[tuple[int, int], ...],
    routeSense: RouteSense,
) -> RealizedRoute | None:
    if len(cellWalk) < 2:
        return None
    directionMap: dict[tuple[int, int], set[TrackDirection]] = {}

    def _directionSet_get(
        columnIndex: int, rowIndex: int
    ) -> set[TrackDirection]:
        return directionMap.setdefault((columnIndex, rowIndex), set())

    for (column0, row0), (column1, row1) in zip(
        cellWalk, cellWalk[1:], strict=False
    ):
        columnDelta = column1 - column0
        rowDelta = row1 - row0
        if abs(columnDelta) + abs(rowDelta) != 1:
            return None
        if columnDelta == 1:
            _directionSet_get(column0, row0).add(TrackDirection.EAST)
            _directionSet_get(column1, row1).add(TrackDirection.WEST)
        elif columnDelta == -1:
            _directionSet_get(column0, row0).add(TrackDirection.WEST)
            _directionSet_get(column1, row1).add(TrackDirection.EAST)
        elif rowDelta == 1:
            _directionSet_get(column0, row0).add(TrackDirection.SOUTH)
            _directionSet_get(column1, row1).add(TrackDirection.NORTH)
        else:
            _directionSet_get(column0, row0).add(TrackDirection.NORTH)
            _directionSet_get(column1, row1).add(TrackDirection.SOUTH)
    realizedCells = tuple(
        RealizedRouteCell(
            worldRow=rowIndex,
            worldCol=columnIndex,
            trackCell=trackCell_build(frozenset(directions)),
        )
        for (columnIndex, rowIndex), directions in sorted(
            directionMap.items(),
            key=lambda item: (item[0][1], item[0][0]),
        )
    )
    return RealizedRoute(
        sourceChipRef=sourceChipRef,
        destinationChipRef=destinationChipRef,
        childCallIndex=childCallIndex,
        routeSense=routeSense,
        cells=realizedCells,
    )


def _endpointAttachPoint_build(
    debugContext: SignalFlowContext,
    routingZoneId: RoutingZoneId,
    kernelWire: KernelWire,
    endpointText: str,
) -> tuple[int, int] | None:
    zoneResult = (
        debugContext.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )
    )
    if not result_isOkCheck(zoneResult):
        return None
    geometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        debugContext.circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(geometrySetResult):
        return None
    attachPointSetResult = chipAttachPointSetResult_buildFromPlacedZone(
        zone=zoneResult.value,
        chipLocalGeometrySet=geometrySetResult.value,
        circuitDocument=debugContext.circuitDocument,
    )
    if not result_isOkCheck(attachPointSetResult):
        return None
    if endpointText == kernelWire.sourceEndpointText:
        chipRef = kernelWire.sourceChipRef
        terminalName = kernelWire.sourceTerminalName
        terminalSide = kernelWire.sourceTerminalSide
    elif endpointText == kernelWire.destinationEndpointText:
        chipRef = kernelWire.destinationChipRef
        terminalName = kernelWire.destinationTerminalName
        terminalSide = kernelWire.destinationTerminalSide
    else:
        return None
    attachPointResult = (
        attachPointSetResult.value.attachPointForTerminalResult_get(
            chipRef=chipRef,
            terminalSide=terminalSide,
            terminalName=terminalName,
        )
    )
    if not result_isOkCheck(attachPointResult):
        return None
    return (
        attachPointResult.value.worldColumn,
        attachPointResult.value.worldRow,
    )


def _channelAnchorPoint_build(
    board: KernelBoardHandle,
    channelToken: str,
    isReturn: bool,
) -> tuple[int, int] | None:
    del isReturn
    channelMatch = re.fullmatch(r"([a-zA-Z]+)\[(\d+)\]", channelToken)
    if channelMatch is None:
        return None
    channelName = channelMatch.group(1)
    laneIndex = int(channelMatch.group(2))
    geometry = board.geometry_get()
    if channelName == "wLong":
        laneRegion = geometry.area_get(sfN.Wi.region_key or "")
        if (
            laneRegion is None
            or laneIndex > laneRegion.routingZoneRegionFrame.horizontalSpan
        ):
            return None
        return (
            laneRegion.routingZoneRegionFrame.horizontalStart + laneIndex - 1,
            0,
        )
    if channelName == "eLong":
        laneRegion = geometry.area_get(sfN.Ei.region_key or "")
        if (
            laneRegion is None
            or laneIndex > laneRegion.routingZoneRegionFrame.horizontalSpan
        ):
            return None
        return (
            laneRegion.routingZoneRegionFrame.horizontalStart + laneIndex - 1,
            0,
        )
    if channelName == "nLat":
        laneRegion = geometry.area_get(sfN.Ni.region_key or "")
        if (
            laneRegion is None
            or laneIndex > laneRegion.routingZoneRegionFrame.verticalSpan
        ):
            return None
        return (
            0,
            laneRegion.routingZoneRegionFrame.verticalStart + laneIndex - 1,
        )
    if channelName == "sLat":
        laneRegion = geometry.area_get(sfN.Si.region_key or "")
        if (
            laneRegion is None
            or laneIndex > laneRegion.routingZoneRegionFrame.verticalSpan
        ):
            return None
        return (
            0,
            laneRegion.routingZoneRegionFrame.verticalStart + laneIndex - 1,
        )
    return None
