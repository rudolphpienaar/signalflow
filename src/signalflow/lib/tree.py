"""Tree utilities: flatten, col_assign, subtree height."""

from signalflow.config import BASE_LEAF, ROW_GAP
from signalflow.models import Node


def tree_flatten(root: Node) -> list:
    """Returns all unique nodes in the graph in visit order."""
    result = []
    seen   = set()

    def _visit(n: Node) -> None:
        if id(n) in seen: return
        seen.add(id(n))
        result.append(n)
        for child in n.children:
            _visit(child)

    _visit(root)
    return result


def col_assign(root: Node) -> None:
    """Set node.col = max call depth (root = 0). Mutates in-place."""
    # Reset columns since nodes are unique and might be revisited
    for n in tree_flatten(root):
        n.col = 0

    def _visit(n: Node, depth: int) -> None:
        n.col = max(n.col, depth)
        for child in n.children:
            _visit(child, depth + 1)

    _visit(root, 0)


def chip_h_precompute(node: Node, is_root: bool) -> int:
    """Compute chip height based on the maximum number of ports on either side.

    Each port pair (signal + return + space) needs 3 rows.
    Height = 3 * max(ports_left, ports_right) + 3 (header + footer).
    """
    n_left  = len(node.input_ports)
    n_right = len(node.output_ports)
    n = max(n_left, n_right)
    
    if n <= 1:
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
