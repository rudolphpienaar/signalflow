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


def wire_forward_render(canvas: Canvas, parent: Node, child: Node) -> None:
    """Draw the forward call wire from parent chip to child chip."""
    # Find the specific row for this connection
    exit_y  = parent.y + 3 + 3 * list(parent.output_ports.keys()).index(id(child))
    entry_y = child.entry_rows[id(parent)]
    
    entry_x = child.x
    parent_rx = parent.x + parent.ow - 1

    # Arrows are always flush against the chip ports
    arrow_x_exit  = parent_rx + 1
    arrow_x_entry = entry_x - 1

    if exit_y == entry_y:
        channel_x = entry_x
        hline_pierce(canvas, exit_y, parent_rx + 1, entry_x)
        canvas.set(arrow_x_exit, exit_y, Wire.RA)
        canvas.set(arrow_x_entry, entry_y, Wire.RA)
    else:
        # Unified Staggering Rule: Use max of port indices on both walls.
        p_idx = list(parent.output_ports.keys()).index(id(child))
        c_idx = list(child.input_ports.keys()).index(id(parent))
        stagger_idx = max(p_idx, c_idx)
        
        # Vertical Affinity: The track closest to the wall (Rightmost) 
        # must be the one encountered FIRST by the vertical flow.
        # i.e., Top-most port for Down-flow, Bottom-most port for Up-flow.
        n_stagger = max(len(parent.output_ports), len(child.input_ports))
        if exit_y > entry_y: # Ascending
            stagger_idx = (n_stagger - 1) - stagger_idx

        # Max space needed for any child-side label in this group
        max_child_lbl = 0
        for c in parent.children:
            if c.input_ports:
                p = c.input_ports.get(id(parent))
                if p:
                    lbl_f = len(p.signal) if p.signal else 0
                    lbl_r = len(p.ret) if p.ret else 0
                    max_child_lbl = max(max_child_lbl, lbl_f, lbl_r)
        
        stagger_start = max_child_lbl + 3
        channel_x = entry_x - stagger_start - 2 * stagger_idx
        
        hline_pierce(canvas, exit_y, parent_rx + 1, channel_x)
        canvas.set(arrow_x_exit, exit_y, Wire.RA)
        if exit_y < entry_y:
            canvas.set(channel_x, exit_y, Wire.RD)
            canvas.vline(channel_x, exit_y + 1, entry_y)
            canvas.set(channel_x, entry_y, Wire.DR)
        else:
            canvas.set(channel_x, exit_y, Wire.RU)
            canvas.vline(channel_x, entry_y + 1, exit_y)
            canvas.set(channel_x, entry_y, Wire.UR)
        hline_pierce(canvas, entry_y, channel_x + 1, entry_x)
        canvas.set(arrow_x_entry, entry_y, Wire.RA)

    # Labels
    p_port = parent.output_ports.get(id(child))
    c_port = child.input_ports.get(id(parent))
    p_signal = p_port.signal if p_port else None
    c_signal = c_port.signal if c_port else None

    if p_signal:
        label_x = arrow_x_exit + 1
        limit_x = channel_x if exit_y != entry_y else arrow_x_entry
        if exit_y == entry_y and c_signal:
            limit_x = min(limit_x, arrow_x_entry - len(c_signal) - 1)
        max_label = max(0, limit_x - label_x)
        canvas.text(label_x, exit_y, p_signal[:max_label])

    if c_signal:
        label_len = len(c_signal)
        label_x   = arrow_x_entry - label_len
        limit_x   = channel_x + 1 if exit_y != entry_y else arrow_x_exit + 1
        if exit_y == entry_y and p_signal:
            limit_x = max(limit_x, arrow_x_exit + 1 + len(p_signal[:max_label]) + 1)
        label_x   = max(limit_x, label_x)
        max_label = arrow_x_entry - label_x
        canvas.text(label_x, entry_y, c_signal[:max_label])


def wire_return_render(canvas: Canvas, parent: Node, child: Node) -> None:
    """Draw the return wire from child chip back to parent chip."""
    # Find specific rows
    child_ret_y  = child.return_rows[id(parent)]
    parent_ret_y = parent.y + 4 + 3 * list(parent.output_ports.keys()).index(id(child))
    
    child_lx = child.x
    parent_rx = parent.x + parent.ow - 1

    arrow_x_exit  = child_lx - 1
    arrow_x_entry = parent_rx + 1

    if child_ret_y == parent_ret_y:
        channel_x = child_lx
        hline_pierce(canvas, child_ret_y, parent_rx + 1, child_lx)
        canvas.set(arrow_x_exit, child_ret_y, Wire.LA)
    else:
        # Unified Staggering Rule
        p_idx = list(parent.output_ports.keys()).index(id(child))
        c_idx = list(child.input_ports.keys()).index(id(parent))
        stagger_idx = max(p_idx, c_idx)

        # Vertical Affinity
        n_stagger = max(len(parent.output_ports), len(child.input_ports))
        if child_ret_y < parent_ret_y: # Ascending (Target parent is ABOVE)
            stagger_idx = (n_stagger - 1) - stagger_idx

        max_child_lbl = 0
        for c in parent.children:
            if c.input_ports:
                p = c.input_ports.get(id(parent))
                if p:
                    lbl_f = len(p.signal) if p.signal else 0
                    lbl_r = len(p.ret) if p.ret else 0
                    max_child_lbl = max(max_child_lbl, lbl_f, lbl_r)
        
        stagger_start = max_child_lbl + 3
        
        # Helix Flip
        if child_ret_y > parent_ret_y:
            channel_x = child_lx - stagger_start - 1 - 2 * stagger_idx
        else:
            channel_x = child_lx - stagger_start + 1 - 2 * stagger_idx
        
        hline_pierce(canvas, child_ret_y, channel_x + 1, child_lx)
        canvas.set(arrow_x_exit, child_ret_y, Wire.LA)
        if child_ret_y > parent_ret_y:
            canvas.set(channel_x, child_ret_y, Wire.LU)
            canvas.vline(channel_x, parent_ret_y + 1, child_ret_y)
            canvas.set(channel_x, parent_ret_y, Wire.UL)
        else:
            canvas.set(channel_x, child_ret_y, Wire.LD)
            canvas.vline(channel_x, child_ret_y + 1, parent_ret_y)
            canvas.set(channel_x, parent_ret_y, Wire.DL)
        hline_pierce(canvas, parent_ret_y, parent_rx + 2, channel_x)

    canvas.set(arrow_x_entry, parent_ret_y, Wire.LA)

    p_port = parent.output_ports.get(id(child))
    c_port = child.input_ports.get(id(parent))
    p_ret = p_port.ret if p_port else None
    c_ret = c_port.ret if c_port else None

    if p_ret:
        label_x = arrow_x_entry + 1
        limit_x = channel_x if child_ret_y != parent_ret_y else arrow_x_exit
        if child_ret_y == parent_ret_y and c_ret:
            limit_x = min(limit_x, arrow_x_exit - len(c_ret) - 1)
        max_label_p = max(0, limit_x - label_x)
        canvas.text(label_x, parent_ret_y, p_ret[:max_label_p])

    if c_ret:
        label_len = len(c_ret)
        label_x   = arrow_x_exit - label_len
        limit_x   = channel_x + 1 if child_ret_y != parent_ret_y else arrow_x_entry + 1
        if child_ret_y == parent_ret_y and p_ret:
            limit_x = max(limit_x, arrow_x_entry + 1 + len(p_ret[:max_label_p]) + 1)
        label_x   = max(limit_x, label_x)
        max_label_c = arrow_x_exit - label_x
        canvas.text(label_x, child_ret_y, c_ret[:max_label_c])


def thread_render(canvas: Canvas, root: Node) -> None:
    """Drive the wire through the full DFS call tree."""

    def _wire(node: Node) -> None:
        for child in node.children:
            wire_forward_render(canvas, node, child)
            _wire(child)
            wire_return_render(canvas, node, child)

    _wire(root)
