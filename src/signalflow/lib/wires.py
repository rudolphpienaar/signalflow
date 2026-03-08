"""Wire rendering: forward calls, returns, DFS thread driver."""

from signalflow.config import Wire
from signalflow.models import Canvas, Node


def wireForward_render(
    canvas: Canvas, parent: Node, child: Node, color: str | None = None
) -> None:
    """Draw the forward call wire from parent chip to child chip."""
    from signalflow.config import config

    # Find the specific row for this connection
    pSpacing: int = config.portVerticalSpacing if parent.internal_wiring else 3
    pIdx: int = list(parent.output_ports.keys()).index(id(child))
    exitY: int = parent.y + 3 + parent.geometry.ewOff + pSpacing * pIdx
    entryY: int = child.entryRows[id(parent)]

    entryX: int = child.x
    parentRx: int = parent.x + parent.ow - 1

    # Arrows are always flush against the chip ports
    arrowXExit: int = parentRx + 1
    arrowXEntry: int = entryX - 1

    channelX: int
    if exitY == entryY:
        channelX = entryX
        canvas.hline_pierce(exitY, parentRx + 1, entryX, color)
        canvas.set(arrowXExit, exitY, Wire.RA, color)
        canvas.set(arrowXEntry, entryY, Wire.RA, color)
    else:
        # Unified Staggering Rule: Use max of port indices on both walls.
        pIdx: int = list(parent.output_ports.keys()).index(id(child))
        cIdx: int = list(child.input_ports.keys()).index(id(parent))
        staggerIdx: int = max(pIdx, cIdx)

        # Vertical Affinity: The track closest to the wall (Rightmost)
        # must be the one encountered FIRST by the vertical flow.
        # i.e., Top-most port for Down-flow, Bottom-most port for Up-flow.
        nStagger: int = max(len(parent.output_ports), len(child.input_ports))
        if exitY > entryY:  # Ascending
            staggerIdx = (nStagger - 1) - staggerIdx

        # Max space needed for any child-side label in this group
        maxChildLbl: int = 0
        c: Node
        for c in parent.children:
            if c.input_ports:
                p: Node.Port | None = c.input_ports.get(id(parent))
                if p:
                    lblF: int = len(p.signal) if p.signal else 0
                    lblR: int = len(p.ret) if p.ret else 0
                    maxChildLbl = max(maxChildLbl, lblF, lblR)

        staggerStart: int = maxChildLbl + 3
        channelX = entryX - staggerStart - 2 * staggerIdx

        canvas.hline_pierce(exitY, parentRx + 1, channelX + 1, color)
        canvas.set(arrowXExit, exitY, Wire.RA, color)
        if exitY < entryY:
            canvas.set(channelX, exitY, Wire.RD, color)
            canvas.vline(channelX, exitY + 1, entryY, color=color, pass_through=True)
        else:
            canvas.set(channelX, exitY, Wire.RU, color)
            canvas.vline(channelX, entryY + 1, exitY, color=color, pass_through=True)
        canvas.hline_pierce(entryY, channelX, entryX, color)
        if exitY < entryY:
            canvas.set(channelX, entryY, Wire.DR, color)
        else:
            canvas.set(channelX, entryY, Wire.UR, color)
        canvas.set(arrowXEntry, entryY, Wire.RA, color)

    # Labels
    pPort: Node.Port | None = parent.output_ports.get(id(child))
    cPort: Node.Port | None = child.input_ports.get(id(parent))
    pSignal: str | None = pPort.signal if pPort else None
    cSignal: str | None = cPort.signal if cPort else None

    if pSignal:
        labelX: int = arrowXExit + 1
        limitX: int = channelX if exitY != entryY else arrowXEntry
        maxLabel: int
        if exitY == entryY and cSignal:
            limitX = min(limitX, arrowXEntry - len(cSignal) - 1)
        maxLabel = max(0, limitX - labelX)
        canvas.text(labelX, exitY, pSignal[:maxLabel], color)

    if cSignal:
        labelLen: int = len(cSignal)
        labelX = arrowXEntry - labelLen
        limitX = channelX + 1 if exitY != entryY else arrowXExit + 1
        if exitY == entryY and pSignal:
            # We need pSignal's rendered length here, but pSignal is the full string.
            # maxLabel was used for pSignal rendering.
            limitX = max(limitX, arrowXExit + 1 + len(pSignal) + 1)
        labelX = max(limitX, labelX)
        maxLabel = arrowXEntry - labelX
        canvas.text(labelX, entryY, cSignal[:maxLabel], color)


def wireReturn_render(
    canvas: Canvas, parent: Node, child: Node, color: str | None = None
) -> None:
    """Draw the return wire from child chip back to parent chip."""
    from signalflow.config import config

    # Find specific rows
    pSpacing: int = config.portVerticalSpacing if parent.internal_wiring else 3
    pIdx: int = list(parent.output_ports.keys()).index(id(child))
    childRetY: int = child.returnRows[id(parent)]
    parentRetY: int = parent.y + 4 + parent.geometry.ewOff + pSpacing * pIdx

    childLx: int = child.x
    parentRx: int = parent.x + parent.ow - 1

    arrowXExit: int = childLx - 1
    arrowXEntry: int = parentRx + 1

    channelX: int
    if childRetY == parentRetY:
        channelX = childLx
        canvas.hline_pierce(childRetY, parentRx + 1, childLx, color)
        canvas.set(arrowXExit, childRetY, Wire.LA, color)
    else:
        # Unified Staggering Rule
        pIdx: int = list(parent.output_ports.keys()).index(id(child))
        cIdx: int = list(child.input_ports.keys()).index(id(parent))
        staggerIdx: int = max(pIdx, cIdx)

        # Vertical Affinity
        nStagger: int = max(len(parent.output_ports), len(child.input_ports))
        if childRetY < parentRetY:  # Ascending (Target parent is ABOVE)
            staggerIdx = (nStagger - 1) - staggerIdx

        maxChildLbl: int = 0
        c: Node
        for c in parent.children:
            if c.input_ports:
                p: Node.Port | None = c.input_ports.get(id(parent))
                if p:
                    lblF: int = len(p.signal) if p.signal else 0
                    lblR: int = len(p.ret) if p.ret else 0
                    maxChildLbl = max(maxChildLbl, lblF, lblR)

        staggerStart: int = maxChildLbl + 3

        # Helix Flip
        if childRetY > parentRetY:
            channelX = childLx - staggerStart - 1 - 2 * staggerIdx
        else:
            channelX = childLx - staggerStart + 1 - 2 * staggerIdx

        canvas.hline_pierce(childRetY, channelX, childLx, color)
        canvas.set(arrowXExit, childRetY, Wire.LA, color)
        if childRetY > parentRetY:
            canvas.set(channelX, childRetY, Wire.LU, color)
            canvas.vline(channelX, parentRetY + 1, childRetY, color=color, pass_through=True)
        else:
            canvas.set(channelX, childRetY, Wire.LD, color)
            canvas.vline(channelX, childRetY + 1, parentRetY, color=color, pass_through=True)
        canvas.hline_pierce(parentRetY, parentRx + 2, channelX + 1, color)
        if childRetY > parentRetY:
            canvas.set(channelX, parentRetY, Wire.UL, color)
        else:
            canvas.set(channelX, parentRetY, Wire.DL, color)

    canvas.set(arrowXEntry, parentRetY, Wire.LA, color)

    pPort: Node.Port | None = parent.output_ports.get(id(child))
    cPort: Node.Port | None = child.input_ports.get(id(parent))
    pRet: str | None = pPort.ret if pPort else None
    cRet: str | None = cPort.ret if cPort else None

    maxLabelP: int = 0
    if pRet:
        labelX: int = arrowXEntry + 1
        limitX: int = channelX if childRetY != parentRetY else arrowXExit
        if childRetY == parentRetY and cRet:
            limitX = min(limitX, arrowXExit - len(cRet) - 1)
        maxLabelP = max(0, limitX - labelX)
        canvas.text(labelX, parentRetY, pRet[:maxLabelP], color)

    if cRet:
        labelLen: int = len(cRet)
        labelX = arrowXExit - labelLen
        limitX = channelX + 1 if childRetY != parentRetY else arrowXEntry + 1
        if childRetY == parentRetY and pRet:
            limitX = max(limitX, arrowXEntry + 1 + len(pRet) + 1)
        labelX = max(limitX, labelX)
        maxLabelC: int = arrowXExit - labelX
        canvas.text(labelX, childRetY, cRet[:maxLabelC], color)



def thread_render(canvas: Canvas, root: Node) -> None:
    """Drive the wire through the full DFS call tree."""

    def _wire(node: Node) -> None:
        child: Node
        for child in node.children:
            wireForward_render(canvas, node, child)
            _wire(child)
            wireReturn_render(canvas, node, child)

    _wire(root)
