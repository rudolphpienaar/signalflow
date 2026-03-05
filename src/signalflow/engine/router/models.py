"""VLSI Router Models: Enums and Dataclasses for manifold synthesis (RPN Naming)."""
from __future__ import annotations

# Standard library
from dataclasses import dataclass, field
from enum import Enum, auto


class Location(Enum):
    """Physical placement of a terminal on the chip boundary."""
    EASTSIDE = auto()
    WESTSIDE = auto()


class Transversal(Enum):
    """Direction of travel within the Manhattan grid."""
    EASTWARDS = auto()
    WESTWARDS = auto()
    NORTHWARDS = auto()
    SOUTHWARDS = auto()


class AttachmentSense(Enum):
    """Heuristic for selecting a lane within a channel."""
    FROM_START = auto()  # Pack toward Top or Left (index 0)
    FROM_END = auto()    # Pack toward Bottom or Right (index -1)


class AttachmentDirection(Enum):
    """Vertical bias for dogleg segments."""
    FROM_BOTTOM = auto()
    FROM_TOP = auto()


class Waypoint(Enum):
    """The 5 discrete segments of a logical trace journey."""
    PORT_EXIT = auto()      # Terminal -> Vertical Channel (H)
    DOGLEG_ALPHA = auto()   # Local Vertical to Trunk Altitude (V)
    TRUNK = auto()          # Manifold Cross-over (H)
    DOGLEG_OMEGA = auto()   # Trunk Altitude to Destination altitude (V)
    PORT_ENTRY = auto()     # Vertical Channel -> Terminal (H)


@dataclass
class AttachmentPolicy:
    """Designer policy for global manifold geometry.

    Governs how threads attach to lanes across different transversals and edges.
    """
    eastEdge: AttachmentSense = AttachmentSense.FROM_START
    westEdge: AttachmentSense = AttachmentSense.FROM_END
    westTransversalInChannel: AttachmentSense = AttachmentSense.FROM_START
    eastTransversalInChannel: AttachmentSense = AttachmentSense.FROM_END
    northTransversalInChannel: AttachmentSense = AttachmentSense.FROM_START
    southTransversalInChannel: AttachmentSense = AttachmentSense.FROM_END


@dataclass
class Terminal:
    """Represents a physical Pin on the chip boundary."""
    label: str
    location: Location
    y: int  # Physical row coordinate
    x: int  # Physical column coordinate


@dataclass
class Coords:
    """Coordinate within the Routing Fabric (not global canvas coordinates)."""
    channel: str
    lane: int


@dataclass
class Track:
    """A collection of fabric coordinates representing a complete trace path."""
    signal_id: str
    segments: list[list[Coords]] = field(default_factory=list)
    noCollisions: bool = True
    length: int = 0


class Channel:
    """A band of lanes reserved for logical interconnects.

    Maintains occupancy state to prevent trace coincidence.
    """
    def __init__(self, name: str, size: int, sense: Transversal):
        self.name: str = name
        self.sense: Transversal = sense
        self.laneOccupancy: list[bool] = [False] * size

    def lane_allocate(self, sense: AttachmentSense) -> int:
        """RPN: lane_allocate - Find and reserve the next available lane.

        Args:
            sense: The attachment sense (FROM_START or FROM_END).

        Returns:
            The index of the allocated lane.

        Raises:
            IndexError: If no lanes are available in this channel.
        """
        indices = range(len(self.laneOccupancy))
        if sense == AttachmentSense.FROM_END:
            indices = reversed(indices)

        for i in indices:
            if not self.laneOccupancy[i]:
                self.laneOccupancy[i] = True
                return i

        raise IndexError(f"Channel '{self.name}' is saturated (Density violation).")

    def laneOccupied_check(self, lane_idx: int) -> bool:
        """RPN: laneOccupied_check - Check if a specific lane is in use."""
        if 0 <= lane_idx < len(self.laneOccupancy):
            return self.laneOccupancy[lane_idx]
        return True
