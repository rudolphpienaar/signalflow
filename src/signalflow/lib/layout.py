"""Layout computation: column positions, chip sizes, channel widths.

Computes geometry for every node in the call tree before any rendering takes
place. All canvas coordinates are integers (column, row) with (0,0) at the
top-left.
"""
from __future__ import annotations

# Standard library
from typing import Iterable

# Local
from signalflow.config import config
from signalflow.lib.tree import chip_h_precompute
from signalflow.models import Node


def channelWidth_compute(root: Node) -> int:
    """Scan the entire tree to find the minimum global channel width needed.

    Finds the maximum horizontal space required by any parent->children group,
    considering signal/return labels and internal staggering.

    Args:
        root: The root node of the call graph.

    Returns:
        The calculated minimum channel width as an integer.
    """
    min_cw: int = config.channelWidth

    def _scan(node: Node) -> None:
        nonlocal min_cw
        n_ch = len(node.children)
        if n_ch == 0:
            return

        # Max space needed for any child-side label in this group (LEFT wall of children)
        max_child_lbl = 0
        for child in node.children:
            local_p = child.input_ports.get(id(node))
            if local_p:
                lbl_f = len(local_p.signal) if local_p.signal else 0
                lbl_r = len(local_p.ret) if local_p.ret else 0
                max_child_lbl = max(max_child_lbl, lbl_f, lbl_r)

        # Max space needed for any parent-side label in this group (RIGHT wall of parent)
        max_parent_lbl = 0
        for child in node.children:
            p_port = node.output_ports.get(id(child))
            if p_port:
                lbl_f_p = len(p_port.signal) if p_port.signal else 0
                lbl_r_p = len(p_port.ret) if p_port.ret else 0
                max_parent_lbl = max(max_parent_lbl, lbl_f_p, lbl_r_p)

        # Total width = [Parent Exit (1)] + [Parent Label] + [Bus (2*N)] + [Child Label] + [Child Entry (1)]
        # We also need at least 1 column gap between label and bus.
        bus_w = 2 * n_ch
        total = 1 + max_parent_lbl + 1 + bus_w + 1 + max_child_lbl + 1

        # Module box padding if applicable
        total += 2 * config.moduleOuterWidth

        if total > min_cw:
            min_cw = total

        for child in node.children:
            _scan(child)

    _scan(root)
    return min_cw


def chip_ow_compute(node: Node) -> int:
    """Compute the specific outer width needed for this chip.

    Scales based on label length and shared vertical tracks in the manifold.

    Args:
        node: The node to compute width for.

    Returns:
        The calculated outer width as an integer.
    """
    label_w = len(node.func) + config.chipPaddingX * 2

    # Track Count Logic: Calculate left and right manifolds separately for balance
    v_left, v_right = 0, 0
    if config.share_internal_routes:
        uniq_l, uniq_r = set(), set()
        for wire_pair in node.internal_wiring:
            if ":" not in wire_pair: continue
            src, dst = wire_pair.split(":")
            # We determine side by the shared port (the one acting as the manifold hub)
            # Hub ports on the LEFT wall (input signals and return signals)
            if src.startswith('s') or src.startswith('r'): uniq_l.add(src)
            else:                                          uniq_r.add(dst)
        v_left, v_right = len(uniq_l), len(uniq_r)
    else:
        for wire_pair in node.internal_wiring:
            if ":" not in wire_pair: continue
            src, dst = wire_pair.split(":")
            if src != dst:
                # Assign to left/right manifold based on destination wall
                if dst.startswith('r') or src.startswith('s'): v_left += 1
                else:                                          v_right += 1

    # Width needed = LeftBus + Label/Buffer + RightBus
    # Each track needs 2 columns.
    manifold_w = (2 * v_left) + (2 * v_right) + 4
    inner_w = max(label_w, manifold_w)
    return inner_w + 2


def leftMargin_compute(root: Node) -> int:
    """Compute the left canvas margin required before the root chip.

    This space is needed for root-entry labels or module box padding. If
    root has children (meaning it's part of a larger graph), the standard
    minimum margin (moduleOuterWidth + moduleInnerMargin) is returned unchanged.

    Args:
        root: The root node of the graph.

    Returns:
        Minimum horizontal offset for the first column.
    """
    if root.children:
        return config.moduleOuterWidth + config.moduleInnerMargin

    max_lbl: int = 0
    for p in root.input_ports.values():
        if p.signal:
            max_lbl = max(max_lbl, len(p.signal))
        if p.ret:
            max_lbl = max(max_lbl, len(p.ret))

    # 2 leading dashes + label + 2 trailing dashes + moduleOuterWidth (box border gap)
    return max(
        config.moduleOuterWidth + config.moduleInnerMargin,
        max_lbl + config.moduleOuterWidth + 4,
    )


def col_assign(root: Node) -> int:
    """Assign column index to every node in the tree recursively.

    Args:
        root: Root node to start assignment from.

    Returns:
        The maximum column index assigned.
    """
    max_c = 0

    def _walk(n: Node, c: int) -> None:
        nonlocal max_c
        n.col = c
        max_c = max(max_c, c)
        for child in n.children:
            _walk(child, c + 1)

    _walk(root, 0)
    return max_c


def layout_compute(root: Node, cw: int) -> None:
    """Compute final (x,y) coordinates for all nodes.

    Args:
        root: The root node of the graph.
        cw: The global channel width to use between columns.
    """
    from signalflow.lib.tree import tree_flatten

    nodes = tree_flatten(root)

    # 1. Compute individual widths
    for n in nodes:
        n.ow = chip_ow_compute(n)
        n.chip_h = chip_h_precompute(n, is_root=(n == root))

    # 2. Assign X by column
    max_col = col_assign(root)
    left_offset = leftMargin_compute(root)

    col_x_offsets = {}
    current_x = left_offset

    for c in range(max_col + 1):
        col_nodes = [n for n in nodes if n.col == c]
        if not col_nodes:
            col_x_offsets[c] = current_x
            continue

        col_x_offsets[c] = current_x
        # Find widest chip in this column
        max_ow = max(n.ow for n in col_nodes)
        current_x += max_ow + cw

    for n in nodes:
        n.x = col_x_offsets[n.col]

    # 3. Assign Y by stacking nodes within each column
    for c in range(max_col + 1):
        col_nodes = [n for n in nodes if n.col == c]
        cursor_y = config.moduleTopRows
        for n in col_nodes:
            n.y = cursor_y
            cursor_y += n.chip_h + config.verticalChipPadding

    # 4. Map Port Rows
    for n in nodes:
        # High-Resolution Rule: Only stretch if a complex manifold is present
        spacing = config.portVerticalSpacing if n.internal_wiring else 3
        
        for i, parent_id in enumerate(n.input_ports):
            n.entry_rows[parent_id] = n.y + 3 + spacing * i
            n.return_rows[parent_id] = n.y + 4 + spacing * i

        # Note: output_ports are also mapped relative to the same spacing in chips.py
        # but we compute the node's internal state here for reference.
