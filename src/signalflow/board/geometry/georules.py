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

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from enum import StrEnum
from typing import TypeAlias, cast

from signalflow.board.geometry.expr import ZoneFace
from signalflow.board.geometry.mutation import boardRegionIdResult_fromSfN
from signalflow.board.geometry.zones import BoardGeometry, GeometryZone
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    TerminalPositionsByChip,
)
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


class TopologyRegions(StrEnum):
    """Sweep direction for a zone-collection rule target.

    Distinct from ``TopologyFace`` (which names the face of a single zone to
    stretch).  ``TopologyRegions`` describes the cardinal direction used to
    gather all first-class zones beyond an anchor when applying a bulk effect.
    """

    WEST = "west"
    EAST = "east"
    NORTH = "north"
    SOUTH = "south"


@dataclass(frozen=True)
class ZoneRegionCollectExclusive:
    """Rule-bank descriptor for a directional zone collection (anchor excluded).

    When used as the target in a ``RuleEntry`` tuple, ``rules_apply`` resolves
    ``anchor`` to a ``BoardRegionId``, calls
    ``geometry.zonesCollect_get(anchorId, alongDirection=direction)``, and
    applies the entry's ``GeoEffect`` to every zone strictly beyond the anchor.
    The anchor itself is not included.

    Only ``GeoEffect.TRANSLATE`` is valid on a collection; ``STRETCH``
    requires a single named face and will be rejected.

    Attributes:
        anchor: First-class sfN zone whose frame position defines the
            collection threshold.
        direction: Cardinal direction to sweep from the anchor.
    """

    anchor: sfN
    direction: TopologyRegions


@dataclass(frozen=True)
class ZoneRegionCollectInclusive:
    """Rule-bank descriptor for a directional zone collection (anchor included).

    Identical to ``ZoneRegionCollectExclusive`` except the anchor zone itself
    is also translated.  Use when the anchor is the westernmost (or northernmost)
    member of the cluster that should move as a rigid block.

    Attributes:
        anchor: First-class sfN zone whose frame position defines the
            collection threshold; also translated.
        direction: Cardinal direction to sweep from the anchor.
    """

    anchor: sfN
    direction: TopologyRegions


ZoneRegionCollect = ZoneRegionCollectExclusive


class GeoOp(StrEnum):
    """Operation applied to an anchor zone."""

    DISPLACE     = "+="   # sign-agnostic fallback
    DISPLACE_NEG = "+=-"  # used when delta < 0
    DISPLACE_POS = "+=+"  # used when delta > 0


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
# target: sfN                        — specific named zone
#         sfN.Z                       — all zones in geometry (sentinel)
#         ZoneRegionCollectExclusive  — all first-class zones strictly beyond anchor
#         ZoneRegionCollectInclusive  — anchor + all first-class zones beyond it
# face is None for TRANSLATE (whole zone moves, no single face)
# factor multiplies the anchor delta to produce the applied delta
RuleTarget: TypeAlias = sfN | ZoneRegionCollectExclusive | ZoneRegionCollectInclusive
RuleEntry = list[tuple[RuleTarget, TopologyFace | None, GeoEffect, int]]
RuleBank = dict[sfN, dict[GeoOp, RuleEntry]]

RULES: RuleBank = {
    sfN.Z: {
        GeoOp.DISPLACE: [
            (sfN.Z, None, GeoEffect.TRANSLATE, +1),
        ],
    },
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
    # ---- west chip terminal ------------------------------------------------
    # Wt -= m  =>  Z +m (floor guard), {Wt,Wfe,We,Ne,Se} -m
    #              (net zero via WEST collect), Wfi.west +~~ -m,
    #              Ne.east +~~ +m, Se.east +~~ +m
    # Order load-bearing: Z fires first.  Net absolute: routing core shifts
    # east by m; Wt/Wfe/We hold position, widening chip-terminal real estate.
    # Wfi stretches its west face to bridge the new gap.
    # Ne/Se stretch only their east face to cover displaced east extent.
    #
    # Wt += m  =>  Z +m (all east), {Wt,Wfe,We,Ne,Se} back via WEST collect,
    #              Wfi needs no stretch (Z already positions it flush with
    #              expanded Wt right edge), Ne/Se stretch west face to cover
    #              the gap between outer boundary and shifted frame.
    sfN.Wt: {
        GeoOp.DISPLACE_NEG: [
            (sfN.Z,  None,              GeoEffect.TRANSLATE, -1),
            (
                ZoneRegionCollect(sfN.Wfi, TopologyRegions.WEST),
                None,
                GeoEffect.TRANSLATE,
                +1,
            ),
            (sfN.Wfi, TopologyFace.WEST, GeoEffect.STRETCH, +1),
            (sfN.Ne, TopologyFace.EAST,  GeoEffect.STRETCH, -1),
            (sfN.Se, TopologyFace.EAST,  GeoEffect.STRETCH, -1),
        ],
        GeoOp.DISPLACE_POS: [
            (sfN.Z,  None,              GeoEffect.TRANSLATE, +1),
            (
                ZoneRegionCollect(sfN.Wfi, TopologyRegions.WEST),
                None,
                GeoEffect.TRANSLATE,
                -1,
            ),
            (sfN.Ne, TopologyFace.EAST,  GeoEffect.STRETCH, +1),
            (sfN.Se, TopologyFace.EAST,  GeoEffect.STRETCH, +1),
        ],
    },
    # ---- north extra ring --------------------------------------------------
    # Ne -= n  =>  Z +n (floor guard), Ne/Nt/Nfi/Nfe -n
    #              (net zero — undo Z shift for north perimeter),
    #              We.north +~~ -n, Wi.north +~~ -n,
    #              Ei.north +~~ -n, Ee.north +~~ -n
    # Order load-bearing: Z fires first.  Net absolute: routing core shifts
    # south by n; north perimeter (Ne/Nt/Nfi/Nfe) holds position, widening
    # northern real estate.
    sfN.Ne: {
        GeoOp.DISPLACE: [
            (sfN.Z,   None,               GeoEffect.TRANSLATE, -1),
            (sfN.Ne,  None,               GeoEffect.TRANSLATE, +1),
            (sfN.Nt,  None,               GeoEffect.TRANSLATE, +1),
            (sfN.Nfi, None,               GeoEffect.TRANSLATE, +1),
            (sfN.Nfe, None,               GeoEffect.TRANSLATE, +1),
            (sfN.We,  TopologyFace.NORTH, GeoEffect.STRETCH,  +1),
            (sfN.Wi,  TopologyFace.NORTH, GeoEffect.STRETCH,  +1),
            (sfN.Ei,  TopologyFace.NORTH, GeoEffect.STRETCH,  +1),
            (sfN.Ee,  TopologyFace.NORTH, GeoEffect.STRETCH,  +1),
        ],
    },
    # ---- south extra ring --------------------------------------------------
    # Se += n  =>  Se/St/Sfi/Sfe translates +n,  We.south +~~ n,
    #              Wi.south +~~ n,  Ei.south +~~ n,  Ee.south +~~ n
    sfN.Se: {
        GeoOp.DISPLACE: [
            (sfN.Se,  None,               GeoEffect.TRANSLATE, +1),
            (sfN.St,  None,               GeoEffect.TRANSLATE, +1),
            (sfN.Sfi, None,               GeoEffect.TRANSLATE, +1),
            (sfN.Sfe, None,               GeoEffect.TRANSLATE, +1),
            (sfN.We,  TopologyFace.SOUTH, GeoEffect.STRETCH,  +1),
            (sfN.Wi,  TopologyFace.SOUTH, GeoEffect.STRETCH,  +1),
            (sfN.Ei,  TopologyFace.SOUTH, GeoEffect.STRETCH,  +1),
            (sfN.Ee,  TopologyFace.SOUTH, GeoEffect.STRETCH,  +1),
        ],
    },
    # ---- east chip terminal ------------------------------------------------
    # Et += n  =>  everything east of Efi translates +n (Et, Efe, Ee),
    #              Efi.east +~~ n,  Ne.east +~~ n,  Se.east +~~ n
    # Efi stretches its east face to stay abutting Et.
    sfN.Et: {
        GeoOp.DISPLACE: [
            (
                ZoneRegionCollect(sfN.Efi, TopologyRegions.EAST),
                None,
                GeoEffect.TRANSLATE,
                +1,
            ),
            (sfN.Efi, TopologyFace.EAST, GeoEffect.STRETCH, +1),
            (sfN.Ne, TopologyFace.EAST, GeoEffect.STRETCH, +1),
            (sfN.Se, TopologyFace.EAST, GeoEffect.STRETCH, +1),
        ],
    },
}


def _boundaryPredicate_build(
    *,
    horizontal: bool,
    anchorCoord: int,
    forward: bool,
) -> Callable[[float, float], bool]:
    """Return boundary-centre predicate for collected zones."""

    def predicate(horizontalMid: float, verticalMid: float) -> bool:
        if horizontal:
            if forward:
                return horizontalMid > anchorCoord
            return horizontalMid < anchorCoord
        if forward:
            return verticalMid > anchorCoord
        return verticalMid < anchorCoord

    return predicate


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

    anchorRules: dict[GeoOp, RuleEntry] = RULES.get(anchor, {})
    effects: RuleEntry
    if op is GeoOp.DISPLACE:
        delta: int = deltaColumns or deltaRows
        if delta < 0 and GeoOp.DISPLACE_NEG in anchorRules:
            effects = anchorRules[GeoOp.DISPLACE_NEG]
        elif delta > 0 and GeoOp.DISPLACE_POS in anchorRules:
            effects = anchorRules[GeoOp.DISPLACE_POS]
        else:
            effects = anchorRules.get(GeoOp.DISPLACE, [])
    else:
        effects = anchorRules.get(op, [])
    if not effects:
        return geometry

    zonesById: dict[BoardRegionId, GeometryZone] = dict(
        geometry.geometryZonesById
    )
    boundaryFramesByName: dict[str, RoutingZoneRegionFrame] = dict(
        geometry.effectiveBoundaryFramesByName
    )
    # Orphans follow Z-sentinel translations only (global coordinate shifts).
    # ZoneRegionCollect and individual-zone translates are zone-specific and
    # cannot be applied to position-unknown orphans without containment checks.
    orphanDeltaCols: int = 0
    orphanDeltaRows: int = 0

    target: RuleTarget
    face: TopologyFace | None
    effect: GeoEffect
    factor: int
    for target, face, effect, factor in effects:
        appliedCols: int = factor * deltaColumns
        appliedRows: int = factor * deltaRows

        # ------------------------------------------------------------------
        # Phase 1: resolve the set of zone IDs to affect, and the optional
        # boundary-filter predicate (None = all boundaries, callable = filter
        # by centre coordinate).
        # ------------------------------------------------------------------

        translateRids: list[BoardRegionId] | None = None  # TRANSLATE targets
        stretchRids: list[BoardRegionId] | None = None    # STRETCH targets
        # Boundary predicate: given (horizontalMid, verticalMid) -> bool
        boundaryPredicate: bool | Callable[[float, float], bool] | None = None

        if isinstance(target, (ZoneRegionCollectExclusive, ZoneRegionCollectInclusive)):
            if effect is not GeoEffect.TRANSLATE:
                continue
            anchorRidResult: Result[BoardRegionId] = (
                boardRegionIdResult_fromSfN(target.anchor)
            )
            if not result_isOkCheck(anchorRidResult):
                continue
            zoneFace: ZoneFace = ZoneFace(target.direction.value)
            collectGeometry: BoardGeometry = BoardGeometry(
                geometryZonesById=zonesById
            )
            collectIds: frozenset[BoardRegionId] = (
                collectGeometry.zonesCollect_get(
                    anchorRidResult.value,
                    alongDirection=zoneFace,
                )
            )
            translateRids = list(collectIds)
            if isinstance(target, ZoneRegionCollectInclusive):
                translateRids.append(anchorRidResult.value)
            # Boundary frames follow the collect if their centre is in the
            # same directional half as the collected zones.
            anchorZone: GeometryZone | None = zonesById.get(
                anchorRidResult.value
            )
            if anchorZone is not None:
                horizontal: bool = zoneFace in (ZoneFace.EAST, ZoneFace.WEST)
                anchorCoord: int = (
                    anchorZone.frame.horizontalStart
                    if horizontal
                    else anchorZone.frame.verticalStart
                )
                forward: bool = zoneFace in (ZoneFace.EAST, ZoneFace.SOUTH)
                boundaryPredicate = _boundaryPredicate_build(
                    horizontal=horizontal,
                    anchorCoord=anchorCoord,
                    forward=forward,
                )

        elif target is sfN.Z:
            translateRids = list(zonesById)
            boundaryPredicate = True  # all boundaries follow Z
            if effect is GeoEffect.TRANSLATE:
                orphanDeltaCols += appliedCols
                orphanDeltaRows += appliedRows

        else:
            ridResult: Result[BoardRegionId] = (
                boardRegionIdResult_fromSfN(cast(sfN, target))
            )
            if not result_isOkCheck(ridResult):
                continue
            regionId: BoardRegionId = ridResult.value
            # Band wildcard: sfN resolves band=None.
            # Zones store upper/lower.
            if regionId in zonesById:
                stretchRids = translateRids = [regionId]
            else:
                matched: list[BoardRegionId] = [
                    rid for rid in zonesById
                    if rid.family == regionId.family
                    and rid.side == regionId.side
                    and regionId.band is None
                ]
                stretchRids = translateRids = matched
            if not translateRids:
                continue

        # ------------------------------------------------------------------
        # Phase 2: apply effect to resolved zone IDs.
        # ------------------------------------------------------------------

        rid: BoardRegionId
        if effect is GeoEffect.TRANSLATE and translateRids is not None:
            for rid in translateRids:
                zone: GeometryZone = zonesById[rid]
                zonesById[rid] = _zoneTranslated_build(
                    zone, appliedCols, appliedRows
                )

        elif effect is GeoEffect.STRETCH and face is not None:
            rids = stretchRids or []
            stretchDelta: int = (
                appliedCols
                if face in (TopologyFace.EAST, TopologyFace.WEST)
                else appliedRows
            )
            for rid in rids:
                zone = zonesById[rid]
                zonesById[rid] = GeometryZone(
                    regionId=zone.regionId,
                    frame=_frameFaceStretched_build(
                        zone.frame, face, stretchDelta
                    ),
                    routingZoneRegionId=zone.routingZoneRegionId,
                    chipDrawPlacementsByChip=zone.chipDrawPlacementsByChip,
                    exactTerminalWorldPositionsByChip=(
                        zone.exactTerminalWorldPositionsByChip
                    ),
                )

        # ------------------------------------------------------------------
        # Phase 3: translate boundary frames when the effect is a translate
        # and a predicate was resolved.
        # ------------------------------------------------------------------

        if effect is GeoEffect.TRANSLATE and boundaryPredicate is not None:
            bName: str
            for bName in list(boundaryFramesByName):
                bFrame = boundaryFramesByName[bName]
                bMid_h: float = (
                    bFrame.horizontalStart + bFrame.horizontalSpan / 2.0
                )
                bMid_v: float = (
                    bFrame.verticalStart + bFrame.verticalSpan / 2.0
                )
                include: bool = (
                    boundaryPredicate is True
                    or boundaryPredicate(bMid_h, bMid_v)  # type: ignore[operator]
                )
                if include:
                    boundaryFramesByName[bName] = _frameTranslated_build(
                        bFrame, appliedCols, appliedRows
                    )

    newGeometry = BoardGeometry(
        geometryZonesById=zonesById,
        effectiveBoundaryFramesByName=boundaryFramesByName,
    )
    # Forward orphan chip placements and terminal positions from the source
    # geometry, shifted by the accumulated Z-sentinel delta.  BoardGeometry
    # has no constructor path for orphan fields, so we set them directly.
    orphanPlacements: dict[str, BoardChipDrawPlacement] = {
        chipName: BoardChipDrawPlacement(
            chipName=placement.chipName,
            moduleName=placement.moduleName,
            side=placement.side,
            drawTopLeft=(
                placement.drawTopLeft[0] + orphanDeltaCols,
                placement.drawTopLeft[1] + orphanDeltaRows,
            ),
            drawLines=placement.drawLines,
        )
        for chipName, placement in (
            geometry._orphanChipDrawPlacementsByChip.items()
        )
    }
    orphanTerminals: TerminalPositionsByChip = {
        chipName: {
            termName: (pos[0] + orphanDeltaCols, pos[1] + orphanDeltaRows)
            for termName, pos in termPositions.items()
        }
        for chipName, termPositions in (
            geometry._orphanExactTerminalWorldPositionsByChip.items()
        )
    }
    object.__setattr__(
        newGeometry, "_orphanChipDrawPlacementsByChip", orphanPlacements
    )
    object.__setattr__(
        newGeometry,
        "_orphanExactTerminalWorldPositionsByChip",
        orphanTerminals,
    )
    return newGeometry


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
    """Return translated zone with frame, chip placements, and terminals."""
    shiftedPlacements: dict[str, BoardChipDrawPlacement] = {
        chipName: BoardChipDrawPlacement(
            chipName=placement.chipName,
            moduleName=placement.moduleName,
            side=placement.side,
            drawTopLeft=(
                placement.drawTopLeft[0] + deltaColumns,
                placement.drawTopLeft[1] + deltaRows,
            ),
            drawLines=placement.drawLines,
        )
        for chipName, placement in zone.chipDrawPlacementsByChip.items()
    }
    shiftedTerminals: TerminalPositionsByChip = {
        chipName: {
            termName: (pos[0] + deltaColumns, pos[1] + deltaRows)
            for termName, pos in termPositions.items()
        }
        for chipName, termPositions in (
            zone.exactTerminalWorldPositionsByChip.items()
        )
    }
    return GeometryZone(
        regionId=zone.regionId,
        frame=_frameTranslated_build(
            zone.frame, deltaColumns, deltaRows
        ),
        routingZoneRegionId=zone.routingZoneRegionId,
        chipDrawPlacementsByChip=shiftedPlacements,
        exactTerminalWorldPositionsByChip=shiftedTerminals,
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
    "RuleTarget",
    "RULES",
    "TopologyFace",
    "TopologyRegions",
    "ZoneRegionCollect",
    "ZoneRegionCollectExclusive",
    "ZoneRegionCollectInclusive",
    "geometry_change",
    "rules_apply",
]
