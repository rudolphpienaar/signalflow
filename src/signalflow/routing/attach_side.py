"""Shared attach-side helpers for routing substrates."""

from __future__ import annotations

from enum import Enum

from signalflow.models import (
    Chip,
    ChipTerminalSide,
    Result,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


class AttachEndpointRole(Enum):
    """Endpoint role when resolving attach-side preferences."""

    SOURCE = "source"
    DESTINATION = "destination"


def preferredTerminalSidesForEndpoint_get(
    chip: Chip,
    terminalName: str,
    endpointRole: AttachEndpointRole,
) -> tuple[ChipTerminalSide, ...]:
    """Return preferred terminal sides for one chip endpoint role."""

    preferredSidesMutable: list[ChipTerminalSide] = []
    if endpointRole is AttachEndpointRole.SOURCE:
        for portDeclaration in chip.inputPortDeclarationSet.portDeclarations:
            if terminalName in (
                portDeclaration.signalName,
                portDeclaration.returnName,
            ):
                preferredSidesMutable.append(ChipTerminalSide.WEST)
    else:
        for portDeclaration in chip.outputPortDeclarationSet.portDeclarations:
            if terminalName in (
                portDeclaration.signalName,
                portDeclaration.returnName,
            ):
                preferredSidesMutable.append(ChipTerminalSide.EAST)
    return tuple(dict.fromkeys(preferredSidesMutable))


def channelFacingTerminalSideResult_build(
    routingZoneSense: RoutingZoneSense,
    regionSide: RoutingZoneRegionSide,
) -> Result[ChipTerminalSide]:
    """Build the chip-terminal side that faces the routing channel."""

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        if regionSide is RoutingZoneRegionSide.WEST:
            return resultOk_build(ChipTerminalSide.EAST)
        if regionSide is RoutingZoneRegionSide.EAST:
            return resultOk_build(ChipTerminalSide.WEST)
    else:
        if regionSide is RoutingZoneRegionSide.NORTH:
            return resultOk_build(ChipTerminalSide.SOUTH)
        if regionSide is RoutingZoneRegionSide.SOUTH:
            return resultOk_build(ChipTerminalSide.NORTH)

    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.attach_side.invalid_region_side_for_zone_sense",
        message=(
            "Routing zone side does not expose a channel-facing chip terminal "
            "side for the zone sense"
        ),
        context=(routingZoneSense.value, regionSide.value),
    )
    return resultErr_build()
