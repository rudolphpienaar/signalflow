"""Tests for the top-level engine boundary and CLI defaults.

These tests verify the explicit runtime boundary between the top-level engine
path and the quarantined legacy engine path.
"""
from __future__ import annotations

from signalflow.__main__ import arguments_parse
from signalflow.engine.render import diagram_render
from signalflow.models.engine import EngineName

SIMPLE_TREE: dict = {
    "module": "M",
    "func": "root()",
    "calls": [
        {
            "module": "N",
            "func": "child()",
            "calls": [],
        }
    ],
}


class TestEngineBoundary:
    """Verification of engine dispatch and CLI defaults."""

    def test_arguments_parse_defaults_to_new_engine(self) -> None:
        """CLI parsing should default to the top-level engine path."""

        arguments = arguments_parse(["examples/root-multi-child.yaml"])

        assert arguments.engine == EngineName.NEW.value

    def test_diagram_render_dispatches_to_new_engine_status(self) -> None:
        """The new engine path should report the zone-grid runtime status."""

        outputLines = diagram_render(
            title="boundary test",
            treeDict=SIMPLE_TREE,
            engineName=EngineName.NEW,
        )
        joinedOutput = "\n".join(outputLines)

        assert "engine: new" in joinedOutput
        assert "status: pending" in joinedOutput
        assert "ingress: typed CircuitDocument" in joinedOutput
        assert "worldModel: RoutingZoneGrid" in joinedOutput
        assert "seamModel: RoutingZoneInterconnect" in joinedOutput

    def test_diagram_render_dispatches_to_legacy_renderer(self) -> None:
        """The legacy engine path should still use the legacy artifact renderer."""

        outputLines = diagram_render(
            title="boundary test",
            treeDict=SIMPLE_TREE,
            engineName=EngineName.LEGACY,
        )
        joinedOutput = "\n".join(outputLines)

        assert "root()" in joinedOutput
        assert "child()" in joinedOutput
        assert "engine: new" not in joinedOutput

    def test_diagram_render_new_engine_status_ignores_tree_shape_for_now(self) -> None:
        """The current new-engine runtime should report pending status uniformly."""

        outputLines = diagram_render(
            title="boundary test",
            treeDict={"tree": {"module": "M", "func": "root()", "calls": "bad"}},
            engineName=EngineName.NEW,
        )
        joinedOutput = "\n".join(outputLines)

        assert "engine: new" in joinedOutput
        assert "status: pending" in joinedOutput
        assert "planning: assignment + placement + route obligations" in joinedOutput
        assert "zone-grid solver path is not implemented yet" in joinedOutput
