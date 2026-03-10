"""End-to-end smoke tests for diagram_render."""

from pathlib import Path

import yaml

from signalflow.engine.render import diagram_render
from signalflow.models.node import Node

SIMPLE_TREE = {
    "module": "M",
    "func": "root()",
    "input_signal": None,
    "calls": [
        {
            "module": "N",
            "func": "child()",
            "input_signal": "sig",
            "calls": []
        }
    ]
}

DEEP_TREE = {
    "module": "A",
    "func": "a()",
    "signal": None,
    "calls": [
        {
            "module": "B",
            "func": "b()",
            "signal": "s1",
            "calls": [
                {
                    "module": "C",
                    "func": "c()",
                    "signal": "s2",
                    "calls": []
                }
            ]
        }
    ]
}


class TestDiagramRender:
    """Smoke tests for the top-level diagram renderer."""

    def test_returns_nonempty_list(self):
        """diagram_render should always return at least one output line."""
        lines = diagram_render("test", SIMPLE_TREE)
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_title_in_output(self):
        """The title banner should appear when a title is provided."""
        lines = diagram_render("My Title", SIMPLE_TREE)
        assert any('My Title' in line for line in lines)

    def test_func_label_in_output(self):
        """Rendered output should include both parent and child function labels."""
        lines = diagram_render("", SIMPLE_TREE)
        joined = '\n'.join(lines)
        assert 'root()' in joined
        assert 'child()' in joined

    def test_signal_label_in_output(self):
        """Rendered output should include the declared signal label."""
        lines = diagram_render("", SIMPLE_TREE)
        assert any('sig' in line for line in lines)

    def test_deep_tree_smoke(self):
        """A deeper tree should still render a multi-line diagram successfully."""
        lines = diagram_render("deep", DEEP_TREE)
        assert len(lines) > 5

    def test_no_title(self):
        """No title banner should be rendered when the title is empty."""
        lines = diagram_render("", SIMPLE_TREE)
        assert not any('==' in line for line in lines)

    def test_cli_main_self_recursive_canonical_node_smoke(self):
        """The recursive cli-main example should render without crashing."""
        example = Path(__file__).parent.parent / "examples" / "cli-main.yaml"
        with open(example) as fh:
            data = yaml.safe_load(fh)
        lines = diagram_render(data.get("title", ""), data)
        joined = "\n".join(lines)
        assert "yamlNode_build" in joined


class TestPerChipOverrides:
    """Parsing tests for chip-local internal-wiring overrides."""

    def test_node_from_dict_parses_chip_local_internal_wiring_overrides(self):
        """Node parsing should capture chip-local internal wiring override flags."""
        node = Node.node_fromDict(
            {
                "module": "M",
                "func": "hub()",
                "chip_io": {
                    "internal_wiring": {
                        "colorize": False,
                        "showInternalLabels": False,
                        "aliasInternalLabels": True,
                    }
                },
                "calls": [],
            }
        )
        assert node.internalWireColorizeOverride is False
        assert node.showInternalLabelsOverride is False
        assert node.aliasInternalLabelsOverride is True
