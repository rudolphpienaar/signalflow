"""Runtime materialized-solution objects for the quarantine board surface.

This module exposes the first-class runtime types that realize solved board
routes onto exact board/world geometry. It owns board-overlay text, realized
wire summaries, and collision reporting for the quarantine board workflow.

Key components:
    - BoardMaterializedWire: One solved wire realized onto exact coordinates
    - BoardMaterializedSolution: Full realized route set with geometry and collisions
    - materializedSolution_build: Builder from `BoardSolution` to realized runtime object

Typical usage:
    solution = solver.solution_get()
    materialized = solution.board_materialize(board)
    print(materialized.geometry_text())

Dependencies:
    - Requires board render and board realizer helpers
    - Consumes solved wires from `solver_runtime`
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from signalflow.board.board import Board
from signalflow.board.doctrine import BoardMaterializePolicy
from signalflow.board.realizer import algebraicRouteRealization_build, realizationPlan_build
from signalflow.board.render import boardCanvas_render, realizedGeometry_text
from signalflow.board.types import WorldFrame
from signalflow.models import ChipRef, RoutingZoneRegionFrame
from signalflow.routing import RealizedRoute, RealizedRouteCell, RealizedRouteSet, RouteSense
from signalflow.routing.track import TrackDirection, trackCell_build


@dataclass(frozen=True)
class BoardMaterializedWire:
    """One solved wire realized onto exact board/world geometry.

    Attributes:
        solvedWire: Solved wire from which this realized wire was built.
        tokenStartPoints: Realized world start points for algebraic tokens.
        routePoints: Ordered orthogonal world points for the route polyline.
        routeCells: Ordered occupied world cells for this realized route.
    """

    solvedWire: "BoardSolvedWire"
    tokenStartPoints: tuple[tuple[int, int], ...]
    routePoints: tuple[tuple[int, int], ...]
    routeCells: tuple[tuple[int, int], ...]

    def algebraicWorld_text(self) -> str:
        """Return the algebraic path annotated with realized world points.

        Returns:
            Algebraic path text with token world coordinates inserted when available.
        """

        pathTokens = self.solvedWire.algebraicPathText.split("::")
        if len(pathTokens) != 7 or len(self.tokenStartPoints) != 5:
            return self.solvedWire.algebraicPathText
        annotatedTokens: list[str] = [pathTokens[0]]
        for tokenText, (columnIndex, rowIndex) in zip(
            pathTokens[1:6],
            self.tokenStartPoints,
            strict=True,
        ):
            annotatedTokens.append(f"{tokenText}@({rowIndex},{columnIndex})")
        annotatedTokens.append(pathTokens[6])
        return "::".join(annotatedTokens)

    def summary_text(self) -> str:
        """Return a readable summary of this realized wire.

        Returns:
            Multi-line summary text including algebraic path and realized points.
        """

        pointText = " -> ".join(
            f"({columnIndex},{rowIndex})"
            for columnIndex, rowIndex in self.routePoints
        )
        return "\n".join(
            [
                self.solvedWire.wireText_get(),
                f"  algebraic: {self.solvedWire.algebraicPathText}",
                f"  points: {pointText}",
            ]
        )


@dataclass(frozen=True)
class _MaterializedPath:
    tokenStartPoints: tuple[tuple[int, int], ...]
    routePoints: tuple[tuple[int, int], ...]
    routeCells: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class BoardMaterializedSolution:
    """Exact realized geometry for one solved board route set.

    Attributes:
        board: Board used as the realization substrate.
        solution: Solved algebraic route set realized onto the board.
        _materializedWires: Realized wire summaries in stable order.
        _realizedRouteSet: Canonical realized route set for board rendering and collision checks.
    """

    board: Board
    solution: "BoardSolution"
    _materializedWires: tuple[BoardMaterializedWire, ...]
    _realizedRouteSet: RealizedRouteSet

    def __dir__(self) -> list[str]:
        """Return the curated public materialized-solution surface.

        Returns:
            Public materialized-solution methods intended for interactive use.
        """

        return [
            "algebraicWorld_text",
            "boundaryViolations_get",
            "boundaryViolations_text",
            "collisions_get",
            "collisions_text",
            "geometry_text",
            "occupancyViolations_get",
            "occupancyViolations_text",
            "occupancy_text",
            "summary_text",
            "wiring_text",
        ]

    def summary_text(self) -> str:
        """Return a concise summary of this materialized solution.

        Returns:
            Multi-line summary of board side, zone, and realized wire count.
        """

        return "\n".join(
            [
                f"materialized solution on board {self.board.side} of {self.board.routingZoneId.id}",
                f"  wireCount: {len(self._materializedWires)}",
            ]
        )

    def wiring_text(self) -> str:
        """Return detailed wire summaries for all realized wires.

        Returns:
            Multi-line text containing one realized wire summary block per wire.
        """

        if not self._materializedWires:
            return "<no materialized wires>"
        return "\n\n".join(wire.summary_text() for wire in self._materializedWires)

    def algebraicWorld_text(self, endpointText: str) -> str:
        """Return world-annotated algebraic text for matching wires.

        Args:
            endpointText: Endpoint or wire text used to select matching wires.

        Returns:
            World-annotated algebraic path text for matching wires, or fallback text.
        """

        matching = tuple(
            wire
            for wire in self._materializedWires
            if endpointText in (
                wire.solvedWire.kernelWire.sourceEndpointText,
                wire.solvedWire.kernelWire.destinationEndpointText,
                wire.solvedWire.wireText_get(),
            )
        )
        if not matching:
            return f"<no wiring for endpoint {endpointText}>"
        return "\n".join(wire.algebraicWorld_text() for wire in matching)

    def occupancy_text(self) -> str:
        """Return a readable occupancy and collision report.

        Returns:
            Multi-line occupancy report covering symbolic and rendered collisions.
        """

        report = self._collisionReport_build()
        occupancy = report["collisions"]
        symbolicChannelClaims = report["claims"]["symbolic_channel"]
        symbolicFanClaims = report["claims"]["symbolic_fan"]

        lines: list[str] = ["symbolic channel claims:"]
        for claimToken in sorted(symbolicChannelClaims):
            lines.append(f"  {claimToken}: {' | '.join(symbolicChannelClaims[claimToken])}")
        lines.append("")
        lines.append("symbolic fan claims:")
        for claimToken in sorted(symbolicFanClaims):
            lines.append(f"  {claimToken}: {' | '.join(symbolicFanClaims[claimToken])}")
        lines.append("")
        lines.append("symbolic channel collisions:")
        lines.extend(
            [f"  {entry['token']}: {' | '.join(entry['wires'])}" for entry in occupancy["symbolic_channel"]]
            or ["  <none>"]
        )
        lines.append("")
        lines.append("symbolic fan sharing:")
        lines.extend(
            [f"  {entry['token']}: {' | '.join(entry['wires'])}" for entry in occupancy["symbolic_fan"]]
            or ["  <none>"]
        )
        lines.append("")
        lines.append("rendered board-cell collisions:")
        lines.extend(
            [
                f"  ({entry['cell'][1]},{entry['cell'][0]})"
                f" [{', '.join(entry['regions']) or 'unowned'}]: "
                f"{' | '.join(entry['wires'])}"
                for entry in occupancy["rendered_board_cell"]
            ]
            or ["  <none>"]
        )
        lines.append("")
        lines.append("rendered fan-cell sharing:")
        lines.extend(
            [
                f"  ({entry['cell'][1]},{entry['cell'][0]})"
                f" [{', '.join(entry['regions']) or 'unowned'}]: "
                f"{' | '.join(entry['wires'])}"
                for entry in occupancy["rendered_fan"]
            ]
            or ["  <none>"]
        )
        return "\n".join(lines)

    def occupancyViolations_get(self) -> dict[str, list[dict[str, object]]]:
        """Return structured occupancy-related collision categories.

        Returns:
            Mapping of occupancy collision categories to structured entries.
        """

        collisions = self._collisionReport_build()["collisions"]
        return {
            "symbolic_channel": collisions["symbolic_channel"],
            "symbolic_fan": collisions["symbolic_fan"],
            "rendered_board_cell": collisions["rendered_board_cell"],
            "rendered_fan": collisions["rendered_fan"],
        }

    def occupancyViolations_text(self) -> str:
        """Return the occupancy violation report as text.

        Returns:
            Multi-line occupancy violation report.
        """

        return self.occupancy_text()

    def boundaryViolations_get(self) -> list[dict[str, object]]:
        """Return structured boundary-overlap violations.

        Returns:
            Structured boundary-overlap violations for this materialized result.
        """

        return self._collisionReport_build()["collisions"]["boundary"]

    def boundaryViolations_text(self) -> str:
        """Return the boundary violation report as text.

        Returns:
            Multi-line boundary violation report.
        """

        violations = self.boundaryViolations_get()
        if not violations:
            return "boundary violations:\n  <none>"
        lines = ["boundary violations:"]
        for entry in violations:
            cellText = ", ".join(
                f"({rowIndex},{columnIndex})"
                for columnIndex, rowIndex in entry["cells"]
            )
            lines.extend(
                [
                    f"  {entry['wire']}",
                    f"    boundary: {entry['boundary']}",
                    f"    kind: {entry['kind']}",
                    f"    cells: {cellText}",
                ]
            )
        return "\n".join(lines)

    def collisions_get(self) -> dict[str, object]:
        """Return the complete structured collision report.

        Returns:
            Structured collision report covering symbolic, rendered, and boundary categories.
        """

        return self._collisionReport_build()

    def collisions_text(self) -> str:
        """Return the complete collision report as readable text.

        Returns:
            Multi-line collision report across all tracked collision categories.
        """

        report = self.collisions_get()
        counts = report["counts"]
        collisions = report["collisions"]
        lines = [
            "collisions:",
            f"  boundary: {counts['boundary']}",
            f"  symbolic_channel: {counts['symbolic_channel']}",
            f"  symbolic_fan: {counts['symbolic_fan']}",
            f"  rendered_board_cell: {counts['rendered_board_cell']}",
            f"  rendered_fan: {counts['rendered_fan']}",
        ]
        for category in (
            "boundary",
            "symbolic_channel",
            "symbolic_fan",
            "rendered_board_cell",
            "rendered_fan",
        ):
            entries = collisions[category]
            lines.append("")
            lines.append(f"{category}:")
            if not entries:
                lines.append("  <none>")
                continue
            if category == "boundary":
                for entry in entries:
                    lines.append(f"  {entry['wire']}")
                    lines.append(f"    boundary: {entry['boundary']}")
                    lines.append(f"    kind: {entry['kind']}")
                    lines.append(
                        "    cells: "
                        + ", ".join(
                            f"({rowIndex},{columnIndex})"
                            for columnIndex, rowIndex in entry["cells"]
                        )
                    )
            elif category in {"symbolic_channel", "symbolic_fan"}:
                for entry in entries:
                    lines.append(f"  {entry['token']}: {' | '.join(entry['wires'])}")
            else:
                for entry in entries:
                    lines.append(
                        f"  ({entry['cell'][1]},{entry['cell'][0]}) "
                        f"[{', '.join(entry['regions']) or 'unowned'}]: "
                        f"{' | '.join(entry['wires'])}"
                    )
        return "\n".join(lines)

    def geometry_text(self) -> str:
        """Render the board geometry with realized wires overlaid.

        Returns:
            Multi-line board geometry text including realized wires and wire legend.
        """

        baseCanvasLines = list(
            boardCanvas_render(
                board=self.board,
                realizedRouteSet=self._realizedRouteSet,
            )
        )
        routeCells = {
            (cell.worldCol, cell.worldRow)
            for realizedRoute in self._realizedRouteSet.realizedRoutes
            for cell in realizedRoute.cells
        }
        cropFrames: list[WorldFrame] = [
            chipPlacement.worldFrame_get()
            for chipPlacement in self.board.geometry.chipDrawPlacementsByChip.values()
        ]
        cropFrames.extend(
            WorldFrame(
                topLeft=(frame.horizontalStart, frame.verticalStart),
                bottomRight=(
                    frame.horizontalEnd_calculate() - 1,
                    frame.verticalEnd_calculate() - 1,
                ),
            )
            for frame in self.board.geometry.effectiveBoundaryFramesByName.values()
        )
        wiringLegendLines = [
            "",
            "wires:",
            *[
                f"  {wire.solvedWire.wireText_get()}  ->  {wire.solvedWire.algebraicPathText}"
                for wire in self._materializedWires
            ],
        ]
        return realizedGeometry_text(
            baseCanvasLines=baseCanvasLines,
            routeCells=routeCells,
            extraFrames=tuple(cropFrames),
            wiringLegendLines=tuple(wiringLegendLines),
        )

    def _collisionReport_build(self) -> dict[str, object]:
        symbolicChannelClaims: dict[str, list[str]] = {}
        symbolicFanClaims: dict[str, list[str]] = {}
        cellClaims: dict[tuple[int, int], list[str]] = {}
        cellDirectionsByWire: dict[tuple[int, int], dict[str, frozenset[TrackDirection]]] = {}
        routeCellsByWire: dict[str, set[tuple[int, int]]] = {}
        boardGeometry = self.board.geometry

        for materializedWire in self._materializedWires:
            wireText = materializedWire.solvedWire.wireText_get()
            routeCellsByWire[wireText] = set(materializedWire.routeCells)
            pathTokens = materializedWire.solvedWire.algebraicPathText.split("::")
            for tokenText in pathTokens[1:6]:
                if re.fullmatch(r"[a-zA-Z]+\[\d+\]", tokenText) is None:
                    continue
                if tokenText in {"wf[0]", "ef[0]"}:
                    symbolicFanClaims.setdefault(tokenText, []).append(wireText)
                    continue
                symbolicChannelClaims.setdefault(tokenText, []).append(wireText)
            for columnIndex, rowIndex in materializedWire.routeCells:
                cellClaims.setdefault((columnIndex, rowIndex), []).append(wireText)

        for realizedRoute in self._realizedRouteSet.realizedRoutes:
            wireText = (
                f"{realizedRoute.sourceChipRef.chipId.moduleName}."
                f"{realizedRoute.sourceChipRef.chipId.functionName}:"
                f"{realizedRoute.destinationChipRef.chipId.moduleName}."
                f"{realizedRoute.destinationChipRef.chipId.functionName}"
            )
            for realizedCell in realizedRoute.cells:
                cellDirectionsByWire.setdefault(
                    (realizedCell.worldCol, realizedCell.worldRow),
                    {},
                )[wireText] = realizedCell.trackCell.directions

        symbolicChannelCollisions: list[dict[str, object]] = []
        for claimToken in sorted(symbolicChannelClaims):
            claimants = symbolicChannelClaims[claimToken]
            if len(claimants) > 1:
                symbolicChannelCollisions.append(
                    {"token": claimToken, "wires": tuple(claimants)}
                )

        symbolicFanSharing: list[dict[str, object]] = []
        for claimToken in sorted(symbolicFanClaims):
            claimants = symbolicFanClaims[claimToken]
            if len(claimants) > 1:
                symbolicFanSharing.append(
                    {"token": claimToken, "wires": tuple(claimants)}
                )

        renderedBoardCollisions: list[dict[str, object]] = []
        renderedFanCollisions: list[dict[str, object]] = []
        for (columnIndex, rowIndex), claimants in sorted(
            cellClaims.items(),
            key=lambda item: (item[0][1], item[0][0]),
        ):
            if len(claimants) <= 1:
                continue
            regionKinds = _regionTaggedNamesForWorldCell_build(
                boardGeometry,
                columnIndex,
                rowIndex,
            )
            if any("transition" in regionName for regionName in regionKinds):
                continue
            directionsByWire = cellDirectionsByWire.get((columnIndex, rowIndex), {})
            claimantDirections = [
                directionsByWire.get(claimant, frozenset())
                for claimant in claimants
            ]
            if len(claimantDirections) == 2:
                directions0, directions1 = claimantDirections
                isHorizontal0 = directions0 <= {TrackDirection.EAST, TrackDirection.WEST}
                isVertical0 = directions0 <= {TrackDirection.NORTH, TrackDirection.SOUTH}
                isHorizontal1 = directions1 <= {TrackDirection.EAST, TrackDirection.WEST}
                isVertical1 = directions1 <= {TrackDirection.NORTH, TrackDirection.SOUTH}
                if (isHorizontal0 and isVertical1) or (isVertical0 and isHorizontal1):
                    continue
            entry = {
                "cell": (columnIndex, rowIndex),
                "wires": tuple(claimants),
                "regions": tuple(regionKinds),
            }
            if any("fan_in_out" in regionName for regionName in regionKinds):
                renderedFanCollisions.append(entry)
            else:
                renderedBoardCollisions.append(entry)

        exactTerminalCells = {
            terminalPosition
            for terminalPositions in boardGeometry.exactTerminalWorldPositionsByChip.values()
            for terminalPosition in terminalPositions.values()
        }
        chipDrawCells: set[tuple[int, int]] = set()
        for chipPlacement in boardGeometry.chipDrawPlacementsByChip.values():
            chipFrame = chipPlacement.worldFrame_get()
            for rowIndex in range(chipFrame.topLeft[1], chipFrame.bottomRight[1] + 1):
                for columnIndex in range(chipFrame.topLeft[0], chipFrame.bottomRight[0] + 1):
                    chipDrawCells.add((columnIndex, rowIndex))

        boundaryViolations: list[dict[str, object]] = []
        for boundaryName, frame in boardGeometry.effectiveBoundaryFramesByName.items():
            borderCells = _frameBorderCells_build(frame)
            interiorCells = _frameInteriorCells_build(frame)
            for wireText, routeCells in routeCellsByWire.items():
                overlappingBorderCells = tuple(
                    sorted(
                        (
                            cell
                            for cell in (routeCells & borderCells)
                            if cell not in exactTerminalCells
                            and cell not in chipDrawCells
                            and not any(
                                "chip_terminal" in regionName
                                for regionName in _regionTaggedNamesForWorldCell_build(
                                    boardGeometry,
                                    cell[0],
                                    cell[1],
                                )
                            )
                        ),
                        key=lambda cell: (cell[1], cell[0]),
                    )
                )
                if overlappingBorderCells:
                    boundaryViolations.append(
                        {
                            "wire": wireText,
                            "boundary": boundaryName,
                            "kind": "border_overlap",
                            "cells": overlappingBorderCells,
                        }
                    )
                overlappingInteriorCells = tuple(
                    sorted(
                        (
                            cell
                            for cell in (routeCells & interiorCells)
                            if cell not in exactTerminalCells
                            and cell not in chipDrawCells
                            and not any(
                                "chip_terminal" in regionName
                                for regionName in _regionTaggedNamesForWorldCell_build(
                                    boardGeometry,
                                    cell[0],
                                    cell[1],
                                )
                            )
                        ),
                        key=lambda cell: (cell[1], cell[0]),
                    )
                )
                if overlappingInteriorCells:
                    boundaryViolations.append(
                        {
                            "wire": wireText,
                            "boundary": boundaryName,
                            "kind": "interior_overlap",
                            "cells": overlappingInteriorCells,
                        }
                    )

        return {
            "hasCollisions": any(
                (
                    boundaryViolations,
                    symbolicChannelCollisions,
                    symbolicFanSharing,
                    renderedBoardCollisions,
                    renderedFanCollisions,
                )
            ),
            "counts": {
                "boundary": len(boundaryViolations),
                "symbolic_channel": len(symbolicChannelCollisions),
                "symbolic_fan": len(symbolicFanSharing),
                "rendered_board_cell": len(renderedBoardCollisions),
                "rendered_fan": len(renderedFanCollisions),
            },
            "claims": {
                "symbolic_channel": {
                    token: tuple(wires)
                    for token, wires in symbolicChannelClaims.items()
                },
                "symbolic_fan": {
                    token: tuple(wires)
                    for token, wires in symbolicFanClaims.items()
                },
            },
            "collisions": {
                "boundary": boundaryViolations,
                "symbolic_channel": symbolicChannelCollisions,
                "symbolic_fan": symbolicFanSharing,
                "rendered_board_cell": renderedBoardCollisions,
                "rendered_fan": renderedFanCollisions,
            },
        }


def materializedSolution_build(
    board: Board,
    solution: "BoardSolution",
    policy: BoardMaterializePolicy | None = None,
) -> BoardMaterializedSolution:
    """Build a materialized solution from one solved board route set.

    Args:
        board: Board that defines the legal realization substrate.
        solution: Solved algebraic route set to realize onto the board.
        policy: Optional realization policy.

    Returns:
        `BoardMaterializedSolution` realized onto the requested board.
    """

    baseRegionFramesByName = dict(board.geometry.regionFramesByName)
    routeInputsMutable: list[tuple[str, tuple[int, int], tuple[int, int]]] = []
    for solvedWire in solution.all_get():
        pathTokens = solvedWire.algebraicPathText.split("::")
        if len(pathTokens) != 7:
            continue
        sourceAttachPoint = _boardEndpointAttachPoint_build(board, pathTokens[0])
        destinationAttachPoint = _boardEndpointAttachPoint_build(board, pathTokens[6])
        if sourceAttachPoint is None or destinationAttachPoint is None:
            continue
        routeInputsMutable.append(
            (
                solvedWire.algebraicPathText,
                sourceAttachPoint,
                destinationAttachPoint,
            )
        )

    realizationPlan = realizationPlan_build(
        routeInputs=tuple(routeInputsMutable),
        regionFramesByName=baseRegionFramesByName,
        policy=policy or BoardMaterializePolicy(),
    )

    materializedWiresMutable: list[BoardMaterializedWire] = []
    realizedRoutesMutable: list[RealizedRoute] = []
    for solvedWire in solution.all_get():
        materializedPath = _materializedPath_build(
            board=board,
            solvedWire=solvedWire,
            regionFramesByName=realizationPlan.regionFramesByName,
            prebuiltRealization=realizationPlan.routeRealizationsByPathText.get(
                solvedWire.algebraicPathText
            ),
        )
        realizedRoute = _realizedRoute_buildFromCellWalk(
            sourceChipRef=solvedWire.kernelWire.sourceChipRef,
            destinationChipRef=solvedWire.kernelWire.destinationChipRef,
            childCallIndex=0,
            cellWalk=materializedPath.routeCells,
            routeSense=(
                RouteSense.BACK
                if solvedWire.kernelWire.isReturn
                else RouteSense.FORWARD
            ),
        )
        if realizedRoute is not None:
            realizedRoutesMutable.append(realizedRoute)
            routeCells = tuple(
                (cell.worldCol, cell.worldRow)
                for cell in realizedRoute.cells
            )
        else:
            routeCells = tuple()
        materializedWiresMutable.append(
            BoardMaterializedWire(
                solvedWire=solvedWire,
                tokenStartPoints=materializedPath.tokenStartPoints,
                routePoints=materializedPath.routePoints,
                routeCells=routeCells,
            )
        )

    return BoardMaterializedSolution(
        board=board,
        solution=solution,
        _materializedWires=tuple(materializedWiresMutable),
        _realizedRouteSet=RealizedRouteSet(
            realizedRoutes=tuple(realizedRoutesMutable)
        ),
    )


def _materializedPath_build(
    board: Board,
    solvedWire: "BoardSolvedWire",
    regionFramesByName: dict[str, RoutingZoneRegionFrame] | None = None,
    prebuiltRealization=None,
) -> _MaterializedPath:
    pathTokens = solvedWire.algebraicPathText.split("::")
    if len(pathTokens) != 7:
        return _MaterializedPath(tuple(), tuple(), tuple())
    sourceAttachPoint = _boardEndpointAttachPoint_build(board, pathTokens[0])
    destinationAttachPoint = _boardEndpointAttachPoint_build(board, pathTokens[6])
    if sourceAttachPoint is None or destinationAttachPoint is None:
        return _MaterializedPath(tuple(), tuple(), tuple())
    if prebuiltRealization is not None:
        return _MaterializedPath(
            tokenStartPoints=prebuiltRealization.tokenStartPoints,
            routePoints=prebuiltRealization.routePoints,
            routeCells=prebuiltRealization.routeCells,
        )
    realizedRoute = algebraicRouteRealization_build(
        algebraicPathText=solvedWire.algebraicPathText,
        sourceAttachPoint=sourceAttachPoint,
        destinationAttachPoint=destinationAttachPoint,
        regionFramesByName=regionFramesByName or dict(board.geometry.regionFramesByName),
    )
    return _MaterializedPath(
        tokenStartPoints=realizedRoute.tokenStartPoints,
        routePoints=realizedRoute.routePoints,
        routeCells=realizedRoute.routeCells,
    )


def _boardEndpointAttachPoint_build(
    board: Board,
    endpointText: str,
) -> tuple[int, int] | None:
    endpointParts = endpointText.split(".")
    if len(endpointParts) < 3:
        return None
    terminalName = endpointParts[-1]
    chipName = ".".join(endpointParts[:-1])
    return board.terminal_get(chipName, terminalName)


def _regionTaggedNamesForWorldCell_build(
    boardGeometry,
    columnIndex: int,
    rowIndex: int,
) -> tuple[str, ...]:
    taggedNamesMutable: list[str] = []
    for regionName, frame in boardGeometry.regionFramesByName.items():
        if (
            frame.horizontalStart <= columnIndex < frame.horizontalEnd_calculate()
            and frame.verticalStart <= rowIndex < frame.verticalEnd_calculate()
        ):
            taggedNamesMutable.append(regionName)
    return tuple(sorted(taggedNamesMutable))


def _frameBorderCells_build(
    frame: RoutingZoneRegionFrame,
) -> set[tuple[int, int]]:
    horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
    verticalEndInclusive = frame.verticalEnd_calculate() - 1
    cells: set[tuple[int, int]] = set()
    for columnIndex in range(frame.horizontalStart, horizontalEndInclusive + 1):
        cells.add((columnIndex, frame.verticalStart))
        cells.add((columnIndex, verticalEndInclusive))
    for rowIndex in range(frame.verticalStart, verticalEndInclusive + 1):
        cells.add((frame.horizontalStart, rowIndex))
        cells.add((horizontalEndInclusive, rowIndex))
    return cells


def _frameInteriorCells_build(
    frame: RoutingZoneRegionFrame,
) -> set[tuple[int, int]]:
    horizontalEndInclusive = frame.horizontalEnd_calculate() - 1
    verticalEndInclusive = frame.verticalEnd_calculate() - 1
    if horizontalEndInclusive - frame.horizontalStart < 2:
        return set()
    if verticalEndInclusive - frame.verticalStart < 2:
        return set()
    return {
        (columnIndex, rowIndex)
        for columnIndex in range(frame.horizontalStart + 1, horizontalEndInclusive)
        for rowIndex in range(frame.verticalStart + 1, verticalEndInclusive)
    }


def _realizedRoute_buildFromCellWalk(
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    cellWalk: tuple[tuple[int, int], ...],
    routeSense: RouteSense,
) -> RealizedRoute | None:
    if len(cellWalk) < 2:
        return None

    directionMap: dict[tuple[int, int], set[TrackDirection]] = {}

    def _directionSet_get(columnIndex: int, rowIndex: int) -> set[TrackDirection]:
        return directionMap.setdefault((columnIndex, rowIndex), set())

    for (column0, row0), (column1, row1) in zip(
        cellWalk,
        cellWalk[1:],
        strict=False,
    ):
        columnDelta = column1 - column0
        rowDelta = row1 - row0
        if abs(columnDelta) + abs(rowDelta) != 1:
            return None
        if columnDelta == 1:
            _directionSet_get(column0, row0).add(TrackDirection.EAST)
            _directionSet_get(column1, row1).add(TrackDirection.WEST)
        elif columnDelta == -1:
            _directionSet_get(column0, row0).add(TrackDirection.WEST)
            _directionSet_get(column1, row1).add(TrackDirection.EAST)
        elif rowDelta == 1:
            _directionSet_get(column0, row0).add(TrackDirection.SOUTH)
            _directionSet_get(column1, row1).add(TrackDirection.NORTH)
        else:
            _directionSet_get(column0, row0).add(TrackDirection.NORTH)
            _directionSet_get(column1, row1).add(TrackDirection.SOUTH)

    realizedCells: tuple[RealizedRouteCell, ...] = tuple(
        RealizedRouteCell(
            worldRow=rowIndex,
            worldCol=columnIndex,
            trackCell=trackCell_build(frozenset(directions)),
        )
        for (columnIndex, rowIndex), directions in sorted(
            directionMap.items(),
            key=lambda item: (item[0][1], item[0][0]),
        )
    )
    return RealizedRoute(
        sourceChipRef=sourceChipRef,
        destinationChipRef=destinationChipRef,
        childCallIndex=childCallIndex,
        routeSense=routeSense,
        cells=realizedCells,
    )
