"""Layout and rendering constants for the signalFlow diagram engine.

Single source of truth for all geometry parameters.  Import the 'config'
singleton instance to access live parameters.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Config:
    """System-wide rendering parameters."""
    channelWidth:        int = 22   # Min horizontal gap between columns
    verticalChipPadding: int = 4    # Blank rows between sibling subtrees
    chipPaddingX:        int = 2    # Min padding left/right of func name in chip
    moduleOuterWidth:    int = 2    # Cols between chip and module border
    moduleInnerMargin:   int = 4    # Extra left margin for root chips
    moduleTopRows:       int = 3    # Rows from module top to chip top
    modulePadding:       int = 2    # Gap between content and module wall
    baseLeafHeight:      int = 6    # Standard leaf chip height
    uTurnWidth:          int = 3    # Columns for the leaf U-turn arm
    portVerticalSpacing: int = 3    # Rows between physical ports on a chip
    internalWireColorize: bool = False # Enable ANSI colors for internal wiring
    share_internal_routes: bool = False # Disable track-sharing for clean junctions

    def config_update(self, data: dict) -> None:
        """Update singleton properties from a dictionary."""
        if 'internalWireColorize' in data:
            self.internalWireColorize = bool(data['internalWireColorize'])
        if 'verticalChipPadding' in data:
            self.verticalChipPadding = int(data['verticalChipPadding'])
        if 'channelWidth' in data:
            self.channelWidth = int(data['channelWidth'])
        if 'portVerticalSpacing' in data:
            self.portVerticalSpacing = int(data['portVerticalSpacing'])
        if 'share_internal_routes' in data:
            self.share_internal_routes = bool(data['share_internal_routes'])



# Singleton instance for the current render session
config = Config()


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

    # Junctions
    TJ = '┬'  # Top Junction (Down-flow)
    BJ = '┴'  # Bottom Junction (Up-flow)
    LJ = '┤'  # Left Junction
    RJ = '├'  # Right Junction

    # Atomic Terminals
    N_TERM = '╵'
    S_TERM = '╷'
    E_TERM = '╶'
    W_TERM = '╴'

    # Universal
    DN = '│'  # Vertical Down
    UP = '│'  # Vertical Up
    CR = '┼'  # Crossing
    MC = '╫'  # Module Crossing
