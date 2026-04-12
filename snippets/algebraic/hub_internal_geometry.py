from signalflow.board import (
    Board,
    BoardChip,
    BoardChipPlacementPolicy,
    BoardKernel,
    GeometryZone,
)

chip: BoardChip = chips.chip_get(  # type: ignore[name-defined]  # noqa: F821
    "Hub.ts", "process()"
)  # chips is injected by the SignalFlow REPL, not a module-level import
kernel: BoardKernel = chip.internalBoard_get()
board: Board = kernel.board_get(
    chipPlacementPolicy=BoardChipPlacementPolicy.CENTROIDAL
)

print(board.geometry_sprint())
print()
print("geometry zones:")
geometryZone: GeometryZone
for geometryZone in board.geometry_get().zones_get():
    print(f"  {geometryZone.summary_sprint()}")
print()
print("region frames:")
for regionName, frame in sorted(
    board.geometry_get().regionFramesByName.items()
):
    print(f"  {regionName}: {frame}")
print()
print("exact terminals:")
for chipName, terminalPositions in sorted(
    board.geometry_get().exactTerminalWorldPositionsByChip.items()
):
    print(f"  {chipName}:")
    for terminalName, worldPoint in sorted(terminalPositions.items()):
        print(f"    {terminalName}: {worldPoint}")
