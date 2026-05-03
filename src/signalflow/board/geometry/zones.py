"""Canonical board-domain geometry models.

This module is the board-owned home for explicit region geometry. It stores
the concrete routing-region frames, effective boundaries, exact terminal
positions, and first-class geometry-zone projections that downstream layers
inspect and mutate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

from signalflow.board.geometry.expr import ZoneFace
from signalflow.board.render import boardGeometry_sprint
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    BoardSide,
    RegionBand,
    RegionBranch,
    RegionFamily,
    TerminalPositionsByChip,
    WorldFrame,
    WorldPoint,
    boardRegionLabel_build,
)
from signalflow.models import RoutingZoneRegionFrame, RoutingZoneRegionId
from signalflow.models.chip import ChipRef
from signalflow.models.geometry_scope import BoardGeometryScope

T = TypeVar("T")


def regionByName_get(
    itemsByName: dict[str, T],
    kindOrKey: str,
    side: str | None = None,
) -> T | None:
    """Resolve a named region from canonical lookup text.

    Args:
        itemsByName: Mapping keyed by canonical region labels.
        kindOrKey: Fully qualified label or unsided family label.
        side: Optional side qualifier such as `west` or `east`.

    Returns:
        Matching item when present, otherwise `None`.
    """

    if side is None and kindOrKey in itemsByName:
        return itemsByName[kindOrKey]

    wantKey = f"{side}/{kindOrKey}" if side is not None else kindOrKey
    if wantKey in itemsByName:
        return itemsByName[wantKey]

    suffix = f"/{kindOrKey}"
    for regionName, item in itemsByName.items():
        if regionName.endswith(suffix) and (
            side is None or regionName.startswith(f"{side}/")
        ):
            return item
    return None


def _frameContainsPointCheck(
    frame: RoutingZoneRegionFrame,
    worldPoint: WorldPoint,
) -> bool:
    """Return whether a world point lies inside a region frame.

    Args:
        frame: Region frame to test.
        worldPoint: Inclusive `(columnIndex, rowIndex)` world coordinate.

    Returns:
        `True` when the point lies inside the frame, otherwise `False`.
    """

    worldColumn, worldRow = worldPoint
    return (
        frame.horizontalStart
        <= worldColumn
        < frame.horizontalEnd_calculate()
        and frame.verticalStart <= worldRow < frame.verticalEnd_calculate()
    )


def UNUSED_frameContainsFrameCheck(
    outerFrame: RoutingZoneRegionFrame,
    innerFrame: WorldFrame,
) -> bool:
    """Return whether one inclusive frame is fully contained in a region frame.

    Args:
        outerFrame: Region frame to test.
        innerFrame: Inclusive world frame of an owned object such as a chip.

    Returns:
        `True` when the inclusive frame lies fully inside the region frame.
    """

    return _frameContainsPointCheck(outerFrame, innerFrame.topLeft) and (
        _frameContainsPointCheck(outerFrame, innerFrame.bottomRight)
    )


@dataclass(frozen=True)
class GeometryZone:
    """First-class board-owned geometry zone.

    Attributes:
        regionId: Canonical board-region identity.
        frame: Explicit world-coordinate frame for this region.
        routingZoneRegionId: Optional legacy region id retained for
            compatibility surfaces that still want the older model identity.
        chipDrawPlacementsByChip: Chip draw placements owned by this geometry
            zone.
        exactTerminalWorldPositionsByChip: Exact terminal attach points owned
            by this geometry zone.
    """

    regionId: BoardRegionId
    frame: RoutingZoneRegionFrame
    routingZoneRegionId: RoutingZoneRegionId | None = None
    chipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = field(
        default_factory=dict,
    )
    exactTerminalWorldPositionsByChip: TerminalPositionsByChip = field(
        default_factory=dict,
    )

    def __repr__(self) -> str:
        return (
            f"<GeometryZone {self.name_get()}"
            f" col={self.frame.horizontalStart}.."
            f"{self.frame.horizontalEnd_calculate() - 1}"
            f" row={self.frame.verticalStart}.."
            f"{self.frame.verticalEnd_calculate() - 1}"
            f" span=({self.frame.horizontalSpan}w x "
            f"{self.frame.verticalSpan}h)>"
        )

    def name_get(self) -> str:
        """Return the canonical readable label for this geometry zone.

        Returns:
            Legacy-style readable label such as `east/chip_terminal`.
        """

        return boardRegionLabel_build(self.regionId)

    def family_get(self) -> str:
        """Return the canonical board-region family name.

        Returns:
            Canonical board-region family value such as `chip_terminal`.
        """

        return self.regionId.family.value

    def side_get(self) -> str | None:
        """Return the optional board side for this geometry zone.

        Returns:
            Board side value when the region is sided, otherwise `None`.
        """

        if self.regionId.side is None:
            return None
        return self.regionId.side.value

    def topLeft_get(self) -> WorldPoint:
        """Return the inclusive world top-left of this geometry zone.

        Returns:
            `(columnIndex, rowIndex)` world coordinate for the top-left cell.
        """

        return (self.frame.horizontalStart, self.frame.verticalStart)

    def extent_get(self) -> tuple[int, int]:
        """Return the width/height extent of this geometry zone.

        Returns:
            `(widthColumns, heightRows)` span tuple.
        """

        return (self.frame.horizontalSpan, self.frame.verticalSpan)

    def worldFrame_get(self) -> WorldFrame:
        """Return the inclusive world frame of this geometry zone.

        Returns:
            Inclusive world frame spanning the geometry zone.
        """

        return WorldFrame(
            topLeft=self.topLeft_get(),
            bottomRight=(
                self.frame.horizontalEnd_calculate() - 1,
                self.frame.verticalEnd_calculate() - 1,
            ),
        )

    def summary_sprint(self) -> str:
        """Return a compact one-line human-readable summary.

        Returns:
            Summary line containing the zone label, top-left, bottom-right,
            and width/height span.
        """

        worldFrame = self.worldFrame_get()
        widthColumns, heightRows = self.extent_get()
        return (
            f"{self.name_get()}: topLeft={worldFrame.topLeft} "
            f"bottomRight={worldFrame.bottomRight} "
            f"span=({widthColumns}w x {heightRows}h)"
        )

    def chips_get(self) -> tuple[BoardChipDrawPlacement, ...]:
        """Return chip draw placements owned by this geometry zone.

        Returns:
            Tuple of chip draw placements sorted by chip name.
        """

        return tuple(
            chipPlacement
            for _, chipPlacement in sorted(
                self.chipDrawPlacementsByChip.items()
            )
        )

    def exactTerminals_get(self) -> TerminalPositionsByChip:
        """Return exact terminal attach points owned by this geometry zone.

        Returns:
            Terminal-position mapping keyed by chip name and terminal name.
        """

        return {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                self.exactTerminalWorldPositionsByChip.items()
            )
        }


@dataclass(frozen=True, init=False)
class BoardGeometry:
    """Canonical geometric state for one board.

    Attributes:
        geometryZonesById: Canonical geometry zones keyed by canonical
            board-region id.
        geometryScopes: Ordered depth-layer geometry scopes owning chip
            membership and load-bearing boundary frames.
        exactTerminalWorldPositionsByChip: Compatibility projection of exact
            attach-point coordinates aggregated from geometry zones.
        chipDrawPlacementsByChip: Compatibility projection of chip draw
            placements aggregated from geometry zones.
    """

    geometryZonesById: dict[BoardRegionId, GeometryZone] = field(
        default_factory=dict,
    )
    _geometryScopes: tuple[BoardGeometryScope, ...] = field(
        default_factory=tuple,
        repr=False,
    )
    _orphanExactTerminalWorldPositionsByChip: TerminalPositionsByChip = field(
        default_factory=dict,
        repr=False,
    )
    _orphanChipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement] = field(
        default_factory=dict,
        repr=False,
    )

    def __init__(
        self,
        *,
        geometryZonesById: dict[BoardRegionId, GeometryZone] | None = None,
        regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame]
        | None = None,
        routingZoneRegionIdsById: dict[BoardRegionId, RoutingZoneRegionId]
        | None = None,
        geometryScopes: tuple[BoardGeometryScope, ...] | None = None,
        exactTerminalWorldPositionsByChip: TerminalPositionsByChip
        | None = None,
        chipDrawPlacementsByChip: dict[str, BoardChipDrawPlacement]
        | None = None,
    ) -> None:
        """Normalize constructor inputs into canonical geometry zones.

        Args:
            geometryZonesById: Optional canonical geometry zones keyed by
                canonical board-region id.
            regionFramesById: Optional legacy region-frame map supplied by
                existing builder and test call sites.
            routingZoneRegionIdsById: Optional legacy region-id map keyed by
                canonical board-region id.
            geometryScopes: Ordered depth-layer geometry scopes owning chip
                membership and load-bearing boundary frames for this board.
            exactTerminalWorldPositionsByChip: Optional exact terminal
                attach-point map keyed by chip and terminal name.
            chipDrawPlacementsByChip: Optional chip draw placements keyed by
                chip name.
        """

        canonicalZonesById: dict[BoardRegionId, GeometryZone] = {}
        if geometryZonesById is not None:
            canonicalZonesById = dict(geometryZonesById)
        else:
            for regionId, frame in (regionFramesById or {}).items():
                canonicalZonesById[regionId] = GeometryZone(
                    regionId=regionId,
                    frame=frame,
                    routingZoneRegionId=(routingZoneRegionIdsById or {}).get(
                        regionId
                    ),
                )
        chipOwnerRegionIdByChip: dict[str, BoardRegionId] = {}
        chipPlacementsByName = dict(chipDrawPlacementsByChip or {})
        for chipName, chipPlacement in chipPlacementsByName.items():
            ownerRegionId = BoardRegionId(
                family=RegionFamily.CHIP_TERMINAL,
                side=chipPlacement.side,
            )
            ownerGeometryZone = canonicalZonesById.get(ownerRegionId)
            if ownerGeometryZone is None:
                continue
            canonicalZonesById[ownerRegionId] = GeometryZone(
                regionId=ownerGeometryZone.regionId,
                frame=ownerGeometryZone.frame,
                routingZoneRegionId=ownerGeometryZone.routingZoneRegionId,
                chipDrawPlacementsByChip={
                    **ownerGeometryZone.chipDrawPlacementsByChip,
                    chipName: chipPlacement,
                },
                exactTerminalWorldPositionsByChip=(
                    ownerGeometryZone.exactTerminalWorldPositionsByChip
                ),
            )
            chipOwnerRegionIdByChip[chipName] = ownerRegionId

        terminalPositionsByChip = dict(exactTerminalWorldPositionsByChip or {})
        for chipName, chipTerminalPositions in terminalPositionsByChip.items():
            ownerRegionId = chipOwnerRegionIdByChip.get(chipName)
            for terminalName, worldPoint in chipTerminalPositions.items():
                if ownerRegionId is not None:
                    geometryZone = canonicalZonesById[ownerRegionId]
                    existingChipPositions = dict(
                        geometryZone.exactTerminalWorldPositionsByChip.get(
                            chipName,
                            {},
                        )
                    )
                    existingChipPositions[terminalName] = worldPoint
                    canonicalZonesById[ownerRegionId] = GeometryZone(
                        regionId=geometryZone.regionId,
                        frame=geometryZone.frame,
                        routingZoneRegionId=geometryZone.routingZoneRegionId,
                        chipDrawPlacementsByChip=(
                            geometryZone.chipDrawPlacementsByChip
                        ),
                        exactTerminalWorldPositionsByChip={
                            **geometryZone.exactTerminalWorldPositionsByChip,
                            chipName: existingChipPositions,
                        },
                    )
                    continue

                for regionId, geometryZone in canonicalZonesById.items():
                    if not _frameContainsPointCheck(
                        geometryZone.frame,
                        worldPoint,
                    ):
                        continue
                    existingChipPositions = dict(
                        geometryZone.exactTerminalWorldPositionsByChip.get(
                            chipName,
                            {},
                        )
                    )
                    existingChipPositions[terminalName] = worldPoint
                    canonicalZonesById[regionId] = GeometryZone(
                        regionId=geometryZone.regionId,
                        frame=geometryZone.frame,
                        routingZoneRegionId=geometryZone.routingZoneRegionId,
                        chipDrawPlacementsByChip=(
                            geometryZone.chipDrawPlacementsByChip
                        ),
                        exactTerminalWorldPositionsByChip={
                            **geometryZone.exactTerminalWorldPositionsByChip,
                            chipName: existingChipPositions,
                        },
                    )
                    break
        object.__setattr__(self, "geometryZonesById", canonicalZonesById)
        object.__setattr__(
            self,
            "_geometryScopes",
            tuple(geometryScopes) if geometryScopes is not None else (),
        )
        assignedChipNames = {
            chipName
            for geometryZone in canonicalZonesById.values()
            for chipName in geometryZone.chipDrawPlacementsByChip
        }
        object.__setattr__(
            self,
            "_orphanChipDrawPlacementsByChip",
            {
                chipName: chipPlacement
                for chipName, chipPlacement in (
                    chipPlacementsByName.items()
                )
                if chipName not in assignedChipNames
            },
        )
        assignedTerminalChipNames = {
            chipName
            for geometryZone in canonicalZonesById.values()
            for chipName in geometryZone.exactTerminalWorldPositionsByChip
        }
        object.__setattr__(
            self,
            "_orphanExactTerminalWorldPositionsByChip",
            {
                chipName: dict(chipTerminalPositions)
                for chipName, chipTerminalPositions in (
                    terminalPositionsByChip.items()
                )
                if chipName not in assignedTerminalChipNames
            },
        )

    def all_get(self) -> tuple[RoutingZoneRegionFrame, ...]:
        """Return all concrete routing-region frames in stable label order.

        Returns:
            Tuple of routing-region frames sorted by canonical readable label.
        """

        return tuple(
            frame
            for _, frame in sorted(
                self.regionFramesByName.items(),
                key=lambda item: item[0],
            )
        )

    def zones_get(self) -> tuple[GeometryZone, ...]:
        """Return all geometry zones in stable label order.

        Returns:
            Tuple of `GeometryZone` objects sorted by canonical readable label.
        """

        zonesByName = self.zonesByName
        return tuple(
            zone
            for _, zone in sorted(
                zonesByName.items(),
                key=lambda item: item[0],
            )
        )

    def zone_get(
        self,
        kindOrKey: str,
        side: str | None = None,
    ) -> GeometryZone | None:
        """Return one geometry zone by canonical key or kind-and-side text.

        Args:
            kindOrKey: Fully qualified label or unsided family label.
            side: Optional side qualifier such as `west` or `east`.

        Returns:
            Matching `GeometryZone` when present, otherwise `None`.
        """

        return regionByName_get(self.zonesByName, kindOrKey, side)

    def area_get(
        self,
        kindOrKey: str,
        side: str | None = None,
    ) -> RoutingZoneRegionFrame | None:
        """Return one region frame by canonical key or kind-and-side text.

        Args:
            kindOrKey: Fully qualified label or unsided family label.
            side: Optional side qualifier such as `west` or `east`.

        Returns:
            Matching routing-region frame when present, otherwise `None`.
        """

        return regionByName_get(self.regionFramesByName, kindOrKey, side)

    def scopeForChipRef_get(
        self,
        chipRef: ChipRef,
    ) -> BoardGeometryScope | None:
        """Return the geometry scope that contains the given chip reference.

        Args:
            chipRef: Chip occurrence to look up by membership.

        Returns:
            First matching ``BoardGeometryScope`` when present, otherwise
            ``None``.
        """

        for scope in self._geometryScopes:
            if scope.chipRef_containsCheck(chipRef):
                return scope
        return None

    def scopeForModuleName_get(
        self,
        moduleName: str,
    ) -> BoardGeometryScope | None:
        """Return the geometry scope whose chips include at least one chip from
        the given module.

        Args:
            moduleName: Source module name to search by chip membership.

        Returns:
            First matching ``BoardGeometryScope`` when present, otherwise
            ``None``.
        """

        for scope in self._geometryScopes:
            if any(
                chipRef.chipId.moduleName == moduleName
                for chipRef in scope.chipRefs
            ):
                return scope
        return None

    @property
    def effectiveBoundaryFramesByName(
        self,
    ) -> dict[str, RoutingZoneRegionFrame]:
        """Derived boundary-frame dict keyed by scope label.

        Returns:
            Mapping from scope label (e.g. ``"layer/0"``) to the scope's
            bounding frame. Scopes with ``None`` frames are excluded.
        """

        return {
            scope.label: scope.frame
            for scope in self._geometryScopes
            if scope.frame is not None
        }

    def effectiveBoundaryFrame_get(
        self,
        scopeLabel: str,
    ) -> RoutingZoneRegionFrame | None:
        """Return the boundary frame for one scope by label or module name.

        Args:
            scopeLabel: Scope label (e.g. ``"layer/0"``) or legacy
                ``"module/X.ts"`` module-name key for backward compatibility.

        Returns:
            Bounding frame when the scope exists and has a frame, otherwise
            ``None``.
        """

        if scopeLabel.startswith("module/"):
            moduleName = scopeLabel[len("module/"):]
            scope = self.scopeForModuleName_get(moduleName)
            return scope.frame if scope is not None else None
        return self.effectiveBoundaryFramesByName.get(scopeLabel)

    def zoneNeighbor_get(
        self,
        anchorId: BoardRegionId,
        direction: ZoneFace,
    ) -> BoardRegionId | None:
        """Return the immediate first-class neighbor in the given direction.

        Operates only on first-class zones (``geometryZonesById``).  Derived
        corners and transfer regions are excluded.

        For EAST/WEST the comparison axis is ``horizontalStart``.
        For NORTH/SOUTH the comparison axis is ``verticalStart``.

        EAST neighbor = zone with smallest start that is still greater than
        the anchor's start.  WEST neighbor = zone with largest start that is
        still less than the anchor's start.  NORTH/SOUTH are analogous on the
        vertical axis.

        Args:
            anchorId: Region id of the anchor zone.
            direction: Cardinal direction to search.

        Returns:
            Region id of the nearest first-class neighbor, or ``None`` when no
            zone exists in that direction.
        """

        anchorZone: GeometryZone | None = self.geometryZonesById.get(anchorId)
        if anchorZone is None:
            return None

        horizontal: bool = direction in (ZoneFace.EAST, ZoneFace.WEST)
        anchorCoord: int = (
            anchorZone.frame.horizontalStart
            if horizontal
            else anchorZone.frame.verticalStart
        )
        forward: bool = direction in (ZoneFace.EAST, ZoneFace.SOUTH)

        best: BoardRegionId | None = None
        bestCoord: int | None = None
        rid: BoardRegionId
        zone: GeometryZone
        for rid, zone in self.geometryZonesById.items():
            if rid == anchorId:
                continue
            coord: int = (
                zone.frame.horizontalStart
                if horizontal
                else zone.frame.verticalStart
            )
            if forward:
                if coord > anchorCoord and (
                    bestCoord is None or coord < bestCoord
                ):
                    best = rid
                    bestCoord = coord
            else:
                if coord < anchorCoord and (
                    bestCoord is None or coord > bestCoord
                ):
                    best = rid
                    bestCoord = coord
        return best

    def zonesCollect_get(
        self,
        anchorId: BoardRegionId,
        *,
        alongDirection: ZoneFace,
    ) -> frozenset[BoardRegionId]:
        """Return all first-class zones beyond the anchor in the given direction.

        Uses the anchor's ``horizontalStart`` (for EAST/WEST) or
        ``verticalStart`` (for NORTH/SOUTH) as threshold.  Zones whose
        corresponding start coordinate is strictly beyond that threshold are
        included.  The anchor itself is excluded.

        Operates only on first-class zones (``geometryZonesById``).

        Args:
            anchorId: Region id of the anchor zone.
            alongDirection: Cardinal direction to collect zones in.

        Returns:
            Frozen set of region ids of all first-class zones beyond the
            anchor in ``alongDirection``.
        """

        anchorZone: GeometryZone | None = self.geometryZonesById.get(anchorId)
        if anchorZone is None:
            return frozenset()

        horizontal: bool = alongDirection in (ZoneFace.EAST, ZoneFace.WEST)
        anchorCoord: int = (
            anchorZone.frame.horizontalStart
            if horizontal
            else anchorZone.frame.verticalStart
        )
        forward: bool = alongDirection in (ZoneFace.EAST, ZoneFace.SOUTH)

        result: set[BoardRegionId] = set()
        rid: BoardRegionId
        zone: GeometryZone
        for rid, zone in self.geometryZonesById.items():
            if rid == anchorId:
                continue
            coord: int = (
                zone.frame.horizontalStart
                if horizontal
                else zone.frame.verticalStart
            )
            if (
                forward and coord > anchorCoord
                or not forward and coord < anchorCoord
            ):
                result.add(rid)
        return frozenset(result)

    def exactTerminalWorldPosition_get(
        self,
        chipName: str,
        terminalName: str,
    ) -> WorldPoint | None:
        """Return the exact world attach point for one chip terminal.

        Args:
            chipName: Chip display name.
            terminalName: Terminal name on that chip.

        Returns:
            Exact attach-point world coordinate when present, otherwise `None`.
        """

        chipTerminalPositions = self.exactTerminalWorldPositionsByChip.get(
            chipName
        )
        if chipTerminalPositions is None:
            return None
        return chipTerminalPositions.get(terminalName)

    @property
    def geometryScopes(self) -> tuple[BoardGeometryScope, ...]:
        """Return ordered depth-layer geometry scopes for this board.

        Returns:
            Tuple of ``BoardGeometryScope`` objects in depth order.
        """

        return self._geometryScopes

    @property
    def drawableGeometryScopes(self) -> tuple[BoardGeometryScope, ...]:
        """Return only the geometry scopes configured for visible rendering.

        Returns:
            Tuple of ``BoardGeometryScope`` objects where ``drawable`` is
            ``True``, in depth order.
        """

        return tuple(s for s in self._geometryScopes if s.drawable)

    @property
    def exactTerminalWorldPositionsByChip(self) -> TerminalPositionsByChip:
        """Return exact terminal attach points aggregated from geometry zones.

        Returns:
            Mapping from chip name to terminal-name/world-point mappings.
        """

        positionsByChip: TerminalPositionsByChip = {}
        for geometryZone in self.geometryZonesById.values():
            for chipName, chipTerminalPositions in (
                geometryZone.exactTerminalWorldPositionsByChip.items()
            ):
                positionsByChip.setdefault(chipName, {}).update(
                    chipTerminalPositions
                )
        for chipName, chipTerminalPositions in (
            self._orphanExactTerminalWorldPositionsByChip.items()
        ):
            positionsByChip.setdefault(chipName, {}).update(
                chipTerminalPositions
            )
        return positionsByChip

    @property
    def chipDrawPlacementsByChip(self) -> dict[str, BoardChipDrawPlacement]:
        """Return chip draw placements aggregated from geometry zones.

        Returns:
            Mapping from chip name to draw placement.
        """

        placementsByChip: dict[str, BoardChipDrawPlacement] = {}
        for geometryZone in self.geometryZonesById.values():
            placementsByChip.update(geometryZone.chipDrawPlacementsByChip)
        placementsByChip.update(self._orphanChipDrawPlacementsByChip)
        return placementsByChip

    @property
    def regionFramesByName(self) -> dict[str, RoutingZoneRegionFrame]:
        """Compatibility projection keyed by legacy readable region labels.

        Includes stored zones and all derived corner/transfer frames so that
        consumers such as the realizer can access INTRA_TRANSITION and sibling
        families without requiring them to be stored in the builder output.

        Returns:
            Mapping from readable region label to routing-region frame.
        """

        return {
            boardRegionLabel_build(regionId): frame
            for regionId, frame in self.regionFramesAllById.items()
        }

    @property
    def regionIdsByName(self) -> dict[str, RoutingZoneRegionId]:
        """Compatibility projection keyed by legacy readable region labels.

        Returns:
            Mapping from readable region label to legacy region id.
        """

        return {
            boardRegionLabel_build(regionId): geometryZone.routingZoneRegionId
            for regionId, geometryZone in self.geometryZonesById.items()
            if geometryZone.routingZoneRegionId is not None
        }

    @property
    def regionFramesById(self) -> dict[BoardRegionId, RoutingZoneRegionFrame]:
        """Compatibility projection keyed by canonical board-region id.

        Returns:
            Mapping from canonical board-region id to routing-region frame.
        """

        return {
            regionId: geometryZone.frame
            for regionId, geometryZone in self.geometryZonesById.items()
        }

    @property
    def routingZoneRegionIdsById(
        self,
    ) -> dict[BoardRegionId, RoutingZoneRegionId]:
        """Compatibility projection keyed by canonical board-region id.

        Returns:
            Mapping from canonical board-region id to legacy region id.
        """

        return {
            regionId: geometryZone.routingZoneRegionId
            for regionId, geometryZone in self.geometryZonesById.items()
            if geometryZone.routingZoneRegionId is not None
        }

    @property
    def zonesByName(self) -> dict[str, GeometryZone]:
        """Return first-class geometry zones keyed by canonical labels.

        Returns:
            Mapping from readable region label to `GeometryZone`.
        """

        return {
            boardRegionLabel_build(regionId): geometryZone
            for regionId, geometryZone in self.geometryZonesById.items()
        }

    @property
    def zonesById(self) -> dict[BoardRegionId, GeometryZone]:
        """Return first-class geometry zones keyed by canonical region id.

        Returns:
            Mapping from canonical board-region id to `GeometryZone`.
        """

        return dict(self.geometryZonesById)

    def derivedFrameById_get(
        self,
        regionId: BoardRegionId,
    ) -> RoutingZoneRegionFrame | None:
        """Derive a corner or transfer region frame from parent band frames.

        All three corner/transfer families are pure frame intersections:

        - ``INTRA_TRANSITION``: INTRA_LONGITUDE(side, band) ∩ INTRA_LATITUDE(branch)
        - ``EXTRA_TRANSITION``: EXTRA_LONGITUDE(side) ∩ EXTRA_LATITUDE(branch)
        - ``INTRA_EXTRA_TRANSFER``: MEDIAL_LONGITUDE(side) ∩ EXTRA_LATITUDE(branch)

        Returns ``None`` when required parent frames are not stored (e.g. the
        board does not have extra routing).
        """

        family = regionId.family
        side = regionId.side
        branch = regionId.branch
        if side is None or branch is None:
            return None
        latSide = BoardSide(branch.value)

        if family is RegionFamily.INTRA_TRANSITION:
            band = RegionBand.UPPER if branch is RegionBranch.NORTH else RegionBand.LOWER
            longZone = self.geometryZonesById.get(
                BoardRegionId(family=RegionFamily.INTRA_LONGITUDE, side=side, band=band)
            )
            latZone = self.geometryZonesById.get(
                BoardRegionId(family=RegionFamily.INTRA_LATITUDE, side=latSide)
            )
            if longZone is None or latZone is None:
                return None
            return RoutingZoneRegionFrame(
                horizontalStart=longZone.frame.horizontalStart,
                horizontalSpan=longZone.frame.horizontalSpan,
                verticalStart=latZone.frame.verticalStart,
                verticalSpan=latZone.frame.verticalSpan,
            )

        if family is RegionFamily.EXTRA_TRANSITION:
            longZone = self.geometryZonesById.get(
                BoardRegionId(family=RegionFamily.EXTRA_LONGITUDE, side=side)
            )
            latZone = self.geometryZonesById.get(
                BoardRegionId(family=RegionFamily.EXTRA_LATITUDE, side=latSide)
            )
            if longZone is None or latZone is None:
                return None
            return RoutingZoneRegionFrame(
                horizontalStart=longZone.frame.horizontalStart,
                horizontalSpan=longZone.frame.horizontalSpan,
                verticalStart=latZone.frame.verticalStart,
                verticalSpan=latZone.frame.verticalSpan,
            )

        if family is RegionFamily.INTRA_EXTRA_TRANSFER:
            longZone = self.geometryZonesById.get(
                BoardRegionId(family=RegionFamily.MEDIAL_LONGITUDE, side=side)
            )
            latZone = self.geometryZonesById.get(
                BoardRegionId(family=RegionFamily.EXTRA_LATITUDE, side=latSide)
            )
            if longZone is None or latZone is None:
                return None
            return RoutingZoneRegionFrame(
                horizontalStart=longZone.frame.horizontalStart,
                horizontalSpan=longZone.frame.horizontalSpan,
                verticalStart=latZone.frame.verticalStart,
                verticalSpan=latZone.frame.verticalSpan,
            )

        return None

    @property
    def regionFramesAllById(self) -> dict[BoardRegionId, RoutingZoneRegionFrame]:
        """All region frames: stored zones plus all derived corner/transfer frames.

        Returns:
            Mapping from canonical board-region id to routing-region frame,
            including INTRA_TRANSITION, EXTRA_TRANSITION, and
            INTRA_EXTRA_TRANSFER corners derived on demand.
        """

        result: dict[BoardRegionId, RoutingZoneRegionFrame] = dict(
            self.regionFramesById
        )
        for family in (
            RegionFamily.INTRA_TRANSITION,
            RegionFamily.EXTRA_TRANSITION,
            RegionFamily.INTRA_EXTRA_TRANSFER,
        ):
            for side in (BoardSide.WEST, BoardSide.EAST):
                for branch in (RegionBranch.NORTH, RegionBranch.SOUTH):
                    rid = BoardRegionId(family=family, side=side, branch=branch)
                    frame = self.derivedFrameById_get(rid)
                    if frame is not None:
                        result[rid] = frame
        return result

    def geometry_sprint(
        self,
        columnOffset: int | None = None,
        legend_show: bool = True,
        drawableScopes: tuple[BoardGeometryScope, ...] | None = None,
    ) -> str:
        """Render the board routing substrate as world-coordinate text.

        Args:
            columnOffset: Optional world-column at which to begin the visible
                crop. When omitted, rendering begins at the first occupied
                board column.
            legend_show: Whether to append the legend block.
            drawableScopes: Override which scopes render boundary boxes.

        Returns:
            Multi-line rendered board geometry text.
        """

        effectiveScopes = (
            drawableScopes
            if drawableScopes is not None
            else self.drawableGeometryScopes
        )
        return boardGeometry_sprint(
            self.regionFramesAllById,
            geometryScopes=effectiveScopes,
            columnOffset=columnOffset,
            legend_show=legend_show,
        )
