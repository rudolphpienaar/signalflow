"""Canvas dataclass: 2D mutable character grid with draw primitives (RPN Naming)."""
from __future__ import annotations

# Standard library
from dataclasses import dataclass, field
from typing import Final


@dataclass
class Canvas:
    """A 2D mutable character grid with ANSI color support.

    Attributes:
        rows: Number of rows in the canvas.
        cols: Number of columns in the canvas.
        grid: 2D list of (character, color) tuples.
        modeMerge: When True, set() performs an algebraic merge via LayoutJoiner.
    """

    rows: int
    cols: int
    grid: list[list[tuple[str, str | None]]] = field(default_factory=list)
    modeMerge: bool = False  # When True, set() performs an algebraic merge

    def __post_init__(self) -> None:
        """Allocate the backing grid when one was not supplied explicitly."""
        if not self.grid:
            self.grid = [[(" ", None)] * self.cols for _ in range(self.rows)]

    def set(
        self,
        x: int,
        y: int,
        ch: str,
        color: str | None = None,
        mask: int | None = None,
    ) -> None:
        """Write character at (x,y). Uses algebraic merge if modeMerge is True.

        Args:
            x: Column index.
            y: Row index.
            ch: Character glyph to place.
            color: Optional ANSI color escape code.
            mask: Optional directional intent bitmask for merging.
        """
        if not (0 <= y < self.rows and 0 <= x < self.cols):
            if __debug__:
                raise IndexError(
                    f"Canvas OOB: ({x},{y}) in {self.cols}×{self.rows}"
                )
            return

        from signalflow.lib.layout_joiner import LayoutJoiner
        if self.modeMerge:
            current: str
            curColor: str | None
            current, curColor = self.grid[y][x]
            # Perform intermediate algebra (result may be a stub)
            newCh: str = LayoutJoiner.glyph_merge(
                current, incomingChar=ch, incomingMask=mask
            )
            self.grid[y][x] = (newCh, color if color else curColor)
        else:
            # Overwrite mode: standard placement
            self.grid[y][x] = (ch, color)

    def get(self, x: int, y: int) -> str:
        """Read character at (x,y)."""
        if 0 <= y < self.rows and 0 <= x < self.cols:
            return self.grid[y][x][0]
        return " "

    def hline_force(
        self, y: int, x0: int, x1: int, ch: str = "─", color: str | None = None
    ) -> None:
        """Horizontal run overwriting content."""
        x: int
        for x in range(x0, x1):
            self.set(x, y, ch, color)

    def hline_pierce(self, y: int, x0: int, x1: int, color: str | None = None) -> None:
        """Horizontal run from x0 to x1-1, using current mode and intent."""
        from signalflow.config import Wire
        from signalflow.lib.layout_joiner import LayoutJoiner

        if x1 <= x0:
            return
        x: int
        for x in range(x0, x1):
            intent: int = LayoutJoiner.E | LayoutJoiner.W
            if x == x0:
                intent = LayoutJoiner.E  # Start (East leg only)
            if x == x1 - 1:
                intent = LayoutJoiner.W  # End (West leg only)
            if x1 - x0 == 1:
                intent = LayoutJoiner.E | LayoutJoiner.W
            self.set(x, y, Wire.RT, color, mask=intent)

    def vline(
        self,
        x: int,
        y0: int,
        y1: int,
        ch: str | None = None,
        color: str | None = None,
        pass_through: bool = False,
    ) -> None:
        """Vertical run from y0 to y1-1, using current mode and intent.

        Args:
            x: Column index.
            y0: Starting row index (inclusive, y0 < y1).
            y1: Ending row index (exclusive).
            ch: Optional override character glyph.
            color: Optional ANSI color escape code.
            pass_through: When True, all cells use N|S (full pass-through intent),
                allowing crossings with hlines to merge into ┼. When False (default),
                endpoints use directional stubs so vline+hline endpoint merges
                produce proper corners (┌/┐/└/┘).
        """
        from signalflow.config import Wire
        from signalflow.lib.layout_joiner import LayoutJoiner

        if y1 <= y0:
            return
        char: str = ch if ch is not None else Wire.DN
        y: int
        for y in range(y0, y1):
            if pass_through or y1 - y0 == 1:
                intent: int = LayoutJoiner.N | LayoutJoiner.S
            else:
                if y == y0:
                    intent = LayoutJoiner.S
                elif y == y1 - 1:
                    intent = LayoutJoiner.N
                else:
                    intent = LayoutJoiner.N | LayoutJoiner.S
            self.set(x, y, char, color, mask=intent)

    def text(self, x: int, y: int, s: str, color: str | None = None) -> None:
        """Write string starting at (x,y), overwriting existing chars."""
        i: int
        ch: str
        for i, ch in enumerate(s):
            self.set(x + i, y, ch, color)

    def lines_get(self) -> list[str]:
        """Return canvas strings with final visual promotion."""
        from signalflow.lib.layout_joiner import LayoutJoiner

        RESET: Final[str] = "\033[0m"
        lines: list[str] = []
        row: list[tuple[str, str | None]]
        for row in self.grid:
            lineParts: list[str] = []
            currentColor: str | None = None
            char: str
            color: str | None
            for char, color in row:
                finalCh: str = LayoutJoiner.character_promote(char)
                if color != currentColor:
                    if currentColor is not None:
                        lineParts.append(RESET)
                    if color is not None:
                        lineParts.append(color)
                    currentColor = color
                lineParts.append(finalCh)
            if currentColor is not None:
                lineParts.append(RESET)
            lines.append("".join(lineParts).rstrip())
        while lines and not lines[-1]:
            lines.pop()
        return lines
