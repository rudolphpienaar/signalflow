"""End-to-end smoke tests for diagram_render."""

from signalflow.engine.render import diagram_render

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
    def test_returns_nonempty_list(self):
        lines = diagram_render("test", SIMPLE_TREE)
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_title_in_output(self):
        lines = diagram_render("My Title", SIMPLE_TREE)
        assert any('My Title' in line for line in lines)

    def test_func_label_in_output(self):
        lines = diagram_render("", SIMPLE_TREE)
        joined = '\n'.join(lines)
        assert 'root()' in joined
        assert 'child()' in joined

    def test_signal_label_in_output(self):
        lines = diagram_render("", SIMPLE_TREE)
        assert any('sig' in line for line in lines)

    def test_deep_tree_smoke(self):
        lines = diagram_render("deep", DEEP_TREE)
        assert len(lines) > 5

    def test_no_title(self):
        lines = diagram_render("", SIMPLE_TREE)
        assert not any('==' in line for line in lines)
