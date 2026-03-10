"""Unit tests for the VLSI Manifold Router (TDD)."""
from __future__ import annotations

# Standard library
from signalflow.engine.router.models import (
    Location,
    Terminal,
    Track,
)

# Local
from signalflow.engine.router.router import VLSIRouter


def test_fabric_init_density():
    """Verify that channels are correctly sized based on netlist density."""
    signals: list[tuple[str, str]] = [("s2", "out2"), ("s2", "out3"), ("s3", "out2")]
    router: VLSIRouter = VLSIRouter(signals)

    # Port s2 appears twice (as source), out2 twice (as dest), s3 once, out3 once
    assert router.longitudeChannels["s2"].laneOccupancy == [False, False]
    assert router.longitudeChannels["out2"].laneOccupancy == [False, False]
    assert router.longitudeChannels["s3"].laneOccupancy == [False]
    assert router.longitudeChannels["out3"].laneOccupancy == [False]


def test_route_lay_isolation():
    """Verify that logical threads are assigned unique lanes and rows."""
    signals: list[tuple[str, str]] = [("s2", "out2"), ("s2", "out3")]
    router: VLSIRouter = VLSIRouter(signals)

    t1: Terminal = Terminal("s2", Location.WESTSIDE, x=10, y=10)
    t2: Terminal = Terminal("out2", Location.EASTSIDE, x=40, y=10)
    t3: Terminal = Terminal("out3", Location.EASTSIDE, x=40, y=20)

    track1: Track = router.route_lay("s2:out2_0", t1, t2)
    track2: Track = router.route_lay("s2:out3_1", t1, t3)

    # Verify unique lanes in the shared longitude channel 's2'
    assert track1.segments[0][0].lane != track2.segments[0][0].lane

    # Both threads share the same grouped 's2' Latitude Channel but use different lanes
    assert track1.segments[1][1].channel == "s2"
    assert track2.segments[1][1].channel == "s2"
    assert track1.segments[1][1].lane != track2.segments[1][1].lane


def test_coordinate_mapping():
    """Verify that fabric coordinates map correctly to canvas (x, y)."""
    signals: list[tuple[str, str]] = [("s2", "out2")]
    router: VLSIRouter = VLSIRouter(signals)

    # Mock Chip at (10, 10), Width 30, Height 20
    chipX: int = 10
    chipY: int = 10
    chipOw: int = 30

    t1: Terminal = Terminal("s2", Location.WESTSIDE, x=chipX, y=chipY + 3)
    t2: Terminal = Terminal(
        "out2",
        Location.EASTSIDE,
        x=chipX + chipOw - 1,
        y=chipY + 3,
    )

    track: Track = router.route_lay("s2:out2_0", t1, t2)

    # Coordinate Resolver: translates abstract fabric to canvas (x,y)
    # We pass the chip state so the resolver knows the 'Longitude' column indices
    portToX: dict[str, int] = {"s2": chipX + 2, "out2": chipX + chipOw - 3}
    # threadToY is keyed by source signal name (grouped Latitude Band base row)
    threadToY: dict[str, int] = {"s2": chipY + 5}

    coords: list[tuple[int, int]] = router.canvasCoords_resolve(
        track, portToX, threadToY
    )

    # Waypoint 1: Port Exit (H)
    # Start at Wall (10, 13), Move to riser at (11, 13), then to track at (12, 13)
    assert (chipX, t1.y) in coords
    assert (portToX["s2"], t1.y) in coords

    # Waypoint 2: Dogleg Alpha (V)
    # From (12, 13) to Flight Level row (12, 15)
    assert (portToX["s2"], threadToY["s2"]) in coords

    # Waypoint 3: Trunk (H)
    # From (12, 15) to (27, 15)
    assert (portToX["out2"], threadToY["s2"]) in coords

    # Waypoint 4: Dogleg Omega (V)
    # From (27, 15) to (27, 13)
    assert (portToX["out2"], t2.y) in coords

    # Waypoint 5: Port Entry (H)
    # From (27, 13) to Wall (29, 13)
    assert (t2.x, t2.y) in coords
