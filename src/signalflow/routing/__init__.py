"""Routing subsystem package for the new SignalFlow engine.

This package is reserved for routing-specific algorithms such as classification,
solvers, geometry, and track algebra. Configuration now lives centrally in
`signalflow.config`.
"""

from __future__ import annotations

from signalflow.routing.assignment import (
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
)
from signalflow.routing.attach import (
    chipAttachPointSetResult_buildFromPlacedZone,
)
from signalflow.routing.attach_side import (
    AttachEndpointRole,
    channelFacingTerminalSideResult_build,
    preferredTerminalSidesForEndpoint_get,
)
from signalflow.routing.chip_solver import (
    chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet,
)
from signalflow.routing.geometry import (
    chipLocalGeometryResult_build,
    chipLocalGeometrySetResult_buildFromChips,
)
from signalflow.routing.grid_solver import (
    routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)
from signalflow.routing.interconnect_solver import (
    routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)
from signalflow.routing.obligations import (
    routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid,
)
from signalflow.routing.placement import (
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
)
from signalflow.routing.route import (
    RealizedRoute,
    RealizedRouteCell,
    RealizedRouteSet,
    RouteSense,
    realizedRouteSetResult_buildFromChipInternalSolvedRouteSet,
    realizedRouteSetResult_buildFromInterconnectSolvedRouteSet,
    realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet,
    routePoints_realize,
)
from signalflow.routing.topology import (
    routingZoneGridResult_buildFromConfig,
    routingZoneGridResult_buildFromSignalFlowConfig,
)
from signalflow.routing.track import (
    EMPTY_TRACK_CELL,
    TrackCell,
    TrackDirection,
    TrackIntent,
    glyph_resolveFromDirections,
    trackCell_build,
    trackCell_buildFromIntent,
    trackCells_merge,
    trackIntent_build,
    trackIntents_merge,
)
from signalflow.routing.zone_solver import (
    routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations,
)

__all__: list[str] = [
    "routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid",
    "AttachEndpointRole",
    "channelFacingTerminalSideResult_build",
    "chipAttachPointSetResult_buildFromPlacedZone",
    "chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet",
    "chipLocalGeometryResult_build",
    "chipLocalGeometrySetResult_buildFromChips",
    "preferredTerminalSidesForEndpoint_get",
    "routeObligationSetResult_buildFromCircuitDocumentAndPlacedGrid",
    "routingZoneGridSolvedRouteSetResult_buildFromPlacedGridAndObligations",
    "routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid",
    "routingZoneInterconnectSolvedRouteSetResult_buildFromPlacedGridAndObligations",
    "routingZoneGridResult_buildFromConfig",
    "routingZoneGridResult_buildFromSignalFlowConfig",
    "routingZoneLocalSolvedRouteSetResult_buildFromPlacedGridAndObligations",
    "RealizedRoute",
    "RealizedRouteCell",
    "RealizedRouteSet",
    "RouteSense",
    "realizedRouteSetResult_buildFromChipInternalSolvedRouteSet",
    "realizedRouteSetResult_buildFromInterconnectSolvedRouteSet",
    "realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet",
    "routePoints_realize",
    "EMPTY_TRACK_CELL",
    "TrackCell",
    "TrackDirection",
    "TrackIntent",
    "glyph_resolveFromDirections",
    "trackCell_build",
    "trackCell_buildFromIntent",
    "trackCells_merge",
    "trackIntent_build",
    "trackIntents_merge",
]
