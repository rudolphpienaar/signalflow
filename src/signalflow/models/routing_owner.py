"""Routing-substrate ownership models for SignalFlow.

This module defines the world-level owner id used by routing artifacts that
address a routing zone, and the concrete chip-local routing owner used by
chip-internal routing artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.models.chip import ChipId, ChipRef
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import Result, resultErr_build, resultOk_build
from signalflow.models.routing_zone import RoutingZoneId


@dataclass(frozen=True)
class RoutingOwnerId:
    """Stable identifier for one world routing-substrate owner.

    Attributes:
        id: One world-scoped `RoutingZoneId`.
    """

    id: RoutingZoneId

    def routingZoneIdResult_get(self) -> Result[RoutingZoneId]:
        """Build the world routing-zone owner id when present."""

        if isinstance(self.id, RoutingZoneId):
            return resultOk_build(self.id)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.owner.id.missing_routing_zone_address",
            message="RoutingOwnerId does not address a world routing zone",
        )
        return resultErr_build()

    def routingZoneAddress_isPresentCheck(self) -> bool:
        """Return whether this owner id addresses a world routing zone."""

        return isinstance(self.id, RoutingZoneId)


@dataclass(frozen=True)
class ChipLocalRoutingOwner:
    """Concrete chip-local routing owner.

    Attributes:
        chipRef: Stable reference to the chip that owns the local routing
            substrate.
    """

    chipRef: ChipRef

    def chipId_get(self) -> ChipId:
        """Return the owning chip id."""

        return self.chipRef.chipId


def chipLocalRoutingOwner_build(chipRef: ChipRef) -> ChipLocalRoutingOwner:
    """Build one concrete chip-local routing owner from a chip ref."""

    return ChipLocalRoutingOwner(chipRef=chipRef)
