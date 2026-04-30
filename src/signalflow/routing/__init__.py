"""Routing subsystem package for the new SignalFlow engine.

This package exports the clean active routing entrypoints. Legacy long-form
builder names remain in their defining modules, but they are no longer the
package-level public surface.
"""

from __future__ import annotations

from signalflow.routing.assignment import routingZoneAssignmentsResult_build
from signalflow.routing.attach import (
    chipAttachPointSetResult_buildFromPlacedZone,
)
from signalflow.routing.attach_side import (
    AttachEndpointRole,
    channelFacingTerminalSideResult_build,
    preferredTerminalSidesForEndpoint_get,
)
from signalflow.routing.chip_solver import chipInternalSolvedRoutesResult_build
from signalflow.routing.geometry import (
    chipLocalGeometryResult_build,
    chipLocalGeometrySetResult_buildFromChips,
)
from signalflow.routing.grid_solver import gridSolvedRoutesResult_build
from signalflow.routing.interconnect_solver import (
    interconnectSolvedRoutesResult_build,
)
from signalflow.routing.obligations import routeObligationsResult_build
from signalflow.routing.placement import placedRoutingZoneGridResult_build
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
from signalflow.routing.zone_solver import zoneLocalSolvedRoutesResult_build

__all__: list[str] = [
    "AttachEndpointRole",
    "EMPTY_TRACK_CELL",
    "RealizedRoute",
    "RealizedRouteCell",
    "RealizedRouteSet",
    "RouteSense",
    "TrackCell",
    "TrackDirection",
    "TrackIntent",
    "channelFacingTerminalSideResult_build",
    "chipAttachPointSetResult_buildFromPlacedZone",
    "chipInternalSolvedRoutesResult_build",
    "chipLocalGeometryResult_build",
    "chipLocalGeometrySetResult_buildFromChips",
    "glyph_resolveFromDirections",
    "gridSolvedRoutesResult_build",
    "interconnectSolvedRoutesResult_build",
    "placedRoutingZoneGridResult_build",
    "preferredTerminalSidesForEndpoint_get",
    "realizedRouteSetResult_buildFromChipInternalSolvedRouteSet",
    "realizedRouteSetResult_buildFromInterconnectSolvedRouteSet",
    "realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet",
    "routeObligationsResult_build",
    "routePoints_realize",
    "routingZoneAssignmentsResult_build",
    "routingZoneGridResult_buildFromConfig",
    "routingZoneGridResult_buildFromSignalFlowConfig",
    "trackCell_build",
    "trackCell_buildFromIntent",
    "trackCells_merge",
    "trackIntent_build",
    "trackIntents_merge",
    "zoneLocalSolvedRoutesResult_build",
]
