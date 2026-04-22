"""Chip attach-point models for the new SignalFlow engine.

This module converts chip-local geometry (line offsets within a chip block)
into world-coordinate attach points by combining:

1. `ChipLocalGeometry` — which line within the chip a terminal occupies
2. `RoutingZone` placement — where the chip sits within a terminal region
3. The chip's stack offset — how many lines precede this chip in its region

The result is `ChipAttachPoint`: the exact world-coordinate row
(for WE zones) or column (for NS zones) at which a chip terminal
connects to the routing fabric.

These models are the authoritative answer to
"where does this terminal wire enter the routing network?"
and must not be rediscovered by renderer heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.board.doctrine import BoardChipPlacementPolicy
from signalflow.models import (
    ChipPlacement,
    ChipRef,
    ChipTerminalRef,
    ChipTerminalSide,
    CircuitDocument,
    Result,
    RoutingZone,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    routingZoneRegionForKindAndSideResult_get,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.routing.geometry import (
    ChipLocalGeometry,
    ChipLocalGeometrySet,
    chipCanvasPlacementGeometry_build,
    chipPlacementStackOffsetResult_build,
)


@dataclass(frozen=True)
class ChipAttachPoint:
    """World-coordinate attach point for one terminal of one placed chip.

    Attributes:
        chipTerminalRef: Owner-qualified terminal identity.
        worldRow: World-coordinate vertical index (primary for WE zones).
        worldColumn: World-coordinate horizontal index (primary for NS zones;
            equals the terminal region column for WE zones).
    """

    chipTerminalRef: ChipTerminalRef
    worldRow: int
    worldColumn: int

    @property
    def chipRef(self) -> ChipRef:
        """Return the owning chip reference."""

        return self.chipTerminalRef.chipRef

    @property
    def terminalSide(self) -> ChipTerminalSide:
        """Return the terminal side."""

        return self.chipTerminalRef.terminalSide

    @property
    def terminalName(self) -> str:
        """Return the terminal name."""

        return self.chipTerminalRef.terminalName


@dataclass(frozen=True)
class ChipAttachPointSet:
    """Modeled collection of chip attach points for one placed routing zone.

    Attributes:
        attachPoints: All computed attach points for the zone.
    """

    attachPoints: tuple[ChipAttachPoint, ...] = field(default_factory=tuple)

    def attachPointsForChip_get(
        self,
        chipRef: ChipRef,
    ) -> tuple[ChipAttachPoint, ...]:
        """Return all attach points belonging to one chip.

        Args:
            chipRef: Stable reference to the chip to look up.

        Returns:
            Tuple of `ChipAttachPoint` records for the chip, possibly empty.
        """

        return tuple(pt for pt in self.attachPoints if pt.chipRef == chipRef)

    def attachPointForTerminalResult_get(
        self,
        chipRef: ChipRef,
        terminalSide: ChipTerminalSide,
        terminalName: str,
    ) -> Result[ChipAttachPoint]:
        """Return the attach point for one specific terminal.

        Args:
            chipRef: Stable reference to the chip that owns the terminal.
            terminalSide: Side on which the terminal is exposed.
            terminalName: Stable terminal label to look up.

        Returns:
            Successful result containing the `ChipAttachPoint`, or a failed
            result if no matching attach point is found.
        """

        for pt in self.attachPoints:
            if (
                pt.chipTerminalRef.chipRef == chipRef
                and pt.chipTerminalRef.terminalSide is terminalSide
                and pt.chipTerminalRef.terminalName == terminalName
            ):
                return resultOk_build(pt)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.attach.set.missing_terminal",
            message=(
                "ChipAttachPointSet does not contain the requested terminal"
            ),
            context=(
                chipRef.chipId.moduleName,
                chipRef.chipId.functionName,
                terminalSide.value,
                terminalName,
            ),
        )
        return resultErr_build()


def chipAttachPointSetResult_buildFromPlacedZone(
    zone: RoutingZone,
    chipLocalGeometrySet: ChipLocalGeometrySet,
    circuitDocument: CircuitDocument,
    chipPlacementPolicy: BoardChipPlacementPolicy = (
        BoardChipPlacementPolicy.CENTROIDAL
    ),
) -> Result[ChipAttachPointSet]:
    """Build world-coordinate attach points for all chips in one placed zone.

    For each terminal region side (WEST+EAST for WE zones; NORTH+SOUTH for NS
    zones), chips are stacked in `orderIndex` order within the region. Each
    chip's stack offset follows the same spacing doctrine used by the world
    compositor and chip-route placement maps: the cumulative chip extent of all
    preceding chips in that region plus the inter-chip gutter.

    World row computation for WE zones:
        worldRow = (
            terminalRegionVerticalStart + stackOffset + terminalLineOffset
        )

    World column is the `horizontalStart` of the CHIP_TERMINAL region for that
    side.

    Args:
        zone: Fully placed routing zone with chip placements and region frames.
        chipLocalGeometrySet: Pre-built chip-local geometry for every chip
            that may appear in the zone.
        circuitDocument: Circuit document providing chip specifications.

    Returns:
        Successful result containing `ChipAttachPointSet`, or a failed result
        if any chip or terminal geometry cannot be resolved.
    """

    if zone.routingZoneSense is RoutingZoneSense.WEST_TO_EAST:
        return _weAttachPointSetResult_build(
            zone=zone,
            chipLocalGeometrySet=chipLocalGeometrySet,
            circuitDocument=circuitDocument,
            chipPlacementPolicy=chipPlacementPolicy,
        )
    return _nsAttachPointSetResult_build(
        zone=zone,
        chipLocalGeometrySet=chipLocalGeometrySet,
        circuitDocument=circuitDocument,
        chipPlacementPolicy=chipPlacementPolicy,
    )


def _weAttachPointSetResult_build(
    zone: RoutingZone,
    chipLocalGeometrySet: ChipLocalGeometrySet,
    circuitDocument: CircuitDocument,
    chipPlacementPolicy: BoardChipPlacementPolicy,
) -> Result[ChipAttachPointSet]:
    """Build attach points for a west-to-east zone."""

    attachPointsMutable: list[ChipAttachPoint] = []

    for regionSide in (
        RoutingZoneRegionSide.WEST,
        RoutingZoneRegionSide.EAST,
    ):
        terminalRegionResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.CHIP_TERMINAL,
            regionSide,
        )
        if not result_isOkCheck(terminalRegionResult):
            return resultErr_build()

        terminalRegionVerticalStart: int = (
            terminalRegionResult.value.routingZoneRegionFrame.verticalStart
        )
        terminalRegionHorizontalStart: int = (
            terminalRegionResult.value.routingZoneRegionFrame.horizontalStart
        )

        sidePlacements: list[ChipPlacement] = sorted(
            (
                p
                for p in zone.chipPlacementSet.placements
                if p.chipTerminalRegionId.routingZoneRegionSide is regionSide
            ),
            key=lambda p: p.orderIndex,
        )

        for placement in sidePlacements:
            chipResult = circuitDocument.circuitChipSet.chipResult_get(
                placement.chipRef.chipId
            )
            if not result_isOkCheck(chipResult):
                return resultErr_build()

            geoResult = chipLocalGeometrySet.geometryForChipResult_get(
                placement.chipRef
            )
            if not result_isOkCheck(geoResult):
                return resultErr_build()
            geo: ChipLocalGeometry = geoResult.value
            stackOffsetResult = chipPlacementStackOffsetResult_build(
                sidePlacements=sidePlacements,
                targetPlacement=placement,
                chipLocalGeometrySet=chipLocalGeometrySet,
                routingZoneSense=zone.routingZoneSense,
                regionSide=regionSide,
                terminalRegionSpan=terminalRegionResult.value.routingZoneRegionFrame.verticalSpan,
                chipPlacementPolicy=chipPlacementPolicy,
            )
            if not result_isOkCheck(stackOffsetResult):
                return resultErr_build()
            placementGeometry = chipCanvasPlacementGeometry_build(
                chipLocalGeometry=geo,
                routingZoneSense=zone.routingZoneSense,
                regionSide=regionSide,
                terminalRegionVerticalStart=terminalRegionVerticalStart,
                terminalRegionHorizontalStart=terminalRegionHorizontalStart,
                stackOffset=stackOffsetResult.value,
            )

            for entry in geo.terminalLineOffsets:
                if entry.terminalSide not in {
                    ChipTerminalSide.WEST,
                    ChipTerminalSide.EAST,
                }:
                    continue
                worldRow: int = (
                    placementGeometry.drawWorldRow + entry.lineOffset
                )
                worldColumn: int = placementGeometry.boxWorldColumn
                if entry.terminalSide is ChipTerminalSide.EAST:
                    worldColumn += geo.boxWidth - 1
                attachPointsMutable.append(
                    ChipAttachPoint(
                        chipTerminalRef=entry.chipTerminalRef,
                        worldRow=worldRow,
                        worldColumn=worldColumn,
                    )
                )

    return resultOk_build(
        ChipAttachPointSet(attachPoints=tuple(attachPointsMutable))
    )


def _nsAttachPointSetResult_build(
    zone: RoutingZone,
    chipLocalGeometrySet: ChipLocalGeometrySet,
    circuitDocument: CircuitDocument,
    chipPlacementPolicy: BoardChipPlacementPolicy,
) -> Result[ChipAttachPointSet]:
    """Build attach points for a north-to-south zone.

    In NS zones the primary dimension for stacking is horizontal.  Chips are
    stacked left-to-right within the NORTH and SOUTH CHIP_TERMINAL regions.
    The world column is the terminal region horizontal start plus the chip
    stack offset; the world row is the terminal region vertical start.
    """

    attachPointsMutable: list[ChipAttachPoint] = []

    for regionSide in (
        RoutingZoneRegionSide.NORTH,
        RoutingZoneRegionSide.SOUTH,
    ):
        terminalRegionResult = routingZoneRegionForKindAndSideResult_get(
            zone,
            RoutingZoneRegionKind.CHIP_TERMINAL,
            regionSide,
        )
        if not result_isOkCheck(terminalRegionResult):
            return resultErr_build()

        terminalRegionHorizontalStart: int = (
            terminalRegionResult.value.routingZoneRegionFrame.horizontalStart
        )
        terminalRegionVerticalStart: int = (
            terminalRegionResult.value.routingZoneRegionFrame.verticalStart
        )

        sidePlacements: list[ChipPlacement] = sorted(
            (
                p
                for p in zone.chipPlacementSet.placements
                if p.chipTerminalRegionId.routingZoneRegionSide is regionSide
            ),
            key=lambda p: p.orderIndex,
        )

        for placement in sidePlacements:
            chipResult = circuitDocument.circuitChipSet.chipResult_get(
                placement.chipRef.chipId
            )
            if not result_isOkCheck(chipResult):
                return resultErr_build()

            geoResult = chipLocalGeometrySet.geometryForChipResult_get(
                placement.chipRef
            )
            if not result_isOkCheck(geoResult):
                return resultErr_build()
            geo: ChipLocalGeometry = geoResult.value
            stackOffsetResult = chipPlacementStackOffsetResult_build(
                sidePlacements=sidePlacements,
                targetPlacement=placement,
                chipLocalGeometrySet=chipLocalGeometrySet,
                routingZoneSense=zone.routingZoneSense,
                regionSide=regionSide,
                terminalRegionSpan=terminalRegionResult.value.routingZoneRegionFrame.horizontalSpan,
                chipPlacementPolicy=chipPlacementPolicy,
            )
            if not result_isOkCheck(stackOffsetResult):
                return resultErr_build()
            placementGeometry = chipCanvasPlacementGeometry_build(
                chipLocalGeometry=geo,
                routingZoneSense=zone.routingZoneSense,
                regionSide=regionSide,
                terminalRegionVerticalStart=terminalRegionVerticalStart,
                terminalRegionHorizontalStart=terminalRegionHorizontalStart,
                stackOffset=stackOffsetResult.value,
            )

            for entry in geo.terminalLineOffsets:
                if entry.terminalSide not in {
                    ChipTerminalSide.NORTH,
                    ChipTerminalSide.SOUTH,
                }:
                    continue
                worldColumn: int = (
                    placementGeometry.drawWorldColumn + entry.lineOffset
                )
                worldRow: int = placementGeometry.boxWorldRow
                if entry.terminalSide is ChipTerminalSide.SOUTH:
                    worldRow += geo.boxHeight - 1
                attachPointsMutable.append(
                    ChipAttachPoint(
                        chipTerminalRef=entry.chipTerminalRef,
                        worldRow=worldRow,
                        worldColumn=worldColumn,
                    )
                )

    return resultOk_build(
        ChipAttachPointSet(attachPoints=tuple(attachPointsMutable))
    )
