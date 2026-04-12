"""Routing-zone models for SignalFlow.

This module defines the atomic local routing block vocabulary for the new
routing-zone architecture.

Key components:
    - GridCoord: Typed world-grid coordinate for inter-chip routing zones
    - RoutingZoneSense: Major information-propagation sense for a zone
    - RoutingZoneChannelSense: Travel policy for zone/interconnect channels
    - RoutingZoneRegionKind: Canonical owned region kinds inside a zone
    - RoutingZoneRegionSide: Cardinal side for sided zone regions
    - RoutingZoneFrame: Solved outer frame for one routing zone
    - RoutingZoneRegionFrame: Solved frame for one owned zone region
    - RoutingZoneRegionId: Stable identity for one owned zone region
    - RoutingZoneRegion: One explicit owned region inside a routing zone
    - RoutingZoneRegionSet: Modeled collection of owned zone regions
    - RoutingZoneId: Stable identifier for one zone position
    - ChipPlacement: Placement of one chip inside one zone
    - ChipPlacementSet: Modeled collection of local chip placements
    - RoutingZone: Atomic local routing block
    - RoutingZoneInterconnectAxis: Orientation of one zone-to-zone seam
    - RoutingZoneInterconnectFrame: Solved outer frame for one interconnect
    - RoutingZoneInterconnectId: Stable identity for one interconnect
    - RoutingZoneInterconnect: Continuity mediator between two zones
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from signalflow.models.cardinal_side import CardinalSide
from signalflow.models.chip import ChipRef
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)

if TYPE_CHECKING:
    from signalflow.models.route_obligation import CallRouteObligation


class RoutingZoneSense(Enum):
    """Major information-propagation sense for one routing zone.

    Attributes:
        WEST_TO_EAST: Information propagates from west terminal region to east.
        NORTH_TO_SOUTH: Information propagates from north terminal region to south.
    """

    WEST_TO_EAST = "west_to_east"
    NORTH_TO_SOUTH = "north_to_south"


class RoutingZoneChannelSense(Enum):
    """Travel policy for routing-zone and interconnect channels.

    Attributes:
        CLOCKWISE: Prefer clockwise travel in longitude/latitude channels.
        ANTICLOCKWISE: Prefer anti-clockwise travel in longitude/latitude channels.
    """

    CLOCKWISE = "clockwise"
    ANTICLOCKWISE = "anticlockwise"


class RoutingOccupancyPolicy(Enum):
    """Occupancy doctrine for routing-channel reservation."""

    CELL = "cell"
    STRIP = "strip"


class RoutingLanePackingPolicy(Enum):
    """Lane-packing doctrine for routing-channel allocation."""

    FREE = "free"
    MONOTONE = "monotone"


class RoutingLaneAttachmentSense(Enum):
    """Lane-pick direction inside one routing channel or edge band."""

    FROM_START = "from_start"
    FROM_END = "from_end"


@dataclass(frozen=True)
class RoutingZoneAttachmentPolicy:
    """Fine-grained lane-pick policy for one routing substrate."""

    westEdge: RoutingLaneAttachmentSense = RoutingLaneAttachmentSense.FROM_END
    eastEdge: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_START
    )
    northEdge: RoutingLaneAttachmentSense = RoutingLaneAttachmentSense.FROM_END
    southEdge: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_START
    )
    westTransversalInChannel: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_START
    )
    eastTransversalInChannel: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_END
    )
    northTransversalInChannel: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_START
    )
    southTransversalInChannel: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_END
    )


class RoutingZoneRegionKind(Enum):
    """Canonical owned region kinds inside a routing zone.

    Attributes:
        CHIP_TERMINAL: Terminal band that owns placed chips for one sided boundary.
        INTRA_ROUTING_FAN_IN_OUT: Local fan-in/fan-out region between chips and
            intra-zone channels.
        INTRA_ROUTING_TRANSITION: Local turn/manifold region where wires may
            change between longitude and latitude travel.
        INTRA_ROUTING_LONGITUDE: Local travel band parallel to the world major
            direction.
        INTRA_ROUTING_LATITUDE: Local travel band perpendicular to the world major
            direction.
        INTER_ROUTING_FAN_IN_OUT: Edge fan-in/fan-out region between the zone and
            a neighboring interconnect seam.
        INTER_ROUTING_TRANSITION: Edge turn/manifold region where wires may
            change between longitude and latitude travel.
        INTER_ROUTING_LONGITUDE: Edge travel band parallel to the world major
            direction.
        INTER_ROUTING_LATITUDE: Edge travel band perpendicular to the world major
            direction.
    """

    CHIP_TERMINAL = "chip_terminal"
    INTRA_ROUTING_FAN_IN_OUT = "intra_routing_fan_in_out"
    INTRA_ROUTING_TRANSITION = "intra_routing_transition"
    INTRA_ROUTING_LONGITUDE = "intra_routing_longitude"
    INTRA_ROUTING_LATITUDE = "intra_routing_latitude"
    INTER_ROUTING_FAN_IN_OUT = "inter_routing_fan_in_out"
    INTER_ROUTING_TRANSITION = "inter_routing_transition"
    INTER_ROUTING_LONGITUDE = "inter_routing_longitude"
    INTER_ROUTING_LATITUDE = "inter_routing_latitude"


RoutingZoneRegionSide = CardinalSide


class RoutingZoneInterconnectAxis(Enum):
    """Orientation of one routing-zone interconnect.

    Attributes:
        HORIZONTAL: Interconnect joins zones differing in column index.
        VERTICAL: Interconnect joins zones differing in row index.
    """

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass(frozen=True)
class GridCoord:
    """Typed world-grid coordinate for one inter-chip routing zone.

    Attributes:
        columnIndex: One-based column coordinate in the zone grid.
        rowIndex: One-based row coordinate in the zone grid.
    """

    columnIndex: int
    rowIndex: int

    def manhattanDistanceToCoord_calculate(
        self, otherGridCoord: GridCoord
    ) -> int:
        """Calculate Manhattan distance to another grid coordinate.

        Args:
            otherGridCoord: Other world-grid coordinate.

        Returns:
            Manhattan distance between the two grid locations.
        """

        return abs(self.columnIndex - otherGridCoord.columnIndex) + abs(
            self.rowIndex - otherGridCoord.rowIndex
        )

    def neighboringToCoord_isAdjacentCheck(
        self, otherGridCoord: GridCoord
    ) -> bool:
        """Return whether another coordinate is an edge-adjacent neighbor.

        Args:
            otherGridCoord: Other world-grid coordinate.

        Returns:
            `True` when the other zone is exactly one Manhattan step away.
        """

        return self.manhattanDistanceToCoord_calculate(otherGridCoord) == 1


@dataclass(frozen=True)
class RoutingZoneId:
    """Stable identity for one routing zone.

    Attributes:
        id: `GridCoord` for one world-grid routing zone.
    """

    id: GridCoord

    def worldGridCoordResult_get(self) -> Result[GridCoord]:
        """Build the world-grid coordinate for one inter-chip routing zone.

        Returns:
            Successful result containing this zone's `GridCoord`.
        """

        if not isinstance(self.id, GridCoord):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone.id.missing_world_grid_address",
                message="RoutingZoneId does not address a world-grid zone",
            )
            return resultErr_build()
        return resultOk_build(self.id)

    def worldGridAddress_isPresentCheck(self) -> bool:
        """Return whether this routing-zone id addresses a world-grid zone."""

        return isinstance(self.id, GridCoord)

    def manhattanDistanceToZoneResult_build(
        self,
        otherZoneId: RoutingZoneId,
    ) -> Result[int]:
        """Build Manhattan distance to another world-grid zone id.

        Returns:
            Successful result containing Manhattan distance when both ids are
            world-grid addressed, otherwise failed result.
        """

        sourceGridCoordResult: Result[GridCoord] = (
            self.worldGridCoordResult_get()
        )
        if not result_isOkCheck(sourceGridCoordResult):
            return resultErr_build()
        otherGridCoordResult: Result[GridCoord] = (
            otherZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(otherGridCoordResult):
            return resultErr_build()
        return resultOk_build(
            sourceGridCoordResult.value.manhattanDistanceToCoord_calculate(
                otherGridCoordResult.value
            )
        )

    def neighboringToZoneResult_build(
        self,
        otherZoneId: RoutingZoneId,
    ) -> Result[bool]:
        """Build whether another zone is an edge-adjacent world-grid neighbor.

        Returns:
            Successful result containing adjacency status when both ids are
            world-grid addressed, otherwise failed result.
        """

        manhattanDistanceResult: Result[int] = (
            self.manhattanDistanceToZoneResult_build(otherZoneId)
        )
        if not result_isOkCheck(manhattanDistanceResult):
            return resultErr_build()
        return resultOk_build(manhattanDistanceResult.value == 1)


@dataclass(frozen=True)
class RoutingZoneFrame:
    """Solved outer frame for one routing zone on the world canvas.

    The routing-zone frame is the outer geometric envelope that must contain all
    owned chip-terminal, intra-routing, and inter-routing regions.

    Attributes:
        horizontalStart: Screen-horizontal start coordinate of the zone.
        verticalStart: Screen-vertical start coordinate of the zone.
        horizontalSpan: Screen-horizontal span of the zone.
        verticalSpan: Screen-vertical span of the zone.
    """

    horizontalStart: int
    verticalStart: int
    horizontalSpan: int
    verticalSpan: int

    def horizontalEnd_calculate(self) -> int:
        """Calculate the exclusive horizontal end coordinate."""

        return self.horizontalStart + self.horizontalSpan

    def verticalEnd_calculate(self) -> int:
        """Calculate the exclusive vertical end coordinate."""

        return self.verticalStart + self.verticalSpan

    def frameContaining_isContainedCheck(
        self,
        regionFrame: RoutingZoneRegionFrame,
    ) -> bool:
        """Return whether the zone frame fully contains one region frame.

        Args:
            regionFrame: Region frame to test.

        Returns:
            `True` when the region frame lies fully inside the zone frame.
        """

        return (
            regionFrame.horizontalStart >= self.horizontalStart
            and regionFrame.verticalStart >= self.verticalStart
            and regionFrame.horizontalEnd_calculate()
            <= self.horizontalEnd_calculate()
            and regionFrame.verticalEnd_calculate()
            <= self.verticalEnd_calculate()
        )


@dataclass(frozen=True)
class RoutingZoneRegionFrame:
    """Solved frame for one explicit owned routing-zone region.

    Attributes:
        horizontalStart: Screen-horizontal start coordinate of the region.
        verticalStart: Screen-vertical start coordinate of the region.
        horizontalSpan: Screen-horizontal span of the region.
        verticalSpan: Screen-vertical span of the region.
    """

    horizontalStart: int
    verticalStart: int
    horizontalSpan: int
    verticalSpan: int

    def horizontalEnd_calculate(self) -> int:
        """Calculate the exclusive horizontal end coordinate."""

        return self.horizontalStart + self.horizontalSpan

    def verticalEnd_calculate(self) -> int:
        """Calculate the exclusive vertical end coordinate."""

        return self.verticalStart + self.verticalSpan


@dataclass(frozen=True)
class RoutingZoneRegionId:
    """Stable identity for one explicit owned routing-zone region.

    A region id names one region unambiguously by zone, region kind, and when
    applicable the side of the zone on which the region lives.

    Attributes:
        routingZoneId: Owning routing-zone identity.
        routingZoneRegionKind: Canonical region kind.
        routingZoneRegionSide: Cardinal side for sided regions, otherwise `None`.
        routingZoneRegionTag: Optional qualifier when one kind/side needs more
            than one explicit rectangular frame.
    """

    routingZoneId: RoutingZoneId
    routingZoneRegionKind: RoutingZoneRegionKind
    routingZoneRegionSide: RoutingZoneRegionSide | None = None
    routingZoneRegionTag: str | None = None


@dataclass(frozen=True)
class RoutingZoneRegion:
    """One explicit owned region inside a routing zone.

    Attributes:
        routingZoneRegionId: Stable region identity.
        routingZoneRegionFrame: Solved frame for this region.
    """

    routingZoneRegionId: RoutingZoneRegionId
    routingZoneRegionFrame: RoutingZoneRegionFrame

    def sideRequired_isRequiredCheck(self) -> bool:
        """Return whether this region kind requires a cardinal side.

        Returns:
            `True` — every region in the zone model carries a cardinal side.
        """

        return True


@dataclass(frozen=True)
class RoutingZoneRegionSet:
    """Modeled collection of explicit owned routing-zone regions.

    Attributes:
        routingZoneRegions: Ordered regions owned by one routing zone.
    """

    routingZoneRegions: tuple[RoutingZoneRegion, ...] = field(
        default_factory=tuple
    )

    def regionResult_get(
        self,
        routingZoneRegionId: RoutingZoneRegionId,
    ) -> Result[RoutingZoneRegion]:
        """Build one region by id.

        Returns:
            Successful result containing the matching region, otherwise failed
            result with routing diagnostics.
        """

        routingZoneRegion: RoutingZoneRegion
        for routingZoneRegion in self.routingZoneRegions:
            if routingZoneRegion.routingZoneRegionId == routingZoneRegionId:
                return resultOk_build(routingZoneRegion)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region.missing",
            message="Requested RoutingZoneRegion is absent from the region set",
        )
        return resultErr_build()

    def regionsOfKind_build(
        self,
        routingZoneRegionKind: RoutingZoneRegionKind,
    ) -> RoutingZoneRegionSet:
        """Build a filtered region set for one region kind.

        Args:
            routingZoneRegionKind: Region kind to filter by.

        Returns:
            `RoutingZoneRegionSet` containing only the requested kind.
        """

        return RoutingZoneRegionSet(
            routingZoneRegions=tuple(
                routingZoneRegion
                for routingZoneRegion in self.routingZoneRegions
                if routingZoneRegion.routingZoneRegionId.routingZoneRegionKind
                is routingZoneRegionKind
            )
        )

    def regionForKindAndSideResult_get(
        self,
        routingZoneRegionKind: RoutingZoneRegionKind,
        routingZoneRegionSide: RoutingZoneRegionSide,
    ) -> Result[RoutingZoneRegion]:
        """Build one sided region by kind and side.

        Args:
            routingZoneRegionKind: Region kind to locate.
            routingZoneRegionSide: Side on which the region must live.

        Returns:
            Successful result containing the matching region, otherwise failed
            result with routing diagnostics.
        """

        routingZoneRegion: RoutingZoneRegion
        for routingZoneRegion in self.routingZoneRegions:
            if (
                routingZoneRegion.routingZoneRegionId.routingZoneRegionKind
                == routingZoneRegionKind
                and routingZoneRegion.routingZoneRegionId.routingZoneRegionSide
                == routingZoneRegionSide
            ):
                return resultOk_build(routingZoneRegion)

        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region.missing_kind_and_side",
            message="Requested sided RoutingZoneRegion is absent from the region set",
        )
        return resultErr_build()

    def regionsForKindAndSide_build(
        self,
        routingZoneRegionKind: RoutingZoneRegionKind,
        routingZoneRegionSide: RoutingZoneRegionSide,
    ) -> RoutingZoneRegionSet:
        """Build all regions matching one kind and side."""

        return RoutingZoneRegionSet(
            routingZoneRegions=tuple(
                routingZoneRegion
                for routingZoneRegion in self.routingZoneRegions
                if (
                    routingZoneRegion.routingZoneRegionId.routingZoneRegionKind
                    is routingZoneRegionKind
                    and routingZoneRegion.routingZoneRegionId.routingZoneRegionSide
                    is routingZoneRegionSide
                )
            )
        )

    def singleRegionForKindResult_get(
        self,
        routingZoneRegionKind: RoutingZoneRegionKind,
    ) -> Result[RoutingZoneRegion]:
        """Build one non-sided region by kind.

        This is intended for region kinds that should exist exactly once in a
        zone, such as the current intra/inter longitude and latitude bands.
        """

        matchingRegions: tuple[RoutingZoneRegion, ...] = tuple(
            routingZoneRegion
            for routingZoneRegion in self.routingZoneRegions
            if (
                routingZoneRegion.routingZoneRegionId.routingZoneRegionKind
                is routingZoneRegionKind
            )
        )
        if len(matchingRegions) != 1:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone.region.invalid_single_region_kind_count",
                message=(
                    "Requested RoutingZoneRegion kind must exist exactly once "
                    "in the region set"
                ),
                context=(
                    routingZoneRegionKind.value,
                    str(len(matchingRegions)),
                ),
            )
            return resultErr_build()
        return resultOk_build(matchingRegions[0])


@dataclass(frozen=True)
class ChipPlacement:
    """Placement of one chip inside one routing zone.

    Attributes:
        chipRef: Referenced chip placed in the zone.
        chipTerminalRegionId: Terminal region that owns the placement.
        orderIndex: Stable local ordering within that terminal region.
    """

    chipRef: ChipRef
    chipTerminalRegionId: RoutingZoneRegionId
    orderIndex: int


@dataclass(frozen=True)
class ChipPlacementSet:
    """Modeled collection of chip placements inside one zone.

    Attributes:
        placements: Ordered chip placements in one routing zone.
    """

    placements: tuple[ChipPlacement, ...] = field(default_factory=tuple)

    def placementForChipOrNone_get(
        self,
        chipRef: ChipRef,
    ) -> ChipPlacement | None:
        """Return the placement for one chip when present, otherwise `None`."""

        chipPlacement: ChipPlacement
        for chipPlacement in self.placements:
            if chipPlacement.chipRef == chipRef:
                return chipPlacement
        return None

    def placementForChipResult_get(
        self, chipRef: ChipRef
    ) -> Result[ChipPlacement]:
        """Build the placement for one referenced chip.

        Args:
            chipRef: Referenced chip to locate.

        Returns:
            Successful result containing the matching placement, otherwise
            failed result with routing diagnostics.
        """

        chipPlacement = self.placementForChipOrNone_get(chipRef)
        if chipPlacement is not None:
            return resultOk_build(chipPlacement)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.placement.missing_chip",
            message="Requested ChipPlacement is absent from the placement set",
            context=(chipRef.chipId.moduleName, chipRef.chipId.functionName),
        )
        return resultErr_build()

    def placementsInRegion_build(
        self, chipTerminalRegionId: RoutingZoneRegionId
    ) -> ChipPlacementSet:
        """Build a filtered placement set for one terminal region.

        Args:
            chipTerminalRegionId: Terminal region to filter by.

        Returns:
            `ChipPlacementSet` containing only placements in that region.
        """

        return ChipPlacementSet(
            placements=tuple(
                chipPlacement
                for chipPlacement in self.placements
                if chipPlacement.chipTerminalRegionId == chipTerminalRegionId
            )
        )


class RoutingZoneFamily(Enum):
    """The family of routing zones in the SignalFlow substrate."""

    STANDARD = "standard"
    EMBEDDED = "embedded"


@dataclass(frozen=True)
class KernelObligation:
    """Directed routing demand for a single kernel."""

    callRouteObligation: CallRouteObligation
    sourcePlacement: ChipPlacement
    destinationPlacement: ChipPlacement
    destinationPortIndex: int = 0
    laneIndex: int = 0


@dataclass(frozen=True)
class RoutingKernel:
    """The atomic, independent routing block of the SignalFlow substrate.

    A kernel owns a localized substrate and connects a source wall to a
    destination wall using monotone ribbon packing.
    """

    routingZoneId: RoutingZoneId
    routingZoneRegionSet: RoutingZoneRegionSet
    occupancyPolicy: RoutingOccupancyPolicy = RoutingOccupancyPolicy.STRIP
    packingPolicy: RoutingLanePackingPolicy = RoutingLanePackingPolicy.MONOTONE
    attachmentPolicy: RoutingZoneAttachmentPolicy = field(
        default_factory=RoutingZoneAttachmentPolicy
    )


@dataclass(frozen=True)
class RoutingZone:
    """Atomic local routing block in the world topology.

    A Standard RoutingZone is a composition of five kernels (the Kernel
    Crossbar). An Embedded RoutingZone is a single-kernel transition.
    """

    routingZoneId: RoutingZoneId
    routingZoneSense: RoutingZoneSense
    routingZoneFamily: RoutingZoneFamily = RoutingZoneFamily.STANDARD
    channelSense: RoutingZoneChannelSense = RoutingZoneChannelSense.CLOCKWISE
    routingZoneFrame: RoutingZoneFrame = field(
        default_factory=lambda: RoutingZoneFrame(
            horizontalStart=0,
            verticalStart=0,
            horizontalSpan=1,
            verticalSpan=1,
        )
    )
    chipPlacementSet: ChipPlacementSet = field(
        default_factory=ChipPlacementSet
    )
    occupancyPolicy: RoutingOccupancyPolicy = RoutingOccupancyPolicy.STRIP
    packingPolicy: RoutingLanePackingPolicy = RoutingLanePackingPolicy.MONOTONE
    attachmentPolicy: RoutingZoneAttachmentPolicy = field(
        default_factory=RoutingZoneAttachmentPolicy
    )

    # The Kernel Crossbar (for Standard zones)
    # These are lazily resolved or built by the solver, but modeled here
    # as the authoritative decomposition.
    intraKernel: RoutingKernel | None = None
    westKernel: RoutingKernel | None = None
    eastKernel: RoutingKernel | None = None
    northKernel: RoutingKernel | None = None
    southKernel: RoutingKernel | None = None

    def regionAllowed_isAllowedCheck(
        self,
        routingZoneRegion: RoutingZoneRegion,
    ) -> bool:
        """Return whether one owned region is compatible with this zone sense.

        Args:
            routingZoneRegion: Region to test.

        Returns:
            `True` when the region kind/side combination is valid for the zone sense.
        """

        return (
            routingZoneRegion.routingZoneRegionId.routingZoneRegionSide
            is not None
        )


@dataclass(frozen=True)
class RoutingZoneInterconnectId:
    """Stable identity for one zone-to-zone interconnect.

    Attributes:
        sourceZoneId: Source-side zone identity.
        destinationZoneId: Destination-side zone identity.
    """

    sourceZoneId: RoutingZoneId
    destinationZoneId: RoutingZoneId


@dataclass(frozen=True)
class RoutingZoneInterconnectFrame:
    """Solved outer frame for one routing-zone interconnect on the world canvas.

    Attributes:
        horizontalStart: Screen-horizontal start coordinate of the interconnect.
        verticalStart: Screen-vertical start coordinate of the interconnect.
        horizontalSpan: Screen-horizontal span of the interconnect.
        verticalSpan: Screen-vertical span of the interconnect.
    """

    horizontalStart: int
    verticalStart: int
    horizontalSpan: int
    verticalSpan: int


@dataclass(frozen=True)
class RoutingZoneInterconnect:
    """Continuity mediator between two neighboring routing zones.

    Attributes:
        routingZoneInterconnectId: Stable interconnect identity.
        sourceZoneId: Source-side zone identity.
        destinationZoneId: Destination-side zone identity.
        breakoutZone: Optional EmbeddedRoutingZone for seam breakout.
        channelSense: Travel policy for the seam channels.
        occupancyPolicy: Occupancy doctrine for seam-channel reservation.
        packingPolicy: Lane-packing doctrine for seam-channel allocation.
        attachmentPolicy: Fine-grained lane-pick policy for seam channels.
        routingZoneInterconnectFrame: Solved outer frame for this seam.
    """

    routingZoneInterconnectId: RoutingZoneInterconnectId
    sourceZoneId: RoutingZoneId
    destinationZoneId: RoutingZoneId
    breakoutZone: RoutingZone | None = None
    channelSense: RoutingZoneChannelSense = RoutingZoneChannelSense.CLOCKWISE
    occupancyPolicy: RoutingOccupancyPolicy = RoutingOccupancyPolicy.STRIP
    packingPolicy: RoutingLanePackingPolicy = RoutingLanePackingPolicy.MONOTONE
    attachmentPolicy: RoutingZoneAttachmentPolicy = field(
        default_factory=RoutingZoneAttachmentPolicy
    )
    routingZoneInterconnectFrame: RoutingZoneInterconnectFrame = field(
        default_factory=lambda: RoutingZoneInterconnectFrame(
            horizontalStart=0,
            verticalStart=0,
            horizontalSpan=1,
            verticalSpan=1,
        )
    )

    def interconnectAxisResult_get(
        self,
    ) -> Result[RoutingZoneInterconnectAxis]:
        """Build the orientation of this interconnect.

        Returns:
            Successful result containing the derived axis when both connected
            zones are world-grid addressed, otherwise failed result.
        """

        sourceGridCoordResult: Result[GridCoord] = (
            self.sourceZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(sourceGridCoordResult):
            return resultErr_build()
        destinationGridCoordResult: Result[GridCoord] = (
            self.destinationZoneId.worldGridCoordResult_get()
        )
        if not result_isOkCheck(destinationGridCoordResult):
            return resultErr_build()
        sourceGridCoord: GridCoord = sourceGridCoordResult.value
        destinationGridCoord: GridCoord = destinationGridCoordResult.value
        if sourceGridCoord.rowIndex == destinationGridCoord.rowIndex:
            return resultOk_build(RoutingZoneInterconnectAxis.HORIZONTAL)
        return resultOk_build(RoutingZoneInterconnectAxis.VERTICAL)


def routingZoneFrameResult_build(
    horizontalStart: int,
    verticalStart: int,
    horizontalSpan: int,
    verticalSpan: int,
) -> Result[RoutingZoneFrame]:
    """Build a validated routing-zone frame.

    Args:
        horizontalStart: Screen-horizontal start coordinate.
        verticalStart: Screen-vertical start coordinate.
        horizontalSpan: Screen-horizontal span.
        verticalSpan: Screen-vertical span.

    Returns:
        Successful result containing `RoutingZoneFrame`, or failed result when
        the spans are not positive.
    """

    if horizontalSpan <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.frame.invalid_horizontal_span",
            message="RoutingZoneFrame horizontal span must be positive",
        )
        return resultErr_build()
    if verticalSpan <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.frame.invalid_vertical_span",
            message="RoutingZoneFrame vertical span must be positive",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneFrame(
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            horizontalSpan=horizontalSpan,
            verticalSpan=verticalSpan,
        )
    )


def routingZoneRegionFrameResult_build(
    horizontalStart: int,
    verticalStart: int,
    horizontalSpan: int,
    verticalSpan: int,
) -> Result[RoutingZoneRegionFrame]:
    """Build a validated routing-zone region frame."""

    if horizontalSpan <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region_frame.invalid_horizontal_span",
            message="RoutingZoneRegionFrame horizontal span must be positive",
        )
        return resultErr_build()
    if verticalSpan <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region_frame.invalid_vertical_span",
            message="RoutingZoneRegionFrame vertical span must be positive",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneRegionFrame(
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            horizontalSpan=horizontalSpan,
            verticalSpan=verticalSpan,
        )
    )


def routingZoneRegionResult_build(
    routingZoneRegionId: RoutingZoneRegionId,
    routingZoneRegionFrame: RoutingZoneRegionFrame,
) -> Result[RoutingZoneRegion]:
    """Build a validated routing-zone region."""

    routingZoneRegion: RoutingZoneRegion = RoutingZoneRegion(
        routingZoneRegionId=routingZoneRegionId,
        routingZoneRegionFrame=routingZoneRegionFrame,
    )
    if routingZoneRegion.routingZoneRegionId.routingZoneRegionSide is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region.missing_side",
            message="All routing-zone regions must declare a cardinal side",
        )
        return resultErr_build()
    return resultOk_build(routingZoneRegion)


def routingZoneRegionSetResult_build(
    routingZoneRegions: tuple[RoutingZoneRegion, ...],
) -> Result[RoutingZoneRegionSet]:
    """Build a validated routing-zone region set."""

    regionIds: tuple[RoutingZoneRegionId, ...] = tuple(
        routingZoneRegion.routingZoneRegionId
        for routingZoneRegion in routingZoneRegions
    )
    if len(set(regionIds)) != len(regionIds):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region_set.duplicate_region_id",
            message="RoutingZoneRegion ids must be unique in one zone",
        )
        return resultErr_build()

    if routingZoneRegions:
        owningZoneId: RoutingZoneId = routingZoneRegions[
            0
        ].routingZoneRegionId.routingZoneId
        routingZoneRegion: RoutingZoneRegion
        for routingZoneRegion in routingZoneRegions:
            if (
                routingZoneRegion.routingZoneRegionId.routingZoneId
                != owningZoneId
            ):
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.zone.region_set.mixed_zone_ids",
                    message=(
                        "RoutingZoneRegionSet may contain regions from only "
                        "one zone"
                    ),
                )
                return resultErr_build()

    return resultOk_build(
        RoutingZoneRegionSet(routingZoneRegions=routingZoneRegions)
    )


def chipPlacementSetResult_build(
    placements: tuple[ChipPlacement, ...],
) -> Result[ChipPlacementSet]:
    """Build a validated chip-placement set."""

    chipRefs: tuple[ChipRef, ...] = tuple(
        chipPlacement.chipRef for chipPlacement in placements
    )
    if len(set(chipRefs)) != len(chipRefs):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.placement_set.duplicate_chip",
            message="A chip may not be placed more than once in one zone",
        )
        return resultErr_build()
    return resultOk_build(ChipPlacementSet(placements=placements))


def routingZoneResult_build(
    routingZoneId: RoutingZoneId,
    routingZoneSense: RoutingZoneSense,
    routingZoneFamily: RoutingZoneFamily = RoutingZoneFamily.STANDARD,
    channelSense: RoutingZoneChannelSense = RoutingZoneChannelSense.CLOCKWISE,
    occupancyPolicy: RoutingOccupancyPolicy = RoutingOccupancyPolicy.STRIP,
    packingPolicy: RoutingLanePackingPolicy = RoutingLanePackingPolicy.MONOTONE,
    attachmentPolicy: RoutingZoneAttachmentPolicy | None = None,
    routingZoneFrame: RoutingZoneFrame | None = None,
    routingZoneRegionSet: RoutingZoneRegionSet | None = None,
    chipPlacementSet: ChipPlacementSet | None = None,
) -> Result[RoutingZone]:
    """Build a validated routing zone with a partitioned Kernel Crossbar."""

    routingZoneFrameValue: RoutingZoneFrame = (
        routingZoneFrame
        or RoutingZoneFrame(
            horizontalStart=0,
            verticalStart=0,
            horizontalSpan=1,
            verticalSpan=1,
        )
    )
    routingZoneRegionSetValue: RoutingZoneRegionSet = (
        routingZoneRegionSet or RoutingZoneRegionSet()
    )
    chipPlacementSetValue: ChipPlacementSet = (
        chipPlacementSet or ChipPlacementSet()
    )
    attachmentPolicyValue = attachmentPolicy or RoutingZoneAttachmentPolicy()

    # Partition regions into Kernels
    def _kernel_build(regions: list[RoutingZoneRegion]) -> RoutingKernel:
        return RoutingKernel(
            routingZoneId=routingZoneId,
            routingZoneRegionSet=RoutingZoneRegionSet(tuple(regions)),
            occupancyPolicy=occupancyPolicy,
            packingPolicy=packingPolicy,
            attachmentPolicy=attachmentPolicyValue,
        )

    intra_regs, west_regs, east_regs, north_regs, south_regs = (
        [],
        [],
        [],
        [],
        [],
    )

    for r in routingZoneRegionSetValue.routingZoneRegions:
        k = r.routingZoneRegionId.routingZoneRegionKind
        s = r.routingZoneRegionId.routingZoneRegionSide

        # Intra Kernel owns chip terminals and intra-routing regions
        if k in (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        ):
            # Terminals are shared conceptually but owned by Intra for the main solve
            intra_regs.append(r)

        # West Breakout Kernel
        if s == RoutingZoneRegionSide.WEST and k in (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
        ):
            west_regs.append(r)

        # East Breakout Kernel
        if s == RoutingZoneRegionSide.EAST and k in (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
        ):
            east_regs.append(r)

        # Perimeter Kernels (NORTH and SOUTH)
        if s == RoutingZoneRegionSide.NORTH and k in (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
        ):
            north_regs.append(r)
        if s == RoutingZoneRegionSide.SOUTH and k in (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
        ):
            south_regs.append(r)

    routingZone: RoutingZone = RoutingZone(
        routingZoneId=routingZoneId,
        routingZoneSense=routingZoneSense,
        routingZoneFamily=routingZoneFamily,
        channelSense=channelSense,
        occupancyPolicy=occupancyPolicy,
        packingPolicy=packingPolicy,
        attachmentPolicy=attachmentPolicyValue,
        routingZoneFrame=routingZoneFrameValue,
        chipPlacementSet=chipPlacementSetValue,
        intraKernel=_kernel_build(intra_regs),
        westKernel=_kernel_build(west_regs),
        eastKernel=_kernel_build(east_regs),
        northKernel=_kernel_build(north_regs),
        southKernel=_kernel_build(south_regs),
    )

    routingZoneRegion: RoutingZoneRegion
    for routingZoneRegion in routingZoneRegionSetAll_get(routingZone):
        if (
            routingZoneFamily == RoutingZoneFamily.STANDARD
            and routingZoneRegion.routingZoneRegionId.routingZoneId
            != routingZone.routingZoneId
        ):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone.region.invalid_owner",
                message="Standard RoutingZone may own only regions with matching zone id",
            )
            return resultErr_build()

        if routingZoneFamily == RoutingZoneFamily.STANDARD:
            if not routingZone.regionAllowed_isAllowedCheck(routingZoneRegion):
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.zone.region.invalid_side_for_sense",
                    message="RoutingZone region is incompatible with zone sense",
                )
                return resultErr_build()
            if not routingZone.routingZoneFrame.frameContaining_isContainedCheck(
                routingZoneRegion.routingZoneRegionFrame
            ):
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.zone.region.outside_zone_frame",
                    message="RoutingZone regions must lie fully inside the zone frame",
                )
                return resultErr_build()

    chipPlacement: ChipPlacement
    for chipPlacement in routingZone.chipPlacementSet.placements:
        chipTerminalRegionResult: Result[RoutingZoneRegion] = (
            routingZoneRegionByIdResult_get(
                routingZone,
                chipPlacement.chipTerminalRegionId,
            )
        )
        if not result_isOkCheck(chipTerminalRegionResult):
            return resultErr_build()
        chipTerminalRegion: RoutingZoneRegion = chipTerminalRegionResult.value
        if (
            chipTerminalRegion.routingZoneRegionId.routingZoneRegionKind
            is not RoutingZoneRegionKind.CHIP_TERMINAL
        ):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.zone.placement.invalid_region_kind",
                message="Chip placements must target regions of kind CHIP_TERMINAL",
            )
            return resultErr_build()

    return resultOk_build(routingZone)


def routingZoneRegionForKindAndSideResult_get(
    routingZone: RoutingZone,
    routingZoneRegionKind: RoutingZoneRegionKind,
    routingZoneRegionSide: RoutingZoneRegionSide,
) -> Result[RoutingZoneRegion]:
    """Dispatch a region lookup to the owning kernel on *routingZone*.

    The ownership map mirrors the partitioning logic in
    ``routingZoneResult_build``:

    - CHIP_TERMINAL / INTRA_ROUTING_* → intraKernel (any side)
    - INTER_ROUTING_FAN_IN_OUT + WEST / INTER_ROUTING_LONGITUDE + WEST → westKernel
    - INTER_ROUTING_FAN_IN_OUT + EAST / INTER_ROUTING_LONGITUDE + EAST → eastKernel
    - INTER_ROUTING_LATITUDE + NORTH → northKernel
    - INTER_ROUTING_LATITUDE + SOUTH → southKernel
    - INTER_ROUTING_FAN_IN_OUT + NORTH / INTER_ROUTING_LONGITUDE + NORTH → northKernel
    - INTER_ROUTING_FAN_IN_OUT + SOUTH / INTER_ROUTING_LONGITUDE + SOUTH → southKernel

    Args:
        routingZone: Zone whose kernel crossbar is searched.
        routingZoneRegionKind: Region kind to locate.
        routingZoneRegionSide: Side on which the region must live.

    Returns:
        Successful result containing the matching region, otherwise failed
        result with routing diagnostics.
    """

    _INTRA_KINDS = (
        RoutingZoneRegionKind.CHIP_TERMINAL,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
    )

    if routingZoneRegionKind in _INTRA_KINDS:
        kernel = routingZone.intraKernel
    elif routingZoneRegionSide is RoutingZoneRegionSide.WEST:
        kernel = routingZone.westKernel
    elif routingZoneRegionSide is RoutingZoneRegionSide.EAST:
        kernel = routingZone.eastKernel
    elif routingZoneRegionSide is RoutingZoneRegionSide.NORTH:
        kernel = routingZone.northKernel
    elif routingZoneRegionSide is RoutingZoneRegionSide.SOUTH:
        kernel = routingZone.southKernel
    else:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region.unknown_kernel",
            message="Cannot determine owning kernel for region kind and side",
        )
        return resultErr_build()

    if kernel is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.region.missing_kernel",
            message="Owning kernel is absent from the routing zone",
        )
        return resultErr_build()

    return kernel.routingZoneRegionSet.regionForKindAndSideResult_get(
        routingZoneRegionKind, routingZoneRegionSide
    )


def routingZoneRegionSetAll_get(
    routingZone: RoutingZone,
) -> tuple[RoutingZoneRegion, ...]:
    """Return all regions owned by *routingZone* across all five kernels.

    This replaces iteration over the removed ``routingZoneRegionSet`` field.

    Args:
        routingZone: Zone whose kernel crossbar is collected.

    Returns:
        Concatenated tuple of every ``RoutingZoneRegion`` across the five
        kernels (intra, west, east, north, south).
    """

    seen_ids: set[RoutingZoneRegionId] = set()
    regions: list[RoutingZoneRegion] = []
    for kernel in (
        routingZone.intraKernel,
        routingZone.westKernel,
        routingZone.eastKernel,
        routingZone.northKernel,
        routingZone.southKernel,
    ):
        if kernel is None:
            continue
        for region in kernel.routingZoneRegionSet.routingZoneRegions:
            if region.routingZoneRegionId not in seen_ids:
                seen_ids.add(region.routingZoneRegionId)
                regions.append(region)
    return tuple(regions)


def routingZoneRegionByIdResult_get(
    routingZone: RoutingZone,
    routingZoneRegionId: RoutingZoneRegionId,
) -> Result[RoutingZoneRegion]:
    """Locate one region by its id across all five kernels on *routingZone*.

    This replaces calls to the removed ``routingZoneRegionSet.regionResult_get``
    on the zone itself.

    Args:
        routingZone: Zone whose kernel crossbar is searched.
        routingZoneRegionId: Identity of the region to locate.

    Returns:
        Successful result containing the matching region, otherwise failed
        result with routing diagnostics.
    """

    for kernel in (
        routingZone.intraKernel,
        routingZone.westKernel,
        routingZone.eastKernel,
        routingZone.northKernel,
        routingZone.southKernel,
    ):
        if kernel is None:
            continue
        for region in kernel.routingZoneRegionSet.routingZoneRegions:
            if region.routingZoneRegionId == routingZoneRegionId:
                return resultOk_build(region)

    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.zone.region.missing",
        message="Requested RoutingZoneRegion is absent from the region set",
    )
    return resultErr_build()


def routingZoneKernelOrNone_build(
    routingZone: RoutingZone,
    role: str,
) -> RoutingKernel | None:
    """Build one compatibility kernel slice from the zone region set.

    This is a transitional helper for code that still expects a per-side
    `RoutingKernel` object even though the kernel cross is no longer the
    intended architecture.
    """

    roleNormalized = role.strip().lower()
    regions: list[RoutingZoneRegion] = []
    for region in routingZoneRegionSetAll_get(routingZone):
        kind = region.routingZoneRegionId.routingZoneRegionKind
        side = region.routingZoneRegionId.routingZoneRegionSide

        if roleNormalized == "intra" and kind in (
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT,
            RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
            RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE,
            RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION,
        ):
            regions.append(region)
        elif roleNormalized == "west" and (
            side is RoutingZoneRegionSide.WEST
            and kind in (
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            )
        ):
            regions.append(region)
        elif roleNormalized == "east" and (
            side is RoutingZoneRegionSide.EAST
            and kind in (
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
            )
        ):
            regions.append(region)
        elif roleNormalized == "north" and (
            side is RoutingZoneRegionSide.NORTH
            and kind in (
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            )
        ):
            regions.append(region)
        elif roleNormalized == "south" and (
            side is RoutingZoneRegionSide.SOUTH
            and kind in (
                RoutingZoneRegionKind.CHIP_TERMINAL,
                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT,
                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE,
                RoutingZoneRegionKind.INTER_ROUTING_LATITUDE,
            )
        ):
            regions.append(region)

    if not regions:
        return None

    return RoutingKernel(
        routingZoneId=routingZone.routingZoneId,
        routingZoneRegionSet=RoutingZoneRegionSet(tuple(regions)),
        occupancyPolicy=routingZone.occupancyPolicy,
        packingPolicy=routingZone.packingPolicy,
        attachmentPolicy=routingZone.attachmentPolicy,
    )


def routingZoneRegionsForKindAndSide_get(
    routingZone: RoutingZone,
    routingZoneRegionKind: RoutingZoneRegionKind,
    routingZoneRegionSide: RoutingZoneRegionSide,
) -> RoutingZoneRegionSet:
    """Return all regions matching one kind and side across the kernel crossbar.

    This replaces calls to the removed
    ``routingZoneRegionSet.regionsForKindAndSide_build`` on the zone itself.

    Args:
        routingZone: Zone whose kernel crossbar is searched.
        routingZoneRegionKind: Region kind to filter by.
        routingZoneRegionSide: Side to filter by.

    Returns:
        ``RoutingZoneRegionSet`` containing every matching region.
    """

    return RoutingZoneRegionSet(
        routingZoneRegions=tuple(
            region
            for region in routingZoneRegionSetAll_get(routingZone)
            if (
                region.routingZoneRegionId.routingZoneRegionKind
                is routingZoneRegionKind
                and region.routingZoneRegionId.routingZoneRegionSide
                is routingZoneRegionSide
            )
        )
    )


def routingZoneInterconnectFrameResult_build(
    horizontalStart: int,
    verticalStart: int,
    horizontalSpan: int,
    verticalSpan: int,
) -> Result[RoutingZoneInterconnectFrame]:
    """Build a validated interconnect frame."""

    if horizontalSpan <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.interconnect_frame.invalid_horizontal_span",
            message="RoutingZoneInterconnectFrame horizontal span must be positive",
        )
        return resultErr_build()
    if verticalSpan <= 0:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.interconnect_frame.invalid_vertical_span",
            message="RoutingZoneInterconnectFrame vertical span must be positive",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneInterconnectFrame(
            horizontalStart=horizontalStart,
            verticalStart=verticalStart,
            horizontalSpan=horizontalSpan,
            verticalSpan=verticalSpan,
        )
    )


def routingZoneInterconnectResult_build(
    routingZoneInterconnectId: RoutingZoneInterconnectId,
    sourceZoneId: RoutingZoneId,
    destinationZoneId: RoutingZoneId,
    breakoutZone: RoutingZone | None = None,
    channelSense: RoutingZoneChannelSense = RoutingZoneChannelSense.CLOCKWISE,
    occupancyPolicy: RoutingOccupancyPolicy = RoutingOccupancyPolicy.STRIP,
    packingPolicy: RoutingLanePackingPolicy = RoutingLanePackingPolicy.MONOTONE,
    attachmentPolicy: RoutingZoneAttachmentPolicy | None = None,
    routingZoneInterconnectFrame: RoutingZoneInterconnectFrame | None = None,
) -> Result[RoutingZoneInterconnect]:
    """Build a validated routing-zone interconnect."""

    if routingZoneInterconnectId.sourceZoneId != sourceZoneId:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.interconnect.invalid_source_id",
            message="Interconnect source zone id must match its identity",
        )
        return resultErr_build()
    if routingZoneInterconnectId.destinationZoneId != destinationZoneId:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.interconnect.invalid_destination_id",
            message="Interconnect destination zone id must match its identity",
        )
        return resultErr_build()
    zonesAreAdjacentResult: Result[bool] = (
        sourceZoneId.neighboringToZoneResult_build(destinationZoneId)
    )
    if not result_isOkCheck(zonesAreAdjacentResult):
        return resultErr_build()
    if not zonesAreAdjacentResult.value:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.zone.interconnect.non_neighbor",
            message="RoutingZoneInterconnect may connect only neighboring zones",
        )
        return resultErr_build()

    return resultOk_build(
        RoutingZoneInterconnect(
            routingZoneInterconnectId=routingZoneInterconnectId,
            sourceZoneId=sourceZoneId,
            destinationZoneId=destinationZoneId,
            breakoutZone=breakoutZone,
            channelSense=channelSense,
            occupancyPolicy=occupancyPolicy,
            packingPolicy=packingPolicy,
            attachmentPolicy=attachmentPolicy or RoutingZoneAttachmentPolicy(),
            routingZoneInterconnectFrame=(
                routingZoneInterconnectFrame
                or RoutingZoneInterconnectFrame(
                    horizontalStart=0,
                    verticalStart=0,
                    horizontalSpan=1,
                    verticalSpan=1,
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# Zone drawing
# ---------------------------------------------------------------------------


def routingZoneDrawLines_build(zone: RoutingZone) -> tuple[str, ...]:
    """Build the canonical schematic drawing lines for one routing zone.

    This is the single source of truth for zone visual geometry. Both the
    interactive debugger and the final circuit renderer must call this function
    so the representation is identical in both contexts.

    West-to-east zones are drawn as a three-column schematic::

        zone [1,1]  west_to_east  30×9
        ┌──────────┬──────────────┬──────────┐
        │   WEST   │   routing    │   EAST   │
        │  main()  │              │  a()     │
        │          │              │  b()     │
        │          │              │  c()     │
        └──────────┴──────────────┴──────────┘

    North-to-south zones are drawn as a three-row schematic::

        zone [1,1]  north_to_south  13×12
        ┌──────────────────┐
        │      NORTH       │
        │  main()          │
        ├──────────────────┤
        │     routing      │
        ├──────────────────┤
        │      SOUTH       │
        │  child()         │
        └──────────────────┘
    """

    coord = zone.routingZoneId.id
    coordLabel = (
        f"[{coord.columnIndex},{coord.rowIndex}]"
        if isinstance(coord, GridCoord)
        else str(coord)
    )
    frame = zone.routingZoneFrame
    header = (
        f"zone {coordLabel}  {zone.routingZoneSense.value}"
        f"  {frame.horizontalSpan}\u00d7{frame.verticalSpan}"
    )

    def _names_for_side(side: RoutingZoneRegionSide) -> list[str]:
        return [
            p.chipRef.chipId.functionName
            for p in sorted(
                (
                    p
                    for p in zone.chipPlacementSet.placements
                    if p.chipTerminalRegionId.routingZoneRegionSide is side
                ),
                key=lambda p: p.orderIndex,
            )
        ]

    if zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return _zoneHorizontalDrawLines_build(
            header,
            westNames=_names_for_side(RoutingZoneRegionSide.WEST),
            eastNames=_names_for_side(RoutingZoneRegionSide.EAST),
        )
    return _zoneVerticalDrawLines_build(
        header,
        northNames=_names_for_side(RoutingZoneRegionSide.NORTH),
        southNames=_names_for_side(RoutingZoneRegionSide.SOUTH),
    )


def _zoneHorizontalDrawLines_build(
    header: str,
    westNames: list[str],
    eastNames: list[str],
) -> tuple[str, ...]:
    """Build ASCII art lines for a west-to-east zone schematic."""

    WEST = "WEST"
    EAST = "EAST"
    ROUTING = "routing"

    west_w = max(len(WEST), max((len(n) for n in westNames), default=0)) + 2
    east_w = max(len(EAST), max((len(n) for n in eastNames), default=0)) + 2
    mid_w = max(len(ROUTING) + 2, 10)

    def _cell(text: str, width: int) -> str:
        return text.center(width) if text else " " * width

    rows = max(len(westNames), len(eastNames), 1)
    horizWest = "─" * west_w
    horizMid = "─" * mid_w
    horizEast = "─" * east_w
    lines: list[str] = [
        header,
        f"┌{horizWest}┬{horizMid}┬{horizEast}┐",
        f"│{_cell(WEST, west_w)}│{_cell(ROUTING, mid_w)}│{_cell(EAST, east_w)}│",
    ]
    for i in range(rows):
        w = westNames[i] if i < len(westNames) else ""
        e = eastNames[i] if i < len(eastNames) else ""
        lines.append(f"│{_cell(w, west_w)}│{' ' * mid_w}│{_cell(e, east_w)}│")
    lines.append(f"└{horizWest}┴{horizMid}┴{horizEast}┘")
    return tuple(lines)


def _zoneVerticalDrawLines_build(
    header: str,
    northNames: list[str],
    southNames: list[str],
) -> tuple[str, ...]:
    """Build ASCII art lines for a north-to-south zone schematic."""

    NORTH = "NORTH"
    SOUTH = "SOUTH"
    ROUTING = "routing"

    all_names = northNames + southNames
    col_w = (
        max(
            len(NORTH),
            len(SOUTH),
            len(ROUTING),
            max((len(n) for n in all_names), default=0),
        )
        + 2
    )
    horiz = "─" * col_w

    def _cell(text: str) -> str:
        return text.center(col_w)

    lines: list[str] = [
        header,
        f"┌{horiz}┐",
        f"│{_cell(NORTH)}│",
    ]
    for name in northNames:
        lines.append(f"│  {name.ljust(col_w - 2)}│")
    lines.append(f"├{horiz}┤")
    lines.append(f"│{_cell(ROUTING)}│")
    lines.append(f"├{horiz}┤")
    lines.append(f"│{_cell(SOUTH)}│")
    for name in southNames:
        lines.append(f"│  {name.ljust(col_w - 2)}│")
    lines.append(f"└{horiz}┘")
    return tuple(lines)
