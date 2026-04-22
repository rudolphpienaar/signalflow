"""Runtime solver and solution objects for the quarantine board surface.

This module exposes the first-class runtime types that solve board-local wiring
and carry the resulting algebraic route set. These objects sit between kernel
runtime objects and materialized runtime objects.

Key components:
    - BoardSolvedWire: One solved directed wire with structured algebraic
      state
    - BoardSolver: Board-local symbolic solver
    - BoardSolution: Solved algebraic route set with board materialization
      entry

Typical usage:
    solver = kernel.solver_get(board)
    solution = solver.solution_get()
    materialized = solution.board_materialize(board)

Dependencies:
    - Requires board-local algebra from `signalflow.board.solver`
    - Delegates materialization to `materialized_runtime`
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from signalflow.board.board import Board
from signalflow.board.doctrine import BoardMaterializePolicy
from signalflow.notation.sfn import sfN

if TYPE_CHECKING:
    from signalflow.board.materialized_runtime import BoardMaterializedSolution
from signalflow.board.kernel_runtime import BoardKernelWire, BoardWiring
from signalflow.board.solver import (
    SolverWireInput,
    boardChannelLaneCounts_build,
    boardWireAlgebraicPath_build,
    wireTopology_build,
)
from signalflow.models import (
    RoutingLaneAttachmentSense,
    RoutingZoneChannelSense,
)
from signalflow.notation import AlgebraicPath, LaneSense, WiringSolution


@dataclass(frozen=True)
class BoardSolvedWire:
    """One algebraically solved directed wire.

    Attributes:
        kernelWire: Source wiring record that was solved.
        algebraicPath: Topology-only solved path.
        wireIndex: Zero-based wire rank in the owning topology bundle.
        wiringSolution: Owning bundle for concrete lane assignment.
        laneMap: Concrete lane indices keyed by channel area.
    """

    kernelWire: BoardKernelWire
    algebraicPath: AlgebraicPath
    wireIndex: int
    wiringSolution: WiringSolution
    laneMap: dict[sfN, int]

    def wireText_get(self) -> str:
        """Return the canonical `source:destination` wire text.

        Returns:
            Canonical directed wire text inherited from the source kernel wire.
        """

        return self.kernelWire.wireText_get()

    @property
    def algebraicPathText(self) -> str:
        """Return the compatibility string form for this solved wire."""

        parts: list[str] = [
            self.kernelWire._endpointDisplayText_build(
                self.algebraicPath.source,
                self.kernelWire.sourceDisplayEndpointText,
            )
        ]
        for hop in self.algebraicPath.hops:
            token = hop.area.channel_name or ""
            if hop.laneSense is LaneSense.FIXED:
                parts.append(f"{token}[0]")
                continue
            laneIndex = self.laneMap.get(hop.area, 0)
            parts.append(f"{token}[{laneIndex}]")
        parts.append(
            self.kernelWire._endpointDisplayText_build(
                self.algebraicPath.sink,
                self.kernelWire.destinationDisplayEndpointText,
            )
        )
        return "::".join(parts)

    @property
    def topologyName(self) -> str:
        """Return the selected path-solution name for this solved wire."""

        return self.wiringSolution.topology.name_get()


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
    laneFillSense: RoutingLaneAttachmentSense = (
        RoutingLaneAttachmentSense.FROM_START
    )
    solutionProvider: Callable[[BoardSolver], BoardSolution] | None = None

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
                sourceTerminalSide=wire.sourceTerminalSide,
                zoneLocalGeometryKind=wire.zoneLocalGeometryKind,
                callingStackDelta=wire.callingStackDelta,
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
                sourceTerminalSide=kernelWire.sourceTerminalSide,
                zoneLocalGeometryKind=kernelWire.zoneLocalGeometryKind,
                callingStackDelta=kernelWire.callingStackDelta,
                isReturn=kernelWire.isReturn,
            ),
            rotationSense=self.rotationSense,
            laneFillSense=self.laneFillSense,
        )

    def _solvedWires_build(self) -> tuple[BoardSolvedWire, ...]:
        """Build structured solved wires for the current board wiring scope."""

        allWires = tuple(self.wiring.all_get())
        laneCounts = boardChannelLaneCounts_build(self.board)
        wireIndicesByTopologyName: dict[str, list[int]] = {}
        topologyByName = {}
        wireIndex: int
        wire: BoardKernelWire
        for wireIndex, wire in enumerate(allWires):
            topology = wireTopology_build(
                SolverWireInput(
                    sourceEndpointText=wire.sourceEndpointText,
                    destinationEndpointText=wire.destinationEndpointText,
                    sourceTerminalSide=wire.sourceTerminalSide,
                    zoneLocalGeometryKind=wire.zoneLocalGeometryKind,
                    callingStackDelta=wire.callingStackDelta,
                    isReturn=wire.isReturn,
                ),
                rotationSense=self.rotationSense,
            )
            topologyName: str = topology.name_get()
            wireIndicesByTopologyName.setdefault(topologyName, []).append(
                wireIndex
            )
            topologyByName[topologyName] = topology

        solutionByWireIndex: dict[int, tuple[WiringSolution, int]] = {}
        algebraicPathByWireIndex: dict[int, AlgebraicPath] = {}
        topologyName: str
        for topologyName, wireIndices in wireIndicesByTopologyName.items():
            wiringSolution = WiringSolution(
                topology=topologyByName[topologyName],
                channelLaneCounts=laneCounts,
            )
            insertionOrder: tuple[int, ...]
            if self.laneFillSense is RoutingLaneAttachmentSense.FROM_END:
                insertionOrder = tuple(reversed(wireIndices))
            else:
                insertionOrder = tuple(wireIndices)
            localWireIndex: int
            originalWireIndex: int
            for localWireIndex, originalWireIndex in enumerate(
                insertionOrder
            ):
                groupedWire: BoardKernelWire = allWires[originalWireIndex]
                wiringSolution.wire_add(
                    source=groupedWire.sourceEndpointText,
                    sink=groupedWire.destinationEndpointText,
                )
                algebraicPathByWireIndex[originalWireIndex] = (
                    wiringSolution.paths_get()[localWireIndex]
                )
                solutionByWireIndex[originalWireIndex] = (
                    wiringSolution,
                    localWireIndex,
                )

        laneMapByWireIndex = _outerLaneMapsByWireIndex_build(
            allWires=allWires,
            algebraicPathByWireIndex=algebraicPathByWireIndex,
            laneFillSense=self.laneFillSense,
            solutionByWireIndex=solutionByWireIndex,
        )

        solvedWires: list[BoardSolvedWire] = []
        for wireIndex, wire in enumerate(allWires):
            matched = solutionByWireIndex.get(wireIndex)
            if matched is None:
                continue
            wiringSolution, localWireIndex = matched
            solvedWires.append(
                BoardSolvedWire(
                    kernelWire=wire,
                    algebraicPath=wiringSolution.paths_get()[localWireIndex],
                    wireIndex=localWireIndex,
                    wiringSolution=wiringSolution,
                    laneMap=laneMapByWireIndex[wireIndex],
                )
            )
        return tuple(solvedWires)

    def summary_sprint(self) -> str:
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

    def list_sprint(self) -> str:
        """Return one solved algebraic path per line.

        Returns:
            Multi-line text containing one solved algebraic path per line.
        """

        return "\n".join(
            self._wireAlgebraicText_build(wire)
            for wire in self.wiring.all_get()
        )

    def algebraic_sprint(self, endpointText: str) -> str:
        """Return solved algebraic paths for wires touching one endpoint.

        Args:
            endpointText: Endpoint or wire text used to select matching wires.

        Returns:
            Solved algebraic paths for matching wires, or an explanatory
            fallback.
        """

        matchingWires = tuple(
            wire
            for wire in self.wiring.all_get()
            if endpointText
            in (
                wire.sourceEndpointText,
                wire.destinationEndpointText,
                wire.wireText_get(),
            )
        )
        if not matchingWires:
            return f"<no wiring for endpoint {endpointText}>"
        return "\n".join(
            self._wireAlgebraicText_build(wire) for wire in matchingWires
        )

    def solution_get(self) -> BoardSolution:
        """Solve the current wiring scope and return a board solution.

        Returns:
            `BoardSolution` representing the solved algebraic route set.
        """

        if self.solutionProvider is not None:
            return self.solutionProvider(self)
        solvedWires = self._solvedWires_build()
        return BoardSolution(
            board=self.board,
            wiring=self.wiring,
            _solvedWires=solvedWires,
        )


_GLOBAL_OUTER_LANE_AREAS: frozenset[sfN] = frozenset(
    {
        sfN.We,
        sfN.Ee,
        sfN.Ne,
        sfN.Se,
        sfN.Wm,
        sfN.Em,
    }
)


def _outerLaneMapsByWireIndex_build(
    *,
    allWires: tuple[BoardKernelWire, ...],
    algebraicPathByWireIndex: dict[int, AlgebraicPath],
    laneFillSense: RoutingLaneAttachmentSense,
    solutionByWireIndex: dict[int, tuple[WiringSolution, int]],
) -> dict[int, dict[sfN, int]]:
    """Return final lane maps with global outer-channel ownership.

    Outer-channel lanes must be unique across all solved wires, not just
    within one topology bundle. Intra channels keep the existing per-topology
    bundle behavior.
    """

    laneMapByWireIndex: dict[int, dict[sfN, int]] = {}
    wireIndex: int
    for wireIndex, (_wiringSolution, localWireIndex) in (
        solutionByWireIndex.items()
    ):
        wiringSolution, _ = solutionByWireIndex[wireIndex]
        laneMapByWireIndex[wireIndex] = dict(
            wiringSolution.laneMap_get(localWireIndex)
        )

    wireIndicesByArea: dict[sfN, list[int]] = {}
    for wireIndex, algebraicPath in algebraicPathByWireIndex.items():
        seenAreas: set[sfN] = set()
        for hop in algebraicPath.hops:
            if (
                hop.laneSense is LaneSense.FIXED
                or hop.area not in _GLOBAL_OUTER_LANE_AREAS
                or hop.area in seenAreas
            ):
                continue
            wireIndicesByArea.setdefault(hop.area, []).append(wireIndex)
            seenAreas.add(hop.area)

    for area, wireIndices in wireIndicesByArea.items():
        orderedWireIndices = (
            list(reversed(wireIndices))
            if laneFillSense is RoutingLaneAttachmentSense.FROM_END
            else list(wireIndices)
        )
        for laneIndex, wireIndex in enumerate(orderedWireIndices, start=1):
            laneMapByWireIndex[wireIndex][area] = laneIndex

    for wireIndex in range(len(allWires)):
        laneMapByWireIndex.setdefault(wireIndex, {})
    return laneMapByWireIndex


@dataclass(frozen=True)
class BoardSolution:
    """Solved algebraic route set for one board-local solve.

    Attributes:
        board: Board that was solved.
        wiring: Wiring collection solved on that board.
        _solvedWires: Stable solved wires in display order.
        materializeProvider: Optional override for materialized-solution
            construction.
    """

    board: Board
    wiring: BoardWiring
    _solvedWires: tuple[BoardSolvedWire, ...]
    materializeProvider: (
        Callable[
            [Board, BoardSolution, BoardMaterializePolicy],
            BoardMaterializedSolution,
        ]
        | None
    ) = None

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

    def algebraic_sprint(self, endpointText: str) -> str:
        """Return solved algebraic paths for wires touching one endpoint.

        Args:
            endpointText: Endpoint or wire text used to select matching
                solved wires.

        Returns:
            Solved algebraic paths for matching wires, or an explanatory
            fallback.
        """

        matchingSolvedWires = tuple(
            solvedWire
            for solvedWire in self._solvedWires
            if endpointText
            in (
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

    def list_sprint(self) -> str:
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
        policy: BoardMaterializePolicy | None = None,
    ) -> BoardMaterializedSolution:
        """Materialize this solved route set onto one concrete board.

        Args:
            board: Optional replacement board. Defaults to the solved board.
            policy: Optional realization policy. Defaults to board-materialize
                defaults.

        Returns:
            `BoardMaterializedSolution` realized onto the active board.
        """

        from signalflow.board.materialized_runtime import (
            materializedSolution_build,
        )

        activeBoard = board or self.board
        activePolicy = policy or BoardMaterializePolicy()
        if self.materializeProvider is not None:
            return self.materializeProvider(activeBoard, self, activePolicy)
        return materializedSolution_build(
            board=activeBoard,
            solution=self,
            policy=activePolicy,
        )
