"""Explicit geo-zone displacement rule bank and engine.

For each first-class anchor zone and displacement op, defines the ordered
list of (target, face, effect, factor) tuples that must be applied when
the anchor moves by a given delta.

``rules_apply`` iterates the matching rule list and applies each effect
to the supplied ``BoardGeometry``, returning a new geometry instance.

The applied delta for each rule entry is ``factor * anchorDelta``.
Factor is +1 for same-direction effects, -1 to invert (e.g. the
sfN.Z all-zones translate when the coordinate floor requires a
counter-shift before the anchor is displaced).

Notation:
    GeoOp.DISPLACE  — move anchor by delta; cascades to dependents
    GeoEffect.STRETCH  — shift one named face of target by (factor*delta)
    GeoEffect.TRANSLATE — shift entire target by (factor*delta)

Special target:
    sfN.Z — sentinel meaning "apply effect to ALL zones in geometry".
"""

from __future__ import annotations

from dataclasses import dataclass, replace as dc_replace
from enum import StrEnum
from typing import TypeAlias

from signalflow.board.geometry.mutation import boardRegionIdResult_fromSfN
from signalflow.board.geometry.zones import BoardGeometry, GeometryZone
from signalflow.board.types import BoardRegionId
from signalflow.models import RoutingZoneRegionFrame
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.notation.sfn import sfN


class TopologyFace(StrEnum):
    """Cardinal face of a symbolic region token."""

    WEST = "west"
    EAST = "east"
    NORTH = "north"
    SOUTH = "south"


class GeoOp(StrEnum):
    """Operation applied to an anchor zone."""

    DISPLACE = "+="


class GeoEffect(StrEnum):
    """Effect applied to a dependent zone."""

    STRETCH = "+~~"
    TRANSLATE = "=~~"


# ---------------------------------------------------------------------------
# Geo argument types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeoArgScalar:
    """Simple integer displacement argument."""

    value: int


@dataclass(frozen=True)
class GeoArgScaled:
    """Displacement as a fraction of a reference zone's extent.

    Not yet consumed by the engine — reserved for future use.
    """

    factor: float
    reference: sfN


GeoArg: TypeAlias = GeoArgScalar | GeoArgScaled | None


# ---------------------------------------------------------------------------
# Rule bank: {anchor: {op: [(target, face, effect, factor), ...]}}
# face is None for TRANSLATE (whole zone moves, no single face)
# factor multiplies the anchor delta to produce the applied delta
RuleEntry = list[tuple[sfN, TopologyFace | None, GeoEffect, int]]
RuleBank = dict[sfN, dict[GeoOp, RuleEntry]]

RULES: RuleBank = {
    # ---- extra ring ------------------------------------------------
    # Ee += n  =>  Ee translates +n,  Ne.east +~~ n,  Se.east +~~ n
    sfN.Ee: {
        GeoOp.DISPLACE: [
            (sfN.Ee, None,              GeoEffect.TRANSLATE, +1),
            (sfN.Ne, TopologyFace.EAST, GeoEffect.STRETCH,  +1),
            (sfN.Se, TopologyFace.EAST, GeoEffect.STRETCH,  +1),
        ],
    },
    # We -= m  =>  Z +m (floor guard), We -m, Ne.west +~~ -m, Se.west +~~ -m
    # Order is load-bearing: Z fires first so We is already at a legal
    # position before its own translate pulls it back west.
    sfN.We: {
        GeoOp.DISPLACE: [
            (sfN.Z,  None,              GeoEffect.TRANSLATE, -1),
            (sfN.We, None,              GeoEffect.TRANSLATE, +1),
            (sfN.Ne, TopologyFace.WEST, GeoEffect.STRETCH,  +1),
            (sfN.Se, TopologyFace.WEST, GeoEffect.STRETCH,  +1),
        ],
    },
}


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------


def _frameFaceStretched_build(
    frame: RoutingZoneRegionFrame,
    face: TopologyFace,
    delta: int,
) -> RoutingZoneRegionFrame:
    if face is TopologyFace.EAST:
        return dc_replace(
            frame, horizontalSpan=frame.horizontalSpan + delta
        )
    if face is TopologyFace.WEST:
        return dc_replace(
            frame,
            horizontalStart=frame.horizontalStart + delta,
            horizontalSpan=frame.horizontalSpan - delta,
        )
    if face is TopologyFace.SOUTH:
        return dc_replace(
            frame, verticalSpan=frame.verticalSpan + delta
        )
    # NORTH
    return dc_replace(
        frame,
        verticalStart=frame.verticalStart + delta,
        verticalSpan=frame.verticalSpan - delta,
    )


def _frameTranslated_build(
    frame: RoutingZoneRegionFrame,
    deltaColumns: int,
    deltaRows: int,
) -> RoutingZoneRegionFrame:
    return dc_replace(
        frame,
        horizontalStart=frame.horizontalStart + deltaColumns,
        verticalStart=frame.verticalStart + deltaRows,
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def rules_apply(
    anchor: sfN,
    op: GeoOp,
    deltaColumns: int,
    deltaRows: int,
    geometry: BoardGeometry,
) -> BoardGeometry:
    """Apply displacement rules for one anchor op to a geometry.

    Looks up ``RULES[anchor][op]``, iterates effects, and returns a new
    ``BoardGeometry`` with all dependent zone frames updated.

    Each rule entry carries a signed ``factor``; the applied delta is
    ``factor * deltaColumns`` (or ``factor * deltaRows`` for vertical
    faces).  ``sfN.Z`` as target applies the effect to every zone.

    Args:
        anchor: The sfN token being displaced.
        op: The operation kind (e.g. ``GeoOp.DISPLACE``).
        deltaColumns: Horizontal displacement in board columns.
        deltaRows: Vertical displacement in board rows.
        geometry: Current board geometry to apply rules against.

    Returns:
        New ``BoardGeometry`` with cascaded frame changes applied.
        Returns ``geometry`` unchanged when no rules match.
    """

    effects: RuleEntry = RULES.get(anchor, {}).get(op, [])
    if not effects:
        return geometry

    zonesById: dict[BoardRegionId, GeometryZone] = dict(
        geometry.geometryZonesById
    )

    target: sfN
    face: TopologyFace | None
    effect: GeoEffect
    factor: int
    for target, face, effect, factor in effects:
        appliedCols: int = factor * deltaColumns
        appliedRows: int = factor * deltaRows

        if target is sfN.Z:
            # Apply to every zone in geometry.
            rid: BoardRegionId
            for rid in list(zonesById):
                allZone: GeometryZone = zonesById[rid]
                zonesById[rid] = _zoneTranslated_build(
                    allZone, appliedCols, appliedRows
                )
            continue

        ridResult: Result[BoardRegionId] = (
            boardRegionIdResult_fromSfN(target)
        )
        if not result_isOkCheck(ridResult):
            continue
        zone: GeometryZone | None = zonesById.get(ridResult.value)
        if zone is None:
            continue

        newFrame: RoutingZoneRegionFrame
        if effect is GeoEffect.STRETCH and face is not None:
            delta: int = (
                appliedCols
                if face in (TopologyFace.EAST, TopologyFace.WEST)
                else appliedRows
            )
            newFrame = _frameFaceStretched_build(zone.frame, face, delta)
        elif effect is GeoEffect.TRANSLATE:
            newFrame = _frameTranslated_build(
                zone.frame, appliedCols, appliedRows
            )
        else:
            continue

        zonesById[ridResult.value] = GeometryZone(
            regionId=zone.regionId,
            frame=newFrame,
            routingZoneRegionId=zone.routingZoneRegionId,
            chipDrawPlacementsByChip=zone.chipDrawPlacementsByChip,
            exactTerminalWorldPositionsByChip=(
                zone.exactTerminalWorldPositionsByChip
            ),
        )

    return BoardGeometry(
        geometryZonesById=zonesById,
        effectiveBoundaryFramesByName=(
            geometry.effectiveBoundaryFramesByName
        ),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

GeoChange: TypeAlias = tuple[sfN, GeoArg, str | GeoOp]


def _anchorDeltas_resolve(
    anchor: sfN,
    delta: int,
) -> tuple[int, int]:
    """Return (deltaColumns, deltaRows) from anchor axis and delta."""
    if anchor.name[0] in ("E", "W"):
        return (delta, 0)
    if anchor.name[0] in ("N", "S"):
        return (0, delta)
    return (delta, 0)


def _zoneTranslated_build(
    zone: GeometryZone,
    deltaColumns: int,
    deltaRows: int,
) -> GeometryZone:
    """Return zone with frame translated by given deltas."""
    return GeometryZone(
        regionId=zone.regionId,
        frame=_frameTranslated_build(
            zone.frame, deltaColumns, deltaRows
        ),
        routingZoneRegionId=zone.routingZoneRegionId,
        chipDrawPlacementsByChip=zone.chipDrawPlacementsByChip,
        exactTerminalWorldPositionsByChip=(
            zone.exactTerminalWorldPositionsByChip
        ),
    )


def geometry_change(
    changes: list[GeoChange],
    geometry: BoardGeometry,
) -> Result[BoardGeometry]:
    """Apply one or more geo-zone displacements to a geometry.

    For each ``(anchor, arg, op)`` change the RULES bank is the complete
    description of what happens — including the anchor zone's own
    movement.  No implicit anchor-translate is applied outside the rules.

    Returns ``Err`` when any change names an anchor with no rules or
    carries an unsupported ``GeoArg`` variant.

    Args:
        changes: Ordered list of ``(anchor, arg, op)`` tuples.
        geometry: Current board geometry.

    Returns:
        ``Result[BoardGeometry]`` — Ok with updated geometry on
        success, Err on first failure.
    """

    anchor: sfN
    arg: GeoArg
    op: str | GeoOp
    for anchor, arg, op in changes:
        if not isinstance(arg, GeoArgScalar):
            return resultErr_build(
                f"unsupported GeoArg type: {type(arg).__name__}"
                f" for anchor {anchor.name}"
            )
        geoOp: GeoOp = GeoOp(op) if isinstance(op, str) else op
        dCols: int
        dRows: int
        dCols, dRows = _anchorDeltas_resolve(anchor, arg.value)

        if anchor not in RULES:
            return resultErr_build(
                f"anchor {anchor.name} has no rules defined"
            )
        geometry = rules_apply(
            anchor, geoOp, dCols, dRows, geometry
        )

    return resultOk_build(geometry)


__all__ = [
    "GeoArg",
    "GeoArgScalar",
    "GeoArgScaled",
    "GeoChange",
    "GeoEffect",
    "GeoOp",
    "RuleBank",
    "RuleEntry",
    "RULES",
    "TopologyFace",
    "geometry_change",
    "rules_apply",
]
