"""Quarantine symbolic-kernel solver tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from signalflow.board import (
    Board,
    BoardChipDrawPlacement,
    BoardGeometry,
    BoardKernel,
    BoardSolver,
    BoardWorldMaterializedSolution,
    BoardZone,
)
from signalflow.board.builders import boardGeometryBoundaryNormalized_build
from signalflow.board.doctrine import (
    BoardMaterializePolicy,
    BoardRelaxationSymmetry,
)
from signalflow.board.geometry import (
    GeometryCouplingOp,
    GeometryCouplingSymbolicExpr,
    GeometryOp,
    GeometryZone,
    WorldChainResolution,
    WorldGeometryResolver,
    ZoneConnectivityKind,
    ZoneGeometryTarget,
    ZoneMutationExpr,
    ZoneMutationKind,
    ZoneOverlapExprBank,
    ZoneRelationExpr,
    ZoneRelationKind,
    chipTerminalCouplingAppliedResult_build,
    chipTerminalCouplingFamilyResult_build,
    chipTerminalCouplingSymbolicExprsResult_build,
    eastWestZoneOverlapExprBank_build,
    geometryCouplingExpr_buildFromSymbolic,
    geometryExprLoweredResult_build,
    zoneCouplingOperandResult_build,
    zoneExtentMaxAlignRelation_build,
    zoneOperandResult_build,
    zoneOperandsResult_build,
    zoneOpResult_build,
    zonePaddingAddMutation_build,
)
from signalflow.board.geometry.georules import (
    GeoArgScalar,
    GeoOp,
    geometry_change,
)
from signalflow.board.geometry.mutation import (
    boardRegionIdResult_fromSfN,
    zoneAdjacencyConstraint_buildFromExpr,
    zoneGeometryMutation_buildFromExpr,
)
from signalflow.board.realizer import (
    RealizerRouteInput,
    algebraicRouteRealization_build,
    algebraicRouteRealization_buildFromPath,
    regionFramesRelaxed_build,
)
from signalflow.board.solver import (
    SolverWireInput,
    boardChannelLaneCounts_build,
    wireTopology_build,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.input import circuitDocumentResult_buildFromDocumentDict
from signalflow.engine.inspect import (
    ChipView,
    KernelBoardHandle,
    SignalFlowContext,
    ZoneHandle,
    _replLocals_build,
)
from signalflow.engine.inspect.geometry import regionSymbol_get
from signalflow.engine.inspect.zone_local import (
    contextResult_buildFromDocumentAndZone,
)
from signalflow.engine.render import diagram_render
from signalflow.engine.world_render import WorldRenderOptions
from signalflow.models import (
    CallingStack,
    ChipId,
    ChipTerminalSide,
    GridCoord,
    RoutingLaneAttachmentSense,
    RoutingZoneChannelSense,
    RoutingZoneRegionFrame,
    ZoneLocalGeometryKind,
    callingStackResult_buildFromCircuitDocument,
    result_isErrCheck,
    result_isOkCheck,
)
from signalflow.models.assignment import (
    RoutingZoneLayerSet,
    routingZoneLayerSetResult_buildFromCircuitDocument,
)
from signalflow.models.engine import EngineName
from signalflow.notation import (
    WTE_INTRA_FORWARD,
    WTE_INTRA_RETURN,
    WiringSolution,
    sfN,
)
from signalflow.notation.path import WTE_OUTER_EASTBOUND_ARC


def _hubDocumentDict_build() -> dict:
    """Build the parsed `examples/hub.yaml` document."""

    hubPath = Path(__file__).resolve().parent.parent / "examples" / "hub.yaml"
    with hubPath.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _exampleDocumentDict_build(exampleName: str) -> dict[str, Any]:
    """Build one parsed example document from the repo `examples/` tree."""

    examplePath = (
        Path(__file__).resolve().parent.parent / "examples" / exampleName
    )
    with examplePath.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _worldOverlapRuntime_build() -> tuple[
    dict[int, BoardGeometry],
    dict[int, Board],
    dict[int, BoardSolver],
]:
    """Build active overlap-zone runtime inputs for back-and-forth."""

    return _worldRuntimeForExample_build("simple-circuit/back-and-forth.yaml")


def _worldRuntimeForExample_build(
    exampleName: str,
) -> tuple[
    dict[int, BoardGeometry],
    dict[int, Board],
    dict[int, BoardSolver],
]:
    """Build active overlap-zone runtime inputs for an example document."""

    documentDict: dict[str, Any] = _exampleDocumentDict_build(exampleName)
    cdResult = circuitDocumentResult_buildFromDocumentDict(documentDict)
    assert result_isOkCheck(cdResult)
    callingStackResult = callingStackResult_buildFromCircuitDocument(
        cdResult.value
    )
    assert result_isOkCheck(callingStackResult)

    bandCount: int = callingStackResult.value.bandCount_calculate()
    geometriesByIndex: dict[int, BoardGeometry] = {}
    boardByIndex: dict[int, Board] = {}
    solverByIndex: dict[int, BoardSolver] = {}
    for overlapIndex in range(1, max(0, bandCount - 1) + 1):
        contextResult = contextResult_buildFromDocumentAndZone(
            documentDict,
            columnIndex=overlapIndex,
            rowIndex=1,
        )
        assert result_isOkCheck(contextResult)
        boardZone: BoardZone = contextResult.value.zones.zone_get(1, 1)
        kernel: BoardKernel | None = boardZone.kernel_get("intra")
        assert kernel is not None
        board: Board = kernel.board_get()
        geometriesByIndex[overlapIndex] = board.geometry_get()
        boardByIndex[overlapIndex] = board
        solverByIndex[overlapIndex] = kernel.solver_get()
    return geometriesByIndex, boardByIndex, solverByIndex


def _worldOverlapGeometries_build() -> dict[int, BoardGeometry]:
    """Build active overlap-zone geometries for the back-and-forth fixture."""

    geometriesByIndex, _boardByIndex, _solverByIndex = (
        _worldOverlapRuntime_build()
    )
    return geometriesByIndex


def _frameByToken_get(
    geometry: BoardGeometry,
    token: sfN,
) -> RoutingZoneRegionFrame:
    """Return a first-class geometry frame for an sfN token."""

    return _geometryZoneByToken_get(geometry, token).frame


def _geometryZoneByToken_get(
    geometry: BoardGeometry,
    token: sfN,
) -> GeometryZone:
    """Return a first-class geometry zone for an sfN token."""

    ridResult = boardRegionIdResult_fromSfN(token)
    assert result_isOkCheck(ridResult)
    zone: GeometryZone | None = geometry.geometryZonesById.get(
        ridResult.value
    )
    assert zone is not None
    return zone


def _inclusiveRows_get(frame: RoutingZoneRegionFrame) -> tuple[int, int]:
    """Return inclusive row span for assertions."""

    return (frame.verticalStart, frame.verticalEnd_calculate() - 1)


def _placementRows_get(
    placement: BoardChipDrawPlacement,
) -> tuple[int, int]:
    """Return inclusive row span for a chip draw placement."""

    top: int = placement.drawTopLeft[1]
    return (top, top + len(placement.drawLines) - 1)


def test_inspect_package_import_surface_smoke() -> None:
    """The inspect package should expose the post-split import surface."""

    assert SignalFlowContext.__module__ == "signalflow.engine.inspect.context"
    assert KernelBoardHandle.__module__ == (
        "signalflow.engine.inspect.primitives"
    )
    assert ChipView.__module__ == "signalflow.engine.inspect.surfaces"
    assert ZoneHandle.__module__ == "signalflow.engine.inspect.surfaces"
    assert callable(_replLocals_build)


def test_world_geometry_resolver_harmonizes_key_seam_rows() -> None:
    """World resolver should preserve the proven 1,2 / 1,3 seam rows."""

    resolution: WorldChainResolution = (
        WorldGeometryResolver.harmonized_chain_build(
            _worldOverlapGeometries_build()
        )
    )
    zone12: BoardGeometry = resolution.geometryByIndex[2]
    zone13: BoardGeometry = resolution.geometryByIndex[3]

    assert _inclusiveRows_get(_frameByToken_get(zone12, sfN.Et)) == (25, 48)
    assert _inclusiveRows_get(_frameByToken_get(zone13, sfN.Wt)) == (25, 48)
    assert _inclusiveRows_get(_frameByToken_get(zone13, sfN.Ne)) == (17, 20)

    _zone12GrandchildScope = zone12.scopeForModuleName_get("grandchild.ts")
    assert _zone12GrandchildScope is not None
    assert _zone12GrandchildScope.frame is not None
    zone12Grandchild: RoutingZoneRegionFrame = _zone12GrandchildScope.frame
    _zone13GrandchildScope = zone13.scopeForModuleName_get("grandchild.ts")
    assert _zone13GrandchildScope is not None
    assert _zone13GrandchildScope.frame is not None
    zone13Grandchild: RoutingZoneRegionFrame = _zone13GrandchildScope.frame
    assert _inclusiveRows_get(zone12Grandchild) == (25, 48)
    assert _inclusiveRows_get(zone13Grandchild) == (25, 48)
    assert (
        resolution.wOffsetsByIndex[3] - resolution.wOffsetsByIndex[2]
    ) == 64


def test_world_geometry_resolver_keeps_neural_network_modules_coherent(
) -> None:
    """Shared-module seam moves should keep all chip projections coherent."""

    geometriesByIndex, _boardByIndex, _solverByIndex = (
        _worldRuntimeForExample_build("simple-circuit/neural-network.yaml")
    )
    resolution: WorldChainResolution = (
        WorldGeometryResolver.harmonized_chain_build(geometriesByIndex)
    )
    zone12: BoardGeometry = resolution.geometryByIndex[2]
    zone13: BoardGeometry = resolution.geometryByIndex[3]
    zone12Et: GeometryZone = _geometryZoneByToken_get(zone12, sfN.Et)
    zone13Wt: GeometryZone = _geometryZoneByToken_get(zone13, sfN.Wt)
    zone13Et: GeometryZone = _geometryZoneByToken_get(zone13, sfN.Et)

    for chipName in ("hiddenLayer.ts.h1()", "hiddenLayer.ts.h2()"):
        assert (
            zone12Et.chipDrawPlacementsByChip[chipName].drawTopLeft[1]
            == zone13Wt.chipDrawPlacementsByChip[chipName].drawTopLeft[1]
        )

    _zone13OutputLayerScope = zone13.scopeForModuleName_get("outputLayer.ts")
    assert _zone13OutputLayerScope is not None
    assert _zone13OutputLayerScope.frame is not None
    zone13Boundary: RoutingZoneRegionFrame = _zone13OutputLayerScope.frame
    boundaryRows: tuple[int, int] = _inclusiveRows_get(zone13Boundary)
    etRows: tuple[int, int] = _inclusiveRows_get(zone13Et.frame)
    for placement in zone13Et.chipDrawPlacementsByChip.values():
        placementRows: tuple[int, int] = _placementRows_get(placement)
        assert etRows[0] <= placementRows[0]
        assert placementRows[1] <= etRows[1]
        assert boundaryRows[0] <= placementRows[0]
        assert placementRows[1] <= boundaryRows[1]


def test_board_world_materialized_solution_sprints_key_surfaces() -> None:
    """World aggregate should preserve inspect geometry and wiring surfaces."""

    (
        geometriesByIndex,
        boardByIndex,
        solverByIndex,
    ) = _worldOverlapRuntime_build()
    resolution: WorldChainResolution = (
        WorldGeometryResolver.harmonized_chain_build(geometriesByIndex)
    )
    worldSolution: BoardWorldMaterializedSolution = (
        BoardWorldMaterializedSolution.fromResolvedChain_build(
            boardByIndex=boardByIndex,
            solverByIndex=solverByIndex,
            resolution=resolution,
        )
    )

    geometryText: str = worldSolution.geometry_sprint(
        [2, 3],
        legend_show=True,
    )
    wiringText: str = worldSolution.wiring_sprint([2, 3])

    assert "=== ZONE (1,2) GEOMETRY ===" in geometryText
    assert "=== ZONE (1,3) GEOMETRY ===" in geometryText
    assert "--- WORLD WIRING: (1,2)  (1,3) ---" in wiringText
    assert "grandchild.ts" in geometryText
    assert "grandchild.ts" in wiringText


def test_new_engine_top_level_renders_world_circuit_by_default() -> None:
    """Default new-engine CLI render should use the world aggregate."""

    documentDict: dict[str, Any] = _exampleDocumentDict_build(
        "simple-circuit/back-and-forth.yaml"
    )
    lines: list[str] = diagram_render(
        title=str(documentDict.get("title", "")),
        treeDict=documentDict,
        engineName=EngineName.NEW,
    )
    outputText: str = "\n".join(lines)

    assert "--- WORLD CIRCUIT ---" in outputText
    assert "--- WORLD WIRING: (1,1)  (1,2)  (1,3) ---" in outputText
    assert "grandchild.ts" in outputText


def test_new_engine_top_level_supports_filtered_geometry() -> None:
    """Top-level new-engine render should support snippet-like filters."""

    documentDict: dict[str, Any] = _exampleDocumentDict_build(
        "simple-circuit/back-and-forth.yaml"
    )
    lines: list[str] = diagram_render(
        title=str(documentDict.get("title", "")),
        treeDict=documentDict,
        engineName=EngineName.NEW,
        worldRenderOptions=WorldRenderOptions(
            zoneSpecs=((1, 2), (1, 3)),
            geometryShow=True,
            wiringShow=False,
        ),
    )
    outputText: str = "\n".join(lines)

    assert "zones: (1,2) off=0  (1,3) off=64" in outputText
    assert "=== ZONE (1,2) GEOMETRY ===" in outputText
    assert "=== ZONE (1,3) GEOMETRY ===" in outputText
    assert "--- WORLD WIRING:" not in outputText
    assert "grandchild.ts" in outputText


def test_input_parser_rejects_empty_optional_return_label() -> None:
    """A present return field must name a real return terminal."""

    documentResult = circuitDocumentResult_buildFromDocumentDict(
        {
            "title": "empty-return",
            "tree": {
                "module": "root.ts",
                "func": "root()",
                "output_ports": [{"signal": "x", "return": ""}],
                "calls": [
                    {
                        "module": "leaf.ts",
                        "func": "leaf()",
                        "input_ports": [{"signal": "x"}],
                    }
                ],
            },
        }
    )

    assert result_isErrCheck(documentResult)


def test_new_engine_renders_forward_only_neural_network_without_return_stubs(
) -> None:
    """The C-style fan-out example has only forward signal wires."""

    documentDict: dict[str, Any] = _exampleDocumentDict_build(
        "simple-circuit/neural-network.yaml"
    )
    lines: list[str] = diagram_render(
        title=str(documentDict.get("title", "")),
        treeDict=documentDict,
        engineName=EngineName.NEW,
    )
    outputText: str = "\n".join(lines)

    assert "--- WORLD CIRCUIT ---" in outputText
    assert "x1w11" in outputText
    assert "h3v32" in outputText
    assert "◄" not in outputText


def test_board_first_world_does_not_treat_interconnects_as_geometry() -> None:
    """The board-first compatibility grid should be seam-free."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    boardPlacedGrid = debugContextResult.value.boardPlacedGrid_get()

    assert (
        boardPlacedGrid.routingZoneInterconnectSet.routingZoneInterconnects
        == ()
    )


def test_backedge_example_context_builds_without_negative_route_points() -> (
    None
):
    """Backedge example should build without emitting negative route points."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build(
            "simple-circuit/rearch-external-backedge.yaml"
        )
    )

    assert result_isOkCheck(debugContextResult)


def test_backedge_example_classifies_outer_parent_route_from_call_depth() -> (
    None
):
    """Backedge example should classify ancestor return by call depth."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build(
            "simple-circuit/rearch-external-backedge.yaml"
        )
    )

    assert result_isOkCheck(debugContextResult)
    routeObligationSet = debugContextResult.value.routeObligationSet
    callRouteObligationSet = routeObligationSet.callRouteObligationSet
    obligations = callRouteObligationSet.callRouteObligations

    assert len(obligations) == 2
    assert obligations[0].zoneLocalGeometryKind is (
        ZoneLocalGeometryKind.INTRA_PARENT_TOCHILD
    )
    assert obligations[1].zoneLocalGeometryKind is (
        ZoneLocalGeometryKind.OUTER_CHILD_TOPARENT
    )


def test_backedge_example_uses_outer_arc_topology_in_board_solver() -> None:
    """Backedge board solve should select the outer-arc algebraic topology."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build(
            "simple-circuit/rearch-external-backedge.yaml"
        )
    )

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    assert kernel is not None

    solution = kernel.solver_get(kernel.board_get()).solution_get()
    backedgeSolvedWires = tuple(
        solvedWire
        for solvedWire in solution.all_get()
        if (
            solvedWire.kernelWire.sourceChipRef.chipId.functionName
            == "callee()"
            and solvedWire.kernelWire.destinationChipRef.chipId.functionName
            == "caller()"
            and not solvedWire.kernelWire.isReturn
        )
    )

    assert len(backedgeSolvedWires) == 1
    assert backedgeSolvedWires[0].wiringSolution.topology.name_get() == (
        "wte_outer_westbound_arc"
    )
    assert tuple(
        hop.area for hop in backedgeSolvedWires[0].algebraicPath.hops
    ) == (
        sfN.Efe,
        sfN.Ee,
        sfN.Ne,
        sfN.We,
        sfN.Wfe,
    )
    materialized = solution.board_materialize(kernel.board_get())
    backedgeMaterializedWires = tuple(
        wire
        for wire in materialized._materializedWires
        if (
            wire.solvedWire.kernelWire.sourceChipRef.chipId.functionName
            == "callee()"
            and (
                wire.solvedWire.kernelWire.destinationChipRef.chipId.functionName
            )
            == "caller()"
            and not wire.solvedWire.kernelWire.isReturn
        )
    )
    assert len(backedgeMaterializedWires) == 1
    assert (97, 3) in backedgeMaterializedWires[0].routeCells
    assert (98, 3) not in backedgeMaterializedWires[0].routeCells


def test_back_and_forth_calling_stack_uses_module_bands() -> None:
    """Back-and-forth fixture should keep parent and child modules in bands."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(circuitDocumentResult)
    callingStackResult = callingStackResult_buildFromCircuitDocument(
        circuitDocumentResult.value
    )

    assert result_isOkCheck(callingStackResult)
    callingStack: CallingStack = callingStackResult.value

    assert callingStack.levels_sprint().splitlines() == [
        "calling stack:",
        "  depth 0: parent.ts:p1(), parent.ts:p2()",
        "  depth 1: child.ts:c1(), child.ts:c2(), child.ts:c3()",
        "  depth 2: grandchild.ts:gc1(), grandchild.ts:gc2()",
        (
            "  depth 3: greatgrandchild.ts:ggc1(), "
            "greatgrandchild.ts:ggc2(), greatgrandchild.ts:ggc3()"
        ),
    ]


def test_back_and_forth_assignment_layers_use_calling_stack_bands() -> None:
    """Routing layers should match the same parent-child banding."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(circuitDocumentResult)
    layerSetResult = routingZoneLayerSetResult_buildFromCircuitDocument(
        circuitDocumentResult.value
    )

    assert result_isOkCheck(layerSetResult)
    layerSet: RoutingZoneLayerSet = layerSetResult.value

    assert [
        (
            layer.depthIndex,
            tuple(
                f"{chipRef.chipId.moduleName}:{chipRef.chipId.functionName}"
                for chipRef in layer.chipRefs
            ),
        )
        for layer in layerSet.routingZoneLayers
    ] == [
        (0, ("parent.ts:p1()", "parent.ts:p2()")),
        (1, ("child.ts:c1()", "child.ts:c2()", "child.ts:c3()")),
        (2, ("grandchild.ts:gc1()", "grandchild.ts:gc2()")),
        (
            3,
            (
                "greatgrandchild.ts:ggc1()",
                "greatgrandchild.ts:ggc2()",
                "greatgrandchild.ts:ggc3()",
            ),
        ),
    ]


def test_back_and_forth_context_uses_one_zone_from_calling_stack_bands() -> (
    None
):
    """Implicit world sizing should follow CallingStack bands."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    assert debugContextResult.value.routingZoneCount_get() == 3


def test_back_and_forth_bind_output_is_display_only_on_source_chips() -> None:
    """`bind_output` should change wall text without changing canonical ids."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(circuitDocumentResult)
    circuitDocument = circuitDocumentResult.value
    c2ChipResult = circuitDocument.circuitChipSet.chipResult_get(
        ChipId(moduleName="child.ts", functionName="c2()")
    )
    p2ChipResult = circuitDocument.circuitChipSet.chipResult_get(
        ChipId(moduleName="parent.ts", functionName="p2()")
    )

    assert result_isOkCheck(c2ChipResult)
    assert result_isOkCheck(p2ChipResult)
    assert [
        (port.signalName, port.returnName)
        for port in (
            c2ChipResult.value.outputPortDeclarationSet.portDeclarations
        )
    ] == [
        ("c1sig", "c1ret"),
        ("p2sig", "p2ret"),
    ]
    assert [
        (port.signalName, port.returnName)
        for port in (
            c2ChipResult.value.outputDisplayPortDeclarationSet.portDeclarations
        )
    ] == [
        ("c2sig", "c1ret"),
        ("c1ret", "p2ret"),
    ]
    assert [
        (port.signalName, port.returnName)
        for port in (
            p2ChipResult.value.outputPortDeclarationSet.portDeclarations
        )
    ] == [("c3sig", "c3ret")]
    assert [
        (port.signalName, port.returnName)
        for port in (
            p2ChipResult.value.outputDisplayPortDeclarationSet.portDeclarations
        )
    ] == [("p2sig", "c3ret")]


def test_back_and_forth_route_obligations_keep_canonical_source_ids() -> None:
    """Display aliases should not replace canonical source route ids."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    routeObligationSet = debugContextResult.value.routeObligationSet
    callRouteObligationSet = routeObligationSet.callRouteObligationSet
    obligations = callRouteObligationSet.callRouteObligations
    c2ToP2Obligations = tuple(
        obligation
        for obligation in obligations
        if (
            obligation.sourceChipRef.chipId.functionName == "c2()"
            and obligation.destinationChipRef.chipId.functionName == "p2()"
        )
    )
    p2ToC3Obligations = tuple(
        obligation
        for obligation in obligations
        if (
            obligation.sourceChipRef.chipId.functionName == "p2()"
            and obligation.destinationChipRef.chipId.functionName == "c3()"
        )
    )

    assert len(c2ToP2Obligations) == 1
    assert c2ToP2Obligations[0].sourcePortDeclaration is not None
    assert c2ToP2Obligations[0].sourceDisplayPortDeclaration is not None
    assert c2ToP2Obligations[0].sourcePortDeclaration.signalName == "p2sig"
    assert (
        c2ToP2Obligations[0].sourceDisplayPortDeclaration.signalName == "c1ret"
    )
    assert len(p2ToC3Obligations) == 1
    assert p2ToC3Obligations[0].sourcePortDeclaration is not None
    assert p2ToC3Obligations[0].sourceDisplayPortDeclaration is not None
    assert p2ToC3Obligations[0].sourcePortDeclaration.signalName == "c3sig"
    assert (
        p2ToC3Obligations[0].sourceDisplayPortDeclaration.signalName == "p2sig"
    )


def test_back_and_forth_outer_ring_spans_grow_from_outer_wire_demand() -> None:
    """Back-and-forth fixture should widen the outer ring to outer demand."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")
    assert kernel is not None
    geometry = kernel.board_get().geometry

    westExtraFrame = geometry.zone_get("extra_routing_longitude", "west")
    eastExtraFrame = geometry.zone_get("extra_routing_longitude", "east")
    northExtraFrame = geometry.zone_get("extra_routing_latitude", "north")
    southExtraFrame = geometry.zone_get("extra_routing_latitude", "south")

    assert westExtraFrame is not None
    assert eastExtraFrame is not None
    assert northExtraFrame is not None
    assert southExtraFrame is not None
    assert westExtraFrame.frame.horizontalSpan == 6
    assert eastExtraFrame.frame.horizontalSpan == 6
    assert northExtraFrame.frame.verticalSpan == 6
    assert southExtraFrame.frame.verticalSpan == 6


def test_back_and_forth_board_terminal_map_contains_all_face_labels() -> None:
    """Board terminal map should expose every rendered face terminal."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")
    assert kernel is not None
    terminalPositions = (
        kernel.board_get().geometry.exactTerminalWorldPositionsByChip
    )

    assert sorted(terminalPositions["child.ts.c2()"].keys()) == [
        "c1ret",
        "c1sig",
        "c2ret",
        "c2sig",
        "p2ret",
        "p2sig",
    ]
    assert sorted(terminalPositions["parent.ts.p2()"].keys()) == [
        "c3ret",
        "c3sig",
        "p2ret",
        "p2sig",
    ]


def test_back_and_forth_outer_routes_realize_non_empty_points() -> None:
    """All selected outer routes should realize to non-empty point lists."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    solution = kernel.solver_get(board).solution_get()
    materialized = solution.board_materialize(board)

    outerPointCounts = {
        materializedWire.solvedWire.wiringSolution.topology.name_get(): len(
            materializedWire.routePoints
        )
        for materializedWire in materialized._materializedWires
        if (
            materializedWire.solvedWire.wiringSolution.topology.name_get().startswith(
                "wte_outer"
            )
        )
    }

    assert outerPointCounts["wte_outer_eastsignal_uturn"] > 0
    assert outerPointCounts["wte_outer_westbound_arc"] > 0
    assert outerPointCounts["wte_outer_eastreturn_uturn"] > 0
    assert outerPointCounts["wte_outer_eastbound_arc"] > 0


def test_back_and_forth_child_self_return_uses_eastreturn_uturn() -> None:
    """Child-band self return should select the east return U-turn."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    solution = kernel.solver_get(board).solution_get()

    matchingWires = tuple(
        solvedWire
        for solvedWire in solution.all_get()
        if (
            solvedWire.kernelWire.sourceEndpointText == "child.ts.c3().c3ret"
            and solvedWire.kernelWire.destinationEndpointText
            == "child.ts.c3().c3ret"
        )
    )

    assert len(matchingWires) == 1
    assert (
        matchingWires[0].wiringSolution.topology.name_get()
        == "wte_outer_eastreturn_uturn"
    )


def test_back_and_forth_materialized_report_shows_label_and_canonical_id() -> (
    None
):
    """Materialized report should show display labels and canonical ids."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    assert kernel is not None
    materialized = (
        kernel.solver_get(kernel.board_get())
        .solution_get()
        .board_materialize(kernel.board_get())
    )
    geometryText = materialized.geometry_sprint()

    assert (
        "│ source module │ source function │ source label │ source id │"
        in geometryText
    )
    assert (
        "│ child.ts      │ c2()            │ c1ret        │ p2sig     │"
        in geometryText
    )
    assert (
        "child.ts.c2().c1ret [id=p2sig]::[0]::xeLong[3]::xnLat[3]"
        "::xwLong[1]::[0]::parent.ts.p2().p2sig [id=p2sig]" in geometryText
    )


def test_back_and_forth_module_boundaries_clamp_to_chip_terminal_zones() -> (
    None
):
    """Back-and-forth module boxes should clamp to chip-terminal zones."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml")
    )

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    parentBoundary = board.boundary_get("module/parent.ts")
    childBoundary = board.boundary_get("module/child.ts")

    assert parentBoundary is not None
    assert parentBoundary.horizontalStart == 11
    assert parentBoundary.verticalStart == 13
    assert parentBoundary.horizontalEnd_calculate() - 1 == 42
    assert parentBoundary.verticalEnd_calculate() - 1 == 36

    assert childBoundary is not None
    assert childBoundary.horizontalStart == 91
    assert childBoundary.verticalStart == 9
    assert childBoundary.horizontalEnd_calculate() - 1 == 123
    assert childBoundary.verticalEnd_calculate() - 1 == 40


def test_back_and_forth_zone_1_3_has_no_rendered_board_cell_collisions() -> (
    None
):
    """Zone 1,3 should reduce to fan sharing only."""

    debugContextResult = contextResult_buildFromDocumentAndZone(
        _exampleDocumentDict_build("simple-circuit/back-and-forth.yaml"),
        columnIndex=1,
        rowIndex=3,
    )

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    materialized = (
        kernel.solver_get(board).solution_get().board_materialize(board)
    )

    collisions = materialized.collisions_get()
    assert collisions["counts"]["rendered_board_cell"] == 0


def test_backedge_example_materialized_outer_ring_remains_visible() -> None:
    """Backedge materialization should render visible outer-ring geometry."""

    debugContextResult = context_buildFromDocument(
        _exampleDocumentDict_build(
            "simple-circuit/rearch-external-backedge.yaml"
        )
    )

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    solution = kernel.solver_get(board).solution_get()
    materialized = solution.board_materialize(board)

    boundary = board.boundary_get("module/App.ts")
    assert boundary is not None
    assert boundary.horizontalStart == 7
    assert boundary.verticalStart == 5
    assert boundary.horizontalEnd_calculate() - 1 == 92
    assert boundary.verticalEnd_calculate() - 1 == 13

    geometryText = materialized.geometry_sprint()
    assert " 3:  ┌" in geometryText

    et = board.geometry_get().area_get("east/chip_terminal")
    efi = board.geometry_get().area_get("east/intra_routing_fan_in_out")
    assert et is not None
    assert efi is not None
    assert efi.horizontalEnd_calculate() - 1 < et.horizontalStart


def test_outer_child_uturn_selects_eastside_uturn_topology() -> None:
    """Child-side U-turn should select the eastside outer U-turn family."""

    topology = wireTopology_build(
        SolverWireInput(
            sourceEndpointText="src",
            destinationEndpointText="dst",
            sourceTerminalSide=ChipTerminalSide.EAST,
            zoneLocalGeometryKind=ZoneLocalGeometryKind.OUTER_CHILD_UTURN,
            callingStackDelta=0,
            isReturn=False,
        ),
        rotationSense=RoutingZoneChannelSense.CLOCKWISE,
    )

    assert tuple(hop.area for hop in topology.topology_get()) == (
        sfN.Efe,
        sfN.Ee,
        sfN.Ne,
        sfN.Em,
        sfN.Efi,
    )


def test_outer_parent_uturn_selects_westside_uturn_topology() -> None:
    """Parent-side U-turn should select the westside outer U-turn family."""

    topology = wireTopology_build(
        SolverWireInput(
            sourceEndpointText="src",
            destinationEndpointText="dst",
            sourceTerminalSide=ChipTerminalSide.WEST,
            zoneLocalGeometryKind=ZoneLocalGeometryKind.OUTER_PARENT_UTURN,
            callingStackDelta=0,
            isReturn=False,
        ),
        rotationSense=RoutingZoneChannelSense.CLOCKWISE,
    )

    assert tuple(hop.area for hop in topology.topology_get()) == (
        sfN.Wfi,
        sfN.Wm,
        sfN.Ne,
        sfN.We,
        sfN.Wfe,
    )


def test_outer_child_uturn_return_selects_eastreturn_topology() -> None:
    """Child-band return U-turn should stay east-sided."""

    topology = wireTopology_build(
        SolverWireInput(
            sourceEndpointText="src",
            destinationEndpointText="dst",
            sourceTerminalSide=ChipTerminalSide.EAST,
            zoneLocalGeometryKind=ZoneLocalGeometryKind.OUTER_CHILD_UTURN,
            callingStackDelta=0,
            isReturn=True,
        ),
        rotationSense=RoutingZoneChannelSense.CLOCKWISE,
    )

    assert topology.name_get() == "wte_outer_eastreturn_uturn"
    assert tuple(hop.area for hop in topology.topology_get()) == (
        sfN.Efi,
        sfN.Em,
        sfN.Se,
        sfN.Ee,
        sfN.Efe,
    )


def test_outer_parent_uturn_return_selects_westreturn_topology() -> None:
    """Parent-band return U-turn should stay west-sided."""

    topology = wireTopology_build(
        SolverWireInput(
            sourceEndpointText="src",
            destinationEndpointText="dst",
            sourceTerminalSide=ChipTerminalSide.WEST,
            zoneLocalGeometryKind=ZoneLocalGeometryKind.OUTER_PARENT_UTURN,
            callingStackDelta=0,
            isReturn=True,
        ),
        rotationSense=RoutingZoneChannelSense.CLOCKWISE,
    )

    assert topology.name_get() == "wte_outer_westreturn_uturn"
    assert tuple(hop.area for hop in topology.topology_get()) == (
        sfN.Wfe,
        sfN.We,
        sfN.Se,
        sfN.Wm,
        sfN.Wfi,
    )


def test_zone_chip_overlap_surface_reports_terminal_harmonization() -> None:
    """Zones should expose the first chip-terminal overlap resolution."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    overlap = zone.chipOverlap_get("east")

    assert overlap is not None
    assert overlap.dominantSide.value in {"west", "east"}
    assert overlap.targetColumnFrame.heightRows == max(
        overlap.westColumnFrame.heightRows,
        overlap.eastColumnFrame.heightRows,
    )
    assert overlap.westChipTargetFramesByName
    assert overlap.eastChipTargetFramesByName
    assert overlap.targetExtent == max(overlap.westExtent, overlap.eastExtent)
    assert overlap.westDelta >= 0
    assert overlap.eastDelta >= 0


def test_zone_chip_overlap_applied_surface_shifts_recessive_column() -> None:
    """Applied overlap should shift the recessive chip column in geometry."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    zone = debugContextResult.value.zones.zone_get(1, 1)
    applied = zone.chipOverlapApplied_get("east")

    assert applied is not None
    assert applied.mutationPlan.recessiveSide.value == "east"
    appliedZone = applied.eastBoard.geometry_get().zone_get(
        "chip_terminal",
        "west",
    )
    assert appliedZone is not None
    assert appliedZone.topLeft_get() == (
        applied.mutationPlan.targetRegionFrame.horizontalStart,
        applied.mutationPlan.targetRegionFrame.verticalStart,
    )
    chipPlacements = appliedZone.chips_get()
    assert chipPlacements
    assert chipPlacements[0].worldFrame_get().topLeft == (89, 8)


def test_board_geometry_exposes_first_class_geometry_zones() -> None:
    """Board geometry should expose first-class geometry-zone objects."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    geometry = board.geometry_get()
    geometryZones = geometry.zones_get()
    eastTerminalZone = geometry.zone_get("chip_terminal", "east")

    assert geometryZones
    assert isinstance(geometryZones[0], GeometryZone)
    assert eastTerminalZone is not None
    assert (
        board.geometry_get().zonesById[eastTerminalZone.regionId]
        is eastTerminalZone
    )
    assert eastTerminalZone.name_get() == "east/chip_terminal"
    assert eastTerminalZone.chips_get()
    assert "Proxy.ts.p1()" in eastTerminalZone.exactTerminals_get()
    assert eastTerminalZone.topLeft_get() == (
        eastTerminalZone.frame.horizontalStart,
        eastTerminalZone.frame.verticalStart,
    )
    assert eastTerminalZone.extent_get() == (
        eastTerminalZone.frame.horizontalSpan,
        eastTerminalZone.frame.verticalSpan,
    )
    assert eastTerminalZone.worldFrame_get().topLeft == (
        eastTerminalZone.topLeft_get()
    )


def test_symbolic_geometry_exprs_bind_into_board_mutation_objects() -> None:
    """Overlap geometry notation should compile into typed board selectors."""

    lhs = ZoneGeometryTarget(zoneRef="A", region=sfN.Et)
    rhs = ZoneGeometryTarget(zoneRef="B", region=sfN.Wt)
    relationExpr = zoneExtentMaxAlignRelation_build(
        lhs=lhs,
        rhs=rhs,
        connectivityKind=ZoneConnectivityKind.FIXED_OVERLAP,
    )
    mutationExpr = zonePaddingAddMutation_build(target=rhs, padding=4)

    relationResult = zoneAdjacencyConstraint_buildFromExpr(relationExpr)
    mutationResult = zoneGeometryMutation_buildFromExpr(mutationExpr)
    assert result_isOkCheck(relationResult)
    assert result_isOkCheck(mutationResult)
    relation = relationResult.value
    mutation = mutationResult.value

    etIdResult = boardRegionIdResult_fromSfN(sfN.Et)
    wtIdResult = boardRegionIdResult_fromSfN(sfN.Wt)
    assert result_isOkCheck(etIdResult) and result_isOkCheck(wtIdResult)
    assert relation.lhs.regionId == etIdResult.value
    assert relation.rhs.regionId == wtIdResult.value
    assert relation.connectivityKind is ZoneConnectivityKind.FIXED_OVERLAP
    assert mutation.selector.regionId == wtIdResult.value
    assert mutation.magnitude == 4
    face = sfN.Et.face_get()
    w_axis = sfN.Wi.axis_get()
    n_axis = sfN.Ni.axis_get()
    assert face is not None
    assert w_axis is not None
    assert n_axis is not None
    assert face.value == "east"
    assert w_axis.value == "horizontal"
    assert n_axis.value == "vertical"


def test_symbolic_geometry_tuple_surface_lowers_cleanly() -> None:
    """Top-layer symbolic tuple notation should lower into normalized IR."""

    operandsResult = zoneOperandsResult_build("A", "B")
    assert result_isOkCheck(operandsResult)
    A, B = operandsResult.value
    exprs = (
        (A.Et, "=max", B.Wt),
        (B.Ee, "+=", 4),
        (A.Et, "~", B.Wt),
    )

    lowered0 = geometryExprLoweredResult_build(exprs[0])
    lowered1 = geometryExprLoweredResult_build(exprs[1])
    lowered2 = geometryExprLoweredResult_build(exprs[2])

    assert result_isOkCheck(lowered0)
    assert result_isOkCheck(lowered1)
    assert result_isOkCheck(lowered2)
    assert isinstance(lowered0.value, ZoneRelationExpr)
    assert isinstance(lowered1.value, ZoneMutationExpr)
    assert isinstance(lowered2.value, ZoneRelationExpr)
    assert lowered0.value.kind is ZoneRelationKind.EXTENT_MAX_ALIGN
    assert lowered1.value.kind is ZoneMutationKind.PADDING_ADD
    assert lowered2.value.kind is ZoneRelationKind.EXTENT_MAX_ALIGN
    assert lowered0.value.lhs.region is sfN.Et
    assert lowered0.value.rhs.region is sfN.Wt
    assert lowered1.value.target.region is sfN.Ee
    assert lowered1.value.magnitude == 4


def test_symbolic_geometry_ops_build_from_tokens() -> None:
    """Top-layer operator tokens should round-trip through a factory."""

    operandsResult = zoneOperandsResult_build("A", "B")
    maxOpResult = zoneOpResult_build("=max")
    padOpResult = zoneOpResult_build("+=")

    assert result_isOkCheck(operandsResult)
    assert result_isOkCheck(maxOpResult)
    assert result_isOkCheck(padOpResult)
    A, B = operandsResult.value
    assert maxOpResult.value is GeometryOp.EXTENT_MAX_ALIGN
    assert padOpResult.value is GeometryOp.PADDING_ADD
    lowered0 = geometryExprLoweredResult_build((A.Et, maxOpResult.value, B.Wt))
    lowered1 = geometryExprLoweredResult_build((B.Ee, padOpResult.value, 4))

    assert result_isOkCheck(lowered0)
    assert result_isOkCheck(lowered1)
    assert isinstance(lowered0.value, ZoneRelationExpr)
    assert isinstance(lowered1.value, ZoneMutationExpr)
    assert lowered0.value.kind is ZoneRelationKind.EXTENT_MAX_ALIGN
    assert lowered1.value.kind is ZoneMutationKind.PADDING_ADD


def test_east_west_overlap_expression_bank_exposes_terminal_rule() -> None:
    """Overlap doctrine should exist as a named symbolic expression bank."""

    operandsResult = zoneOperandsResult_build("A", "B")
    assert result_isOkCheck(operandsResult)
    A, B = operandsResult.value
    bank: ZoneOverlapExprBank = eastWestZoneOverlapExprBank_build(A, B)

    assert bank.terminalHarmonize == ((A.Et, "=max", B.Wt),)
    assert bank.all_get() == ((A.Et, "=max", B.Wt),)


def test_chip_terminal_coupling_moves_module_boundary_and_downstream() -> None:
    """Chip-terminal coupling should express and apply downstream reaction."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    geometry = board.geometry_get()
    familyResult = chipTerminalCouplingFamilyResult_build(geometry, "east")
    symbolicResult = chipTerminalCouplingSymbolicExprsResult_build(
        geometry,
        "east",
    )

    assert result_isOkCheck(familyResult)
    assert result_isOkCheck(symbolicResult)
    symbolicExprs: tuple[GeometryCouplingSymbolicExpr, ...] = (
        symbolicResult.value
    )
    couplingOperandResult = zoneCouplingOperandResult_build("A")
    assert result_isOkCheck(couplingOperandResult)
    A = couplingOperandResult.value
    assert (A.Et, "~=>", A.chips) in symbolicExprs
    assert (
        A.Et,
        "~=>",
        A.moduleOperand_build("Proxy.ts"),
    ) in symbolicExprs
    assert (A.Et, "~->", A.Ee) in symbolicExprs
    loweredSymbolicResult = geometryCouplingExpr_buildFromSymbolic(
        (A.Et, "~->", A.Ee)
    )
    assert result_isOkCheck(loweredSymbolicResult)
    family = familyResult.value
    assert any(
        expr.op is GeometryCouplingOp.PROPAGATES_DRAG
        and expr.dependent.label_sprint() == "chips"
        for expr in family.expressions
    )
    assert any(
        expr.op is GeometryCouplingOp.PROPAGATES_DRAG
        and expr.dependent.label_sprint() == "module/Proxy.ts"
        for expr in family.expressions
    )
    assert any(
        expr.op is GeometryCouplingOp.PROPAGATES_DISPLACE
        and expr.dependent.label_sprint() == "east/extra_routing_longitude"
        for expr in family.expressions
    )

    beforeBoundary = geometry.effectiveBoundaryFrame_get("module/Proxy.ts")
    beforeExtraLong = geometry.zone_get("extra_routing_longitude", "east")
    assert beforeBoundary is not None
    assert beforeExtraLong is not None

    appliedResult = chipTerminalCouplingAppliedResult_build(
        geometry,
        "east",
        deltaColumns=5,
    )
    assert result_isOkCheck(appliedResult)
    shiftedGeometry = appliedResult.value.geometry

    afterBoundary = shiftedGeometry.effectiveBoundaryFrame_get(
        "module/Proxy.ts"
    )
    afterExtraLong = shiftedGeometry.zone_get(
        "extra_routing_longitude",
        "east",
    )
    assert afterBoundary is not None
    assert afterExtraLong is not None
    assert afterBoundary.horizontalStart == beforeBoundary.horizontalStart + 5
    assert (
        afterExtraLong.frame.horizontalStart
        == beforeExtraLong.frame.horizontalStart + 5
    )


def test_zone_operand_factory_is_cached() -> None:
    """Zone operand factories should return stable cached roots."""

    operandA0 = zoneOperandResult_build("A")
    operandA1 = zoneOperandResult_build("A")

    assert result_isOkCheck(operandA0)
    assert result_isOkCheck(operandA1)
    assert operandA0.value is operandA1.value
    assert operandA0.value.Et.region is sfN.Et


def test_symbolic_geometry_result_builders_fail_cleanly() -> None:
    """Notation-layer builders should fail via `Result`, not exceptions."""

    assert result_isErrCheck(zoneOperandResult_build(""))
    assert result_isErrCheck(zoneOpResult_build("bogus"))


def test_kernel_wiring_handle_exposes_quarantine_symbolic_surface() -> None:
    """Kernel wiring should expose solve and channel entry points."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    assert dir(kernel) == [
        "areas_get",
        "board_get",
        "raw_get",
        "routes_text",
        "schematic_text",
        "side_get",
        "solver_get",
        "wiring_get",
        "yaml_text",
    ]
    assert "world:" in kernel.yaml_sprint()
    board = kernel.board_get()
    assert dir(board) == [
        "backend_get",
        "boundaries_get",
        "boundary_get",
        "channels_get",
        "chipPlacementPolicy_get",
        "chipPlacementPolicy_set",
        "effective_get",
        "geometry_get",
        "geometry_text",
        "minimumCrossbarSpan_get",
        "model_get",
        "problems_get",
        "sense_get",
        "substrate_get",
        "summary_text",
        "terminal_get",
        "terminals_get",
        "topology_get",
        "validation_text",
        "worldFrame_get",
        "worldGridCoord_get",
    ]
    wiring = kernel.wiring_get()
    assert dir(wiring) == [
        "algebraic_text",
        "all_get",
        "board_get",
        "channels_get",
        "list_text",
        "solver_get",
    ]
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    assert dir(solver) == [
        "algebraic_text",
        "laneFillSense_get",
        "list_text",
        "policy_set",
        "rotationSense_get",
        "solution_get",
        "summary_text",
        "wiring_get",
    ]
    solution = solver.solution_get()
    assert dir(solution) == [
        "algebraic_text",
        "all_get",
        "board_materialize",
        "list_text",
        "wiring_get",
    ]
    chip = debugContextResult.value.chips.chip_get("Proxy.ts", "p5()")
    assert dir(chip) == [
        "child_get",
        "children_get",
        "dimensions_get",
        "geometry_get",
        "geometry_text",
        "height_get",
        "internalBoard_get",
        "location_get",
        "locations_get",
        "placement_get",
        "raw_get",
        "routes_get",
        "schematic_text",
        "size_get",
        "summary_text",
        "terminals_get",
        "terminals_getLocalPositions",
        "terminals_getWorldPositions",
        "title_get",
        "width_get",
        "worldFrame_get",
    ]


def test_chip_internal_board_harmonizer_exposes_board_compatible_schema() -> (
    None
):
    """A chip with internal wiring should expose a chip-local board kernel."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    chip = debugContextResult.value.chips.chip_get("Hub.ts", "process()")
    kernel = chip.internalBoard_get()

    assert dir(kernel) == [
        "areas_get",
        "board_get",
        "raw_get",
        "routes_text",
        "schematic_text",
        "side_get",
        "solver_get",
        "wiring_get",
        "yaml_text",
    ]
    assert kernel.side_get() == "internal"
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    solution = solver.solution_get()
    materialized = solution.board_materialize(board)

    assert "s1:out1" in kernel.routes_sprint()
    assert "s1.r1()" in kernel.schematic_sprint()
    assert "out1.ret1()" in kernel.schematic_sprint()
    assert "module: InternalWest.ts" in kernel.yaml_sprint()
    assert "func: s1.r1()" in kernel.yaml_sprint()
    assert "func: out1.ret1()" in kernel.yaml_sprint()
    assert (
        "InternalWest.ts.s1.r1().s1 [id=s1]:"
        "InternalEast.ts.out1.ret1().out1 [id=out1]"
        in kernel.wiring_get().list_sprint()
    )
    assert (
        "InternalWest.ts.s1.r1().s1 [id=s1]::wf[0]::wLong[1]::nLat[1]"
        in solution.list_sprint()
    )
    assert "InternalWest.ts" in materialized.geometry_sprint()
    assert "InternalEast.ts" in materialized.geometry_sprint()
    assert "output terminal label: s1" in materialized.wiring_sprint()
    assert "output terminal id: s1" in materialized.wiring_sprint()
    assert "input terminal label: out1" in materialized.wiring_sprint()
    assert "input terminal id: out1" in materialized.wiring_sprint()


def test_relaxation_respects_zone_bounds() -> None:
    """Relaxation shifts Ni/Si frames within geometry bounds.

    Ni may shift northward and Si southward (depending on policy) but must not
    overlap the Nfi/Sfi fan regions — that hard boundary is enforced by
    _regionFramesShifted_build returning None. With Ni/Si sized only from
    parent-to-child demand, some boards no longer have enough slack for the
    MINIMAL and SYMMETRIC policies to diverge.
    """

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    chip = debugContextResult.value.chips.chip_get("Hub.ts", "process()")
    kernel = chip.internalBoard_get()
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    solution = solver.solution_get()

    minimal = solution.board_materialize(
        board,
        policy=BoardMaterializePolicy(
            relaxationSymmetry=BoardRelaxationSymmetry.MINIMAL
        ),
    )
    symmetric = solution.board_materialize(
        board,
        policy=BoardMaterializePolicy(
            relaxationSymmetry=BoardRelaxationSymmetry.SYMMETRIC
        ),
    )

    assert symmetric.geometry_sprint() == minimal.geometry_sprint()

    nfiFrame = board.geometry.regionFramesByName.get(
        "north/intra_routing_fan_in_out"
    )
    sfiFrame = board.geometry.regionFramesByName.get(
        "south/intra_routing_fan_in_out"
    )
    niFrame = board.geometry.regionFramesByName.get(
        "north/intra_routing_latitude"
    )
    siFrame = board.geometry.regionFramesByName.get(
        "south/intra_routing_latitude"
    )
    assert niFrame is not None
    assert siFrame is not None
    assert nfiFrame is not None
    assert sfiFrame is not None
    niHardFloor = nfiFrame.verticalEnd_calculate()
    siHardCeiling = sfiFrame.verticalStart

    for wire in minimal._materializedWires:
        for point in wire.routePoints:
            col, row = point
            if (
                niFrame.horizontalStart
                <= col
                < niFrame.horizontalEnd_calculate()
            ):
                assert row >= niHardFloor, (
                    "nLat wire at row "
                    f"{row} above Nfi hard floor {niHardFloor}"
                )
            if (
                siFrame.horizontalStart
                <= col
                < siFrame.horizontalEnd_calculate()
            ):
                assert row < siHardCeiling, (
                    "sLat wire at row "
                    f"{row} below Sfi hard ceiling {siHardCeiling}"
                )


def test_kernel_channel_and_lane_handles_reflect_current_board_geometry() -> (
    None
):
    """The quarantine board view should expose current channel lane counts."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    channels = board.channels_get()

    assert channels.list_sprint().splitlines() == [
        "wLong (10 lanes)",
        "nLat (5 lanes)",
        "eLong (10 lanes)",
        "sLat (5 lanes)",
        "xwLong (2 lanes)",
        "xnLat (2 lanes)",
        "xeLong (2 lanes)",
        "xsLat (2 lanes)",
    ]
    assert board.summary_sprint().splitlines()[0] == (
        "board intra of GridCoord(columnIndex=1, rowIndex=1)"
    )
    assert board.worldGridCoord_get() == GridCoord(columnIndex=1, rowIndex=1)
    assert board.worldFrame_get().topLeft == (22, 5)
    assert board.backend_get() == "new"
    assert board.sense_get().value == "WTE"
    assert board.minimumCrossbarSpan_get() == 10
    substrateBoard = board.substrate_get()
    effectiveBoard = board.effective_get()
    assert effectiveBoard is board
    assert substrateBoard is not board
    assert substrateBoard.boundaries_get() == {}

    assert set(effectiveBoard.boundaries_get()) == {
        "module/App.ts",
        "module/Proxy.ts",
    }
    proxyBoundary = effectiveBoard.boundary_get("module/Proxy.ts")
    assert proxyBoundary is not None
    proxyPlacement = (
        effectiveBoard.model_get().geometry.chipDrawPlacementsByChip[
            "Proxy.ts.p1()"
        ]
    )
    assert proxyPlacement.drawTopLeft[0] == (
        proxyBoundary.horizontalStart
        + effectiveBoard.model_get().doctrine.moduleBoundaryPaddingCells
    )
    geometryText = board.geometry_sprint()
    assert "legend:" in geometryText
    assert "north/intra_routing_latitude" in geometryText
    assert "west/intra_routing_longitude" in geometryText
    assert (
        board.geometry_get().area_get("west/intra_routing_longitude:upper")
        is not None
    )
    assert (
        board.geometry_get().area_get("west/intra_routing_longitude:lower")
        is not None
    )
    boundaries = board.boundaries_get()
    assert set(boundaries) == {"module/App.ts", "module/Proxy.ts"}
    assert boundaries["module/App.ts"] == board.boundary_get("module/App.ts")
    assert boundaries["module/Proxy.ts"] == board.boundary_get(
        "module/Proxy.ts"
    )
    terminalPoint = board.terminal_get("App.ts.main()", "s1")
    assert terminalPoint == (36, 23)
    terminalGroups = board.terminals_get()
    assert terminalGroups["App.ts.main()"]["s1"] == (36, 23)
    assert board.problems_get() == ()
    assert board.validation_sprint() == "board validation:\n  <none>"
    geometryTextWithOffset = board.geometry_sprint(columnOffset=0)
    assert geometryTextWithOffset.splitlines()[0].startswith(" 0: 0")
    assert "82" in geometryTextWithOffset.splitlines()[0]
    assert geometryTextWithOffset != geometryText
    assert substrateBoard.geometry_sprint(
        columnOffset=0
    ) != effectiveBoard.geometry_sprint(columnOffset=0)

    northLanes = channels.channel_get("nLat")
    assert northLanes is not None
    lanes = northLanes.lanes_get()
    assert lanes.count_get() == 5
    lane = lanes.lane_get(1)
    assert lane is not None
    assert lane.canonicalName_get() == "nLat[1]"


def test_sfn_owns_canonical_region_symbols() -> None:
    """Named region glyphs should come from `sfN`, not inspect-local tables."""

    assert sfN.symbolFromRegionKey_get(sfN.Wi.region_key or "") == "🭲"
    assert sfN.symbolFromRegionKey_get(sfN.Efi.region_key or "") == "🮥"
    assert (
        sfN.symbolFromRegionKey_get("west/intra_routing_longitude:tag") == "🭲"
    )


def test_inspect_region_symbol_projection_uses_sfn_truth_first() -> None:
    """Inspect rendering should project `sfN` glyph truth for named regions."""

    assert regionSymbol_get(sfN.Wi.region_key or "") == sfN.Wi.symbol
    assert regionSymbol_get(sfN.Sfi.region_key or "") == sfN.Sfi.symbol
    assert regionSymbol_get("west/inter_routing_transition") == "X"


def test_wiringSolution_forward_laneMap_get() -> None:
    """Forward WTE lane mapping should use board capacity on east reverse."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    laneCounts = boardChannelLaneCounts_build(board)
    wiringSolution = WiringSolution(
        topology=WTE_INTRA_FORWARD,
        channelLaneCounts=laneCounts,
    )

    for index in range(5):
        wiringSolution.wire_add(
            source=f"App.ts.main().s{index + 1}",
            sink=f"Proxy.ts.p1().s{index + 1}",
        )

    assert wiringSolution.laneMap_get(0) == {
        sfN.Wi: 1,
        sfN.Ni: 1,
        sfN.Ei: 10,
    }
    assert wiringSolution.laneMap_get(4) == {
        sfN.Wi: 5,
        sfN.Ni: 5,
        sfN.Ei: 6,
    }


def test_wiringSolution_return_laneMap_get() -> None:
    """Return WTE lane mapping should reverse south and west shell hops."""

    wiringSolution = WiringSolution(topology=WTE_INTRA_RETURN)

    for index in range(5):
        wiringSolution.wire_add(
            source=f"Proxy.ts.p1().r{index + 1}",
            sink=f"App.ts.main().r{index + 1}",
        )

    assert wiringSolution.laneMap_get(0) == {
        sfN.Ei: 1,
        sfN.Si: 5,
        sfN.Wi: 5,
    }
    assert wiringSolution.laneMap_get(4) == {
        sfN.Ei: 5,
        sfN.Si: 1,
        sfN.Wi: 1,
    }


def test_wiringSolution_laneCount_get_isExplicit() -> None:
    """Lane count should be explicit bundle state, not derived on demand."""

    wiringSolution = WiringSolution(topology=WTE_INTRA_FORWARD)

    assert wiringSolution.laneCount_get() == 0
    wiringSolution.wire_add(
        source="App.ts.main().s1",
        sink="Proxy.ts.p1().s1",
    )
    wiringSolution.wire_add(
        source="App.ts.main().s2",
        sink="Proxy.ts.p1().s2",
    )

    assert wiringSolution.laneCount_get() == 2
    assert len(wiringSolution.paths_get()) == 2
    assert wiringSolution.kernel_wiring == [
        "App.ts.main().s1 -> Proxy.ts.p1().s1",
        "App.ts.main().s2 -> Proxy.ts.p1().s2",
    ]


def test_wiringSolution_isPerInstance_notShared() -> None:
    """Separate WiringSolution objects should not share mutable lane state."""

    firstWiringSolution = WiringSolution(topology=WTE_INTRA_FORWARD)
    secondWiringSolution = WiringSolution(topology=WTE_INTRA_FORWARD)

    firstWiringSolution.wire_add(
        source="App.ts.main().s1",
        sink="Proxy.ts.p1().s1",
    )

    assert firstWiringSolution.laneCount_get() == 1
    assert secondWiringSolution.laneCount_get() == 0
    assert len(firstWiringSolution.paths_get()) == 1
    assert len(secondWiringSolution.paths_get()) == 0
    assert firstWiringSolution.kernel_wiring == [
        "App.ts.main().s1 -> Proxy.ts.p1().s1"
    ]
    assert secondWiringSolution.kernel_wiring == []


def test_quarantine_symbolic_solver_emits_forward_and_return_paths() -> None:
    """The first quarantine solver should emit the agreed intra/WTE algebra."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    assert solver.algebraic_sprint("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]::Proxy.ts.p1().s1"
    )
    assert solver.algebraic_sprint("Proxy.ts.p1().r1") == (
        "Proxy.ts.p1().r1::ef[0]::eLong[1]::sLat[5]::wLong[10]::wf[0]::App.ts.main().r1"
    )


def test_quarantine_symbolic_solution_carries_structured_state() -> None:
    """Solved wires should retain structured path and bundle ownership."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    solution = solver.solution_get()
    solvedWire = next(
        wire
        for wire in solution.all_get()
        if wire.kernelWire.sourceEndpointText == "App.ts.main().s1"
    )

    assert solvedWire.algebraicPath.source == "App.ts.main().s1"
    assert solvedWire.algebraicPath.sink == "Proxy.ts.p1().s1"
    assert solvedWire.wireIndex == 0
    assert solvedWire.wiringSolution.laneCount_get() == 5
    assert solvedWire.wiringSolution.kernel_wiring[0] == (
        "App.ts.main().s1 -> Proxy.ts.p1().s1"
    )
    assert solvedWire.algebraicPathText == (
        "App.ts.main().s1 [id=s1]::wf[0]::wLong[1]::nLat[1]::"
        "eLong[10]::ef[0]::Proxy.ts.p1().s1 [id=s1]"
    )


def test_structured_realizer_entryPoint_matches_legacy_path_geometry() -> None:
    """Structured realizer entry point should match the legacy string shim."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    solution = solver.solution_get()
    solvedWire = next(
        wire
        for wire in solution.all_get()
        if wire.kernelWire.sourceEndpointText == "App.ts.main().s1"
    )
    sourceAttachPoint = board.terminal_get(
        solvedWire.kernelWire.sourceEndpointText.rsplit(".", 1)[0],
        solvedWire.kernelWire.sourceEndpointText.rsplit(".", 1)[1],
    )
    destinationAttachPoint = board.terminal_get(
        solvedWire.kernelWire.destinationEndpointText.rsplit(".", 1)[0],
        solvedWire.kernelWire.destinationEndpointText.rsplit(".", 1)[1],
    )

    assert sourceAttachPoint is not None
    assert destinationAttachPoint is not None
    structuredRealization = algebraicRouteRealization_buildFromPath(
        algebraicPath=solvedWire.algebraicPath,
        laneMap=solvedWire.wiringSolution.laneMap_get(solvedWire.wireIndex),
        sourceAttachPoint=sourceAttachPoint,
        destinationAttachPoint=destinationAttachPoint,
        regionFramesByName=board.geometry.regionFramesByName,
    )
    legacyRealization = algebraicRouteRealization_build(
        algebraicPathText=solvedWire.algebraicPathText,
        sourceAttachPoint=sourceAttachPoint,
        destinationAttachPoint=destinationAttachPoint,
        regionFramesByName=board.geometry.regionFramesByName,
    )

    assert structuredRealization == legacyRealization


def test_structured_realizer_can_materialize_extra_ring_path() -> None:
    """Extra-ring structured paths should realize to non-empty world routes."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    wiringSolution = WiringSolution(
        topology=WTE_OUTER_EASTBOUND_ARC,
        channelLaneCounts=boardChannelLaneCounts_build(board),
    )
    wiringSolution.wire_add(
        "App.ts.main().s1",
        "Proxy.ts.p1().s1",
    )
    algebraicPath = wiringSolution.paths_get()[0]
    laneMap = wiringSolution.laneMap_get(0)
    sourceAttachPoint = board.terminal_get("App.ts.main()", "s1")
    destinationAttachPoint = board.terminal_get("Proxy.ts.p1()", "s1")

    assert sourceAttachPoint is not None
    assert destinationAttachPoint is not None
    realization = algebraicRouteRealization_buildFromPath(
        algebraicPath=algebraicPath,
        laneMap=laneMap,
        sourceAttachPoint=sourceAttachPoint,
        destinationAttachPoint=destinationAttachPoint,
        regionFramesByName=board.geometry.regionFramesByName,
    )

    assert realization.routePoints
    assert realization.routeCells
    assert any(
        point[0] < sourceAttachPoint[0] or point[0] > destinationAttachPoint[0]
        for point in realization.routePoints
    )


def test_quarantine_solver_can_resolve_with_derived_policy() -> None:
    """The quarantine solver should allow REPL policy experiments."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    variant = solver.policy_set(
        rotationSense=RoutingZoneChannelSense.ANTICLOCKWISE
    )

    assert variant.rotationSense_get() is RoutingZoneChannelSense.ANTICLOCKWISE
    assert variant.laneFillSense_get() is RoutingLaneAttachmentSense.FROM_START
    assert variant.algebraic_sprint("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]::wLong[1]::sLat[1]::eLong[1]::ef[0]::Proxy.ts.p1().s1"
    )


def test_symbolic_solution_can_materialize_on_board() -> None:
    """A symbolic solution should materialize into inspectable geometry."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    replLocals: dict[str, Any] = {}
    replLocals.update(
        _replLocals_build(debugContextResult.value, replLocals=replLocals)
    )
    assert replLocals["board_backend_get"]() == "new"
    assert replLocals["board_backend_set"]("legacy") == "legacy"
    assert replLocals["board_backend_get"]() == "legacy"
    assert replLocals["board_backend_set"]("new") == "new"
    assert replLocals["board_backend_get"]() == "new"
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    solution = solver.solution_get()
    materialized = replLocals["solution_materialize"](board, solution)

    assert dir(materialized) == [
        "algebraicWorld_text",
        "boundaryViolations_get",
        "boundaryViolations_text",
        "collisions_get",
        "collisions_text",
        "geometryRelaxed_text",
        "geometry_text",
        "occupancyViolations_get",
        "occupancyViolations_text",
        "occupancy_text",
        "relaxedRegionFrames_get",
        "summary_text",
        "wiring_text",
    ]
    assert (
        "materialized solution on board intra of "
        "GridCoord(columnIndex=1, rowIndex=1)" in materialized.summary_sprint()
    )
    assert "output terminal label: s1" in materialized.wiring_sprint()
    assert "output terminal id: s1" in materialized.wiring_sprint()
    assert "input terminal label: s1" in materialized.wiring_sprint()
    assert "input terminal id: s1" in materialized.wiring_sprint()
    assert "topology: wte_intra_forward" in materialized.wiring_sprint()
    assert materialized.algebraicWorld_sprint("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]@(23,36)::wLong[1]@(23,50)::nLat[1]@(14,60)::"
        "eLong[10]@(14,79)::ef[0]@(11,82)::Proxy.ts.p1().s1"
    )
    geometryText = materialized.geometry_sprint()
    assert "wires:" in geometryText
    assert "main()" in geometryText
    assert "•" in geometryText or "│" in geometryText or "─" in geometryText
    occupancyText = materialized.occupancy_sprint()
    assert "symbolic channel collisions:\n  <none>" in occupancyText
    assert "symbolic fan sharing:" in occupancyText
    assert (
        "eLong[10]: App.ts.main().s1 [id=s1]:Proxy.ts.p1().s1 [id=s1]"
        in occupancyText
    )
    assert "App.ts.main().s2 [id=s2]:Proxy.ts.p2().s2 [id=s2]" in (
        occupancyText
    )
    collisions = materialized.collisions_get()
    assert collisions["hasCollisions"] is True
    assert collisions["counts"]["boundary"] == 0
    assert collisions["counts"]["rendered_board_cell"] == 0
    assert collisions["counts"]["symbolic_fan"] == 2
    assert materialized.boundaryViolations_get() == []
    assert "boundary violations:" in materialized.boundaryViolations_sprint()
    assert "collisions:" in materialized.collisions_sprint()
    assert "boundary:" in materialized.collisions_sprint()


def test_centroid_spread_runs_to_completion_as_paired_bands() -> None:
    """Centroid spread should run to hard bounds as a paired Ni/Si move."""

    with Path("examples/hub.yaml").open() as handle:
        documentDict = yaml.safe_load(handle)

    debugContextResult = context_buildFromDocument(documentDict)

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    displacedGeometryResult = geometry_change(
        [(sfN.Wt, GeoArgScalar(-15), GeoOp.DISPLACE)],
        board.geometry_get(),
    )

    assert result_isOkCheck(displacedGeometryResult)
    displacedGeometry = boardGeometryBoundaryNormalized_build(
        displacedGeometryResult.value,
        moduleBoundaryPaddingCells=board.doctrine.moduleBoundaryPaddingCells,
    )
    displacedBoard = replace(board, geometry=displacedGeometry)
    solution = kernel.solver_get(displacedBoard).solution_get()

    routeInputsMutable: list[RealizerRouteInput] = []
    for solvedWire in solution.all_get():
        sourceAttachPoint = displacedBoard.terminal_get(
            solvedWire.algebraicPath.source.rsplit(".", 1)[0],
            solvedWire.algebraicPath.source.rsplit(".", 1)[1],
        )
        destinationAttachPoint = displacedBoard.terminal_get(
            solvedWire.algebraicPath.sink.rsplit(".", 1)[0],
            solvedWire.algebraicPath.sink.rsplit(".", 1)[1],
        )
        assert sourceAttachPoint is not None
        assert destinationAttachPoint is not None
        routeInputsMutable.append(
            (
                solvedWire.algebraicPathText,
                sourceAttachPoint,
                destinationAttachPoint,
            )
        )

    relaxedFrames = regionFramesRelaxed_build(
        tuple(routeInputsMutable),
        displacedBoard.geometry.regionFramesByName,
        BoardMaterializePolicy(),
    )

    assert relaxedFrames["north/intra_routing_latitude"].verticalStart == 14
    assert relaxedFrames["south/intra_routing_latitude"].verticalStart == 37
    assert relaxedFrames["north/intra_routing_fan_in_out"].verticalStart == 2
    assert relaxedFrames["south/intra_routing_fan_in_out"].verticalStart == 51


def test_chip_terminal_world_positions_align_with_chip_frame() -> None:
    """World terminal positions should land inside the rendered chip frame."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    chip = debugContextResult.value.chips.chip_get("Proxy.ts", "p5()")
    worldFrame = chip.worldFrame_get()

    assert worldFrame is not None
    terminalPositions = chip.terminals_getWorldPositions("west")
    assert terminalPositions == {
        "s5": (81, 41),
        "r5": (81, 42),
    }
    for terminalColumnIndex, terminalRowIndex in terminalPositions.values():
        assert (
            worldFrame.topLeft[0]
            <= terminalColumnIndex
            <= worldFrame.bottomRight[0]
        )
        assert (
            worldFrame.topLeft[1]
            <= terminalRowIndex
            <= worldFrame.bottomRight[1]
        )


def test_world_canvas_composes_effective_board_geometry() -> None:
    """World composition should use effective board geometry, not substrate."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)

    worldText = debugContextResult.value.world.gridCanvas_sprint()

    assert "╔═ layer/" in worldText
    assert "layer/" in worldText
    assert "s1─►┤" in worldText


def test_repl_load_executes_snippet_in_live_namespace(tmp_path: Path) -> None:
    """The REPL load helper should execute a snippet against live locals."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    replLocals: dict[str, Any] = {}
    replLocals.update(
        _replLocals_build(debugContextResult.value, replLocals=replLocals)
    )

    snippetPath = tmp_path / "hub_snippet.py"
    snippetPath.write_text(
        "\n".join(
            [
                "kernel = zones.zone_get(1, 1).kernel_get('intra')",
                "board = kernel.board_get()",
                "solver = kernel.solver_get(board)",
                "solution = solver.solution_get()",
                "materialized = solution.board_materialize(board)",
                "result_text = materialized.summary_sprint()",
            ]
        ),
        encoding="utf-8",
    )

    replLocals["load"](str(snippetPath))

    assert (
        "materialized solution on board intra of "
        "GridCoord(columnIndex=1, rowIndex=1)" in replLocals["result_text"]
    )
