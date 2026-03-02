"""Chip rendering: function boxes, centered labels, in-band ► / ◄ markers."""
from __future__ import annotations

# Standard library
from typing import Final

# Local
from signalflow.config import Wire
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

    from signalflow.config import config

    palette: Final[list[str]] = [
        "\033[31m",
        "\033[32m",
        "\033[33m",
        "\033[34m",
        "\033[35m",
        "\033[36m",
        "\033[91m",
        "\033[92m",
        "\033[93m",
        "\033[94m",
        "\033[95m",
        "\033[96m",
    ]

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
                    node.y + 3 + 3 * i
                    if port.signal == signal_name
                    else node.y + 4 + 3 * i
                )
                options.append((row_idx, "R"))
        if not options:
            return -1, None
        if side_hint:
            for opt in options:
                if opt[1] == side_hint:
                    return opt
        return options[0]

    signal_to_track: dict[str, int] = {}
    v_track_count: int = 0
    # Assign Tracks (Independent tracks by default for clean junctions)
    for wire_pair in sorted(node.internal_wiring):
        if ":" not in wire_pair:
            continue
        src_name, dst_name = wire_pair.split(":")
        src_y, src_side = get_port_info(src_name)
        dst_y, dst_side = get_port_info(dst_name, "R" if src_side == "L" else "L")
        if src_y != -1 and dst_y != -1 and src_y != dst_y:
            track_key: str = (
                (src_name if src_side == "L" else dst_name)
                if config.share_internal_routes
                else wire_pair
            )
            if track_key not in signal_to_track:
                v_x: int = (
                    x0 + 2 + 2 * v_track_count
                    if dst_side == "L"
                    else rx - 2 - 2 * v_track_count
                )
                if v_x <= x0:
                    v_x = x0 + 1
                if v_x >= rx:
                    v_x = rx - 1
                signal_to_track[track_key] = v_x
                v_track_count += 1

    # Draw Manifold Traces
    for idx, wire_pair in enumerate(node.internal_wiring):
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

        if src_y == dst_y and src_side != dst_side:
            canvas.hline_pierce(src_y, x0 + 1, rx, color)
        else:
            track_key: str = (
                (src_name if src_side == "L" else dst_name)
                if config.share_internal_routes
                else wire_pair
            )
            v_x: int | None = signal_to_track.get(track_key)
            if v_x is None:
                continue

            # Base Lines
            if src_side == "L":
                canvas.hline_pierce(src_y, x0 + 1, v_x + 1, color)
            else:
                canvas.hline_pierce(src_y, v_x, rx, color)

            # Vertical Segment (Inclusive of both endpoints to trigger intent bitmasks)
            if src_y < dst_y:
                canvas.vline(v_x, src_y, dst_y + 1, color=color, flow="down")
            else:
                canvas.vline(v_x, dst_y, src_y + 1, color=color, flow="up")

            if dst_side == "L":
                canvas.hline_pierce(dst_y, x0 + 1, v_x + 1, color)
            else:
                canvas.hline_pierce(dst_y, v_x, rx, color)

    # Deactivate algebraic merging
    canvas.mode_merge = False

    # 3. External Wall Piercings (Ports)
    for parent_id in node.input_ports:
        canvas.set(x0, node.entry_rows[parent_id], Wire.CR)
        canvas.set(x0, node.return_rows[parent_id], Wire.CR)
    for i in range(len(node.output_ports)):
        canvas.set(rx, node.y + 3 + 3 * i, Wire.CR)
        canvas.set(rx, node.y + 4 + 3 * i, Wire.CR)

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
