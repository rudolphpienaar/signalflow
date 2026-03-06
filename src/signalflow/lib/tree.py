"""Tree utilities: flattening, depth, height pre-computation."""
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


def chipH_precompute(node: Node, isRoot: bool = False) -> int:
    """Calculate the height (rows) required for a function chip.

    For manifold chips, the trunk zone sits below all anchor rows.
    Anchor rows extend at most maxPortDensity rows past the last wall-port
    row; trunk rows then follow (one row per unique source group × its lane
    count).  chipH is sized to guarantee no overflow.
    """
    nLeft: int = len(node.input_ports)
    # Fall back to children count when output_ports not yet bound
    # (e.g. manually created nodes)
    nRight: int = len(node.output_ports) if node.output_ports else len(node.children)
    n: int = max(nLeft, nRight)

    if n <= 1:
        return config.baseLeafHeight

    if not node.internal_wiring:
        return 3 * n + 3

    spacing: int = config.portVerticalSpacing

    # Conservative upper-bound geometry:
    #   last wall-port returnRow  = y0 + 3 + spacing*(n-1) + 1
    #   max anchor depth           = max times any port appears as src or dst
    #   trunk rows                 = total manifold wiring pairs (upper bound)
    #
    # h = (last_wall_return_offset) + max_anchor_depth + n_trunk_rows + 2
    portCounts: dict[str, int] = {}
    wiringCount: int = 0
    w: str
    for w in node.internal_wiring:
        if ":" not in w:
            continue
        wiringCount += 1
        src: str
        dst: str
        src, dst = w.split(":")
        portCounts[src] = portCounts.get(src, 0) + 1
        portCounts[dst] = portCounts.get(dst, 0) + 1

    maxPortDensity: int = max(portCounts.values(), default=0)
    lastWallReturnOffset: int = 3 + spacing * (n - 1) + 1
    h: int = lastWallReturnOffset + maxPortDensity + wiringCount + 2
    return max(config.baseLeafHeight, h)


def ewTopOffset_get(node: Node) -> int:
    """Number of E→W trunk rows reserved at the top of the chip interior.

    Counts all E→W source threads that need manifold trunk rows. A source
    is E→W if it lives on the right (east) wall — i.e. it is a ret port of
    one of the node's output_ports. Sources that appear only once are likely
    straight-through pairs (excluded by ``cnt == 1`` filter).
    """
    if not node.internal_wiring:
        return 0
    rightRetPorts: set[str] = {
        port.ret
        for port in node.output_ports.values()
        if port.ret
    }
    srcCounts: dict[str, int] = {}
    for w in node.internal_wiring:
        if ":" not in w:
            continue
        src: str
        src, _ = w.split(":", 1)
        if src in rightRetPorts:
            srcCounts[src] = srcCounts.get(src, 0) + 1
    return sum(cnt for cnt in srcCounts.values() if cnt > 1)


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
