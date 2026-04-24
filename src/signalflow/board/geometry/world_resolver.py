"""World-scale geometry resolver.

Implements the two-pass algorithm from docs/zoneInterconnect_geometry.adoc
§Prefix-Sum Case:

  Pass 1 — budgets_collect: compute per-seam horizontal and vertical budgets
  H(A,B) and V(A,B) from fixed zone extra-ring and chip-terminal spans.

  Pass 2 — displacements_apply: accumulate prefix-sum displacements from the
  NW anchor outward and apply a Z-translate to each zone geometry.

  propagate_run composes both passes into one call.

The NW anchor zone (default GridCoord(1,1)) receives zero displacement.
All eastern and southern zones receive Δx ≥ 0, Δy ≥ 0 (monotone propagation).

Budget formulas (horizontal seam A→B):
  H(A,B) = X^E_A + X^W_B + ΔT(A,B)
  where:
    X^E_A = sfN.Ee horizontal span in A
    X^W_B = sfN.We horizontal span in B
    ΔT(A,B) = max(0, T^W_B - T^E_A)  — terminal-face harmonization delta

Budget formulas (vertical seam A→B):
  V(A,B) = Y^S_A + Y^N_B + ΔT_v(A,B)
  where:
    Y^S_A = sfN.Se vertical span in A
    Y^N_B = sfN.Ne vertical span in B
    ΔT_v(A,B) = max(0, T^N_B - T^S_A)  — north/south terminal harmonization

Zones are visited in post-order (reverse column/row) for budget collection,
which is correct for future demand-driven geometry.  For the current a-priori
case (fixed spans), order is immaterial.
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.geometry.georules import GeoOp, rules_apply
from signalflow.board.geometry.mutation import boardRegionIdResult_fromSfN
from signalflow.board.geometry.world_state import WorldGeometryState
from signalflow.board.geometry.zones import BoardGeometry, GeometryZone
from signalflow.board.types import BoardRegionId
from signalflow.models.result import Result, result_isOkCheck
from signalflow.models.routing_zone import GridCoord
from signalflow.notation.sfn import sfN


@dataclass(frozen=True)
class SeamBudgets:
    """Per-seam displacement budgets for the two world axes.

    Attributes:
        horizontal: H(A,B) for each east-facing adjacent pair (A→B).
        vertical:   V(A,B) for each south-facing adjacent pair (A→B).
    """

    horizontal: dict[tuple[GridCoord, GridCoord], int]
    vertical: dict[tuple[GridCoord, GridCoord], int]


def _span_get(geometry: BoardGeometry, anchor: sfN, horizontal: bool) -> int:
    """Return horizontal or vertical span of one sfN region, 0 if absent."""
    ridResult: Result[BoardRegionId] = boardRegionIdResult_fromSfN(anchor)
    if result_isOkCheck(ridResult):
        rid: BoardRegionId = ridResult.value
        zone: GeometryZone | None = geometry.geometryZonesById.get(rid)
        if zone is not None:
            return (
                zone.frame.horizontalSpan
                if horizontal
                else zone.frame.verticalSpan
            )
    return 0


def _horizontalBudget_calculate(
    aGeometry: BoardGeometry,
    bGeometry: BoardGeometry,
) -> int:
    """H(A,B) = X^E_A + X^W_B + ΔT(A,B).

    Extra-ring clearance plus terminal-face harmonization delta.
    ΔT is zero when terminal extents are already harmonized.
    """
    xEastA: int = _span_get(aGeometry, sfN.Ee, horizontal=True)
    xWestB: int = _span_get(bGeometry, sfN.We, horizontal=True)
    tEastA: int = _span_get(aGeometry, sfN.Et, horizontal=True)
    tWestB: int = _span_get(bGeometry, sfN.Wt, horizontal=True)
    deltaT: int = max(0, tWestB - tEastA)
    return xEastA + xWestB + deltaT


def _verticalBudget_calculate(
    aGeometry: BoardGeometry,
    bGeometry: BoardGeometry,
) -> int:
    """V(A,B) = Y^S_A + Y^N_B + ΔT_v(A,B).

    South/north extra-ring clearance plus vertical terminal harmonization.
    """
    ySouthA: int = _span_get(aGeometry, sfN.Se, horizontal=False)
    yNorthB: int = _span_get(bGeometry, sfN.Ne, horizontal=False)
    tSouthA: int = _span_get(aGeometry, sfN.St, horizontal=False)
    tNorthB: int = _span_get(bGeometry, sfN.Nt, horizontal=False)
    deltaT: int = max(0, tNorthB - tSouthA)
    return ySouthA + yNorthB + deltaT


class WorldGeometryResolver:
    """Two-pass world assembly resolver.

    Pass 1 — budgets_collect: per-seam clearance budgets.
    Pass 2 — displacements_apply: prefix-sum Z-translate per zone.

    Both passes are pure functions over WorldGeometryState.
    The resolver holds no mutable state.
    """

    @staticmethod
    def budgets_collect(state: WorldGeometryState) -> SeamBudgets:
        """Compute H(A,B) and V(A,B) for all adjacent zone pairs.

        Visits zones in post-order (decreasing column, decreasing row) so
        that leaf zones are processed before their anchoring neighbors.

        Args:
            state: Current world geometry snapshot.

        Returns:
            SeamBudgets with horizontal and vertical budget dicts.
        """
        horizontal: dict[tuple[GridCoord, GridCoord], int] = {}
        vertical: dict[tuple[GridCoord, GridCoord], int] = {}

        coords: list[GridCoord] = sorted(
            state.coords_get(),
            key=lambda c: (-c.columnIndex, -c.rowIndex),
        )
        coord: GridCoord
        for coord in coords:
            aGeometry: BoardGeometry | None = state.zone_get(coord)
            if aGeometry is None:
                continue

            eastCoord: GridCoord | None = state.eastNeighbor_get(coord)
            if eastCoord is not None:
                bGeometry: BoardGeometry | None = state.zone_get(eastCoord)
                if bGeometry is not None:
                    horizontal[(coord, eastCoord)] = (
                        _horizontalBudget_calculate(aGeometry, bGeometry)
                    )

            southCoord: GridCoord | None = state.southNeighbor_get(coord)
            if southCoord is not None:
                bGeometry = state.zone_get(southCoord)
                if bGeometry is not None:
                    vertical[(coord, southCoord)] = (
                        _verticalBudget_calculate(aGeometry, bGeometry)
                    )

        return SeamBudgets(horizontal=horizontal, vertical=vertical)

    @staticmethod
    def displacements_apply(
        state: WorldGeometryState,
        budgets: SeamBudgets,
    ) -> WorldGeometryState:
        """Apply prefix-sum displacements to every non-anchor zone.

        For zone at GridCoord(col, row):
          Δx(col, row) = Σ H((i,row)→(i+1,row)) for i = anchorCol .. col-1
          Δy(col, row) = Σ V((col,j)→(col,j+1)) for j = anchorRow .. row-1

        Displacement is applied via a Z-sentinel translate (all zones in the
        geometry shift by (Δx, Δy)).  Anchor zone is left unchanged.

        Args:
            state: World geometry snapshot with local zone geometries.
            budgets: Seam budgets from budgets_collect.

        Returns:
            New WorldGeometryState with all zones at world coordinates.
        """
        anchor: GridCoord = state.anchorCoord
        coords: list[GridCoord] = sorted(
            state.coords_get(),
            key=lambda c: (c.columnIndex, c.rowIndex),
        )
        updatedState: WorldGeometryState = state
        coord: GridCoord
        for coord in coords:
            if coord == anchor:
                continue

            dx: int = 0
            col: int = anchor.columnIndex
            while col < coord.columnIndex:
                westCoord: GridCoord = GridCoord(
                    columnIndex=col, rowIndex=coord.rowIndex
                )
                eastCoord: GridCoord = GridCoord(
                    columnIndex=col + 1, rowIndex=coord.rowIndex
                )
                dx += budgets.horizontal.get((westCoord, eastCoord), 0)
                col += 1

            dy: int = 0
            row: int = anchor.rowIndex
            while row < coord.rowIndex:
                northCoord: GridCoord = GridCoord(
                    columnIndex=coord.columnIndex, rowIndex=row
                )
                southCoord: GridCoord = GridCoord(
                    columnIndex=coord.columnIndex, rowIndex=row + 1
                )
                dy += budgets.vertical.get((northCoord, southCoord), 0)
                row += 1

            if dx == 0 and dy == 0:
                continue

            geometry: BoardGeometry | None = updatedState.zone_get(coord)
            if geometry is None:
                continue
            displaced: BoardGeometry = rules_apply(
                sfN.Z, GeoOp.DISPLACE, dx, dy, geometry
            )
            updatedState = updatedState.withZoneGeometry_build(
                coord, displaced
            )

        return updatedState

    @staticmethod
    def propagate_run(state: WorldGeometryState) -> WorldGeometryState:
        """Collect budgets then apply prefix-sum displacements.

        Single entry point for full world assembly.  Returns a new
        WorldGeometryState where every zone geometry is at its correct
        world-coordinate position.

        Args:
            state: World snapshot with per-zone local geometries.

        Returns:
            Assembled world state; anchor zone is unchanged, all others
            carry (Δx, Δy) ≥ 0 world offsets.
        """
        budgets: SeamBudgets = WorldGeometryResolver.budgets_collect(state)
        return WorldGeometryResolver.displacements_apply(state, budgets)


__all__ = [
    "SeamBudgets",
    "WorldGeometryResolver",
]
