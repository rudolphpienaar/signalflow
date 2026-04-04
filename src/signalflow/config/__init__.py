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
    - signalFlowConfigResult_buildFromDocumentDict: Public YAML-to-config entry
      point
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
    routingZoneGridConfigForCallingDepth_build,
    routingZoneGridConfigResult_buildFromDocumentDict,
    routingZoneGridConfigSourceResult_buildFromDocumentDict,
    routingZoneGridDimensionsForCallingDepth_build,
    routingZoneGridDimensionsResult_build,
    signalFlowConfigResult_buildFromDocumentDict,
    signalFlowConfigSourceResult_buildFromDocumentDict,
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
    "routingZoneGridDimensionsResult_build",
    "routingZoneGridConfigForCallingDepth_build",
    "routingZoneGridConfigResult_buildFromDocumentDict",
    "routingZoneGridConfigSourceResult_buildFromDocumentDict",
    "routingZoneGridDimensionsForCallingDepth_build",
    "signalFlowConfigResult_buildFromDocumentDict",
    "signalFlowConfigSourceResult_buildFromDocumentDict",
    "worldGridSize_calculate",
]
