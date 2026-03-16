"""Layout computation: column positions, chip sizes, channel widths.

Computes geometry for every node in the call tree before any rendering takes
place. All canvas coordinates are integers (column, row) with (0,0) at the
top-left.
"""
from __future__ import annotations

# Standard library
# Local
from signalflow.legacy.config import config
from signalflow.legacy.models import Node, PortKey
from signalflow.legacy.models.chip_geometry import ChipGeometry


def _nodes_stage1_build(nodes: list[Node]) -> None:
    """Build Stage 1 structural geometry for every flattened node."""
    node: Node
    for node in nodes:
        node.geometry = ChipGeometry.build_structural(node)
        node.ow = node.geometry.chipOw
        node.chipH = node.geometry.chipH


def _columnOffsets_compute(
    nodes: list[Node], root: Node, cw: int
) -> tuple[int, dict[int, int]]:
    """Return maximum column index and the assigned X offset per column."""
    maxCol: int = col_assign(root)
    leftOffset: int = leftMargin_compute(root)
    colXOffsets: dict[int, int] = {}
    currentX: int = leftOffset
    gapWidths: dict[int, int] = channelGapWidths_compute(root)

    col: int
    for col in range(maxCol + 1):
        colNodes: list[Node] = [node for node in nodes if node.col == col]
        colXOffsets[col] = currentX
        if not colNodes:
            continue
        currentX += max(node.ow for node in colNodes) + gapWidths.get(col, cw)

    return maxCol, colXOffsets


def _x_assign(nodes: list[Node], colXOffsets: dict[int, int]) -> None:
    """Assign X coordinates from precomputed column offsets."""
    node: Node
    for node in nodes:
        node.x = colXOffsets[node.col]


def _y_assign(nodes: list[Node], maxCol: int) -> None:
    """Stack nodes vertically within each column."""
    col: int
    for col in range(maxCol + 1):
        colNodes: list[Node] = [node for node in nodes if node.col == col]
        cursorY: int = config.moduleTopRows
        node: Node
        for node in colNodes:
            node.y = cursorY
            cursorY += node.chipH + config.verticalChipPadding


def _moduleRegions_deoverlap(nodes: list[Node]) -> None:
    """Shift whole modules downward until their rectangles no longer overlap."""
    from signalflow.legacy.lib.boxes import moduleBox_compute

    placed: list[tuple[str, int, int, int, int]] = []
    while True:
        boxes = moduleBox_compute(nodes)
        shifted: bool = False
        for box in sorted(boxes, key=lambda b: (b.oy0, b.ox0, b.label)):
            shiftY: int = 0
            label: str = box.label
            ox0: int = box.ox0
            oy0: int = box.oy0
            ox1: int = box.ox1
            oy1: int = box.oy1

            prevOx0: int
            prevOy0: int
            prevOx1: int
            prevOy1: int
            for _prevLabel, prevOx0, prevOy0, prevOx1, prevOy1 in placed:
                xOverlap: bool = not (ox1 < prevOx0 or prevOx1 < ox0)
                yOverlap: bool = not (oy1 < prevOy0 or prevOy1 < oy0 + shiftY)
                if xOverlap and yOverlap:
                    shiftY = max(shiftY, prevOy1 - oy0 + 1)

            if shiftY <= 0:
                placed.append((label, ox0, oy0, ox1, oy1))
                continue

            node: Node
            for node in nodes:
                if node.module == label:
                    node.y += shiftY
            shifted = True
            break

        if not shifted:
            return
        placed.clear()


def _leafRows_assign(node: Node) -> None:
    """Assign the single-entry leaf geometry rows."""
    pkey: PortKey = next(iter(node.input_ports))
    node.entryRows[pkey] = node.y + 3
    node.returnRows[pkey] = node.y + 5


def _sovereignRows_assign(node: Node) -> None:
    """Collapse all caller-specific west rows onto one sovereign input pair."""
    centeredEntry: int = node.y + 3 + (node.chipH - 5) // 2
    centeredReturn: int = centeredEntry + 1
    pkey: PortKey
    for pkey in node.input_ports:
        node.entryRows[pkey] = centeredEntry
        node.returnRows[pkey] = centeredReturn


def _explicitRows_assign(node: Node, spacing: int) -> None:
    """Assign explicit west-wall entry/return rows for one chip."""
    assert node.geometry is not None
    pairBaseRow: int = node.y + 3 + node.geometry.ewOff
    leftSignalCounts: dict[str, int] = {}
    leftReturnCounts: dict[str, int] = {}
    if node.geometry.usesManifoldLayout:
        leftSignalCounts, leftReturnCounts = (
            ChipGeometry.leftEndpointDensityHints_compute(
                node, node.geometry.signalNames
            )
        )

    pkey: PortKey
    port: Node.Port
    for pkey, port in node.input_ports.items():
        signalCount: int = leftSignalCounts.get(port.signal, 0) if port.signal else 0
        returnCount: int = leftReturnCounts.get(port.ret, 0) if port.ret else 0

        signalLift: int = 0
        if signalCount > 0 and not (config.passThroughAllowed and signalCount == 1):
            signalLift = signalCount

        returnTail: int = 0
        if returnCount > 0 and not (config.passThroughAllowed and returnCount == 1):
            returnTail = returnCount

        entryRow: int = pairBaseRow + signalLift
        returnRow: int = entryRow + 1
        node.entryRows[pkey] = entryRow
        node.returnRows[pkey] = returnRow
        pairBaseRow = max(pairBaseRow + spacing, returnRow + returnTail + 1)


def _portRows_assign(nodes: list[Node]) -> None:
    """Assign per-port entry/return rows and finalize Stage 2 geometry."""
    node: Node
    for node in nodes:
        spacing: int = (
            config.portVerticalSpacing
            if node.geometry and node.geometry.usesManifoldLayout
            else 3
        )

        if not node.isInputExplicit and len(node.input_ports) > 1:
            _sovereignRows_assign(node)
        elif (
            not node.internal_wiring
            and not node.children
            and len(node.input_ports) == 1
        ):
            _leafRows_assign(node)
        else:
            _explicitRows_assign(node, spacing)

        if node.entryRows:
            node.entryRow = next(iter(node.entryRows.values()))
        if node.returnRows:
            node.returnRow = next(iter(node.returnRows.values()))

        node.geometry.resolve(node, node.y, node.entryRows, node.returnRows)


def _channelWidth_required(node: Node) -> int:
    """Return the required horizontal gap after this parent column."""
    nCh: int = len(node.children)
    if nCh == 0:
        return config.channelWidth

    # Max space needed for child-side label in this group (LEFT wall of children)
    maxChildLbl: int = 0
    child: Node
    key: PortKey
    port: Node.Port
    for child in node.children:
        for key, port in child.input_ports.items():
            if key[0] == id(node):   # only ports whose parent is this node
                lblF: int = len(port.signal) if port.signal else 0
                lblR: int = len(port.ret) if port.ret else 0
                maxChildLbl = max(maxChildLbl, lblF, lblR)

    # Max space needed for parent-side label in this group (RIGHT wall of parent)
    maxParentLbl: int = 0
    for child in node.children:
        for key, port in node.output_ports.items():
            if key[0] == id(child):   # only ports whose child is this child
                lblFP: int = len(port.signal) if port.signal else 0
                lblRP: int = len(port.ret) if port.ret else 0
                maxParentLbl = max(maxParentLbl, lblFP, lblRP)

    # Total width = [Exit(1)]+[ParentLabel]+[Bus(2N)]+[ChildLabel]+[Entry(1)]
    # Use call_sequence length for the wire count (includes repeated children).
    busW: int = 2 * len(node.call_sequence) if node.call_sequence else 2 * nCh
    total: int = 1 + maxParentLbl + 1 + busW + 1 + maxChildLbl + 1

    # Module box padding if applicable
    total += 2 * config.moduleOuterWidth

    return max(config.channelWidth, total)


def channelGapWidths_compute(root: Node) -> dict[int, int]:
    """Compute required horizontal spacing per column gap.

    The key is the parent column index. ``gapWidths[c]`` is the minimum gap
    required between column ``c`` and column ``c + 1``.
    """
    col_assign(root)
    gapWidths: dict[int, int] = {}
    seen: set[int] = set()

    def _node_scan(node: Node) -> None:
        """Scan one subtree and accumulate required gap widths per column."""
        if id(node) in seen:
            return
        seen.add(id(node))
        if node.children:
            required: int = _channelWidth_required(node)
            gapWidths[node.col] = max(
                gapWidths.get(node.col, config.channelWidth),
                required,
            )
        for child in node.children:
            _node_scan(child)

    _node_scan(root)
    return gapWidths


def channelWidth_compute(root: Node) -> int:
    """Return the maximum required inter-column gap for backward compatibility."""
    gapWidths: dict[int, int] = channelGapWidths_compute(root)
    return max(gapWidths.values(), default=config.channelWidth)


def leftMargin_compute(root: Node) -> int:
    """Compute the left canvas margin required before the root chip.

    This space is needed for root-entry labels or module box padding. If
    root has children (meaning it's part of a larger graph), the standard
    minimum margin (moduleOuterWidth + moduleInnerMargin) is returned unchanged.

    Args:
        root: The root node of the graph.

    Returns:
        Minimum horizontal offset for the first column.
    """
    if root.children:
        return config.moduleOuterWidth + config.moduleInnerMargin

    maxLbl: int = 0
    p: Node.Port
    for p in root.input_ports.values():
        if p.signal:
            maxLbl = max(maxLbl, len(p.signal))
        if p.ret:
            maxLbl = max(maxLbl, len(p.ret))

    # 2 leading dashes + label + 2 trailing dashes + moduleOuterWidth (box border gap)
    return max(
        config.moduleOuterWidth + config.moduleInnerMargin,
        maxLbl + config.moduleOuterWidth + 4,
    )


def col_assign(root: Node) -> int:
    """Assign column index to every node in the tree recursively.

    Args:
        root: Root node to start assignment from.

    Returns:
        The maximum column index assigned.
    """
    maxC: int = 0
    seen: set[int] = set()

    def _column_walk(n: Node, c: int) -> None:
        """Assign one node and its descendants to successive columns."""
        nonlocal maxC
        if id(n) in seen:
            return
        seen.add(id(n))
        n.col = c
        maxC = max(maxC, c)
        for child in n.children:
            _column_walk(child, c + 1)

    _column_walk(root, 0)
    return maxC


def layout_compute(root: Node, cw: int) -> None:
    """Compute final (x,y) coordinates for all nodes.

    Args:
        root: The root node of the graph.
        cw: The global channel width to use between columns.
    """
    from signalflow.legacy.lib.tree import tree_flatten

    nodes: list[Node] = tree_flatten(root)
    _nodes_stage1_build(nodes)
    maxCol: int
    colXOffsets: dict[int, int]
    maxCol, colXOffsets = _columnOffsets_compute(nodes, root, cw)
    _x_assign(nodes, colXOffsets)
    _y_assign(nodes, maxCol)
    _moduleRegions_deoverlap(nodes)
    _portRows_assign(nodes)
