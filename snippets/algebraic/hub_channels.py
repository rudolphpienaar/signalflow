"""Inspect symbolic channels and lanes for `examples/hub.yaml`.

Run from the REPL with:
    load("snippets/algebraic/hub_channels.py")
"""

from __future__ import annotations

from signalflow.engine.debug import (
    DebugKernelBoardHandle,
    DebugKernelChannelHandle,
    DebugKernelChannelsHandle,
    DebugKernelHandle,
    DebugKernelLanesHandle,
    DebugKernelWiringHandle,
    DebugZoneHandle,
)

zone: DebugZoneHandle = zones.zone_get(1, 1)
kernel: DebugKernelHandle | None = zone.kernel_get("intra")
if kernel is None:
    raise RuntimeError("Expected intra kernel for zone (1,1)")
wiring: DebugKernelWiringHandle = kernel.wiring_get()
board: DebugKernelBoardHandle = kernel.board_get()
channels: DebugKernelChannelsHandle = board.channels_get()
northChannel: DebugKernelChannelHandle | None = channels.channel_get("nLat")
northLanes: DebugKernelLanesHandle | None = (
    northChannel.lanes_get() if northChannel is not None else None
)

print(board.summary_text())
print()
print("board geometry:")
print(board.geometry_text())
if northLanes is not None:
    print()
    print("nLat lanes:")
    print(northLanes.list_text())
