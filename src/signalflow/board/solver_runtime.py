"""Runtime solver and solution objects for the quarantine board surface.

This module exposes the first-class runtime types that solve board-local wiring
and carry the resulting algebraic route set. These objects sit between kernel
runtime objects and materialized runtime objects.

Key components:
    - BoardSolvedWire: One solved directed wire with algebraic path text
    - BoardSolver: Board-local symbolic solver
    - BoardSolution: Solved algebraic route set with board materialization entry

Typical usage:
    solver = kernel.solver_get(board)
    solution = solver.solution_get()
    materialized = solution.board_materialize(board)

Dependencies:
    - Requires board-local algebra from `signalflow.board.solver`
    - Delegates materialization to `materialized_runtime`
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from signalflow.board.board import Board
from signalflow.board.kernel_runtime import BoardKernelWire, BoardWiring
from signalflow.board.solver import (
    SolverWireInput,
    boardWireAlgebraicPath_build,
)
from signalflow.models import RoutingLaneAttachmentSense, RoutingZoneChannelSense


@dataclass(frozen=True)
class BoardSolvedWire:
    """One algebraically solved directed wire.

    Attributes:
        kernelWire: Source wiring record that was solved.
        algebraicPathText: Canonical solved algebraic path text.
    """

    kernelWire: BoardKernelWire
    algebraicPathText: str

    def wireText_get(self) -> str:
        """Return the canonical `source:destination` wire text.

        Returns:
            Canonical directed wire text inherited from the source kernel wire.
        """

        return self.kernelWire.wireText_get()


@dataclass(frozen=True)
class BoardSolver:
    """Board-local symbolic solver bound to one wiring scope.

    Attributes:
        board: Board that defines the legal routing substrate.
        wiring: Directed wiring scope to solve.
        rotationSense: Latitude rotation policy for the current solve.
        laneFillSense: Lane fill policy for the current solve.
        solutionProvider: Optional override for solution construction.
    """

    board: Board
    wiring: BoardWiring
    rotationSense: RoutingZoneChannelSense = RoutingZoneChannelSense.CLOCKWISE
    laneFillSense: RoutingLaneAttachmentSense = RoutingLaneAttachmentSense.FROM_START
    solutionProvider: Callable[["BoardSolver"], "BoardSolution"] | None = None

    def __dir__(self) -> list[str]:
        """Return the curated public solver surface.

        Returns:
            Public solver methods intended for interactive use.
        """

        return [
            "algebraic_text",
            "laneFillSense_get",
            "list_text",
            "policy_set",
            "rotationSense_get",
            "solution_get",
            "summary_text",
            "wiring_get",
        ]

    def wiring_get(self) -> BoardWiring:
        """Return the wiring collection solved by this solver.

        Returns:
            Runtime wiring collection bound to this solver.
        """

        return self.wiring

    def rotationSense_get(self) -> RoutingZoneChannelSense:
        """Return the current rotation policy.

        Returns:
            Current rotation policy enum.
        """

        return self.rotationSense

    def laneFillSense_get(self) -> RoutingLaneAttachmentSense:
        """Return the current lane-fill policy.

        Returns:
            Current lane-fill policy enum.
        """

        return self.laneFillSense

    def policy_set(
        self,
        rotationSense: RoutingZoneChannelSense | None = None,
        laneFillSense: RoutingLaneAttachmentSense | None = None,
    ) -> BoardSolver:
        """Return a solver copy with updated solve policy.

        Args:
            rotationSense: Optional replacement rotation policy.
            laneFillSense: Optional replacement lane-fill policy.

        Returns:
            New `BoardSolver` with updated policy fields.
        """

        return BoardSolver(
            board=self.board,
            wiring=self.wiring,
            rotationSense=rotationSense or self.rotationSense,
            laneFillSense=laneFillSense or self.laneFillSense,
            solutionProvider=self.solutionProvider,
        )

    def _wireAlgebraicText_build(self, kernelWire: BoardKernelWire) -> str:
        allWires = tuple(
            SolverWireInput(
                sourceEndpointText=wire.sourceEndpointText,
                destinationEndpointText=wire.destinationEndpointText,
                isReturn=wire.isReturn,
            )
            for wire in self.wiring.all_get()
        )
        return boardWireAlgebraicPath_build(
            board=self.board,
            allWires=allWires,
            wire=SolverWireInput(
                sourceEndpointText=kernelWire.sourceEndpointText,
                destinationEndpointText=kernelWire.destinationEndpointText,
                isReturn=kernelWire.isReturn,
            ),
            rotationSense=self.rotationSense,
            laneFillSense=self.laneFillSense,
        )

    def summary_text(self) -> str:
        """Return a readable summary of this solver configuration.

        Returns:
            Multi-line summary text for the current solver configuration.
        """

        return "\n".join(
            [
                "kernel symbolic solver",
                f"  rotationSense: {self.rotationSense.value}",
                f"  laneFillSense: {self.laneFillSense.value}",
                f"  wireCount: {len(self.wiring.all_get())}",
            ]
        )

    def list_text(self) -> str:
        """Return one solved algebraic path per line.

        Returns:
            Multi-line text containing one solved algebraic path per line.
        """

        return "\n".join(
            self._wireAlgebraicText_build(wire)
            for wire in self.wiring.all_get()
        )

    def algebraic_text(self, endpointText: str) -> str:
        """Return solved algebraic paths for wires touching one endpoint.

        Args:
            endpointText: Endpoint or wire text used to select matching wires.

        Returns:
            Solved algebraic paths for matching wires, or an explanatory fallback.
        """

        matchingWires = tuple(
            wire
            for wire in self.wiring.all_get()
            if endpointText in (
                wire.sourceEndpointText,
                wire.destinationEndpointText,
                wire.wireText_get(),
            )
        )
        if not matchingWires:
            return f"<no wiring for endpoint {endpointText}>"
        return "\n".join(
            self._wireAlgebraicText_build(wire)
            for wire in matchingWires
        )

    def solution_get(self) -> BoardSolution:
        """Solve the current wiring scope and return a board solution.

        Returns:
            `BoardSolution` representing the solved algebraic route set.
        """

        if self.solutionProvider is not None:
            return self.solutionProvider(self)
        solvedWires = tuple(
            BoardSolvedWire(
                kernelWire=wire,
                algebraicPathText=self._wireAlgebraicText_build(wire),
            )
            for wire in self.wiring.all_get()
        )
        return BoardSolution(
            board=self.board,
            wiring=self.wiring,
            _solvedWires=solvedWires,
        )


@dataclass(frozen=True)
class BoardSolution:
    """Solved algebraic route set for one board-local solve.

    Attributes:
        board: Board that was solved.
        wiring: Wiring collection solved on that board.
        _solvedWires: Stable solved wires in display order.
        materializeProvider: Optional override for materialized-solution construction.
    """

    board: Board
    wiring: BoardWiring
    _solvedWires: tuple[BoardSolvedWire, ...]
    materializeProvider: Callable[[Board, "BoardSolution"], "BoardMaterializedSolution"] | None = None

    def __dir__(self) -> list[str]:
        """Return the curated public solution surface.

        Returns:
            Public solution methods intended for interactive use.
        """

        return [
            "algebraic_text",
            "all_get",
            "board_materialize",
            "list_text",
            "wiring_get",
        ]

    def all_get(self) -> tuple[BoardSolvedWire, ...]:
        """Return all solved wires in stable order.

        Returns:
            Tuple of solved wires in stable display order.
        """

        return self._solvedWires

    def wiring_get(self) -> BoardWiring:
        """Return the wiring collection solved by this solution.

        Returns:
            Runtime wiring collection associated with this solution.
        """

        return self.wiring

    def algebraic_text(self, endpointText: str) -> str:
        """Return solved algebraic paths for wires touching one endpoint.

        Args:
            endpointText: Endpoint or wire text used to select matching solved wires.

        Returns:
            Solved algebraic paths for matching wires, or an explanatory fallback.
        """

        matchingSolvedWires = tuple(
            solvedWire
            for solvedWire in self._solvedWires
            if endpointText in (
                solvedWire.kernelWire.sourceEndpointText,
                solvedWire.kernelWire.destinationEndpointText,
                solvedWire.kernelWire.wireText_get(),
            )
        )
        if not matchingSolvedWires:
            return f"<no wiring for endpoint {endpointText}>"
        return "\n".join(
            solvedWire.algebraicPathText for solvedWire in matchingSolvedWires
        )

    def list_text(self) -> str:
        """Return one solved algebraic path per line.

        Returns:
            Multi-line text containing one solved algebraic path per line.
        """

        return "\n".join(
            solvedWire.algebraicPathText for solvedWire in self._solvedWires
        )

    def board_materialize(
        self,
        board: Board | None = None,
    ) -> "BoardMaterializedSolution":
        """Materialize this solved route set onto one concrete board.

        Args:
            board: Optional replacement board. Defaults to the solved board.

        Returns:
            `BoardMaterializedSolution` realized onto the active board.
        """

        from signalflow.board.materialized_runtime import materializedSolution_build

        activeBoard = board or self.board
        if self.materializeProvider is not None:
            return self.materializeProvider(activeBoard, self)
        return materializedSolution_build(board=activeBoard, solution=self)
