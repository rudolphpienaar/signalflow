"""Board build pipeline: infrastructure, stage functions, and DAG declaration.

This is the single place a coder reads to understand how a Board is built.
BOARD_BUILD_PIPELINE is the executive dependency graph: each PipelineNode
declares its named inputs and the function that transforms them.  The executor
(boardPipeline_run) resolves deps from a context dict and accumulates results.

Adding a geometry modifier means updating one stage's fn — downstream stages
re-run automatically because they declare their deps by name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from dataclasses import replace as _replace
from typing import Any

from signalflow.board.board import Board

# Private builder helpers — imported here so pipeline.py owns the DAG logic
# while builders.py owns the geometry implementation details.
from signalflow.board.builders import (  # noqa: E402
    _boardGeometriesNormalizedToPositiveWorld_build,
    _boardSense_build,
    _boardWorldFrame_build,
    _chipDrawPlacementsByChip_build,
    _chipName_build,
    _effectiveGeometry_build,
    _extraGeometry_build,
    _geometryScopes_build,
    _minimumCrossbarSpan_calculate,
    _moduleBoundaryClampedToTerminalZones_build,
    _wteCoreRegionFrames_build,
)
from signalflow.board.doctrine import (
    BoardChipPlacementPolicy,
    BoardDoctrine,
    BoardGeometrySpec,
    EffectiveBoundaryMode,
)
from signalflow.board.geometry import BoardGeometry
from signalflow.board.substrate import BoardSubstrate
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    BoardSense,
    TerminalPositionsByChip,
    WorldFrame,
)
from signalflow.models import (
    CallingStack,
    ChipRef,
    ChipTerminalSide,
    CircuitDocument,
    RoutingZone,
    RoutingZoneId,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
    callingStackResult_buildFromCircuitDocument,
    result_isOkCheck,
)
from signalflow.models.geometry_scope import BoardGeometryScope
from signalflow.routing.geometry import (
    ChipLocalGeometrySet,
    chipLocalGeometrySetResult_buildFromChips,
)

# ---------------------------------------------------------------------------
# Pipeline infrastructure
# ---------------------------------------------------------------------------


class PipelineError(Exception):
    """Raised by a stage function to signal unrecoverable pipeline failure."""


@dataclass(frozen=True)
class PipelineNode:
    """One node in the board build DAG.

    Attributes:
        name:    Label for this stage; also the context key when outputs is
                 None.
        deps:    Names of context keys this stage reads as keyword arguments.
        fn:      Callable invoked with deps as kwargs; returns stage output.
        outputs: If set, fn returns a tuple and each element is stored under
                 the corresponding name.  name is used as a label only.
    """

    name: str
    deps: tuple[str, ...]
    fn: Callable[..., Any]
    outputs: tuple[str, ...] | None = field(default=None)


def boardPipeline_run(
    pipeline: tuple[PipelineNode, ...],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Execute pipeline nodes in order, accumulating results in ctx.

    Raises PipelineError on first stage failure.
    """

    for node in pipeline:
        kwargs = {dep: ctx[dep] for dep in node.deps}
        result = node.fn(**kwargs)
        if node.outputs is not None:
            for key, val in zip(node.outputs, result, strict=True):
                ctx[key] = val
        else:
            ctx[node.name] = result
    return ctx


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------


def _stage_sense(*, routingZone: RoutingZone) -> BoardSense:
    return _boardSense_build(routingZone)


def _stage_chipLocalGeometrySet(
    *, circuitDocument: CircuitDocument
) -> ChipLocalGeometrySet:
    result = chipLocalGeometrySetResult_buildFromChips(
        circuitDocument.circuitChipSet.chips
    )
    if not result_isOkCheck(result):
        raise PipelineError("chipLocalGeometrySet")
    return result.value


def _stage_chipDrawPlacements(
    *,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    chipLocalGeometrySet: ChipLocalGeometrySet,
    chipPlacementPolicy: BoardChipPlacementPolicy,
    moduleBoundaryPaddingCells: int,
) -> dict[str, BoardChipDrawPlacement]:
    return _chipDrawPlacementsByChip_build(
        routingZone=routingZone,
        circuitDocument=circuitDocument,
        chipLocalGeometrySet=chipLocalGeometrySet,
        chipPlacementPolicy=chipPlacementPolicy,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
    )


def _stage_terminalPositionsByChip(
    *,
    chipDrawPlacements: dict[str, BoardChipDrawPlacement],
    chipLocalGeometrySet: ChipLocalGeometrySet,
    routingZone: RoutingZone,
) -> TerminalPositionsByChip:
    """Derive wire-endpoint world positions directly from already-placed chips.

    Reads drawTopLeft from the BoardChipDrawPlacement produced by
    _stage_chipDrawPlacements — guaranteed coherent with chip render positions.
    No independent re-run of the stack-offset formula; geometry modifiers
    propagate automatically through the declared dependency on
    chipDrawPlacements.
    """
    chipRefByName: dict[str, ChipRef] = {
        _chipName_build(p.chipRef): p.chipRef
        for p in routingZone.chipPlacementSet.placements
    }
    terminalPositionsByChip: TerminalPositionsByChip = {}
    for chipName, chipDrawPlacement in chipDrawPlacements.items():
        chipRef = chipRefByName.get(chipName)
        if chipRef is None:
            continue
        geoResult = chipLocalGeometrySet.geometryForChipResult_get(chipRef)
        if not result_isOkCheck(geoResult):
            continue
        geo = geoResult.value
        drawWorldColumn, drawWorldRow = chipDrawPlacement.drawTopLeft
        boxWorldRow = drawWorldRow + geo.boxTopLineOffset
        for entry in geo.terminalLineOffsets:
            side = entry.terminalSide
            if side is ChipTerminalSide.WEST or side is ChipTerminalSide.EAST:
                worldRow = drawWorldRow + entry.lineOffset
                worldColumn = drawWorldColumn + entry.columnOffset
            elif side is ChipTerminalSide.NORTH:
                worldColumn = drawWorldColumn + entry.columnOffset
                worldRow = boxWorldRow
            else:
                worldColumn = drawWorldColumn + entry.columnOffset
                worldRow = boxWorldRow + geo.boxHeight - 1
            terminalPositionsByChip.setdefault(chipName, {})[
                entry.terminalName
            ] = (worldColumn, worldRow)
    return terminalPositionsByChip


def _stage_callingStack(*, circuitDocument: CircuitDocument) -> CallingStack:
    result = callingStackResult_buildFromCircuitDocument(circuitDocument)
    return result.value if result_isOkCheck(result) else CallingStack()


def _stage_regionFrames(
    *,
    routingZoneId: RoutingZoneId,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    geometrySpec: BoardGeometrySpec,
    moduleBoundaryPaddingCells: int,
    terminalPositionsByChip: TerminalPositionsByChip,
    chipDrawPlacements: dict[str, BoardChipDrawPlacement],
    sense: BoardSense,
) -> tuple[
    dict[BoardRegionId, RoutingZoneRegionFrame],
    dict[BoardRegionId, RoutingZoneRegionId],
]:
    if sense not in (BoardSense.WEST_TO_EAST, BoardSense.EAST_TO_WEST):
        raise PipelineError("regionFrames: unsupported zone sense")
    regionFramesById, routingZoneRegionIdsById = _wteCoreRegionFrames_build(
        routingZoneId=routingZoneId,
        routingZone=routingZone,
        circuitDocument=circuitDocument,
        geometrySpec=geometrySpec,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
        terminalPositionsByChip=terminalPositionsByChip,
        chipDrawPlacementsByChip=chipDrawPlacements,
    )
    if not regionFramesById:
        raise PipelineError("regionFrames: empty result")
    return regionFramesById, routingZoneRegionIdsById


def _stage_geometryScopes(
    *,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    callingStack: CallingStack,
    effectiveBoundaryMode: EffectiveBoundaryMode,
    moduleBoundaryPaddingCells: int,
    chipPlacementPolicy: BoardChipPlacementPolicy,
) -> tuple[BoardGeometryScope, ...]:
    return _geometryScopes_build(
        routingZone=routingZone,
        circuitDocument=circuitDocument,
        callingStack=callingStack,
        effectiveBoundaryMode=effectiveBoundaryMode,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
        chipPlacementPolicy=chipPlacementPolicy,
    )


def _stage_substrateGeometry(
    *,
    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame],
    routingZoneRegionIdsById: dict[BoardRegionId, RoutingZoneRegionId],
    geometryScopes: tuple[BoardGeometryScope, ...],
    terminalPositionsByChip: TerminalPositionsByChip,
    chipDrawPlacements: dict[str, BoardChipDrawPlacement],
) -> BoardGeometry:
    return BoardGeometry(
        regionFramesById=regionFramesById,
        routingZoneRegionIdsById=routingZoneRegionIdsById,
        geometryScopes=geometryScopes,
        exactTerminalWorldPositionsByChip=terminalPositionsByChip,
        chipDrawPlacementsByChip=chipDrawPlacements,
    )


def _stage_effectiveGeometry(
    *,
    substrateGeometry: BoardGeometry,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    moduleBoundaryPaddingCells: int,
    chipPlacementPolicy: BoardChipPlacementPolicy,
) -> BoardGeometry:
    return _effectiveGeometry_build(
        substrateGeometry=substrateGeometry,
        routingZone=routingZone,
        circuitDocument=circuitDocument,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
        chipPlacementPolicy=chipPlacementPolicy,
    )


def _stage_extraGeometry(
    *,
    effectiveGeometry: BoardGeometry,
    routingZone: RoutingZone,
    circuitDocument: CircuitDocument,
    geometrySpec: BoardGeometrySpec,
) -> BoardGeometry:
    result = _extraGeometry_build(
        effectiveGeometry=effectiveGeometry,
        routingZone=routingZone,
        circuitDocument=circuitDocument,
        spec=geometrySpec,
    )
    if not result_isOkCheck(result):
        raise PipelineError("extraGeometry")
    return result.value


def _stage_normalizedGeometries(
    *,
    substrateGeometry: BoardGeometry,
    extraGeometry: BoardGeometry,
) -> tuple[BoardGeometry, BoardGeometry]:
    return _boardGeometriesNormalizedToPositiveWorld_build(
        substrateGeometry=substrateGeometry,
        effectiveGeometry=extraGeometry,
    )


def _stage_clampedGeometry(
    *,
    normalizedEffectiveGeometry: BoardGeometry,
    moduleBoundaryPaddingCells: int,
) -> BoardGeometry:
    return _moduleBoundaryClampedToTerminalZones_build(
        normalizedEffectiveGeometry,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
    )


def _stage_board(
    *,
    routingZoneId: RoutingZoneId,
    side: str,
    routingZone: RoutingZone,
    sense: BoardSense,
    normalizedSubstrateGeometry: BoardGeometry,
    clampedGeometry: BoardGeometry,
    regionFramesById: dict[BoardRegionId, RoutingZoneRegionFrame],
    effectiveBoundaryMode: EffectiveBoundaryMode,
    moduleBoundaryPaddingCells: int,
    chipPlacementPolicy: BoardChipPlacementPolicy,
) -> Board:
    substrateWorldFrame = _boardWorldFrame_build(
        geometry=normalizedSubstrateGeometry,
        fallbackFrame=routingZone.routingZoneFrame,
    )
    effectiveWorldFrame = _boardWorldFrame_build(
        geometry=clampedGeometry,
        fallbackFrame=routingZone.routingZoneFrame,
    )
    pinnedWorldFrame = WorldFrame(
        topLeft=substrateWorldFrame.topLeft,
        bottomRight=effectiveWorldFrame.bottomRight,
    )
    substrate = BoardSubstrate(sense=sense, regionFramesById=regionFramesById)
    doctrine = BoardDoctrine(
        sense=sense,
        minimumCrossbarSpan=_minimumCrossbarSpan_calculate(
            regionFramesById, sense
        ),
        effectiveBoundaryMode=effectiveBoundaryMode,
        moduleBoundaryPaddingCells=moduleBoundaryPaddingCells,
        chipPlacementPolicy=chipPlacementPolicy,
    )
    effectiveBoard = Board(
        routingZoneId=routingZoneId,
        side=side,
        worldFrame=pinnedWorldFrame,
        doctrine=doctrine,
        substrate=substrate,
        geometry=clampedGeometry,
    )
    substrateBoard = Board(
        routingZoneId=routingZoneId,
        side=side,
        worldFrame=substrateWorldFrame,
        doctrine=_replace(
            doctrine,
            effectiveBoundaryMode=EffectiveBoundaryMode.CONTENT_ONLY,
            moduleBoundaryPaddingCells=0,
        ),
        substrate=substrate,
        geometry=BoardGeometry(
            geometryZonesById=normalizedSubstrateGeometry.zonesById,
        ),
    )
    object.__setattr__(effectiveBoard, "substrateBoard", substrateBoard)
    object.__setattr__(effectiveBoard, "effectiveBoard", effectiveBoard)
    object.__setattr__(substrateBoard, "substrateBoard", substrateBoard)
    object.__setattr__(substrateBoard, "effectiveBoard", effectiveBoard)
    return effectiveBoard


# ---------------------------------------------------------------------------
# Board build DAG — open this file to understand the full pipeline
# ---------------------------------------------------------------------------

BOARD_BUILD_PIPELINE: tuple[PipelineNode, ...] = (
    PipelineNode(
        name="sense",
        deps=("routingZone",),
        fn=_stage_sense,
    ),
    PipelineNode(
        name="chipLocalGeometrySet",
        deps=("circuitDocument",),
        fn=_stage_chipLocalGeometrySet,
    ),
    PipelineNode(
        name="chipDrawPlacements",
        deps=(
            "routingZone",
            "circuitDocument",
            "chipLocalGeometrySet",
            "chipPlacementPolicy",
            "moduleBoundaryPaddingCells",
        ),
        fn=_stage_chipDrawPlacements,
    ),
    PipelineNode(
        name="terminalPositionsByChip",
        deps=("chipDrawPlacements", "chipLocalGeometrySet", "routingZone"),
        fn=_stage_terminalPositionsByChip,
    ),
    PipelineNode(
        name="callingStack",
        deps=("circuitDocument",),
        fn=_stage_callingStack,
    ),
    PipelineNode(
        name="regionFrames",
        deps=(
            "routingZoneId",
            "routingZone",
            "circuitDocument",
            "geometrySpec",
            "moduleBoundaryPaddingCells",
            "terminalPositionsByChip",
            "chipDrawPlacements",
            "sense",
        ),
        fn=_stage_regionFrames,
        outputs=("regionFramesById", "routingZoneRegionIdsById"),
    ),
    PipelineNode(
        name="geometryScopes",
        deps=(
            "routingZone",
            "circuitDocument",
            "callingStack",
            "effectiveBoundaryMode",
            "moduleBoundaryPaddingCells",
            "chipPlacementPolicy",
        ),
        fn=_stage_geometryScopes,
    ),
    PipelineNode(
        name="substrateGeometry",
        deps=(
            "regionFramesById",
            "routingZoneRegionIdsById",
            "geometryScopes",
            "terminalPositionsByChip",
            "chipDrawPlacements",
        ),
        fn=_stage_substrateGeometry,
    ),
    PipelineNode(
        name="effectiveGeometry",
        deps=(
            "substrateGeometry",
            "routingZone",
            "circuitDocument",
            "moduleBoundaryPaddingCells",
            "chipPlacementPolicy",
        ),
        fn=_stage_effectiveGeometry,
    ),
    PipelineNode(
        name="extraGeometry",
        deps=(
            "effectiveGeometry",
            "routingZone",
            "circuitDocument",
            "geometrySpec",
        ),
        fn=_stage_extraGeometry,
    ),
    PipelineNode(
        name="normalizedGeometries",
        deps=("substrateGeometry", "extraGeometry"),
        fn=_stage_normalizedGeometries,
        outputs=("normalizedSubstrateGeometry", "normalizedEffectiveGeometry"),
    ),
    PipelineNode(
        name="clampedGeometry",
        deps=("normalizedEffectiveGeometry", "moduleBoundaryPaddingCells"),
        fn=_stage_clampedGeometry,
    ),
    PipelineNode(
        name="board",
        deps=(
            "routingZoneId",
            "side",
            "routingZone",
            "sense",
            "normalizedSubstrateGeometry",
            "clampedGeometry",
            "regionFramesById",
            "effectiveBoundaryMode",
            "moduleBoundaryPaddingCells",
            "chipPlacementPolicy",
        ),
        fn=_stage_board,
    ),
)
