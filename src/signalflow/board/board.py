"""Top-level first-class board model.

The board object is the stable domain boundary that the REPL and downstream
subsystems should eventually speak to. It binds placement, geometry,
substrate, doctrine, and exact terminal truth into one coherent object.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from signalflow.board.doctrine import BoardDoctrine, EffectiveBoundaryMode
from signalflow.board.geometry import BoardGeometry
from signalflow.board.substrate import BoardSubstrate
from signalflow.board.types import WorldFrame
from signalflow.models import RoutingZoneId


@dataclass(frozen=True)
class Board:
    """First-class board model.

    The current public surface is intentionally small but already useful:
    - identity and side
    - world placement frame
    - doctrine and substrate
    - canonical geometry
    - board-native geometry rendering
    """

    routingZoneId: RoutingZoneId
    side: str
    worldFrame: WorldFrame
    doctrine: BoardDoctrine
    substrate: BoardSubstrate
    geometry: BoardGeometry
    substrateBoard: Board | None = field(default=None, repr=False, compare=False)
    effectiveBoard: Board | None = field(default=None, repr=False, compare=False)

    def worldFrame_get(self) -> WorldFrame:
        """Return the inclusive world frame occupied by this board."""

        return self.worldFrame

    def geometry_text(self, columnOffset: int | None = None) -> str:
        """Render this board's geometry using the canonical board geometry."""

        return self.geometry.geometry_text(columnOffset=columnOffset)

    def substrate_get(self) -> Board:
        """Return the raw substrate board used as the baseline geometry.

        The substrate board preserves the same routing substrate and exact
        terminal positions but omits doctrine-derived effective boundaries.
        This is the comparison surface for users who want to inspect the board
        before label-aware clearance or other effective-boundary policy is
        applied.
        """

        if self.substrateBoard is not None:
            return self.substrateBoard

        substrateGeometry = replace(
            self.geometry,
            effectiveBoundaryFramesByName={},
        )
        substrateDoctrine = replace(
            self.doctrine,
            effectiveBoundaryMode=EffectiveBoundaryMode.CONTENT_ONLY,
            moduleBoundaryPaddingCells=0,
        )
        return Board(
            routingZoneId=self.routingZoneId,
            side=self.side,
            worldFrame=self.worldFrame,
            doctrine=substrateDoctrine,
            substrate=self.substrate,
            geometry=substrateGeometry,
        )

    def effective_get(self) -> Board:
        """Return the doctrine-adjusted effective board used operationally."""

        if self.effectiveBoard is not None:
            return self.effectiveBoard
        return self
