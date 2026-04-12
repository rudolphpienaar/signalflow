"""Topmost symbolic geometry notation for overlap-driven zone mutation.

This module exposes the compact user-facing geometry expression form:

    A, B = zoneOperandsResult_build("A", "B").value
    exprs = (
        (A.Et, "=max", B.Wt),
        (B.Ee, "+=", 4),
        (A.Et, "~", B.Wt),
    )

The tuple form is intentionally lightweight. Each tuple is:

    (<region operand>, <symbolic operator>, <region operand or literal>)

The symbolic layer does not execute geometry changes. It only normalizes these
top-layer tuples into the typed expression objects in
`signalflow.board.geometry.expr`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import TypeAlias

from signalflow.board.geometry.expr import (
    ZoneConnectivityKind,
    ZoneGeometryTarget,
    ZoneMutationExpr,
    ZoneRelationExpr,
    zoneExtentMaxAlignRelation_build,
    zoneMinClearanceRelation_build,
    zonePaddingAddMutation_build,
)
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.notation.sfn import sfN


@dataclass(frozen=True)
class RegionOperand:
    """One region-scoped symbolic operand such as ``A.Et`` or ``B.Wt``."""

    zoneRef: str
    region: sfN

    def target_build(self) -> ZoneGeometryTarget:
        """Lower this symbolic operand into a normalized target."""

        return ZoneGeometryTarget(zoneRef=self.zoneRef, region=self.region)


@dataclass(frozen=True)
class ZoneOperand:
    """One zone-scoped symbolic operand root such as ``A`` or ``B``."""

    label: str

    def __getattr__(self, name: str) -> RegionOperand:
        region = sfN.__members__.get(name)
        if region is None:
            raise AttributeError(
                f"{self.__class__.__name__!s} has no symbolic region {name!r}"
            )
        return RegionOperand(zoneRef=self.label, region=region)


class GeometryOp(StrEnum):
    """Top-layer symbolic operator tokens for geometry expressions."""

    EXTENT_MAX_ALIGN = "=max"
    FIXED_OVERLAP = "~"
    PADDING_ADD = "+="
    MIN_CLEARANCE = ">="


GeometryExprRhs: TypeAlias = RegionOperand | int
GeometryExprOp: TypeAlias = str | GeometryOp
GeometryExpr: TypeAlias = tuple[RegionOperand, GeometryExprOp, GeometryExprRhs]
GeometryOpLike: TypeAlias = GeometryExprOp
GeometryRhs: TypeAlias = GeometryExprRhs


@cache
def zoneOperandResult_build(label: str) -> Result[ZoneOperand]:
    """Build one cached zone operand root from a symbolic label."""

    if not label:
        return resultErr_build()
    return resultOk_build(ZoneOperand(label=label))


def zoneOperandsResult_build(
    *labels: str,
) -> Result[tuple[ZoneOperand, ...]]:
    """Build a tuple of cached zone operand roots."""

    operands: list[ZoneOperand] = []
    for label in labels:
        operandResult = zoneOperandResult_build(label)
        if not result_isOkCheck(operandResult):
            return resultErr_build()
        operands.append(operandResult.value)
    return resultOk_build(tuple(operands))


def zoneOpResult_build(symbol: str) -> Result[GeometryOp]:
    """Build one symbolic geometry operator from its display token."""

    try:
        return resultOk_build(GeometryOp(symbol))
    except ValueError:
        return resultErr_build()


def geometryExprLoweredResult_build(
    expr: GeometryExpr,
) -> Result[ZoneRelationExpr | ZoneMutationExpr]:
    """Compile one top-layer symbolic tuple into normalized geometry IR."""

    lhs, op, rhs = expr
    opValue = op.value if isinstance(op, GeometryOp) else op

    if opValue == "=max":
        if not isinstance(rhs, RegionOperand):
            return resultErr_build()
        return resultOk_build(
            zoneExtentMaxAlignRelation_build(
                lhs=lhs.target_build(),
                rhs=rhs.target_build(),
                connectivityKind=ZoneConnectivityKind.FIXED_OVERLAP,
            )
        )

    if opValue == "~":
        if not isinstance(rhs, RegionOperand):
            return resultErr_build()
        return resultOk_build(
            zoneExtentMaxAlignRelation_build(
                lhs=lhs.target_build(),
                rhs=rhs.target_build(),
                connectivityKind=ZoneConnectivityKind.FIXED_OVERLAP,
            )
        )

    if opValue == "+=":
        if not isinstance(rhs, int):
            return resultErr_build()
        return resultOk_build(
            zonePaddingAddMutation_build(
                target=lhs.target_build(),
                padding=rhs,
            )
        )

    if opValue == ">=":
        if not isinstance(rhs, int):
            return resultErr_build()
        return resultOk_build(
            zoneMinClearanceRelation_build(
                lhs=lhs.target_build(),
                rhs=lhs.target_build(),
                minimum=rhs,
                connectivityKind=ZoneConnectivityKind.MIN_CLEARANCE,
            )
        )

    return resultErr_build()


__all__ = [
    "GeometryExpr",
    "GeometryExprOp",
    "GeometryExprRhs",
    "GeometryOp",
    "GeometryOpLike",
    "GeometryRhs",
    "RegionOperand",
    "ZoneOperand",
    "geometryExprLoweredResult_build",
    "zoneOpResult_build",
    "zoneOperandResult_build",
    "zoneOperandsResult_build",
]
