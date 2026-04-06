"""Shared cardinal-side vocabulary for routing substrates."""

from __future__ import annotations

from enum import Enum


class CardinalSide(Enum):
    """Cardinal side for a chip, region, or routing substrate boundary."""

    WEST = "west"
    EAST = "east"
    NORTH = "north"
    SOUTH = "south"
