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

    def terminalsNamed_getAll(
        self,
        terminalName: str,
    ) -> tuple[ChipTerminal, ...]:
        """Return all terminals with one name in stable declaration order."""

        return tuple(
            chipTerminal
            for chipTerminal in self.terminals
            if chipTerminal.terminalName == terminalName
        )

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


def chipDrawLines_build(chip: Chip) -> tuple[str, ...]:
    """Build the canonical text-drawing lines for one chip.

    This is the single source of truth for chip visual geometry. Both the
    interactive debugger and the final circuit renderer must call this function
    so the representation is identical in both contexts.

    Every chip that has declared terminals is drawn as:

        {leftPad}┌──────────┐
        {leftPad}│  func()  │   ← dedicated title header
        {leftPad}├──────────┤   ← separator
          a  ─►┤          ├─► b    ← signal: exits east through T-junction
          ra ◄─┤          ├◄─ rb   ← return: enters from east through T-junction
        {leftPad}└──────────┘

    West side single-thread contract:
      row 0  – forward thread, named with the first west terminal's signal
      row 1  – return thread, labelled with the first input port's returnName

    East arrow direction:
      output_ports signal terminals → outward arrow (─►)
      output_ports return terminals → inward arrow  (◄─)

    T-junction glyphs (┤ / ├) close the visual gap between each stub arrow
    and the box wall.

    A chip with no declared terminals uses a compact three-row title-only form.
    """

    titleText: str = chip.chipId.functionName

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
    northTerminals: tuple[str, ...] = tuple(
        t.terminalName
        for t in chip.chipTerminalSet.terminals
        if t.terminalSide is ChipTerminalSide.NORTH
    )
    southTerminals: tuple[str, ...] = tuple(
        t.terminalName
        for t in chip.chipTerminalSet.terminals
        if t.terminalSide is ChipTerminalSide.SOUTH
    )

    bodyWidth: int = max(len(titleText) + 4, 10)
    topBorder: str = f"┌{'─' * bodyWidth}┐"
    bottomBorder: str = f"└{'─' * bodyWidth}┘"
    titleRow: str = f"│{titleText.center(bodyWidth)}│"
    separatorRow: str = f"├{'─' * bodyWidth}┤"

    hasTerminals: bool = bool(
        westTerminals or eastTerminals or northTerminals or southTerminals
    )

    if not hasTerminals:
        return (topBorder, titleRow, bottomBorder)

    forwardName: str = westTerminals[0] if westTerminals else ""

    returnName: str = ""
    for _portDecl in chip.inputPortDeclarationSet.portDeclarations:
        if _portDecl.returnName is not None:
            returnName = _portDecl.returnName
            break

    westWidth: int = max(len(forwardName), len(returnName))
    leftPad: str = " " * (westWidth + 2) if westTerminals else ""

    # ─► and ◄─ are both 2-char sequences; stubs are westWidth + 2 chars total.
    # Shorter names are padded with ─ so the wire blends seamlessly with the route.
    _wpad = lambda name: "─" * (westWidth - len(name))
    forwardStub: str = f"{_wpad(forwardName)}{forwardName}─►" if forwardName else ""
    if westTerminals:
        returnStub: str = (
            f"{_wpad(returnName)}{returnName}◄─"
            if returnName
            else f"{' ' * (westWidth + 1)}◄"
        )
    else:
        returnStub = ""
    emptyWestStub: str = " " * (westWidth + 2) if westTerminals else ""

    eastWidth: int = max((len(n) for n in eastTerminals), default=0)

    eastReturnNames: frozenset[str] = frozenset(
        portDecl.returnName
        for portDecl in chip.outputPortDeclarationSet.portDeclarations
        if portDecl.returnName is not None
    )

    # Every chip needs at least 2 body rows.  For chips with east terminals,
    # the zone / interconnect solver places each call's return wire at
    # signal_row + 1.  The last call's return row = bodyStart + N, so we
    # need one extra (spare) row beyond N to keep it inside the body.
    # Exception: when the last east terminal is already an explicit inward
    # return (◄─) stub, it occupies the return slot and no spare is needed.
    _needsSpareReturnRow: bool = bool(
        eastTerminals and eastTerminals[-1] not in eastReturnNames
    )
    bodyRows: int = max(
        2 if hasTerminals else 1,
        len(eastTerminals) + (1 if _needsSpareReturnRow else 0),
    )

    lines: list[str] = []
    for northName in northTerminals:
        lines.append(f"{leftPad}{northName.center(bodyWidth + 2)}")
    lines.append(f"{leftPad}{topBorder}")
    lines.append(f"{leftPad}{titleRow}")
    lines.append(f"{leftPad}{separatorRow}")

    # The last body row is a spare return-slot for the last east terminal's
    # return wire.  It carries an inward (◄) stub so the route wire connects
    # visually to the chip body without a gap.
    _spareReturnRow: int = len(eastTerminals) if eastTerminals else -1

    for rowIndex in range(bodyRows):
        if rowIndex == 0 and westTerminals:
            leftStub: str = forwardStub
        elif rowIndex == 1 and westTerminals:
            leftStub = returnStub
        else:
            leftStub = emptyWestStub

        if rowIndex == _spareReturnRow:
            # Spare return slot: inward arrow stub, same width as signal stubs.
            rightStub: str = f"◄─{'─' * eastWidth}"
            eastWall: str = "├"
        else:
            eastName: str = (
                eastTerminals[rowIndex] if rowIndex < len(eastTerminals) else ""
            )
            if eastName:
                _epad: str = "─" * (eastWidth - len(eastName))
                rightStub = (
                    f"◄─{eastName}{_epad}"
                    if eastName in eastReturnNames
                    else f"─►{eastName}{_epad}"
                )
            else:
                rightStub = ""
            eastWall = "├" if rightStub else "│"
        westWall: str = "┤" if leftStub != emptyWestStub else "│"
        lines.append(f"{leftStub}{westWall}{' ' * bodyWidth}{eastWall}{rightStub}")

    lines.append(f"{leftPad}{bottomBorder}")
    for southName in southTerminals:
        lines.append(f"{leftPad}{southName.center(bodyWidth + 2)}")

    return tuple(lines)


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
