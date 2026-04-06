"""Unified configuration boundary for SignalFlow.

This package owns the single public configuration ingress for the new engine
line. Config models and config parsing live together here so the repo does not
grow multiple competing config stories across `models/`, `routing/`, and
`settings/`.

Key components:
    - SignalFlowConfig: Validated top-level application config
    - SignalFlowConfigSource: Serialized top-level app-config source
    - RoutingZoneGridConfig: Validated world-grid config
    - RoutingZoneGridConfigSource: Serialized world-grid config source
    - configResult_build: Public YAML-to-config entry point
"""

from __future__ import annotations

from signalflow.config.board_defaults import (
    BoardGeometryConfig,
    boardGeometryConfig,
    boardGeometryConfig_load,
)
from signalflow.config.config import (
    RoutingLanePackingPolicy,
    RoutingOccupancyPolicy,
    RoutingZoneGridConfig,
    RoutingZoneGridConfigSource,
    RoutingZoneGridDimensions,
    RoutingZoneGridDimensionsSource,
    SignalFlowConfig,
    SignalFlowConfigSource,
    config_build,
    configResult_build,
    configSource_build,
    configSourceResult_build,
    routingZoneGridConfig_build,
    routingZoneGridConfigByCallingDepth_build,
    routingZoneGridConfigResult_build,
    routingZoneGridConfigSourceResult_build,
    routingZoneGridDimensionsByCallingDepth_build,
    routingZoneGridDimensionsResult_build,
)
from signalflow.config.world_size import worldGridSize_calculate

__all__: list[str] = [
    "BoardGeometryConfig",
    "boardGeometryConfig",
    "boardGeometryConfig_load",
    "RoutingLanePackingPolicy",
    "RoutingOccupancyPolicy",
    "RoutingZoneGridConfig",
    "RoutingZoneGridConfigSource",
    "RoutingZoneGridDimensions",
    "RoutingZoneGridDimensionsSource",
    "SignalFlowConfig",
    "SignalFlowConfigSource",
    "configResult_build",
    "configSourceResult_build",
    "configSource_build",
    "config_build",
    "routingZoneGridDimensionsResult_build",
    "routingZoneGridConfigByCallingDepth_build",
    "routingZoneGridConfigResult_build",
    "routingZoneGridConfigSourceResult_build",
    "routingZoneGridConfig_build",
    "routingZoneGridDimensionsByCallingDepth_build",
    "worldGridSize_calculate",
]
