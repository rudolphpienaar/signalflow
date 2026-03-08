"""Chip rendering: function boxes, centered labels, in-band ► / ◄ markers."""
from __future__ import annotations

# Standard library
from typing import TYPE_CHECKING, Final

# Local
from signalflow.config import Wire, config
from signalflow.engine.router.models import Location, Terminal
from signalflow.engine.router.router import VLSIRouter
from signalflow.models import Canvas, Node

if TYPE_CHECKING:
    from signalflow.engine.router.models import Track

def chip_render(canvas: Canvas, node: Node) -> None:
    """Draw the function chip for *node* onto *canvas*.

    Args:
        canvas: The canvas to draw on.
        node: The node representing the function chip.
    """

    x0: int = node.x
    y0: int = node.y
    h: int = node.chipH
    ow: int = node.ow
    iw: int = ow - 2
    rx: int = x0 + ow - 1

    # 1. Framework (Borders and Separator) — modeMerge always False here
    canvas.set(x0, y0, "┌")
    canvas.hline_force(y0, x0 + 1, rx, "─")
    canvas.set(rx, y0, "┐")
    by: int = y0 + h - 1
    canvas.set(x0, by, "└")
    canvas.hline_force(by, x0 + 1, rx, "─")
    canvas.set(rx, by, "┘")
    row: int
    for row in range(1, h - 1):
        ry: int = y0 + row
        canvas.set(x0, ry, "│")
        canvas.set(rx, ry, "│")
    canvas.set(x0, y0 + 2, "├")
    canvas.hline_force(y0 + 2, x0 + 1, rx, "─")
    canvas.set(rx, y0 + 2, "┤")

    # 2. Internal Wiring Manifold — guard BEFORE modeMerge
    if not node.internal_wiring:
        if not node.children:
            parent_id: int
            for parent_id in node.input_ports:
                ey: int = node.entryRows[parent_id]
                ry: int = node.returnRows[parent_id]
                canvas.hline_force(ey, x0 + 1, x0 + config.uTurnWidth, "─")
                canvas.set(x0 + config.uTurnWidth, ey, "┐")
                canvas.hline_force(ry, x0 + 1, x0 + config.uTurnWidth, "─")
                canvas.set(x0 + config.uTurnWidth, ry, "┘")
        content: str = node.func.center(iw)[:iw]
        canvas.text(x0 + 1, y0 + 1, content)
        if node.isRoot and 0 in node.input_ports and not node.children:
            p = node.input_ports[0]
            ey, ry2 = node.y + 3, node.y + 4
            canvas.set(x0 - 1, ey, Wire.RA)
            if p.signal:
                canvas.text(2, ey, p.signal[: x0 - 4])
            if p.ret:
                canvas.text(2, ry2, p.ret[: x0 - 4])
        return

    # Geometry is fully resolved by layout_compute — read from node.geometry.
    geo = node.geometry
    assert geo is not None and geo.resolved, (
        f"chip_render({node.func}): geometry not resolved — "
        "layout_compute must run before chip_render"
    )

    palette: Final[list[str]] = [
        "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
        "\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m",
    ]

    # Assign colours to straight-through pairs (rendering detail — stays here).
    straightPairsColored: list[tuple[str, str, str | None]] = []
    idx: int
    src: str
    dst: str
    for idx, (src, dst) in enumerate(geo.straightPairs):
        color: str | None = (
            palette[idx % len(palette)] if config.internalWireColorize else None
        )
        straightPairsColored.append((src, dst, color))

    canvas.modeMerge = True
    try:
        # ------------------------------------------------------------------
        # 2.2 Render straight-through pairs (simple full-width hline)
        # ------------------------------------------------------------------
        _dst: str
        _color: str | None
        for src, _dst, _color in straightPairsColored:
            canvas.hline_pierce(geo.wall_row(src), x0, rx + 1, _color)

        if geo.wiringPairs:
            # ------------------------------------------------------------------
            # 2.5 Latitude Band trunk-row allocation (rendering detail)
            #
            # threadToY maps each source signal to its trunk row — computed
            # fresh each render because it depends on usedRows seeding order.
            # ------------------------------------------------------------------
            hCounts: dict[str, int] = {}
            for src, _dst in geo.wiringPairs:
                hCounts[src] = hCounts.get(src, 0) + 1

            ewHCounts: dict[str, int] = {}   # E→W (ret sources on right wall)
            weHCounts: dict[str, int] = {}   # W→E (signal sources on left wall)
            cnt: int
            for src, cnt in hCounts.items():
                if geo.port_side(src) == "R":
                    ewHCounts[src] = cnt
                else:
                    weHCounts[src] = cnt

            threadToY: dict[str, int] = {}
            usedRows: set[int] = set()

            # Seed: straight-through rows and unit-port wall rows are forbidden.
            for src, _dst in geo.straightPairs:
                usedRows.add(geo.wall_row(src))
            port: str
            for port in geo.unitPorts:
                usedRows.add(geo.wall_row(port))

            # Top zone: E→W (westward) — scan from y0+3.
            ewNext: int = y0 + 3
            for src in sorted(ewHCounts.keys()):
                laneCount: int = ewHCounts[src]
                while any(r in usedRows for r in range(ewNext, ewNext + laneCount)):
                    ewNext += 1
                threadToY[src] = ewNext
                usedRows.update(range(ewNext, ewNext + laneCount))
                ewNext += laneCount

            # Bottom zone: W→E (eastward) — sequential from lastAnchorRow + 1.
            lastAnchorRow: int = (
                max(max(rows) for rows in geo.allAnchorRows.values())
                if geo.allAnchorRows else y0 + 2
            )
            weNextRow: int = lastAnchorRow + 1
            for src in sorted(weHCounts.keys()):
                laneCount = weHCounts[src]
                threadToY[src] = weNextRow
                usedRows.update(range(weNextRow, weNextRow + laneCount))
                weNextRow += laneCount

            # ------------------------------------------------------------------
            # 2.6.5 Structured Junction Bus (Wall-to-Anchor connector, uncolored)
            # ------------------------------------------------------------------
            rows: list[int]
            for port, rows in geo.allAnchorRows.items():
                if port in geo.unitPorts:
                    continue
                side: str = geo.port_side(port)
                wallRow: int = geo.wall_row(port)
                busX: int = x0 + 1 if side == "L" else rx - 1
                if geo.is_signal(port):
                    canvas.vline(busX, min(rows), wallRow, None)
                    canvas.set(busX, wallRow, "┘" if side == "L" else "└")
                else:
                    canvas.vline(busX, wallRow + 1, max(rows) + 1, None)
                    canvas.set(busX, wallRow, "┐" if side == "L" else "┌")

            # ------------------------------------------------------------------
            # 2.7 Initialise router
            # ------------------------------------------------------------------
            router: VLSIRouter = VLSIRouter(geo.wiringPairs)

            # ------------------------------------------------------------------
            # 2.8 Synthesis and Rendering (7-segment path per thread)
            # ------------------------------------------------------------------
            srcColorMap: dict[str, str | None] = {}
            if config.internalWireColorize:
                srcSlot: int = len(straightPairsColored)
                for src, _dst in geo.wiringPairs:
                    if src not in srcColorMap:
                        srcColorMap[src] = palette[srcSlot % len(palette)]
                        srcSlot += 1

            srcCounters: dict[str, int] = {}
            dstCounters: dict[str, int] = {}

            for src, dst in geo.wiringPairs:
                color = srcColorMap.get(src)
                threadId: str = f"{src}:{dst}"

                srcSide: str = geo.port_side(src)
                dstSide: str = geo.port_side(dst, prefer="R" if srcSide == "L" else "L")

                srcIdx: int = srcCounters.get(src, 0)
                srcCounters[src] = srcIdx + 1
                srcY: int = geo.allAnchorRows[src][srcIdx]

                dstIdx: int = dstCounters.get(dst, 0)
                dstCounters[dst] = dstIdx + 1
                dstY: int = geo.allAnchorRows[dst][dstIdx]

                tSrc: Terminal = Terminal(
                    src,
                    Location.WESTSIDE if srcSide == "L" else Location.EASTSIDE,
                    x=x0 + 1 if srcSide == "L" else rx - 1,
                    y=srcY,
                )
                tDst: Terminal = Terminal(
                    dst,
                    Location.WESTSIDE if dstSide == "L" else Location.EASTSIDE,
                    x=x0 + 1 if dstSide == "L" else rx - 1,
                    y=dstY,
                )

                track: Track = router.route_lay(threadId, tSrc, tDst)
                points: list[tuple[int, int]] = router.canvasCoords_resolve(
                    track, geo.portToX, threadToY
                )

                trunkY: int     = points[2][1]
                vXSrcPt: int    = points[2][0]
                vXDstPt: int    = points[3][0]

                # W1: port anchor → longitude column (H, colored)
                canvas.hline_pierce(
                    points[0][1],
                    min(points[0][0], points[1][0]),
                    max(points[0][0], points[1][0]) + 1,
                    color,
                )
                # W2: Dogleg Alpha (V) — skip if zero-height
                if points[1][1] != points[2][1]:
                    canvas.vline(
                        points[1][0],
                        min(points[1][1], points[2][1]),
                        max(points[1][1], points[2][1]) + 1,
                        color=color,
                    )
                # W2_ext
                if srcSide == "L" and vXSrcPt < geo.leftZoneInnerX:
                    canvas.hline_pierce(trunkY, vXSrcPt, geo.leftZoneInnerX, color)
                elif srcSide == "R" and vXSrcPt > geo.rightZoneInnerX:
                    canvas.hline_pierce(trunkY, geo.rightZoneInnerX, vXSrcPt + 1, color)
                # W3: trunk — latitude zone only
                w3End: int = geo.rightZoneInnerX + (
                    1 if srcSide == "R" and vXSrcPt == geo.rightZoneInnerX else 0
                )
                if geo.leftZoneInnerX < w3End:
                    canvas.hline_pierce(trunkY, geo.leftZoneInnerX, w3End, color)
                # W4_ext
                if dstSide == "R" and vXDstPt >= geo.rightZoneInnerX:
                    canvas.hline_pierce(trunkY, geo.rightZoneInnerX, vXDstPt + 1, color)
                elif dstSide == "L" and vXDstPt < geo.leftZoneInnerX:
                    canvas.hline_pierce(trunkY, vXDstPt, geo.leftZoneInnerX, color)
                # W4: Dogleg Omega (V) — skip if zero-height
                if points[3][1] != points[4][1]:
                    canvas.vline(
                        points[3][0],
                        min(points[3][1], points[4][1]),
                        max(points[3][1], points[4][1]) + 1,
                        color=color,
                    )
                # W5: longitude column → dest anchor (H, colored)
                canvas.hline_pierce(
                    points[4][1],
                    min(points[4][0], points[5][0]),
                    max(points[4][0], points[5][0]) + 1,
                    color,
                )

            # ------------------------------------------------------------------
            # 2.9 Internal Anchor Label Overlay (Sovereign — written last)
            # ------------------------------------------------------------------
            for port, rows in geo.allAnchorRows.items():
                if port in geo.unitPorts:
                    continue
                side = geo.port_side(port)
                isSig: bool = geo.is_signal(port)
                arrow: str = "►" if isSig else "◄"
                color = srcColorMap.get(port)
                busX = x0 + 1 if side == "L" else rx - 1
                label: str
                junctionGlyph: str
                isEnd: bool
                i: int
                row: int
                from signalflow.models.chip_geometry import _anchor_display
                display: str = _anchor_display(port)
                if side == "L":
                    label = f"{display}{arrow}"
                    for i, row in enumerate(rows):
                        isEnd = i == len(rows) - 1
                        junctionGlyph = ("┌" if isSig else "└") if isEnd else "├"
                        canvas.set(busX, row, junctionGlyph, color)
                        canvas.set(busX + 1, row, "─", color)
                        canvas.text(x0 + 3, row, label, color=color)
                else:
                    label = f"{arrow}{display}"
                    for i, row in enumerate(rows):
                        isEnd = i == len(rows) - 1
                        junctionGlyph = ("┐" if isSig else "┘") if isEnd else "┤"
                        canvas.set(busX - 1, row, "─", color)
                        canvas.set(busX, row, junctionGlyph, color)
                        canvas.text(rx - 2 - len(label), row, label, color=color)

            # ------------------------------------------------------------------
            # 2.10 Post-Audit: Anchor Materialization Count Check
            # ------------------------------------------------------------------
            expectedCount: int
            for port, expectedCount in geo.lCounts.items():
                if port in geo.unitPorts:
                    continue
                wallRowAudit: int = geo.wall_row(port)
                actualRows: list[int] = geo.allAnchorRows.get(port, [])
                assert len(actualRows) == expectedCount, (
                    f"PORT {port}: expected {expectedCount} internal anchors, "
                    f"got {len(actualRows)}"
                )
                r: int
                for r in actualRows:
                    assert r != wallRowAudit, (
                        f"PORT {port}: anchor row {r} coincides with"
                        f" wall port row {wallRowAudit}"
                    )
                assert len(set(actualRows)) == len(actualRows), (
                    f"PORT {port}: duplicate anchor rows: {actualRows}"
                )

    finally:
        canvas.modeMerge = False

    # 5. Labels (Sovereign Overlay — always outside modeMerge zone)
    content = node.func.center(iw)[:iw]
    canvas.text(x0 + 1, y0 + 1, content)
    if node.isRoot and 0 in node.input_ports and not node.children:
        p = node.input_ports[0]
        ey, ry2 = node.y + 3, node.y + 4
        canvas.set(x0 - 1, ey, Wire.RA)
        if p.signal:
            canvas.text(2, ey, p.signal[: x0 - 4])
        if p.ret:
            canvas.text(2, ry2, p.ret[: x0 - 4])
