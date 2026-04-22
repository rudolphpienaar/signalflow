"""Calling-stack models derived from the canonical circuit graph.

This module gives routing a first-class view of call depth so that route
semantics come from the call tree rather than from later placement geometry.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from signalflow.models.chip import Chip, ChipRef
from signalflow.models.circuit import CircuitCall, CircuitDocument
from signalflow.models.result import Result, resultOk_build


def _chipLabel_build(chipRef: ChipRef) -> str:
    """Build one stable human-readable chip label.

    Args:
        chipRef: Chip occurrence to label.

    Returns:
        Stable `module:function` text for sprint surfaces.
    """

    chipId = chipRef.chipId
    return f"{chipId.moduleName}:{chipId.functionName}"


@dataclass(frozen=True)
class CallingLevel:
    """One ordered depth band of chip references.

    Attributes:
        depthIndex: Zero-based call depth for this band.
        chipRefs: Ordered chip occurrences assigned to this depth.
    """

    depthIndex: int
    chipRefs: tuple[ChipRef, ...] = field(default_factory=tuple)

    def summary_sprint(self) -> str:
        """Return one compact text line for this depth band.

        Returns:
            Text line containing the depth index and ordered chip labels.
        """

        chipLabelsText = ", ".join(
            _chipLabel_build(chipRef) for chipRef in self.chipRefs
        )
        return f"depth {self.depthIndex}: {chipLabelsText}"


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

    def summary_sprint(self) -> str:
        """Return a short summary for this calling stack.

        Returns:
            Header line describing the number of depth bands.
        """

        return f"calling stack: {len(self.levels)} depth bands"

    def bandCount_calculate(self) -> int:
        """Return the number of occupied calling-stack bands.

        Returns:
            Count of ordered calling-stack depth bands.
        """

        return len(self.levels)

    def levels_sprint(self) -> str:
        """Return the ordered depth-band listing for this calling stack.

        Returns:
            Multi-line text with one depth band per line.
        """

        if not self.levels:
            return "calling stack:\n  <none>"
        levelLines = "\n".join(
            f"  {level.summary_sprint()}" for level in self.levels
        )
        return f"calling stack:\n{levelLines}"


def callingStackResult_buildFromCircuitDocument(
    circuitDocument: CircuitDocument,
) -> Result[CallingStack]:
    """Build a breadth-first calling stack from the circuit document root.

    Args:
        circuitDocument: Canonical circuit graph to project into depth bands.

    Returns:
        Successful result containing the built `CallingStack`.
    """

    depthByChipRefMutable: dict[ChipRef, int] = _depthByChipRef_build(
        circuitDocument
    )
    chipRefsByDepthMutable: dict[int, list[ChipRef]] = {}
    chip: Chip
    for chip in circuitDocument.circuitChipSet.chips:
        chipRef = ChipRef(chipId=chip.chipId)
        depthIndex: int | None = depthByChipRefMutable.get(chipRef)
        if depthIndex is None:
            continue
        chipRefsByDepthMutable.setdefault(depthIndex, []).append(chipRef)

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


def _depthByChipRef_build(
    circuitDocument: CircuitDocument,
) -> dict[ChipRef, int]:
    """Build chip depths for the calling stack.

    Args:
        circuitDocument: Canonical circuit graph to project into depth bands.

    Returns:
        Mapping from chip occurrence to assigned calling-stack depth.
    """

    moduleNames: tuple[str, ...] = tuple(
        dict.fromkeys(
            chip.chipId.moduleName
            for chip in circuitDocument.circuitChipSet.chips
        )
    )
    if len(moduleNames) > 1:
        return _moduleBandedDepthByChipRef_build(circuitDocument)
    return _chipBreadthDepthByChipRef_build(circuitDocument)


def _moduleBandedDepthByChipRef_build(
    circuitDocument: CircuitDocument,
) -> dict[ChipRef, int]:
    """Build chip depths from the module-level call graph.

    Args:
        circuitDocument: Canonical circuit graph to project into module bands.

    Returns:
        Mapping from chip occurrence to the depth of its owning module band.
    """

    rootModuleName: str = circuitDocument.rootChipRef.chipId.moduleName
    moduleDepthByNameMutable: dict[str, int] = {rootModuleName: 0}
    frontierMutable: deque[str] = deque((rootModuleName,))

    while frontierMutable:
        sourceModuleName: str = frontierMutable.popleft()
        nextDepth: int = moduleDepthByNameMutable[sourceModuleName] + 1
        circuitCall: CircuitCall
        for circuitCall in circuitDocument.circuitCallSet.circuitCalls:
            if circuitCall.sourceChipRef.chipId.moduleName != sourceModuleName:
                continue
            destinationModuleName: str = (
                circuitCall.destinationChipRef.chipId.moduleName
            )
            if destinationModuleName in moduleDepthByNameMutable:
                continue
            moduleDepthByNameMutable[destinationModuleName] = nextDepth
            frontierMutable.append(destinationModuleName)

    depthByChipRefMutable: dict[ChipRef, int] = {}
    chip: Chip
    for chip in circuitDocument.circuitChipSet.chips:
        depthIndex: int = moduleDepthByNameMutable.get(
            chip.chipId.moduleName,
            0,
        )
        depthByChipRefMutable[ChipRef(chipId=chip.chipId)] = depthIndex
    return depthByChipRefMutable


def _chipBreadthDepthByChipRef_build(
    circuitDocument: CircuitDocument,
) -> dict[ChipRef, int]:
    """Build chip depths from shortest-path graph reachability.

    Args:
        circuitDocument: Canonical circuit graph to project into chip bands.

    Returns:
        Mapping from chip occurrence to assigned shortest-path depth.
    """

    rootChipRef: ChipRef = circuitDocument.rootChipRef
    queueMutable: deque[tuple[ChipRef, int]] = deque(((rootChipRef, 0),))
    depthByChipRefMutable: dict[ChipRef, int] = {rootChipRef: 0}

    while queueMutable:
        chipRef, depthIndex = queueMutable.popleft()
        outgoingCalls: tuple[CircuitCall, ...] = (
            circuitDocument.circuitCallSet.outgoingCallsForChip_get(
                chipRef.chipId
            )
        )
        outgoingCall: CircuitCall
        for outgoingCall in outgoingCalls:
            destinationChipRef: ChipRef = outgoingCall.destinationChipRef
            if destinationChipRef in depthByChipRefMutable:
                continue
            destinationDepth: int = depthIndex + 1
            depthByChipRefMutable[destinationChipRef] = destinationDepth
            queueMutable.append((destinationChipRef, destinationDepth))

    return depthByChipRefMutable
