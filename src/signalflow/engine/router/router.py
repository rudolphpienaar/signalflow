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
        self.LatitudeChannels: dict[str, Channel] = {}
        self.LongitudeChannels: dict[str, Channel] = {}
        self.tracks: list[Track] = []
        
        # DRC Engine
        self.occupancy = OccupancyGrid()

        self.fabric_init()

    def fabric_init(self) -> None:
        """RPN: fabric_init - Analyze netlist density and synthesize channels."""
        # 1. Group signals by port to determine required capacity
        l_counts: dict[str, int] = {}  # Longitude (Vertical) channels
        h_counts: dict[str, int] = {}  # Latitude (Horizontal) channels

        for src, dst in self.signals:
            l_counts[src] = l_counts.get(src, 0) + 1
            l_counts[dst] = l_counts.get(dst, 0) + 1
            # Group horizontal flight levels by source signal name (the band)
            h_counts[src] = h_counts.get(src, 0) + 1

        # 2. Instantiate Channels
        for port, density in l_counts.items():
            # Longitude channels are vertical bands
            self.LongitudeChannels[port] = Channel(
                port, density, Transversal.NORTHWARDS
            )

        for signal_name, lane_count in h_counts.items():
            # Latitude channels are horizontal bands, grouped by source signal name
            self.LatitudeChannels[signal_name] = Channel(
                signal_name, lane_count, Transversal.EASTWARDS
            )

    def route_lay(self, signal_id: str, start: Terminal, end: Terminal) -> Track:
        """RPN: route_lay - Synthesize a 5-waypoint trace for a logical connection.

        Args:
            signal_id: Unique identifier for the logical thread.
            start: The physical entry Pin.
            end: The physical exit Pin.

        Returns:
            A Track instance containing the fabric coordinates.
        """
        track = Track(signal_id)

        # Waypoint 1: Port Exit (Terminal -> Longitude Channel)
        l_chan_src = self.LongitudeChannels[start.label]
        sense_src = (
            self.policy.westEdge
            if start.location == Location.WESTSIDE
            else self.policy.eastEdge
        )
        l_lane_src = l_chan_src.lane_allocate(sense_src)

        # Waypoint 2: Dogleg Alpha (Local Vertical to Trunk Altitude)
        # base_id is the source signal name — the grouped Latitude Channel key
        base_id = signal_id.split(":")[0]
        h_chan = self.LatitudeChannels[base_id]
        h_lane = h_chan.lane_allocate(AttachmentSense.FROM_START)

        # Waypoint 3: The Trunk (Manifold Cross-over)
        l_chan_dst = self.LongitudeChannels[end.label]
        sense_dst = (
            self.policy.westEdge
            if end.location == Location.WESTSIDE
            else self.policy.eastEdge
        )
        l_lane_dst = l_chan_dst.lane_allocate(sense_dst)

        # Assemble Segments (Fabric Coordinate Mapping)
        track.start_terminal = start
        track.end_terminal = end
        track.l_lane_src = l_lane_src
        track.h_lane = h_lane
        track.l_lane_dst = l_lane_dst
        track.h_chan_name = base_id

        track.segments = [
            [Coords(start.label, l_lane_src)], # W1: Port Exit (H)
            [Coords(start.label, l_lane_src), Coords(base_id, h_lane)], # W2: Dogleg Alpha (V)
            [Coords(base_id, h_lane)], # W3: Trunk (H)
            [Coords(base_id, h_lane), Coords(end.label, l_lane_dst)], # W4: Dogleg Omega (V)
            [Coords(end.label, l_lane_dst)]  # W5: Port Entry (H)
        ]

        self.tracks.append(track)
        return track

    def canvas_coords_resolve(
        self,
        track: Track,
        port_to_x: dict[str, int],
        thread_to_y: dict[str, int],
    ) -> list[tuple[int, int]]:
        """RPN: canvas_coords_resolve - Map fabric coordinates to canvas points."""
        v_x_src = port_to_x[track.start_terminal.label] + 2 * track.l_lane_src
        v_x_dst = port_to_x[track.end_terminal.label] + 2 * track.l_lane_dst
        logical_y = thread_to_y[track.h_chan_name] + track.h_lane

        return [
            (track.start_terminal.x, track.start_terminal.y), # Start at Wall
            (v_x_src, track.start_terminal.y),               # Exit to Track
            (v_x_src, logical_y),                            # Dogleg Alpha
            (v_x_dst, logical_y),                            # Trunk Cross
            (v_x_dst, track.end_terminal.y),                 # Dogleg Omega
            (track.end_terminal.x, track.end_terminal.y)     # Entry to Wall
        ]

    def trackClear_check(
        self, 
        track: Track, 
        port_to_x: dict[str, int], 
        thread_to_y: dict[str, int]
    ) -> bool:
        """RPN: trackClear_check - Verify no coincidence with existing tracks.

        Checks every discrete cell on the track's path against the occupancy grid.
        Note: Point intersections (Crossings) are ignored; only segments are 
        checked for coincidence.
        """
        points = self.canvas_coords_resolve(track, port_to_x, thread_to_y)
        
        # Test each segment for reservation
        for i in range(len(points) - 1):
            if not self.occupancy.range_reserve(points[i], points[i+1]):
                return False
        return True

    def track_reroute(self, track: Track) -> tuple[str, int] | None:
        """RPN: track_reroute - Return resource request for adaptive expansion.

        Returns:
            Tuple of (channel_name, required_increment) or None.
        """
        # Simple heuristic: request 1 more lane for the source channel
        return (track.start_terminal.label, 1)
