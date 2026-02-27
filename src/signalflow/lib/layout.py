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

    Scans the entire call tree for signal labels on both parent and child
    sides of the channel and returns an even integer wide enough to render
    them with proper spacing and arrows.

    Args:
        root: Root of the call tree to scan.

    Returns:
        Minimum even channel width >= CHANNEL_W (cols).
    """
    min_cw: int = CHANNEL_W

    def _scan(node: Node) -> None:
        nonlocal min_cw
        for i, child in enumerate(node.children):
            # Base space for staggering vertical wires
            stagger_w = 2 + 2 * i + 4

            # Forward signals: [parent output] + gap (1) + [child input] + arrow (1) + padding (2)
            fwd_needed = 4
            if node.output_signal:
                fwd_needed += len(node.output_signal) + 1
            if child.input_signal:
                fwd_needed += len(child.input_signal)

            # Return signals: [arrow] + [parent output_return] + gap (1) + [child input_return] + padding (2)
            ret_needed = 4
            if node.output_return:
                ret_needed += len(node.output_return) + 1
            if child.input_return:
                ret_needed += len(child.input_return)

            total = max(fwd_needed, ret_needed, stagger_w)
            if node.module != child.module:
                from signalflow.config import MB_OUTER
                total += 2 * MB_OUTER

            if total > min_cw:
                min_cw = total
            _scan(child)

    _scan(root)
    if min_cw % 2 != 0:
        min_cw += 1
    return min_cw


def innerWidth_get(nodes: list[Node]) -> int:
    """Return the uniform chip inner width for a set of nodes.

    Inner width = longest func label + 2 * CHIP_PAD, so every chip has at
    least CHIP_PAD columns of padding on each side of its centered label.
    This value is shared across all chips in the diagram for visual alignment.

    Args:
        nodes: All nodes whose func labels are considered.

    Returns:
        Chip inner width in canvas columns (>= 2 * CHIP_PAD).
    """
    max_func_len: int = max((len(n.func) for n in nodes), default=0)
    return max_func_len + CHIP_PAD * 2


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
    if root.input_signal:
        max_lbl = max(max_lbl, len(root.input_signal))
    if root.input_return:
        max_lbl = max(max_lbl, len(root.input_return))
    # 2 leading dashes + label + 2 trailing dashes + MB_OUTER (box border gap)
    return max(MB_OUTER + MB_INNER, max_lbl + MB_OUTER + 4)


def layout_compute(root: Node, ow: int, cw: int) -> None:
    """Assign canvas coordinates and wire-row indices to every node in the tree.

    Sets node.x, node.y, node.is_root, node.chip_h, node.entry_row, and
    node.return_row for the root and all descendants via a recursive DFS.

    The root chip's left edge is placed at leftMargin_compute(root) so that
    stub signal labels appear fully outside the module box.

    Args:
        root: Root of the call tree to lay out (modified in place).
        ow:   Chip outer width (inner width + 2 border cols).
        cw:   Channel width between adjacent chip columns.
    """
    left_offset: int = leftMargin_compute(root)
    top_offset:  int = MB_TOP

    def _layout(node: Node, x: int, y: int, is_root: bool) -> None:
        """Recursively assign position and geometry to node and its subtree."""
        node.x       = x
        node.y       = y
        node.is_root = is_root
        node.chip_h  = chip_h_precompute(node, is_root)

        n_ch: int = len(node.children)

        if n_ch == 0:
            node.entry_row  = y + 3
            node.return_row = y + 4
        elif is_root:
            node.entry_row  = y + 3
            node.return_row = y + 4 + 3 * (n_ch - 1)
        else:
            node.entry_row  = y + 3
            node.return_row = y + 4 + 3 * (n_ch - 1)

        child_x:  int = x + ow + cw
        cursor_y: int = y

        for child in node.children:
            child.chip_h = chip_h_precompute(child, False)
            _layout(child, child_x, cursor_y, False)
            cursor_y += subtree_canvasH(child) + ROW_GAP

    _layout(root, left_offset, top_offset, True)
