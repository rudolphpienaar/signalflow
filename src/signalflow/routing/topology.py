"""Topology builders for the new SignalFlow routing world.

This module turns validated configuration into an empty `RoutingZoneGrid`
topology skeleton. The builder owns only world topology materialization:
zone identities, orthogonal neighboring interconnects, and default geometry
placeholders. It does not place chips or solve routes.
"""
from __future__ import annotations

from signalflow.config import RoutingZoneGridConfig, SignalFlowConfig
from signalflow.models import (
    GridCoord,
    Result,
    RoutingZone,
    RoutingZoneGrid,
    RoutingZoneId,
    RoutingZoneInterconnect,
    RoutingZoneInterconnectId,
    RoutingZoneInterconnectSet,
    RoutingZoneSet,
    result_isOkCheck,
    resultErr_build,
    routingZoneGridResult_build,
    routingZoneInterconnectResult_build,
    routingZoneInterconnectSetResult_build,
    routingZoneResult_build,
    routingZoneSetResult_build,
)


def routingZoneGridResult_buildFromConfig(
    routingZoneGridConfig: RoutingZoneGridConfig,
) -> Result[RoutingZoneGrid]:
    """Build an empty routing-zone-grid skeleton from world config.

    Args:
        routingZoneGridConfig: Validated world-grid config.

    Returns:
        Successful result containing an empty `RoutingZoneGrid` skeleton, or a
        failed result when one of the modeled topology components fails to build.
    """

    routingZoneSetResult: Result[RoutingZoneSet] = routingZoneSetResult_build(
        routingZones=_routingZones_build(routingZoneGridConfig)
    )
    if not result_isOkCheck(routingZoneSetResult):
        return resultErr_build()

    routingZoneInterconnectSetResult: Result[RoutingZoneInterconnectSet] = (
        routingZoneInterconnectSetResult_build(
            routingZoneInterconnects=_routingZoneInterconnects_build(
                routingZoneGridConfig
            )
        )
    )
    if not result_isOkCheck(routingZoneInterconnectSetResult):
        return resultErr_build()

    return routingZoneGridResult_build(
        worldSense=routingZoneGridConfig.worldSense,
        gridSize=GridCoord(
            columnIndex=routingZoneGridConfig.routingZoneGridDimensions.columnCount,
            rowIndex=routingZoneGridConfig.routingZoneGridDimensions.rowCount,
        ),
        routingZoneSet=routingZoneSetResult.value,
        moduleBoxPadding=routingZoneGridConfig.moduleBoxPadding,
        routingZoneInterconnectSet=routingZoneInterconnectSetResult.value,
    )


def routingZoneGridResult_buildFromSignalFlowConfig(
    signalFlowConfig: SignalFlowConfig,
) -> Result[RoutingZoneGrid]:
    """Build an empty routing-zone-grid skeleton from top-level app config.

    Args:
        signalFlowConfig: Validated top-level app config.

    Returns:
        Successful result containing an empty `RoutingZoneGrid` skeleton, or a
        failed result when one of the modeled topology components fails to build.
    """

    return routingZoneGridResult_buildFromConfig(
        signalFlowConfig.routingZoneGridConfig
    )


def _routingZones_build(
    routingZoneGridConfig: RoutingZoneGridConfig,
) -> tuple[RoutingZone, ...]:
    """Build the empty routing zones for one configured world."""

    routingZonesMutable: list[RoutingZone] = []
    rowIndex: int
    columnIndex: int
    for rowIndex in range(
        1,
        routingZoneGridConfig.routingZoneGridDimensions.rowCount + 1,
    ):
        for columnIndex in range(
            1,
            routingZoneGridConfig.routingZoneGridDimensions.columnCount + 1,
        ):
            routingZoneResult: Result[RoutingZone] = routingZoneResult_build(
                routingZoneId=RoutingZoneId(
                    id=GridCoord(
                        columnIndex=columnIndex,
                        rowIndex=rowIndex,
                    )
                ),
                routingZoneSense=routingZoneGridConfig.worldSense,
                channelSense=routingZoneGridConfig.channelSense,
                occupancyPolicy=routingZoneGridConfig.occupancyPolicy,
                packingPolicy=routingZoneGridConfig.packingPolicy,
            )
            assert result_isOkCheck(routingZoneResult)
            routingZonesMutable.append(routingZoneResult.value)
    return tuple(routingZonesMutable)


def _routingZoneInterconnects_build(
    routingZoneGridConfig: RoutingZoneGridConfig,
) -> tuple[RoutingZoneInterconnect, ...]:
    """Build all orthogonal neighboring interconnects for one world."""

    routingZoneInterconnectsMutable: list[RoutingZoneInterconnect] = []
    rowCount: int = routingZoneGridConfig.routingZoneGridDimensions.rowCount
    columnCount: int = routingZoneGridConfig.routingZoneGridDimensions.columnCount

    rowIndex: int
    columnIndex: int
    for rowIndex in range(1, rowCount + 1):
        for columnIndex in range(1, columnCount):
            sourceZoneId: RoutingZoneId = RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            )
            destinationZoneId: RoutingZoneId = RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex + 1, rowIndex=rowIndex)
            )
            routingZoneInterconnectResult: Result[RoutingZoneInterconnect] = (
                routingZoneInterconnectResult_build(
                    routingZoneInterconnectId=RoutingZoneInterconnectId(
                        sourceZoneId=sourceZoneId,
                        destinationZoneId=destinationZoneId,
                    ),
                    sourceZoneId=sourceZoneId,
                    destinationZoneId=destinationZoneId,
                    channelSense=routingZoneGridConfig.channelSense,
                    occupancyPolicy=routingZoneGridConfig.occupancyPolicy,
                    packingPolicy=routingZoneGridConfig.packingPolicy,
                )
            )
            assert result_isOkCheck(routingZoneInterconnectResult)
            routingZoneInterconnectsMutable.append(
                routingZoneInterconnectResult.value
            )

    for columnIndex in range(1, columnCount + 1):
        for rowIndex in range(1, rowCount):
            sourceZoneId = RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            )
            destinationZoneId = RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex + 1)
            )
            routingZoneInterconnectResult = routingZoneInterconnectResult_build(
                routingZoneInterconnectId=RoutingZoneInterconnectId(
                    sourceZoneId=sourceZoneId,
                    destinationZoneId=destinationZoneId,
                ),
                sourceZoneId=sourceZoneId,
                destinationZoneId=destinationZoneId,
                channelSense=routingZoneGridConfig.channelSense,
                occupancyPolicy=routingZoneGridConfig.occupancyPolicy,
                packingPolicy=routingZoneGridConfig.packingPolicy,
            )
            assert result_isOkCheck(routingZoneInterconnectResult)
            routingZoneInterconnectsMutable.append(
                routingZoneInterconnectResult.value
            )

    return tuple(routingZoneInterconnectsMutable)
