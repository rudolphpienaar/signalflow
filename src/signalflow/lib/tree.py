"""Tree utilities: flattening, depth, height pre-computation."""
from __future__ import annotations

# Local
from signalflow.config import config
from signalflow.models import Node


def tree_flatten(root: Node) -> list[Node]:
    """Return a flat list of all unique nodes in the graph (BFS order)."""
    result = []
    seen = set()

    def _visit(n: Node) -> None:
        if id(n) in seen:
            return
        seen.add(id(n))
        result.append(n)
        for child in n.children:
            _visit(child)

    _visit(root)
    return result


def tree_depth(node: Node) -> int:
    """Return the maximum depth of the call tree from node."""
    if not node.children:
        return 1
    return 1 + max(tree_depth(c) for c in node.children)


def chip_h_precompute(node: Node, is_root: bool = False) -> int:
    """Calculate the height (rows) required for a function chip.

    Height is dynamic based on the number of input and output ports.
    Base height for a leaf or single-port chip is defined in config.

    Args:
        node: The node to compute height for.
        is_root: True if this is the root node.

    Returns:
        Height in canvas rows as an integer.
    """
    n_left = len(node.input_ports)
    n_right = len(node.output_ports)
    n = max(n_left, n_right)

    if n <= 1:
        return config.baseLeafHeight

    # 3 rows per port (exit/return/gap) + 3 rows for header
    return 3 * n + 3


def subtree_canvasH(node: Node) -> int:
    """Calculate the total canvas height required by a subtree.

    Sum of all chip heights plus vertical padding between sibling subtrees.

    Args:
        node: The root of the subtree.

    Returns:
        Total vertical rows required as an integer.
    """
    if not node.children:
        return node.chip_h

    return sum(subtree_canvasH(c) for c in node.children) + config.verticalChipPadding * (
        len(node.children) - 1
    )
