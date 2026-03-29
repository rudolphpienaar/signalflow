"""Canonical board-domain geometry models.

This module is the starting point for making board geometry first-class.

The design goal is simple:
- the board owns the geometric substrate
- downstream layers read that substrate
- downstream layers do not re-invent spacing, region extents, or display
  boundaries for themselves

At the moment this module intentionally does only a small amount of work, but
that work is concrete and useful because it stores the explicit region frames,
effective boundaries, and exact terminal positions that define a board.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.board.render import boardGeometry_text
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    WorldPoint,
    boardRegionLabel_build,
)
from signalflow.models import RoutingZoneRegionFrame, RoutingZoneRegionId


@dataclass(frozen=True)
class BoardGeometry:
    """Canonical geometric state for one board.

    `BoardGeometry` is meant to be the place where explicit board facts live.
    From the start it needs to carry two different kinds of truth that must
    never be conflated:

    - `regionFramesByName`
      The concrete routing-region substrate in world coordinates. These are the
      owned routing bands, transitions, fans, and terminal strips that the
      board exposes.

    - `regionIdsByName`
      The exact region identities associated with those frames. Keeping the ids
      alongside the frames lets the existing REPL surface continue to expose
      side/kind/tag-aware region inspection while moving the canonical source
      of truth underneath into the board package.

    - `effectiveBoundaryFramesByName`
      Optional derived envelopes such as label-aware module boundaries or
      effective terminal-clearance boundaries. These are not yet used broadly,
      but this field exists so those envelopes can become first-class geometry
      rather than ad hoc spacing doctrine.

    - `exactTerminalWorldPositionsByChip`
      The exact world-coordinate attach points for real chip terminals. These
      are the coordinates wires truly start and end from during realization.
      They are intentionally separate from effective boundaries because layout
      clearance and attach-point truth are not the same fact.
    """

    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame] = field(
        default_factory=dict,
    )
    routingZoneRegionIdsById: dict[BoardRegionId, RoutingZoneRegionId] = field(
        default_factory=dict,
    )
    effectiveBoundaryFramesByName: dict[str, RoutingZoneRegionFrame] = field(
        default_factory=dict,
    )
    exactTerminalWorldPositionsByChip: dict[str, dict[str, WorldPoint]] = field(
        default_factory=dict,
    )
    chipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = field(
        default_factory=dict,
    )

    def effectiveBoundaryFrame_get(
        self,
        boundaryName: str,
    ) -> RoutingZoneRegionFrame | None:
        """Return one effective layout boundary by canonical name.

        Effective boundaries are the padded envelopes used for layout and
        clearance decisions. They are appropriate for spacing, corridor
        placement, and visual no-go reasoning.
        """

        return self.effectiveBoundaryFramesByName.get(boundaryName)

    def exactTerminalWorldPosition_get(
        self,
        chipName: str,
        terminalName: str,
    ) -> WorldPoint | None:
        """Return the exact world attach point for one chip terminal.

        This method deliberately answers a narrower question than effective
        boundary accessors. It returns the precise attach point used by route
        realization, not the padded envelope used by layout.
        """

        chipTerminalPositions = self.exactTerminalWorldPositionsByChip.get(chipName)
        if chipTerminalPositions is None:
            return None
        return chipTerminalPositions.get(terminalName)

    @property
    def regionFramesByName(self) -> dict[str, RoutingZoneRegionFrame]:
        """Compatibility projection keyed by legacy readable region labels."""

        return {
            boardRegionLabel_build(regionId): frame
            for regionId, frame in self.regionFramesById.items()
        }

    @property
    def regionIdsByName(self) -> dict[str, RoutingZoneRegionId]:
        """Compatibility projection keyed by legacy readable region labels."""

        return {
            boardRegionLabel_build(regionId): routingZoneRegionId
            for regionId, routingZoneRegionId in self.routingZoneRegionIdsById.items()
        }

    def geometry_text(self, columnOffset: int | None = None) -> str:
        """Render the board's routing substrate as world-coordinate text.

        Args:
            columnOffset: Optional world-column at which to begin the visible
                crop. When omitted, the render begins at the first occupied
                board column. When set to `0`, the output can be aligned
                directly against a full-world render.

        Returns:
            A multi-line text block containing:
            - a world-column ruler on row `0`
            - a world-true filled-region board render
            - a legend with inclusive world-coordinate bounds for each region
        """

        return boardGeometry_text(
            self.regionFramesById,
            effectiveBoundaryFramesByName=self.effectiveBoundaryFramesByName,
            columnOffset=columnOffset,
        )
