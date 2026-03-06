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
from signalflow.lib.tree import chip_h_precompute, ew_top_offset
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

    Scales based on the total longitude zone density required on each wall so
    that the left and right zones never overlap and the latitude zone in
    between always has at least 4 columns.

    Args:
        node: The node to compute width for.

    Returns:
        The calculated outer width as an integer.
    """
    label_w = len(node.func) + config.chipPaddingX * 2

    if not node.internal_wiring:
        return label_w + 2

    # Build per-port connection density (mirrors chips.py section 2.4 logic)
    l_counts: dict[str, int] = {}
    for wire_pair in node.internal_wiring:
        if ":" not in wire_pair:
            continue
        src, dst = wire_pair.split(":")
        l_counts[src] = l_counts.get(src, 0) + 1
        l_counts[dst] = l_counts.get(dst, 0) + 1

    left_names: set[str] = {
        name
        for port in node.input_ports.values()
        for name in (port.signal, port.ret)
        if name
    }
    right_names: set[str] = {
        name
        for port in node.output_ports.values()
        for name in (port.signal, port.ret)
        if name
    }

    v_left = sum(cnt for name, cnt in l_counts.items() if name in left_names)
    v_right = sum(cnt for name, cnt in l_counts.items() if name in right_names)

    # Anchor labels: "{port}►/◄" on left, "►/◄{port}" on right — len = len(name)+1
    max_left_label = max((len(n) + 1 for n in left_names if n in l_counts), default=0)
    max_right_label = max((len(n) + 1 for n in right_names if n in l_counts), default=0)

    # Width: 1(border) + max_left_label + 1(gap) + 2*v_left + ≥4(latitude) + 2*v_right + 1(gap) + max_right_label + 1(border)
    manifold_min_ow = 8 + max_left_label + max_right_label + 2 * (v_left + v_right)
    return max(label_w + 2, manifold_min_ow)


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
        
        ew_off = ew_top_offset(n)
        for i, parent_id in enumerate(n.input_ports):
            n.entry_rows[parent_id] = n.y + 3 + ew_off + spacing * i
            n.return_rows[parent_id] = n.y + 4 + ew_off + spacing * i

        # Set legacy single-port shortcuts from first port (backward compat)
        if n.entry_rows:
            n.entry_row = next(iter(n.entry_rows.values()))
        if n.return_rows:
            n.return_row = next(iter(n.return_rows.values()))

        # Note: output_ports are also mapped relative to the same spacing in chips.py
        # but we compute the node's internal state here for reference.
