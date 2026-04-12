"""Symbolic geometry expression IR for overlap-driven zone mutation.

This module defines the typed symbolic language for geometric reasoning at the
notation layer. It does not mutate board geometry directly. Instead it
describes geometry targets, local mutation intent, and adjacency relations in a
form that the board package can evaluate against authoritative zone geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from signalflow.notation.sfn import sfN


class GeometryAxis(StrEnum):
    """Major geometry axis implied by a symbolic region."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class ZoneFace(StrEnum):
    """Neighbor-facing side for overlap and adjacency relations."""

    WEST = "west"
    EAST = "east"
    NORTH = "north"
    SOUTH = "south"


class ZoneConnectivityKind(StrEnum):
    """How one zone-face relation propagates into its neighbor."""

    FIXED_OVERLAP = "fixed_overlap"
    MIN_CLEARANCE = "min_clearance"
    FREE_SEPARATION = "free_separation"
    DISCONNECTED = "disconnected"


class ZoneRelationKind(StrEnum):
    """Symbolic relation kind between two geometry targets."""

    EXTENT_MAX_ALIGN = "extent_max_align"
    MIN_CLEARANCE = "min_clearance"
    FIXED_OVERLAP = "fixed_overlap"


class ZoneMutationKind(StrEnum):
    """Local zone mutation intent."""

    EXTENT_SET = "extent_set"
    PADDING_ADD = "padding_add"
    SHIFT_APPLY = "shift_apply"


@dataclass(frozen=True)
class ZoneGeometryTarget:
    """One symbolic zone-local geometry target.

    `zoneRef` is intentionally a lightweight symbolic label rather than a live
    model object. This keeps the notation layer purely symbolic and allows
    board/world layers to bind expressions to real zone identities later.
    """

    zoneRef: str
    region: sfN

    def axis_get(self) -> GeometryAxis | None:
        return self.region.axis_get()

    def face_get(self) -> ZoneFace | None:
        return self.region.face_get()


@dataclass(frozen=True)
class ZoneRelationExpr:
    """One symbolic relation between two zone-local geometry targets."""

    lhs: ZoneGeometryTarget
    rhs: ZoneGeometryTarget
    kind: ZoneRelationKind
    connectivityKind: ZoneConnectivityKind
    magnitude: int | None = None


@dataclass(frozen=True)
class ZoneMutationExpr:
    """One symbolic local mutation request."""

    target: ZoneGeometryTarget
    kind: ZoneMutationKind
    magnitude: int
    orthogonalMagnitude: int = 0


def zoneExtentMaxAlignRelation_build(
    *,
    lhs: ZoneGeometryTarget,
    rhs: ZoneGeometryTarget,
    connectivityKind: ZoneConnectivityKind = (
        ZoneConnectivityKind.FIXED_OVERLAP
    ),
) -> ZoneRelationExpr:
    """Build a max-extent alignment relation."""

    return ZoneRelationExpr(
        lhs=lhs,
        rhs=rhs,
        kind=ZoneRelationKind.EXTENT_MAX_ALIGN,
        connectivityKind=connectivityKind,
    )


def zoneMinClearanceRelation_build(
    *,
    lhs: ZoneGeometryTarget,
    rhs: ZoneGeometryTarget,
    minimum: int,
    connectivityKind: ZoneConnectivityKind = (
        ZoneConnectivityKind.MIN_CLEARANCE
    ),
) -> ZoneRelationExpr:
    """Build a minimum-clearance relation."""

    return ZoneRelationExpr(
        lhs=lhs,
        rhs=rhs,
        kind=ZoneRelationKind.MIN_CLEARANCE,
        connectivityKind=connectivityKind,
        magnitude=minimum,
    )


def zoneExtentSetMutation_build(
    *,
    target: ZoneGeometryTarget,
    extent: int,
) -> ZoneMutationExpr:
    """Build a local extent-set mutation."""

    return ZoneMutationExpr(
        target=target,
        kind=ZoneMutationKind.EXTENT_SET,
        magnitude=extent,
    )


def zonePaddingAddMutation_build(
    *,
    target: ZoneGeometryTarget,
    padding: int,
) -> ZoneMutationExpr:
    """Build a local padding-add mutation."""

    return ZoneMutationExpr(
        target=target,
        kind=ZoneMutationKind.PADDING_ADD,
        magnitude=padding,
    )


def zoneShiftApplyMutation_build(
    *,
    target: ZoneGeometryTarget,
    deltaPrimary: int,
    deltaOrthogonal: int = 0,
) -> ZoneMutationExpr:
    """Build a local shift-apply mutation."""

    return ZoneMutationExpr(
        target=target,
        kind=ZoneMutationKind.SHIFT_APPLY,
        magnitude=deltaPrimary,
        orthogonalMagnitude=deltaOrthogonal,
    )


__all__ = [
    "GeometryAxis",
    "ZoneConnectivityKind",
    "ZoneFace",
    "ZoneGeometryTarget",
    "ZoneMutationExpr",
    "ZoneMutationKind",
    "ZoneRelationExpr",
    "ZoneRelationKind",
    "zoneExtentMaxAlignRelation_build",
    "zoneMinClearanceRelation_build",
    "zoneExtentSetMutation_build",
    "zonePaddingAddMutation_build",
    "zoneShiftApplyMutation_build",
]
