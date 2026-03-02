"""Layout computation: column positions, chip sizes, channel widths.

Computes geometry for every node in the call tree before any rendering takes
place.  All canvas coordinates are integers (column, row) with (0,0) at the
top-left.

Key functions:
    channelWidth_compute: Minimum channel width to fit signal labels.
    innerWidth_get:       Uniform chip inner width across all nodes.
    leftMargin_compute:   Left canvas margin needed for root-leaf stubs.
    layout_compute:       Assigns x, y, chip_h, entry_row, return_row to all nodes.
"""
from __future__ import annotations

from signalflow.config import (
    CHANNEL_W,
    CHIP_PAD,
    MB_INNER,
    MB_OUTER,
    MB_TOP,
    ROW_GAP,
)
from signalflow.lib.tree import chip_h_precompute, subtree_canvasH
from signalflow.models import Node


def channelWidth_compute(root: Node) -> int:
    """Compute the minimum channel width needed to display all signal labels.

    The width must accommodate the parent-side label, the vertical bus of
    staggered channels (2 cols per child), and the child-side label.
    """
    min_cw: int = CHANNEL_W

    def _scan(node: Node) -> None:
        nonlocal min_cw
        n_ch = len(node.children)
        if n_ch == 0: return

        # Max space needed for any child-side label in this group (LEFT wall of children)
        max_child_lbl = 0
        for child in node.children:
            if child.input_ports:
                # Find the port connecting back to THIS node
                p = child.input_ports.get(id(node))
                if p:
                    lbl_f = len(p.signal) if p.signal else 0
                    lbl_r = len(p.ret) if p.ret else 0
                    max_child_lbl = max(max_child_lbl, lbl_f, lbl_r)

        # Max space needed for any parent-side label in this group (RIGHT wall of node)
        max_parent_lbl = 0
        for p in node.output_ports.values():
            lbl_f_p = len(p.signal) if p.signal else 0
            lbl_r_p = len(p.ret) if p.ret else 0
            max_parent_lbl = max(max_parent_lbl, lbl_f_p, lbl_r_p)

        # Total width = [Parent Exit (1)] + [Parent Label] + [Bus (2*N)] + [Child Label] + [Child Entry (1)]
        # We also need at least 1 column gap between label and bus.
        bus_w = 2 * n_ch
        total = 2 + max_parent_lbl + 1 + bus_w + 1 + max_child_lbl

        # Add module box margins if cross-module
        if any(child.module != node.module for child in node.children):
            total += 2 * MB_OUTER

        if total > min_cw:
            min_cw = total
        
        for child in node.children:
            _scan(child)

    _scan(root)
    if min_cw % 2 != 0:
        min_cw += 1
    return min_cw


def chip_ow_compute(node: Node) -> int:
    """Compute the specific outer width needed for this chip.

    Scales based on label length and internal manifold complexity.
    """
    label_w = len(node.func) + CHIP_PAD * 2
    
    # Manifold complexity
    v_tracks = 0
    for wire_pair in node.internal_wiring:
        if ':' not in wire_pair: continue
        src, dst = wire_pair.split(':')
        if src != dst:
            v_tracks += 1
    
    manifold_w = v_tracks + 6
    inner_w = max(label_w, manifold_w)
    return inner_w + 2 # +2 for walls


def leftMargin_compute(root: Node) -> int:
    """Compute the left canvas margin required before the root chip.

    For a leaf root, signal labels on the stub wires appear to the left of
    the module box.  The margin must accommodate two leading dashes, the
    longest label, two trailing dashes, and the module-box border gap.

    For a parent root (has children) there are no left stubs, so the legacy
    minimum margin (MB_OUTER + MB_INNER) is returned unchanged.

    Args:
        root: The tree root node (not yet laid out; only children and signal
            fields are inspected).

    Returns:
        Number of canvas columns to reserve left of the root chip's x origin.
    """
    if root.children:
        return MB_OUTER + MB_INNER
    
    max_lbl: int = 0
    for p in root.input_ports.values():
        if p.signal: max_lbl = max(max_lbl, len(p.signal))
        if p.ret:    max_lbl = max(max_lbl, len(p.ret))
        
    # 2 leading dashes + label + 2 trailing dashes + MB_OUTER (box border gap)
    return max(MB_OUTER + MB_INNER, max_lbl + MB_OUTER + 4)


def layout_compute(root: Node, cw: int) -> None:
    """Assign canvas coordinates and individual widths to every node.

    Nodes are arranged in columns. X coordinates are based on the cumulative
    width of previous columns (using the maximum chip width in each column).
    """
    from signalflow.lib.tree import tree_flatten
    nodes = tree_flatten(root)
    
    # 1. Compute individual widths
    for n in nodes:
        n.ow = chip_ow_compute(n)
        n.chip_h = chip_h_precompute(n, n.is_root)

    # 2. Assign X based on column groups
    left_offset = leftMargin_compute(root)
    max_col = max((n.col for n in nodes), default=0)
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
        # Advance current_x for the next column
        current_x += max_ow + cw

    for n in nodes:
        n.x = col_x_offsets[n.col]

    # 3. Assign Y by stacking nodes within each column
    for c in range(max_col + 1):
        col_nodes = [n for n in nodes if n.col == c]
        cursor_y = MB_TOP
        for n in col_nodes:
            n.y = cursor_y
            cursor_y += n.chip_h + ROW_GAP

    # 4. Map Port Rows
    for n in nodes:
        for i, parent_id in enumerate(n.input_ports.keys()):
            n.entry_rows[parent_id]  = n.y + 3 + 3 * i
            n.return_rows[parent_id] = n.y + 4 + 3 * i
        
        if n.input_ports:
            first_parent = list(n.input_ports.keys())[0]
            n.entry_row  = n.entry_rows[first_parent]
            n.return_row = n.return_rows[first_parent]
        else:
            n.entry_row  = n.y + 3
            n.return_row = n.y + 4
