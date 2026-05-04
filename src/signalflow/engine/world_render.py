"""World-circuit rendering path for the new engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from signalflow.board import (
    Board,
    BoardGeometry,
    BoardKernel,
    BoardSolver,
    BoardWorldMaterializedSolution,
    BoardZone,
)
from signalflow.board.doctrine import BoardMaterializePolicy
from signalflow.board.geometry.world_resolver import (
    WorldChainResolution,
    WorldGeometryResolver,
)
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.engine.inspect import SignalFlowContext
from signalflow.engine.inspect.zone_local import (
    contextResult_buildFromDocumentAndZone,
)
from signalflow.models import (
    CallingStack,
    CircuitDocument,
    Result,
    callingStackResult_buildFromCircuitDocument,
    result_isOkCheck,
)


class ModulePolicy(StrEnum):
    """Controls how module boundary boxes are rendered."""

    NONE = "none"
    COLUMN = "column"
    CROSS = "cross"


class RoutingPolicy(StrEnum):
    """Controls centroid relaxation during board realization."""

    MANHATTAN = "manhattan"
    PARIS = "paris"
    NONE = "none"


@dataclass(frozen=True)
class WorldRenderOptions:
    """Top-level world render options."""

    zoneSpecs: tuple[tuple[int, int], ...] | None = None
    geometryShow: bool = False
    wiringShow: bool = True
    modulePolicy: ModulePolicy = ModulePolicy.CROSS
    depthBox: bool = False
    routingPolicy: RoutingPolicy = RoutingPolicy.MANHATTAN


@dataclass(frozen=True)
class _WorldRuntimeInputs:
    geometriesByIndex: dict[int, BoardGeometry]
    boardByIndex: dict[int, Board]
    solverByIndex: dict[int, BoardSolver]


def _zoneIndex_get(zoneSpec: tuple[int, int]) -> int:
    """Return overlap-zone index from a zone coordinate."""

    columnIndex, rowIndex = zoneSpec
    return max(columnIndex, rowIndex)


def _requestedIndexes_get(
    zoneSpecs: Sequence[tuple[int, int]] | None,
    activeIndexes: Sequence[int],
) -> list[int]:
    """Return requested indexes, defaulting to all active indexes."""

    if zoneSpecs is None:
        return list(activeIndexes)
    return [_zoneIndex_get(zoneSpec) for zoneSpec in zoneSpecs]


def _requestedIndexes_validate(
    requestedIndexes: Sequence[int],
    activeIndexes: Sequence[int],
) -> list[str]:
    """Return validation errors for requested world-zone indexes."""

    activeSet: set[int] = set(activeIndexes)
    errors: list[str] = []
    for index in requestedIndexes:
        if index not in activeSet:
            errors.append(
                f"zone (1,{index}) is not active; "
                f"active zones: {[(1, active) for active in activeIndexes]}"
            )

    for position in range(len(requestedIndexes) - 1):
        currentIndex: int = requestedIndexes[position]
        nextIndex: int = requestedIndexes[position + 1]
        if currentIndex >= nextIndex:
            errors.append(
                f"zones out of order at position {position + 1}: "
                f"(1,{currentIndex}) then (1,{nextIndex}); must ascend"
            )
        if nextIndex - currentIndex != 1:
            errors.append(
                f"non-sequential zones: (1,{currentIndex}) then "
                f"(1,{nextIndex}); zones must be consecutive"
            )
    return errors


def worldMaterializedSolution_build(
    documentDict: dict[str, object],
) -> BoardWorldMaterializedSolution:
    """Build the fully harmonized, materialized world solution."""

    runtimeInputs: _WorldRuntimeInputs = _worldRuntimeInputs_build(
        documentDict
    )
    resolution: WorldChainResolution = (
        WorldGeometryResolver.harmonized_chain_build(
            runtimeInputs.geometriesByIndex
        )
    )
    return BoardWorldMaterializedSolution.fromResolvedChain_build(
        boardByIndex=runtimeInputs.boardByIndex,
        solverByIndex=runtimeInputs.solverByIndex,
        resolution=resolution,
    )


def worldRenderLines_build(
    title: str,
    documentDict: dict[str, object],
    options: WorldRenderOptions | None = None,
) -> list[str]:
    """Build printable lines for the new-engine world circuit."""

    renderOptions: WorldRenderOptions = options or WorldRenderOptions()
    if not renderOptions.geometryShow and not renderOptions.wiringShow:
        renderOptions = WorldRenderOptions(
            zoneSpecs=renderOptions.zoneSpecs,
            geometryShow=False,
            wiringShow=True,
        )

    runtimeInputs: _WorldRuntimeInputs = _worldRuntimeInputs_build(
        documentDict
    )
    activeIndexes: list[int] = sorted(runtimeInputs.geometriesByIndex)
    requestedIndexes: list[int] = _requestedIndexes_get(
        renderOptions.zoneSpecs,
        activeIndexes,
    )
    errors: list[str] = _requestedIndexes_validate(
        requestedIndexes,
        activeIndexes,
    )
    if errors:
        return _worldFailureLines_build(title, errors)

    resolution: WorldChainResolution = (
        WorldGeometryResolver.harmonized_chain_build(
            runtimeInputs.geometriesByIndex
        )
    )
    materializePolicy = BoardMaterializePolicy(
        skipRelaxation=(renderOptions.routingPolicy is RoutingPolicy.NONE),
        invertRelaxation=(renderOptions.routingPolicy is RoutingPolicy.PARIS),
    )
    worldSolution: BoardWorldMaterializedSolution = (
        BoardWorldMaterializedSolution.fromResolvedChain_build(
            boardByIndex=runtimeInputs.boardByIndex,
            solverByIndex=runtimeInputs.solverByIndex,
            resolution=resolution,
            materializePolicy=materializePolicy,
        )
    )
    reoriginatedOffsets: dict[int, int] = (
        worldSolution.offsetsReoriginated_get(requestedIndexes[0])
        if requestedIndexes
        else {}
    )

    lines: list[str] = []
    if title:
        lines.append(f"== {title} ==")
        lines.append("")
    lines.append("--- WORLD CIRCUIT ---")
    lines.append("")
    offsetSummary: str = "  ".join(
        f"(1,{index}) off={reoriginatedOffsets.get(index, 0)}"
        for index in requestedIndexes
    )
    lines.append(f"zones: {offsetSummary}")
    lines.append("")
    modulePolicy = renderOptions.modulePolicy.value
    depthBox = renderOptions.depthBox
    if renderOptions.geometryShow:
        lines.extend(
            worldSolution.geometry_sprint(
                requestedIndexes,
                legend_show=True,
                modulePolicy=modulePolicy,
                depthBox=depthBox,
            ).splitlines()
        )
    if renderOptions.wiringShow:
        lines.extend(
            worldSolution.wiring_sprint(
                requestedIndexes,
                modulePolicy=modulePolicy,
                depthBox=depthBox,
            ).splitlines()
        )
    return lines


def _worldRuntimeInputs_build(
    documentDict: dict[str, object],
) -> _WorldRuntimeInputs:
    """Build all active overlap-zone inputs for world rendering."""

    circuitDocumentResult: Result[CircuitDocument] = (
        circuitDocumentResult_buildFromDocumentDict(documentDict)
    )
    if not result_isOkCheck(circuitDocumentResult):
        return _WorldRuntimeInputs({}, {}, {})

    callingStackResult: Result[CallingStack] = (
        callingStackResult_buildFromCircuitDocument(
            circuitDocumentResult.value
        )
    )
    if not result_isOkCheck(callingStackResult):
        return _WorldRuntimeInputs({}, {}, {})

    bandCount: int = callingStackResult.value.bandCount_calculate()
    geometriesByIndex: dict[int, BoardGeometry] = {}
    boardByIndex: dict[int, Board] = {}
    solverByIndex: dict[int, BoardSolver] = {}

    for overlapIndex in range(1, max(0, bandCount - 1) + 1):
        contextResult: Result[SignalFlowContext] = (
            contextResult_buildFromDocumentAndZone(
                documentDict,
                columnIndex=overlapIndex,
                rowIndex=1,
            )
        )
        if not result_isOkCheck(contextResult):
            continue
        boardZone: BoardZone = contextResult.value.zones.zone_get(1, 1)
        kernel: BoardKernel | None = boardZone.kernel_get("intra")
        if kernel is None:
            continue
        board: Board = kernel.board_get()
        geometriesByIndex[overlapIndex] = board.geometry_get()
        boardByIndex[overlapIndex] = board
        solverByIndex[overlapIndex] = kernel.solver_get()

    return _WorldRuntimeInputs(
        geometriesByIndex=geometriesByIndex,
        boardByIndex=boardByIndex,
        solverByIndex=solverByIndex,
    )


def _worldFailureLines_build(title: str, errors: Sequence[str]) -> list[str]:
    """Build readable world-render failure lines."""

    lines: list[str] = []
    if title:
        lines.append(f"== {title} ==")
        lines.append("")
    lines.append("engine: new")
    lines.append("status: error")
    lines.append("diagnostics:")
    lines.extend(f"  {error}" for error in errors)
    return lines
