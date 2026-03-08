"""Tree utilities: flattening, depth, subtree height."""
from __future__ import annotations

# Local
from signalflow.config import config
from signalflow.models import Node


def tree_flatten(root: Node) -> list[Node]:
    """Return a flat list of all unique nodes in the graph (BFS order)."""
    result: list[Node] = []
    seen: set[int] = set()

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


def subtreeCanvasH_calculate(node: Node) -> int:
    """Calculate the total canvas height required by a subtree.

    Sum of all chip heights plus vertical padding between sibling subtrees.

    Args:
        node: The root of the subtree.

    Returns:
        Total vertical rows required as an integer.
    """
    if not node.children:
        return node.chipH

    childSum: int = sum(subtreeCanvasH_calculate(c) for c in node.children)
    return childSum + config.verticalChipPadding * (len(node.children) - 1)
