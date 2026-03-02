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
        mode_merge: When True, set() performs an algebraic merge via LayoutJoiner.
    """

    rows: int
    cols: int
    grid: list[list[tuple[str, str | None]]] = field(default_factory=list)
    mode_merge: bool = False  # When True, set() performs an algebraic merge

    def __post_init__(self) -> None:
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
        """Write character at (x,y). Uses algebraic merge if mode_merge is True.

        Args:
            x: Column index.
            y: Row index.
            ch: Character glyph to place.
            color: Optional ANSI color escape code.
            mask: Optional directional intent bitmask for merging.
        """
        if not (0 <= y < self.rows and 0 <= x < self.cols):
            return

        from signalflow.lib.layout_joiner import LayoutJoiner

        if self.mode_merge:
            current, cur_color = self.grid[y][x]
            # Perform intermediate algebra (result may be a stub)
            new_ch: str = LayoutJoiner.glyph_merge(
                current, incoming_char=ch, incoming_mask=mask
            )
            self.grid[y][x] = (new_ch, color if color else cur_color)
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
        for x in range(x0, x1):
            self.set(x, y, ch, color)

    def hline_pierce(self, y: int, x0: int, x1: int, color: str | None = None) -> None:
        """Horizontal run from x0 to x1-1, using current mode and intent."""
        from signalflow.config import Wire
        from signalflow.lib.layout_joiner import LayoutJoiner

        if x1 <= x0:
            return
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
        flow: str = "down",
    ) -> None:
        """Vertical run from y0 to y1-1, using current mode and intent.

        Args:
            x: Column index.
            y0: Starting row index (inclusive, y0 < y1).
            y1: Ending row index (exclusive).
            ch: Optional override character glyph.
            color: Optional ANSI color escape code.
            flow: Direction of travel ('down' or 'up').
        """
        from signalflow.config import Wire
        from signalflow.lib.layout_joiner import LayoutJoiner

        if y1 <= y0:
            return
        char: str = ch if ch is not None else Wire.DN
        for y in range(y0, y1):
            # Default: Pass-through (both legs)
            intent: int = LayoutJoiner.N | LayoutJoiner.S

            if flow == "down":
                if y == y0:
                    intent = LayoutJoiner.S  # Start: Only has South leg
                if y == y1 - 1:
                    intent = LayoutJoiner.N  # End: Only has North leg
            else:  # UP flow (traveling from high row to low row)
                if y == y0:
                    intent = LayoutJoiner.S  # Destination: Terminal arrival from below (South leg)
                if y == y1 - 1:
                    intent = LayoutJoiner.N  # Source: Terminal departure upward (North leg)

            if y1 - y0 == 1:
                intent = LayoutJoiner.N | LayoutJoiner.S
            self.set(x, y, char, color, mask=intent)

    def text(self, x: int, y: int, s: str, color: str | None = None) -> None:
        """Write string starting at (x,y), overwriting existing chars."""
        for i, ch in enumerate(s):
            self.set(x + i, y, ch, color)

    def lines_get(self) -> list[str]:
        """Return canvas strings with final visual promotion."""
        from signalflow.lib.layout_joiner import LayoutJoiner

        RESET: Final[str] = "\033[0m"
        lines: list[str] = []
        for row in self.grid:
            line_parts: list[str] = []
            current_color: str | None = None
            for char, color in row:
                final_ch: str = LayoutJoiner.character_promote(char)
                if color != current_color:
                    if current_color is not None:
                        line_parts.append(RESET)
                    if color is not None:
                        line_parts.append(color)
                    current_color = color
                line_parts.append(final_ch)
            if current_color is not None:
                line_parts.append(RESET)
            lines.append("".join(line_parts).rstrip())
        while lines and not lines[-1]:
            lines.pop()
        return lines
