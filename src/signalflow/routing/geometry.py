"""Chip-local geometry models for the new SignalFlow engine.

This module derives the drawing geometry for one chip from the canonical
`chipDrawLines_build` output. It is the authoritative source for:

- how many lines a chip occupies in its terminal region
- which line index within the chip block each terminal attaches to

These models are chip-relative (0-indexed from the chip's first drawn line).
World-coordinate conversion happens in `routing.attach`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.models import (
    Chip,
    ChipLocalRoutingOwner,
    ChipPlacement,
    ChipPortDeclaration,
    ChipRef,
    ChipTerminalRef,
    ChipTerminalSide,
    Result,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    chipDrawLines_build,
    chipRenderedWestTerminalNames_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


@dataclass(frozen=True)
class ChipTerminalLineOffset:
    """Row offset within one chip's own drawn block for one terminal.

    Attributes:
        chipTerminalRef: Owner-qualified terminal identity.
        lineOffset: 0-indexed line within the chip's own line block where
            the terminal's wire stub appears in `chipDrawLines_build` output.
    """

    chipTerminalRef: ChipTerminalRef
    lineOffset: int

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
class ChipLocalGeometry:
    """Local geometry for one chip as drawn in its terminal region.

    Attributes:
        owningChipLocalRoutingOwner: Concrete owner of this chip-local routing
            substrate.
        lineCount: Total lines produced by `chipDrawLines_build` for this chip.
        lineWidth: Width of the widest line in the chip's drawing.
        boxTopLineOffset: 0-indexed row of the actual top box border inside the
            full chip drawing.
        boxBottomLineOffset: 0-indexed row of the actual bottom box border
            inside the full chip drawing.
        boxLeftColumnOffset: 0-indexed column of the actual west box wall
            inside the full chip drawing.
        boxRightColumnOffset: 0-indexed column of the actual east box wall
            inside the full chip drawing.
        terminalLineOffsets: Row offsets within the chip's block for each terminal.
    """

    owningChipLocalRoutingOwner: ChipLocalRoutingOwner
    lineCount: int
    lineWidth: int
    boxTopLineOffset: int
    boxBottomLineOffset: int
    boxLeftColumnOffset: int
    boxRightColumnOffset: int
    terminalLineOffsets: tuple[ChipTerminalLineOffset, ...] = field(
        default_factory=tuple
    )

    @property
    def chipRef(self) -> ChipRef:
        """Return the owning chip reference."""

        return self.owningChipLocalRoutingOwner.chipRef

    @property
    def boxHeight(self) -> int:
        """Return the height of the actual chip box, excluding outer labels."""

        return self.boxBottomLineOffset - self.boxTopLineOffset + 1

    @property
    def boxWidth(self) -> int:
        """Return the width of the actual chip box, excluding outer stubs."""

        return self.boxRightColumnOffset - self.boxLeftColumnOffset + 1

    @property
    def westMarginWidth(self) -> int:
        """Return materialized width left of the west box wall."""

        return self.boxLeftColumnOffset

    @property
    def eastMarginWidth(self) -> int:
        """Return materialized width right of the east box wall."""

        return self.lineWidth - self.boxRightColumnOffset - 1

    @property
    def northMarginHeight(self) -> int:
        """Return materialized height above the top box border."""

        return self.boxTopLineOffset

    @property
    def southMarginHeight(self) -> int:
        """Return materialized height below the bottom box border."""

        return self.lineCount - self.boxBottomLineOffset - 1

    def lineOffsetForTerminalResult_get(
        self,
        terminalSide: ChipTerminalSide,
        terminalName: str,
    ) -> Result[int]:
        """Return the line offset for one named terminal on one side.

        Args:
            terminalSide: Side on which the terminal is expected.
            terminalName: Stable terminal label to look up.

        Returns:
            Successful result containing the line offset integer, or a failed
            result if the terminal is not found in this chip's geometry.
        """

        for entry in self.terminalLineOffsets:
            if (
                entry.terminalSide is terminalSide
                and entry.terminalName == terminalName
            ):
                return resultOk_build(entry.lineOffset)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.geometry.chip_local.missing_terminal",
            message="ChipLocalGeometry does not contain the requested terminal",
            context=(terminalSide.value, terminalName),
        )
        return resultErr_build()


@dataclass(frozen=True)
class ChipLocalGeometrySet:
    """Modeled collection of chip-local geometries.

    Attributes:
        chipLocalGeometries: All computed geometries, one per chip.
    """

    chipLocalGeometries: tuple[ChipLocalGeometry, ...] = field(
        default_factory=tuple
    )

    def geometryForChipResult_get(
        self,
        chipRef: ChipRef,
    ) -> Result[ChipLocalGeometry]:
        """Return the local geometry for one chip.

        Args:
            chipRef: Stable reference to the chip to look up.

        Returns:
            Successful result containing the `ChipLocalGeometry`, or a failed
            result if no geometry exists for the requested chip.
        """

        for geo in self.chipLocalGeometries:
            if geo.chipRef == chipRef:
                return resultOk_build(geo)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.geometry.set.missing_chip",
            message="ChipLocalGeometrySet does not contain the requested chip",
            context=(chipRef.chipId.moduleName, chipRef.chipId.functionName),
        )
        return resultErr_build()


@dataclass(frozen=True)
class ChipCanvasPlacementGeometry:
    """Resolved draw and box origins for one placed chip.

    Attributes:
        drawWorldRow: World row at which the full `chipDrawLines_build` block
            begins.
        drawWorldColumn: World column at which the full draw block begins.
        boxWorldRow: World row of the actual top box border.
        boxWorldColumn: World column of the actual west box wall.
    """

    drawWorldRow: int
    drawWorldColumn: int
    boxWorldRow: int
    boxWorldColumn: int


def chipPlacementStackSpan_calculate(
    chipLocalGeometry: ChipLocalGeometry,
    routingZoneSense: RoutingZoneSense,
    regionSide: RoutingZoneRegionSide,
) -> int:
    """Calculate the occupied stack span for one placed chip.

    This span includes the chip drawing itself plus the inter-chip gutter used
    by the world compositor and route-placement logic.

    Args:
        chipLocalGeometry: Local geometry of the placed chip.
        routingZoneSense: Primary routing sense of the owning zone.
        regionSide: Terminal-region side in which the chip is stacked.

    Returns:
        Total stack span contributed by this placed chip along the stacking
        axis.
    """

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST or regionSide in {
        RoutingZoneRegionSide.WEST,
        RoutingZoneRegionSide.EAST,
    }:
        return chipLocalGeometry.lineCount + 2
    return chipLocalGeometry.lineWidth + 2


def chipPlacementStackOffsetResult_build(
    sidePlacements: tuple[ChipPlacement, ...] | list[ChipPlacement],
    targetPlacement: ChipPlacement,
    chipLocalGeometrySet: ChipLocalGeometrySet,
    routingZoneSense: RoutingZoneSense,
    regionSide: RoutingZoneRegionSide,
) -> Result[int]:
    """Build the cumulative stack offset for one placed chip.

    Args:
        sidePlacements: Ordered placements that share one terminal-side band.
        targetPlacement: Placement whose stack offset is required.
        chipLocalGeometrySet: Local geometry set for every participating chip.
        routingZoneSense: Primary routing sense of the owning zone.
        regionSide: Terminal-region side on which the placements are stacked.

    Returns:
        Successful result containing the cumulative stack offset of the target
        placement, or a failed result when chip geometry cannot be resolved or
        the target placement is not found in the provided side placements.
    """

    cumulativeOffset: int = 0
    placement: ChipPlacement
    for placement in sidePlacements:
        if placement.chipRef == targetPlacement.chipRef:
            return resultOk_build(cumulativeOffset)
        geometryResult = chipLocalGeometrySet.geometryForChipResult_get(
            placement.chipRef
        )
        if not result_isOkCheck(geometryResult):
            return resultErr_build()
        cumulativeOffset += chipPlacementStackSpan_calculate(
            chipLocalGeometry=geometryResult.value,
            routingZoneSense=routingZoneSense,
            regionSide=regionSide,
        )
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.geometry.stack_offset.missing_target",
        message="Chip placement was not found in the requested side placement set",
        context=(
            targetPlacement.chipRef.chipId.moduleName,
            targetPlacement.chipRef.chipId.functionName,
            regionSide.value,
        ),
    )
    return resultErr_build()


def chipLocalGeometryResult_build(chip: Chip) -> Result[ChipLocalGeometry]:
    """Build local geometry for one chip from its canonical drawing.

    The chip-local geometry mirrors the structural layout of
    `chipDrawLines_build`: north-terminal labels, top-border, title,
    separator, body rows, bottom-border, south-terminal labels.  Terminal
    line offsets index into that sequence starting from 0.

    For a chip that has declared terminals the body starts at:
        northCount + 3  (1 for top border, 1 for title, 1 for separator)

    West terminals occupy body rows 0, 1, 2, ... in declaration order.
    East terminals also occupy body rows 0, 1, 2, ... in declaration order.

    North and south terminal label offsets are currently deferred; they do
    not carry route attach semantics in the WE primary routing regime.

    Args:
        chip: First-class chip specification to derive geometry from.

    Returns:
        Successful result containing `ChipLocalGeometry`, or a failed result
        if the chip drawing cannot be computed.
    """

    lines: tuple[str, ...] = chipDrawLines_build(chip)
    if not lines:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.geometry.chip_local.empty_drawing",
            message="chipDrawLines_build produced no lines for chip",
            context=(chip.chipId.moduleName, chip.chipId.functionName),
        )
        return resultErr_build()

    lineCount: int = len(lines)
    lineWidth: int = max(len(line) for line in lines)
    boxTopLineOffsetResult = _boxTopLineOffsetResult_build(lines)
    if not result_isOkCheck(boxTopLineOffsetResult):
        return resultErr_build()
    boxBottomLineOffsetResult = _boxBottomLineOffsetResult_build(lines)
    if not result_isOkCheck(boxBottomLineOffsetResult):
        return resultErr_build()
    boxLeftColumnOffsetResult = _boxLeftColumnOffsetResult_build(lines)
    if not result_isOkCheck(boxLeftColumnOffsetResult):
        return resultErr_build()
    boxRightColumnOffsetResult = _boxRightColumnOffsetResult_build(lines)
    if not result_isOkCheck(boxRightColumnOffsetResult):
        return resultErr_build()

    northCount: int = sum(
        1
        for t in chip.chipTerminalSet.terminals
        if t.terminalSide is ChipTerminalSide.NORTH
    )

    hasTerminals: bool = bool(chip.chipTerminalSet.terminals)

    terminalOffsetsMutable: list[ChipTerminalLineOffset] = []

    if hasTerminals:
        bodyStart: int = northCount + 3  # top-border + title-row + separator

        westTerminals: tuple[str, ...] = chipRenderedWestTerminalNames_build(chip)
        eastTerminals: tuple[str, ...] = tuple(
            t.terminalName
            for t in chip.chipTerminalSet.terminals
            if t.terminalSide is ChipTerminalSide.EAST
        )
        eastPortDecls = chip.outputPortDeclarationSet.portDeclarations
        if not eastPortDecls and eastTerminals:
            eastPortDecls = tuple(
                ChipPortDeclaration(signalName=name) for name in eastTerminals
            )
        nEastCalls: int = len(eastPortDecls)
        bodyRows: int = max(2 if hasTerminals else 1, 2 * nEastCalls)

        westSignalOffset: int = bodyStart
        westReturnOffset: int = bodyStart + 1
        if len(westTerminals) == 2 and bodyRows > 2:
            westSignalOffset = bodyStart + max(0, (bodyRows - 2) // 2)
            westReturnOffset = westSignalOffset + 1

        for i, terminalName in enumerate(westTerminals):
            if len(westTerminals) == 2:
                lineOffset = westSignalOffset if i == 0 else westReturnOffset
            else:
                lineOffset = bodyStart + i
            terminalOffsetsMutable.append(
                ChipTerminalLineOffset(
                    chipTerminalRef=ChipTerminalRef(
                        chipRef=chip.chipRef_build(),
                        terminalSide=ChipTerminalSide.WEST,
                        terminalName=terminalName,
                    ),
                    lineOffset=lineOffset,
                )
            )

        eastSignalOffset: int = bodyStart
        eastReturnOffset: int = bodyStart + 1
        centerSingleEastPair: bool = (
            nEastCalls == 1 and len(eastTerminals) == 2 and bodyRows > 2
        )
        if centerSingleEastPair:
            eastSignalOffset = bodyStart + max(0, (bodyRows - 2) // 2)
            eastReturnOffset = eastSignalOffset + 1

        for i, terminalName in enumerate(eastTerminals):
            if centerSingleEastPair:
                lineOffset = eastSignalOffset if i == 0 else eastReturnOffset
            else:
                lineOffset = bodyStart + i
            terminalOffsetsMutable.append(
                ChipTerminalLineOffset(
                    chipTerminalRef=ChipTerminalRef(
                        chipRef=chip.chipRef_build(),
                        terminalSide=ChipTerminalSide.EAST,
                        terminalName=terminalName,
                    ),
                    lineOffset=lineOffset,
                )
            )

    return resultOk_build(
        ChipLocalGeometry(
            owningChipLocalRoutingOwner=ChipLocalRoutingOwner(
                chipRef=chip.chipRef_build()
            ),
            lineCount=lineCount,
            lineWidth=lineWidth,
            boxTopLineOffset=boxTopLineOffsetResult.value,
            boxBottomLineOffset=boxBottomLineOffsetResult.value,
            boxLeftColumnOffset=boxLeftColumnOffsetResult.value,
            boxRightColumnOffset=boxRightColumnOffsetResult.value,
            terminalLineOffsets=tuple(terminalOffsetsMutable),
        )
    )


def chipLocalGeometrySetResult_buildFromChips(
    chips: tuple[Chip, ...],
) -> Result[ChipLocalGeometrySet]:
    """Build local geometry for every chip in a collection.

    Args:
        chips: All chips to derive geometry from.

    Returns:
        Successful result containing `ChipLocalGeometrySet`, or a failed result
        if any chip's geometry cannot be computed.
    """

    geometriesMutable: list[ChipLocalGeometry] = []
    for chip in chips:
        geoResult: Result[ChipLocalGeometry] = chipLocalGeometryResult_build(chip)
        if not result_isOkCheck(geoResult):
            return resultErr_build()
        geometriesMutable.append(geoResult.value)

    return resultOk_build(
        ChipLocalGeometrySet(chipLocalGeometries=tuple(geometriesMutable))
    )


def chipCanvasPlacementGeometry_build(
    chipLocalGeometry: ChipLocalGeometry,
    routingZoneSense: RoutingZoneSense,
    regionSide: RoutingZoneRegionSide,
    terminalRegionVerticalStart: int,
    terminalRegionHorizontalStart: int,
    stackOffset: int,
) -> ChipCanvasPlacementGeometry:
    """Return draw-origin and box-origin world coordinates for one placed chip."""

    if routingZoneSense is RoutingZoneSense.WEST_TO_EAST or regionSide in {
        RoutingZoneRegionSide.WEST,
        RoutingZoneRegionSide.EAST,
    }:
        boxWorldRow: int = terminalRegionVerticalStart + stackOffset + 1
        boxWorldColumn: int = terminalRegionHorizontalStart
    else:
        boxWorldRow = terminalRegionVerticalStart
        boxWorldColumn = terminalRegionHorizontalStart + stackOffset + 1

    return ChipCanvasPlacementGeometry(
        drawWorldRow=boxWorldRow - chipLocalGeometry.boxTopLineOffset,
        drawWorldColumn=boxWorldColumn - chipLocalGeometry.boxLeftColumnOffset,
        boxWorldRow=boxWorldRow,
        boxWorldColumn=boxWorldColumn,
    )


def _boxTopLineOffsetResult_build(
    lines: tuple[str, ...],
) -> Result[int]:
    """Return the row offset of the actual top box border."""

    rowIndex: int
    line: str
    for rowIndex, line in enumerate(lines):
        if "┌" in line and "┐" in line:
            return resultOk_build(rowIndex)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.geometry.chip_local.missing_box_top",
        message="ChipLocalGeometry could not find the top box border",
    )
    return resultErr_build()


def _boxBottomLineOffsetResult_build(
    lines: tuple[str, ...],
) -> Result[int]:
    """Return the row offset of the actual bottom box border."""

    rowIndex: int
    for rowIndex in range(len(lines) - 1, -1, -1):
        line = lines[rowIndex]
        if "└" in line and "┘" in line:
            return resultOk_build(rowIndex)
    diagnosticStack.error_push(
        phase=DiagnosticPhase.ROUTING,
        code="routing.geometry.chip_local.missing_box_bottom",
        message="ChipLocalGeometry could not find the bottom box border",
    )
    return resultErr_build()


def _boxLeftColumnOffsetResult_build(
    lines: tuple[str, ...],
) -> Result[int]:
    """Return the column offset of the actual west box wall."""

    topRowResult = _boxTopLineOffsetResult_build(lines)
    if not result_isOkCheck(topRowResult):
        return resultErr_build()
    line: str = lines[topRowResult.value]
    return resultOk_build(line.index("┌"))


def _boxRightColumnOffsetResult_build(
    lines: tuple[str, ...],
) -> Result[int]:
    """Return the column offset of the actual east box wall."""

    topRowResult = _boxTopLineOffsetResult_build(lines)
    if not result_isOkCheck(topRowResult):
        return resultErr_build()
    line: str = lines[topRowResult.value]
    return resultOk_build(line.rindex("┐"))
