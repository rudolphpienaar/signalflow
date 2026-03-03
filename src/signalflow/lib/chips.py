"""Chip rendering: function boxes, centered labels, in-band ► / ◄ markers."""
from __future__ import annotations

# Standard library
from typing import Final

# Local
from signalflow.config import config, Wire
from signalflow.models import Canvas, Node


def chip_render(canvas: Canvas, node: Node) -> None:
    """Draw the function chip for *node* onto *canvas*.

    Args:
        canvas: The canvas to draw on.
        node: The node representing the function chip.
    """
    x0: int = node.x
    y0: int = node.y
    h: int = node.chip_h
    ow: int = node.ow
    iw: int = ow - 2
    rx: int = x0 + ow - 1

    # 1. Framework (Borders and Separator) - Mode Merge False (Default)
    canvas.set(x0, y0, "┌")
    canvas.hline_force(y0, x0 + 1, rx, "─")
    canvas.set(rx, y0, "┐")
    by: int = y0 + h - 1
    canvas.set(x0, by, "└")
    canvas.hline_force(by, x0 + 1, rx, "─")
    canvas.set(rx, by, "┘")
    for row in range(1, h - 1):
        ry: int = y0 + row
        canvas.set(x0, ry, "│")
        canvas.set(rx, ry, "│")
    canvas.set(x0, y0 + 2, "├")
    canvas.hline_force(y0 + 2, x0 + 1, rx, "─")
    canvas.set(rx, y0 + 2, "┤")

    # 2. Internal Wiring Manifold - Activate Algebraic Merging
    canvas.mode_merge = True

    palette: Final[list[str]] = [
        "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
        "\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m",
    ]

    # High-Resolution Rule: Only stretch if a complex manifold is present
    spacing = config.portVerticalSpacing if node.internal_wiring else 3

    def get_port_info(
        signal_name: str, side_hint: str | None = None
    ) -> tuple[int, str | None]:
        options: list[tuple[int, str]] = []
        for parent_id, port in node.input_ports.items():
            if port.signal == signal_name or port.ret == signal_name:
                row_idx = (
                    node.entry_rows[parent_id]
                    if port.signal == signal_name
                    else node.return_rows[parent_id]
                )
                options.append((row_idx, "L"))
        for i, port in enumerate(node.output_ports.values()):
            if port.signal == signal_name or port.ret == signal_name:
                row_idx = (
                    node.y + 3 + spacing * i
                    if port.signal == signal_name
                    else node.y + 4 + spacing * i
                )
                options.append((row_idx, "R"))
        if not options:
            return -1, None
        if side_hint:
            for opt in options:
                if opt[1] == side_hint:
                    return opt
        return options[0]

    # Pre-sort manifold to ensure deterministic assignment
    wiring = sorted(node.internal_wiring)
    signal_to_track: dict[str, int] = {}
    v_track_count_l: int = 0
    v_track_count_r: int = 0
    
    # Assign Tracks (Manifold Columns)
    for idx, wire_pair in enumerate(wiring):
        if ":" not in wire_pair:
            continue
        src_name, dst_name = wire_pair.split(":")
        src_y, src_side = get_port_info(src_name)
        dst_y, dst_side = get_port_info(dst_name, "R" if src_side == "L" else "L")
        
        if src_y != -1 and dst_y != -1:
            track_key: str = (
                (src_name if src_side == "L" else dst_name)
                if config.share_internal_routes
                else f"{wire_pair}_{idx}"
            )
            if track_key not in signal_to_track:
                if dst_side == "L": # Manifold on the left side
                    v_x: int = x0 + 2 + 2 * v_track_count_l
                    v_track_count_l += 1
                else: # Manifold on the right side
                    v_x: int = rx - 2 - 2 * v_track_count_r
                    v_track_count_r += 1
                if v_x <= x0: v_x = x0 + 1
                if v_x >= rx: v_x = rx - 1
                signal_to_track[track_key] = v_x

    # Draw Manifold Traces
    # To implement "Zoned Port" resolution, we stagger rows within the port gap.
    port_hit_count: dict[int, int] = {}

    for idx, wire_pair in enumerate(wiring):
        if ":" not in wire_pair:
            continue
        src_name, dst_name = wire_pair.split(":")
        src_y, src_side = get_port_info(src_name)
        dst_y, dst_side = get_port_info(dst_name, "R" if src_side == "L" else "L")
        if src_y == -1 or dst_y == -1:
            continue
        color: str | None = (
            palette[idx % len(palette)] if config.internalWireColorize else None
        )

        # 1. Straight Line Short-Circuit: Prevent Vertical Tracks for pass-throughs
        if src_y == dst_y and src_side != dst_side:
            canvas.hline_pierce(src_y, x0, rx + 1, color)
            continue

        # 2. Complex Manifold Logic
        track_key: str = (
            (src_name if src_side == "L" else dst_name)
            if config.share_internal_routes
            else f"{wire_pair}_{idx}"
        )
        v_x: int | None = signal_to_track.get(track_key)
        if v_x is None:
            # Case for straight-line connections (Wall to Wall)
            if src_y == dst_y and src_side != dst_side:
                canvas.hline_pierce(src_y, x0, rx + 1, color)
            continue

        # Zoned Port Logic: Stagger rows within the gap provided by portVerticalSpacing
        # This makes every horizontal line physically distinct and visible.
        offset = port_hit_count.get(src_y, 0)
        logical_y_src = src_y + (offset % (config.portVerticalSpacing - 1))
        port_hit_count[src_y] = offset + 1

        # Vertical Riser from physical port to its logical manifold row
        if src_y != logical_y_src:
            canvas.vline(x0 + 1 if src_side == 'L' else rx - 1, 
                         min(src_y, logical_y_src), max(src_y, logical_y_src) + 1, 
                         color=color, flow="down" if src_y < logical_y_src else "up")

        # Manifold Routing: Start at x0 to pierce the left wall correctly
        if src_side == "L":
            canvas.hline_pierce(logical_y_src, x0, v_x + 1, color)
        else:
            canvas.hline_pierce(logical_y_src, v_x, rx + 1, color)

        # Vertical Track (Connecting planes)
        if logical_y_src < dst_y:
            canvas.vline(v_x, logical_y_src, dst_y + 1, color=color, flow="down")
        else:
            canvas.vline(v_x, dst_y, logical_y_src + 1, color=color, flow="up")

        # Manifold Convergence: End at rx+1 to pierce the right wall correctly
        if dst_side == "L":
            canvas.hline_pierce(dst_y, x0, v_x + 1, color)
        else:
            canvas.hline_pierce(dst_y, v_x, rx + 1, color)

    # Deactivate algebraic merging after manifold is complete
    canvas.mode_merge = False

    # 3. External Wall Piercings (Ports)
    # DEPRECATED: Manual CR overrides removed. 
    # Piercings are now handled reactively by the algebraic manifold and external wires.

    # 4. Leaf U-turns
    if not node.children and not node.internal_wiring:
        for parent_id in node.input_ports:
            ey, ry = node.entry_rows[parent_id], node.return_rows[parent_id]
            canvas.hline_force(ey, x0 + 1, x0 + config.uTurnWidth, "─")
            canvas.set(x0 + config.uTurnWidth, ey, "┐")
            canvas.hline_force(ry, x0 + 1, x0 + config.uTurnWidth, "─")
            canvas.set(x0 + config.uTurnWidth, ry, "┘")

    # 5. Labels (Sovereign Overlay)
    content: str = node.func.center(iw)[:iw]
    canvas.text(x0 + 1, y0 + 1, content)
    if node.is_root and 0 in node.input_ports and not node.children:
        p = node.input_ports[0]
        ey, ry = node.y + 3, node.y + 4
        canvas.set(x0 - 1, ey, Wire.RA)
        if p.signal:
            canvas.text(2, ey, p.signal[: x0 - 4])
        if p.ret:
            canvas.text(2, ry, p.ret[: x0 - 4])
