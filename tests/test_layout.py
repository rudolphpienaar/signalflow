"""Tests for layout_compute, subtree_canvasH, chip_h formulas."""

from signalflow.config import config
from signalflow.lib.layout import channelWidth_compute, layout_compute, col_assign
from signalflow.lib.tree import chip_h_precompute
from signalflow.models import Node


def _leaf(func: str = "f()") -> Node:
    return Node(module="M", func=func, children=[])


def _parent(func: str, children: list, is_root: bool = False) -> Node:
    return Node(module="M", func=func, children=children)


class TestChipH:
    def test_leaf(self):
        assert chip_h_precompute(_leaf(), is_root=False) == config.baseLeafHeight

    def test_root_one_child(self):
        assert chip_h_precompute(_parent("p", [_leaf()]), is_root=True) == 6   # 3*1+3

    def test_root_two_children(self):
        # 3*2+3
        assert chip_h_precompute(_parent("p", [_leaf(), _leaf()]), is_root=True) == 9

    def test_nonroot_one_child(self):
        assert chip_h_precompute(_parent("p", [_leaf()]), is_root=False) == 6  # 3*1+3

    def test_nonroot_two_children(self):
        # 3*2+3
        assert chip_h_precompute(_parent("p", [_leaf(), _leaf()]), is_root=False) == 9


class TestLayoutCompute:
    def test_root_position(self):
        root = _leaf("root()")
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        assert root.x > 0
        assert root.y > 0

    def test_child_x_greater_than_parent(self):
        child = _leaf("child()")
        root  = _parent("root()", [child], is_root=True)
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        assert child.x > root.x
