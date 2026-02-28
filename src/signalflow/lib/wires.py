"""Wire rendering: forward calls, returns, DFS thread driver."""

from signalflow.config import MB_OUTER, Wire
from signalflow.models import Canvas, Node


def hline_pierce(canvas: Canvas, y: int, x0: int, x1: int) -> None:
    """Horizontal wire from x0 to x1-1 on row y, piercing existing vertical tracks."""
    for x in range(x0, x1):
        current = canvas.get(x, y)
        if current in (' ', Wire.RT):
            canvas.set(x, y, Wire.RT)
        elif current in (Wire.DN, '║', '╫', '│', '├', '┤'):
            # These are vertical segments or wall characters that should become crossings
            canvas.set(x, y, Wire.MC if current in ('║', '╫') else Wire.CR)
        elif current in (Wire.LA, Wire.RA, Wire.RD, Wire.RU, Wire.DR, Wire.UR):
            # Preserve arrows and turns (they are already part of a valid wire structure)
            continue


def wire_forward_render(canvas: Canvas, parent: Node, child: Node, ow: int) -> None:
    """Draw the forward call wire from parent chip to child chip."""
    n_ch      = len(parent.children)
    child_idx = parent.children.index(child)
    parent_rx = parent.x + ow - 1

    if parent.is_root:
        exit_y = parent.y + 3 + 3 * child_idx
    else:
        exit_y = parent.entry_row + 3 * child_idx

    entry_y = child.entry_row
    entry_x = child.x

    # Arrows are always flush against the chip ports
    arrow_x_exit  = parent_rx + 1
    arrow_x_entry = entry_x - 1

    if exit_y == entry_y:
        channel_x = entry_x
        hline_pierce(canvas, exit_y, parent_rx + 1, entry_x)
        canvas.set(arrow_x_exit, exit_y, Wire.RA)
        canvas.set(arrow_x_entry, entry_y, Wire.RA)
    else:
        # Stagger Rule: Earlier children (top) bend further RIGHT.
        # This prevents lower horizontal wires from crossing upper vertical ones.
        max_child_lbl = 0
        for c in parent.children:
            lbl_f = 0
            lbl_r = 0
            if c.input_ports:
                lbl_f = len(c.input_ports[0].signal) if c.input_ports[0].signal else 0
                lbl_r = len(c.input_ports[0].ret) if c.input_ports[0].ret else 0
            max_child_lbl = max(max_child_lbl, lbl_f, lbl_r)
        
        # Buffer space: [label] + [arrow (1)] + [gap (1)] + [staggered track (1)]
        stagger_start = max_child_lbl + 3
        # Argument (Forward) is to the Right of Return (X vs X-1).
        # Child 0 is at (X_child - stagger_start).
        # Child N is at (X_child - stagger_start - 2*N).
        channel_x = entry_x - stagger_start - 2 * child_idx
        
        hline_pierce(canvas, exit_y, parent_rx + 1, channel_x)
        canvas.set(arrow_x_exit, exit_y, Wire.RA)
        if exit_y < entry_y:
            # Descending: RIGHT turns DOWN (RD), ABOVE turns RIGHT (DR)
            canvas.set(channel_x, exit_y, Wire.RD)
            canvas.vline(channel_x, exit_y + 1, entry_y)
            canvas.set(channel_x, entry_y, Wire.DR)
        else:
            # Ascending: RIGHT turns UP (RU), BELOW turns RIGHT (UR)
            canvas.set(channel_x, exit_y, Wire.RU)
            canvas.vline(channel_x, entry_y + 1, exit_y)
            canvas.set(channel_x, entry_y, Wire.UR)
        hline_pierce(canvas, entry_y, channel_x + 1, entry_x)
        canvas.set(arrow_x_entry, entry_y, Wire.RA)

    # Label Limiting Logic:
    # Forward wires consist of: [Segment A (exit_y)] + [Vertical] + [Segment B (entry_y)]

    # Parent-side label: ALWAYS on Segment A (at exit_y), flush against exit arrow
    p_signal = parent.output_ports[child_idx].signal if child_idx < len(parent.output_ports) else None
    if p_signal:
        label_x = arrow_x_exit + 1
        # Must not cross into the channel bend (at channel_x)
        limit_x = channel_x if exit_y != entry_y else arrow_x_entry
        # Also must not overlap child label if on same row
        c_signal = child.input_ports[0].signal if child.input_ports else None
        if exit_y == entry_y and c_signal:
            limit_x = min(limit_x, arrow_x_entry - len(c_signal) - 1)

        max_label = max(0, limit_x - label_x)
        canvas.text(label_x, exit_y, p_signal[:max_label])

    # Child-side label: ALWAYS on Segment B (at entry_y), flush against entry arrow
    c_signal = child.input_ports[0].signal if child.input_ports else None
    if c_signal:
        label_len = len(c_signal)
        label_x   = arrow_x_entry - label_len
        # Must not cross back into the channel bend (at channel_x)
        limit_x   = channel_x + 1 if exit_y != entry_y else arrow_x_exit + 1
        # If on same row, parent label wins the leftmost space
        if exit_y == entry_y and p_signal:
            limit_x = max(limit_x, arrow_x_exit + 1 + len(p_signal[:max_label]) + 1)

        label_x   = max(limit_x, label_x)
        max_label = arrow_x_entry - label_x
        canvas.text(label_x, entry_y, c_signal[:max_label])


def wire_return_render(canvas: Canvas, parent: Node, child: Node, ow: int) -> None:
    """Draw the return wire from child chip back to parent chip."""
    n_ch       = len(parent.children)
    child_idx  = parent.children.index(child)
    parent_rx  = parent.x + ow - 1

    if parent.is_root:
        parent_ret_y = parent.y + 4 + 3 * child_idx
    else:
        parent_ret_y = parent.entry_row + 1 + 3 * child_idx

    child_ret_y = child.return_row
    child_lx    = child.x

    # Arrows are always flush against the chip ports
    arrow_x_exit  = child_lx - 1
    arrow_x_entry = parent_rx + 1

    if child_ret_y == parent_ret_y:
        channel_x = child_lx
        hline_pierce(canvas, child_ret_y, parent_rx + 1, child_lx)
        canvas.set(arrow_x_exit, child_ret_y, Wire.LA)
    else:
        # Double Helix: Return is to the LEFT of Argument (X-1 vs X).
        # Earlier children bend further RIGHT.
        max_child_lbl = 0
        for c in parent.children:
            max_child_lbl = max(max_child_lbl, 
                                max((len(p.signal or "") for p in c.input_ports), default=0),
                                max((len(p.ret or "") for p in c.input_ports), default=0))
        
        stagger_start = max_child_lbl + 3
        # Child 0 Return is at (X_child - stagger_start - 1)
        channel_x = child_lx - stagger_start - 1 - 2 * child_idx
        
        hline_pierce(canvas, child_ret_y, channel_x + 1, child_lx)
        canvas.set(arrow_x_exit, child_ret_y, Wire.LA)
        if child_ret_y > parent_ret_y:
            # Ascending: LEFT turns UP (LU), BELOW turns LEFT (UL)
            canvas.set(channel_x, child_ret_y, Wire.LU)
            canvas.vline(channel_x, parent_ret_y + 1, child_ret_y)
            canvas.set(channel_x, parent_ret_y, Wire.UL)
        else:
            # Descending: LEFT turns DOWN (LD), ABOVE turns LEFT (DL)
            canvas.set(channel_x, child_ret_y, Wire.LD)
            canvas.vline(channel_x, child_ret_y + 1, parent_ret_y)
            canvas.set(channel_x, parent_ret_y, Wire.DL)
        hline_pierce(canvas, parent_ret_y, parent_rx + 2, channel_x)

    # Return entry arrow (at parent wall)
    canvas.set(arrow_x_entry, parent_ret_y, Wire.LA)

    # Parent and Child labels
    p_ret = parent.output_ports[child_idx].ret if child_idx < len(parent.output_ports) else None
    c_ret = child.input_ports[0].ret if child.input_ports else None

    # Parent-side label: ALWAYS on caller's horizontal segment (at parent_ret_y)
    # This is an entry port, so label is to the RIGHT of the arrow: ◄label
    if p_ret:
        label_x = arrow_x_entry + 1
        # Limit to the channel bend
        limit_x = channel_x if child_ret_y != parent_ret_y else arrow_x_exit
        # Limit to child label if on same row
        if child_ret_y == parent_ret_y and c_ret:
            limit_x = min(limit_x, arrow_x_exit - len(c_ret) - 1)

        max_label_p = max(0, limit_x - label_x)
        canvas.text(label_x, parent_ret_y, p_ret[:max_label_p])

    # Child-side label: ALWAYS on child's horizontal segment (at child_ret_y)
    # This is an exit port, so label is to the LEFT of the arrow: label◄
    if c_ret:
        label_len = len(c_ret)
        label_x   = arrow_x_exit - label_len
        # Limit to channel bend
        limit_x   = channel_x + 1 if child_ret_y != parent_ret_y else arrow_x_entry + 1
        # Limit to parent label if on same row
        if child_ret_y == parent_ret_y and p_ret:
            limit_x = max(limit_x, arrow_x_entry + 1 + len(p_ret[:max_label_p]) + 1)

        label_x   = max(limit_x, label_x)
        max_label_c = arrow_x_exit - label_x
        canvas.text(label_x, child_ret_y, c_ret[:max_label_c])


def thread_render(canvas: Canvas, root: Node, ow: int) -> None:
    """Drive the wire through the full DFS call tree."""

    def _wire(node: Node) -> None:
        for child in node.children:
            wire_forward_render(canvas, node, child, ow)
            _wire(child)
            wire_return_render(canvas, node, child, ow)

    _wire(root)
