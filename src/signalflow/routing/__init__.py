"""Routing subsystem package for the new SignalFlow engine.

This package is reserved for routing-specific algorithms such as classification,
solvers, geometry, and track algebra. Configuration now lives centrally in
`signalflow.config`.
"""
from __future__ import annotations

from signalflow.routing.assignment import (
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
)
from signalflow.routing.obligations import (
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
)
from signalflow.routing.placement import (
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
)
from signalflow.routing.topology import (
    routingZoneGridResult_buildFromConfig,
    routingZoneGridResult_buildFromSignalFlowConfig,
)

__all__: list[str] = [
    "routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid",
    "routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid",
    "routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid",
    "routingZoneGridResult_buildFromConfig",
    "routingZoneGridResult_buildFromSignalFlowConfig",
]
