"""Inspect reconstructed WiringSolution objects for `Hub.ts.process()`.

Run from the REPL with:
    load("snippets/algebraic/hub_internal_wiring_solution.py")
"""

from __future__ import annotations

from signalflow.board import (
    Board,
    BoardChip,
    BoardChipPlacementPolicy,
    BoardKernel,
    BoardSolver,
    BoardWiring,
    boardChannelLaneCounts_build,
)
from signalflow.notation import (
    WTE_INTRA_FORWARD,
    WTE_INTRA_RETURN,
    WiringSolution,
)

chip: BoardChip = chips.chip_get("Hub.ts", "process()")
kernel: BoardKernel = chip.internalBoard_get()
board: Board = kernel.board_get(
    chipPlacementPolicy=BoardChipPlacementPolicy.CENTROIDAL
)
solver: BoardSolver = kernel.solver_get(board)
wiring: BoardWiring = solver.wiring_get()
channelLaneCounts: dict[str, int] = boardChannelLaneCounts_build(board)

forwardWiringSolution: WiringSolution = WiringSolution(
    topology=WTE_INTRA_FORWARD,
    channelLaneCounts=channelLaneCounts,
)
returnWiringSolution: WiringSolution = WiringSolution(
    topology=WTE_INTRA_RETURN,
    channelLaneCounts=channelLaneCounts,
)

for wire in wiring.all_get():
    targetWiringSolution: WiringSolution = (
        returnWiringSolution if wire.isReturn else forwardWiringSolution
    )
    targetWiringSolution.wire_add(
        source=wire.sourceEndpointText,
        sink=wire.destinationEndpointText,
    )

print("board channelLaneCounts:")
print(channelLaneCounts)
print()

print("forward wiring solution:")
print(f"  laneCount: {forwardWiringSolution.laneCount_get()}")
print(f"  kernel_wiring: {forwardWiringSolution.kernel_wiring}")
if forwardWiringSolution.laneCount_get() > 0:
    print(f"  laneMap[0]: {forwardWiringSolution.laneMap_get(0)}")
    print(
        "  path[0]: "
        f"{forwardWiringSolution.paths_get()[0].text_sprint().value}"
    )
print()

print("return wiring solution:")
print(f"  laneCount: {returnWiringSolution.laneCount_get()}")
print(f"  kernel_wiring: {returnWiringSolution.kernel_wiring}")
if returnWiringSolution.laneCount_get() > 0:
    print(f"  laneMap[0]: {returnWiringSolution.laneMap_get(0)}")
    print(
        "  path[0]: "
        f"{returnWiringSolution.paths_get()[0].text_sprint().value}"
    )
