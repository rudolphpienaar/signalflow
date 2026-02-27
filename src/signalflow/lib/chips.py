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


def chip_render(canvas: Canvas, node: Node, ow: int) -> None:
    """Draw the function chip for *node* onto *canvas*.

    Renders the box border, centered func label, ├──┤ separator, and the
    wire-entry/return glyphs appropriate for the node type:

    - Leaf:        U-turn (──┐ / ──┘) at y+3/y+4; ┼ on left wall; ►/◄
                   approach arrows at x-1; stubs with signal labels drawn to
                   the left of the module box for root leaves.
    - Root parent: ├ exits on the right wall at y+3+3i / y+4+3i per child.
    - Inner node:  ┼ on both walls at entry/return; ├ on right wall for
                   additional children.

    Args:
        canvas: Mutable 2-D character grid to draw onto.
        node:   Node whose geometry (x, y, chip_h, is_root, children) drives
                all rendering decisions.  entry_row and return_row are set
                as a side-effect of this call.
        ow:     Chip outer width (inner width + 2 border cols).
    """
    x0: int = node.x
    y0: int = node.y
    h:  int = node.chip_h
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

    n_ch: int = len(node.children)

    if n_ch == 0:
        # Leaf: U-turn at y+3/y+4; both left-wall rows pierce (┼)
        ey:   int = y0 + 3
        ry_u: int = y0 + 4
        canvas.set(x0, ey, '┼')
        canvas.hline_force(ey, x0 + 1, x0 + UTURN_W, '─')
        canvas.set(x0 + UTURN_W, ey, '┐')
        # Return row is adjacent — no intermediate │
        canvas.set(x0, ry_u, '┼')
        canvas.hline_force(ry_u, x0 + 1, x0 + UTURN_W, '─')
        canvas.set(x0 + UTURN_W, ry_u, '┘')
        node.entry_row  = ey
        node.return_row = ry_u

        # Approach arrows one column left of the chip wall.
        # wire_forward_render confirms ► at the same position for connected
        # leaves. ◄ is now rendered by wire_return_render at the parent side.
        canvas.set(x0 - 1, ey, '►')

        # For standalone root leaf: draw stubs and signal labels to the left
        # of the module box.  The module-box border ║ is replaced by ╫ where
        # the stub wire crosses it.
        # If node has children, its signal/return_signal are used for the
        # internal wires between chips, so no stubs are drawn.
        if node.is_root and not node.children:
            for row in (ey, ry_u):
                # Stubs extend from col 0 to the chip wall (x0-1)
                for x in range(0, x0):
                    ch: str = canvas.get(x, row)
                    if ch == ' ':
                        canvas.set(x, row, '─')
                    elif ch in ('║', '╫'):
                        canvas.set(x, row, '╫')
            # Root stubs: arrows flush against chip wall (x0-1)
            if node.input_signal:
                canvas.set(x0 - 1, ey,   Wire.RA)
            if node.input_return:
                canvas.set(x0 - 1, ry_u, Wire.LA)

            # Label starts at col 2 (after two leading dashes).
            # x0-4 ensures space for label + arrow (at x0-1) + wall (at x0).
            if node.input_signal:
                canvas.text(2, ey,   node.input_signal[:x0 - 4])
            if node.input_return:
                canvas.text(2, ry_u, node.input_return[:x0 - 4])

    elif node.is_root:
        # Root parent: left wall never pierced; right wall ├ per child pair.
        # Internal: vertical thread connecting child N return to child N+1 call.
        for i in range(n_ch):
            ry_c = y0 + 3 + 3 * i
            ry_r = y0 + 4 + 3 * i
            
            # Use ┼ if this port is part of an internal thread, else ├
            # A call port is threaded if it's NOT the first child (i > 0)
            # A return port is threaded if it's NOT the last child (i < n_ch - 1)
            canvas.set(rx, ry_c, '┼' if i > 0 else '├')
            canvas.set(rx, ry_r, '┼' if i < n_ch - 1 else '├')

            if i < n_ch - 1:
                # Thread return of i to call of i+1
                # Enters from RIGHT wall, turns DOWN (┌).
                # Arrives from above, turns RIGHT (└).
                canvas.set(rx - 1, ry_r,     '┌')
                canvas.set(rx - 1, ry_r + 1, '│')
                canvas.set(rx - 1, ry_r + 2, '└')

    else:
        # Non-root parent: left wall ┼ at entry (y+3) and return (node.return_row).
        # Internal: horizontal passthrough wires and vertical threading.
        entry_y: int = y0 + 3
        exit_y:  int = node.return_row
        canvas.set(x0, entry_y, Wire.CR)
        canvas.set(x0, exit_y,  Wire.CR)

        # Draw entry passthrough: x0 → rx (always row y+3)
        from signalflow.lib.wires import hline_pierce
        hline_pierce(canvas, entry_y, x0 + 1, rx)

        # Sequential threading
        for i in range(n_ch):
            ry_c = entry_y + 3 * i
            ry_r = entry_y + 1 + 3 * i

            # Right wall is ALWAYS pierced for child calls/returns
            canvas.set(rx, ry_c, Wire.CR)
            canvas.set(rx, ry_r, Wire.CR)

            if i < n_ch - 1:
                # Thread return of child i to call of child i+1.
                # Flows LEFT from rx, turns DOWN at rx-1.
                # Arrives from above at rx-1, turns RIGHT to rx.
                canvas.set(rx - 1, ry_r,     Wire.LD) # ┌
                canvas.set(rx - 1, ry_r + 1, Wire.DN) # │
                canvas.set(rx - 1, ry_r + 2, Wire.UR) # └
                # Horizontal segments to connect walls to the threading track
                canvas.set(rx - 1, ry_r,     '┌') # Wire.LD
                canvas.set(rx - 1, ry_r + 2, '└') # Wire.UR
            else:
                # Final child return: flow all the way back to the left wall x0.
                hline_pierce(canvas, ry_r, x0 + 1, rx)

        # node.entry_row and node.return_row are already set by layout_compute
