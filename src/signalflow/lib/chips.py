"""Chip rendering: function boxes, centered labels, in-band ► / ◄ markers."""
from __future__ import annotations

# Standard library
from typing import TYPE_CHECKING, Final

# Local
from signalflow.config import Wire, config
from signalflow.engine.router.models import Location, Terminal
from signalflow.engine.router.router import VLSIRouter
from signalflow.lib.tree import ewTopOffset_get as _ewTopOffset_get
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

    canvas.modeMerge = True

    palette: Final[list[str]] = [
        "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
        "\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m",
    ]

    spacing: int = config.portVerticalSpacing

    # ------------------------------------------------------------------
    # Helper: which wall does a port name live on?
    # ------------------------------------------------------------------
    def portSide_get(name: str, prefer: str | None = None) -> str | None:
        """RPN: portSide_get - Return 'L' (west) or 'R' (east) for a port name.

        prefer='R' checks output_ports first — used so same-name pass-through
        signals (e.g. 's1:s1') resolve src→'L' and dst→'R'.
        """
        checks: list[str] = ["L", "R"] if prefer != "R" else ["R", "L"]
        side: str
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
    leftBaseRows: dict[str, list[int]] = {}
    parentId: int
    for parentId, port in node.input_ports.items():
        name: str | None
        for name in (port.signal, port.ret):
            if name:
                leftBaseRows.setdefault(name, [])
                row: int = (
                    node.entryRows[parentId]
                    if port.signal == name
                    else node.returnRows[parentId]
                )
                if row not in leftBaseRows[name]:
                    leftBaseRows[name].append(row)

    # ewOff: rows reserved at top of chip interior for E→W ribbon zone.
    # Right-wall ports are shifted down by this amount so E→W trunks have
    # a clean unobstructed band above the wall port rows.
    ewOff: int = _ewTopOffset_get(node)

    rightBaseRows: dict[str, list[int]] = {}
    i: int
    for i, port in enumerate(node.output_ports.values()):
        name: str | None
        offset: int
        for name, offset in ((port.signal, 0), (port.ret, 1)):
            if name:
                rightBaseRows.setdefault(name, [])
                row: int = y0 + 3 + ewOff + spacing * i + offset
                if row not in rightBaseRows[name]:
                    rightBaseRows[name].append(row)

    # ------------------------------------------------------------------
    # 2.1 Classify wiring pairs: straight-through vs VLSI manifold
    #
    # Straight-through: cross-wall, single-source, single-destination,
    # same wall row — rendered as a full-width hline; no internal anchors.
    # Criterion uses per-role counts (srcCounts / dstCounts) to avoid
    # double-counting same-name pass-through signals (s1:s1).
    # ------------------------------------------------------------------
    allPairsRaw: list[tuple[str, str]] = []
    w: str
    for w in sorted(node.internal_wiring):
        if ":" not in w:
            continue
        src: str
        dst: str
        src, dst = w.split(":")
        allPairsRaw.append((src, dst))

    srcCounts: dict[str, int] = {}
    dstCounts: dict[str, int] = {}
    src: str
    dst: str
    for src, dst in allPairsRaw:
        srcCounts[src] = srcCounts.get(src, 0) + 1
        dstCounts[dst] = dstCounts.get(dst, 0) + 1

    straightPairs: list[tuple[str, str, str | None]] = []
    wiringPairs: list[tuple[str, str]] = []

    for src, dst in allPairsRaw:
        sSide: str = portSide_get(src) or "L"
        dSide: str = portSide_get(dst, prefer="R" if sSide == "L" else "L") or (
            "R" if sSide == "L" else "L"
        )
        if (
            sSide != dSide
            and srcCounts.get(src, 0) == 1
            and dstCounts.get(dst, 0) == 1
        ):
            sRows: dict[str, list[int]] = (
                leftBaseRows if sSide == "L" else rightBaseRows
            )
            dRows: dict[str, list[int]] = (
                rightBaseRows if dSide == "R" else leftBaseRows
            )
            sRow: int = (sRows.get(src) or [y0 + 3])[0]
            dRow: int = (dRows.get(dst) or [y0 + 3])[0]
            if sRow == dRow:
                straightPairs.append((src, dst, None))
                continue
        wiringPairs.append((src, dst))

    # Assign colours to straight pairs
    idx: int
    for idx, (src, dst, _) in enumerate(straightPairs):
        color: str | None = (
            palette[idx % len(palette)] if config.internalWireColorize else None
        )
        straightPairs[idx] = (src, dst, color)

    # ------------------------------------------------------------------
    # 2.2 Render straight-through pairs (simple full-width hline)
    # ------------------------------------------------------------------
    for src, _dst, color in straightPairs:
        sSide: str = portSide_get(src) or "L"
        sRows: dict[str, list[int]] = (
            leftBaseRows if sSide == "L" else rightBaseRows
        )
        row: int = (sRows.get(src) or [y0 + 3])[0]
        canvas.hline_pierce(row, x0, rx + 1, color)

    # If every pair was a straight-through, no manifold needed.
    if not wiringPairs:
        canvas.modeMerge = False
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

    # ------------------------------------------------------------------
    # 2.4 Longitude Channel column assignment (manifold pairs only)
    # ------------------------------------------------------------------
    lCounts: dict[str, int] = {}
    for src, dst in wiringPairs:
        lCounts[src] = lCounts.get(src, 0) + 1
        lCounts[dst] = lCounts.get(dst, 0) + 1

    portToX: dict[str, int] = {}
    vTrackL: int = 0
    vTrackR: int = 0

    leftPorts: list[str] = sorted(
        p for p in lCounts
        if portSide_get(p) == "L" and not any(
            port.signal == p or port.ret == p
            for port in node.output_ports.values()
        )
    )
    rightPorts: list[str] = sorted(
        p for p in lCounts
        if any(port.signal == p or port.ret == p for port in node.output_ports.values())
    )

    # Longitude zones must start BEYOND the widest anchor label on each wall.
    # Left:  glyph(x0+1) + dash(x0+2) + "{port}►/◄"(x0+3..) + gap → x0+4+LL
    # Right: gap + "►/◄{port}"(..rx-3) + dash(rx-2) + glyph(rx-1) → rx-4-RL
    maxLeftLabel: int = max((len(p) + 1 for p in leftPorts), default=0)
    maxRightLabel: int = max((len(p) + 1 for p in rightPorts), default=0)
    leftLongStart: int = x0 + 4 + maxLeftLabel
    rightLongStart: int = rx - 4 - maxRightLabel

    for port in leftPorts:
        portToX[port] = leftLongStart + 2 * vTrackL
        vTrackL += lCounts[port]

    for port in rightPorts:
        portToX[port] = rightLongStart - 2 * (vTrackR + lCounts[port] - 1)
        vTrackR += lCounts[port]

    # Inner edges of the longitude zones — bound the latitude zone.
    leftZoneInnerX: int = leftLongStart + 2 * vTrackL
    rightZoneInnerX: int = rightLongStart + 2 - 2 * vTrackR

    # ------------------------------------------------------------------
    # 2.5.pre  Anchor row helpers and pre-computation
    #
    # MUST precede trunk allocation so usedRows can be seeded correctly.
    # ------------------------------------------------------------------
    def wallRow_get(port: str) -> int:
        """RPN: wallRow_get - Return the external wall row for a port."""
        side: str | None = portSide_get(port)
        base: dict[str, list[int]] = leftBaseRows if side == "L" else rightBaseRows
        return (base.get(port) or [y0 + 3])[0]

    def portIsSignal_check(port: str) -> bool:
        """RPN: portIsSignal_check - True if port is a forward signal (not return)."""
        if any(p.signal == port for p in node.input_ports.values()):
            return True
        return any(p.signal == port for p in node.output_ports.values())

    interiorMax: int = y0 + h - 2
    # Anchors must not enter the E→W ribbon zone at the top.
    anchorFloor: int = y0 + 3 + ewOff

    allAnchorRows: dict[str, list[int]] = {}
    port: str
    for port in lCounts:
        density: int = lCounts[port]
        wallRow: int = wallRow_get(port)
        isSig: bool = portIsSignal_check(port)
        rows: list[int]
        if isSig:
            rows = [wallRow - 1 - i for i in range(density)]
            if rows and min(rows) < anchorFloor:
                rows = [wallRow + 1 + i for i in range(density)]
        else:
            rows = [wallRow + 1 + i for i in range(density)]
            if rows and max(rows) > interiorMax:
                rows = [wallRow - 1 - i for i in range(density)]
        rows = [max(anchorFloor, min(interiorMax, r)) for r in rows]
        allAnchorRows[port] = rows

    # ------------------------------------------------------------------
    # 2.5 Latitude Band base-row assignment (grouped by source signal)
    #
    # E→W (westward) trunks are placed at the TOP of the chip interior,
    # scanning down from y0+3 and skipping only straight-through rows.
    # Anchor rows are intentionally NOT blocked: W3 runs in the latitude
    # zone while W1/W5 anchor segments run in the longitude zones — these
    # X spans are disjoint, so no cell coincidence arises.
    # W→E (eastward) trunks start sequentially from lastAnchorRow+1,
    # placing them in the lower interior below the anchor stack.
    # ------------------------------------------------------------------
    hCounts: dict[str, int] = {}
    src: str
    for src, _dst in wiringPairs:
        hCounts[src] = hCounts.get(src, 0) + 1

    # Split by direction: E→W sources sit on the RIGHT wall (ret ports).
    ewHCounts: dict[str, int] = {}   # westward → top of interior
    weHCounts: dict[str, int] = {}   # eastward → below anchor stack
    cnt: int
    for src, cnt in hCounts.items():
        if portSide_get(src) == "R":
            ewHCounts[src] = cnt
        else:
            weHCounts[src] = cnt

    threadToY: dict[str, int] = {}
    usedRows: set[int] = set()

    # Seed with straight-through rows (full-width — must be avoided).
    sSt: str
    _dSt: str
    _color: str | None
    for sSt, _dSt, _color in straightPairs:
        sSideSt: str = portSide_get(sSt) or "L"
        sRowsSt: dict[str, list[int]] = (
            leftBaseRows if sSideSt == "L" else rightBaseRows
        )
        stRow: int = (sRowsSt.get(sSt) or [y0 + 3])[0]
        usedRows.add(stRow)

    # Top zone: E→W (westward) — scan from y0+3, skip straight-through only.
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
        max(max(rows) for rows in allAnchorRows.values())
        if allAnchorRows else y0 + 2
    )
    weNextRow: int = lastAnchorRow + 1
    for src in sorted(weHCounts.keys()):
        laneCount: int = weHCounts[src]
        threadToY[src] = weNextRow
        usedRows.update(range(weNextRow, weNextRow + laneCount))
        weNextRow += laneCount

    # ------------------------------------------------------------------
    # 2.6.5 Structured Junction Bus (Wall-to-Anchor connector, uncolored)
    #
    # Wall row gets a corner glyph turning the incoming external wire into
    # the vertical bus.  The span between anchor rows is drawn neutral (│).
    # Section 2.9 overwrites each anchor row with the colored junction arm.
    # ------------------------------------------------------------------
    rows: list[int]
    for port, rows in allAnchorRows.items():
        side: str | None = portSide_get(port)
        wallRow: int = wallRow_get(port)
        busX: int = x0 + 1 if side == "L" else rx - 1
        if portIsSignal_check(port):
            canvas.vline(busX, min(rows), wallRow, None)
            canvas.set(busX, wallRow, "┘" if side == "L" else "└")
        else:
            canvas.vline(busX, wallRow + 1, max(rows) + 1, None)
            canvas.set(busX, wallRow, "┐" if side == "L" else "┌")

    # ------------------------------------------------------------------
    # 2.7 Initialise router
    # ------------------------------------------------------------------
    router: VLSIRouter = VLSIRouter(wiringPairs)

    # ------------------------------------------------------------------
    # 2.8 Synthesis and Rendering (7-segment path per thread)
    # ------------------------------------------------------------------
    srcColorMap: dict[str, str | None] = {}
    if config.internalWireColorize:
        srcSlot: int = len(straightPairs)
        for src, _dst in wiringPairs:
            if src not in srcColorMap:
                srcColorMap[src] = palette[srcSlot % len(palette)]
                srcSlot += 1

    srcCounters: dict[str, int] = {}
    dstCounters: dict[str, int] = {}

    for src, dst in wiringPairs:
        color = srcColorMap.get(src)
        threadId: str = f"{src}:{dst}"

        srcSide: str = portSide_get(src) or "L"
        dstSide: str = portSide_get(dst, prefer="R" if srcSide == "L" else "L") or (
            "R" if srcSide == "L" else "L"
        )

        srcIdx: int = srcCounters.get(src, 0)
        srcCounters[src] = srcIdx + 1
        srcY: int = allAnchorRows[src][srcIdx]

        dstIdx: int = dstCounters.get(dst, 0)
        dstCounters[dst] = dstIdx + 1
        dstY: int = allAnchorRows[dst][dstIdx]

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
            track, portToX, threadToY
        )

        trunkY: int = points[2][1]
        vXSrcPt: int = points[2][0]
        vXDstPt: int = points[3][0]

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
        # W2_ext: horizontal at trunkY within source longitude zone
        if srcSide == "L" and vXSrcPt < leftZoneInnerX:
            canvas.hline_pierce(trunkY, vXSrcPt, leftZoneInnerX, color)
        elif srcSide == "R" and vXSrcPt >= rightZoneInnerX:
            canvas.hline_pierce(trunkY, rightZoneInnerX, vXSrcPt + 1, color)
        # W3: trunk — latitude zone only
        if leftZoneInnerX < rightZoneInnerX:
            canvas.hline_pierce(trunkY, leftZoneInnerX, rightZoneInnerX, color)
        # W4_ext: horizontal at trunkY within dest longitude zone
        if dstSide == "R" and vXDstPt >= rightZoneInnerX:
            canvas.hline_pierce(trunkY, rightZoneInnerX, vXDstPt + 1, color)
        elif dstSide == "L" and vXDstPt < leftZoneInnerX:
            canvas.hline_pierce(trunkY, vXDstPt, leftZoneInnerX, color)
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
    canvas.modeMerge = False

    # ------------------------------------------------------------------
    # 2.9 Internal Anchor Label Overlay (Sovereign — written last)
    #
    # Each anchor row gets three sovereign writes (overwrite mode):
    #   busX        → junction glyph (┌/├/└ left; ┐/┤/┘ right), colored
    #   busX ± 1    → ─ dash bridging glyph to label, colored
    #   x0+3 / rx-2-len(label) → label text with directionality arrow, colored
    #
    # Junction glyph selection (rows ordered closest→farthest from wall row):
    #   Signal (upward stack):  rows[-1]=farthest → ┌(L)/┐(R); others → ├/┤
    #   Return (downward stack): rows[-1]=farthest → └(L)/┘(R); others → ├/┤
    # ------------------------------------------------------------------
    for port, rows in allAnchorRows.items():
        side: str | None = portSide_get(port)
        isSig: bool = portIsSignal_check(port)
        arrow: str = "►" if isSig else "◄"
        color: str | None = srcColorMap.get(port)
        busX: int = x0 + 1 if side == "L" else rx - 1
        label: str
        junctionGlyph: str
        isEnd: bool
        i: int
        row: int
        if side == "L":
            label = f"{port}{arrow}"
            for i, row in enumerate(rows):
                isEnd = i == len(rows) - 1
                junctionGlyph = ("┌" if isSig else "└") if isEnd else "├"
                canvas.set(busX, row, junctionGlyph, color)
                canvas.set(busX + 1, row, "─", color)
                canvas.text(x0 + 3, row, label, color=color)
        else:
            label = f"{arrow}{port}"
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
    for port, expectedCount in lCounts.items():
        wallRowAudit: int = wallRow_get(port)
        actualRows: list[int] = allAnchorRows.get(port, [])
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

    # 5. Labels (Sovereign Overlay)
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
