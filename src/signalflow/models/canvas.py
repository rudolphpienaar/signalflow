"""Canvas dataclass: 2D mutable character grid with draw primitives."""

from dataclasses import dataclass, field


@dataclass
class Canvas:
    """A 2D mutable character grid.

    Attributes:
        rows: Number of character rows.
        cols: Number of character columns.
        grid: 2D list[list[str]], filled with spaces.
    """
    rows: int
    cols: int
    grid: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.grid:
            self.grid = [[' '] * self.cols for _ in range(self.rows)]

    def set(self, x: int, y: int, ch: str) -> None:
        """Write ch at (x,y). Silently ignore out-of-bounds."""
        if 0 <= y < self.rows and 0 <= x < self.cols:
            self.grid[y][x] = ch

    def get(self, x: int, y: int) -> str:
        """Read char at (x,y). Return ' ' for out-of-bounds."""
        if 0 <= y < self.rows and 0 <= x < self.cols:
            return self.grid[y][x]
        return ' '

    def hline(self, y: int, x0: int, x1: int, ch: str = '─') -> None:
        """Horizontal run of ch from x0 to x1-1 on row y (space-only cells)."""
        for x in range(x0, x1):
            if self.get(x, y) == ' ':
                self.set(x, y, ch)

    def hline_force(self, y: int, x0: int, x1: int, ch: str = '─') -> None:
        """Horizontal run of ch overwriting whatever is there."""
        for x in range(x0, x1):
            self.set(x, y, ch)

    def vline(self, x: int, y0: int, y1: int, ch: str | None = None) -> None:
        """Vertical run from y0 to y1-1 on col x, piercing horizontal wires."""
        from signalflow.config import Wire
        char = ch if ch is not None else Wire.DN
        # Turn characters that must be protected
        turns = ('┌', '┐', '└', '┘', Wire.RD, Wire.RU, Wire.DR, Wire.UR, Wire.LD, Wire.LU, Wire.DL, Wire.UL)
        
        for y in range(y0, y1):
            current = self.get(x, y)
            if current in turns:
                continue
            if current in (' ', Wire.DN, '╪'):
                self.set(x, y, char if current != '╪' else '╪')
            elif current == Wire.RT:
                self.set(x, y, Wire.CR)
            elif current == '═':
                self.set(x, y, '╪')

    def text(self, x: int, y: int, s: str) -> None:
        """Write string s starting at (x,y), overwriting existing chars."""
        from signalflow.config import Wire
        for i, ch in enumerate(s):
            target_x = x + i
            if self.get(target_x, y) == '║':
                self.set(target_x, y, Wire.MC)
            self.set(target_x, y, ch)

    def lines_get(self) -> list:
        """Return canvas as list of strings, trailing spaces and blank bottom rows
        stripped."""
        lines = [''.join(row).rstrip() for row in self.grid]
        while lines and not lines[-1]:
            lines.pop()
        return lines
