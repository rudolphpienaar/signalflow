"""Quarantine symbolic-kernel solver tests."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.engine import newEngineDebugContextResult_buildFromDocumentDict
from signalflow.engine.debug import _replLocals_build
from signalflow.models import (
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

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
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
    ]
    board = kernel.board_get()
    assert dir(board) == [
        "channels_get",
        "geometry_get",
        "geometry_text",
        "summary_text",
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
        "list_text",
        "wiring_get",
    ]
    chip = debugContextResult.value.chips.chip_get("Proxy.ts", "p5()")
    assert dir(chip) == [
        "child_get",
        "children_get",
        "dimensions_get",
        "height_get",
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


def test_kernel_channel_and_lane_handles_reflect_current_board_geometry() -> None:
    """The quarantine board view should expose current channel lane counts."""

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    channels = board.channels_get()

    assert channels.list_text().splitlines() == [
        "wLong (10 lanes)",
        "nLat (10 lanes)",
        "eLong (10 lanes)",
        "sLat (10 lanes)",
    ]
    assert board.summary_text().splitlines()[0] == "board intra of GridCoord(columnIndex=1, rowIndex=1)"
    geometryText = board.geometry_text()
    assert "legend:" in geometryText
    assert "north/intra_routing_latitude" in geometryText
    assert "west/intra_routing_longitude" in geometryText
    assert board.geometry_get().area_get("west/intra_routing_longitude:upper") is not None
    assert board.geometry_get().area_get("west/intra_routing_longitude:lower") is not None
    geometryTextWithOffset = board.geometry_text(columnOffset=0)
    assert geometryTextWithOffset.splitlines()[0].startswith(" 0: 0")
    assert "22" in geometryTextWithOffset.splitlines()[0]
    assert geometryTextWithOffset != geometryText

    northLanes = channels.channel_get("nLat")
    assert northLanes is not None
    lanes = northLanes.lanes_get()
    assert lanes.count_get() == 10
    lane = lanes.lane_get(1)
    assert lane is not None
    assert lane.canonicalName_get() == "nLat[1]"


def test_quarantine_symbolic_solver_emits_forward_and_return_paths() -> None:
    """The first quarantine solver should emit the agreed intra/WTE algebra."""

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    assert solver.algebraic_text("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]::wLong[1]::nLat[1]::eLong[10]::ef[0]::"
        "Proxy.ts.p1().s1"
    )
    assert solver.algebraic_text("Proxy.ts.p1().r1") == (
        "Proxy.ts.p1().r1::ef[0]::eLong[1]::sLat[6]::wLong[6]::wf[0]::"
        "App.ts.main().r1"
    )


def test_quarantine_solver_can_resolve_with_derived_policy() -> None:
    """The quarantine solver should allow REPL policy experiments."""

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
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
    assert variant.algebraic_text("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]::wLong[1]::sLat[1]::eLong[1]::ef[0]::"
        "Proxy.ts.p1().s1"
    )


def test_symbolic_solution_can_materialize_on_board() -> None:
    """A symbolic solution should materialize into inspectable board geometry."""

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)
    replLocals: dict[str, object] = {}
    replLocals.update(
        _replLocals_build(debugContextResult.value, replLocals=replLocals)
    )
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")

    assert kernel is not None
    board = kernel.board_get()
    solver = kernel.solver_get(board)
    solution = solver.solution_get()
    materialized = replLocals["solution_materialize"](board, solution)

    assert dir(materialized) == [
        "algebraicWorld_text",
        "geometry_text",
        "occupancy_text",
        "summary_text",
        "wiring_text",
    ]
    assert "materialized solution on board intra of GridCoord(columnIndex=1, rowIndex=1)" in materialized.summary_text()
    assert "App.ts.main().s1:Proxy.ts.p1().s1" in materialized.wiring_text()
    assert materialized.algebraicWorld_text("App.ts.main().s1") == (
        "App.ts.main().s1::wf[0]@(9,33)::wLong[1]@(9,38)::nLat[1]@(5,48)::"
        "eLong[10]@(5,67)::ef[0]@(9,68)::Proxy.ts.p1().s1"
    )
    geometryText = materialized.geometry_text()
    assert "wires:" in geometryText
    assert "main()" in geometryText
    assert "•" in geometryText or "│" in geometryText or "─" in geometryText
    occupancyText = materialized.occupancy_text()
    assert "symbolic channel collisions:\n  <none>" in occupancyText
    assert "symbolic fan sharing:" in occupancyText
    assert "wLong[1]: App.ts.main().s1:Proxy.ts.p1().s1" in occupancyText
    assert "nLat[2]: App.ts.main().s2:Proxy.ts.p2().s2" in occupancyText


def test_chip_terminal_world_positions_align_with_chip_frame() -> None:
    """World terminal positions should land inside the rendered chip frame."""

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
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


def test_repl_load_executes_snippet_in_live_namespace(tmp_path) -> None:
    """The REPL load helper should execute a snippet against live locals."""

    debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
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
                "materialized = solution_materialize(board, solution)",
                "result_text = materialized.summary_text()",
            ]
        ),
        encoding="utf-8",
    )

    replLocals["load"](str(snippetPath))

    assert "materialized solution on board intra of GridCoord(columnIndex=1, rowIndex=1)" in replLocals["result_text"]
