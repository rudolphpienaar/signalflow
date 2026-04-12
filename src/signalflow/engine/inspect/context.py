"""Shared inspect context and workflow types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from signalflow.config import SignalFlowConfig
from signalflow.models import (
    ChipId,
    ChipInternalSolvedRouteSet,
    ChipPlacement,
    ChipRef,
    ChipTerminalSide,
    CircuitDocument,
    Diagnostic,
    GridCoord,
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

if TYPE_CHECKING:
    from signalflow.board import BoardZone


@dataclass(frozen=True)
class InspectStagedWorld:
    """Explicit staging bundle from the upstream routing/placement pipeline."""

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


@dataclass(frozen=True)
class InspectBoardWorld:
    """Board-first staged zone substrate used by inspect surfaces."""

    boardZonesById: dict[RoutingZoneId, BoardZone]
    compatibilityPlacedGrid: RoutingZoneGrid


@dataclass(frozen=True)
class SignalFlowContext:
    """Materialized current-stage inspect context for the new engine."""

    documentDict: dict[str, object]
    circuitDocument: CircuitDocument
    signalFlowConfig: SignalFlowConfig
    stagedWorld: InspectStagedWorld
    boardWorld: InspectBoardWorld

    @property
    def routingZoneGrid(self) -> RoutingZoneGrid:
        return self.stagedWorld.routingZoneGrid

    @property
    def routingZoneAssignmentSet(self) -> RoutingZoneAssignmentSet:
        return self.stagedWorld.routingZoneAssignmentSet

    @property
    def placedRoutingZoneGrid(self) -> RoutingZoneGrid:
        return self.stagedWorld.placedRoutingZoneGrid

    @property
    def routeObligationSet(self) -> RouteObligationSet:
        return self.stagedWorld.routeObligationSet

    @property
    def chipInternalSolvedRouteSet(self) -> ChipInternalSolvedRouteSet:
        return self.stagedWorld.chipInternalSolvedRouteSet

    @property
    def routingZoneLocalSolvedRouteSet(
        self,
    ) -> RoutingZoneLocalSolvedRouteSet:
        return self.stagedWorld.routingZoneLocalSolvedRouteSet

    @property
    def routingZoneInterconnectSolvedRouteSet(
        self,
    ) -> RoutingZoneInterconnectSolvedRouteSet:
        return self.stagedWorld.routingZoneInterconnectSolvedRouteSet

    @property
    def compatibilityInterconnectSolvedRouteSet(
        self,
    ) -> RoutingZoneInterconnectSolvedRouteSet:
        return self.routingZoneInterconnectSolvedRouteSet

    @property
    def routingZoneGridSolvedRouteSet(
        self,
    ) -> RoutingZoneGridSolvedRouteSet:
        return self.stagedWorld.routingZoneGridSolvedRouteSet

    def __dir__(self) -> list[str]:
        return [
            "calls",
            "chipCount_get",
            "chips",
            "compatibility_interconnects",
            "diagnostics_getAll",
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

    def stagedZoneResult_get(self, routingZoneId: RoutingZoneId):
        """Return one placed/staged zone by id.

        This is an explicit access point for the upstream placement-stage zone
        model. Inspect internals should prefer this method over reaching
        directly into `placedRoutingZoneGrid`.
        """

        return self.placedRoutingZoneGrid.routingZoneSet.zoneResult_get(
            routingZoneId
        )

    def stagedInterconnectAtCoordsResult_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        """Return one placed/staged interconnect by endpoint coordinates."""

        return self.placedRoutingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=GridCoord(
                columnIndex=sourceColumnIndex,
                rowIndex=sourceRowIndex,
            ),
            destinationGridCoord=GridCoord(
                columnIndex=destinationColumnIndex,
                rowIndex=destinationRowIndex,
            ),
        )

    def stagedGridSize_get(self) -> GridCoord:
        """Return the grid size of the placed/staged routing world."""

        return self.placedRoutingZoneGrid.gridSize

    def moduleBoundaryPadding_get(self) -> int:
        """Return the current staged module-box padding policy."""

        return self.placedRoutingZoneGrid.moduleBoxPadding

    def placedGrid_get(self) -> RoutingZoneGrid:
        """Return the staged/placed routing grid compatibility object."""

        return self.placedRoutingZoneGrid

    def callRouteObligations_getAll(self):
        """Return all staged call-route obligations."""

        return (
            self.routeObligationSet
            .callRouteObligationSet
            .callRouteObligations
        )

    def chipInternalRouteObligations_getAll(self):
        """Return all staged chip-internal route obligations."""

        return (
            self.routeObligationSet
            .chipInternalRouteObligationSet
            .chipInternalRouteObligations
        )

    def routingZoneAssignments_getAll(self):
        """Return all staged zone assignments."""

        return self.routingZoneAssignmentSet.routingZoneAssignments

    def assignmentsForZone_get(self, routingZoneId: RoutingZoneId):
        """Return staged assignments for one zone."""

        return self.routingZoneAssignmentSet.assignmentsForZone_get(
            routingZoneId
        )

    def zoneOwningChipResult_get(self, chipId: ChipId) -> Result[RoutingZone]:
        chipResult = self.circuitDocument.circuitChipSet.chipResult_get(chipId)
        if not result_isOkCheck(chipResult):
            return resultErr_build()
        for routingZone in (
            self.placedRoutingZoneGrid.routingZoneSet.routingZones
        ):
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

    def routingGridSize_get(self) -> GridCoord:
        return self.routingZoneGrid.gridSize

    def routingZoneAtCoordResult_get(self, gridCoord: GridCoord):
        return self.routingZoneGrid.zoneAtCoordResult_get(gridCoord)

    def routingInterconnectAtCoordsResult_get(
        self,
        sourceGridCoord: GridCoord,
        destinationGridCoord: GridCoord,
    ):
        return self.routingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=sourceGridCoord,
            destinationGridCoord=destinationGridCoord,
        )

    def zones_getAll(self):
        return self.compatibilityZones_getAll()

    def interconnects_getAll(self):
        return (
            self.routingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects
        )

    def compatibilityInterconnects_getAll(self):
        return self.interconnects_getAll()

    def placementsForZone_get(self, routingZoneId):
        routingZoneResult = self.stagedZoneResult_get(routingZoneId)
        if not result_isOkCheck(routingZoneResult):
            return ()
        return routingZoneResult.value.chipPlacementSet.placements

    def assignmentForChipResult_get(self, chipId: ChipId):
        return self.routingZoneAssignmentSet.assignmentForChipResult_get(
            chipId
        )

    def boardZones_getAll(self):
        return tuple(self.boardWorld.boardZonesById.values())

    def boardZoneById_get(self, routingZoneId: RoutingZoneId):
        return self.boardWorld.boardZonesById.get(routingZoneId)

    def boardPlacedGrid_get(self) -> RoutingZoneGrid:
        return self.boardWorld.compatibilityPlacedGrid

    def compatibilityZoneResult_get(
        self, routingZoneId: RoutingZoneId
    ) -> Result[RoutingZone]:
        boardZone = self.boardZoneById_get(routingZoneId)
        if boardZone is not None:
            return cast(Result[RoutingZone], boardZone.raw_get())
        return self.stagedZoneResult_get(routingZoneId)

    def compatibilityZones_getAll(self) -> tuple[RoutingZone, ...]:
        zonesMutable: list[RoutingZone] = []
        for boardZone in self.boardZones_getAll():
            zoneResult = cast(Result[RoutingZone], boardZone.raw_get())
            if result_isOkCheck(zoneResult):
                zonesMutable.append(zoneResult.value)
        return tuple(zonesMutable)

    def chipInternalSolvedRoutes_getAll(self):
        return self.chipInternalSolvedRouteSet.chipInternalSolvedRoutes

    def zoneLocalSolvedRoutes_getAll(self):
        return self.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes

    def interconnectSolvedRoutes_getAll(self):
        return (
            self.routingZoneInterconnectSolvedRouteSet
            .routingZoneInterconnectSolvedRoutes
        )

    def compatibilityInterconnectSolvedRoutes_getAll(self):
        return self.interconnectSolvedRoutes_getAll()

    def gridSolvedRoutes_getAll(self):
        return self.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes

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

    def compatibilityInterconnectRoutesForZone_get(
        self, routingZoneId: RoutingZoneId
    ):
        return self.interconnectRoutesForZone_get(routingZoneId)

    def interconnectRoutesForChip_get(self, chipId: ChipId):
        return self.routingZoneInterconnectSolvedRouteSet.routesForChip_get(
            ChipRef(chipId=chipId)
        )

    def compatibilityInterconnectRoutesForChip_get(self, chipId: ChipId):
        return self.interconnectRoutesForChip_get(chipId)

    def interconnectRoutesForInterconnect_get(self, routingZoneInterconnectId):
        return (
            self.routingZoneInterconnectSolvedRouteSet
            .routesForInterconnect_get(routingZoneInterconnectId)
        )

    def compatibilityInterconnectRoutesForInterconnect_get(
        self, routingZoneInterconnectId
    ):
        return self.interconnectRoutesForInterconnect_get(
            routingZoneInterconnectId
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
    def compatibility_interconnects(self):
        from .views import InterconnectView

        return InterconnectView(self)

    @property
    def interconnects(self):
        """Compatibility alias for older seam/interconnect inspection code."""

        return self.compatibility_interconnects

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
            + _ansiWrap_build("world", _ANSI_BOLD, _ANSI_MAGENTA)
            + "           — world view composes zone-owned geometry",
            "  4. "
            + _ansiWrap_build(
                "compatibility_interconnects", _ANSI_BOLD, _ANSI_MAGENTA
            )
            + " — deprecated seam tooling only",
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
            "    "
            + _ansiWrap_build("world.gridStyle_sprint('zones')", _ANSI_DIM),
            "    "
            + _ansiWrap_build(
                "compatibility_interconnects.all_sprint()", _ANSI_DIM
            ),
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
                    (
                        "ctx  zones  chips  world  "
                        "compatibility_interconnects  routes"
                    ),
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
                    (
                        "ctx  zones  chips  world  "
                        "compatibility_interconnects  routes"
                    ),
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
                    (
                        "ctx  zones  chips  world  "
                        "compatibility_interconnects  routes"
                    ),
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
