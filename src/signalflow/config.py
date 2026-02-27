"""Layout and rendering constants for the signalFlow diagram engine.

Single source of truth for all geometry parameters.  Import these symbols
directly; do not hard-code numeric literals elsewhere.

Constants:
    CHANNEL_W: Minimum horizontal gap (cols) between adjacent chip columns.
    ROW_GAP:   Blank canvas rows inserted between sibling subtrees.
    CHIP_PAD:  Minimum padding cols left and right of the func label inside a
               function chip.  Chip inner width = 2*CHIP_PAD + len(func_name).
    MB_OUTER:  Cols between chip edge and the module-box border (each side).
    MB_INNER:  Additional cols used as left-canvas margin for root chips.
    MB_TOP:    Canvas rows from module-box top border down to chip top row.
    BASE_LEAF: Height (rows) of a leaf chip: top + func + sep + entry + return + bottom.
    UTURN_W:   Width (cols) of the U-turn arm drawn inside a leaf chip.
"""
from __future__ import annotations

CHANNEL_W: int = 22   # horizontal gap between chip columns
ROW_GAP:   int = 6    # blank rows between sibling subtrees
CHIP_PAD:  int = 2    # minimum padding cols left/right of func name in chip
MB_OUTER:  int = 2    # cols from chip edge to module-box border (each side)
MB_INNER:  int = 4    # extra left-canvas margin for root chips
MB_TOP:    int = 3    # rows from module-box top to chip top
BASE_LEAF: int = 6    # leaf chip height
UTURN_W:   int = 3    # columns for the U-turn arm inside a leaf chip


class Wire:
    """Semantic tokens for wire segments and joins."""
    # Right-Sense (Flowing →)
    RT = '─'  # Horizontal
    RD = '┐'  # Right-then-Down
    RU = '┘'  # Right-then-Up
    DR = '└'  # Down-then-Right
    UR = '┌'  # Up-then-Right
    RJ = '├'  # Branch Right
    RA = '►'  # Arrow Right

    # Left-Sense (Flowing ←)
    LT = '─'  # Horizontal
    LD = '┌'  # Left-then-Down
    LU = '└'  # Left-then-Up
    DL = '┘'  # Down-then-Left
    UL = '┐'  # Up-then-Left
    LJ = '┤'  # Branch Left
    LA = '◄'  # Arrow Left

    # Universal
    DN = '│'  # Vertical Down
    UP = '│'  # Vertical Up
    CR = '┼'  # Crossing
    MC = '╫'  # Module Crossing
