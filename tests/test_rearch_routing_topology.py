"""Tests for config-to-topology world skeleton building."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.config import (
    RoutingZoneGridConfig,
    SignalFlowConfig,
    routingZoneGridConfigResult_buildFromDocumentDict,
    signalFlowConfigResult_buildFromDocumentDict,
)
from signalflow.models import (
    GridCoord,
    Result,
    RoutingZoneGrid,
    RoutingZoneInterconnectAxis,
    RoutingZoneSense,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    routingZoneGridResult_buildFromConfig,
    routingZoneGridResult_buildFromSignalFlowConfig,
)


def configFixtureDocument_build(fixtureName: str) -> dict[str, object]:
    """Load one config-only YAML fixture by file name."""

    fixturePath: Path = (
        Path(__file__).parent.parent / "examples" / "configs" / fixtureName
    )
    with fixturePath.open(encoding="utf-8") as inputHandle:
        loadedDocument = yaml.safe_load(inputHandle.read())
    assert isinstance(loadedDocument, dict)
    return loadedDocument


class TestRoutingZoneGridTopology:
    """Verification of empty world-topology skeleton building."""

    def test_routingZoneGridResult_buildFromConfig_builds_4x4_world(self) -> None:
        """Explicit 4x4 world config should materialize 16 zones and 24 seams."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-rectangular-4x4.yaml")
            )
        )
        assert result_isOkCheck(configResult)

        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromConfig(configResult.value)
        )

        assert result_isOkCheck(routingZoneGridResult)
        routingZoneGrid: RoutingZoneGrid = routingZoneGridResult.value

        assert routingZoneGrid.worldSense is RoutingZoneSense.WEST_TO_EAST
        assert routingZoneGrid.gridSize == GridCoord(columnIndex=4, rowIndex=4)
        assert len(routingZoneGrid.routingZoneSet.routingZones) == 16
        assert len(
            routingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects
        ) == 24

        firstZoneResult = routingZoneGrid.zoneAtCoordResult_get(
            gridCoord=GridCoord(columnIndex=1, rowIndex=1)
        )
        assert result_isOkCheck(firstZoneResult)
        assert firstZoneResult.value.routingZoneSense is RoutingZoneSense.WEST_TO_EAST

    def test_routingZoneGridResult_buildFromSignalFlowConfig_honors_implicit_world(
        self,
    ) -> None:
        """Implicit world config should derive the simple 1 x (depth - 1) world."""

        diagnosticStack.stack_clear()
        configResult: Result[SignalFlowConfig] = (
            signalFlowConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-implicit-horizontal.yaml"),
                callingDepth=6,
            )
        )
        assert result_isOkCheck(configResult)

        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromSignalFlowConfig(configResult.value)
        )

        assert result_isOkCheck(routingZoneGridResult)
        routingZoneGrid: RoutingZoneGrid = routingZoneGridResult.value

        assert routingZoneGrid.gridSize == GridCoord(columnIndex=5, rowIndex=1)
        assert len(routingZoneGrid.routingZoneSet.routingZones) == 5
        assert (
            len(routingZoneGrid.routingZoneInterconnectSet.routingZoneInterconnects)
            == 4
        )

    def test_routingZoneGridResult_buildFromConfig_builds_vertical_interconnects(
        self,
    ) -> None:
        """Vertical worlds should include vertical neighboring seams."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-vertical-2x3.yaml")
            )
        )
        assert result_isOkCheck(configResult)

        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromConfig(configResult.value)
        )
        assert result_isOkCheck(routingZoneGridResult)
        routingZoneGrid: RoutingZoneGrid = routingZoneGridResult.value

        interconnectResult = routingZoneGrid.interconnectAtCoordsResult_get(
            sourceGridCoord=GridCoord(columnIndex=1, rowIndex=1),
            destinationGridCoord=GridCoord(columnIndex=1, rowIndex=2),
        )
        assert result_isOkCheck(interconnectResult)
        interconnectAxisResult = interconnectResult.value.interconnectAxisResult_get()
        assert result_isOkCheck(interconnectAxisResult)
        assert interconnectAxisResult.value is RoutingZoneInterconnectAxis.VERTICAL

    def test_routingZoneGridResult_buildFromConfig_preserves_pathing_surface(
        self,
    ) -> None:
        """The empty world skeleton should still support macro path selection."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-rectangular-4x4.yaml")
            )
        )
        assert result_isOkCheck(configResult)

        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromConfig(configResult.value)
        )
        assert result_isOkCheck(routingZoneGridResult)
        routingZoneGrid: RoutingZoneGrid = routingZoneGridResult.value

        pathResult = routingZoneGrid.pathBetweenZonesResult_build(
            sourceZoneId=type(
                routingZoneGrid.routingZoneSet.routingZones[0].routingZoneId
            )(id=GridCoord(columnIndex=3, rowIndex=3)),
            destinationZoneId=type(
                routingZoneGrid.routingZoneSet.routingZones[0].routingZoneId
            )(id=GridCoord(columnIndex=1, rowIndex=1)),
        )

        assert result_isOkCheck(pathResult)
        assert pathResult.value.zoneIds == (
            type(pathResult.value.zoneIds[0])(id=GridCoord(columnIndex=3, rowIndex=3)),
            type(pathResult.value.zoneIds[0])(id=GridCoord(columnIndex=2, rowIndex=3)),
            type(pathResult.value.zoneIds[0])(id=GridCoord(columnIndex=1, rowIndex=3)),
            type(pathResult.value.zoneIds[0])(id=GridCoord(columnIndex=1, rowIndex=2)),
            type(pathResult.value.zoneIds[0])(id=GridCoord(columnIndex=1, rowIndex=1)),
        )

    def test_zoneAtCoordResult_get_rejects_out_of_bounds_coord(self) -> None:
        """Direct coordinate lookup should reject coordinates outside the grid."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-simple-horizontal.yaml")
            )
        )
        assert result_isOkCheck(configResult)
        routingZoneGridResult: Result[RoutingZoneGrid] = (
            routingZoneGridResult_buildFromConfig(configResult.value)
        )
        assert result_isOkCheck(routingZoneGridResult)

        zoneResult = routingZoneGridResult.value.zoneAtCoordResult_get(
            gridCoord=GridCoord(columnIndex=4, rowIndex=1)
        )

        assert not result_isOkCheck(zoneResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[-1].code == "routing.zone_grid.coord.out_of_bounds"
