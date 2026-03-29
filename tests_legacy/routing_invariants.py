"""Reusable routing invariant helpers for the new engine tests."""
from __future__ import annotations

from signalflow.models import result_isOkCheck
from signalflow.routing import routePoints_realize
from signalflow.routing.track import TrackDirection


def _dirs_are_horizontal(directions: frozenset[TrackDirection]) -> bool:
    return directions <= {TrackDirection.EAST, TrackDirection.WEST}


def _dirs_are_vertical(directions: frozenset[TrackDirection]) -> bool:
    return directions <= {TrackDirection.NORTH, TrackDirection.SOUTH}


def assert_solved_routes_have_no_shared_realized_cells(
    routes,
    *,
    allow_orthogonal_crossings: bool = False,
) -> None:
    """Assert distinct solved routes do not share realized cells.

    When ``allow_orthogonal_crossings`` is true, a horizontal/vertical crossing
    on the same cell is allowed. The default is strict non-coincidence.
    """

    occupied_directions_by_cell: dict[tuple[int, int], frozenset[TrackDirection]] = {}

    for route in routes:
        realized_route_result = routePoints_realize(
            sourceChipRef=route.sourceChipRef,
            destinationChipRef=route.destinationChipRef,
            childCallIndex=route.childCallIndex,
            routePoints=route.routePoints,
        )
        assert result_isOkCheck(realized_route_result)

        for cell in realized_route_result.value.cells:
            key = (cell.worldRow, cell.worldCol)
            directions = cell.trackCell.directions
            if key not in occupied_directions_by_cell:
                occupied_directions_by_cell[key] = directions
                continue

            existing_directions = occupied_directions_by_cell[key]
            crossing_is_legal = (
                (
                    _dirs_are_horizontal(existing_directions)
                    and _dirs_are_vertical(directions)
                )
                or (
                    _dirs_are_vertical(existing_directions)
                    and _dirs_are_horizontal(directions)
                )
            )
            assert allow_orthogonal_crossings and crossing_is_legal, (
                f"shared realized route cell at {key}: "
                f"{sorted(d.value for d in existing_directions)} vs "
                f"{sorted(d.value for d in directions)}"
            )
            occupied_directions_by_cell[key] = existing_directions | directions
