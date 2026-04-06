"""CSS-inspired box vocabulary for board layout.

The board package separates exact attach-point truth from effective layout
envelopes. These box dataclasses provide the naming surface for those layout
envelopes so later code can talk about content, padding, borders, and keepout
explicitly instead of overloading one ambiguous frame.
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.types import WorldFrame


@dataclass(frozen=True)
class ContentBox:
    """Visible content extent of one module or chip group."""

    frame: WorldFrame


@dataclass(frozen=True)
class PaddingBox:
    """Content extent after label and terminal-side clearance is applied."""

    frame: WorldFrame


@dataclass(frozen=True)
class BorderBox:
    """Visible framed extent of one module or chip group."""

    frame: WorldFrame


@dataclass(frozen=True)
class KeepoutBox:
    """Outer routing keepout envelope used for corridor spacing decisions."""

    frame: WorldFrame


@dataclass(frozen=True)
class EffectiveBoundary:
    """Composed effective boundary for one routed module or chip group.

    This is the box stack that downstream board-layout code should read instead
    of inventing spacing assumptions independently.
    """

    contentBox: ContentBox
    paddingBox: PaddingBox
    borderBox: BorderBox
    keepoutBox: KeepoutBox
