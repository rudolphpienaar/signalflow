"""Chip-local harmonization into a board-compatible schema.

This module does not solve chip-internal geometry directly. It normalizes a
chip's declared `internal_wiring` into a tiny synthetic external-style
document, then reuses the normal circuit/assignment/placement pipeline so the
resulting internal board can be built through `board_buildFromKernel(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.board.types import BoardSense, YamlDocument
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipRef,
    CircuitDocument,
    GridCoord,
    RoutingKernel,
    RoutingZone,
    RoutingZoneGrid,
    RoutingZoneId,
    RoutingZoneSense,
    result_isOkCheck,
    routingZoneGridResult_build,
    routingZoneResult_build,
    routingZoneSetResult_build,
)
from signalflow.models.chip import (
    Chip,
    ChipInternalWiringDirective,
    ChipPortDeclaration,
)
from signalflow.routing.assignment import (
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
)
from signalflow.routing.placement import (
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
)


@dataclass(frozen=True)
class ChipInternalBoardWire:
    """One normalized chip-local wiring obligation."""

    wiringDeclaration: str
    sourceTerminalName: str
    destinationTerminalName: str


@dataclass(frozen=True)
class ChipInternalBoardSchema:
    """Board-compatible schema derived from one chip-local routing declaration."""

    chipTitle: str
    sense: BoardSense
    westTerminalNames: tuple[str, ...] = field(default_factory=tuple)
    eastTerminalNames: tuple[str, ...] = field(default_factory=tuple)
    wires: tuple[ChipInternalBoardWire, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ChipInternalSyntheticCall:
    """One synthetic external-style call used to model internal wiring."""

    westSignalName: str | None
    westReturnName: str | None
    eastSignalName: str | None
    eastReturnName: str | None
    eastFunctionName: str


@dataclass(frozen=True)
class ChipInternalPlacedKernelArtifacts:
    """Upstream-harmonized chip-internal kernel inputs.

    These artifacts are deliberately shaped to match the existing external
    zone path: a real `CircuitDocument`, a real placed `RoutingZone`, and the
    placed `intra` `RoutingKernel` extracted from that zone.
    """

    schema: ChipInternalBoardSchema
    syntheticDocumentDict: YamlDocument
    circuitDocument: CircuitDocument
    routingZoneGrid: RoutingZoneGrid
    routingZone: RoutingZone
    kernel: RoutingKernel
    westChipRef: ChipRef
    syntheticCalls: tuple[ChipInternalSyntheticCall, ...]


def chipInternalBoardSchema_build(chip: Chip) -> ChipInternalBoardSchema:
    """Build a board-compatible chip-local schema from one canonical chip."""

    wiresMutable: list[ChipInternalBoardWire] = []
    westTerminalNamesMutable: list[str] = []
    eastTerminalNamesMutable: list[str] = []
    for directive in chip.internalWiringDirectiveSet.directives:
        sourceTerminalName, destinationTerminalName, *_ = (
            directive.wiringDeclaration.split(":")
        )
        if sourceTerminalName not in westTerminalNamesMutable:
            westTerminalNamesMutable.append(sourceTerminalName)
        if destinationTerminalName not in eastTerminalNamesMutable:
            eastTerminalNamesMutable.append(destinationTerminalName)
        wiresMutable.append(
            ChipInternalBoardWire(
                wiringDeclaration=directive.wiringDeclaration,
                sourceTerminalName=sourceTerminalName,
                destinationTerminalName=destinationTerminalName,
            )
        )
    return ChipInternalBoardSchema(
        chipTitle=f"{chip.chipId.moduleName}.{chip.chipId.functionName}",
        sense=BoardSense.WEST_TO_EAST,
        westTerminalNames=tuple(westTerminalNamesMutable),
        eastTerminalNames=tuple(eastTerminalNamesMutable),
        wires=tuple(wiresMutable),
    )


def chipInternalPlacedKernelArtifacts_build(
    chip: Chip,
    *,
    moduleBoundaryPaddingCells: int = 3,
) -> ChipInternalPlacedKernelArtifacts:
    """Build a real placed synthetic kernel for one chip's internal wiring.

    The harmonization happens entirely upstream:
    - convert chip-local internal wiring into a synthetic external-style document
    - run that document through the normal circuit/assignment/placement path
    - extract the placed `intra` kernel for `board_buildFromKernel(...)`
    """

    schema = chipInternalBoardSchema_build(chip)
    syntheticDocumentDict = _chipInternalDocumentDict_build(
        chip=chip,
        schema=schema,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
    )
    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
        syntheticDocumentDict
    )
    if not result_isOkCheck(circuitDocumentResult):
        raise RuntimeError(
            "Could not build synthetic circuit document for chip internal board"
        )
    circuitDocument = circuitDocumentResult.value

    routingZoneId = RoutingZoneId(id=GridCoord(columnIndex=1, rowIndex=1))
    emptyZoneResult = routingZoneResult_build(
        routingZoneId=routingZoneId,
        routingZoneSense=RoutingZoneSense.WEST_TO_EAST,
    )
    if not result_isOkCheck(emptyZoneResult):
        raise RuntimeError("Could not build synthetic routing zone")
    routingZoneSetResult = routingZoneSetResult_build((emptyZoneResult.value,))
    if not result_isOkCheck(routingZoneSetResult):
        raise RuntimeError("Could not build synthetic routing-zone set")
    routingZoneGridResult = routingZoneGridResult_build(
        worldSense=RoutingZoneSense.WEST_TO_EAST,
        gridSize=GridCoord(columnIndex=1, rowIndex=1),
        routingZoneSet=routingZoneSetResult.value,
        moduleBoxPadding=moduleBoundaryPaddingCells,
    )
    if not result_isOkCheck(routingZoneGridResult):
        raise RuntimeError("Could not build synthetic routing-zone grid")
    routingZoneGrid = routingZoneGridResult.value

    assignmentSetResult = (
        routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
            circuitDocument,
            routingZoneGrid,
        )
    )
    if not result_isOkCheck(assignmentSetResult):
        raise RuntimeError(
            "Could not assign synthetic chips into routing zone"
        )

    placedGridResult = (
        routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
            assignmentSetResult.value,
            routingZoneGrid,
            circuitDocument,
        )
    )
    if not result_isOkCheck(placedGridResult):
        raise RuntimeError("Could not place synthetic chips into routing zone")
    placedGrid = placedGridResult.value

    placedZoneResult = placedGrid.routingZoneSet.zoneResult_get(routingZoneId)
    if not result_isOkCheck(placedZoneResult):
        raise RuntimeError("Could not recover placed synthetic routing zone")
    placedZone = placedZoneResult.value
    if placedZone.intraKernel is None:
        raise RuntimeError("Synthetic placed routing zone has no intra kernel")

    westChipRef = circuitDocument.rootChipRef

    return ChipInternalPlacedKernelArtifacts(
        schema=schema,
        syntheticDocumentDict=syntheticDocumentDict,
        circuitDocument=circuitDocument,
        routingZoneGrid=placedGrid,
        routingZone=placedZone,
        kernel=placedZone.intraKernel,
        westChipRef=westChipRef,
        syntheticCalls=_chipInternalSyntheticCalls_build(chip),
    )


def _chipInternalDocumentDict_build(
    *,
    chip: Chip,
    schema: ChipInternalBoardSchema,
    moduleBoundaryPaddingCells: int,
) -> YamlDocument:
    """Build a synthetic external-style document for one internal board."""

    syntheticCalls = _chipInternalSyntheticCalls_build(chip)
    if not syntheticCalls:
        raise RuntimeError(
            "Chip internal board has no representable synthetic calls"
        )
    westModuleName = "InternalWest.ts"
    westPortObject = _portObject_build(
        signalName=syntheticCalls[0].westSignalName,
        returnName=syntheticCalls[0].westReturnName,
    )
    callObjects: list[dict[str, object]] = []
    syntheticCall: ChipInternalSyntheticCall
    for syntheticCall in syntheticCalls:
        callObjects.append(
            {
                "module": "InternalEast.ts",
                "func": syntheticCall.eastFunctionName,
                "bind_output": _portObject_build(
                    signalName=syntheticCall.westSignalName,
                    returnName=syntheticCall.westReturnName,
                ),
                "input_ports": [
                    _portObject_build(
                        signalName=syntheticCall.eastSignalName,
                        returnName=syntheticCall.eastReturnName,
                    )
                ],
            }
        )
    return {
        "title": f"{chip.chipId.moduleName}.{chip.chipId.functionName} internal board",
        "world": {
            "sense": "west_to_east",
            "occupancy_policy": "strip",
            "packing_policy": "monotone",
            "module_box_padding": moduleBoundaryPaddingCells,
        },
        "tree": {
            "module": westModuleName,
            "func": _westFunctionName_build(syntheticCalls[0]),
            "output_ports": [
                _portObject_build(
                    signalName=westPortObject.get("signal"),
                    returnName=westPortObject.get("return"),
                )
            ],
            "calls": callObjects,
        },
    }


def _chipInternalSyntheticCalls_build(
    chip: Chip,
) -> tuple[ChipInternalSyntheticCall, ...]:
    """Build representable synthetic calls for one chip's internal board.

    The current step models the `explicit:false` case that the quarantine work
    is using:
    - one synthetic west chip from the first declared input pair
    - one synthetic east chip per active declared output pair
    - activity is derived from `internal_wiring`
    """

    inputDeclarations = chip.inputPortDeclarationSet.portDeclarations
    if not inputDeclarations:
        return ()
    if chip.chipIo.chipIoInput.explicit not in (False, None):
        raise RuntimeError(
            "chip.internalBoard_get() currently supports only input explicit:false"
        )
    westPortDeclaration = inputDeclarations[0]
    westNames = {
        terminalName
        for terminalName in (
            westPortDeclaration.signalName,
            westPortDeclaration.returnName,
        )
        if terminalName is not None
    }
    directives = chip.internalWiringDirectiveSet.directives
    activeTerminalNames = {
        terminalName
        for directive in directives
        for terminalName in directive.wiringDeclaration.split(":")[:2]
    }
    if not westNames & activeTerminalNames:
        return ()

    syntheticCallsMutable: list[ChipInternalSyntheticCall] = []
    outputDeclaration = None
    for outputDeclaration in chip.outputPortDeclarationSet.portDeclarations:
        eastNames = {
            terminalName
            for terminalName in (
                outputDeclaration.signalName,
                outputDeclaration.returnName,
            )
            if terminalName is not None
        }
        if not eastNames or not (eastNames & activeTerminalNames):
            continue
        if not _eastChipParticipatesWithWest_build(
            directives=directives,
            westNames=westNames,
            eastNames=eastNames,
        ):
            continue
        syntheticCallsMutable.append(
            ChipInternalSyntheticCall(
                westSignalName=westPortDeclaration.signalName,
                westReturnName=westPortDeclaration.returnName,
                eastSignalName=outputDeclaration.signalName,
                eastReturnName=outputDeclaration.returnName,
                eastFunctionName=_eastFunctionName_build(outputDeclaration),
            )
        )
    return tuple(syntheticCallsMutable)


def _eastChipParticipatesWithWest_build(
    *,
    directives: tuple[ChipInternalWiringDirective, ...],
    westNames: set[str],
    eastNames: set[str],
) -> bool:
    """Return whether one east candidate participates in a west/east relation."""

    directive = None
    for directive in directives:
        sourceTerminalName, destinationTerminalName, *_ = (
            directive.wiringDeclaration.split(":")
        )
        if (
            sourceTerminalName in westNames
            and destinationTerminalName in eastNames
        ):
            return True
        if (
            sourceTerminalName in eastNames
            and destinationTerminalName in westNames
        ):
            return True
    return False


def _portObject_build(
    *,
    signalName: str | None,
    returnName: str | None,
) -> dict[str, str]:
    """Build one YAML-style port object from explicit names."""

    portObject: dict[str, str] = {}
    if signalName is not None:
        portObject["signal"] = signalName
    if returnName is not None:
        portObject["return"] = returnName
    return portObject


def _westFunctionName_build(syntheticCall: ChipInternalSyntheticCall) -> str:
    """Build the synthetic west function name from one visible west pair."""

    return _syntheticFunctionName_build(
        signalName=syntheticCall.westSignalName,
        returnName=syntheticCall.westReturnName,
    )


def _eastFunctionName_build(outputDeclaration: ChipPortDeclaration) -> str:
    """Build the synthetic east function name from one output port pair."""

    return _syntheticFunctionName_build(
        signalName=outputDeclaration.signalName,
        returnName=outputDeclaration.returnName,
    )


def _syntheticFunctionName_build(
    *,
    signalName: str | None,
    returnName: str | None,
) -> str:
    """Build a stable synthetic chip function name from one port pair."""

    parts: list[str] = []
    if signalName is not None:
        parts.append(signalName)
    if returnName is not None:
        parts.append(returnName)
    if not parts:
        return "unnamed()"
    return ".".join(parts) + "()"
