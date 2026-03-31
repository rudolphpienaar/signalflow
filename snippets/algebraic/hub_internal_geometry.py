from signalflow.board import (
    Board,
    BoardChip,
    BoardChipPlacementPolicy,
    BoardKernel,
)

chip: BoardChip = chips.chip_get("Hub.ts", "process()")
kernel: BoardKernel = chip.internalBoard_get()
board: Board = kernel.board_get(
    chipPlacementPolicy=BoardChipPlacementPolicy.CENTROIDAL
)

print(board.geometry_text())
print()
print("region frames:")
for regionName, frame in sorted(board.geometry_get().regionFramesByName.items()):
    print(f"  {regionName}: {frame}")
print()
print("exact terminals:")
for chipName, terminalPositions in sorted(
    board.geometry_get().exactTerminalWorldPositionsByChip.items()
):
    print(f"  {chipName}:")
    for terminalName, worldPoint in sorted(terminalPositions.items()):
        print(f"    {terminalName}: {worldPoint}")
