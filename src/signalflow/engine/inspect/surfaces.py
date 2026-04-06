"""Interactive chip/kernel/zone debug surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board import BoardKernel, BoardSolver
from signalflow.models import (
    ChipId,
    RoutingKernel,
    RoutingZoneId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    result_isOkCheck,
)

from .chip_helpers import (
    _chipDrawingLines_build,
    _chipHandle_build,
    _chipSummaryText_build,
    _chipTerminalLocalPositions_build,
    _chipTerminalWorldPositions_build,
    _chipTitleParts_build,
    _chipTitleText_build,
    _chipWorldFrameOrNone_build,
)
from .context import ChipWorldFrame, SignalFlowContext
from .geometry import (
    _textBlockSize_build,
    _worldCanvasLines_build,
    _zoneDrawingLines_build,
    _zoneRoutesText_build,
    _zoneSummaryText_build,
    _zoneWorldCanvasText_build,
)
from .kernel_runtime import (
    _boardKernelRuntime_build,
    _boardWiringRuntime_build,
    _kernelBoard_build,
    _kernelSolvedRoutes_get,
    _kernelWire_build,
)
from .primitives import (
    KernelBoardHandle,
    KernelWire,
    ZoneAreaView,
    ZoneRegionHandle,
    ZoneRegionSetHandle,
)


def _summary_print(text: str) -> None:
    from .repl import _summary_print as _impl

    _impl(text)


@dataclass(frozen=True)
class ChipView:
    """Interactive inspection view over canonical chips."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "all_get",
            "all_text",
            "chipByTitle_get",
            "chip_get",
            "count_get",
            "ids_get",
            "location_get",
            "locations_get",
            "names_get",
            "placement_get",
            "root_get",
            "routes_get",
            "schematic_text",
            "size_get",
            "summary_text",
            "terminals_get",
            "terminals_getLocalPositions",
            "terminals_getWorldPositions",
            "title_get",
            "worldFrame_get",
        ]

    def __repr__(self) -> str:
        return "<chips>"

    def all_get(self):
        return tuple(
            _chipHandle_build(
                debugContext=self.debugContext, chipId=chip.chipId
            )
            for chip in self.debugContext.chips_getAll()
        )

    def count_get(self) -> int:
        return len(self.all_get())

    def ids_get(self):
        return self.debugContext.chipIds_getAll()

    def names_get(self) -> tuple[str, ...]:
        return tuple(
            f"{chipId.moduleName}:{chipId.functionName}"
            for chipId in self.ids_get()
        )

    def all_sprint(self) -> str:
        return "\n\n".join(
            self.summary_sprint(chipId.moduleName, chipId.functionName)
            for chipId in self.ids_get()
        )

    def root_get(self):
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=self.debugContext.circuitDocument.rootChipRef.chipId,
        )

    def title_get(self, moduleName: str, functionName: str) -> str:
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return _chipTitleText_build(chipId)

    def size_get(self, moduleName: str, functionName: str) -> tuple[int, int]:
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        drawingLines = _chipDrawingLines_build(
            debugContext=self.debugContext,
            chipId=chipId,
        )
        return _textBlockSize_build(drawingLines)

    def terminals_get(
        self, moduleName: str, functionName: str
    ) -> dict[str, int]:
        return self.debugContext.terminalCountsForChip_build(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def terminals_getLocalPositions(
        self, moduleName: str, functionName: str, wall: str
    ):
        return _chipTerminalLocalPositions_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
            wall=wall,
        )

    def terminals_getWorldPositions(
        self, moduleName: str, functionName: str, wall: str
    ):
        return _chipTerminalWorldPositions_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
            wall=wall,
        )

    def placement_get(self, moduleName: str, functionName: str):
        return self.debugContext.placementForChipResult_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def location_get(self, moduleName: str, functionName: str):
        locations = self.locations_get(moduleName, functionName)
        return locations[0] if locations else None

    def locations_get(self, moduleName: str, functionName: str):
        return self.debugContext.locationRecordsForChip_build(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def routes_get(self, moduleName: str, functionName: str):
        return self.debugContext.chipRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def schematic_sprint(self, moduleName: str, functionName: str) -> str:
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return "\n".join(
            _chipDrawingLines_build(
                debugContext=self.debugContext,
                chipId=chipId,
            )
        )

    def summary_sprint(self, moduleName: str, functionName: str) -> str:
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return _chipSummaryText_build(
            debugContext=self.debugContext, chipId=chipId
        )

    def worldFrame_get(
        self, moduleName: str, functionName: str
    ) -> ChipWorldFrame | None:
        return _chipWorldFrameOrNone_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def chip_get(self, moduleName: str, functionName: str):
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def chipByTitle_get(self, chipTitle: str):
        moduleName, functionName = _chipTitleParts_build(chipTitle)
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=ChipId(moduleName=moduleName, functionName=functionName),
        )

    def __getitem__(self, chipTitle: str):
        return self.chipByTitle_get(chipTitle)


@dataclass(frozen=True)
class KernelWiringHandle:
    """Inspectable symbolic wiring surface for one routing kernel."""

    debugContext: SignalFlowContext
    routingZoneId: RoutingZoneId
    side: str
    kernel: RoutingKernel
    _wires: tuple[KernelWire, ...]

    def __dir__(self) -> list[str]:
        return [
            "algebraic_text",
            "all_get",
            "board_get",
            "channels_get",
            "list_text",
            "solver_get",
        ]

    def __repr__(self) -> str:
        return f"<kernel-wiring {len(self._wires)} wire(s)>"

    def all_get(self) -> tuple[KernelWire, ...]:
        return self._wires

    def board_get(self):
        return _kernelBoard_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
        )

    def channels_get(self):
        return self.board_get().channels_get()

    def solver_get(self) -> BoardSolver:
        boardHandle = self.board_get()
        runtimeWiring = _boardWiringRuntime_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            boardModel=boardHandle.boardModel,
        )
        return BoardSolver(board=boardHandle.boardModel, wiring=runtimeWiring)

    def list_sprint(self) -> str:
        if not self._wires:
            return "<no wiring in this kernel>"
        return "\n".join(
            kernelWire.wireText_get() for kernelWire in self._wires
        )

    def algebraic_sprint(self, endpointText: str) -> str:
        matchingWires = tuple(
            kernelWire
            for kernelWire in self._wires
            if endpointText
            in (
                kernelWire.sourceEndpointText,
                kernelWire.destinationEndpointText,
                kernelWire.wireText_get(),
            )
        )
        if not matchingWires:
            return f"<no wiring for endpoint {endpointText}>"
        return self.solver_get().algebraic_sprint(endpointText)


@dataclass(frozen=True)
class KernelHandle:
    """Interactive handle for a single Routing Kernel."""

    debugContext: SignalFlowContext
    routingZoneId: RoutingZoneId
    side: str
    kernel: RoutingKernel

    def __dir__(self) -> list[str]:
        return [
            "areas_get",
            "board_get",
            "raw_get",
            "routes_text",
            "schematic_text",
            "side_get",
            "solver_get",
            "wiring_get",
        ]

    def __repr__(self) -> str:
        return f"<kernel {self.side} of {self.routingZoneId.id}>"

    def side_get(self) -> str:
        return self.side

    def areas_get(self) -> ZoneRegionSetHandle:
        return ZoneRegionSetHandle(
            _regions=tuple(
                ZoneRegionHandle(
                    routingZoneRegionId=region.routingZoneRegionId,
                    routingZoneRegionFrame=region.routingZoneRegionFrame,
                )
                for region in (
                    self.kernel.routingZoneRegionSet.routingZoneRegions
                )
            )
        )

    def board_get(self) -> KernelBoardHandle:
        return _kernelBoard_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
        )

    def _kernelDraw_render(self, mode: str = "pixel") -> str:
        regions = self.kernel.routingZoneRegionSet.routingZoneRegions
        if not regions:
            return f"<kernel {self.side} has no regions>"
        h_start = min(
            r.routingZoneRegionFrame.horizontalStart for r in regions
        )
        h_end = max(
            r.routingZoneRegionFrame.horizontalEnd_calculate() for r in regions
        )
        v_start = min(r.routingZoneRegionFrame.verticalStart for r in regions)
        v_end = max(
            r.routingZoneRegionFrame.verticalEnd_calculate() for r in regions
        )
        worldCanvasLines = _worldCanvasLines_build(self.debugContext)
        if not worldCanvasLines:
            return "<error: could not build world canvas>"
        croppedLines: list[str] = []
        for rowIndex in range(v_start, v_end):
            if rowIndex < len(worldCanvasLines):
                croppedLines.append(worldCanvasLines[rowIndex][h_start:h_end])
        header = (
            f"kernel {self.side} of {self.routingZoneId.id}  "
            f"({h_end - h_start}x{v_end - v_start})"
        )
        return header + "\n" + "\n".join(croppedLines)

    def schematic_sprint(self, mode: str = "pixel") -> str:
        return self._kernelDraw_render(mode=mode)

    def wiring_get(self) -> KernelWiringHandle:
        callRouteObligationByKey = {
            (
                callRouteObligation.sourceChipRef,
                callRouteObligation.destinationChipRef,
                callRouteObligation.childCallIndex,
            ): callRouteObligation
            for callRouteObligation in (
                self.debugContext.routeObligationSet.callRouteObligationSet.callRouteObligations
            )
        }
        wiringMutable: list[KernelWire] = []
        for solvedRoute in _kernelSolvedRoutes_get(
            debugContext=self.debugContext,
            kernel=self.kernel,
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
                callRouteObligation = callRouteObligationByKey.get(
                    reverseRouteKey
                )
            if callRouteObligation is None:
                continue
            wiringMutable.append(
                _kernelWire_build(
                    circuitDocument=self.debugContext.circuitDocument,
                    callRouteObligation=callRouteObligation,
                    solvedRoute=solvedRoute,
                )
            )
        return KernelWiringHandle(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            _wires=tuple(wiringMutable),
        )

    def solver_get(
        self, board: KernelBoardHandle | None = None
    ) -> BoardSolver:
        activeBoard = board or self.board_get()
        runtimeWiring = _boardWiringRuntime_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=self.side,
            kernel=self.kernel,
            boardModel=activeBoard.boardModel,
        )
        return BoardSolver(board=activeBoard.boardModel, wiring=runtimeWiring)

    def _kernelRoutesDraw_render(self) -> str:
        zoneResult = (
            self.debugContext
            .placedRoutingZoneGrid
            .routingZoneSet
            .zoneResult_get(self.routingZoneId)
        )
        if not result_isOkCheck(zoneResult):
            return "<error: zone not found>"
        filteredSolvedRoutes = _kernelSolvedRoutes_get(
            debugContext=self.debugContext, kernel=self.kernel
        )
        if not filteredSolvedRoutes:
            return "<no routes in this kernel>"
        from signalflow.routing.route import (
            RealizedRouteSet,
            routePoints_realize,
        )

        realizedRoutes = []
        for route in filteredSolvedRoutes:
            result = routePoints_realize(
                sourceChipRef=route.sourceChipRef,
                destinationChipRef=route.destinationChipRef,
                childCallIndex=route.childCallIndex,
                routePoints=route.routePoints,
            )
            if result_isOkCheck(result):
                realizedRoutes.append(result.value)
        realizedRouteSet = RealizedRouteSet(tuple(realizedRoutes))
        from signalflow.render.routes import (
            RouteCanvasSize,
            routeWorldCanvas_render,
        )

        frame = zoneResult.value.routingZoneFrame
        canvasSize = RouteCanvasSize(
            width=frame.horizontalSpan, height=frame.verticalSpan
        )
        fullCanvasLines = routeWorldCanvas_render(
            realizedRouteSet, canvasSize=canvasSize
        )
        regions = self.kernel.routingZoneRegionSet.routingZoneRegions
        h_start = min(
            r.routingZoneRegionFrame.horizontalStart for r in regions
        )
        h_end = max(
            r.routingZoneRegionFrame.horizontalEnd_calculate() for r in regions
        )
        v_start = min(r.routingZoneRegionFrame.verticalStart for r in regions)
        v_end = max(
            r.routingZoneRegionFrame.verticalEnd_calculate() for r in regions
        )
        rel_h0 = h_start - frame.horizontalStart
        rel_h1 = h_end - frame.horizontalStart
        rel_v0 = v_start - frame.verticalStart
        rel_v1 = v_end - frame.verticalStart
        croppedLines: list[str] = []
        for rowIndex in range(rel_v0, rel_v1):
            if 0 <= rowIndex < len(fullCanvasLines):
                croppedLines.append(fullCanvasLines[rowIndex][rel_h0:rel_h1])
        header = (
            f"kernel routes {self.side} of {self.routingZoneId.id}  "
            f"({h_end - h_start}x{v_end - v_start})"
        )
        return header + "\n" + "\n".join(croppedLines)

    def routes_sprint(self) -> str:
        return self._kernelRoutesDraw_render()

    def raw_get(self):
        return self.kernel


@dataclass(frozen=True)
class ZoneHandle:
    """Interactive handle for one placed routing zone."""

    debugContext: SignalFlowContext
    routingZoneId: RoutingZoneId

    def __dir__(self) -> list[str]:
        return [
            "area_get",
            "areas_get",
            "id_get",
            "kernel_get",
            "kernels_get",
            "placements_get",
            "raw_get",
            "routes_get",
            "routes_text",
            "schematic_text",
            "sense_get",
            "summary_text",
            "world_text",
        ]

    def __repr__(self) -> str:
        return f"<zone {self.routingZoneId.id}>"

    def raw_get(self):
        return self._routingZone_get()

    def areas_get(self) -> ZoneRegionSetHandle:
        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return ZoneRegionSetHandle(_regions=())
        zone = zoneResult.value

        def _handles(kernel):
            if kernel is None:
                return ()
            return tuple(
                ZoneRegionHandle(
                    routingZoneRegionId=region.routingZoneRegionId,
                    routingZoneRegionFrame=region.routingZoneRegionFrame,
                )
                for region in kernel.routingZoneRegionSet.routingZoneRegions
            )

        all_handles = (
            _handles(zone.intraKernel)
            + _handles(zone.westKernel)
            + _handles(zone.eastKernel)
            + _handles(zone.northKernel)
            + _handles(zone.southKernel)
        )
        return ZoneRegionSetHandle(_regions=all_handles)

    def area_get(self, kindOrKey: str, side: str | None = None):
        return self.areas_get().area_get(kindOrKey, side)

    def id_get(self):
        return self._routingZoneId_get()

    def sense_get(self) -> str | None:
        return self._routingZoneSense_get()

    def placements_get(self):
        return self._routingZonePlacements_get()

    def routes_get(self):
        return self._routingZoneLocalRoutes_get()

    def routes_sprint(self) -> str:
        return self._routingZoneRoutesDraw_render()

    def schematic_sprint(self) -> str:
        return self._routingZoneDraw_render()

    def world_sprint(self) -> str:
        return self._routingZoneWorldCanvas_render()

    def kernels_get(self) -> dict[str, BoardKernel]:
        kernelBySide: dict[str, BoardKernel] = {}
        for side in ("north", "south", "east", "west", "intra"):
            kernelHandle = self.kernel_get(side)
            if kernelHandle is not None:
                kernelBySide[side] = kernelHandle
        return kernelBySide

    def kernel_get(self, side: str = "intra") -> BoardKernel | None:
        return self._routingKernel_get(side)

    def _routingZone_get(self):
        return (
            self.debugContext
            .placedRoutingZoneGrid
            .routingZoneSet
            .zoneResult_get(self.routingZoneId)
        )

    def _routingZoneAreas_get(self) -> ZoneAreaView:
        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return ZoneAreaView({})
        zone = zoneResult.value

        def _handle_build(regions):
            return ZoneRegionSetHandle(
                _regions=tuple(
                    ZoneRegionHandle(
                        routingZoneRegionId=region.routingZoneRegionId,
                        routingZoneRegionFrame=region.routingZoneRegionFrame,
                    )
                    for region in regions
                )
            )

        return ZoneAreaView(
            {
                "intra": _handle_build(
                    zone.intraKernel.routingZoneRegionSet.routingZoneRegions
                    if zone.intraKernel
                    else ()
                ),
                "west": _handle_build(
                    zone.westKernel.routingZoneRegionSet.routingZoneRegions
                    if zone.westKernel
                    else ()
                ),
                "east": _handle_build(
                    zone.eastKernel.routingZoneRegionSet.routingZoneRegions
                    if zone.eastKernel
                    else ()
                ),
                "north": _handle_build(
                    zone.northKernel.routingZoneRegionSet.routingZoneRegions
                    if zone.northKernel
                    else ()
                ),
                "south": _handle_build(
                    zone.southKernel.routingZoneRegionSet.routingZoneRegions
                    if zone.southKernel
                    else ()
                ),
            }
        )

    def _routingZoneArea_get(
        self, kindOrKey: str, side: str | None = None
    ) -> ZoneRegionHandle | None:
        if "/" in kindOrKey:
            sidePart, kindPart = kindOrKey.split("/", 1)
        else:
            kindPart = kindOrKey
            sidePart = side
        try:
            wantKind = RoutingZoneRegionKind(kindPart)
        except ValueError:
            return None
        wantSide = None
        if sidePart:
            try:
                wantSide = RoutingZoneRegionSide(sidePart)
            except ValueError:
                return None
        areas = self._routingZoneAreas_get()
        for kernel_side in areas:
            for handle in areas[kernel_side]._regions:
                if (
                    handle.routingZoneRegionId.routingZoneRegionKind
                    is wantKind
                    and handle.routingZoneRegionId.routingZoneRegionSide
                    is wantSide
                ):
                    return handle
        return None

    def _routingZoneId_get(self):
        return self.routingZoneId

    def _routingZoneSense_get(self) -> str | None:
        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return None
        return zoneResult.value.routingZoneSense.value

    def _routingZonePlacements_get(self):
        return self.debugContext.placementsForZone_get(self.routingZoneId)

    def _routingZoneLocalRoutes_get(self):
        return self.debugContext.zoneLocalRoutesForZone_get(self.routingZoneId)

    def _routingKernel_get(self, side: str = "intra") -> BoardKernel | None:
        zoneResult = self._routingZone_get()
        if not result_isOkCheck(zoneResult):
            return None
        zone = zoneResult.value
        kernel_map = {
            "intra": zone.intraKernel,
            "west": zone.westKernel,
            "east": zone.eastKernel,
            "north": zone.northKernel,
            "south": zone.southKernel,
        }
        kernel = kernel_map.get(side.lower())
        if not kernel:
            return None
        return _boardKernelRuntime_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
            side=side.lower(),
            kernel=kernel,
        )

    def _routingZoneRoutesDraw_render(self) -> str:
        return _zoneRoutesText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def _routingZoneRoutesDraw_print(self) -> None:
        _summary_print(self._routingZoneRoutesDraw_render())

    def _routingZoneWorldCanvas_render(self) -> str:
        return _zoneWorldCanvasText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def _routingZoneWorldCanvas_print(self) -> None:
        _summary_print(self._routingZoneWorldCanvas_render())

    def _routingZoneDraw_render(self) -> str:
        return _zoneDrawingLines_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )

    def _routingZoneDraw_print(self) -> None:
        _summary_print(self._routingZoneDraw_render())

    def _routingZone_draw(self) -> None:
        self._routingZoneDraw_print()

    def _routingZone_print(self) -> None:
        self._routingZoneDraw_print()

    def summary_sprint(self) -> str:
        return _zoneSummaryText_build(
            debugContext=self.debugContext,
            routingZoneId=self.routingZoneId,
        )


DebugChipView = ChipView
DebugKernelHandle = KernelHandle
DebugKernelWiringHandle = KernelWiringHandle
DebugZoneHandle = ZoneHandle


__all__ = [
    "DebugChipView",
    "DebugKernelHandle",
    "DebugKernelWiringHandle",
    "DebugZoneHandle",
    "ChipView",
    "KernelHandle",
    "KernelWiringHandle",
    "ZoneHandle",
]
