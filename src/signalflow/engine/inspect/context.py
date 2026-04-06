"""Shared inspect context and workflow types."""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.config import SignalFlowConfig
from signalflow.models import (
    ChipId,
    ChipInternalSolvedRouteSet,
    ChipPlacement,
    ChipRef,
    ChipTerminalSide,
    CircuitDocument,
    Diagnostic,
    Result,
    RouteObligationSet,
    RoutingZone,
    RoutingZoneAssignmentSet,
    RoutingZoneGrid,
    RoutingZoneGridSolvedRouteSet,
    RoutingZoneId,
    RoutingZoneInterconnectSolvedRouteSet,
    RoutingZoneLocalSolvedRouteSet,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack

from .terminal import (
    ANSI_BOLD as _ANSI_BOLD,
)
from .terminal import (
    ANSI_CYAN as _ANSI_CYAN,
)
from .terminal import (
    ANSI_DIM as _ANSI_DIM,
)
from .terminal import (
    ANSI_GREEN as _ANSI_GREEN,
)
from .terminal import (
    ANSI_MAGENTA as _ANSI_MAGENTA,
)
from .terminal import (
    ANSI_RED as _ANSI_RED,
)
from .terminal import (
    ANSI_WHITE as _ANSI_WHITE,
)
from .terminal import (
    ANSI_YELLOW as _ANSI_YELLOW,
)


@dataclass(frozen=True)
class SignalFlowContext:
    """Materialized current-stage inspect context for the new engine."""

    documentDict: dict[str, object]
    circuitDocument: CircuitDocument
    signalFlowConfig: SignalFlowConfig
    routingZoneGrid: RoutingZoneGrid
    routingZoneAssignmentSet: RoutingZoneAssignmentSet
    placedRoutingZoneGrid: RoutingZoneGrid
    routeObligationSet: RouteObligationSet
    chipInternalSolvedRouteSet: ChipInternalSolvedRouteSet
    routingZoneLocalSolvedRouteSet: RoutingZoneLocalSolvedRouteSet
    routingZoneInterconnectSolvedRouteSet: (
        RoutingZoneInterconnectSolvedRouteSet
    )
    routingZoneGridSolvedRouteSet: RoutingZoneGridSolvedRouteSet

    def __dir__(self) -> list[str]:
        return [
            "calls",
            "chipCount_get",
            "chips",
            "diagnostics_getAll",
            "interconnectCount_get",
            "interconnects",
            "placementForChipResult_get",
            "rootPlacementResult_get",
            "routes",
            "routingZoneCount_get",
            "world",
            "zoneOwningChipResult_get",
            "zones",
        ]

    def __repr__(self) -> str:
        return "<ctx>"

    def chipCount_get(self) -> int:
        return len(self.circuitDocument.circuitChipSet.chips)

    def routingZoneCount_get(self) -> int:
        return len(self.routingZoneGrid.routingZoneSet.routingZones)

    def interconnectCount_get(self) -> int:
        return len(
            self.routingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects
        )

    def zoneOwningChipResult_get(self, chipId: ChipId) -> Result[RoutingZone]:
        chipResult = self.circuitDocument.circuitChipSet.chipResult_get(chipId)
        if not result_isOkCheck(chipResult):
            return resultErr_build()
        for (
            routingZone
        ) in self.placedRoutingZoneGrid.routingZoneSet.routingZones:
            placement = (
                routingZone.chipPlacementSet.placementForChipOrNone_get(
                    chipResult.value.chipRef_build()
                )
            )
            if placement is not None:
                return resultOk_build(routingZone)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="engine.debug.missing_chip_zone",
            message=(
                "Inspect context could not find the "
                "owning placed zone for chip"
            ),
            context=(chipId.moduleName, chipId.functionName),
        )
        return resultErr_build()

    def placementForChipResult_get(
        self, chipId: ChipId
    ) -> Result[ChipPlacement]:
        chipResult = self.circuitDocument.circuitChipSet.chipResult_get(chipId)
        if not result_isOkCheck(chipResult):
            return resultErr_build()
        routingZoneResult = self.zoneOwningChipResult_get(chipId)
        if not result_isOkCheck(routingZoneResult):
            return resultErr_build()
        return (
            routingZoneResult.value.chipPlacementSet
            .placementForChipResult_get(chipResult.value.chipRef_build())
        )

    def rootPlacementResult_get(self) -> Result[ChipPlacement]:
        return self.placementForChipResult_get(
            self.circuitDocument.rootChipRef.chipId
        )

    def diagnostics_getAll(self) -> tuple[Diagnostic, ...]:
        return diagnosticStack.diagnosticSet_build().diagnostics_getAll()

    def chips_getAll(self):
        return self.circuitDocument.circuitChipSet.chips

    def chipIds_getAll(self) -> tuple[ChipId, ...]:
        return tuple(
            chip.chipId for chip in self.circuitDocument.circuitChipSet.chips
        )

    def chipResult_get(self, chipId: ChipId):
        return self.circuitDocument.circuitChipSet.chipResult_get(chipId)

    def rootChipResult_get(self):
        return self.circuitDocument.rootChipResult_get()

    def calls_getAll(self):
        return self.circuitDocument.circuitCallSet.circuitCalls

    def zones_getAll(self):
        return self.placedRoutingZoneGrid.routingZoneSet.routingZones

    def interconnects_getAll(self):
        return (
            self.placedRoutingZoneGrid
            .routingZoneInterconnectSet
            .routingZoneInterconnects
        )

    def placementsForZone_get(self, routingZoneId):
        routingZoneResult = (
            self.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
                routingZoneId
            )
        )
        if not result_isOkCheck(routingZoneResult):
            return ()
        return routingZoneResult.value.chipPlacementSet.placements

    def chipRoutesForChip_get(self, chipId: ChipId):
        return self.chipInternalSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def zoneLocalRoutesForChip_get(self, chipId: ChipId):
        return self.routingZoneLocalSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def zoneLocalRoutesForZone_get(self, routingZoneId: RoutingZoneId):
        return self.routingZoneLocalSolvedRouteSet.routesForZone_get(
            routingZoneId
        )

    def interconnectRoutesForZone_get(self, routingZoneId: RoutingZoneId):
        return self.routingZoneInterconnectSolvedRouteSet.routesForZone_get(
            routingZoneId
        )

    def interconnectRoutesForChip_get(self, chipId: ChipId):
        return self.routingZoneInterconnectSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def interconnectRoutesForInterconnect_get(self, routingZoneInterconnectId):
        return (
            self.routingZoneInterconnectSolvedRouteSet
            .routesForInterconnect_get(routingZoneInterconnectId)
        )

    def gridRoutesForChip_get(self, chipId: ChipId):
        return self.routingZoneGridSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def gridRoutesForZone_get(self, routingZoneId: RoutingZoneId):
        return self.routingZoneGridSolvedRouteSet.routesForZone_get(
            routingZoneId
        )

    def terminalCountsForChip_build(self, chipId: ChipId) -> dict[str, int]:
        chipResult = self.chipResult_get(chipId)
        if not result_isOkCheck(chipResult):
            return {}
        return {
            "north": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.NORTH
                ).terminals
            ),
            "south": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.SOUTH
                ).terminals
            ),
            "east": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.EAST
                ).terminals
            ),
            "west": len(
                chipResult.value.chipTerminalSet.terminalsOnSide_build(
                    ChipTerminalSide.WEST
                ).terminals
            ),
        }

    def locationRecordsForChip_build(
        self, chipId: ChipId
    ) -> tuple[dict[str, object], ...]:
        from .geometry import _chipPlacementPointForZone_build

        placementResult = self.placementForChipResult_get(chipId)
        zoneResult = self.zoneOwningChipResult_get(chipId)
        if not (
            result_isOkCheck(placementResult) and result_isOkCheck(zoneResult)
        ):
            return ()
        worldGridCoordResult = (
            zoneResult.value.routingZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(worldGridCoordResult):
            return ()
        worldPoint = _chipPlacementPointForZone_build(
            routingZone=zoneResult.value,
            chipPlacement=placementResult.value,
        )
        regionId = placementResult.value.chipTerminalRegionId
        regionSide = (
            regionId.routingZoneRegionSide.value
            if regionId is not None
            and regionId.routingZoneRegionSide is not None
            else "unknown"
        )
        return (
            {
                "zone": worldGridCoordResult.value,
                "terminalSide": regionSide,
                "orderIndex": placementResult.value.orderIndex,
                "worldPoint": worldPoint,
            },
        )

    @property
    def chips(self):
        from .surfaces import ChipView

        return ChipView(self)

    @property
    def zones(self):
        from .views import ZoneView

        return ZoneView(self)

    @property
    def calls(self):
        from .views import CallView

        return CallView(self)

    @property
    def routes(self):
        from .views import RouteView

        return RouteView(self)

    @property
    def interconnects(self):
        from .views import InterconnectView

        return InterconnectView(self)

    @property
    def world(self):
        from .views import GridView

        return GridView(self)


@dataclass(frozen=True)
class WorkflowView:
    """Interactive workflow surface for multi-step geometry operations."""

    debugContext: SignalFlowContext
    replLocals: dict

    def __dir__(self) -> list[str]:
        return [
            "status_print",
            "inspectOrder_print",
            "chipGeometryPush_run",
            "zonesNormalize_run",
            "zoneRecalculate_run",
        ]

    def __repr__(self) -> str:
        return "<workflows>"

    def _rebuildAndRefresh(self, label: str) -> bool:
        from .build import context_buildFromDocument
        from .repl import _diagnostics_printToStdout, _replLocals_build
        from .views import _ansiWrap_build

        diagnosticStack.stack_clear()
        newContextResult = context_buildFromDocument(
            self.debugContext.documentDict
        )
        if not result_isOkCheck(newContextResult):
            print(
                _ansiWrap_build(label, _ANSI_BOLD, _ANSI_YELLOW)
                + ": "
                + _ansiWrap_build("pipeline rebuild failed", _ANSI_RED)
            )
            _diagnostics_printToStdout()
            return False
        newLocals = _replLocals_build(
            newContextResult.value, replLocals=self.replLocals
        )
        self.replLocals.update(newLocals)
        return True

    def status_print(self) -> None:
        from .views import _ansiWrap_build

        lines = [
            _ansiWrap_build("workflow status", _ANSI_BOLD, _ANSI_CYAN),
            "",
            _ansiWrap_build("zone geometry source", _ANSI_BOLD, _ANSI_GREEN)
            + ": "
            + _ansiWrap_build(
                "chip-geometry-driven (chipDrawLines_build)", _ANSI_WHITE
            ),
            _ansiWrap_build("normalization cascade", _ANSI_BOLD, _ANSI_GREEN)
            + ": "
            + _ansiWrap_build(
                (
                    "per-column width + per-row height, "
                    "full pipeline rebuild on demand"
                ),
                _ANSI_WHITE,
            ),
            "",
            _ansiWrap_build("current zone frames", _ANSI_BOLD, _ANSI_GREEN),
        ]
        for zone in self.debugContext.zones_getAll():
            zoneId = zone.routingZoneId
            frame = zone.routingZoneFrame
            widthText = _ansiWrap_build(str(frame.horizontalSpan), _ANSI_WHITE)
            heightText = _ansiWrap_build(str(frame.verticalSpan), _ANSI_WHITE)
            lines.append(
                f"  {_ansiWrap_build(str(zoneId.id), _ANSI_CYAN)}"
                f"  w={widthText}"
                f"  h={heightText}"
                "  "
                f"origin=({frame.horizontalStart},{frame.verticalStart})"
            )
        print("\n".join(lines))

    def inspectOrder_print(self) -> None:
        from .views import _ansiWrap_build

        lines = [
            _ansiWrap_build(
                "canonical inspection order", _ANSI_BOLD, _ANSI_CYAN
            ),
            "",
            "  1. "
            + _ansiWrap_build("chips", _ANSI_BOLD, _ANSI_MAGENTA)
            + "           — chip geometry is upstream truth",
            "  2. "
            + _ansiWrap_build("zones", _ANSI_BOLD, _ANSI_MAGENTA)
            + "           — zone frame is derived from chips",
            "  3. "
            + _ansiWrap_build("interconnects", _ANSI_BOLD, _ANSI_MAGENTA)
            + "    — seam geometry depends on zone frames",
            "  4. "
            + _ansiWrap_build("world", _ANSI_BOLD, _ANSI_MAGENTA)
            + "           — world grid normalizes all zone frames",
            "",
            "  Example session:",
            "    " + _ansiWrap_build("chips.all_sprint()", _ANSI_DIM),
            "    "
            + _ansiWrap_build(
                "chip = chips.chip_get('App.ts', 'main()')", _ANSI_DIM
            ),
            "    " + _ansiWrap_build("chip.schematic_sprint()", _ANSI_DIM),
            "    " + _ansiWrap_build("zones.all_sprint()", _ANSI_DIM),
            "    " + _ansiWrap_build("zone = zones.zone_get(1, 1)", _ANSI_DIM),
            "    " + _ansiWrap_build("zone.placements_get()", _ANSI_DIM),
            "    " + _ansiWrap_build("interconnects.all_sprint()", _ANSI_DIM),
            "    "
            + _ansiWrap_build("world.gridStyle_sprint('zones')", _ANSI_DIM),
        ]
        print("\n".join(lines))

    def chipGeometryPush_run(self) -> None:
        from .views import _ansiWrap_build

        print(
            _ansiWrap_build("chipGeometryPush_run", _ANSI_BOLD, _ANSI_CYAN)
            + ": rebuilding pipeline from chip geometry…"
        )
        if self._rebuildAndRefresh("chipGeometryPush_run"):
            print(
                "  done — "
                + _ansiWrap_build(
                    "ctx  zones  chips  world  interconnects  routes",
                    _ANSI_MAGENTA,
                )
                + " refreshed"
            )

    def zonesNormalize_run(self) -> None:
        from .views import _ansiWrap_build

        print(
            _ansiWrap_build("zonesNormalize_run", _ANSI_BOLD, _ANSI_CYAN)
            + ": rebuilding pipeline with "
            + "per-column/row normalization…"
        )
        if self._rebuildAndRefresh("zonesNormalize_run"):
            print(
                "  done — zones normalized to column max-width / "
                "row max-height\n  "
                + _ansiWrap_build(
                    "ctx  zones  chips  world  interconnects  routes",
                    _ANSI_MAGENTA,
                )
                + " refreshed"
            )

    def zoneRecalculate_run(self, columnIndex: int, rowIndex: int) -> None:
        from .views import _ansiWrap_build

        print(
            _ansiWrap_build("zoneRecalculate_run", _ANSI_BOLD, _ANSI_CYAN)
            + f"({columnIndex}, {rowIndex}): rebuilding pipeline…"
        )
        if self._rebuildAndRefresh("zoneRecalculate_run"):
            print(
                f"  done — zone ({columnIndex},{rowIndex}) recalculated\n  "
                + _ansiWrap_build(
                    "ctx  zones  chips  world  interconnects  routes",
                    _ANSI_MAGENTA,
                )
                + " refreshed"
            )


@dataclass(frozen=True)
class ChipWorldFrame:
    """Placed world-frame for one chip drawing."""

    topLeft: tuple[int, int]
    bottomRight: tuple[int, int]
    widthColumns: int
    heightRows: int

    def __dir__(self) -> list[str]:
        return ["bottomRight", "heightRows", "topLeft", "widthColumns"]

    def __repr__(self) -> str:
        return (
            "<chip-world-frame "
            f"topLeft={self.topLeft} "
            f"bottomRight={self.bottomRight} "
            f"size={self.widthColumns}x{self.heightRows}>"
        )


DebugWorkflowView = WorkflowView
DebugChipWorldFrame = ChipWorldFrame


__all__ = [
    "ChipWorldFrame",
    "DebugChipWorldFrame",
    "DebugWorkflowView",
    "WorkflowView",
    "SignalFlowContext",
]
