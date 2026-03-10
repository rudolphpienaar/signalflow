"""Phase 0 TDD: pipeline and canvas invariant tests.

These tests verify contracts that must hold at every stage of the rendering
pipeline.  None depend on ChipGeometry existing yet; they test properties of
the current rendering pipeline that ChipGeometry will formalise.
"""
from __future__ import annotations

import copy
from dataclasses import fields

import pytest
import yaml
from pathlib import Path

from signalflow.config import config
from signalflow.lib.boxes import moduleBox_compute
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.lib.wires import thread_render
from signalflow.models.canvas import Canvas
from signalflow.models.node import Node, Port


# ── config fixture ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    saved = {f.name: getattr(config, f.name) for f in fields(config)}
    yield
    for name, val in saved.items():
        setattr(config, name, val)


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_and_render(yaml_path: Path):
    """Full pipeline: parse → layout → render.  Return (canvas, nodes, root)."""
    with open(yaml_path) as fh:
        data = yaml.safe_load(fh)
    config.config_update(data.get("config", {}))
    root  = Node.node_fromDict(data.get("tree", data))
    nodes = tree_flatten(root)
    cw    = channelWidth_compute(root)
    layout_compute(root, cw)
    boxes  = moduleBox_compute(nodes)
    canvas = canvas_create(nodes, cw, boxes)
    for box in boxes:
        from signalflow.lib.boxes import moduleBox_render
        moduleBox_render(canvas, box, nodes)
    for n in nodes:
        chip_render(canvas, n)
    canvas.modeMerge = True
    thread_render(canvas, root)
    canvas.modeMerge = False
    return canvas, nodes, root


HUB_YAML = Path(__file__).parent.parent / "examples" / "hub.yaml"
COHORT_YAML = Path(__file__).parent.parent / "examples" / "show-cohort.yaml"
CLI_MAIN_YAML = Path(__file__).parent.parent / "examples" / "cli-main.yaml"


# ── modeMerge invariant ───────────────────────────────────────────────────────

class TestModeMergeInvariant:
    def test_modeMerge_false_after_each_chip_render(self):
        """chip_render must leave canvas.modeMerge == False on normal exit."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        boxes  = moduleBox_compute(nodes)
        canvas = canvas_create(nodes, cw, boxes)
        for n in nodes:
            assert not canvas.modeMerge, "modeMerge was True before chip_render"
            chip_render(canvas, n)
            assert not canvas.modeMerge, (
                f"chip_render({n.func}) left canvas.modeMerge == True"
            )

    def test_modeMerge_false_after_thread_render(self):
        """thread_render caller must restore modeMerge to False."""
        canvas, nodes, root = _load_and_render(HUB_YAML)
        assert not canvas.modeMerge


# ── canvas bounds ─────────────────────────────────────────────────────────────

class TestCanvasBounds:
    def test_chip_content_within_canvas_rows(self):
        """Every chip's bottom border row must be < canvas.rows."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        boxes  = moduleBox_compute(nodes)
        canvas = canvas_create(nodes, cw, boxes)
        for n in nodes:
            bottom = n.y + n.chipH - 1
            assert bottom < canvas.rows, (
                f"{n.func}: chip bottom row {bottom} >= canvas.rows {canvas.rows}"
            )

    def test_no_chip_overflows_canvas_cols(self):
        """Every chip's right border column must be < canvas.cols."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        boxes  = moduleBox_compute(nodes)
        canvas = canvas_create(nodes, cw, boxes)
        for n in nodes:
            right = n.x + n.ow - 1
            assert right < canvas.cols, (
                f"{n.func}: chip right col {right} >= canvas.cols {canvas.cols}"
            )

    def test_canvas_oob_write_is_detectable(self):
        """OOB writes raise IndexError in debug mode (Phase 6e)."""
        import pytest
        canvas = Canvas(rows=10, cols=10)
        canvas.set(5, 5, "X")
        assert canvas.get(5, 5) == "X"
        with pytest.raises(IndexError, match="Canvas OOB"):
            canvas.set(100, 100, "Z")
        # Valid cell must be unaffected
        assert canvas.get(5, 5) == "X"


class TestModuleBoxes:
    def test_cli_main_module_boxes_do_not_overlap(self):
        """Module regions must be pairwise non-overlapping."""
        with open(CLI_MAIN_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        boxes = moduleBox_compute(nodes)
        i: int
        a: object
        b: object
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                xOverlap = not (a.ox1 < b.ox0 or b.ox1 < a.ox0)
                yOverlap = not (a.oy1 < b.oy0 or b.oy1 < a.oy0)
                assert not (xOverlap and yOverlap), (
                    f"module boxes overlap: {a.label} {a.ox0,a.oy0,a.ox1,a.oy1} "
                    f"vs {b.label} {b.ox0,b.oy0,b.ox1,b.oy1}"
                )

    def test_module_box_width_fits_label(self):
        """Every module box must be wide enough for its top-border label."""
        with open(CLI_MAIN_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        boxes = moduleBox_compute(nodes)
        box: object
        for box in boxes:
            width = box.ox1 - box.ox0 + 1
            required = len(f"═ {box.label} ") + 2
            assert width >= required, (
                f"{box.label}: box width {width} < required {required}"
            )


# ── layout completeness ───────────────────────────────────────────────────────

class TestLayoutCompleteness:
    def test_all_nodes_have_nonzero_y(self):
        """After layout_compute, every node must have y > 0."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        for n in nodes:
            assert n.y > 0, f"{n.func}: y={n.y} (layout not run?)"

    def test_all_nodes_have_nonzero_chipH(self):
        """After layout_compute, every node must have chipH >= baseLeafHeight."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        for n in nodes:
            assert n.chipH >= config.baseLeafHeight, (
                f"{n.func}: chipH={n.chipH} < baseLeafHeight={config.baseLeafHeight}"
            )

    def test_child_x_greater_than_parent_x(self):
        """Children must be positioned to the right of their parents."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        for n in nodes:
            for child in n.children:
                assert child.x > n.x, (
                    f"{child.func}.x={child.x} not > {n.func}.x={n.x}"
                )

    def test_sibling_chips_do_not_vertically_overlap(self):
        """Sibling nodes in the same column must not share any row."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        from itertools import groupby
        by_col: dict[int, list[Node]] = {}
        for n in nodes:
            by_col.setdefault(n.col, []).append(n)
        for col, col_nodes in by_col.items():
            for i, a in enumerate(col_nodes):
                for b in col_nodes[i+1:]:
                    a_rows = set(range(a.y, a.y + a.chipH))
                    b_rows = set(range(b.y, b.y + b.chipH))
                    overlap = a_rows & b_rows
                    assert not overlap, (
                        f"col {col}: {a.func} and {b.func} share rows {sorted(overlap)}"
                    )

    def test_entry_rows_set_for_all_input_ports(self):
        """After layout_compute, entryRows must have an entry for every input port."""
        with open(HUB_YAML) as fh:
            data = yaml.safe_load(fh)
        config.config_update(data.get("config", {}))
        root  = Node.node_fromDict(data.get("tree", data))
        nodes = tree_flatten(root)
        cw    = channelWidth_compute(root)
        layout_compute(root, cw)
        for n in nodes:
            for pid in n.input_ports:
                assert pid in n.entryRows,  f"{n.func}: missing entryRow  for parent {pid}"
                assert pid in n.returnRows, f"{n.func}: missing returnRow for parent {pid}"

