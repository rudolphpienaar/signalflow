"""Validated circuit models for new-engine ingress.

This module defines the validated circuit graph consumed by the new SignalFlow
engine after YAML source has been normalized. Chips are canonical graph nodes,
and call relationships are explicit ordered edges between those canonical
chips.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.models.chip import Chip, ChipId, ChipPortDeclaration, ChipRef
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)


@dataclass(frozen=True)
class CircuitCall:
    """One ordered call edge between two canonical chips."""

    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    callIndex: int
    sourcePortDeclaration: ChipPortDeclaration | None = None


@dataclass(frozen=True)
class CircuitCallSet:
    """Modeled collection of ordered call edges for one circuit."""

    circuitCalls: tuple[CircuitCall, ...] = field(default_factory=tuple)

    def outgoingCallsForChip_get(
        self,
        chipId: ChipId,
    ) -> tuple[CircuitCall, ...]:
        """Return all ordered outgoing calls for one chip."""

        return tuple(
            circuitCall
            for circuitCall in self.circuitCalls
            if circuitCall.sourceChipRef.chipId == chipId
        )

    def incomingCallsForChip_get(
        self,
        chipId: ChipId,
    ) -> tuple[CircuitCall, ...]:
        """Return all incoming calls for one chip."""

        return tuple(
            circuitCall
            for circuitCall in self.circuitCalls
            if circuitCall.destinationChipRef.chipId == chipId
        )


@dataclass(frozen=True)
class CircuitChipSet:
    """Modeled collection of canonical chips for one circuit document."""

    chips: tuple[Chip, ...] = field(default_factory=tuple)

    def chipResult_get(self, chipId: ChipId) -> Result[Chip]:
        """Get one chip by id from this circuit chip set."""

        chip: Chip
        for chip in self.chips:
            if chip.chipId == chipId:
                return resultOk_build(chip)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="circuit.chip_set.missing_chip",
            message="Requested Chip is absent from the CircuitChipSet",
        )
        return resultErr_build()


@dataclass(frozen=True)
class CircuitDocument:
    """Validated top-level circuit document for the new engine."""

    title: str
    rootChipRef: ChipRef
    circuitChipSet: CircuitChipSet = field(default_factory=CircuitChipSet)
    circuitCallSet: CircuitCallSet = field(default_factory=CircuitCallSet)

    def rootChipResult_get(self) -> Result[Chip]:
        """Get the canonical root chip for this circuit document."""

        return self.circuitChipSet.chipResult_get(self.rootChipRef.chipId)

    def callingDepth_calculate(self) -> int:
        """Calculate the longest acyclic call depth rooted at the root chip."""

        if not self.circuitChipSet.chips:
            return 0
        return _chipDepth_calculate(
            chipId=self.rootChipRef.chipId,
            circuitCallSet=self.circuitCallSet,
            pathChipIds=frozenset(),
            memoMutable={},
        )


def circuitCallSetResult_build(
    circuitCalls: tuple[CircuitCall, ...],
) -> Result[CircuitCallSet]:
    """Build a validated circuit-call set."""

    callKeys: tuple[tuple[ChipId, int], ...] = tuple(
        (circuitCall.sourceChipRef.chipId, circuitCall.callIndex)
        for circuitCall in circuitCalls
    )
    if len(set(callKeys)) != len(callKeys):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="circuit.call_set.duplicate_source_call_index",
            message="Circuit call indices must be unique per source chip",
        )
        return resultErr_build()
    return resultOk_build(CircuitCallSet(circuitCalls=circuitCalls))


def circuitChipSetResult_build(chips: tuple[Chip, ...]) -> Result[CircuitChipSet]:
    """Build a validated circuit chip set."""

    chipIds: tuple[ChipId, ...] = tuple(chip.chipId for chip in chips)
    if len(set(chipIds)) != len(chipIds):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="circuit.chip_set.duplicate_chip_id",
            message="Circuit chip ids must be unique within one document",
        )
        return resultErr_build()
    return resultOk_build(CircuitChipSet(chips=chips))


def circuitDocumentResult_build(
    title: str,
    rootChipRef: ChipRef,
    circuitChipSet: CircuitChipSet,
    circuitCallSet: CircuitCallSet,
) -> Result[CircuitDocument]:
    """Build a validated circuit document from canonical chips and calls."""

    rootChipResult = circuitChipSet.chipResult_get(rootChipRef.chipId)
    if not result_isOkCheck(rootChipResult):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="circuit.document.missing_root_chip",
            message="CircuitDocument root chip must be present in the chip set",
        )
        return resultErr_build()
    return resultOk_build(
        CircuitDocument(
            title=title,
            rootChipRef=rootChipRef,
            circuitChipSet=circuitChipSet,
            circuitCallSet=circuitCallSet,
        )
    )


def _chipDepth_calculate(
    chipId: ChipId,
    circuitCallSet: CircuitCallSet,
    pathChipIds: frozenset[ChipId],
    memoMutable: dict[ChipId, int],
) -> int:
    """Calculate longest acyclic depth from one canonical chip."""

    if chipId in memoMutable:
        return memoMutable[chipId]
    if chipId in pathChipIds:
        return 0

    outgoingCalls: tuple[CircuitCall, ...] = circuitCallSet.outgoingCallsForChip_get(
        chipId
    )
    if not outgoingCalls:
        memoMutable[chipId] = 1
        return 1

    childDepth: int = max(
        _chipDepth_calculate(
            chipId=circuitCall.destinationChipRef.chipId,
            circuitCallSet=circuitCallSet,
            pathChipIds=pathChipIds | {chipId},
            memoMutable=memoMutable,
        )
        for circuitCall in outgoingCalls
    )
    memoMutable[chipId] = 1 + childDepth
    return memoMutable[chipId]
