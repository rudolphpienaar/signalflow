"""High-resolution Occupancy Grid for Design Rule Checking (RPN Naming)."""
from __future__ import annotations

# Standard library


class OccupancyGrid:
    """A 2D bitset-like structure to track canvas usage.

    Enforces the 'Non-Coincidence' rule by proving that no two logical
    segments share a coordinate range.
    """

    def __init__(self) -> None:
        """RPN: __init__ - Initialize the grid."""
        # We use a set of (x,y) tuples for simplicity and infinite 'virtual' resolution
        self.usedCells: set[tuple[int, int]] = set()

    def cell_reserve(self, x: int, y: int) -> bool:
        """RPN: cell_reserve - Mark a cell as occupied.

        Returns:
            True if cell was successfully reserved,
            False if a collision was detected.
        """
        if (x, y) in self.usedCells:
            return False
        self.usedCells.add((x, y))
        return True

    def range_reserve(self, p0: tuple[int, int], p1: tuple[int, int]) -> bool:
        """RPN: range_reserve - Mark a Manhattan range as occupied.

        Args:
            p0: Start (x, y) tuple.
            p1: End (x, y) tuple.

        Returns:
            True if entire range was successfully reserved,
            False if ANY collision was detected.
        """
        x0, y0 = p0
        x1, y1 = p1

        # Determine movement range
        dx: int = 1 if x1 >= x0 else -1
        dy: int = 1 if y1 >= y0 else -1

        cellsToReserve: list[tuple[int, int]] = []

        # Manhattan check: either x changes or y changes, not both simultaneously
        # (Choreography ensures this)
        if y0 == y1:
            # Horizontal range
            x: int
            for x in range(x0, x1 + dx, dx):
                cellsToReserve.append((x, y0))
        elif x0 == x1:
            # Vertical range
            y: int
            for y in range(y0, y1 + dy, dy):
                cellsToReserve.append((x0, y))
        else:
            # Diagonal (Unexpected in Manhattan grid)
            return False

        # Atomic reservation check
        cell: tuple[int, int]
        for cell in cellsToReserve:
            if cell in self.usedCells:
                return False

        # Success: commit reservation
        for cell in cellsToReserve:
            self.usedCells.add(cell)
        return True

    def cellOccupied_check(self, x: int, y: int) -> bool:
        """RPN: cellOccupied_check - Verify if a cell is in use."""
        return (x, y) in self.usedCells
