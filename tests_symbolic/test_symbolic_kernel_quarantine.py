"""Quarantine symbolic-kernel solver tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from signalflow.board.doctrine import (
    BoardMaterializePolicy,
    BoardRelaxationSymmetry,
)
from signalflow.board.realizer import (
    algebraicRouteRealization_build,
    algebraicRouteRealization_buildFromPath,
)
from signalflow.board.solver import boardChannelLaneCounts_build
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import (
    ChipView,
    KernelBoardHandle,
    SignalFlowContext,
    ZoneHandle,
    _replLocals_build,
)
from signalflow.engine.inspect.geometry import regionSymbol_get
from signalflow.models import (
    GridCoord,
    RoutingLaneAttachmentSense,
    RoutingZoneChannelSense,
    result_isOkCheck,
)
from signalflow.notation import (
    WTE_INTRA_FORWARD,
    WTE_INTRA_RETURN,
    WiringSolution,
    sfN,
)


def _hubDocumentDict_build() -> dict:
    """Build the parsed `examples/hub.yaml` document."""

    hubPath = Path(__file__).resolve().parent.parent / "examples" / "hub.yaml"
    with hubPath.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_inspect_package_import_surface_smoke() -> None:
    """The inspect package should expose the post-split import surface."""

    assert SignalFlowContext.__module__ == "signalflow.engine.inspect.context"
    assert KernelBoardHandle.__module__ == (
        "signalflow.engine.inspect.primitives"
    )
    assert ChipView.__module__ == "signalflow.engine.inspect.surfaces"
    assert ZoneHandle.__module__ == "signalflow.engine.inspect.surfaces"
    assert callable(_replLocals_build)


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


def test_chip_internal_board_harmonizer_exposes_board_compatible_schema(
) -> None:
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
    assert "InternalWest.ts.s1.r1().s1:InternalEast.ts.out1.ret1().out1" in (
        kernel.wiring_get().list_sprint()
    )
    assert (
        "InternalWest.ts.s1.r1().s1::wf[0]::wLong[1]::nLat[1]"
        in solution.list_sprint()
    )
    assert "InternalWest.ts" in materialized.geometry_sprint()
    assert "InternalEast.ts" in materialized.geometry_sprint()
    assert "InternalWest.ts.s1.r1().s1:InternalEast.ts.out1.ret1().out1" in (
        materialized.wiring_sprint()
    )


def test_symmetric_relaxation_uses_live_board_axis() -> None:
    """Symmetric relaxation should diverge on re-anchored board geometry."""

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

    assert symmetric.geometry_sprint() != minimal.geometry_sprint()


def test_kernel_channel_and_lane_handles_reflect_current_board_geometry(
) -> None:
    """The quarantine board view should expose current channel lane counts."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    channels = board.channels_get()

    assert channels.list_sprint().splitlines() == [
        "wLong (10 lanes)",
        "nLat (10 lanes)",
        "eLong (10 lanes)",
        "sLat (10 lanes)",
        "xwLong (2 lanes)",
        "xnLat (2 lanes)",
        "xeLong (2 lanes)",
        "xsLat (2 lanes)",
    ]
    assert board.summary_sprint().splitlines()[0] == (
        "board intra of GridCoord(columnIndex=1, rowIndex=1)"
    )
    assert board.worldGridCoord_get() == GridCoord(columnIndex=1, rowIndex=1)
    assert board.worldFrame_get().topLeft == (19, 2)
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
    assert (
        proxyPlacement.drawTopLeft[0]
        == proxyBoundary.horizontalStart
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
    assert terminalPoint == (33, 21)
    terminalGroups = board.terminals_get()
    assert terminalGroups["App.ts.main()"]["s1"] == (33, 21)
    assert board.problems_get() == ()
    assert board.validation_sprint() == "board validation:\n  <none>"
    geometryTextWithOffset = board.geometry_sprint(columnOffset=0)
    assert geometryTextWithOffset.splitlines()[0].startswith(" 0: 0")
    assert "19" in geometryTextWithOffset.splitlines()[0]
    assert geometryTextWithOffset != geometryText
    assert substrateBoard.geometry_sprint(
        columnOffset=0
    ) != effectiveBoard.geometry_sprint(columnOffset=0)

    northLanes = channels.channel_get("nLat")
    assert northLanes is not None
    lanes = northLanes.lanes_get()
    assert lanes.count_get() == 10
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
        "Proxy.ts.p1().r1::ef[0]::eLong[1]::sLat[10]::wLong[10]::wf[0]::App.ts.main().r1"
    )


def test_quarantine_symbolic_solution_carries_structured_wiringSolution_state(
) -> None:
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
        "App.ts.main().s1::wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]::Proxy.ts.p1().s1"
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
        "geometry_text",
        "occupancyViolations_get",
        "occupancyViolations_text",
        "occupancy_text",
        "summary_text",
        "wiring_text",
    ]
    assert (
        "materialized solution on board intra of "
        "GridCoord(columnIndex=1, rowIndex=1)"
        in materialized.summary_sprint()
    )
    assert "App.ts.main().s1:Proxy.ts.p1().s1" in materialized.wiring_sprint()
    assert materialized.algebraicWorld_sprint("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]@(21,33)::wLong[1]@(21,45)::nLat[1]@(13,55)::"
        "eLong[10]@(13,74)::ef[0]@(9,75)::Proxy.ts.p1().s1"
    )
    geometryText = materialized.geometry_sprint()
    assert "wires:" in geometryText
    assert "main()" in geometryText
    assert "•" in geometryText or "│" in geometryText or "─" in geometryText
    occupancyText = materialized.occupancy_sprint()
    assert "symbolic channel collisions:\n  <none>" in occupancyText
    assert "symbolic fan sharing:" in occupancyText
    assert "wLong[1]: App.ts.main().s1:Proxy.ts.p1().s1" in occupancyText
    assert "nLat[2]: App.ts.main().s2:Proxy.ts.p2().s2" in occupancyText
    collisions = materialized.collisions_get()
    assert collisions["hasCollisions"] is True
    assert collisions["counts"]["boundary"] == 0
    assert collisions["counts"]["rendered_board_cell"] == 0
    assert collisions["counts"]["symbolic_fan"] == 2
    assert materialized.boundaryViolations_get() == []
    assert "boundary violations:" in materialized.boundaryViolations_sprint()
    assert "collisions:" in materialized.collisions_sprint()
    assert "boundary:" in materialized.collisions_sprint()


def test_chip_terminal_world_positions_align_with_chip_frame() -> None:
    """World terminal positions should land inside the rendered chip frame."""

    debugContextResult = context_buildFromDocument(_hubDocumentDict_build())

    assert result_isOkCheck(debugContextResult)
    chip = debugContextResult.value.chips.chip_get("Proxy.ts", "p5()")
    worldFrame = chip.worldFrame_get()

    assert worldFrame is not None
    terminalPositions = chip.terminals_getWorldPositions("west")
    assert terminalPositions == {
        "s5": (72, 41),
        "r5": (72, 42),
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

    assert "╔═ Proxy.ts ═════════════╗" in worldText
    assert "╫──s1─►┤" in worldText


def test_repl_load_executes_snippet_in_live_namespace(tmp_path) -> None:
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
        "GridCoord(columnIndex=1, rowIndex=1)"
        in replLocals["result_text"]
    )
