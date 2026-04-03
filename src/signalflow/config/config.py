"""Unified configuration models and parsing for SignalFlow.

This module defines the entire new-engine config surface in one place. It owns
both the durable config models and the YAML ingress logic so config does not
fragment across unrelated parts of the source tree.

Key components:
    - RoutingZoneGridDimensionsSource: Serialized grid-dimension source model
    - RoutingZoneGridConfigSource: Serialized world-config source model
    - RoutingZoneGridDimensions: Validated world-grid dimensions
    - RoutingZoneGridConfig: Validated world-grid config
    - SignalFlowConfigSource: Serialized top-level app-config source
    - SignalFlowConfig: Validated top-level app config
    - signalFlowConfigResult_buildFromDocumentDict: Public YAML-to-config entry
      point
"""
from __future__ import annotations

from dataclasses import dataclass

from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.routing_zone import (
    RoutingLanePackingPolicy,
    RoutingOccupancyPolicy,
    RoutingZoneChannelSense,
    RoutingZoneSense,
)
from signalflow.models.routing_zone_grid import RoutingZoneGridPathPolicy
from signalflow.config.world_size import worldGridSize_calculate


@dataclass(frozen=True)
class RoutingZoneGridDimensionsSource:
    """Serialized source model for world-grid dimensions.

    Attributes:
        columnCount: Number of zone columns declared in the world grid.
        rowCount: Number of zone rows declared in the world grid.
    """

    columnCount: int
    rowCount: int


@dataclass(frozen=True)
class RoutingZoneGridConfigSource:
    """Serialized source model for the world-grid configuration.

    Attributes:
        worldSense: Major world propagation sense.
        routingZoneGridDimensionsSource: Declared world-grid dimensions when the
            user specifies them explicitly.
        pathPolicy: Optional macro path policy.
        channelSense: Optional default zone/interconnect channel sense.
        occupancyPolicy: Optional default occupancy policy for zones/interconnects.
        packingPolicy: Optional lane-packing policy for zones/interconnects.
        moduleBoxPadding: Optional module-border padding in world cells.
    """

    worldSense: RoutingZoneSense
    routingZoneGridDimensionsSource: RoutingZoneGridDimensionsSource | None = None
    pathPolicy: RoutingZoneGridPathPolicy | None = None
    channelSense: RoutingZoneChannelSense | None = None
    occupancyPolicy: RoutingOccupancyPolicy | None = None
    packingPolicy: RoutingLanePackingPolicy | None = None
    moduleBoxPadding: int | None = None


@dataclass(frozen=True)
class RoutingZoneGridDimensions:
    """Validated world-grid dimensions.

    Attributes:
        columnCount: Number of zone columns in the world grid.
        rowCount: Number of zone rows in the world grid.
    """

    columnCount: int
    rowCount: int

    def routingZoneCount_calculate(self) -> int:
        """Calculate the number of zones in the world grid."""

        return self.columnCount * self.rowCount

    def routingZoneInterconnectCount_calculate(self) -> int:
        """Calculate the number of orthogonal neighboring interconnects."""

        horizontalInterconnectCount: int = self.rowCount * (self.columnCount - 1)
        verticalInterconnectCount: int = self.columnCount * (self.rowCount - 1)
        return horizontalInterconnectCount + verticalInterconnectCount


@dataclass(frozen=True)
class RoutingZoneGridConfig:
    """Validated world-grid config for the new engine.

    Attributes:
        worldSense: Major world propagation sense.
        routingZoneGridDimensions: Validated world-grid dimensions.
        pathPolicy: Deterministic macro path policy for world traversal.
        channelSense: Default channel-sense policy for zones and interconnects.
        occupancyPolicy: Default occupancy policy for zones and interconnects.
        packingPolicy: Default lane-packing policy for zones and interconnects.
        moduleBoxPadding: Minimum world-cell padding around module borders.
    """

    worldSense: RoutingZoneSense
    routingZoneGridDimensions: RoutingZoneGridDimensions
    pathPolicy: RoutingZoneGridPathPolicy = RoutingZoneGridPathPolicy.HORIZONTAL_FIRST
    channelSense: RoutingZoneChannelSense = RoutingZoneChannelSense.CLOCKWISE
    occupancyPolicy: RoutingOccupancyPolicy = RoutingOccupancyPolicy.STRIP
    packingPolicy: RoutingLanePackingPolicy = RoutingLanePackingPolicy.FREE
    moduleBoxPadding: int = 3

    def routingZoneCount_calculate(self) -> int:
        """Calculate the number of zones in the configured world grid."""

        return self.routingZoneGridDimensions.routingZoneCount_calculate()

    def routingZoneInterconnectCount_calculate(self) -> int:
        """Calculate the interconnect count in the configured world grid."""

        return self.routingZoneGridDimensions.routingZoneInterconnectCount_calculate()


@dataclass(frozen=True)
class SignalFlowConfigSource:
    """Serialized top-level app-config source model.

    Attributes:
        routingZoneGridConfigSource: Serialized world-grid config source.
    """

    routingZoneGridConfigSource: RoutingZoneGridConfigSource


@dataclass(frozen=True)
class SignalFlowConfig:
    """Validated top-level application config for SignalFlow.

    Attributes:
        routingZoneGridConfig: Validated world-grid config.
    """

    routingZoneGridConfig: RoutingZoneGridConfig


def routingZoneGridDimensionsResult_build(
    columnCount: int,
    rowCount: int,
) -> Result[RoutingZoneGridDimensions]:
    """Build validated world-grid dimensions.

    Args:
        columnCount: Number of zone columns in the world grid.
        rowCount: Number of zone rows in the world grid.

    Returns:
        Successful result containing `RoutingZoneGridDimensions`, otherwise
        failed result with validation diagnostics.
    """

    if columnCount <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.grid.invalid_columns",
            message="RoutingZoneGridDimensions column count must be positive",
        )
        return resultErr_build()
    if rowCount <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.grid.invalid_rows",
            message="RoutingZoneGridDimensions row count must be positive",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneGridDimensions(columnCount=columnCount, rowCount=rowCount)
    )


def routingZoneGridDimensionsForCallingDepth_build(
    worldSense: RoutingZoneSense,
    callingDepth: int,
) -> Result[RoutingZoneGridDimensions]:
    """Build simple-regime grid dimensions from calling depth."""

    if callingDepth < 1:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_calling_depth",
            message=(
                "Calling depth must be at least 1 to derive routing-zone "
                "dimensions"
            ),
        )
        return resultErr_build()

    routingZoneCount: int = worldGridSize_calculate(callingDepth)
    if worldSense is RoutingZoneSense.WEST_TO_EAST:
        return routingZoneGridDimensionsResult_build(
            columnCount=routingZoneCount,
            rowCount=1,
        )
    return routingZoneGridDimensionsResult_build(
        columnCount=1,
        rowCount=routingZoneCount,
    )


def routingZoneGridConfig_buildFromSource(
    configSource: RoutingZoneGridConfigSource,
) -> Result[RoutingZoneGridConfig]:
    """Build a validated world-grid config from a typed source config."""

    if configSource.routingZoneGridDimensionsSource is None:
        return resultErr_build()
    routingZoneGridDimensionsResult: Result[RoutingZoneGridDimensions] = (
        routingZoneGridDimensionsResult_build(
            columnCount=configSource.routingZoneGridDimensionsSource.columnCount,
            rowCount=configSource.routingZoneGridDimensionsSource.rowCount,
        )
    )
    if not result_isOkCheck(routingZoneGridDimensionsResult):
        return resultErr_build()

    return resultOk_build(
        RoutingZoneGridConfig(
            worldSense=configSource.worldSense,
            routingZoneGridDimensions=routingZoneGridDimensionsResult.value,
            pathPolicy=(
                configSource.pathPolicy or RoutingZoneGridPathPolicy.HORIZONTAL_FIRST
            ),
            channelSense=(
                configSource.channelSense or RoutingZoneChannelSense.CLOCKWISE
            ),
            occupancyPolicy=(
                configSource.occupancyPolicy or RoutingOccupancyPolicy.STRIP
            ),
            packingPolicy=(
                configSource.packingPolicy or RoutingLanePackingPolicy.FREE
            ),
            moduleBoxPadding=configSource.moduleBoxPadding or 3,
        )
    )


def routingZoneGridConfigForCallingDepth_build(
    configSource: RoutingZoneGridConfigSource,
    callingDepth: int,
) -> Result[RoutingZoneGridConfig]:
    """Build a validated world-grid config using a derived simple-regime grid."""

    routingZoneGridDimensionsResult: Result[RoutingZoneGridDimensions]
    if configSource.routingZoneGridDimensionsSource is None:
        routingZoneGridDimensionsResult = (
            routingZoneGridDimensionsForCallingDepth_build(
                worldSense=configSource.worldSense,
                callingDepth=callingDepth,
            )
        )
    else:
        routingZoneGridDimensionsResult = routingZoneGridDimensionsResult_build(
            columnCount=configSource.routingZoneGridDimensionsSource.columnCount,
            rowCount=configSource.routingZoneGridDimensionsSource.rowCount,
        )
    if not result_isOkCheck(routingZoneGridDimensionsResult):
        return resultErr_build()

    return resultOk_build(
        RoutingZoneGridConfig(
            worldSense=configSource.worldSense,
            routingZoneGridDimensions=routingZoneGridDimensionsResult.value,
            pathPolicy=(
                configSource.pathPolicy or RoutingZoneGridPathPolicy.HORIZONTAL_FIRST
            ),
            channelSense=(
                configSource.channelSense or RoutingZoneChannelSense.CLOCKWISE
            ),
            occupancyPolicy=(
                configSource.occupancyPolicy or RoutingOccupancyPolicy.STRIP
            ),
            packingPolicy=(
                configSource.packingPolicy or RoutingLanePackingPolicy.FREE
            ),
            moduleBoxPadding=configSource.moduleBoxPadding or 3,
        )
    )


def signalFlowConfigSource_buildFromRoutingSource(
    routingZoneGridConfigSource: RoutingZoneGridConfigSource,
) -> SignalFlowConfigSource:
    """Build top-level app-config source from world-grid config source."""

    return SignalFlowConfigSource(
        routingZoneGridConfigSource=routingZoneGridConfigSource,
    )


def signalFlowConfig_buildFromSource(
    configSource: SignalFlowConfigSource,
    callingDepth: int | None = None,
) -> Result[SignalFlowConfig]:
    """Build validated app config from top-level source config."""

    routingZoneGridConfigResult: Result[RoutingZoneGridConfig]
    if configSource.routingZoneGridConfigSource.routingZoneGridDimensionsSource is None:
        if callingDepth is None:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="config.missing_calling_depth",
                message=(
                    "SignalFlowConfig requires callingDepth when 'world.grid' is "
                    "omitted"
                ),
            )
            return resultErr_build()
        routingZoneGridConfigResult = routingZoneGridConfigForCallingDepth_build(
            configSource=configSource.routingZoneGridConfigSource,
            callingDepth=callingDepth,
        )
    else:
        routingZoneGridConfigResult = routingZoneGridConfig_buildFromSource(
            configSource.routingZoneGridConfigSource
        )
    if not result_isOkCheck(routingZoneGridConfigResult):
        return resultErr_build()

    return resultOk_build(
        SignalFlowConfig(routingZoneGridConfig=routingZoneGridConfigResult.value)
    )


def routingZoneGridConfigSourceResult_buildFromDocumentDict(
    documentDict: dict[str, object],
) -> Result[RoutingZoneGridConfigSource]:
    """Build a typed world-grid config source model from YAML-shaped input."""

    worldValue: object | None = documentDict.get("world")
    if worldValue is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.document.missing_world",
            message="Document must define a top-level 'world' section",
        )
        return resultErr_build()
    if not isinstance(worldValue, dict):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid",
            message="'world' must be a dictionary",
        )
        return resultErr_build()

    worldDict: dict[str, object] = worldValue
    worldSenseResult = _routingZoneSenseResult_buildFromWorldDict(worldDict)
    if not result_isOkCheck(worldSenseResult):
        return resultErr_build()

    dimensionsSourceResult = _routingZoneGridDimensionsSourceResult_buildFromWorldDict(
        worldDict
    )
    if not result_isOkCheck(dimensionsSourceResult):
        return resultErr_build()

    pathPolicyResult = _routingZoneGridPathPolicyResult_buildFromWorldDict(worldDict)
    if not result_isOkCheck(pathPolicyResult):
        return resultErr_build()

    channelSenseResult = _routingZoneChannelSenseResult_buildFromWorldDict(worldDict)
    if not result_isOkCheck(channelSenseResult):
        return resultErr_build()
    occupancyPolicyResult = _routingOccupancyPolicyResult_buildFromWorldDict(worldDict)
    if not result_isOkCheck(occupancyPolicyResult):
        return resultErr_build()
    packingPolicyResult = _routingLanePackingPolicyResult_buildFromWorldDict(worldDict)
    if not result_isOkCheck(packingPolicyResult):
        return resultErr_build()
    moduleBoxPaddingResult = _moduleBoxPaddingResult_buildFromWorldDict(worldDict)
    if not result_isOkCheck(moduleBoxPaddingResult):
        return resultErr_build()

    return resultOk_build(
        RoutingZoneGridConfigSource(
            worldSense=worldSenseResult.value,
            routingZoneGridDimensionsSource=dimensionsSourceResult.value,
            pathPolicy=pathPolicyResult.value,
            channelSense=channelSenseResult.value,
            occupancyPolicy=occupancyPolicyResult.value,
            packingPolicy=packingPolicyResult.value,
            moduleBoxPadding=moduleBoxPaddingResult.value,
        )
    )


def signalFlowConfigSourceResult_buildFromDocumentDict(
    documentDict: dict[str, object],
) -> Result[SignalFlowConfigSource]:
    """Build top-level app-config source from YAML-shaped input."""

    routingZoneGridConfigSourceResult: Result[RoutingZoneGridConfigSource] = (
        routingZoneGridConfigSourceResult_buildFromDocumentDict(documentDict)
    )
    if not result_isOkCheck(routingZoneGridConfigSourceResult):
        return resultErr_build()

    return resultOk_build(
        signalFlowConfigSource_buildFromRoutingSource(
            routingZoneGridConfigSourceResult.value
        )
    )


def routingZoneGridConfigResult_buildFromDocumentDict(
    documentDict: dict[str, object],
    callingDepth: int | None = None,
) -> Result[RoutingZoneGridConfig]:
    """Build a validated world-grid config from YAML-shaped input."""

    configSourceResult: Result[RoutingZoneGridConfigSource] = (
        routingZoneGridConfigSourceResult_buildFromDocumentDict(documentDict)
    )
    if not result_isOkCheck(configSourceResult):
        return resultErr_build()

    configSource: RoutingZoneGridConfigSource = configSourceResult.value
    if configSource.routingZoneGridDimensionsSource is None:
        if callingDepth is None:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="config.world.missing_grid_and_calling_depth",
                message=(
                    "When 'world.grid' is omitted, callingDepth must be provided "
                    "to derive the simple world regime"
                ),
            )
            return resultErr_build()
        return routingZoneGridConfigForCallingDepth_build(
            configSource=configSource,
            callingDepth=callingDepth,
        )

    return routingZoneGridConfig_buildFromSource(configSource)


def signalFlowConfigResult_buildFromDocumentDict(
    documentDict: dict[str, object],
    callingDepth: int | None = None,
) -> Result[SignalFlowConfig]:
    """Build validated top-level app config from YAML-shaped input."""

    configSourceResult: Result[SignalFlowConfigSource] = (
        signalFlowConfigSourceResult_buildFromDocumentDict(documentDict)
    )
    if not result_isOkCheck(configSourceResult):
        return resultErr_build()

    return signalFlowConfig_buildFromSource(
        configSource=configSourceResult.value,
        callingDepth=callingDepth,
    )


def _routingZoneSenseResult_buildFromWorldDict(
    worldDict: dict[str, object],
) -> Result[RoutingZoneSense]:
    """Build the world sense from a `world` dictionary."""

    senseValue: object | None = worldDict.get("sense")
    if not isinstance(senseValue, str):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.missing_sense",
            message="'world.sense' must be a string",
        )
        return resultErr_build()

    allowedSenseValues: set[str] = {
        routingZoneSense.value for routingZoneSense in RoutingZoneSense
    }
    if senseValue not in allowedSenseValues:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_sense",
            message="'world.sense' must be one of: west_to_east, north_to_south",
        )
        return resultErr_build()
    return resultOk_build(RoutingZoneSense(senseValue))


def _routingZoneGridDimensionsSourceResult_buildFromWorldDict(
    worldDict: dict[str, object],
) -> Result[RoutingZoneGridDimensionsSource | None]:
    """Build the serialized grid-dimension source model from `world`."""

    gridValue: object | None = worldDict.get("grid")
    if gridValue is None:
        return resultOk_build(None)
    if not isinstance(gridValue, dict):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_grid",
            message="'world.grid' must be a dictionary when provided",
        )
        return resultErr_build()

    gridDict: dict[str, object] = gridValue
    columnCountResult = _positiveIntResult_buildFromDictValue(
        sourceDict=gridDict,
        fieldName="columns",
        diagnosticCode="config.world.grid.invalid_columns",
    )
    if not result_isOkCheck(columnCountResult):
        return resultErr_build()

    rowCountResult = _positiveIntResult_buildFromDictValue(
        sourceDict=gridDict,
        fieldName="rows",
        diagnosticCode="config.world.grid.invalid_rows",
    )
    if not result_isOkCheck(rowCountResult):
        return resultErr_build()

    return resultOk_build(
        RoutingZoneGridDimensionsSource(
            columnCount=columnCountResult.value,
            rowCount=rowCountResult.value,
        )
    )


def _routingZoneGridPathPolicyResult_buildFromWorldDict(
    worldDict: dict[str, object],
) -> Result[RoutingZoneGridPathPolicy | None]:
    """Build the optional path policy from `world`."""

    pathPolicyValue: object | None = worldDict.get("path_policy")
    if pathPolicyValue is None:
        return resultOk_build(None)
    if not isinstance(pathPolicyValue, str):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_path_policy",
            message="'world.path_policy' must be a string when provided",
        )
        return resultErr_build()

    if pathPolicyValue not in {
        routingZoneGridPathPolicy.value
        for routingZoneGridPathPolicy in RoutingZoneGridPathPolicy
    }:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_path_policy",
            message=(
                "'world.path_policy' must be one of: "
                "horizontal_first, vertical_first"
            ),
        )
        return resultErr_build()
    return resultOk_build(RoutingZoneGridPathPolicy(pathPolicyValue))


def _routingZoneChannelSenseResult_buildFromWorldDict(
    worldDict: dict[str, object],
) -> Result[RoutingZoneChannelSense | None]:
    """Build the optional channel sense from `world`."""

    channelSenseValue: object | None = worldDict.get("channel_sense")
    if channelSenseValue is None:
        return resultOk_build(None)
    if not isinstance(channelSenseValue, str):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_channel_sense",
            message="'world.channel_sense' must be a string when provided",
        )
        return resultErr_build()

    if channelSenseValue not in {
        routingZoneChannelSense.value
        for routingZoneChannelSense in RoutingZoneChannelSense
    }:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_channel_sense",
            message=(
                "'world.channel_sense' must be one of: "
                "clockwise, anticlockwise"
            ),
        )
        return resultErr_build()
    return resultOk_build(RoutingZoneChannelSense(channelSenseValue))


def _routingOccupancyPolicyResult_buildFromWorldDict(
    worldDict: dict[str, object],
) -> Result[RoutingOccupancyPolicy]:
    """Build the optional occupancy policy from `world`."""

    occupancyPolicyValue: object | None = worldDict.get("occupancy_policy")
    if occupancyPolicyValue is None:
        return resultOk_build(RoutingOccupancyPolicy.STRIP)
    if not isinstance(occupancyPolicyValue, str):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_occupancy_policy",
            message="'world.occupancy_policy' must be a string when provided",
        )
        return resultErr_build()

    if occupancyPolicyValue not in {
        routingOccupancyPolicy.value
        for routingOccupancyPolicy in RoutingOccupancyPolicy
    }:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_occupancy_policy",
            message="'world.occupancy_policy' must be one of: cell, strip",
        )
        return resultErr_build()

    return resultOk_build(RoutingOccupancyPolicy(occupancyPolicyValue))


def _routingLanePackingPolicyResult_buildFromWorldDict(
    worldDict: dict[str, object],
) -> Result[RoutingLanePackingPolicy]:
    """Build the optional lane-packing policy from `world`."""

    packingPolicyValue: object | None = worldDict.get("packing_policy")
    if packingPolicyValue is None:
        return resultOk_build(RoutingLanePackingPolicy.FREE)
    if not isinstance(packingPolicyValue, str):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_packing_policy",
            message="'world.packing_policy' must be a string when provided",
        )
        return resultErr_build()

    if packingPolicyValue not in {
        routingLanePackingPolicy.value
        for routingLanePackingPolicy in RoutingLanePackingPolicy
    }:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_packing_policy",
            message="'world.packing_policy' must be one of: free, monotone",
        )
        return resultErr_build()

    return resultOk_build(RoutingLanePackingPolicy(packingPolicyValue))


def _moduleBoxPaddingResult_buildFromWorldDict(
    worldDict: dict[str, object],
) -> Result[int | None]:
    """Build the optional module-border padding from `world`."""

    moduleBoxPaddingValue: object | None = worldDict.get("module_box_padding")
    if moduleBoxPaddingValue is None:
        return resultOk_build(None)
    if not isinstance(moduleBoxPaddingValue, int) or isinstance(
        moduleBoxPaddingValue, bool
    ):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_module_box_padding",
            message="'world.module_box_padding' must be an integer when provided",
        )
        return resultErr_build()
    if moduleBoxPaddingValue <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="config.world.invalid_module_box_padding",
            message="'world.module_box_padding' must be positive",
        )
        return resultErr_build()
    return resultOk_build(moduleBoxPaddingValue)


def _positiveIntResult_buildFromDictValue(
    sourceDict: dict[str, object],
    fieldName: str,
    diagnosticCode: str,
) -> Result[int]:
    """Build a positive integer from one dictionary field."""

    fieldValue: object | None = sourceDict.get(fieldName)
    if not isinstance(fieldValue, int) or isinstance(fieldValue, bool):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code=diagnosticCode,
            message=f"'{fieldName}' must be an integer",
        )
        return resultErr_build()
    if fieldValue <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code=diagnosticCode,
            message=f"'{fieldName}' must be positive",
        )
        return resultErr_build()
    return resultOk_build(fieldValue)
