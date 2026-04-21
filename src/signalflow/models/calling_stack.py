"""Calling-stack models derived from the canonical circuit graph.

This module gives routing a first-class view of call depth so that route
semantics come from the call tree rather than from later placement geometry.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from signalflow.models.chip import ChipRef
from signalflow.models.circuit import CircuitCall, CircuitDocument
from signalflow.models.result import Result, resultOk_build


@dataclass(frozen=True)
class CallingLevel:
    """One ordered depth band of chip references.

    Attributes:
        depthIndex: Zero-based call depth for this band.
        chipRefs: Ordered chip occurrences assigned to this depth.
    """

    depthIndex: int
    chipRefs: tuple[ChipRef, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CallingStack:
    """Depth-indexed view of the canonical circuit call graph.

    Attributes:
        levels: Ordered depth bands from root to deepest reachable level.
        depthByChipRef: Lookup table from chip occurrence to assigned depth.
    """

    levels: tuple[CallingLevel, ...] = field(default_factory=tuple)
    depthByChipRef: dict[ChipRef, int] = field(default_factory=dict)

    def depthForChipOrNone_get(self, chipRef: ChipRef) -> int | None:
        """Return the assigned depth for one chip when present.

        Args:
            chipRef: Chip occurrence to look up.

        Returns:
            The chip's assigned depth, or `None` when absent.
        """

        return self.depthByChipRef.get(chipRef)

    def deltaOrNone_get(
        self,
        sourceChipRef: ChipRef,
        destinationChipRef: ChipRef,
    ) -> int | None:
        """Return destination depth minus source depth when both are known.

        Args:
            sourceChipRef: Route source chip occurrence.
            destinationChipRef: Route destination chip occurrence.

        Returns:
            Depth delta `destination - source`, or `None` when either chip is
            absent from this stack.
        """

        sourceDepth: int | None = self.depthForChipOrNone_get(sourceChipRef)
        destinationDepth: int | None = self.depthForChipOrNone_get(
            destinationChipRef
        )
        if sourceDepth is None or destinationDepth is None:
            return None
        return destinationDepth - sourceDepth


def callingStackResult_buildFromCircuitDocument(
    circuitDocument: CircuitDocument,
) -> Result[CallingStack]:
    """Build a breadth-first calling stack from the circuit document root.

    Args:
        circuitDocument: Canonical circuit graph to project into depth bands.

    Returns:
        Successful result containing the built `CallingStack`.
    """

    rootChipRef: ChipRef = circuitDocument.rootChipRef
    queueMutable: deque[tuple[ChipRef, int]] = deque(((rootChipRef, 0),))
    depthByChipRefMutable: dict[ChipRef, int] = {rootChipRef: 0}
    chipRefsByDepthMutable: dict[int, list[ChipRef]] = {0: [rootChipRef]}

    while queueMutable:
        chipRef, depthIndex = queueMutable.popleft()
        outgoingCall = None
        outgoingCalls: tuple[CircuitCall, ...] = (
            circuitDocument.circuitCallSet.outgoingCallsForChip_get(
                chipRef.chipId
            )
        )
        for outgoingCall in outgoingCalls:
            destinationChipRef: ChipRef = outgoingCall.destinationChipRef
            if destinationChipRef in depthByChipRefMutable:
                continue
            destinationDepth: int = depthIndex + 1
            depthByChipRefMutable[destinationChipRef] = destinationDepth
            chipRefsByDepthMutable.setdefault(destinationDepth, []).append(
                destinationChipRef
            )
            queueMutable.append((destinationChipRef, destinationDepth))

    levels: tuple[CallingLevel, ...] = tuple(
        CallingLevel(
            depthIndex=depthIndex,
            chipRefs=tuple(chipRefsByDepthMutable[depthIndex]),
        )
        for depthIndex in sorted(chipRefsByDepthMutable)
    )
    return resultOk_build(
        CallingStack(
            levels=levels,
            depthByChipRef=dict(depthByChipRefMutable),
        )
    )
