"""Inspect symbolic channels and lanes for `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/hub_channels.py")
"""

from __future__ import annotations

from signalflow.board import (
    Board,
    BoardChannel,
    BoardChannels,
    BoardKernel,
    BoardLanes,
    BoardWiring,
    BoardZone,
)

zone: BoardZone = zones.zone_get(1, 1)
kernel: BoardKernel | None = zone.kernel_get("intra")
if kernel is None:
    raise RuntimeError("Expected intra kernel for zone (1,1)")
wiring: BoardWiring = kernel.wiring_get()
board: Board = kernel.board_get()
channels: BoardChannels = board.channels_get()
northChannel: BoardChannel | None = channels.channel_get("nLat")
northLanes: BoardLanes | None = (
    northChannel.lanes_get() if northChannel is not None else None
)

print(board.summary_sprint())
print()
print("board geometry:")
print(board.geometry_sprint())
if northLanes is not None:
    print()
    print("nLat lanes:")
    print(northLanes.list_sprint())
