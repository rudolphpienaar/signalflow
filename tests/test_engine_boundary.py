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
    "output_ports": [{"signal": "s", "return": "r"}],
    "calls": [
        {
            "module": "N",
            "func": "child()",
            "input_ports": [{"signal": "s", "return": "r"}],
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

    def test_diagram_render_new_engine_produces_wiring_diagram(self) -> None:
        """The new engine path should produce a legible ASCII wiring diagram."""

        outputLines = diagram_render(
            title="boundary test",
            treeDict=SIMPLE_TREE,
            engineName=EngineName.NEW,
        )
        joinedOutput = "\n".join(outputLines)

        assert "root()" in joinedOutput
        assert "child()" in joinedOutput
        assert "artifact: planning_projection" not in joinedOutput
        assert "world 1" not in joinedOutput

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

    def test_diagram_render_new_engine_differs_from_legacy_for_deep_tree(self) -> None:
        """Phase 11: new engine renders a world canvas distinct from legacy output."""

        treeDict = {
            "tree": {
                "module": "Root.ts",
                "func": "root()",
                "output_ports": [{"signal": "s", "return": "r"}],
                "calls": [
                    {
                        "module": "A.ts",
                        "func": "a()",
                        "input_ports": [{"signal": "s", "return": "r"}],
                        "output_ports": [{"signal": "s", "return": "r"}],
                        "calls": [
                            {
                                "module": "B.ts",
                                "func": "b()",
                                "input_ports": [{"signal": "s", "return": "r"}],
                                "calls": [],
                            }
                        ],
                    }
                ],
            }
        }
        newLines = diagram_render(
            title="",
            treeDict=treeDict,
            engineName=EngineName.NEW,
        )
        legacyLines = diagram_render(
            title="",
            treeDict=treeDict,
            engineName=EngineName.LEGACY,
        )

        # New engine and legacy engine now produce distinct output.
        assert newLines != legacyLines
        # New engine output contains chip names and no planning artifacts.
        joined = "\n".join(newLines)
        assert "root()" in joined
        assert "a()" in joined
        assert "b()" in joined
        assert "artifact: planning_projection" not in joined
