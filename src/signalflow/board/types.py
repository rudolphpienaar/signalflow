"""Shared board-domain primitive types.

This module holds the low-level vocabulary that multiple board submodules need
to agree on. The goal is to avoid re-declaring slightly different coordinate
or frame concepts in geometry, layout, realization, and render code.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from signalflow.models import RoutingZoneRegionId, RoutingZoneRegionKind, RoutingZoneRegionSide


WorldPoint = tuple[int, int]


@dataclass(frozen=True)
class WorldFrame:
    """Inclusive world-coordinate frame for one board-owned object.

    The board package uses inclusive top-left and bottom-right coordinates for
    human-facing inspection because that matches how the debug surface discusses
    visible cells.
    """

    topLeft: WorldPoint
    bottomRight: WorldPoint

    @property
    def widthColumns(self) -> int:
        """Return the inclusive world width of the frame in columns."""

        return self.bottomRight[0] - self.topLeft[0] + 1

    @property
    def heightRows(self) -> int:
        """Return the inclusive world height of the frame in rows."""

        return self.bottomRight[1] - self.topLeft[1] + 1


class BoardSense(str, Enum):
    """Primary routing sense of a board substrate.

    The board package treats sense as a first-class geometric doctrine because
    it determines which channel family behaves as the carrier direction and
    which family behaves as the cross-bar direction.
    """

    WEST_TO_EAST = "WTE"
    EAST_TO_WEST = "ETW"
    NORTH_TO_SOUTH = "NTS"
    SOUTH_TO_NORTH = "STN"


class RegionFamily(str, Enum):
    """Canonical board-region families.

    These values replace overloaded string parsing in the new board package.
    A region family says what the area *is* without also trying to encode its
    side and optional subdivision into one name token.
    """

    CHIP_TERMINAL = "chip_terminal"
    INTRA_FAN = "intra_routing_fan_in_out"
    INTRA_TRANSITION = "intra_routing_transition"
    INTRA_LONGITUDE = "intra_routing_longitude"
    INTRA_LATITUDE = "intra_routing_latitude"
    INTER_FAN = "inter_routing_fan_in_out"
    INTER_TRANSITION = "inter_routing_transition"
    INTER_LONGITUDE = "inter_routing_longitude"
    INTER_LATITUDE = "inter_routing_latitude"
    EXTRA_LONGITUDE = "extra_routing_longitude"
    EXTRA_LATITUDE = "extra_routing_latitude"
    INTRA_EXTRA_TRANSFER = "intra_extra_transfer"


class BoardSide(str, Enum):
    """Cardinal board side for sided board regions."""

    WEST = "west"
    EAST = "east"
    NORTH = "north"
    SOUTH = "south"


class RegionBand(str, Enum):
    """Optional major-axis subdivision for split channel bands."""

    UPPER = "upper"
    LOWER = "lower"


class RegionBranch(str, Enum):
    """Optional branch quadrant for transition regions."""

    NORTH = "north"
    SOUTH = "south"


@dataclass(frozen=True)
class BoardRegionId:
    """Typed board-region identity.

    This is the canonical identity for regions inside the new board package.
    Human-readable labels such as `west/intra_routing_transition:north` are
    derived from this object at the edge instead of serving as the source of
    truth themselves.
    """

    family: RegionFamily
    side: BoardSide | None = None
    band: RegionBand | None = None
    branch: RegionBranch | None = None

    def label_build(self) -> str:
        """Format the region id using the legacy readable label shape."""

        label = self.family.value
        if self.side is not None:
            label = f"{self.side.value}/{label}"
        if self.band is not None:
            label = f"{label}:{self.band.value}"
        elif self.branch is not None:
            label = f"{label}:{self.branch.value}"
        return label


def boardRegionId_buildFromRoutingZoneRegionId(
    routingZoneRegionId: RoutingZoneRegionId,
) -> BoardRegionId:
    """Convert a legacy routing-zone region id into a board-region id."""

    familyByKind: dict[RoutingZoneRegionKind, RegionFamily] = {
        RoutingZoneRegionKind.CHIP_TERMINAL: RegionFamily.CHIP_TERMINAL,
        RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT: RegionFamily.INTRA_FAN,
        RoutingZoneRegionKind.INTRA_ROUTING_TRANSITION: RegionFamily.INTRA_TRANSITION,
        RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE: RegionFamily.INTRA_LONGITUDE,
        RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE: RegionFamily.INTRA_LATITUDE,
        RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT: RegionFamily.INTER_FAN,
        RoutingZoneRegionKind.INTER_ROUTING_TRANSITION: RegionFamily.INTER_TRANSITION,
        RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE: RegionFamily.INTER_LONGITUDE,
        RoutingZoneRegionKind.INTER_ROUTING_LATITUDE: RegionFamily.INTER_LATITUDE,
    }
    side: BoardSide | None = None
    if routingZoneRegionId.routingZoneRegionSide is not None:
        side = BoardSide(routingZoneRegionId.routingZoneRegionSide.value)

    band: RegionBand | None = None
    branch: RegionBranch | None = None
    tag = routingZoneRegionId.routingZoneRegionTag
    if tag in {RegionBand.UPPER.value, RegionBand.LOWER.value}:
        band = RegionBand(tag)
    elif tag in {RegionBranch.NORTH.value, RegionBranch.SOUTH.value}:
        branch = RegionBranch(tag)

    return BoardRegionId(
        family=familyByKind[routingZoneRegionId.routingZoneRegionKind],
        side=side,
        band=band,
        branch=branch,
    )


def boardRegionLabel_build(regionId: BoardRegionId) -> str:
    """Return the human-readable legacy-style label for one board region."""

    return regionId.label_build()


@dataclass(frozen=True)
class BoardChipDrawPlacement:
    """Canonical draw placement for one chip on one board.

    This is the board-owned render placement for a chip's canonical draw lines.
    Once effective-board doctrine is applied, these placements must move with
    the board so chip rendering, exact terminal positions, and routing
    substrate all remain coherent.
    """

    chipName: str
    moduleName: str
    side: BoardSide
    drawTopLeft: WorldPoint
    drawLines: tuple[str, ...]

    def worldFrame_get(self) -> WorldFrame:
        """Return the inclusive world frame of this chip's drawn block."""

        lineCount = len(self.drawLines)
        lineWidth = max((len(line) for line in self.drawLines), default=0)
        return WorldFrame(
            topLeft=self.drawTopLeft,
            bottomRight=(
                self.drawTopLeft[0] + lineWidth - 1,
                self.drawTopLeft[1] + lineCount - 1,
            ),
        )
