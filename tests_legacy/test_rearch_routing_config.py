"""Tests for routing-zone world configuration models and parsing.

These tests exercise only the configuration surface for the new zone-grid
architecture. They do not build zones or solvers; they only verify that
world-grid settings can be modeled, parsed, defaulted, and counted correctly.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.config import (
    RoutingLanePackingPolicy,
    RoutingOccupancyPolicy,
    RoutingZoneGridConfig,
    RoutingZoneGridConfigSource,
    RoutingZoneGridDimensions,
    routingZoneGridConfigForCallingDepth_build,
    routingZoneGridConfigResult_buildFromDocumentDict,
    routingZoneGridConfigSourceResult_buildFromDocumentDict,
    routingZoneGridDimensionsForCallingDepth_build,
    routingZoneGridDimensionsResult_build,
)
from signalflow.models import (
    Result,
    RoutingZoneChannelSense,
    RoutingZoneGridPathPolicy,
    RoutingZoneSense,
    diagnosticStack,
    result_isOkCheck,
)


def configFixtureDocument_build(fixtureName: str) -> dict[str, object]:
    """Load one config-only YAML fixture by file name.

    Args:
        fixtureName: File name beneath `examples/configs/`.

    Returns:
        Parsed YAML document for the requested fixture.
    """

    fixturePath: Path = (
        Path(__file__).parent.parent / "examples" / "configs" / fixtureName
    )
    with fixturePath.open(encoding="utf-8") as inputHandle:
        loadedDocument = yaml.safe_load(inputHandle.read())
    assert isinstance(loadedDocument, dict)
    return loadedDocument


class TestRoutingZoneGridConfigModels:
    """Verification of routing-zone world-config models."""

    def test_routingZoneGridDimensions_calculate_counts_for_4x4_world(self) -> None:
        """A 4x4 grid should imply 16 zones and 24 interconnects."""

        routingZoneGridDimensionsResult: Result[RoutingZoneGridDimensions] = (
            routingZoneGridDimensionsResult_build(columnCount=4, rowCount=4)
        )
        assert result_isOkCheck(routingZoneGridDimensionsResult)
        routingZoneGridDimensions: RoutingZoneGridDimensions = (
            routingZoneGridDimensionsResult.value
        )

        assert routingZoneGridDimensions.routingZoneCount_calculate() == 16
        assert routingZoneGridDimensions.routingZoneInterconnectCount_calculate() == 24

    def test_routingZoneGridDimensionsForCallingDepth_build_derives_horizontal_regime(
        self,
    ) -> None:
        """West-to-east defaults should derive one zone per two depth layers."""

        routingZoneGridDimensionsResult = (
            routingZoneGridDimensionsForCallingDepth_build(
                worldSense=RoutingZoneSense.WEST_TO_EAST,
                callingDepth=5,
            )
        )
        assert result_isOkCheck(routingZoneGridDimensionsResult)
        routingZoneGridDimensions = routingZoneGridDimensionsResult.value

        assert routingZoneGridDimensions.columnCount == 3
        assert routingZoneGridDimensions.rowCount == 1

    def test_routingZoneGridDimensionsForCallingDepth_build_derives_vertical_regime(
        self,
    ) -> None:
        """North-to-south defaults should derive one zone per two depth layers."""

        routingZoneGridDimensionsResult = (
            routingZoneGridDimensionsForCallingDepth_build(
                worldSense=RoutingZoneSense.NORTH_TO_SOUTH,
                callingDepth=4,
            )
        )
        assert result_isOkCheck(routingZoneGridDimensionsResult)
        routingZoneGridDimensions = routingZoneGridDimensionsResult.value

        assert routingZoneGridDimensions.columnCount == 1
        assert routingZoneGridDimensions.rowCount == 2


class TestRoutingZoneGridConfigParsing:
    """Verification of YAML-to-config parsing for the world-config surface."""

    def test_routingZoneGridConfigResult_buildFromDocumentDict_defaults_optional_fields(
        self,
    ) -> None:
        """Omitted optional policy fields should normalize to explicit defaults."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-simple-horizontal.yaml")
            )
        )

        assert result_isOkCheck(configResult)
        config: RoutingZoneGridConfig = configResult.value
        assert config.worldSense is RoutingZoneSense.WEST_TO_EAST
        assert config.routingZoneGridDimensions.columnCount == 3
        assert config.routingZoneGridDimensions.rowCount == 1
        assert config.pathPolicy is RoutingZoneGridPathPolicy.HORIZONTAL_FIRST
        assert config.channelSense is RoutingZoneChannelSense.CLOCKWISE
        assert config.occupancyPolicy is RoutingOccupancyPolicy.STRIP
        assert config.packingPolicy is RoutingLanePackingPolicy.FREE
        assert config.moduleBoxPadding == 3
        assert config.routingZoneCount_calculate() == 3
        assert config.routingZoneInterconnectCount_calculate() == 2

    def test_routingZoneGridConfigResult_buildFromDocumentDict_parses_rectangular_world(
        self,
    ) -> None:
        """Explicit rectangular world config should preserve all declared values."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-rectangular-4x4.yaml")
            )
        )

        assert result_isOkCheck(configResult)
        config: RoutingZoneGridConfig = configResult.value
        assert config.worldSense is RoutingZoneSense.WEST_TO_EAST
        assert config.routingZoneGridDimensions.columnCount == 4
        assert config.routingZoneGridDimensions.rowCount == 4
        assert config.pathPolicy is RoutingZoneGridPathPolicy.HORIZONTAL_FIRST
        assert config.channelSense is RoutingZoneChannelSense.CLOCKWISE
        assert config.occupancyPolicy is RoutingOccupancyPolicy.STRIP
        assert config.packingPolicy is RoutingLanePackingPolicy.FREE
        assert config.moduleBoxPadding == 3
        assert config.routingZoneCount_calculate() == 16
        assert config.routingZoneInterconnectCount_calculate() == 24

    def test_routingZoneGridConfigSource_parses_vertical_world(self) -> None:
        """Vertical-world config should preserve explicit policy choices."""

        diagnosticStack.stack_clear()
        configSourceResult: Result[RoutingZoneGridConfigSource] = (
            routingZoneGridConfigSourceResult_buildFromDocumentDict(
                configFixtureDocument_build("world-vertical-2x3.yaml")
            )
        )

        assert result_isOkCheck(configSourceResult)
        configSource: RoutingZoneGridConfigSource = configSourceResult.value
        assert configSource.worldSense is RoutingZoneSense.NORTH_TO_SOUTH
        assert configSource.routingZoneGridDimensionsSource.columnCount == 2
        assert configSource.routingZoneGridDimensionsSource.rowCount == 3
        assert configSource.pathPolicy is RoutingZoneGridPathPolicy.VERTICAL_FIRST
        assert configSource.channelSense is RoutingZoneChannelSense.ANTICLOCKWISE
        assert configSource.occupancyPolicy is RoutingOccupancyPolicy.STRIP
        assert configSource.packingPolicy is RoutingLanePackingPolicy.FREE
        assert configSource.moduleBoxPadding is None

    def test_routingZoneGridConfigSource_allows_missing_grid(self) -> None:
        """World config should allow the user to omit explicit grid dimensions."""

        diagnosticStack.stack_clear()
        configSourceResult: Result[RoutingZoneGridConfigSource] = (
            routingZoneGridConfigSourceResult_buildFromDocumentDict(
                configFixtureDocument_build("world-implicit-horizontal.yaml")
            )
        )

        assert result_isOkCheck(configSourceResult)
        configSource: RoutingZoneGridConfigSource = configSourceResult.value
        assert configSource.routingZoneGridDimensionsSource is None
        assert configSource.worldSense is RoutingZoneSense.WEST_TO_EAST
        assert configSource.pathPolicy is RoutingZoneGridPathPolicy.HORIZONTAL_FIRST
        assert configSource.occupancyPolicy is RoutingOccupancyPolicy.STRIP
        assert configSource.packingPolicy is RoutingLanePackingPolicy.FREE
        assert configSource.moduleBoxPadding is None

    def test_routingZoneGridConfigForCallingDepth_build_derives_missing_grid(
        self,
    ) -> None:
        """Missing grid dimensions should derive from calling depth explicitly."""

        diagnosticStack.stack_clear()
        configSourceResult: Result[RoutingZoneGridConfigSource] = (
            routingZoneGridConfigSourceResult_buildFromDocumentDict(
                configFixtureDocument_build("world-implicit-vertical.yaml")
            )
        )

        assert result_isOkCheck(configSourceResult)
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigForCallingDepth_build(
                configSource=configSourceResult.value,
                callingDepth=5,
            )
        )
        assert result_isOkCheck(configResult)
        config: RoutingZoneGridConfig = configResult.value

        assert config.worldSense is RoutingZoneSense.NORTH_TO_SOUTH
        assert config.routingZoneGridDimensions.columnCount == 1
        assert config.routingZoneGridDimensions.rowCount == 3
        assert config.channelSense is RoutingZoneChannelSense.ANTICLOCKWISE
        assert config.occupancyPolicy is RoutingOccupancyPolicy.STRIP
        assert config.packingPolicy is RoutingLanePackingPolicy.FREE
        assert config.moduleBoxPadding == 3

    def test_routingZoneGridConfigResult_parses_explicit_occupancy_policy(
        self,
    ) -> None:
        """Explicit occupancy policy should be preserved."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                {
                    "world": {
                        "sense": "west_to_east",
                        "grid": {"columns": 2, "rows": 1},
                        "occupancy_policy": "cell",
                    }
                }
            )
        )

        assert result_isOkCheck(configResult)
        assert configResult.value.occupancyPolicy is RoutingOccupancyPolicy.CELL

    def test_routingZoneGridConfigResult_parses_explicit_packing_policy(
        self,
    ) -> None:
        """Explicit packing policy should be preserved."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                {
                    "world": {
                        "sense": "west_to_east",
                        "grid": {"columns": 2, "rows": 1},
                        "packing_policy": "monotone",
                    }
                }
            )
        )

        assert result_isOkCheck(configResult)
        assert (
            configResult.value.packingPolicy is RoutingLanePackingPolicy.MONOTONE
        )

    def test_routingZoneGridConfigResult_parses_explicit_module_box_padding(
        self,
    ) -> None:
        """Explicit module-box padding should be preserved."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                {
                    "world": {
                        "sense": "west_to_east",
                        "grid": {"columns": 2, "rows": 1},
                        "module_box_padding": 5,
                    }
                }
            )
        )

        assert result_isOkCheck(configResult)
        assert configResult.value.moduleBoxPadding == 5

    def test_routingZoneGridConfigResult_buildFromDocumentDict_derives_missing_grid(
        self,
    ) -> None:
        """One-step config parsing should derive omitted grid dimensions."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-implicit-horizontal.yaml"),
                callingDepth=6,
            )
        )

        assert result_isOkCheck(configResult)
        config: RoutingZoneGridConfig = configResult.value
        assert config.routingZoneGridDimensions.columnCount == 3
        assert config.routingZoneGridDimensions.rowCount == 1
        assert config.routingZoneCount_calculate() == 3
        assert config.routingZoneInterconnectCount_calculate() == 2

    def test_routingZoneGridConfigResult_buildFromDocumentDict_reports_missing_world(
        self,
    ) -> None:
        """Missing top-level world config should produce a validation diagnostic."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict({})
        )

        assert not result_isOkCheck(configResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "config.document.missing_world"

    def test_routingZoneGridConfigResult_reports_missing_grid_and_calling_depth(
        self,
    ) -> None:
        """Omitted world.grid should require calling depth for derivation."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-implicit-horizontal.yaml")
            )
        )

        assert not result_isOkCheck(configResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert (
            diagnostics[0].code
            == "config.world.missing_grid_and_calling_depth"
        )

    def test_routingZoneGridConfigResult_buildFromDocumentDict_reports_invalid_rows(
        self,
    ) -> None:
        """Non-positive row counts should fail validation explicitly."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                {
                    "world": {
                        "sense": "west_to_east",
                        "grid": {"columns": 4, "rows": 0},
                    }
                }
            )
        )

        assert not result_isOkCheck(configResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "config.world.grid.invalid_rows"

    def test_routingZoneGridConfigResult_reports_invalid_occupancy_policy(
        self,
    ) -> None:
        """Invalid occupancy-policy values should fail validation explicitly."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                {
                    "world": {
                        "sense": "west_to_east",
                        "grid": {"columns": 2, "rows": 1},
                        "occupancy_policy": "banana",
                    }
                }
            )
        )

        assert not result_isOkCheck(configResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "config.world.invalid_occupancy_policy"

    def test_routingZoneGridConfigResult_reports_invalid_packing_policy(
        self,
    ) -> None:
        """Invalid packing-policy values should fail validation explicitly."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                {
                    "world": {
                        "sense": "west_to_east",
                        "grid": {"columns": 2, "rows": 1},
                        "packing_policy": "banana",
                    }
                }
            )
        )

        assert not result_isOkCheck(configResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "config.world.invalid_packing_policy"

    def test_routingZoneGridConfigResult_reports_invalid_module_box_padding(
        self,
    ) -> None:
        """Invalid module-box padding should fail validation explicitly."""

        diagnosticStack.stack_clear()
        configResult: Result[RoutingZoneGridConfig] = (
            routingZoneGridConfigResult_buildFromDocumentDict(
                {
                    "world": {
                        "sense": "west_to_east",
                        "grid": {"columns": 2, "rows": 1},
                        "module_box_padding": 0,
                    }
                }
            )
        )

        assert not result_isOkCheck(configResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "config.world.invalid_module_box_padding"
