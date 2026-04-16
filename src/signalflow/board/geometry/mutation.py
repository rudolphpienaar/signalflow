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
from signalflow.board.types import (
    BoardRegionId,
    BoardSide,
    RegionBranch,
    RegionFamily,
)
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
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


def boardRegionIdResult_fromSfN(
    token: sfN,
) -> Result[BoardRegionId]:
    """Derive a BoardRegionId from an sfN token via its region_key.

    Parses the canonical ``sfN.region_key`` string
    (``"side/family"`` or ``"side/family:branch"``) into a typed
    ``BoardRegionId``.

    This is the single truth source for the sfN → BoardRegionId mapping.
    Covers all tokens with a declared ``region_key`` — routing bands,
    terminals, fans, corners, and transfers — without hardcoded lookup tables.

    Args:
        token: Any sfN region token.

    Returns:
        ``ResultOk`` with ``BoardRegionId`` on success. ``ResultErr`` when
        the token has no ``region_key`` (e.g. ``sfN.Ci``).

    Example:
        >>> result = boardRegionIdResult_fromSfN(sfN.Ee)
        >>> result_isOkCheck(result) and result.value.family
        <RegionFamily.EXTRA_LONGITUDE: 'extra_routing_longitude'>
        >>> result = boardRegionIdResult_fromSfN(sfN.NEe)
        >>> result_isOkCheck(result) and result.value.branch
        <RegionBranch.NORTH: 'north'>
    """

    key = token.region_key
    if key is None:
        return resultErr_build()
    base, _, branchStr = key.partition(":")
    branch = RegionBranch(branchStr) if branchStr else None
    sideStr, _, familyStr = base.partition("/")
    try:
        return resultOk_build(
            BoardRegionId(
                family=RegionFamily(familyStr),
                side=BoardSide(sideStr),
                branch=branch,
            )
        )
    except ValueError:
        return resultErr_build()


def zoneSelectorResult_buildFromTarget(
    target: ZoneGeometryTarget,
) -> Result[ZoneGeometrySelector]:
    """Convert one symbolic target into a board-side region selector."""

    regionResult = boardRegionIdResult_fromSfN(target.region)
    if result_isOkCheck(regionResult):
        return resultOk_build(
            ZoneGeometrySelector(
                zoneRef=target.zoneRef,
                regionId=regionResult.value,
            )
        )
    return resultErr_build()


def zoneMutationResult_buildFromExpr(
    expr: ZoneMutationExpr,
) -> Result[ZoneGeometryMutation]:
    """Bind one symbolic mutation expression to a board mutation object."""

    selectorResult = zoneSelectorResult_buildFromTarget(expr.target)
    if result_isOkCheck(selectorResult):
        return resultOk_build(
            ZoneGeometryMutation(
                selector=selectorResult.value,
                kind=expr.kind,
                magnitude=expr.magnitude,
                orthogonalMagnitude=expr.orthogonalMagnitude,
            )
        )
    return resultErr_build()


def zoneAdjacencyConstraintResult_buildFromExpr(
    expr: ZoneRelationExpr,
) -> Result[ZoneAdjacencyConstraint]:
    """Bind one symbolic relation expression to a board constraint object."""

    lhsResult = zoneSelectorResult_buildFromTarget(expr.lhs)
    rhsResult = zoneSelectorResult_buildFromTarget(expr.rhs)
    if result_isOkCheck(lhsResult) and result_isOkCheck(rhsResult):
        return resultOk_build(
            ZoneAdjacencyConstraint(
                lhs=lhsResult.value,
                rhs=rhsResult.value,
                kind=expr.kind,
                connectivityKind=expr.connectivityKind,
                magnitude=expr.magnitude,
            )
        )
    return resultErr_build()


# ---------------------------------------------------------------------------
# Legacy names — kept for call-site compatibility during migration.
# Prefer the Result-returning variants above.
# ---------------------------------------------------------------------------

def zoneGeometrySelector_buildFromTarget(
    target: ZoneGeometryTarget,
) -> Result[ZoneGeometrySelector]:
    """Alias for ``zoneSelectorResult_buildFromTarget``."""

    return zoneSelectorResult_buildFromTarget(target)


def zoneGeometryMutation_buildFromExpr(
    expr: ZoneMutationExpr,
) -> Result[ZoneGeometryMutation]:
    """Alias for ``zoneMutationResult_buildFromExpr``."""

    return zoneMutationResult_buildFromExpr(expr)


def zoneAdjacencyConstraint_buildFromExpr(
    expr: ZoneRelationExpr,
) -> Result[ZoneAdjacencyConstraint]:
    """Alias for ``zoneAdjacencyConstraintResult_buildFromExpr``."""

    return zoneAdjacencyConstraintResult_buildFromExpr(expr)


__all__ = [
    "ZoneAdjacencyConstraint",
    "ZoneGeometryMutation",
    "ZoneGeometrySelector",
    "boardRegionIdResult_fromSfN",
    "zoneAdjacencyConstraint_buildFromExpr",
    "zoneAdjacencyConstraintResult_buildFromExpr",
    "zoneGeometryMutation_buildFromExpr",
    "zoneGeometrySelector_buildFromTarget",
    "zoneMutationResult_buildFromExpr",
    "zoneSelectorResult_buildFromTarget",
]
