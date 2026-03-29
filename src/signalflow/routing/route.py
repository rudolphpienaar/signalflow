"""Route realization for the new SignalFlow engine.

This module converts solved-route polylines (RoutingZoneRoutePoint sequences)
into modeled RealizedRoute objects.  A RealizedRoute is a collection of
per-cell TrackCell entries ready for canvas projection.

Realization is pure geometry: it operates only on world-coordinate waypoints
and emits TrackCells via the Phase 6 track algebra.  No canvas writes happen
here.

Route Sense
-----------
A RouteSense tag (FORWARD / BACK / SELF) is carried on every RealizedRoute
and controls color and presentation in the rendering layer.  It does not
change which cells the route occupies or which glyph each cell shows.  Two
routes with identical waypoints but different senses realize to the same
per-cell TrackCell set — identical topology under different semantics uses
the same path.

Lane Allocation and Sweep
--------------------------
Lane positions are determined by the upstream solvers (zone_solver,
interconnect_solver, grid_solver), which use chip orderIndex as the row or
column offset within each routing region.  This module consumes those
already-assigned positions without re-assigning them.  Sweep order (the
order in which routes contribute to a combined cell map) follows the
declaration order in the input set so that lane numbering is stable across
route variants.

Polyline Expansion
------------------
Each consecutive waypoint pair (Pi → Pi+1) contributes one axis-aligned
segment.  At each cell along a segment the wire apertures are recorded as
TrackDirection entries:

- Horizontal segment going right (c0 < c1):
    leftmost cell  → EAST only
    interior cells → EAST + WEST
    rightmost cell → WEST only

- Horizontal segment going left (c0 > c1):
    leftmost cell  → WEST only
    interior cells → EAST + WEST
    rightmost cell → EAST only

- Vertical segment going down (r0 < r1):
    topmost cell    → SOUTH only
    interior cells  → NORTH + SOUTH
    bottommost cell → NORTH only

- Vertical segment going up (r0 > r1):
    topmost cell    → NORTH only
    interior cells  → NORTH + SOUTH
    bottommost cell → SOUTH only

Turn cells (shared by two consecutive segments) accumulate contributions
from both segments.  The track merge algebra unions the direction sets, so
a right-then-down turn produces {EAST, SOUTH} → ┌ automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.chip import (
    ChipRef,
    ChipTerminal,
    ChipTerminalSide,
    chipDrawLines_build,
)
from signalflow.models.chip_route import (
    ChipInternalRouteSolveKind,
    ChipInternalSolvedRoute,
    ChipInternalSolvedRouteSet,
)
from signalflow.models.circuit import CircuitDocument
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.interconnect_route import (
    RoutingZoneInterconnectSolvedRoute,
    RoutingZoneInterconnectSolvedRouteSet,
)
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.routing_zone import (
    ChipPlacement,
    RoutingZone,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    routingZoneRegionByIdResult_get,
)
from signalflow.models.routing_zone_grid import RoutingZoneGrid
from signalflow.models.zone_route import (
    RoutingZoneLocalSolvedRoute,
    RoutingZoneLocalSolvedRouteSet,
    RoutingZoneRoutePoint,
)
from signalflow.routing.geometry import (
    ChipCanvasPlacementGeometry,
    ChipLocalGeometry,
    ChipLocalGeometrySet,
    chipCanvasPlacementGeometry_build,
    chipLocalGeometrySetResult_buildFromChips,
    chipPlacementStackSpan_calculate,
)
from signalflow.routing.track import TrackCell, TrackDirection, trackCell_build


class RouteSense(Enum):
    """Semantic classification for one realized route.

    Attributes:
        FORWARD: Normal forward call edge (parent → child).
        BACK: Ancestor / back-edge call (child calls an ancestor).
        SELF: Self-loop call (chip calls itself).
    """

    FORWARD = "forward"
    BACK = "back"
    SELF = "self"


@dataclass(frozen=True)
class RealizedRouteCell:
    """One resolved track-cell entry in a realized route.

    Attributes:
        worldRow: World-coordinate vertical index.
        worldCol: World-coordinate horizontal index.
        trackCell: Resolved box-drawing cell for this position.
    """

    worldRow: int
    worldCol: int
    trackCell: TrackCell


@dataclass(frozen=True)
class RealizedRoute:
    """Fully realized route: metadata plus ordered per-cell geometry.

    Attributes:
        sourceChipRef: Originating chip.
        destinationChipRef: Target chip.
        childCallIndex: Call-sequence index for disambiguation.
        routeSense: Semantic classification; does not affect cell geometry.
        cells: Ordered tuple of realized track cells (sorted by row, col).
    """

    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    childCallIndex: int
    routeSense: RouteSense
    cells: tuple[RealizedRouteCell, ...]

    def cellAt_get(self, worldRow: int, worldCol: int) -> TrackCell | None:
        """Return the TrackCell at (worldRow, worldCol), or None if absent.

        Args:
            worldRow: World-coordinate vertical index to look up.
            worldCol: World-coordinate horizontal index to look up.

        Returns:
            The resolved TrackCell at the given position, or None.
        """

        for c in self.cells:
            if c.worldRow == worldRow and c.worldCol == worldCol:
                return c.trackCell
        return None


@dataclass(frozen=True)
class RealizedRouteSet:
    """Modeled collection of realized routes.

    Attributes:
        realizedRoutes: All realized routes in this set.
    """

    realizedRoutes: tuple[RealizedRoute, ...] = field(default_factory=tuple)

    def routesForChip_get(
        self,
        chipRef: ChipRef,
    ) -> tuple[RealizedRoute, ...]:
        """Return all realized routes that touch one chip.

        Args:
            chipRef: Chip reference to look up.

        Returns:
            Tuple of RealizedRoute objects where the chip is either the
            source or the destination.
        """

        return tuple(
            r
            for r in self.realizedRoutes
            if r.sourceChipRef == chipRef or r.destinationChipRef == chipRef
        )

    def mergedCellMap_get(self) -> dict[tuple[int, int], TrackCell]:
        """Merge all routes into one (worldRow, worldCol) → TrackCell map.

        Overlapping routes are combined via the track merge algebra so that
        intersecting wires produce the correct tee or cross glyphs.

        Returns:
            Dictionary mapping (worldRow, worldCol) positions to resolved
            TrackCells that represent the union of all route wires.
        """

        dirAccum: dict[tuple[int, int], set[TrackDirection]] = {}
        for route in self.realizedRoutes:
            for cell in route.cells:
                key = (cell.worldRow, cell.worldCol)
                if key not in dirAccum:
                    dirAccum[key] = set()
                dirAccum[key] |= cell.trackCell.directions
        return {
            key: trackCell_build(frozenset(dirs)) for key, dirs in dirAccum.items()
        }


@dataclass(frozen=True)
class _ChipCanvasPlacement:
    """World placement plus local draw geometry for one chip body."""

    chipRef: ChipRef
    worldRow: int
    worldCol: int
    boxWorldRow: int
    boxWorldCol: int
    chipLocalGeometry: ChipLocalGeometry
    drawLines: tuple[str, ...]


def routePoints_realize(
    sourceChipRef: ChipRef,
    destinationChipRef: ChipRef,
    childCallIndex: int,
    routePoints: tuple[RoutingZoneRoutePoint, ...],
    routeSense: RouteSense = RouteSense.FORWARD,
) -> Result[RealizedRoute]:
    """Realize one solved route polyline into per-cell TrackCells.

    Expands each consecutive waypoint pair into one axis-aligned segment and
    records the wire apertures (TrackDirection entries) at every cell along
    the segment.  Turn cells accumulate contributions from both their
    incoming and outgoing segments, so the correct elbow or tee glyph is
    resolved automatically by the track merge algebra.

    Args:
        sourceChipRef: Originating chip reference.
        destinationChipRef: Target chip reference.
        childCallIndex: Call-sequence index for disambiguation.
        routePoints: Ordered world-coordinate waypoints (at least two).
        routeSense: Semantic tag; does not affect cell geometry.

    Returns:
        Successful result containing the RealizedRoute, or a failed result
        if the polyline contains fewer than two points or a diagonal segment.
    """

    if len(routePoints) < 2:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.route.realize.too_few_points",
            message="Route polylines must contain at least two waypoints",
        )
        return resultErr_build()

    dirMap: dict[tuple[int, int], set[TrackDirection]] = {}

    def _addDir(row: int, col: int, direction: TrackDirection) -> None:
        key = (row, col)
        if key not in dirMap:
            dirMap[key] = set()
        dirMap[key].add(direction)

    for i in range(len(routePoints) - 1):
        p0 = routePoints[i]
        p1 = routePoints[i + 1]
        r0: int = p0.verticalIndex
        c0: int = p0.horizontalIndex
        r1: int = p1.verticalIndex
        c1: int = p1.horizontalIndex

        if r0 == r1 and c0 == c1:
            # Zero-length segment between coincident waypoints — skip.
            continue

        if r0 != r1 and c0 != c1:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.route.realize.diagonal_segment",
                message=(
                    "Route polylines may only contain axis-aligned segments; "
                    "diagonal segment detected"
                ),
                context=(str(r0), str(c0), str(r1), str(c1)),
            )
            return resultErr_build()

        if r0 == r1:
            # Horizontal segment.
            if c0 < c1:
                # Going right (east).
                _addDir(r0, c0, TrackDirection.EAST)
                for c in range(c0 + 1, c1):
                    _addDir(r0, c, TrackDirection.EAST)
                    _addDir(r0, c, TrackDirection.WEST)
                _addDir(r0, c1, TrackDirection.WEST)
            else:
                # Going left (west); c0 > c1.
                _addDir(r0, c0, TrackDirection.WEST)
                for c in range(c1 + 1, c0):
                    _addDir(r0, c, TrackDirection.EAST)
                    _addDir(r0, c, TrackDirection.WEST)
                _addDir(r0, c1, TrackDirection.EAST)
        else:
            # Vertical segment; c0 == c1.
            if r0 < r1:
                # Going down (south).
                _addDir(r0, c0, TrackDirection.SOUTH)
                for r in range(r0 + 1, r1):
                    _addDir(r, c0, TrackDirection.NORTH)
                    _addDir(r, c0, TrackDirection.SOUTH)
                _addDir(r1, c0, TrackDirection.NORTH)
            else:
                # Going up (north); r0 > r1.
                _addDir(r0, c0, TrackDirection.NORTH)
                for r in range(r1 + 1, r0):
                    _addDir(r, c0, TrackDirection.NORTH)
                    _addDir(r, c0, TrackDirection.SOUTH)
                _addDir(r1, c0, TrackDirection.SOUTH)

    cells: tuple[RealizedRouteCell, ...] = tuple(
        RealizedRouteCell(
            worldRow=row,
            worldCol=col,
            trackCell=trackCell_build(frozenset(dirs)),
        )
        for (row, col), dirs in sorted(dirMap.items())
    )

    return resultOk_build(
        RealizedRoute(
            sourceChipRef=sourceChipRef,
            destinationChipRef=destinationChipRef,
            childCallIndex=childCallIndex,
            routeSense=routeSense,
            cells=cells,
        )
    )


def realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
    solvedRouteSet: RoutingZoneLocalSolvedRouteSet,
    defaultRouteSense: RouteSense = RouteSense.FORWARD,
) -> Result[RealizedRouteSet]:
    """Build a RealizedRouteSet from a set of solved zone-local routes.

    Each solved route's waypoint polyline is expanded into per-cell
    TrackCells using the polyline realization algorithm.

    Args:
        solvedRouteSet: Solved zone-local routes from the zone solver.
        defaultRouteSense: Sense tag applied to every realized route.
            Defaults to FORWARD; caller may supply BACK or SELF when the
            circuit document supplies edge-sense information.

    Returns:
        Successful result containing the RealizedRouteSet, or a failed
        result if any individual route polyline cannot be realized.
    """

    realizedRoutesMutable: list[RealizedRoute] = []
    solvedRoute: RoutingZoneLocalSolvedRoute
    for solvedRoute in solvedRouteSet.routingZoneLocalSolvedRoutes:
        realizedResult: Result[RealizedRoute] = routePoints_realize(
            sourceChipRef=solvedRoute.sourceChipRef,
            destinationChipRef=solvedRoute.destinationChipRef,
            childCallIndex=solvedRoute.childCallIndex,
            routePoints=solvedRoute.routePoints,
            routeSense=defaultRouteSense,
        )
        if not result_isOkCheck(realizedResult):
            return resultErr_build()
        realizedRoutesMutable.append(realizedResult.value)

    return resultOk_build(
        RealizedRouteSet(realizedRoutes=tuple(realizedRoutesMutable))
    )


def realizedRouteSetResult_buildFromInterconnectSolvedRouteSet(
    solvedRouteSet: RoutingZoneInterconnectSolvedRouteSet,
    defaultRouteSense: RouteSense = RouteSense.FORWARD,
) -> Result[RealizedRouteSet]:
    """Build a RealizedRouteSet from a set of solved seam-crossing routes.

    Each solved seam route's waypoint polyline is expanded into per-cell
    TrackCells using the same polyline realization algorithm used for
    zone-local routes.

    Args:
        solvedRouteSet: Solved seam-crossing routes from the interconnect solver.
        defaultRouteSense: Sense tag applied to every realized route.

    Returns:
        Successful result containing the RealizedRouteSet, or a failed
        result if any individual route polyline cannot be realized.
    """

    realizedRoutesMutable: list[RealizedRoute] = []
    solvedRoute: RoutingZoneInterconnectSolvedRoute
    for solvedRoute in solvedRouteSet.routingZoneInterconnectSolvedRoutes:
        realizedResult: Result[RealizedRoute] = routePoints_realize(
            sourceChipRef=solvedRoute.sourceChipRef,
            destinationChipRef=solvedRoute.destinationChipRef,
            childCallIndex=solvedRoute.childCallIndex,
            routePoints=solvedRoute.routePoints,
            routeSense=defaultRouteSense,
        )
        if not result_isOkCheck(realizedResult):
            return resultErr_build()
        realizedRoutesMutable.append(realizedResult.value)

    return resultOk_build(
        RealizedRouteSet(realizedRoutes=tuple(realizedRoutesMutable))
    )


def realizedRouteSetResult_buildFromChipInternalSolvedRouteSet(
    circuitDocument: CircuitDocument,
    placedGrid: RoutingZoneGrid,
    solvedRouteSet: ChipInternalSolvedRouteSet,
    defaultRouteSense: RouteSense = RouteSense.FORWARD,
) -> Result[RealizedRouteSet]:
    """Build a RealizedRouteSet from solved chip-internal routes.

    Chip-internal route realization converts chip-local solve kinds into
    world-coordinate orthogonal polylines inside the owning chip body.
    """

    chipLocalGeometrySetResult = chipLocalGeometrySetResult_buildFromChips(
        circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(chipLocalGeometrySetResult):
        return resultErr_build()

    chipPlacementMapResult = _chipCanvasPlacementMapResult_build(
        placedGrid=placedGrid,
        circuitDocument=circuitDocument,
        chipLocalGeometrySet=chipLocalGeometrySetResult.value,
    )
    if not result_isOkCheck(chipPlacementMapResult):
        return resultErr_build()

    realizedRoutesMutable: list[RealizedRoute] = []
    routeIndex: int
    solvedRoute: ChipInternalSolvedRoute
    for routeIndex, solvedRoute in enumerate(
        solvedRouteSet.chipInternalSolvedRoutes
    ):
        routePointsResult = _chipInternalRoutePointsResult_build(
            solvedRoute=solvedRoute,
            chipCanvasPlacementMap=chipPlacementMapResult.value,
        )
        if not result_isOkCheck(routePointsResult):
            return resultErr_build()
        routeSense: RouteSense = (
            RouteSense.SELF
            if (
                solvedRoute.sourceTerminal.terminalName
                == solvedRoute.destinationTerminal.terminalName
                and solvedRoute.sourceTerminal.terminalSide
                is solvedRoute.destinationTerminal.terminalSide
            )
            else defaultRouteSense
        )
        realizedRouteResult = routePoints_realize(
            sourceChipRef=solvedRoute.chipRef,
            destinationChipRef=solvedRoute.chipRef,
            childCallIndex=routeIndex,
            routePoints=routePointsResult.value,
            routeSense=routeSense,
        )
        if not result_isOkCheck(realizedRouteResult):
            return resultErr_build()
        realizedRoutesMutable.append(realizedRouteResult.value)

    return resultOk_build(
        RealizedRouteSet(realizedRoutes=tuple(realizedRoutesMutable))
    )


def _chipCanvasPlacementMapResult_build(
    placedGrid: RoutingZoneGrid,
    circuitDocument: CircuitDocument,
    chipLocalGeometrySet: ChipLocalGeometrySet,
) -> Result[dict[ChipRef, _ChipCanvasPlacement]]:
    """Build world-placement records for every placed chip body."""

    placementMapMutable: dict[ChipRef, _ChipCanvasPlacement] = {}
    zone: RoutingZone
    for zone in placedGrid.routingZoneSet.routingZones:
        isWestToEast: bool = zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST
        for side in (
            RoutingZoneRegionSide.WEST,
            RoutingZoneRegionSide.EAST,
            RoutingZoneRegionSide.NORTH,
            RoutingZoneRegionSide.SOUTH,
        ):
            sidePlacements: list[ChipPlacement] = sorted(
                (
                    placement
                    for placement in zone.chipPlacementSet.placements
                    if placement.chipTerminalRegionId.routingZoneRegionSide is side
                ),
                key=lambda placement: placement.orderIndex,
            )
            if not sidePlacements:
                continue
            regionResult = routingZoneRegionByIdResult_get(
                zone, sidePlacements[0].chipTerminalRegionId
            )
            if not result_isOkCheck(regionResult):
                return resultErr_build()
            regionFrame = regionResult.value.routingZoneRegionFrame
            cumulativeOffset: int = 0
            placement: ChipPlacement
            for placement in sidePlacements:
                chipResult = circuitDocument.circuitChipSet.chipResult_get(
                    placement.chipRef.chipId
                )
                if not result_isOkCheck(chipResult):
                    return resultErr_build()
                chipLocalGeometryResult = (
                    chipLocalGeometrySet.geometryForChipResult_get(
                        placement.chipRef
                    )
                )
                if not result_isOkCheck(chipLocalGeometryResult):
                    return resultErr_build()
                drawLines = chipDrawLines_build(chipResult.value)
                placementGeometry: ChipCanvasPlacementGeometry = (
                    chipCanvasPlacementGeometry_build(
                        chipLocalGeometry=chipLocalGeometryResult.value,
                        routingZoneSense=zone.routingZoneSense,
                        regionSide=side,
                        terminalRegionVerticalStart=regionFrame.verticalStart,
                        terminalRegionHorizontalStart=regionFrame.horizontalStart,
                        stackOffset=cumulativeOffset,
                    )
                )
                cumulativeOffset += chipPlacementStackSpan_calculate(
                    chipLocalGeometry=chipLocalGeometryResult.value,
                    routingZoneSense=zone.routingZoneSense,
                    regionSide=side,
                )
                placementMapMutable[placement.chipRef] = _ChipCanvasPlacement(
                    chipRef=placement.chipRef,
                    worldRow=placementGeometry.drawWorldRow,
                    worldCol=placementGeometry.drawWorldColumn,
                    boxWorldRow=placementGeometry.boxWorldRow,
                    boxWorldCol=placementGeometry.boxWorldColumn,
                    chipLocalGeometry=chipLocalGeometryResult.value,
                    drawLines=drawLines,
                )
    return resultOk_build(placementMapMutable)


def _chipInternalRoutePointsResult_build(
    solvedRoute: ChipInternalSolvedRoute,
    chipCanvasPlacementMap: dict[ChipRef, _ChipCanvasPlacement],
) -> Result[tuple[RoutingZoneRoutePoint, ...]]:
    """Build world-coordinate route points for one chip-internal solved route."""

    chipCanvasPlacement: _ChipCanvasPlacement | None = chipCanvasPlacementMap.get(
        solvedRoute.chipRef
    )
    if chipCanvasPlacement is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.route.realize.chip_internal.missing_chip_placement",
            message="Chip-internal route realization requires a placed chip body",
            context=(
                solvedRoute.chipRef.chipId.moduleName,
                solvedRoute.chipRef.chipId.functionName,
            ),
        )
        return resultErr_build()

    sourcePointResult = _chipInteriorEntryPointResult_build(
        chipCanvasPlacement=chipCanvasPlacement,
        chipTerminal=solvedRoute.sourceTerminal,
    )
    if not result_isOkCheck(sourcePointResult):
        return resultErr_build()
    destinationPointResult = _chipInteriorEntryPointResult_build(
        chipCanvasPlacement=chipCanvasPlacement,
        chipTerminal=solvedRoute.destinationTerminal,
    )
    if not result_isOkCheck(destinationPointResult):
        return resultErr_build()

    if solvedRoute.solveKind is ChipInternalRouteSolveKind.TRANSVERSE_MANIFOLD:
        return _transverseChipInternalRoutePointsResult_build(
            sourcePoint=sourcePointResult.value,
            destinationPoint=destinationPointResult.value,
            chipCanvasPlacement=chipCanvasPlacement,
        )
    return _sameSideChipInternalRoutePointsResult_build(
        sourcePoint=sourcePointResult.value,
        destinationPoint=destinationPointResult.value,
        sourceTerminal=solvedRoute.sourceTerminal,
        chipCanvasPlacement=chipCanvasPlacement,
    )


def _chipInteriorEntryPointResult_build(
    chipCanvasPlacement: _ChipCanvasPlacement,
    chipTerminal: ChipTerminal,
) -> Result[RoutingZoneRoutePoint]:
    """Build the first interior route cell adjacent to one chip terminal."""

    lineOffsetResult = (
        chipCanvasPlacement.chipLocalGeometry.lineOffsetForTerminalResult_get(
            chipTerminal.terminalSide,
            chipTerminal.terminalName,
        )
    )
    if not result_isOkCheck(lineOffsetResult):
        return resultErr_build()

    lineOffset: int = lineOffsetResult.value
    if not (0 <= lineOffset < len(chipCanvasPlacement.drawLines)):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.route.realize.chip_internal.invalid_terminal_line_offset",
            message=(
                "Chip-internal route terminal line offset is outside the "
                "chip drawing"
            ),
            context=(
                chipCanvasPlacement.chipRef.chipId.moduleName,
                chipCanvasPlacement.chipRef.chipId.functionName,
                chipTerminal.terminalName,
                str(lineOffset),
            ),
        )
        return resultErr_build()

    rowLine: str = chipCanvasPlacement.drawLines[lineOffset]
    westWallColumnResult = _westWallColumnResult_build(rowLine)
    if not result_isOkCheck(westWallColumnResult):
        return resultErr_build()
    eastWallColumnResult = _eastWallColumnResult_build(rowLine)
    if not result_isOkCheck(eastWallColumnResult):
        return resultErr_build()

    worldRow: int = chipCanvasPlacement.worldRow + lineOffset
    if chipTerminal.terminalSide is ChipTerminalSide.WEST:
        worldCol = chipCanvasPlacement.worldCol + westWallColumnResult.value + 1
        return resultOk_build(
            RoutingZoneRoutePoint(horizontalIndex=worldCol, verticalIndex=worldRow)
        )
    if chipTerminal.terminalSide is ChipTerminalSide.EAST:
        worldCol = chipCanvasPlacement.worldCol + eastWallColumnResult.value - 1
        return resultOk_build(
            RoutingZoneRoutePoint(horizontalIndex=worldCol, verticalIndex=worldRow)
        )

    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.route.realize.chip_internal.unsupported_terminal_side",
        message=(
            "Chip-internal route realization currently supports west/east "
            "terminals only"
        ),
        context=(
            chipCanvasPlacement.chipRef.chipId.moduleName,
            chipCanvasPlacement.chipRef.chipId.functionName,
            chipTerminal.terminalSide.value,
            chipTerminal.terminalName,
        ),
    )
    return resultErr_build()


def _westWallColumnResult_build(rowLine: str) -> Result[int]:
    """Find the west wall column in one chip body row."""

    columnIndex: int
    char: str
    for columnIndex, char in enumerate(rowLine):
        if char in {"┤", "│"}:
            return resultOk_build(columnIndex)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.route.realize.chip_internal.missing_west_wall",
        message="Chip-internal route realization could not find the west wall",
    )
    return resultErr_build()


def _eastWallColumnResult_build(rowLine: str) -> Result[int]:
    """Find the east wall column in one chip body row."""

    columnIndex: int
    for columnIndex in range(len(rowLine) - 1, -1, -1):
        if rowLine[columnIndex] in {"├", "│"}:
            return resultOk_build(columnIndex)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.route.realize.chip_internal.missing_east_wall",
        message="Chip-internal route realization could not find the east wall",
    )
    return resultErr_build()


def _transverseChipInternalRoutePointsResult_build(
    sourcePoint: RoutingZoneRoutePoint,
    destinationPoint: RoutingZoneRoutePoint,
    chipCanvasPlacement: _ChipCanvasPlacement,
) -> Result[tuple[RoutingZoneRoutePoint, ...]]:
    """Build an interior manifold path between opposite chip walls."""

    if sourcePoint.verticalIndex == destinationPoint.verticalIndex:
        return resultOk_build((sourcePoint, destinationPoint))

    interiorMidColumn: int = (
        sourcePoint.horizontalIndex + destinationPoint.horizontalIndex
    ) // 2
    interiorLeftBound: int = min(
        sourcePoint.horizontalIndex,
        destinationPoint.horizontalIndex,
    )
    interiorRightBound: int = max(
        sourcePoint.horizontalIndex,
        destinationPoint.horizontalIndex,
    )
    manifoldColumn: int = max(
        interiorLeftBound + 1,
        min(interiorMidColumn, interiorRightBound - 1),
    )
    return resultOk_build(
        (
            sourcePoint,
            RoutingZoneRoutePoint(
                horizontalIndex=manifoldColumn,
                verticalIndex=sourcePoint.verticalIndex,
            ),
            RoutingZoneRoutePoint(
                horizontalIndex=manifoldColumn,
                verticalIndex=destinationPoint.verticalIndex,
            ),
            destinationPoint,
        )
    )


def _sameSideChipInternalRoutePointsResult_build(
    sourcePoint: RoutingZoneRoutePoint,
    destinationPoint: RoutingZoneRoutePoint,
    sourceTerminal: ChipTerminal,
    chipCanvasPlacement: _ChipCanvasPlacement,
) -> Result[tuple[RoutingZoneRoutePoint, ...]]:
    """Build a same-side interior local-continuity path."""

    bodyRows: tuple[int, ...] = tuple(
        chipCanvasPlacement.worldRow + entry.lineOffset
        for entry in chipCanvasPlacement.chipLocalGeometry.terminalLineOffsets
    )
    bodyTopRow: int = min(bodyRows, default=sourcePoint.verticalIndex)
    bodyBottomRow: int = max(bodyRows, default=sourcePoint.verticalIndex)

    if sourceTerminal.terminalSide is ChipTerminalSide.WEST:
        detourColumn: int = sourcePoint.horizontalIndex + 1
    elif sourceTerminal.terminalSide is ChipTerminalSide.EAST:
        detourColumn = sourcePoint.horizontalIndex - 1
    else:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.route.realize.chip_internal.unsupported_same_side_terminal",
            message=(
                "Same-side chip-internal route realization currently supports "
                "west/east terminals only"
            ),
            context=(
                chipCanvasPlacement.chipRef.chipId.moduleName,
                chipCanvasPlacement.chipRef.chipId.functionName,
                sourceTerminal.terminalSide.value,
            ),
        )
        return resultErr_build()

    if sourcePoint.verticalIndex != destinationPoint.verticalIndex:
        return resultOk_build(
            (
                sourcePoint,
                RoutingZoneRoutePoint(
                    horizontalIndex=detourColumn,
                    verticalIndex=sourcePoint.verticalIndex,
                ),
                RoutingZoneRoutePoint(
                    horizontalIndex=detourColumn,
                    verticalIndex=destinationPoint.verticalIndex,
                ),
                destinationPoint,
            )
        )

    loopRow: int = sourcePoint.verticalIndex
    if sourcePoint.verticalIndex < bodyBottomRow:
        loopRow = sourcePoint.verticalIndex + 1
    elif sourcePoint.verticalIndex > bodyTopRow:
        loopRow = sourcePoint.verticalIndex - 1

    if loopRow == sourcePoint.verticalIndex:
        return resultOk_build(
            (
                sourcePoint,
                RoutingZoneRoutePoint(
                    horizontalIndex=detourColumn,
                    verticalIndex=sourcePoint.verticalIndex,
                ),
                destinationPoint,
            )
        )

    return resultOk_build(
        (
            sourcePoint,
            RoutingZoneRoutePoint(
                horizontalIndex=detourColumn,
                verticalIndex=sourcePoint.verticalIndex,
            ),
            RoutingZoneRoutePoint(
                horizontalIndex=detourColumn,
                verticalIndex=loopRow,
            ),
            RoutingZoneRoutePoint(
                horizontalIndex=sourcePoint.horizontalIndex,
                verticalIndex=loopRow,
            ),
            destinationPoint,
        )
    )
