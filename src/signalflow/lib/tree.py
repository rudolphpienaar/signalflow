"""Tree utilities: flatten, col_assign, subtree height."""

from signalflow.config import BASE_LEAF, ROW_GAP
from signalflow.models import Node


def tree_flatten(root: Node) -> list:
    """DFS pre-order flatten. Returns list[Node] in visit order."""
    result = []

    def _visit(n: Node) -> None:
        result.append(n)
        for child in n.children:
            _visit(child)

    _visit(root)
    return result


def col_assign(root: Node) -> None:
    """Set node.col = call depth (root = 0). Mutates in-place."""

    def _visit(n: Node, depth: int) -> None:
        n.col = depth
        for child in n.children:
            _visit(child, depth + 1)

    _visit(root, 0)


def chip_h_precompute(node: Node, is_root: bool) -> int:
    """Compute chip height from tree structure alone (before layout).

    Leaf:          BASE_LEAF  (= 6)
    Parent, N > 0: 3*N + 3   (header=3, body=3N-1, bottom=1; same for root and non-root)

    Body row count per child: call + return + wire-pair-space = 3 rows, except
    the last child which has no trailing space, giving body = 3*N - 1 rows.
    """
    n = len(node.children)
    if n == 0:
        return BASE_LEAF
    return 3 * n + 3


def subtree_canvasH(node: Node) -> int:
    """Compute total canvas height consumed by node's subtree.

    Uses chip_h stored on node (must be set by layout_compute).
    """
    if not node.children:
        return node.chip_h
    children_stack = (
        sum(subtree_canvasH(c) for c in node.children)
        + ROW_GAP * (len(node.children) - 1)
    )
    return max(node.chip_h, children_stack)
