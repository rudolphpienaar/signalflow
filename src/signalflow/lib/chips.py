"""Chip rendering: function boxes, centered labels, in-band ► / ◄ markers.

Each function chip is a box drawn on the canvas with:
  - A centered func label at row y+1.
  - A separator (├──┤) at row y+2.
  - Wire-entry/return rows starting at y+3, governed by node type.

Chip inner width = 2 * CHIP_PAD + len(func_name) (minimum per function chip).
All chips in a diagram share a uniform outer width derived from the longest
func label so that columns visually align.

Key function:
    chip_render: Draw one chip onto the canvas.
"""
from __future__ import annotations

from signalflow.config import UTURN_W, Wire
from signalflow.models import Canvas, Node


def chip_render(canvas: Canvas, node: Node) -> None:
    """Draw the function chip for *node* onto *canvas*."""
    x0: int = node.x
    y0: int = node.y
    h:  int = node.chip_h
    ow: int = node.ow
    iw: int = ow - 2
    rx: int = x0 + ow - 1

    # Top border
    canvas.set(x0, y0, '┌')
    canvas.hline_force(y0, x0 + 1, rx, '─')
    canvas.set(rx, y0, '┐')

    # Bottom border
    by: int = y0 + h - 1
    canvas.set(x0, by, '└')
    canvas.hline_force(by, x0 + 1, rx, '─')
    canvas.set(rx, by, '┘')

    # Side borders
    for row in range(1, h - 1):
        ry: int = y0 + row
        canvas.set(x0, ry, '│')
        canvas.set(rx, ry, '│')

    # Func label centered at y+1
    content: str = node.func.center(iw)[:iw]
    canvas.text(x0 + 1, y0 + 1, content)

    # Separator ├──┤ at y+2 (overwrites │ from side borders)
    canvas.set(x0, y0 + 2, '├')
    canvas.hline_force(y0 + 2, x0 + 1, rx, '─')
    canvas.set(rx, y0 + 2, '┤')

    # Rendering Ports
    # Every chip is now treated as a potential Hub.
    
    # 1. Left Wall (Incoming Connections)
    for i, (parent_id, port) in enumerate(node.input_ports.items()):
        ey = node.entry_rows[parent_id]
        ry = node.return_rows[parent_id]
        
        # Pierce left wall
        if node.is_root and parent_id == 0:
            # Special case for Root stub
            pass
        else:
            canvas.set(x0, ey, Wire.CR)
            canvas.set(x0, ry, Wire.CR)
            
            # If leaf, draw U-turn at THESE rows
            if not node.children:
                canvas.hline_force(ey, x0 + 1, x0 + UTURN_W, '─')
                canvas.set(x0 + UTURN_W, ey, '┐')
                canvas.hline_force(ry, x0 + 1, x0 + UTURN_W, '─')
                canvas.set(x0 + UTURN_W, ry, '┘')

    # 2. Right Wall (Outgoing Connections)
    # Map child calls to specific rows.
    for i, (child_id, port) in enumerate(node.output_ports.items()):
        ey = node.y + 3 + 3 * i
        ry = node.y + 4 + 3 * i
        
        # Pierce right wall
        canvas.set(rx, ey, Wire.CR)
        canvas.set(rx, ry, Wire.CR)
        
    # 3. Internal Wiring Manifold
    from signalflow.lib.wires import hline_pierce
    
    def get_port_info(signal_name, side_hint=None):
        """Find the canvas row and wall side for a named signal."""
        options = []
        for parent_id, port in node.input_ports.items():
            if port.signal == signal_name or port.ret == signal_name:
                options.append((node.entry_rows[parent_id] if port.signal == signal_name else node.return_rows[parent_id], 'L'))
        for i, (child_id, port) in enumerate(node.output_ports.items()):
            if port.signal == signal_name or port.ret == signal_name:
                options.append((node.y + 3 + 3 * i if port.signal == signal_name else node.y + 4 + 3 * i, 'R'))
        
        if not options: return -1, None
        if side_hint:
            for opt in options:
                if opt[1] == side_hint: return opt
        return options[0]

    v_track_count = 0
    for wire_pair in node.internal_wiring:
        if ':' not in wire_pair: continue
        src_name, dst_name = wire_pair.split(':')
        src_y, src_side = get_port_info(src_name)
        dst_y, dst_side = get_port_info(dst_name, 'R' if src_side == 'L' else 'L')
        
        if src_y != -1 and dst_y != -1:
            if src_y == dst_y and src_side != dst_side:
                hline_pierce(canvas, src_y, x0 + 1, rx)
            else:
                # Vertical/Diagonal Threading (Shortest-path staggered bus)
                # Anchor the vertical track to the destination wall
                if dst_side == 'L':
                    v_x = x0 + 2 + v_track_count
                    if v_x >= rx: v_x = rx - 1
                else: # RIGHT
                    v_x = rx - 2 - v_track_count
                    if v_x <= x0: v_x = x0 + 1
                
                v_track_count += 1
                
                # 1. Source Wall to Vertical Track
                if src_side == 'L':
                    hline_pierce(canvas, src_y, x0 + 1, v_x)
                    canvas.set(v_x, src_y, Wire.RD if src_y < dst_y else Wire.RU)
                else: # RIGHT
                    hline_pierce(canvas, src_y, v_x + 1, rx)
                    canvas.set(v_x, src_y, Wire.LD if src_y < dst_y else Wire.LU)
                
                # 2. Vertical Segment
                canvas.vline(v_x, min(src_y, dst_y), max(src_y, dst_y) + 1)
                
                # 3. Vertical Track to Destination Wall
                if dst_side == 'L':
                    hline_pierce(canvas, dst_y, x0 + 1, v_x)
                    canvas.set(v_x, dst_y, Wire.DL if src_y < dst_y else Wire.UL)
                else: # RIGHT
                    hline_pierce(canvas, dst_y, v_x + 1, rx)
                    canvas.set(v_x, dst_y, Wire.DR if src_y < dst_y else Wire.UR)


    # 4. Root Stubs (Legacy/Special Logic)
    if node.is_root and 0 in node.input_ports:
        p = node.input_ports[0]
        ey, ry = node.y + 3, node.y + 4
        # Draw stubs if no children OR if explicitly requested
        if not node.children:
            for row in (ey, ry):
                for x in range(0, x0):
                    ch = canvas.get(x, row)
                    if ch == ' ': canvas.set(x, row, '─')
                    elif ch in ('║', '╫'): canvas.set(x, row, '╫')
            if p.signal:
                canvas.set(x0 - 1, ey, Wire.RA)
                canvas.text(2, ey, p.signal[:x0 - 4])
            if p.ret:
                canvas.set(x0 - 1, ry, Wire.LA)
                canvas.text(2, ry, p.ret[:x0 - 4])
        else:
            # Root parent: just arrows if needed
            if p.signal: canvas.set(x0 - 1, ey, Wire.RA)

        # node.entry_row and node.return_row are already set by layout_compute
