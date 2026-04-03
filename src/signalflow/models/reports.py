from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signalflow.models.routing_zone_grid import GridCoord


@dataclass(frozen=True)
class CollisionReportCounts:
    boundary: int
    symbolic_channel: int
    symbolic_fan: int
    rendered_board_cell: int
    rendered_fan: int


@dataclass(frozen=True)
class CollisionReportSymbolicEntry:
    token: str
    wires: tuple[str, ...]


@dataclass(frozen=True)
class CollisionReportRenderedEntry:
    cell: tuple[int, int]
    regions: tuple[str, ...]
    wires: tuple[str, ...]


@dataclass(frozen=True)
class CollisionReportBoundaryEntry:
    wire: str
    boundary: str
    kind: str
    cells: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class CollisionReportClaims:
    symbolic_channel: dict[str, tuple[str, ...]]
    symbolic_fan: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class CollisionReportCollisions:
    boundary: list[CollisionReportBoundaryEntry]
    symbolic_channel: list[CollisionReportSymbolicEntry]
    symbolic_fan: list[CollisionReportSymbolicEntry]
    rendered_board_cell: list[CollisionReportRenderedEntry]
    rendered_fan: list[CollisionReportRenderedEntry]


@dataclass(frozen=True)
class CollisionReport:
    hasCollisions: bool
    counts: CollisionReportCounts
    claims: CollisionReportClaims
    collisions: CollisionReportCollisions


@dataclass(frozen=True)
class LocationRecord:
    zone: GridCoord
    terminalSide: str
    orderIndex: int
    worldPoint: tuple[int, int] | None
