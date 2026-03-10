"""Tree utilities: flattening, depth, subtree height."""
from __future__ import annotations

# Local
from signalflow.config import config
from signalflow.models import Node


def tree_flatten(root: Node) -> list[Node]:
    """Return a flat list of all unique nodes in the graph (BFS order)."""
    result: list[Node] = []
    seen: set[int] = set()

    def _node_visit(n: Node) -> None:
        """Visit each graph node once while preserving child order."""
        if id(n) in seen:
            return
        seen.add(id(n))
        result.append(n)
        for child in n.children:
            _node_visit(child)

    _node_visit(root)
    return result


def tree_depth(node: Node) -> int:
    """Return the maximum depth of the call tree from node."""
    seen: set[int] = set()

    def _nodeDepth_get(n: Node) -> int:
        """Return depth for one node while breaking canonical cycles."""
        if id(n) in seen:
            return 0
        seen.add(id(n))
        if not n.children:
            return 1
        return 1 + max(_nodeDepth_get(c) for c in n.children)

    return _nodeDepth_get(node)


def subtreeCanvasH_calculate(node: Node) -> int:
    """Calculate the total canvas height required by a subtree.

    Sum of all chip heights plus vertical padding between sibling subtrees.

    Args:
        node: The root of the subtree.

    Returns:
        Total vertical rows required as an integer.
    """
    seen: set[int] = set()

    def _nodeHeight_get(n: Node) -> int:
        """Return subtree canvas height for one node while breaking cycles."""
        if id(n) in seen:
            return 0
        seen.add(id(n))
        if not n.children:
            return n.chipH

        childHeights: list[int] = [_nodeHeight_get(c) for c in n.children]
        childSum: int = sum(childHeights)
        return childSum + config.verticalChipPadding * (len(n.children) - 1)

    return _nodeHeight_get(node)
