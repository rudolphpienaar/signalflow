"""Unit tests for the VLSI Manifold Router (TDD)."""
from __future__ import annotations

# Standard library
import pytest

# Local
from signalflow.engine.router.router import VLSIRouter
from signalflow.engine.router.models import Terminal, Location, AttachmentPolicy, AttachmentSense


def test_fabric_init_density():
    """Verify that channels are correctly sized based on netlist density."""
    signals = [("s2", "out2"), ("s2", "out3"), ("s3", "out2")]
    router = VLSIRouter(signals)
    
    # Port s2 appears twice (as source), out2 twice (as dest), s3 once, out3 once
    assert router.LongitudeChannels["s2"].laneOccupancy == [False, False]
    assert router.LongitudeChannels["out2"].laneOccupancy == [False, False]
    assert router.LongitudeChannels["s3"].laneOccupancy == [False]
    assert router.LongitudeChannels["out3"].laneOccupancy == [False]


def test_route_lay_isolation():
    """Verify that logical threads are assigned unique lanes and rows."""
    signals = [("s2", "out2"), ("s2", "out3")]
    router = VLSIRouter(signals)
    
    t1 = Terminal("s2", Location.WESTSIDE, x=10, y=10)
    t2 = Terminal("out2", Location.EASTSIDE, x=40, y=10)
    t3 = Terminal("out3", Location.EASTSIDE, x=40, y=20)
    
    track1 = router.route_lay("s2:out2_0", t1, t2)
    track2 = router.route_lay("s2:out3_1", t1, t3)
    
    # Verify unique lanes in the shared longitude channel 's2'
    assert track1.segments[0][0].lane != track2.segments[0][0].lane

    # Both threads share the same grouped 's2' Latitude Channel but use different lanes
    assert track1.segments[1][1].channel == "s2"
    assert track2.segments[1][1].channel == "s2"
    assert track1.segments[1][1].lane != track2.segments[1][1].lane


def test_coordinate_mapping():
    """Verify that fabric coordinates map correctly to canvas (x, y)."""
    signals = [("s2", "out2")]
    router = VLSIRouter(signals)
    
    # Mock Chip at (10, 10), Width 30, Height 20
    chip_x, chip_y = 10, 10
    chip_ow = 30
    
    t1 = Terminal("s2", Location.WESTSIDE, x=chip_x, y=chip_y + 3)
    t2 = Terminal("out2", Location.EASTSIDE, x=chip_x + chip_ow - 1, y=chip_y + 3)
    
    track = router.route_lay("s2:out2_0", t1, t2)
    
    # Coordinate Resolver: translates abstract fabric to canvas (x,y)
    # We pass the chip state so the resolver knows the 'Longitude' column indices
    port_to_x = {"s2": chip_x + 2, "out2": chip_x + chip_ow - 3}
    # thread_to_y is keyed by source signal name (grouped Latitude Band base row)
    thread_to_y = {"s2": chip_y + 5}
    
    coords = router.canvas_coords_resolve(track, port_to_x, thread_to_y)
    
    # Waypoint 1: Port Exit (H)
    # Start at Wall (10, 13), Move to riser at (11, 13), then to track at (12, 13)
    assert (chip_x, t1.y) in coords
    assert (port_to_x["s2"], t1.y) in coords
    
    # Waypoint 2: Dogleg Alpha (V)
    # From (12, 13) to Flight Level row (12, 15)
    assert (port_to_x["s2"], thread_to_y["s2"]) in coords

    # Waypoint 3: Trunk (H)
    # From (12, 15) to (27, 15)
    assert (port_to_x["out2"], thread_to_y["s2"]) in coords
    
    # Waypoint 4: Dogleg Omega (V)
    # From (27, 15) to (27, 13)
    assert (port_to_x["out2"], t2.y) in coords
    
    # Waypoint 5: Port Entry (H)
    # From (27, 13) to Wall (29, 13)
    assert (t2.x, t2.y) in coords
