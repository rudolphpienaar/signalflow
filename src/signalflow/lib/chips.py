"""Chip rendering: function boxes, centered labels, in-band ► / ◄ markers."""
from __future__ import annotations

# Standard library
from typing import Final

# Local
from signalflow.config import config, Wire
from signalflow.models import Canvas, Node
from signalflow.engine.router.router import VLSIRouter
from signalflow.engine.router.models import Terminal, Location
from signalflow.lib.tree import ew_top_offset as _ew_top_offset


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

    # 1. Framework (Borders and Separator) — mode_merge always False here
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

    # 2. Internal Wiring Manifold — guard BEFORE mode_merge
    if not node.internal_wiring:
        if not node.children:
            for parent_id in node.input_ports:
                ey = node.entry_rows[parent_id]
                ry = node.return_rows[parent_id]
                canvas.hline_force(ey, x0 + 1, x0 + config.uTurnWidth, "─")
                canvas.set(x0 + config.uTurnWidth, ey, "┐")
                canvas.hline_force(ry, x0 + 1, x0 + config.uTurnWidth, "─")
                canvas.set(x0 + config.uTurnWidth, ry, "┘")
        content: str = node.func.center(iw)[:iw]
        canvas.text(x0 + 1, y0 + 1, content)
        if node.is_root and 0 in node.input_ports and not node.children:
            p = node.input_ports[0]
            ey, ry2 = node.y + 3, node.y + 4
            canvas.set(x0 - 1, ey, Wire.RA)
            if p.signal:
                canvas.text(2, ey, p.signal[: x0 - 4])
            if p.ret:
                canvas.text(2, ry2, p.ret[: x0 - 4])
        return

    canvas.mode_merge = True

    palette: Final[list[str]] = [
        "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
        "\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m",
    ]

    spacing: int = config.portVerticalSpacing

    # ------------------------------------------------------------------
    # Helper: which wall does a port name live on?
    # ------------------------------------------------------------------
    def port_side(name: str, prefer: str | None = None) -> str | None:
        """Return 'L' (west) or 'R' (east) for a port name.

        prefer='R' checks output_ports first — used so same-name pass-through
        signals (e.g. 's1:s1') resolve src→'L' and dst→'R'.
        """
        checks = ["L", "R"] if prefer != "R" else ["R", "L"]
        for side in checks:
            if side == "L":
                for port in node.input_ports.values():
                    if port.signal == name or port.ret == name:
                        return "L"
            else:
                for port in node.output_ports.values():
                    if port.signal == name or port.ret == name:
                        return "R"
        return None

    # ------------------------------------------------------------------
    # Build base-row maps: port_name -> list of wall rows
    # ------------------------------------------------------------------
    left_base_rows: dict[str, list[int]] = {}
    for parent_id, port in node.input_ports.items():
        for name in (port.signal, port.ret):
            if name:
                left_base_rows.setdefault(name, [])
                row = (
                    node.entry_rows[parent_id]
                    if port.signal == name
                    else node.return_rows[parent_id]
                )
                if row not in left_base_rows[name]:
                    left_base_rows[name].append(row)

    # ew_off: rows reserved at top of chip interior for E→W ribbon zone.
    # Right-wall ports are shifted down by this amount so E→W trunks have
    # a clean unobstructed band above the wall port rows.
    ew_off: int = _ew_top_offset(node)

    right_base_rows: dict[str, list[int]] = {}
    for i, port in enumerate(node.output_ports.values()):
        for name, offset in ((port.signal, 0), (port.ret, 1)):
            if name:
                right_base_rows.setdefault(name, [])
                row = y0 + 3 + ew_off + spacing * i + offset
                if row not in right_base_rows[name]:
                    right_base_rows[name].append(row)

    # ------------------------------------------------------------------
    # 2.1 Classify wiring pairs: straight-through vs VLSI manifold
    #
    # Straight-through: cross-wall, single-source, single-destination,
    # same wall row — rendered as a full-width hline; no internal anchors.
    # Criterion uses per-role counts (src_counts / dst_counts) to avoid
    # double-counting same-name pass-through signals (s1:s1).
    # ------------------------------------------------------------------
    all_pairs_raw: list[tuple[str, str]] = []
    for w in sorted(node.internal_wiring):
        if ":" not in w:
            continue
        src, dst = w.split(":")
        all_pairs_raw.append((src, dst))

    src_counts: dict[str, int] = {}
    dst_counts: dict[str, int] = {}
    for src, dst in all_pairs_raw:
        src_counts[src] = src_counts.get(src, 0) + 1
        dst_counts[dst] = dst_counts.get(dst, 0) + 1

    straight_pairs: list[tuple[str, str, str | None]] = []
    wiring_pairs: list[tuple[str, str]] = []

    for src, dst in all_pairs_raw:
        s_side = port_side(src) or "L"
        d_side = port_side(dst, prefer="R" if s_side == "L" else "L") or (
            "R" if s_side == "L" else "L"
        )
        if (
            s_side != d_side
            and src_counts.get(src, 0) == 1
            and dst_counts.get(dst, 0) == 1
        ):
            s_rows = left_base_rows if s_side == "L" else right_base_rows
            d_rows = right_base_rows if d_side == "R" else left_base_rows
            s_row = (s_rows.get(src) or [y0 + 3])[0]
            d_row = (d_rows.get(dst) or [y0 + 3])[0]
            if s_row == d_row:
                straight_pairs.append((src, dst, None))
                continue
        wiring_pairs.append((src, dst))

    # Assign colours to straight pairs
    for idx, (src, dst, _) in enumerate(straight_pairs):
        color = palette[idx % len(palette)] if config.internalWireColorize else None
        straight_pairs[idx] = (src, dst, color)

    # ------------------------------------------------------------------
    # 2.2 Render straight-through pairs (simple full-width hline)
    # ------------------------------------------------------------------
    for src, dst, color in straight_pairs:
        s_side = port_side(src) or "L"
        s_rows = left_base_rows if s_side == "L" else right_base_rows
        row = (s_rows.get(src) or [y0 + 3])[0]
        canvas.hline_pierce(row, x0, rx + 1, color)

    # If every pair was a straight-through, no manifold needed.
    if not wiring_pairs:
        canvas.mode_merge = False
        content: str = node.func.center(iw)[:iw]
        canvas.text(x0 + 1, y0 + 1, content)
        if node.is_root and 0 in node.input_ports and not node.children:
            p = node.input_ports[0]
            ey, ry2 = node.y + 3, node.y + 4
            canvas.set(x0 - 1, ey, Wire.RA)
            if p.signal:
                canvas.text(2, ey, p.signal[: x0 - 4])
            if p.ret:
                canvas.text(2, ry2, p.ret[: x0 - 4])
        return

    # ------------------------------------------------------------------
    # 2.4 Longitude Channel column assignment (manifold pairs only)
    # ------------------------------------------------------------------
    l_counts: dict[str, int] = {}
    for src, dst in wiring_pairs:
        l_counts[src] = l_counts.get(src, 0) + 1
        l_counts[dst] = l_counts.get(dst, 0) + 1

    port_to_x: dict[str, int] = {}
    v_track_l = 0
    v_track_r = 0

    left_ports = sorted(
        p for p in l_counts
        if port_side(p) == "L" and not any(
            port.signal == p or port.ret == p
            for port in node.output_ports.values()
        )
    )
    right_ports = sorted(
        p for p in l_counts
        if any(port.signal == p or port.ret == p for port in node.output_ports.values())
    )

    for port in left_ports:
        port_to_x[port] = x0 + 2 + 2 * v_track_l
        v_track_l += l_counts[port]

    for port in right_ports:
        port_to_x[port] = rx - 2 - 2 * (v_track_r + l_counts[port] - 1)
        v_track_r += l_counts[port]

    # Inner edges of the longitude zones — bound the latitude zone.
    left_zone_inner_x: int = x0 + 2 + 2 * v_track_l
    right_zone_inner_x: int = rx - 2 * v_track_r

    # ------------------------------------------------------------------
    # 2.5.pre  Anchor row helpers and pre-computation
    #
    # MUST precede trunk allocation so used_rows can be seeded correctly.
    # ------------------------------------------------------------------
    def _wall_row(port: str) -> int:
        side = port_side(port)
        base = left_base_rows if side == "L" else right_base_rows
        return (base.get(port) or [y0 + 3])[0]

    def _port_is_signal(port: str) -> bool:
        for p in node.input_ports.values():
            if p.signal == port:
                return True
        for p in node.output_ports.values():
            if p.signal == port:
                return True
        return False

    interior_min: int = y0 + 3
    interior_max: int = y0 + h - 2
    # Anchors must not enter the E→W ribbon zone at the top.
    anchor_floor: int = y0 + 3 + ew_off

    all_anchor_rows: dict[str, list[int]] = {}
    for port in l_counts:
        density = l_counts[port]
        wall_row = _wall_row(port)
        is_sig = _port_is_signal(port)
        if is_sig:
            rows = [wall_row - 1 - i for i in range(density)]
            if rows and min(rows) < anchor_floor:
                rows = [wall_row + 1 + i for i in range(density)]
        else:
            rows = [wall_row + 1 + i for i in range(density)]
            if rows and max(rows) > interior_max:
                rows = [wall_row - 1 - i for i in range(density)]
        rows = [max(anchor_floor, min(interior_max, r)) for r in rows]
        all_anchor_rows[port] = rows

    # ------------------------------------------------------------------
    # 2.5 Latitude Band base-row assignment (grouped by source signal)
    #
    # E→W (westward) trunks are placed at the TOP of the chip interior,
    # scanning down from y0+3 and skipping only straight-through rows.
    # Anchor rows are intentionally NOT blocked: W3 runs in the latitude
    # zone while W1/W5 anchor segments run in the longitude zones — these
    # X spans are disjoint, so no cell coincidence arises.
    # W→E (eastward) trunks start sequentially from last_anchor_row+1,
    # placing them in the lower interior below the anchor stack.
    # ------------------------------------------------------------------
    h_counts: dict[str, int] = {}
    for src, _ in wiring_pairs:
        h_counts[src] = h_counts.get(src, 0) + 1

    # Split by direction: E→W sources sit on the RIGHT wall (ret ports).
    ew_h_counts: dict[str, int] = {}   # westward → top of interior
    we_h_counts: dict[str, int] = {}   # eastward → below anchor stack
    for src, cnt in h_counts.items():
        if port_side(src) == "R":
            ew_h_counts[src] = cnt
        else:
            we_h_counts[src] = cnt

    thread_to_y: dict[str, int] = {}
    used_rows: set[int] = set()

    # Seed with straight-through rows (full-width — must be avoided).
    for s_st, d_st, _ in straight_pairs:
        s_side_st = port_side(s_st) or "L"
        s_rows_st = left_base_rows if s_side_st == "L" else right_base_rows
        st_row = (s_rows_st.get(s_st) or [y0 + 3])[0]
        used_rows.add(st_row)

    # Top zone: E→W (westward) — scan from y0+3, skip straight-through only.
    ew_next = y0 + 3
    for src in sorted(ew_h_counts.keys()):
        lane_count = ew_h_counts[src]
        while any(r in used_rows for r in range(ew_next, ew_next + lane_count)):
            ew_next += 1
        thread_to_y[src] = ew_next
        used_rows.update(range(ew_next, ew_next + lane_count))
        ew_next += lane_count

    # Bottom zone: W→E (eastward) — sequential from last_anchor_row + 1.
    last_anchor_row = (
        max(max(rows) for rows in all_anchor_rows.values())
        if all_anchor_rows else y0 + 2
    )
    we_next_row: int = last_anchor_row + 1
    for src in sorted(we_h_counts.keys()):
        lane_count = we_h_counts[src]
        thread_to_y[src] = we_next_row
        used_rows.update(range(we_next_row, we_next_row + lane_count))
        we_next_row += lane_count

    # ------------------------------------------------------------------
    # 2.6.5 Neutral Longitude Bus (Wall-to-Anchor connector, uncolored)
    # ------------------------------------------------------------------
    for port, rows in all_anchor_rows.items():
        side = port_side(port)
        wall_row = _wall_row(port)
        bus_x = x0 + 1 if side == "L" else rx - 1
        if _port_is_signal(port):
            canvas.vline(bus_x, min(rows), wall_row + 1, None)
        else:
            canvas.vline(bus_x, wall_row, max(rows) + 1, None)

    # ------------------------------------------------------------------
    # 2.7 Initialise router
    # ------------------------------------------------------------------
    router = VLSIRouter(wiring_pairs)

    # ------------------------------------------------------------------
    # 2.8 Synthesis and Rendering (7-segment path per thread)
    # ------------------------------------------------------------------
    src_color_map: dict[str, str | None] = {}
    if config.internalWireColorize:
        _src_slot: int = len(straight_pairs)
        for src, _ in wiring_pairs:
            if src not in src_color_map:
                src_color_map[src] = palette[_src_slot % len(palette)]
                _src_slot += 1

    src_counters: dict[str, int] = {}
    dst_counters: dict[str, int] = {}

    for src, dst in wiring_pairs:
        color = src_color_map.get(src)
        thread_id = f"{src}:{dst}"

        src_side = port_side(src) or "L"
        dst_side = port_side(dst, prefer="R" if src_side == "L" else "L") or (
            "R" if src_side == "L" else "L"
        )

        src_idx = src_counters.get(src, 0)
        src_counters[src] = src_idx + 1
        src_y = all_anchor_rows[src][src_idx]

        dst_idx = dst_counters.get(dst, 0)
        dst_counters[dst] = dst_idx + 1
        dst_y = all_anchor_rows[dst][dst_idx]

        t_src = Terminal(
            src,
            Location.WESTSIDE if src_side == "L" else Location.EASTSIDE,
            x=x0 if src_side == "L" else rx,
            y=src_y,
        )
        t_dst = Terminal(
            dst,
            Location.WESTSIDE if dst_side == "L" else Location.EASTSIDE,
            x=x0 if dst_side == "L" else rx,
            y=dst_y,
        )

        track = router.route_lay(thread_id, t_src, t_dst)
        points = router.canvas_coords_resolve(track, port_to_x, thread_to_y)

        trunk_y: int = points[2][1]
        v_x_src_pt: int = points[2][0]
        v_x_dst_pt: int = points[3][0]

        # W1: port anchor → longitude column (H, colored)
        canvas.hline_pierce(
            points[0][1],
            min(points[0][0], points[1][0]),
            max(points[0][0], points[1][0]) + 1,
            color,
        )
        # W2: Dogleg Alpha (V, colored) — skip if zero-height
        if points[1][1] != points[2][1]:
            canvas.vline(
                points[1][0],
                min(points[1][1], points[2][1]),
                max(points[1][1], points[2][1]) + 1,
                color=color,
                flow="down" if points[1][1] < points[2][1] else "up",
            )
        # W2_ext: horizontal at trunk_y within source longitude zone
        if src_side == "L" and v_x_src_pt < left_zone_inner_x:
            canvas.hline_pierce(trunk_y, v_x_src_pt, left_zone_inner_x, color)
        elif src_side == "R" and v_x_src_pt >= right_zone_inner_x:
            canvas.hline_pierce(trunk_y, right_zone_inner_x, v_x_src_pt + 1, color)
        # W3: trunk — latitude zone only
        if left_zone_inner_x < right_zone_inner_x:
            canvas.hline_pierce(trunk_y, left_zone_inner_x, right_zone_inner_x, color)
        # W4_ext: horizontal at trunk_y within dest longitude zone
        if dst_side == "R" and v_x_dst_pt >= right_zone_inner_x:
            canvas.hline_pierce(trunk_y, right_zone_inner_x, v_x_dst_pt + 1, color)
        elif dst_side == "L" and v_x_dst_pt < left_zone_inner_x:
            canvas.hline_pierce(trunk_y, v_x_dst_pt, left_zone_inner_x, color)
        # W4: Dogleg Omega (V, colored) — skip if zero-height
        if points[3][1] != points[4][1]:
            canvas.vline(
                points[3][0],
                min(points[3][1], points[4][1]),
                max(points[3][1], points[4][1]) + 1,
                color=color,
                flow="down" if points[3][1] < points[4][1] else "up",
            )
        # W5: longitude column → dest anchor (H, colored)
        canvas.hline_pierce(
            points[4][1],
            min(points[4][0], points[5][0]),
            max(points[4][0], points[5][0]) + 1,
            color,
        )

    # Deactivate algebraic merging
    canvas.mode_merge = False

    # ------------------------------------------------------------------
    # 2.9 Internal Anchor Label Overlay (Sovereign — written last)
    #
    # Labels flush against chip wall: x0+1 (left), rx-len(label) (right).
    # Interior-facing edge carries a directionality arrow:
    #   Signal ports (sX left, outX right) → W→E flow → ►
    #   Return ports (rX left, retX right) → E→W flow → ◄
    # Arrow appended to left-wall labels, prepended to right-wall labels.
    # ------------------------------------------------------------------
    for port, rows in all_anchor_rows.items():
        side = port_side(port)
        is_sig = _port_is_signal(port)
        arrow = "►" if is_sig else "◄"
        color = src_color_map.get(port)
        if side == "L":
            label = f"{port}{arrow}"
            label_x = x0 + 1
        else:
            label = f"{arrow}{port}"
            label_x = rx - len(label)
        for row in rows:
            canvas.text(label_x, row, label, color=color)

    # ------------------------------------------------------------------
    # 2.10 Post-Audit: Anchor Materialization Count Check
    # ------------------------------------------------------------------
    for port, expected_count in l_counts.items():
        wall_row_audit = _wall_row(port)
        actual_rows = all_anchor_rows.get(port, [])
        assert len(actual_rows) == expected_count, (
            f"PORT {port}: expected {expected_count} internal anchors, "
            f"got {len(actual_rows)}"
        )
        for r in actual_rows:
            assert r != wall_row_audit, (
                f"PORT {port}: anchor row {r} coincides with wall port row {wall_row_audit}"
            )
        assert len(set(actual_rows)) == len(actual_rows), (
            f"PORT {port}: duplicate anchor rows: {actual_rows}"
        )

    # 5. Labels (Sovereign Overlay)
    content = node.func.center(iw)[:iw]
    canvas.text(x0 + 1, y0 + 1, content)
    if node.is_root and 0 in node.input_ports and not node.children:
        p = node.input_ports[0]
        ey, ry2 = node.y + 3, node.y + 4
        canvas.set(x0 - 1, ey, Wire.RA)
        if p.signal:
            canvas.text(2, ey, p.signal[: x0 - 4])
        if p.ret:
            canvas.text(2, ry2, p.ret[: x0 - 4])
