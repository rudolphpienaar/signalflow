"""Tests for layout_compute, subtree_canvasH, chipH formulas."""

from signalflow.config import config
from signalflow.lib.layout import (
    channelGapWidths_compute,
    channelWidth_compute,
    layout_compute,
)
from signalflow.models import Node
from signalflow.models.chip_geometry import ChipGeometry


def _leaf(func: str = "f()") -> Node:
    return Node(module="M", func=func, children=[])


def _parent(func: str, children: list, isRoot: bool = False) -> Node:
    return Node(module="M", func=func, children=children)


class TestChipH:
    def test_leaf(self):
        assert ChipGeometry.build_structural(_leaf()).chipH == 7  # gap row bumps min

    def test_root_one_child(self):
        assert ChipGeometry.build_structural(_parent("p", [_leaf()])).chipH == 6   # 3*1+3

    def test_root_two_children(self):
        # 3*2+3
        assert ChipGeometry.build_structural(_parent("p", [_leaf(), _leaf()])).chipH == 9

    def test_nonroot_one_child(self):
        assert ChipGeometry.build_structural(_parent("p", [_leaf()])).chipH == 6  # 3*1+3

    def test_nonroot_two_children(self):
        # 3*2+3
        assert ChipGeometry.build_structural(_parent("p", [_leaf(), _leaf()])).chipH == 9


class TestLayoutCompute:
    def test_root_position(self):
        root = _leaf("root()")
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        assert root.x > 0
        assert root.y > 0

    def test_child_x_greater_than_parent(self):
        child = _leaf("child()")
        root  = _parent("root()", [child], isRoot=True)
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        assert child.x > root.x

    def test_per_gap_spacing_does_not_use_deep_global_max_everywhere(self):
        root = Node.node_fromDict(
            {
                "module": "M",
                "func": "root()",
                "output_ports": [{"signal": "s", "return": "r"}],
                "calls": [
                    {
                        "module": "M",
                        "func": "mid()",
                        "input_ports": [{"signal": "s", "return": "r"}],
                        "output_ports": [
                            {
                                "signal": "very_long_signal_for_deep_edge",
                                "return": "very_long_return_for_deep_edge",
                            }
                        ],
                        "calls": [
                            {
                                "module": "M",
                                "func": "leaf()",
                                "input_ports": [
                                    {
                                        "signal": "very_long_signal_for_deep_edge",
                                        "return": "very_long_return_for_deep_edge",
                                    }
                                ],
                                "calls": [],
                            }
                        ],
                    }
                ],
            }
        )
        cw = channelWidth_compute(root)
        gapWidths = channelGapWidths_compute(root)
        layout_compute(root, cw)

        mid = root.children[0]
        rootGap = mid.x - (root.x + root.ow)

        assert gapWidths[0] == config.channelWidth
        assert gapWidths[1] > gapWidths[0]
        assert cw == gapWidths[1]
        assert rootGap == gapWidths[0]
