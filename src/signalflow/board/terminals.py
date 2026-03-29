"""Exact terminal attach-point models for the board domain.

These models intentionally describe the real attach points that wires use
during realization. They are not padded layout envelopes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.board.types import WorldPoint


@dataclass(frozen=True)
class TerminalAttachPoint:
    """Exact world-coordinate attach point for one terminal."""

    chipName: str
    terminalName: str
    worldPoint: WorldPoint


@dataclass(frozen=True)
class ChipTerminalSet:
    """Exact terminal attach points grouped by chip."""

    chipName: str
    terminalsByName: dict[str, WorldPoint] = field(default_factory=dict)

    def worldPoint_get(self, terminalName: str) -> WorldPoint | None:
        """Return the exact world attach point for one terminal."""

        return self.terminalsByName.get(terminalName)
