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
    shareInternalRoutes: bool = False # Disable track-sharing for clean junctions
    chipIoInputExplicit: bool = True  # True: one port per caller; False: one port per function

    def config_update(self, data: dict) -> None:
        """Update singleton properties from a dictionary."""
        # 1. Top-level direct parameters
        if "channelWidth" in data:
            self.channelWidth = int(data["channelWidth"])
        if "verticalChipPadding" in data:
            self.verticalChipPadding = int(data["verticalChipPadding"])

        # 2. Nested internal_wiring section
        if "internal_wiring" in data and isinstance(data["internal_wiring"], dict):
            iw: dict = data["internal_wiring"]
            if "colorize" in iw:
                self.internalWireColorize = bool(iw["colorize"])
            if "shareRoutes" in iw:
                self.shareInternalRoutes = bool(iw["shareRoutes"])
            if "portSpacing" in iw:
                self.portVerticalSpacing = int(iw["portSpacing"])

        # 3. Nested chip_io section
        if "chip_io" in data and isinstance(data["chip_io"], dict):
            cio: dict = data["chip_io"]
            if "input" in cio and isinstance(cio["input"], dict):
                cin: dict = cio["input"]
                if "explicit" in cin:
                    self.chipIoInputExplicit = bool(cin["explicit"])

        # 4. Legacy flat keys (Backward Compatibility)
        if "internalWireColorize" in data:
            self.internalWireColorize = bool(data["internalWireColorize"])
        if "portVerticalSpacing" in data:
            self.portVerticalSpacing = int(data["portVerticalSpacing"])
        if "shareInternalRoutes" in data:
            self.shareInternalRoutes = bool(data["shareInternalRoutes"])
        elif "share_internal_routes" in data:
            self.shareInternalRoutes = bool(data["share_internal_routes"])



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
