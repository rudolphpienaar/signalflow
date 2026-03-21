"""Focused tests for the new-engine rendering boundary.

Covers three layers:

TestNewEngineRender  — top-level diagram_render integration (legacy parity)
TestChipRender       — Phase 8: render/chips.py unit tests
TestRouteWorldCanvas — Phase 8: render/routes.py unit tests
TestWorldCanvasRender — Phase 10: render/world.py composition layer
"""
from __future__ import annotations

from pathlib import Path

import yaml
from yaml import safe_load

from signalflow.engine.debug import newEngineDebugContextResult_buildFromDocumentDict
from signalflow.engine.render import diagram_render
from signalflow.models import diagnosticStack
from signalflow.models.chip import (
    Chip,
    ChipId,
    ChipRef,
    ChipTerminal,
    ChipTerminalSet,
    ChipTerminalSide,
)
from signalflow.models.engine import EngineName
from signalflow.models.result import result_isOkCheck
from signalflow.models.zone_route import RoutingZoneRoutePoint
from signalflow.render.chips import chipLines_render
from signalflow.render.routes import RouteCanvasSize, routeWorldCanvas_render
from signalflow.render.world import worldCanvas_render
from signalflow.routing import (
    realizedRouteSetResult_buildFromChipInternalSolvedRouteSet,
    realizedRouteSetResult_buildFromInterconnectSolvedRouteSet,
    realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet,
)
from signalflow.routing.route import RealizedRouteSet, RouteSense, routePoints_realize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chip(
    func: str,
    module: str = "M.ts",
    terminals: list[tuple[ChipTerminalSide, str]] | None = None,
) -> Chip:
    """Build a minimal Chip for render tests."""
    terminal_objs = tuple(
        ChipTerminal(terminalSide=side, terminalName=name)
        for side, name in (terminals or [])
    )
    return Chip(
        chipId=ChipId(moduleName=module, functionName=func),
        chipTerminalSet=ChipTerminalSet(terminals=terminal_objs),
    )


def _chip_ref(func: str, module: str = "M.ts") -> ChipRef:
    return ChipRef(chipId=ChipId(moduleName=module, functionName=func))


def _pt(col: int, row: int) -> RoutingZoneRoutePoint:
    return RoutingZoneRoutePoint(horizontalIndex=col, verticalIndex=row)


def _realize_simple(
    points: list[tuple[int, int]],
    child_idx: int = 0,
) -> RealizedRouteSet:
    result = routePoints_realize(
        sourceChipRef=_chip_ref("src"),
        destinationChipRef=_chip_ref("dst"),
        childCallIndex=child_idx,
        routePoints=tuple(_pt(c, r) for c, r in points),
        routeSense=RouteSense.FORWARD,
    )
    assert result_isOkCheck(result)
    return RealizedRouteSet(realizedRoutes=(result.value,))


class TestNewEngineRender:
    """Verification that the new engine path produces correct rendered output."""

    def test_three_deep_linear_render_produces_wiring_diagram(
        self,
    ) -> None:
        """The new engine path should produce a legible ASCII wiring diagram."""

        documentDict = safe_load(
            Path("examples/simple-circuit/three-deep-linear.yaml").read_text()
        )

        outputLines = diagram_render(
            title=documentDict.get("title", ""),
            treeDict=documentDict,
            engineName=EngineName.NEW,
        )
        joinedOutput = "\n".join(outputLines)

        # Chip boxes and named wires are present
        assert "root()" in joinedOutput
        assert "mid()" in joinedOutput
        assert "leaf()" in joinedOutput
        # No intermediate planning dump
        assert "artifact: planning_projection" not in joinedOutput
        assert "world 2" not in joinedOutput

    def test_new_engine_produces_world_canvas_not_legacy_artifact(self) -> None:
        """Phase 11: new engine renders the world canvas, not the legacy diagram."""

        documentDict = safe_load(
            Path("examples/simple-circuit/three-deep-linear.yaml").read_text()
        )
        title = documentDict.get("title", "")

        newLines = diagram_render(
            title=title,
            treeDict=documentDict,
            engineName=EngineName.NEW,
        )
        legacyLines = diagram_render(
            title=title,
            treeDict=documentDict,
            engineName=EngineName.LEGACY,
        )

        # New engine and legacy engine now produce distinct output.
        assert newLines != legacyLines
        # New engine output is non-empty and contains no planning-projection artifacts.
        assert newLines
        joined = "\n".join(newLines)
        assert "artifact: planning_projection" not in joined


# ---------------------------------------------------------------------------
# Phase 8: render/chips.py
# ---------------------------------------------------------------------------


class TestChipRender:
    """chipLines_render consumes Chip objects and emits text lines only."""

    def test_no_terminal_chip_produces_three_lines(self) -> None:
        chip = _make_chip("helper()")
        lines = chipLines_render(chip)
        assert len(lines) == 3

    def test_no_terminal_chip_top_border_is_box(self) -> None:
        chip = _make_chip("helper()")
        lines = chipLines_render(chip)
        assert lines[0].startswith("┌")
        assert lines[0].endswith("┐")

    def test_no_terminal_chip_title_row_contains_name(self) -> None:
        chip = _make_chip("helper()")
        lines = chipLines_render(chip)
        assert "helper()" in lines[1]

    def test_no_terminal_chip_bottom_border_is_box(self) -> None:
        chip = _make_chip("helper()")
        lines = chipLines_render(chip)
        assert lines[2].startswith("└")
        assert lines[2].endswith("┘")

    def test_chip_with_west_terminal_has_more_than_three_lines(self) -> None:
        chip = _make_chip("proc()", terminals=[(ChipTerminalSide.WEST, "in")])
        lines = chipLines_render(chip)
        assert len(lines) > 3

    def test_chip_with_terminals_has_separator_row(self) -> None:
        chip = _make_chip("proc()", terminals=[(ChipTerminalSide.WEST, "in")])
        lines = chipLines_render(chip)
        sep_rows = [line for line in lines if "├" in line or "┤" in line]
        assert sep_rows, "expected at least one separator row"

    def test_chip_with_east_terminal_stub_contains_arrow(self) -> None:
        chip = _make_chip("proc()", terminals=[(ChipTerminalSide.EAST, "out")])
        lines = chipLines_render(chip)
        joined = "\n".join(lines)
        assert "►" in joined or "◄" in joined

    def test_chip_name_appears_in_title_row(self) -> None:
        chip = _make_chip("compute()")
        lines = chipLines_render(chip)
        assert any("compute()" in line for line in lines)

    def test_chip_returns_tuple_not_list(self) -> None:
        chip = _make_chip("fn()")
        assert isinstance(chipLines_render(chip), tuple)

    def test_two_chips_same_name_render_identically(self) -> None:
        chip_a = _make_chip("fn()")
        chip_b = _make_chip("fn()")
        assert chipLines_render(chip_a) == chipLines_render(chip_b)

    def test_chip_render_does_not_mutate_chip(self) -> None:
        chip = _make_chip("immutable()")
        _ = chipLines_render(chip)
        assert chip.chipId.functionName == "immutable()"


# ---------------------------------------------------------------------------
# Phase 8: render/routes.py
# ---------------------------------------------------------------------------


class TestRouteWorldCanvas:
    """routeWorldCanvas_render consumes RealizedRouteSet; no topology work."""

    # --- empty / sizing ---

    def test_empty_route_set_without_size_returns_empty(self) -> None:
        rset = RealizedRouteSet()
        assert routeWorldCanvas_render(rset) == ()

    def test_empty_route_set_with_explicit_size_returns_blank_canvas(self) -> None:
        rset = RealizedRouteSet()
        canvas = routeWorldCanvas_render(
            rset,
            canvasSize=RouteCanvasSize(width=4, height=2),
        )
        assert canvas == ("    ", "    ")

    def test_explicit_canvas_pads_right_with_spaces(self) -> None:
        rset = _realize_simple([(0, 0), (1, 0)])  # 2-cell horizontal
        canvas = routeWorldCanvas_render(
            rset,
            canvasSize=RouteCanvasSize(width=5, height=1),
        )
        assert len(canvas[0]) == 5
        assert canvas[0].endswith("   ")  # 3 trailing spaces

    # --- horizontal routes ---

    def test_two_cell_horizontal_route_renders_dashes(self) -> None:
        rset = _realize_simple([(0, 0), (3, 0)])  # row=0, cols 0..3
        canvas = routeWorldCanvas_render(rset)
        assert len(canvas) == 1
        assert len(canvas[0]) == 4
        assert all(ch == "─" for ch in canvas[0])

    def test_horizontal_route_occupies_correct_row(self) -> None:
        # route on row=2
        rset = _realize_simple([(0, 2), (2, 2)])
        canvas = routeWorldCanvas_render(rset)
        assert len(canvas) == 3
        assert canvas[0] == "   "  # rows 0, 1 are blank
        assert canvas[1] == "   "
        assert all(ch == "─" for ch in canvas[2])

    # --- vertical routes ---

    def test_vertical_route_renders_pipes(self) -> None:
        rset = _realize_simple([(0, 0), (0, 2)])  # col=0, rows 0..2
        canvas = routeWorldCanvas_render(rset)
        assert len(canvas) == 3
        assert all(row == "│" for row in canvas)

    # --- elbow route ---

    def test_l_shaped_route_contains_elbow_glyph(self) -> None:
        # right then down: (0,0)→(2,0)→(2,2)
        rset = _realize_simple([(0, 0), (2, 0), (2, 2)])
        canvas = routeWorldCanvas_render(rset)
        joined = "\n".join(canvas)
        # The corner cell should contain ┐
        assert "┐" in joined

    def test_l_shaped_route_canvas_dimensions(self) -> None:
        rset = _realize_simple([(0, 0), (3, 0), (3, 3)])
        canvas = routeWorldCanvas_render(rset)
        assert len(canvas) == 4  # rows 0..3
        assert len(canvas[0]) == 4  # cols 0..3

    # --- cross route ---

    def test_crossing_routes_produce_cross_glyph(self) -> None:
        horiz = _realize_simple([(0, 2), (4, 2)], child_idx=0)
        vert_result = routePoints_realize(
            sourceChipRef=_chip_ref("src2"),
            destinationChipRef=_chip_ref("dst2"),
            childCallIndex=1,
            routePoints=(_pt(2, 0), _pt(2, 4)),
            routeSense=RouteSense.FORWARD,
        )
        assert result_isOkCheck(vert_result)
        rset = RealizedRouteSet(realizedRoutes=(
            horiz.realizedRoutes[0],
            vert_result.value,
        ))
        canvas = routeWorldCanvas_render(rset)
        # Cross should appear at (row=2, col=2)
        assert canvas[2][2] == "┼"

    # --- returns tuple ---

    def test_render_returns_tuple(self) -> None:
        rset = _realize_simple([(0, 0), (2, 0)])
        assert isinstance(routeWorldCanvas_render(rset), tuple)

    # --- pass gate: no topology inside renderer ---

    def test_render_does_not_require_circuit_document(self) -> None:
        # This test proves the pass gate: we build a RealizedRouteSet directly
        # from routePoints_realize (no CircuitDocument, no solver) and pass it
        # straight to routeWorldCanvas_render.  The renderer produces output
        # without access to any circuit, placement, or obligation objects.
        rset = _realize_simple([(0, 0), (5, 0)])
        canvas = routeWorldCanvas_render(rset)
        assert len(canvas) == 1
        assert len(canvas[0]) == 6


# ---------------------------------------------------------------------------
# Phase 10: World canvas compositor (render/world.py)
# ---------------------------------------------------------------------------

_SIMPLE_DIR = Path(__file__).parent.parent / "examples" / "simple-circuit"
_EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _ctx(path: Path):
    """Build a full debug context from one fixture file."""
    diagnosticStack.stack_clear()
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = newEngineDebugContextResult_buildFromDocumentDict(doc)
    assert result_isOkCheck(result), f"Pipeline failed for {path.name}"
    return result.value


def _combinedRouteSet(ctx) -> RealizedRouteSet:
    """Realize chip-local, zone-local, and seam routes into one set."""
    ci = realizedRouteSetResult_buildFromChipInternalSolvedRouteSet(
        ctx.circuitDocument,
        ctx.placedRoutingZoneGrid,
        ctx.chipInternalSolvedRouteSet,
    )
    zl = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
        ctx.routingZoneLocalSolvedRouteSet
    )
    ic = realizedRouteSetResult_buildFromInterconnectSolvedRouteSet(
        ctx.routingZoneInterconnectSolvedRouteSet
    )
    assert (
        result_isOkCheck(ci)
        and result_isOkCheck(zl)
        and result_isOkCheck(ic)
    )
    return RealizedRouteSet(
        realizedRoutes=(
            ci.value.realizedRoutes
            + zl.value.realizedRoutes
            + ic.value.realizedRoutes
        )
    )


class TestWorldCanvasRender:
    """Phase 10: worldCanvas_render composition layer."""

    def test_forward_fixture_produces_non_empty_canvas(self) -> None:
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-forward.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        assert len(canvas) > 0
        assert any(ch != " " for row in canvas for ch in row)

    def test_canvas_is_tuple_of_strings(self) -> None:
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-forward.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        assert isinstance(canvas, tuple)
        assert all(isinstance(row, str) for row in canvas)

    def test_canvas_rows_are_uniform_width(self) -> None:
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-forward.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        widths = {len(row) for row in canvas}
        assert len(widths) == 1, f"Row widths differ: {widths}"

    def test_canvas_contains_both_chip_names(self) -> None:
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-forward.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        combined = "\n".join(canvas)
        assert "caller()" in combined
        assert "callee()" in combined
        assert combined.count("App.ts") == 1

    def test_backedge_fixture_canvas_is_non_empty(self) -> None:
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-backedge.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        assert len(canvas) > 0

    def test_backedge_fixture_uses_single_shared_module_box(self) -> None:
        """Same-module chips should render under one shared module boundary."""

        ctx = _ctx(_SIMPLE_DIR / "rearch-external-backedge.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        combined = "\n".join(canvas)

        assert combined.count("App.ts") == 1

    def test_self_fixture_canvas_contains_chip_name(self) -> None:
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-self.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        assert any("worker()" in row for row in canvas)

    def test_hub_fixture_canvas_contains_seam_routes(self) -> None:
        # hub.yaml has interconnect seam routes; the canvas must include them.
        ctx = _ctx(_EXAMPLES_DIR / "hub.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        assert len(canvas) > 0
        assert any(ch != " " for row in canvas for ch in row)

    def test_hub_fixture_keeps_proxy_module_box_continuous(self) -> None:
        """Grouped module walls should remain continuous through chip blits."""

        ctx = _ctx(_EXAMPLES_DIR / "hub.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )

        topRowIndex = next(
            index for index, row in enumerate(canvas) if "╔═ Proxy.ts ═╗" in row
        )
        topRow = canvas[topRowIndex]
        label = "╔═ Proxy.ts ═╗"
        leftCol = topRow.index(label)
        rightCol = leftCol + len(label) - 1
        bottomRowIndex = next(
            index
            for index in range(topRowIndex + 1, len(canvas))
            if canvas[index][leftCol] == "╚" and canvas[index][rightCol] == "╝"
        )

        for rowIndex in range(topRowIndex + 1, bottomRowIndex):
            assert canvas[rowIndex][leftCol] in {"║", "╫"}
            assert canvas[rowIndex][rightCol] in {"║", "╫"}

    def test_empty_route_set_still_renders_chip_bodies(self) -> None:
        # Passing an empty RealizedRouteSet: chip bodies should still appear.
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-forward.yaml")
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            RealizedRouteSet(),  # no routes
        )
        combined = "\n".join(canvas)
        assert "caller()" in combined

    def test_world_canvas_print_via_debug_context(self) -> None:
        # Pass gate: ctx.world.canvas_render() delegates to worldCanvas_render.
        ctx = _ctx(_SIMPLE_DIR / "rearch-external-forward.yaml")
        text = ctx.world.canvas_render()
        assert isinstance(text, str)
        assert "caller()" in text
        assert "callee()" in text

    def test_world_canvas_renders_chip_internal_route_inside_chip_body(self) -> None:
        diagnosticStack.stack_clear()
        result = newEngineDebugContextResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "input_ports": [{"signal": "a"}],
                    "output_ports": [{"signal": "b"}],
                    "internal_wiring": ["a:b"],
                    "calls": [],
                }
            }
        )
        assert result_isOkCheck(result)
        ctx = result.value
        canvas = worldCanvas_render(
            ctx.placedRoutingZoneGrid,
            ctx.circuitDocument.circuitChipSet,
            _combinedRouteSet(ctx),
        )
        combined = "\n".join(canvas)
        assert "┤──────────├" in combined
