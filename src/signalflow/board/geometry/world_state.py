"""World-scale geometry state for multi-zone assembly.

Holds an immutable snapshot of per-zone BoardGeometry objects keyed by
GridCoord, plus adjacency helpers for the NW-anchored zone grid.
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.geometry.zones import BoardGeometry
from signalflow.models.routing_zone import GridCoord


@dataclass(frozen=True)
class WorldGeometryState:
    """Immutable multi-zone geometry snapshot for world assembly.

    Attributes:
        zoneGeometryByCoord: Per-zone BoardGeometry keyed by GridCoord.
        anchorCoord: Fixed NW anchor; this zone receives zero displacement.
    """

    zoneGeometryByCoord: dict[GridCoord, BoardGeometry]
    anchorCoord: GridCoord

    def zone_get(self, coord: GridCoord) -> BoardGeometry | None:
        """Return the BoardGeometry for the given coord, or None."""
        return self.zoneGeometryByCoord.get(coord)

    def coords_get(self) -> frozenset[GridCoord]:
        """Return all zone coordinates present in the world."""
        return frozenset(self.zoneGeometryByCoord)

    def eastNeighbor_get(self, coord: GridCoord) -> GridCoord | None:
        """Return the GridCoord one column east, or None if absent."""
        candidate: GridCoord = GridCoord(
            columnIndex=coord.columnIndex + 1,
            rowIndex=coord.rowIndex,
        )
        return candidate if candidate in self.zoneGeometryByCoord else None

    def southNeighbor_get(self, coord: GridCoord) -> GridCoord | None:
        """Return the GridCoord one row south, or None if absent."""
        candidate: GridCoord = GridCoord(
            columnIndex=coord.columnIndex,
            rowIndex=coord.rowIndex + 1,
        )
        return candidate if candidate in self.zoneGeometryByCoord else None

    def withZoneGeometry_build(
        self,
        coord: GridCoord,
        geometry: BoardGeometry,
    ) -> WorldGeometryState:
        """Return a new state with one zone geometry replaced."""
        updated: dict[GridCoord, BoardGeometry] = {
            **self.zoneGeometryByCoord,
            coord: geometry,
        }
        return WorldGeometryState(
            zoneGeometryByCoord=updated,
            anchorCoord=self.anchorCoord,
        )


__all__ = [
    "WorldGeometryState",
]
