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
    internalWireColorize: bool = True # Enable ANSI colors for internal wiring
    shareInternalRoutes: bool = False # Disable track-sharing for clean junctions
    # True: one port per caller; False: one port per function
    chipIoInputExplicit: bool = False
    # True: unit-density manifold ports (lCounts==1) route flush to the wall —
    # no internal anchor label, no neutral bus offset. False: always anchor-stack.
    passThroughAllowed: bool = True
    # True: draw manifold anchor labels inside chips.
    showInternalLabels: bool = True
    # True: replace manifold anchor labels with compact per-chip aliases.
    aliasInternalLabels: bool = False
    # 0 = unlimited; positive N = truncate anchor label names to N characters.
    # Reduces chip width when port names are long descriptive strings.
    # The full name still appears on external wires between chips.
    anchorLabelMaxWidth: int = 0
    # "block": draw █ computation block wherever execution is opaque (default).
    # "none":  legacy rendering — no blocks drawn.
    implicitThread: str = "block"

    def _topLevelConfig_apply(self, data: dict) -> None:
        """Apply direct top-level config keys."""
        if "channelWidth" in data:
            self.channelWidth = int(data["channelWidth"])
        if "verticalChipPadding" in data:
            self.verticalChipPadding = int(data["verticalChipPadding"])
        if "implicitThread" in data:
            self.implicitThread = str(data["implicitThread"])

    def _internalWiringConfig_apply(self, data: dict) -> None:
        """Apply nested ``internal_wiring`` config keys."""
        if "colorize" in data:
            self.internalWireColorize = bool(data["colorize"])
        if "shareRoutes" in data:
            self.shareInternalRoutes = bool(data["shareRoutes"])
        if "portSpacing" in data:
            self.portVerticalSpacing = int(data["portSpacing"])
        if "passThroughAllowed" in data:
            self.passThroughAllowed = bool(data["passThroughAllowed"])
        if "showInternalLabels" in data:
            self.showInternalLabels = bool(data["showInternalLabels"])
        if "show_internal_labels" in data:
            self.showInternalLabels = bool(data["show_internal_labels"])
        if "aliasInternalLabels" in data:
            self.aliasInternalLabels = bool(data["aliasInternalLabels"])
        if "alias_internal_labels" in data:
            self.aliasInternalLabels = bool(data["alias_internal_labels"])
        if "anchorLabelWidth" in data:
            self.anchorLabelMaxWidth = int(data["anchorLabelWidth"])

    def _chipIoConfig_apply(self, data: dict) -> None:
        """Apply nested ``chip_io`` config keys."""
        if "input" not in data or not isinstance(data["input"], dict):
            return
        inputConfig: dict = data["input"]
        if "explicit" in inputConfig:
            self.chipIoInputExplicit = bool(inputConfig["explicit"])

    def _legacyKeys_apply(self, data: dict) -> None:
        """Apply backward-compatible flat config keys."""
        if "internalWireColorize" in data:
            self.internalWireColorize = bool(data["internalWireColorize"])
        if "portVerticalSpacing" in data:
            self.portVerticalSpacing = int(data["portVerticalSpacing"])
        if "shareInternalRoutes" in data:
            self.shareInternalRoutes = bool(data["shareInternalRoutes"])
        elif "share_internal_routes" in data:
            self.shareInternalRoutes = bool(data["share_internal_routes"])
        if "passThroughAllowed" in data:
            self.passThroughAllowed = bool(data["passThroughAllowed"])
        if "showInternalLabels" in data:
            self.showInternalLabels = bool(data["showInternalLabels"])
        elif "show_internal_labels" in data:
            self.showInternalLabels = bool(data["show_internal_labels"])
        if "aliasInternalLabels" in data:
            self.aliasInternalLabels = bool(data["aliasInternalLabels"])
        elif "alias_internal_labels" in data:
            self.aliasInternalLabels = bool(data["alias_internal_labels"])

    def config_update(self, data: dict) -> None:
        """Update singleton properties from a config dictionary."""
        self._topLevelConfig_apply(data)

        if "internal_wiring" in data and isinstance(data["internal_wiring"], dict):
            self._internalWiringConfig_apply(data["internal_wiring"])

        if "chip_io" in data and isinstance(data["chip_io"], dict):
            self._chipIoConfig_apply(data["chip_io"])

        self._legacyKeys_apply(data)


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
