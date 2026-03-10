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
    """Structural chip-height formulas used during layout."""

    def test_leaf(self):
        """Leaf chips should reserve the 7-row minimum with a computation gap."""
        assert ChipGeometry.build_structural(_leaf()).chipH == 7  # gap row bumps min

    def test_root_one_child(self):
        """A single-child parent should use the compact 6-row layout."""
        assert ChipGeometry.build_structural(_parent("p", [_leaf()])).chipH == 6

    def test_root_two_children(self):
        """A two-child parent should grow to the 9-row layout."""
        assert (
            ChipGeometry.build_structural(_parent("p", [_leaf(), _leaf()])).chipH
            == 9
        )

    def test_nonroot_one_child(self):
        """A non-root single-child parent should still use the compact 6-row layout."""
        assert ChipGeometry.build_structural(_parent("p", [_leaf()])).chipH == 6

    def test_nonroot_two_children(self):
        """A non-root two-child parent should still use the 9-row layout."""
        assert (
            ChipGeometry.build_structural(_parent("p", [_leaf(), _leaf()])).chipH
            == 9
        )


class TestLayoutCompute:
    """End-to-end layout coordinate assignment tests."""

    def test_root_position(self):
        """The root chip should receive positive canvas coordinates after layout."""
        root = _leaf("root()")
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        assert root.x > 0
        assert root.y > 0

    def test_child_x_greater_than_parent(self):
        """Children should always be placed to the right of their parent."""
        child = _leaf("child()")
        root  = _parent("root()", [child], isRoot=True)
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        assert child.x > root.x

    def test_per_gap_spacing_does_not_use_deep_global_max_everywhere(self):
        """Per-gap spacing should not let deep wide edges bloat earlier gaps."""
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
