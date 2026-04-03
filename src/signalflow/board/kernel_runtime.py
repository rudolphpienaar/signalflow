"""Runtime kernel and wiring objects for the quarantine board surface.

This module exposes the first-class runtime types that represent a board kernel
and its directed wiring set. These objects sit above canonical board geometry
and below solver/materializer runtime types. They do not own solve policy;
instead they hand the wiring scope to `BoardSolver`.

Key components:
    - BoardKernelWire: One directed wire in a kernel-local wiring scope
    - BoardWiring: Runtime wiring collection with solver access
    - BoardKernel: Runtime kernel façade exposing board, wiring, and YAML views

Typical usage:
    kernel = zone.kernel_get("intra")
    wiring = kernel.wiring_get()
    solver = kernel.solver_get(kernel.board_get())

Dependencies:
    - Requires `Board` for geometry and channel access
    - Delegates solve/runtime progression to `solver_runtime`
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from signalflow.board.board import Board

if TYPE_CHECKING:
    from signalflow.board.solver_runtime import BoardSolver
from signalflow.board.channels_runtime import BoardChannels
from signalflow.board.doctrine import BoardChipPlacementPolicy
from signalflow.models import ChipRef, ChipTerminalSide, RoutingZoneId


@dataclass(frozen=True)
class BoardKernelWire:
    """One directed wire visible inside one board kernel.

    Attributes:
        sourceEndpointText: Canonical source endpoint text.
        destinationEndpointText: Canonical destination endpoint text.
        sourceChipRef: Source chip reference.
        destinationChipRef: Destination chip reference.
        sourceTerminalName: Source terminal name.
        destinationTerminalName: Destination terminal name.
        sourceTerminalSide: Side exposing the source terminal.
        destinationTerminalSide: Side exposing the destination terminal.
        isReturn: Whether this wire is a return-path wire.
    """

    sourceEndpointText: str
    destinationEndpointText: str
    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    sourceTerminalName: str
    destinationTerminalName: str
    sourceTerminalSide: ChipTerminalSide
    destinationTerminalSide: ChipTerminalSide
    isReturn: bool = False

    def wireText_get(self) -> str:
        """Return the canonical `source:destination` wire text.

        Returns:
            Canonical directed wire text.
        """

        return f"{self.sourceEndpointText}:{self.destinationEndpointText}"

    def __str__(self) -> str:
        """Return the canonical wire text for interactive display.

        Returns:
            Canonical directed wire text.
        """

        return self.wireText_get()


@dataclass(frozen=True)
class BoardWiring:
    """Collection of directed wires visible in one board kernel.

    Attributes:
        board: Board that owns this wiring scope.
        _wires: Stable directed wires visible in this kernel.
    """

    board: Board
    _wires: tuple[BoardKernelWire, ...]

    def __dir__(self) -> list[str]:
        """Return the curated public wiring inspection surface.

        Returns:
            Public wiring methods intended for interactive use.
        """

        return [
            "algebraic_text",
            "all_get",
            "board_get",
            "channels_get",
            "list_text",
            "solver_get",
        ]

    def all_get(self) -> tuple[BoardKernelWire, ...]:
        """Return all directed wires in stable display order.

        Returns:
            Tuple of all kernel wires in stable order.
        """

        return self._wires

    def board_get(self) -> Board:
        """Return the board that owns this wiring scope.

        Returns:
            Board bound to this wiring collection.
        """

        return self.board

    def channels_get(self) -> BoardChannels:
        """Return the board channels visible to this wiring scope.

        Returns:
            Runtime channel collection derived from the owning board.
        """

        return self.board.channels_get()

    def solver_get(self) -> "BoardSolver":
        """Return a solver bound to this exact wiring scope.

        Returns:
            `BoardSolver` initialized over this wiring collection.
        """

        from signalflow.board.solver_runtime import BoardSolver

        return BoardSolver(board=self.board, wiring=self)

    def list_sprint(self) -> str:
        """Return one directed wire per line.

        Returns:
            Multi-line text containing one wire per line.
        """

        if not self._wires:
            return "<no wiring in this kernel>"
        return "\n".join(wire.wireText_get() for wire in self._wires)

    def algebraic_sprint(self, endpointText: str) -> str:
        """Return algebraic path text for wires touching one endpoint.

        Args:
            endpointText: Endpoint or wire text used to select matching wires.

        Returns:
            Algebraic path text for matching wires, or an explanatory fallback.
        """

        matchingWires = tuple(
            wire
            for wire in self._wires
            if endpointText in (
                wire.sourceEndpointText,
                wire.destinationEndpointText,
                wire.wireText_get(),
            )
        )
        if not matchingWires:
            return f"<no wiring for endpoint {endpointText}>"
        return self.solver_get().algebraic_sprint(endpointText)


@dataclass(frozen=True)
class BoardKernel:
    """Runtime kernel object for the quarantine board surface.

    Attributes:
        routingZoneId: Zone id that owns this kernel.
        side: Kernel side identifier such as `intra` or `internal`.
        kernel: Raw underlying kernel model.
        board: Board derived from this kernel.
        wiring: Directed wiring collection visible in this kernel.
        areasProvider: Optional provider for typed area inspection.
        schematicProvider: Optional provider for schematic text.
        routesProvider: Optional provider for route declaration text.
        yamlProvider: Optional provider for source YAML text.
        solverProvider: Optional custom solver builder.
    """

    routingZoneId: RoutingZoneId
    side: str
    kernel: object
    board: Board
    wiring: BoardWiring
    areasProvider: Callable[[], object] | None = None
    schematicProvider: Callable[[], str] | None = None
    routesProvider: Callable[[], str] | None = None
    yamlProvider: Callable[[], str] | None = None
    solverProvider: Callable[[Board], "BoardSolver"] | None = None
    boardProvider: Callable[[BoardChipPlacementPolicy], Board] | None = None

    def __dir__(self) -> list[str]:
        """Return the curated public kernel inspection surface.

        Returns:
            Public kernel methods intended for interactive use.
        """

        return [
            "areas_get",
            "board_get",
            "raw_get",
            "routes_text",
            "schematic_text",
            "side_get",
            "solver_get",
            "wiring_get",
            "yaml_text",
        ]

    def side_get(self) -> str:
        """Return the kernel side identifier such as `intra` or `internal`.

        Returns:
            Stable side name for this kernel.
        """

        return self.side

    def areas_get(self):
        """Return the typed area view for this kernel when available.

        Returns:
            Area collection/provider output, or `None` when unavailable.
        """

        return self.areasProvider() if self.areasProvider is not None else None

    def board_get(
        self,
        chipPlacementPolicy: BoardChipPlacementPolicy | None = None,
    ) -> Board:
        """Return the board derived from this kernel.

        Args:
            chipPlacementPolicy: Optional replacement chip stack placement
                doctrine for this board view.

        Returns:
            Board bound to this kernel.
        """

        if chipPlacementPolicy is not None:
            if self.boardProvider is not None:
                return self.boardProvider(chipPlacementPolicy)
            return self.board.chipPlacementPolicy_set(chipPlacementPolicy)
        return self.board

    def schematic_sprint(self) -> str:
        """Return a schematic overview for this kernel.

        Returns:
            Multi-line schematic text, or a fallback message when unavailable.
        """

        if self.schematicProvider is None:
            return "<kernel schematic unavailable>"
        return self.schematicProvider()

    def routes_sprint(self) -> str:
        """Return the route declarations visible in this kernel.

        Returns:
            Multi-line route declaration text, or a fallback message when unavailable.
        """

        if self.routesProvider is None:
            return "<kernel routes unavailable>"
        return self.routesProvider()

    def raw_get(self):
        """Return the raw kernel model object.

        Returns:
            Underlying kernel model bound to this runtime kernel.
        """

        return self.kernel

    def wiring_get(self) -> BoardWiring:
        """Return the directed wiring collection for this kernel.

        Returns:
            Runtime wiring collection bound to this kernel.
        """

        return self.wiring

    def yaml_sprint(self) -> str:
        """Return the source YAML text that produced this kernel when available.

        Returns:
            YAML text for this kernel, or a fallback message when unavailable.
        """

        if self.yamlProvider is None:
            return "<kernel yaml unavailable>"
        return self.yamlProvider()

    def solver_get(self, board: Board | None = None) -> "BoardSolver":
        """Return a solver bound to this kernel and board.

        Args:
            board: Optional replacement board. Defaults to this kernel's board.

        Returns:
            `BoardSolver` bound to the active board and this kernel's wiring.
        """

        from signalflow.board.solver_runtime import BoardSolver

        activeBoard = board or self.board
        if self.solverProvider is not None:
            return self.solverProvider(activeBoard)
        return BoardSolver(board=activeBoard, wiring=self.wiring)
