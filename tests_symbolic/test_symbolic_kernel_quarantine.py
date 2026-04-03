"""Quarantine symbolic-kernel solver tests."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.board.doctrine import (
    BoardMaterializePolicy,
    BoardRelaxationSymmetry,
)
from signalflow.engine import context_buildFromDocument
from signalflow.engine.debug import _replLocals_build, solution_materialize
from signalflow.models import (
    GridCoord,
    RoutingLaneAttachmentSense,
    RoutingZoneChannelSense,
    result_isOkCheck,
)


def _hubDocumentDict_build() -> dict:
    """Build the parsed `examples/hub.yaml` document."""

    hubPath = Path(__file__).resolve().parent.parent / "examples" / "hub.yaml"
    with hubPath.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_kernel_wiring_handle_exposes_quarantine_symbolic_surface() -> None:
    """Kernel wiring should expose channels and algebraic solve entry points."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

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


def test_chip_internal_board_harmonizer_exposes_board_compatible_schema() -> None:
    """A chip with internal_wiring should expose a real chip-local board kernel."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

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
    """Symmetric relaxation should diverge once board geometry is re-anchored."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

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


def test_kernel_channel_and_lane_handles_reflect_current_board_geometry() -> None:
    """The quarantine board view should expose current channel lane counts."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

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
    ]
    assert board.summary_sprint().splitlines()[0] == "board intra of GridCoord(columnIndex=1, rowIndex=1)"
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
    assert set(effectiveBoard.boundaries_get()) == {"module/App.ts", "module/Proxy.ts"}
    proxyBoundary = effectiveBoard.boundary_get("module/Proxy.ts")
    assert proxyBoundary is not None
    proxyPlacement = effectiveBoard.model_get().geometry.chipDrawPlacementsByChip["Proxy.ts.p1()"]
    assert (
        proxyPlacement.drawTopLeft[0]
        == proxyBoundary.horizontalStart
        + effectiveBoard.model_get().doctrine.moduleBoundaryPaddingCells
    )
    geometryText = board.geometry_sprint()
    assert "legend:" in geometryText
    assert "north/intra_routing_latitude" in geometryText
    assert "west/intra_routing_longitude" in geometryText
    assert board.geometry_get().area_get("west/intra_routing_longitude:upper") is not None
    assert board.geometry_get().area_get("west/intra_routing_longitude:lower") is not None
    boundaries = board.boundaries_get()
    assert set(boundaries) == {"module/App.ts", "module/Proxy.ts"}
    assert boundaries["module/App.ts"] == board.boundary_get("module/App.ts")
    assert boundaries["module/Proxy.ts"] == board.boundary_get("module/Proxy.ts")
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
    assert substrateBoard.geometry_sprint(columnOffset=0) != effectiveBoard.geometry_sprint(columnOffset=0)

    northLanes = channels.channel_get("nLat")
    assert northLanes is not None
    lanes = northLanes.lanes_get()
    assert lanes.count_get() == 10
    lane = lanes.lane_get(1)
    assert lane is not None
    assert lane.canonicalName_get() == "nLat[1]"


def test_quarantine_symbolic_solver_emits_forward_and_return_paths() -> None:
    """The first quarantine solver should emit the agreed intra/WTE algebra."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    assert solver.algebraic_sprint("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]::"
        "Proxy.ts.p1().s1"
    )
    assert solver.algebraic_sprint("Proxy.ts.p1().r1") == (
        "Proxy.ts.p1().r1::ef[0]::eLong[1]::sLat[6]::wLong[6]::wf[0]::"
        "App.ts.main().r1"
    )


def test_quarantine_solver_can_resolve_with_derived_policy() -> None:
    """The quarantine solver should allow REPL policy experiments."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

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
        "App.ts.main().s1::wf[0]::wLong[1]::sLat[1]::eLong[1]::ef[0]::"
        "Proxy.ts.p1().s1"
    )


def test_symbolic_solution_can_materialize_on_board() -> None:
    """A symbolic solution should materialize into inspectable board geometry."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)
    replLocals: dict[str, object] = {}
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
    assert "materialized solution on board intra of GridCoord(columnIndex=1, rowIndex=1)" in materialized.summary_sprint()
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

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

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
        assert worldFrame.topLeft[0] <= terminalColumnIndex <= worldFrame.bottomRight[0]
        assert worldFrame.topLeft[1] <= terminalRowIndex <= worldFrame.bottomRight[1]


def test_world_canvas_composes_effective_board_geometry() -> None:
    """World composition should use effective board geometry, not substrate."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)

    worldText = debugContextResult.value.world.gridCanvas_sprint()

    assert "╔═ Proxy.ts ═════════════╗" in worldText
    assert "╫──s1─►┤" in worldText


def test_repl_load_executes_snippet_in_live_namespace(tmp_path) -> None:
    """The REPL load helper should execute a snippet against live locals."""

    debugContextResult = context_buildFromDocument(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)
    replLocals: dict[str, object] = {}
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

    assert "materialized solution on board intra of GridCoord(columnIndex=1, rowIndex=1)" in replLocals["result_text"]
