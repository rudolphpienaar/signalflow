"""Shared directional-orientation vocabulary for routing substrates."""

from __future__ import annotations

from enum import Enum

from signalflow.models.cardinal_side import CardinalSide
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import Result, resultErr_build, resultOk_build


class DirectionalOrientation(Enum):
    """Ordered directional orientation between two opposing sides."""

    WEST_TO_EAST = "WE"
    EAST_TO_WEST = "EW"
    NORTH_TO_SOUTH = "NS"
    SOUTH_TO_NORTH = "SN"


def sourceSideForDirectionalOrientation_get(
    directionalOrientation: DirectionalOrientation,
) -> CardinalSide:
    """Return the source-side implied by one directional orientation."""

    if directionalOrientation is DirectionalOrientation.WEST_TO_EAST:
        return CardinalSide.WEST
    if directionalOrientation is DirectionalOrientation.EAST_TO_WEST:
        return CardinalSide.EAST
    if directionalOrientation is DirectionalOrientation.NORTH_TO_SOUTH:
        return CardinalSide.NORTH
    return CardinalSide.SOUTH


def destinationSideForDirectionalOrientation_get(
    directionalOrientation: DirectionalOrientation,
) -> CardinalSide:
    """Return the destination-side implied by one directional orientation."""

    if directionalOrientation is DirectionalOrientation.WEST_TO_EAST:
        return CardinalSide.EAST
    if directionalOrientation is DirectionalOrientation.EAST_TO_WEST:
        return CardinalSide.WEST
    if directionalOrientation is DirectionalOrientation.NORTH_TO_SOUTH:
        return CardinalSide.SOUTH
    return CardinalSide.NORTH


def directionalOrientationResult_buildFromSides(
    sourceSide: CardinalSide,
    destinationSide: CardinalSide,
) -> Result[DirectionalOrientation | None]:
    """Infer a directional orientation from resolved endpoint sides."""

    if sourceSide is destinationSide:
        return resultOk_build(None)
    if (
        sourceSide is CardinalSide.WEST
        and destinationSide is CardinalSide.EAST
    ):
        return resultOk_build(DirectionalOrientation.WEST_TO_EAST)
    if (
        sourceSide is CardinalSide.EAST
        and destinationSide is CardinalSide.WEST
    ):
        return resultOk_build(DirectionalOrientation.EAST_TO_WEST)
    if (
        sourceSide is CardinalSide.NORTH
        and destinationSide is CardinalSide.SOUTH
    ):
        return resultOk_build(DirectionalOrientation.NORTH_TO_SOUTH)
    if (
        sourceSide is CardinalSide.SOUTH
        and destinationSide is CardinalSide.NORTH
    ):
        return resultOk_build(DirectionalOrientation.SOUTH_TO_NORTH)

    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.orientation.unsupported_side_pair",
        message=(
            "Directional orientation currently supports same-side local and "
            "opposite-side transverse pairs only"
        ),
        context=(sourceSide.value, destinationSide.value),
    )
    return resultErr_build()
