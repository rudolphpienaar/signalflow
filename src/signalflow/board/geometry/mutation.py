"""Board-side mutation and constraint models for overlap-driven geometry.

This module binds the symbolic notation-layer geometry expressions to the
board's typed region vocabulary. It does not yet implement world propagation;
it provides the authoritative local mutation/constraint objects that a future
resolver will consume.
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.geometry.expr import (
    ZoneConnectivityKind,
    ZoneGeometryTarget,
    ZoneMutationExpr,
    ZoneMutationKind,
    ZoneRelationExpr,
    ZoneRelationKind,
)
from signalflow.board.types import BoardRegionId, BoardSide, RegionFamily
from signalflow.notation.sfn import sfN


@dataclass(frozen=True)
class ZoneGeometrySelector:
    """Typed board-side selector for one geometry family inside one zone."""

    zoneRef: str
    regionId: BoardRegionId


@dataclass(frozen=True)
class ZoneGeometryMutation:
    """Board-executable local geometry mutation."""

    selector: ZoneGeometrySelector
    kind: ZoneMutationKind
    magnitude: int
    orthogonalMagnitude: int = 0


@dataclass(frozen=True)
class ZoneAdjacencyConstraint:
    """Board-executable adjacency relation between two zone targets."""

    lhs: ZoneGeometrySelector
    rhs: ZoneGeometrySelector
    kind: ZoneRelationKind
    connectivityKind: ZoneConnectivityKind
    magnitude: int | None = None


def zoneGeometrySelector_buildFromTarget(
    target: ZoneGeometryTarget,
) -> ZoneGeometrySelector:
    """Convert one symbolic target into a board-side region selector."""

    return ZoneGeometrySelector(
        zoneRef=target.zoneRef,
        regionId=boardRegionId_buildFromNotation(target.region),
    )


def zoneGeometryMutation_buildFromExpr(
    expr: ZoneMutationExpr,
) -> ZoneGeometryMutation:
    """Bind one symbolic mutation expression to a board mutation object."""

    return ZoneGeometryMutation(
        selector=zoneGeometrySelector_buildFromTarget(expr.target),
        kind=expr.kind,
        magnitude=expr.magnitude,
        orthogonalMagnitude=expr.orthogonalMagnitude,
    )


def zoneAdjacencyConstraint_buildFromExpr(
    expr: ZoneRelationExpr,
) -> ZoneAdjacencyConstraint:
    """Bind one symbolic relation expression to a board constraint object."""

    return ZoneAdjacencyConstraint(
        lhs=zoneGeometrySelector_buildFromTarget(expr.lhs),
        rhs=zoneGeometrySelector_buildFromTarget(expr.rhs),
        kind=expr.kind,
        connectivityKind=expr.connectivityKind,
        magnitude=expr.magnitude,
    )


def boardRegionId_buildFromNotation(region: sfN) -> BoardRegionId:
    """Map one symbolic region token into the board's typed region id.

    This intentionally supports only the stable region families needed for the
    first overlap-mutation phase. More exotic corner/transfer tokens can be
    added once the mutation language expands beyond face-to-face harmonization.
    """

    familyByNotation: dict[sfN, RegionFamily] = {
        sfN.Wt: RegionFamily.CHIP_TERMINAL,
        sfN.Et: RegionFamily.CHIP_TERMINAL,
        sfN.Nt: RegionFamily.CHIP_TERMINAL,
        sfN.St: RegionFamily.CHIP_TERMINAL,
        sfN.Wfi: RegionFamily.INTRA_FAN,
        sfN.Efi: RegionFamily.INTRA_FAN,
        sfN.Nfi: RegionFamily.INTRA_FAN,
        sfN.Sfi: RegionFamily.INTRA_FAN,
        sfN.Wfe: RegionFamily.EXTRA_FAN,
        sfN.Efe: RegionFamily.EXTRA_FAN,
        sfN.Nfe: RegionFamily.EXTRA_FAN,
        sfN.Sfe: RegionFamily.EXTRA_FAN,
        sfN.Wi: RegionFamily.INTRA_LONGITUDE,
        sfN.Ei: RegionFamily.INTRA_LONGITUDE,
        sfN.Ni: RegionFamily.INTRA_LATITUDE,
        sfN.Si: RegionFamily.INTRA_LATITUDE,
        sfN.We: RegionFamily.EXTRA_LONGITUDE,
        sfN.Ee: RegionFamily.EXTRA_LONGITUDE,
        sfN.Ne: RegionFamily.EXTRA_LATITUDE,
        sfN.Se: RegionFamily.EXTRA_LATITUDE,
    }
    sideByNotation: dict[sfN, BoardSide] = {
        sfN.Wt: BoardSide.WEST,
        sfN.Et: BoardSide.EAST,
        sfN.Nt: BoardSide.NORTH,
        sfN.St: BoardSide.SOUTH,
        sfN.Wfi: BoardSide.WEST,
        sfN.Efi: BoardSide.EAST,
        sfN.Nfi: BoardSide.NORTH,
        sfN.Sfi: BoardSide.SOUTH,
        sfN.Wfe: BoardSide.WEST,
        sfN.Efe: BoardSide.EAST,
        sfN.Nfe: BoardSide.NORTH,
        sfN.Sfe: BoardSide.SOUTH,
        sfN.Wi: BoardSide.WEST,
        sfN.Ei: BoardSide.EAST,
        sfN.Ni: BoardSide.NORTH,
        sfN.Si: BoardSide.SOUTH,
        sfN.We: BoardSide.WEST,
        sfN.Ee: BoardSide.EAST,
        sfN.Ne: BoardSide.NORTH,
        sfN.Se: BoardSide.SOUTH,
    }

    family = familyByNotation.get(region)
    side = sideByNotation.get(region)
    if family is None or side is None:
        raise ValueError(
            "Unsupported geometry-notation target for board mutation: "
            f"{region.name}"
        )
    return BoardRegionId(family=family, side=side)


__all__ = [
    "ZoneAdjacencyConstraint",
    "ZoneGeometryMutation",
    "ZoneGeometrySelector",
    "boardRegionId_buildFromNotation",
    "zoneAdjacencyConstraint_buildFromExpr",
    "zoneGeometryMutation_buildFromExpr",
    "zoneGeometrySelector_buildFromTarget",
]
