"""VLSI Manifold Router: Manhattan-Zoned Schematic Synthesizer (RPN Naming)."""
from __future__ import annotations

# Local
from signalflow.engine.router.models import (
    AttachmentPolicy,
    AttachmentSense,
    Channel,
    Coords,
    Location,
    Terminal,
    Track,
    Transversal,
)
from signalflow.engine.router.occupancy import OccupancyGrid


class VLSIRouter:
    """Orchestrates the physical synthesis of logical manifolds.

    Implements the Zoned Channel model where every trace follows a 5-step
    waypoint journey through dynamic orthogonal lanes.
    """

    def __init__(
        self, signals: list[tuple[str, str]], policy: AttachmentPolicy | None = None
    ):
        """RPN: __init__ - Initialize the routing fabric.

        Args:
            signals: List of (src_port, dst_port) logical pairs.
            policy: Optional AttachmentPolicy override.
        """
        self.signals: list[tuple[str, str]] = signals
        self.policy: AttachmentPolicy = policy if policy else AttachmentPolicy()

        # Routing Fabric State
        self.latitudeChannels: dict[str, Channel] = {}
        self.longitudeChannels: dict[str, Channel] = {}
        self.tracks: list[Track] = []

        # DRC Engine
        self.occupancy: OccupancyGrid = OccupancyGrid()

        self.fabric_init()

    def fabric_init(self) -> None:
        """RPN: fabric_init - Analyze netlist density and synthesize channels."""
        # 1. Group signals by port to determine required capacity
        lCounts: dict[str, int] = {}  # Longitude (Vertical) channels
        hCounts: dict[str, int] = {}  # Latitude (Horizontal) channels

        src: str
        dst: str
        for src, dst in self.signals:
            lCounts[src] = lCounts.get(src, 0) + 1
            lCounts[dst] = lCounts.get(dst, 0) + 1
            # Group horizontal flight levels by source signal name (the band)
            hCounts[src] = hCounts.get(src, 0) + 1

        # 2. Instantiate Channels
        port: str
        density: int
        for port, density in lCounts.items():
            # Longitude channels are vertical bands
            self.longitudeChannels[port] = Channel(
                port, density, Transversal.NORTHWARDS
            )

        signalName: str
        laneCount: int
        for signalName, laneCount in hCounts.items():
            # Latitude channels are horizontal bands, grouped by source signal name
            self.latitudeChannels[signalName] = Channel(
                signalName, laneCount, Transversal.EASTWARDS
            )

    def route_lay(self, signalId: str, start: Terminal, end: Terminal) -> Track:
        """RPN: route_lay - Synthesize a 5-waypoint trace for a logical connection.

        Args:
            signalId: Unique identifier for the logical thread.
            start: The physical entry Pin.
            end: The physical exit Pin.

        Returns:
            A Track instance containing the fabric coordinates.
        """
        track: Track = Track(signalId)

        # Waypoint 1: Port Exit (Terminal -> Longitude Channel)
        lChanSrc: Channel = self.longitudeChannels[start.label]
        senseSrc: AttachmentSense = (
            self.policy.westEdge
            if start.location == Location.WESTSIDE
            else self.policy.eastEdge
        )
        lLaneSrc: int = lChanSrc.lane_allocate(senseSrc)

        # Waypoint 2: Dogleg Alpha (Local Vertical to Trunk Altitude)
        # baseId is the source signal name — the grouped Latitude Channel key
        baseId: str = signalId.split(":")[0]
        hChan: Channel = self.latitudeChannels[baseId]
        hLane: int = hChan.lane_allocate(AttachmentSense.FROM_START)

        # Waypoint 3: The Trunk (Manifold Cross-over)
        lChanDst: Channel = self.longitudeChannels[end.label]
        senseDst: AttachmentSense = (
            self.policy.westEdge
            if end.location == Location.WESTSIDE
            else self.policy.eastEdge
        )
        lLaneDst: int = lChanDst.lane_allocate(senseDst)

        # Assemble Segments (Fabric Coordinate Mapping)
        track.start_terminal = start
        track.end_terminal = end
        track.l_lane_src = lLaneSrc
        track.h_lane = hLane
        track.l_lane_dst = lLaneDst
        track.h_chan_name = baseId

        track.segments = [
            [Coords(start.label, lLaneSrc)],  # W1: Port Exit (H)
            [
                Coords(start.label, lLaneSrc),
                Coords(baseId, hLane),
            ],  # W2: Dogleg Alpha (V)
            [Coords(baseId, hLane)],  # W3: Trunk (H)
            [
                Coords(baseId, hLane),
                Coords(end.label, lLaneDst),
            ],  # W4: Dogleg Omega (V)
            [Coords(end.label, lLaneDst)],  # W5: Port Entry (H)
        ]

        self.tracks.append(track)
        return track

    def canvasCoords_resolve(
        self,
        track: Track,
        portToX: dict[str, int],
        threadToY: dict[str, int],
    ) -> list[tuple[int, int]]:
        """RPN: canvasCoords_resolve - Map fabric coordinates to canvas points."""
        vXSrc: int = portToX[track.start_terminal.label] + 2 * track.l_lane_src
        vXDst: int = portToX[track.end_terminal.label] + 2 * track.l_lane_dst
        logicalY: int = threadToY[track.h_chan_name] + track.h_lane

        return [
            (track.start_terminal.x, track.start_terminal.y),  # Start at Wall
            (vXSrc, track.start_terminal.y),  # Exit to Track
            (vXSrc, logicalY),  # Dogleg Alpha
            (vXDst, logicalY),  # Trunk Cross
            (vXDst, track.end_terminal.y),  # Dogleg Omega
            (track.end_terminal.x, track.end_terminal.y),  # Entry to Wall
        ]

    def trackClear_check(
        self,
        track: Track,
        portToX: dict[str, int],
        threadToY: dict[str, int],
    ) -> bool:
        """RPN: trackClear_check - Verify no coincidence with existing tracks.

        Checks every discrete cell on the track's path against the occupancy grid.
        Note: Point intersections (Crossings) are ignored; only segments are
        checked for coincidence.
        """
        points: list[tuple[int, int]] = self.canvasCoords_resolve(
            track, portToX, threadToY
        )

        # Test each segment for reservation
        i: int
        for i in range(len(points) - 1):
            if not self.occupancy.range_reserve(points[i], points[i + 1]):
                return False
        return True

    def track_reroute(self, track: Track) -> tuple[str, int] | None:
        """RPN: track_reroute - Return resource request for adaptive expansion.

        Returns:
            Tuple of (channel_name, required_increment) or None.
        """
        # Simple heuristic: request 1 more lane for the source channel
        return (track.start_terminal.label, 1)
