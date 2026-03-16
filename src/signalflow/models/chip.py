"""First-class chip models for SignalFlow.

This module defines the first-class chip vocabulary used by the new
`RoutingZoneGrid` architecture. Chips own identity, declared chip-local
interface, declarative internal wiring, and optional per-chip io overrides.
They do not own world placement.

Key components:
    - ChipTerminalSide: Cardinal side for one chip terminal
    - ChipId: Stable chip identity
    - ChipPortDeclaration: One declared chip-local port record
    - ChipInternalWiringDirective: One declared internal wiring statement
    - ChipTerminal: One named terminal on one chip side
    - Chip: First-class chip specification
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import Result, resultErr_build, resultOk_build


class ChipTerminalSide(Enum):
    """Cardinal side for one chip terminal.

    Attributes:
        WEST: Terminal on the west side of the chip.
        EAST: Terminal on the east side of the chip.
        NORTH: Terminal on the north side of the chip.
        SOUTH: Terminal on the south side of the chip.
    """

    WEST = "west"
    EAST = "east"
    NORTH = "north"
    SOUTH = "south"


@dataclass(frozen=True)
class ChipId:
    """Stable identity for one chip.

    Attributes:
        moduleName: Module or file that owns the chip.
        functionName: Function or chip label.
    """

    moduleName: str
    functionName: str


@dataclass(frozen=True)
class ChipRef:
    """Lightweight reference to one chip.

    Attributes:
        chipId: Stable identity of the referenced chip.
    """

    chipId: ChipId


@dataclass(frozen=True)
class ChipPortDeclaration:
    """One declared chip-local port record.

    A port declaration mirrors the YAML port object shape. The declaration does
    not itself imply a terminal side. Terminal synthesis is a later modeling
    step that may interpret the forward and return labels differently depending
    on whether the declaration came from an input or output port set.

    Attributes:
        signalName: Forward-call label, when declared.
        returnName: Return-path label, when declared.
    """

    signalName: str | None = None
    returnName: str | None = None

    def names_getAll(self) -> tuple[str, ...]:
        """Return all declared names in stable order."""

        namesMutable: list[str] = []
        if self.signalName is not None:
            namesMutable.append(self.signalName)
        if self.returnName is not None:
            namesMutable.append(self.returnName)
        return tuple(namesMutable)


@dataclass(frozen=True)
class ChipPortDeclarationSet:
    """Modeled collection of declared chip-local port records."""

    portDeclarations: tuple[ChipPortDeclaration, ...] = field(default_factory=tuple)

    def declaredNames_getAll(self) -> tuple[str, ...]:
        """Return all declared port names in stable declaration order."""

        namesMutable: list[str] = []
        portDeclaration: ChipPortDeclaration
        for portDeclaration in self.portDeclarations:
            namesMutable.extend(portDeclaration.names_getAll())
        return tuple(namesMutable)


@dataclass(frozen=True)
class ChipInternalWiringDirective:
    """One declarative internal wiring statement."""

    wiringDeclaration: str


@dataclass(frozen=True)
class ChipInternalWiringDirectiveSet:
    """Modeled collection of declarative internal wiring statements."""

    directives: tuple[ChipInternalWiringDirective, ...] = field(
        default_factory=tuple
    )

    def directives_has(self) -> bool:
        """Return whether this chip declares any internal wiring."""

        return bool(self.directives)


@dataclass(frozen=True)
class ChipIoInput:
    """Per-chip input-io override block."""

    explicit: bool | None = None


@dataclass(frozen=True)
class ChipIoInternalWiring:
    """Per-chip internal-wiring display override block."""

    colorize: bool | None = None
    showInternalLabels: bool | None = None
    aliasInternalLabels: bool | None = None


@dataclass(frozen=True)
class ChipIo:
    """Modeled per-chip io override block."""

    chipIoInput: ChipIoInput = field(default_factory=ChipIoInput)
    chipIoInternalWiring: ChipIoInternalWiring = field(
        default_factory=ChipIoInternalWiring
    )


@dataclass(frozen=True)
class ChipTerminal:
    """One named terminal on one side of a chip.

    Attributes:
        terminalName: Stable terminal label on the chip.
        terminalSide: Side on which the terminal is exposed.
    """

    terminalName: str
    terminalSide: ChipTerminalSide


@dataclass(frozen=True)
class ChipTerminalSet:
    """Modeled collection of chip terminals.

    Attributes:
        terminals: Ordered chip terminals for one chip.
    """

    terminals: tuple[ChipTerminal, ...] = field(default_factory=tuple)

    def terminalForNameAndSideResult_get(
        self,
        terminalName: str,
        terminalSide: ChipTerminalSide,
    ) -> Result[ChipTerminal]:
        """Get one terminal by name and side.

        Args:
            terminalName: Stable terminal label to retrieve.
            terminalSide: Side on which the terminal must be exposed.

        Returns:
            Successful result containing the matching `ChipTerminal`, otherwise
            failed result with validation diagnostics.
        """

        chipTerminal: ChipTerminal
        for chipTerminal in self.terminals:
            if (
                chipTerminal.terminalName == terminalName
                and chipTerminal.terminalSide is terminalSide
            ):
                return resultOk_build(chipTerminal)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="chip.terminal_set.missing_terminal_key",
            message="Requested ChipTerminal is absent from the ChipTerminalSet",
            context=(terminalName, terminalSide.value),
        )
        return resultErr_build()

    def terminalsOnSide_build(
        self, terminalSide: ChipTerminalSide
    ) -> ChipTerminalSet:
        """Build a filtered terminal set for one chip side.

        Args:
            terminalSide: Side to filter by.

        Returns:
            `ChipTerminalSet` containing only terminals on the requested side.
        """

        return ChipTerminalSet(
            terminals=tuple(
                chipTerminal
                for chipTerminal in self.terminals
                if chipTerminal.terminalSide is terminalSide
            )
        )


@dataclass(frozen=True)
class Chip:
    """First-class chip specification.

    Attributes:
        chipId: Stable identity for the chip.
        chipTerminalSet: Declared terminals exposed by the chip.
        inputPortDeclarationSet: Declared input-port records on the chip.
        outputPortDeclarationSet: Declared output-port records on the chip.
        internalWiringDirectiveSet: Declarative internal-wiring statements.
        chipIo: Per-chip io override block.
        internalRoutingDeclared: Whether the chip declares chip-local routing.
    """

    chipId: ChipId
    chipTerminalSet: ChipTerminalSet = field(default_factory=ChipTerminalSet)
    inputPortDeclarationSet: ChipPortDeclarationSet = field(
        default_factory=ChipPortDeclarationSet
    )
    outputPortDeclarationSet: ChipPortDeclarationSet = field(
        default_factory=ChipPortDeclarationSet
    )
    internalWiringDirectiveSet: ChipInternalWiringDirectiveSet = field(
        default_factory=ChipInternalWiringDirectiveSet
    )
    chipIo: ChipIo = field(default_factory=ChipIo)
    internalRoutingDeclared: bool = False

    def chipRef_build(self) -> ChipRef:
        """Build a lightweight reference to this chip.

        Returns:
            `ChipRef` pointing at this chip.
        """

        return ChipRef(chipId=self.chipId)


def chipTerminalSetResult_build(
    terminals: tuple[ChipTerminal, ...],
) -> Result[ChipTerminalSet]:
    """Build a validated chip-terminal set.

    Args:
        terminals: Ordered chip terminals for one chip.

    Returns:
        Successful result containing `ChipTerminalSet`, otherwise failed result
        with validation diagnostics.
    """

    terminalKeys: tuple[tuple[str, ChipTerminalSide], ...] = tuple(
        (chipTerminal.terminalName, chipTerminal.terminalSide)
        for chipTerminal in terminals
    )
    if len(set(terminalKeys)) != len(terminalKeys):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="chip.terminal_set.duplicate_terminal_key",
            message="Chip terminal name/side pairs must be unique",
        )
        return resultErr_build()
    return resultOk_build(ChipTerminalSet(terminals=terminals))


def chipPortDeclarationResult_build(
    signalName: str | None = None,
    returnName: str | None = None,
) -> Result[ChipPortDeclaration]:
    """Build one validated chip-port declaration.

    Returns:
        Successful result containing `ChipPortDeclaration`, otherwise failed
        result with validation diagnostics.
    """

    if signalName is None and returnName is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="chip.port_declaration.empty",
            message=(
                "ChipPortDeclaration must declare at least one of signalName "
                "or returnName"
            ),
        )
        return resultErr_build()
    return resultOk_build(
        ChipPortDeclaration(signalName=signalName, returnName=returnName)
    )


def chipPortDeclarationSetResult_build(
    portDeclarations: tuple[ChipPortDeclaration, ...],
) -> Result[ChipPortDeclarationSet]:
    """Build a validated chip-port declaration set."""

    return resultOk_build(ChipPortDeclarationSet(portDeclarations=portDeclarations))


def chipInternalWiringDirectiveResult_build(
    wiringDeclaration: str,
) -> Result[ChipInternalWiringDirective]:
    """Build one validated chip internal-wiring directive."""

    if not wiringDeclaration:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="chip.internal_wiring.empty_directive",
            message="Chip internal wiring directives must be non-empty strings",
        )
        return resultErr_build()
    return resultOk_build(
        ChipInternalWiringDirective(wiringDeclaration=wiringDeclaration)
    )


def chipInternalWiringDirectiveSetResult_build(
    directives: tuple[ChipInternalWiringDirective, ...],
) -> Result[ChipInternalWiringDirectiveSet]:
    """Build a validated internal-wiring directive set."""

    return resultOk_build(ChipInternalWiringDirectiveSet(directives=directives))


def chipResult_build(
    chipId: ChipId,
    chipTerminalSet: ChipTerminalSet | None = None,
    inputPortDeclarationSet: ChipPortDeclarationSet | None = None,
    outputPortDeclarationSet: ChipPortDeclarationSet | None = None,
    internalWiringDirectiveSet: ChipInternalWiringDirectiveSet | None = None,
    chipIo: ChipIo | None = None,
) -> Result[Chip]:
    """Build a validated first-class chip."""

    resolvedInternalWiringDirectiveSet: ChipInternalWiringDirectiveSet = (
        internalWiringDirectiveSet or ChipInternalWiringDirectiveSet()
    )
    return resultOk_build(
        Chip(
            chipId=chipId,
            chipTerminalSet=chipTerminalSet or ChipTerminalSet(),
            inputPortDeclarationSet=(
                inputPortDeclarationSet or ChipPortDeclarationSet()
            ),
            outputPortDeclarationSet=(
                outputPortDeclarationSet or ChipPortDeclarationSet()
            ),
            internalWiringDirectiveSet=resolvedInternalWiringDirectiveSet,
            chipIo=chipIo or ChipIo(),
            internalRoutingDeclared=(
                resolvedInternalWiringDirectiveSet.directives_has()
            ),
        )
    )
