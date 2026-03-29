"""Routing-substrate models for the board domain.

The board package distinguishes between box/envelope geometry and the routing
substrate that lives between those envelopes. This module gives names to the
channel families and region groups that the board exposes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.board.types import BoardRegionId, BoardSense, boardRegionLabel_build
from signalflow.models import RoutingZoneRegionFrame


@dataclass(frozen=True)
class BoardSubstrate:
    """Canonical routing substrate owned by a board.

    The current form is intentionally simple: it keeps the region frames keyed
    by canonical typed ids and records the routing sense under which those
    regions should be interpreted.
    """

    sense: BoardSense
    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = field(
        default_factory=dict
    )

    @property
    def regionFramesByName(self) -> dict[str, RoutingZoneRegionFrame]:
        """Compatibility projection keyed by readable legacy labels."""

        return {
            boardRegionLabel_build(regionId): frame
            for regionId, frame in self.regionFramesById.items()
        }
