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
    ChipRef,
    ChipTerminalSide,
    Result,
    chipDrawLines_build,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack


@dataclass(frozen=True)
class ChipTerminalLineOffset:
    """Row offset within one chip's own drawn block for one terminal.

    Attributes:
        terminalSide: Side on which the terminal lives.
        terminalName: Stable label for the terminal.
        lineOffset: 0-indexed line within the chip's own line block where
            the terminal's wire stub appears in `chipDrawLines_build` output.
    """

    terminalSide: ChipTerminalSide
    terminalName: str
    lineOffset: int


@dataclass(frozen=True)
class ChipLocalGeometry:
    """Local geometry for one chip as drawn in its terminal region.

    Attributes:
        chipRef: Stable reference to the chip this geometry describes.
        lineCount: Total lines produced by `chipDrawLines_build` for this chip.
        lineWidth: Width of the widest line in the chip's drawing.
        terminalLineOffsets: Row offsets within the chip's block for each terminal.
    """

    chipRef: ChipRef
    lineCount: int
    lineWidth: int
    terminalLineOffsets: tuple[ChipTerminalLineOffset, ...] = field(
        default_factory=tuple
    )

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

    northCount: int = sum(
        1
        for t in chip.chipTerminalSet.terminals
        if t.terminalSide is ChipTerminalSide.NORTH
    )

    hasTerminals: bool = bool(chip.chipTerminalSet.terminals)

    terminalOffsetsMutable: list[ChipTerminalLineOffset] = []

    if hasTerminals:
        bodyStart: int = northCount + 3  # top-border + title-row + separator

        westTerminals: tuple[str, ...] = tuple(
            t.terminalName
            for t in chip.chipTerminalSet.terminals
            if t.terminalSide is ChipTerminalSide.WEST
        )
        eastTerminals: tuple[str, ...] = tuple(
            t.terminalName
            for t in chip.chipTerminalSet.terminals
            if t.terminalSide is ChipTerminalSide.EAST
        )

        for i, terminalName in enumerate(westTerminals):
            terminalOffsetsMutable.append(
                ChipTerminalLineOffset(
                    terminalSide=ChipTerminalSide.WEST,
                    terminalName=terminalName,
                    lineOffset=bodyStart + i,
                )
            )

        for i, terminalName in enumerate(eastTerminals):
            terminalOffsetsMutable.append(
                ChipTerminalLineOffset(
                    terminalSide=ChipTerminalSide.EAST,
                    terminalName=terminalName,
                    lineOffset=bodyStart + i,
                )
            )

    return resultOk_build(
        ChipLocalGeometry(
            chipRef=chip.chipRef_build(),
            lineCount=lineCount,
            lineWidth=lineWidth,
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
