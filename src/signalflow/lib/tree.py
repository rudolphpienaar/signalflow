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

    For manifold chips, the trunk zone sits below all anchor rows.
    Anchor rows extend at most max_port_density rows past the last wall-port
    row; trunk rows then follow (one row per unique source group × its lane
    count).  chip_h is sized to guarantee no overflow.
    """
    n_left = len(node.input_ports)
    # Fall back to children count when output_ports not yet bound (e.g. manually created nodes)
    n_right = len(node.output_ports) if node.output_ports else len(node.children)
    n = max(n_left, n_right)

    if n <= 1:
        return config.baseLeafHeight

    if not node.internal_wiring:
        return 3 * n + 3

    spacing = config.portVerticalSpacing

    # Conservative upper-bound geometry:
    #   last wall-port return_row  = y0 + 3 + spacing*(n-1) + 1
    #   max anchor depth           = max times any port appears as src or dst
    #   trunk rows                 = total manifold wiring pairs (upper bound)
    #
    # h = (last_wall_return_offset) + max_anchor_depth + n_trunk_rows + 2
    port_counts: dict[str, int] = {}
    wiring_count = 0
    for w in node.internal_wiring:
        if ":" not in w:
            continue
        wiring_count += 1
        src, dst = w.split(":")
        port_counts[src] = port_counts.get(src, 0) + 1
        port_counts[dst] = port_counts.get(dst, 0) + 1

    max_port_density = max(port_counts.values(), default=0)
    last_wall_return_offset = 3 + spacing * (n - 1) + 1
    h = last_wall_return_offset + max_port_density + wiring_count + 2
    return max(config.baseLeafHeight, h)


def ew_top_offset(node: Node) -> int:
    """Number of E→W trunk rows reserved at the top of the chip interior.

    Counts all E→W source threads that need manifold trunk rows. A source
    is E→W if it lives on the right (east) wall — i.e. it is a ret port of
    one of the node's output_ports. Sources that appear only once are likely
    straight-through pairs (excluded by ``cnt == 1`` filter).
    """
    if not node.internal_wiring:
        return 0
    right_ret_ports: set[str] = {
        port.ret
        for port in node.output_ports.values()
        if port.ret
    }
    src_counts: dict[str, int] = {}
    for w in node.internal_wiring:
        if ":" not in w:
            continue
        src, _ = w.split(":", 1)
        if src in right_ret_ports:
            src_counts[src] = src_counts.get(src, 0) + 1
    return sum(cnt for cnt in src_counts.values() if cnt > 1)


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
