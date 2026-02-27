"""Tests for layout_compute, subtree_canvasH, chip_h formulas."""

from signalflow.config import BASE_LEAF
from signalflow.lib.layout import channelWidth_compute, innerWidth_get, layout_compute
from signalflow.lib.tree import chip_h_precompute, col_assign
from signalflow.models import Node


def _leaf(func: str = "f()") -> Node:
    return Node(module="M", func=func, input_signal=None, children=[])


def _parent(func: str, children: list, is_root: bool = False) -> Node:
    return Node(module="M", func=func, input_signal=None, children=children, is_root=is_root)


class TestChipH:
    def test_leaf(self):
        assert chip_h_precompute(_leaf(), is_root=False) == BASE_LEAF

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
        col_assign(root)
        iw = innerWidth_get([root])
        ow = iw + 2
        cw = channelWidth_compute(root)
        layout_compute(root, ow, cw)
        assert root.x > 0
        assert root.y > 0

    def test_child_x_greater_than_parent(self):
        child = _leaf("child()")
        root  = _parent("root()", [child], is_root=True)
        col_assign(root)
        nodes = [root, child]
        iw = innerWidth_get(nodes)
        ow = iw + 2
        cw = channelWidth_compute(root)
        layout_compute(root, ow, cw)
        assert child.x > root.x
