"""Named symbolic overlap-expression banks for adjacent zones.

This module turns the tuple expression surface into explicit doctrine. The
returned expressions are symbolic top-layer tuples; they do not execute
geometry changes by themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.geometry.symbolic import (
    GeometryExpr,
    ZoneOperand,
    zoneOperandsResult_build,
)


@dataclass(frozen=True)
class ZoneOverlapExprBank:
    """Named symbolic overlap rules for one adjacent west/east zone pair.

    These banks are doctrine objects: they define which symbolic expressions
    should be evaluated to harmonize adjacent zones under the overlap model.
    """

    westZone: ZoneOperand
    eastZone: ZoneOperand
    terminalHarmonize: tuple[GeometryExpr, ...]
    extraPadding: tuple[GeometryExpr, ...] = ()
    intraClearance: tuple[GeometryExpr, ...] = ()

    def all_get(self) -> tuple[GeometryExpr, ...]:
        """Return the flattened symbolic rule set in evaluation order."""

        return (
            self.terminalHarmonize
            + self.extraPadding
            + self.intraClearance
        )


def eastWestZoneOverlapExprBank_build(
    westZone: ZoneOperand,
    eastZone: ZoneOperand,
) -> ZoneOverlapExprBank:
    """Build the initial symbolic overlap bank for one west/east pair.

    Current first-cut doctrine:
    - the shared terminal territory is harmonized by maximum extent
    """

    return ZoneOverlapExprBank(
        westZone=westZone,
        eastZone=eastZone,
        terminalHarmonize=(
            (westZone.Et, "=max", eastZone.Wt),
        ),
    )


__all__ = [
    "ZoneOverlapExprBank",
    "eastWestZoneOverlapExprBank_build",
    "zoneOperandsResult_build",
]
