"""Top-level first-class board model.

The board object is the stable domain boundary that the REPL and downstream
subsystems should eventually speak to. It binds placement, geometry,
substrate, doctrine, and exact terminal truth into one coherent object.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

from signalflow.board.doctrine import (
    BoardChipPlacementPolicy,
    BoardDoctrine,
    EffectiveBoundaryMode,
)
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
    variantProvider: Callable[[BoardChipPlacementPolicy], "Board"] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __dir__(self) -> list[str]:
        """Return the curated REPL-facing board surface."""

        return [
            "backend_get",
            "boundaries_get",
            "boundary_get",
            "channels_get",
            "chipPlacementPolicy_get",
            "chipPlacementPolicy_set",
            "effective_get",
            "geometry_get",
            "geometry_text",
            "minimumCrossbarSpan_get",
            "model_get",
            "problems_get",
            "sense_get",
            "substrate_get",
            "summary_text",
            "terminal_get",
            "terminals_get",
            "validation_text",
            "worldFrame_get",
            "worldGridCoord_get",
        ]

    def backend_get(self) -> str:
        """Return the currently active board backend label."""

        return "new"

    def worldGridCoord_get(self) -> RoutingZoneId:
        """Return the board's stable grid/world coordinate id."""

        return self.routingZoneId.id

    def model_get(self) -> Board:
        """Return the underlying first-class board object."""

        return self

    def sense_get(self):
        """Return the board routing sense doctrine."""

        return self.doctrine.sense

    def minimumCrossbarSpan_get(self) -> int:
        """Return the doctrinal minimum crossbar span."""

        return self.doctrine.minimumCrossbarSpan

    def chipPlacementPolicy_get(self) -> BoardChipPlacementPolicy:
        """Return the current chip placement policy for this board."""

        return self.doctrine.chipPlacementPolicy

    def boundaries_get(self):
        """Return all effective layout boundaries."""

        return dict(self.geometry.effectiveBoundaryFramesByName)

    def boundary_get(self, boundaryName: str):
        """Return one effective layout boundary by canonical name."""

        return self.geometry.effectiveBoundaryFrame_get(boundaryName)

    def terminals_get(self) -> dict[str, dict[str, tuple[int, int]]]:
        """Return exact terminal world positions grouped by chip name."""

        return {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                self.geometry.exactTerminalWorldPositionsByChip.items()
            )
        }

    def terminal_get(
        self,
        chipName: str,
        terminalName: str,
    ) -> tuple[int, int] | None:
        """Return one exact terminal world attach point."""

        return self.geometry.exactTerminalWorldPosition_get(chipName, terminalName)

    def problems_get(self) -> tuple[str, ...]:
        """Return board invariant problems."""

        from signalflow.board.validators import boardProblems_get

        return boardProblems_get(self)

    def validation_text(self) -> str:
        """Return a human-readable board validation summary."""

        problems = self.problems_get()
        if not problems:
            return "board validation:\n  <none>"
        return "board validation:\n" + "\n".join(
            f"  {problem}" for problem in problems
        )

    def geometry_get(self) -> BoardGeometry:
        """Return the board geometry object itself."""

        return self.geometry

    def channels_get(self):
        """Return board channels derived from canonical geometry."""

        from signalflow.board.channels_runtime import BoardChannels

        return BoardChannels.build(self)

    def worldFrame_get(self) -> WorldFrame:
        """Return the inclusive world frame occupied by this board."""

        return self.worldFrame

    def geometry_text(self, columnOffset: int | None = None) -> str:
        """Render this board's geometry using the canonical board geometry."""

        return self.geometry.geometry_text(columnOffset=columnOffset)

    def chipPlacementPolicy_set(
        self,
        chipPlacementPolicy: BoardChipPlacementPolicy,
    ) -> "Board":
        """Return a board variant built with one chip placement policy.

        Args:
            chipPlacementPolicy: Requested chip stack placement doctrine.

        Returns:
            Board rebuilt under the requested placement policy.
        """

        if chipPlacementPolicy is self.doctrine.chipPlacementPolicy:
            return self
        if self.variantProvider is not None:
            return self.variantProvider(chipPlacementPolicy)
        return replace(
            self,
            doctrine=replace(
                self.doctrine,
                chipPlacementPolicy=chipPlacementPolicy,
            ),
        )

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

    def summary_text(self) -> str:
        """Return a short textual summary of this board."""

        return "\n".join(
            [
                f"board {self.side} of {self.routingZoneId.id}",
                f"worldFrame {self.worldFrame_get()}",
                self.channels_get().list_text(),
            ]
        )
