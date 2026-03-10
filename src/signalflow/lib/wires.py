"""Wire rendering: forward calls, returns, DFS thread driver."""

from signalflow.config import Wire
from signalflow.models import Canvas, Node, PortKey
from signalflow.models.node import Port


def _portIndex_get(ports: dict[PortKey, Port], key: PortKey) -> int:
    """Return the stable occurrence index for one bound port key."""
    return list(ports.keys()).index(key)


def _parentSpacing_get(node: Node) -> int:
    """Return the effective right-wall spacing for one parent chip."""
    from signalflow.config import config

    return config.portVerticalSpacing if node.internal_wiring else 3


def _maxChildLabelWidth_get(parent: Node) -> int:
    """Return the maximum input label width among this parent's child edges."""
    maxChildLbl: int = 0
    child: Node
    for child in parent.children:
        key: PortKey
        port: Node.Port
        for key, port in child.input_ports.items():
            if key[0] != id(parent):
                continue
            lblSignal: int = len(port.signal) if port.signal else 0
            lblReturn: int = len(port.ret) if port.ret else 0
            maxChildLbl = max(maxChildLbl, lblSignal, lblReturn)
    return maxChildLbl


def _staggerIndex_get(
    parent: Node,
    child: Node,
    out_key: PortKey,
    in_key: PortKey,
    ascending: bool,
) -> int:
    """Return the stagger index for a parent→child jog."""
    parentIdx: int = _portIndex_get(parent.output_ports, out_key)
    childIdx: int = _portIndex_get(child.input_ports, in_key)
    staggerIdx: int = max(parentIdx, childIdx)
    nStagger: int = max(len(parent.output_ports), len(child.input_ports))
    if ascending:
        staggerIdx = (nStagger - 1) - staggerIdx
    return staggerIdx


def _forwardRows_resolve(
    parent: Node, child: Node, out_key: PortKey, in_key: PortKey
) -> tuple[int, int, int]:
    """Resolve parent exit row, child entry row, and parent output index."""
    pIdx: int = _portIndex_get(parent.output_ports, out_key)
    exitY: int = (
        parent.y
        + 3
        + parent.geometry.ewOff
        + _parentSpacing_get(parent) * pIdx
    )
    entryY: int = child.entryRows[in_key]
    return exitY, entryY, pIdx


def _returnRows_resolve(
    parent: Node, child: Node, out_key: PortKey, in_key: PortKey
) -> tuple[int, int, int]:
    """Resolve child return row, parent return row, and parent output index."""
    pIdx: int = _portIndex_get(parent.output_ports, out_key)
    childRetY: int = child.returnRows[in_key]
    parentRetY: int = (
        parent.y + 4 + parent.geometry.ewOff + _parentSpacing_get(parent) * pIdx
    )
    return childRetY, parentRetY, pIdx


def _forwardStraight_render(
    canvas: Canvas,
    parentRx: int,
    entryX: int,
    rowY: int,
    color: str | None,
) -> int:
    """Render a same-row forward connection and return its label limit X."""
    arrowXExit: int = parentRx + 1
    arrowXEntry: int = entryX - 1
    canvas.hline_pierce(rowY, parentRx + 1, entryX, color)
    canvas.set(arrowXExit, rowY, Wire.RA, color)
    canvas.set(arrowXEntry, rowY, Wire.RA, color)
    return entryX


def _forwardJog_render(
    canvas: Canvas,
    parent: Node,
    child: Node,
    exitY: int,
    entryY: int,
    out_key: PortKey,
    in_key: PortKey,
    color: str | None,
) -> int:
    """Render a staggered forward connection and return the jog column."""
    entryX: int = child.x
    parentRx: int = parent.x + parent.ow - 1
    ascending: bool = exitY > entryY
    staggerIdx: int = _staggerIndex_get(
        parent, child, out_key, in_key, ascending
    )
    channelX: int = entryX - (_maxChildLabelWidth_get(parent) + 3) - 2 * staggerIdx

    canvas.hline_pierce(exitY, parentRx + 1, channelX + 1, color)
    canvas.set(parentRx + 1, exitY, Wire.RA, color)
    if exitY < entryY:
        canvas.set(channelX, exitY, Wire.RD, color)
        canvas.vline(channelX, exitY + 1, entryY, color=color, pass_through=True)
        canvas.set(channelX, entryY, Wire.DR, color)
    else:
        canvas.set(channelX, exitY, Wire.RU, color)
        canvas.vline(channelX, entryY + 1, exitY, color=color, pass_through=True)
        canvas.set(channelX, entryY, Wire.UR, color)
    canvas.hline_pierce(entryY, channelX, entryX, color)
    canvas.set(entryX - 1, entryY, Wire.RA, color)
    return channelX


def _returnStraight_render(
    canvas: Canvas,
    parentRx: int,
    childLx: int,
    rowY: int,
    color: str | None,
) -> int:
    """Render a same-row return connection and return its label limit X."""
    canvas.hline_pierce(rowY, parentRx + 1, childLx, color)
    canvas.set(childLx - 1, rowY, Wire.LA, color)
    return childLx


def _returnChannelX_get(
    parent: Node,
    child: Node,
    parentIdx: int,
    in_key: PortKey,
    childRetY: int,
    parentRetY: int,
) -> int:
    """Return the staggered channel column for a return jog."""
    ascending: bool = childRetY < parentRetY
    staggerIdx: int = _staggerIndex_get(
        parent,
        child,
        list(parent.output_ports.keys())[parentIdx],
        in_key,
        ascending,
    )
    childLx: int = child.x
    staggerStart: int = _maxChildLabelWidth_get(parent) + 3
    if childRetY > parentRetY:
        return childLx - staggerStart - 1 - 2 * staggerIdx
    return childLx - staggerStart + 1 - 2 * staggerIdx


def _returnJog_render(
    canvas: Canvas,
    parent: Node,
    child: Node,
    childRetY: int,
    parentRetY: int,
    out_key: PortKey,
    in_key: PortKey,
    color: str | None,
) -> int:
    """Render a staggered return connection and return the jog column."""
    childLx: int = child.x
    channelX: int = _returnChannelX_get(
        parent,
        child,
        _portIndex_get(parent.output_ports, out_key),
        in_key,
        childRetY,
        parentRetY,
    )
    canvas.hline_pierce(childRetY, channelX, childLx, color)
    canvas.set(childLx - 1, childRetY, Wire.LA, color)
    if childRetY > parentRetY:
        canvas.set(channelX, childRetY, Wire.LU, color)
        canvas.vline(
            channelX, parentRetY + 1, childRetY, color=color, pass_through=True
        )
    else:
        canvas.set(channelX, childRetY, Wire.LD, color)
        canvas.vline(
            channelX, childRetY + 1, parentRetY, color=color, pass_through=True
        )
    canvas.hline_pierce(parentRetY, parent.x + parent.ow + 1, channelX + 1, color)
    if childRetY > parentRetY:
        canvas.set(channelX, parentRetY, Wire.UL, color)
    else:
        canvas.set(channelX, parentRetY, Wire.DL, color)
    return channelX


def _forwardLabels_render(
    canvas: Canvas,
    parent: Node,
    child: Node,
    out_key: PortKey,
    in_key: PortKey,
    exitY: int,
    entryY: int,
    channelX: int,
    color: str | None,
) -> None:
    """Render forward signal labels on both ends of the call wire."""
    parentRx: int = parent.x + parent.ow - 1
    entryX: int = child.x
    arrowXExit: int = parentRx + 1
    arrowXEntry: int = entryX - 1
    parentPort: Node.Port | None = parent.output_ports.get(out_key)
    childPort: Node.Port | None = child.input_ports.get(in_key)
    parentSignal: str | None = parentPort.signal if parentPort else None
    childSignal: str | None = childPort.signal if childPort else None

    if parentSignal:
        labelX: int = arrowXExit + 1
        limitX: int = channelX if exitY != entryY else arrowXEntry
        if exitY == entryY and childSignal:
            limitX = min(limitX, arrowXEntry - len(childSignal) - 1)
        canvas.text(labelX, exitY, parentSignal[: max(0, limitX - labelX)], color)

    if childSignal:
        labelX = arrowXEntry - len(childSignal)
        limitX = channelX + 1 if exitY != entryY else arrowXExit + 1
        if exitY == entryY and parentSignal:
            limitX = max(limitX, arrowXExit + 1 + len(parentSignal) + 1)
        labelX = max(limitX, labelX)
        canvas.text(
            labelX,
            entryY,
            childSignal[: arrowXEntry - labelX],
            color,
        )


def _returnLabels_render(
    canvas: Canvas,
    parent: Node,
    child: Node,
    out_key: PortKey,
    in_key: PortKey,
    childRetY: int,
    parentRetY: int,
    channelX: int,
    color: str | None,
) -> None:
    """Render return labels on both ends of the return wire."""
    parentRx: int = parent.x + parent.ow - 1
    childLx: int = child.x
    arrowXExit: int = childLx - 1
    arrowXEntry: int = parentRx + 1
    parentPort: Node.Port | None = parent.output_ports.get(out_key)
    childPort: Node.Port | None = child.input_ports.get(in_key)
    parentRet: str | None = parentPort.ret if parentPort else None
    childRet: str | None = childPort.ret if childPort else None

    if parentRet:
        labelX: int = arrowXEntry + 1
        limitX: int = channelX if childRetY != parentRetY else arrowXExit
        if childRetY == parentRetY and childRet:
            limitX = min(limitX, arrowXExit - len(childRet) - 1)
        canvas.text(
            labelX,
            parentRetY,
            parentRet[: max(0, limitX - labelX)],
            color,
        )

    if childRet:
        labelX = arrowXExit - len(childRet)
        limitX = channelX + 1 if childRetY != parentRetY else arrowXEntry + 1
        if childRetY == parentRetY and parentRet:
            limitX = max(limitX, arrowXEntry + 1 + len(parentRet) + 1)
        labelX = max(limitX, labelX)
        canvas.text(labelX, childRetY, childRet[: arrowXExit - labelX], color)


def wireForward_render(
    canvas: Canvas,
    parent: Node,
    child:  Node,
    out_key: PortKey,
    in_key:  PortKey,
    color: str | None = None,
) -> None:
    """Draw the forward call wire from parent chip to child chip."""
    exitY: int
    entryY: int
    parentIdx: int
    exitY, entryY, parentIdx = _forwardRows_resolve(parent, child, out_key, in_key)
    if exitY == entryY:
        channelX: int = _forwardStraight_render(
            canvas,
            parent.x + parent.ow - 1,
            child.x,
            exitY,
            color,
        )
    else:
        channelX = _forwardJog_render(
            canvas, parent, child, exitY, entryY, out_key, in_key, color
        )

    _forwardLabels_render(
        canvas, parent, child, out_key, in_key, exitY, entryY, channelX, color
    )


def wireReturn_render(
    canvas: Canvas,
    parent: Node,
    child:  Node,
    out_key: PortKey,
    in_key:  PortKey,
    color: str | None = None,
) -> None:
    """Draw the return wire from child chip back to parent chip."""
    childRetY: int
    parentRetY: int
    parentIdx: int
    childRetY, parentRetY, parentIdx = _returnRows_resolve(
        parent, child, out_key, in_key
    )
    if childRetY == parentRetY:
        channelX: int = _returnStraight_render(
            canvas,
            parent.x + parent.ow - 1,
            child.x,
            childRetY,
            color,
        )
    else:
        channelX = _returnJog_render(
            canvas, parent, child, childRetY, parentRetY, out_key, in_key, color
        )

    canvas.set(parent.x + parent.ow, parentRetY, Wire.LA, color)
    _returnLabels_render(
        canvas,
        parent,
        child,
        out_key,
        in_key,
        childRetY,
        parentRetY,
        channelX,
        color,
    )


def thread_render(canvas: Canvas, root: Node) -> None:
    """Drive the wire through the full DFS call tree."""
    expanded: set[int] = set()

    def _nodeWire_render(node: Node) -> None:
        """Render one node's outgoing calls while avoiding recursive re-expansion."""
        expanded.add(id(node))
        child: Node
        out_key: PortKey
        in_key:  PortKey
        for child, out_key, in_key in node.call_sequence:
            wireForward_render(canvas, node, child, out_key, in_key)
            if id(child) not in expanded:
                _nodeWire_render(child)
            wireReturn_render(canvas, node, child, out_key, in_key)

    _nodeWire_render(root)
