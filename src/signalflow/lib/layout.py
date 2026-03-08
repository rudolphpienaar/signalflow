"""Layout computation: column positions, chip sizes, channel widths.

Computes geometry for every node in the call tree before any rendering takes
place. All canvas coordinates are integers (column, row) with (0,0) at the
top-left.
"""
from __future__ import annotations

# Standard library
# Local
from signalflow.config import config
from signalflow.models import Node, PortKey
from signalflow.models.chip_geometry import ChipGeometry


def channelWidth_compute(root: Node) -> int:
    """Scan the entire tree to find the minimum global channel width needed.

    Finds the maximum horizontal space required by any parent->children group,
    considering signal/return labels and internal staggering.

    Args:
        root: The root node of the call graph.

    Returns:
        The calculated minimum channel width as an integer.
    """
    minCw: int = config.channelWidth

    def _scan(node: Node) -> None:
        nonlocal minCw
        nCh: int = len(node.children)
        if nCh == 0:
            return

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

        if total > minCw:
            minCw = total

        for child in node.children:
            _scan(child)

    _scan(root)
    return minCw


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

    def _walk(n: Node, c: int) -> None:
        nonlocal maxC
        n.col = c
        maxC = max(maxC, c)
        for child in n.children:
            _walk(child, c + 1)

    _walk(root, 0)
    return maxC


def layout_compute(root: Node, cw: int) -> None:
    """Compute final (x,y) coordinates for all nodes.

    Args:
        root: The root node of the graph.
        cw: The global channel width to use between columns.
    """
    from signalflow.lib.tree import tree_flatten

    nodes: list[Node] = tree_flatten(root)

    # 1. Compute individual widths (Stage 1 geometry)
    n: Node
    for n in nodes:
        n.geometry = ChipGeometry.build_structural(n)
        n.ow    = n.geometry.chipOw
        n.chipH = n.geometry.chipH

    # 2. Assign X by column
    maxCol: int = col_assign(root)
    leftOffset: int = leftMargin_compute(root)

    colXOffsets: dict[int, int] = {}
    currentX: int = leftOffset

    c: int
    for c in range(maxCol + 1):
        colNodes: list[Node] = [n for n in nodes if n.col == c]
        if not colNodes:
            colXOffsets[c] = currentX
            continue

        colXOffsets[c] = currentX
        # Find widest chip in this column
        maxOw: int = max(n.ow for n in colNodes)
        currentX += maxOw + cw

    for n in nodes:
        n.x = colXOffsets[n.col]

    # 3. Assign Y by stacking nodes within each column
    for c in range(maxCol + 1):
        colNodes: list[Node] = [n for n in nodes if n.col == c]
        cursorY: int = config.moduleTopRows
        for n in colNodes:
            n.y = cursorY
            cursorY += n.chipH + config.verticalChipPadding

    # 4. Map Port Rows
    for n in nodes:
        # High-Resolution Rule: Only stretch if a complex manifold is present
        spacing: int = config.portVerticalSpacing if n.internal_wiring else 3

        if not n.isInputExplicit:
            # Sovereign centering: ONE terminal pair on WEST wall, vertically
            # centered in the chip interior. All callers converge on this row.
            centeredEntry: int = n.y + 3 + (n.chipH - 5) // 2
            centeredReturn: int = centeredEntry + 1
            pkey: PortKey
            for pkey in n.input_ports:
                n.entryRows[pkey] = centeredEntry
                n.returnRows[pkey] = centeredReturn
        else:
            ewOff: int = n.geometry.ewOff
            i: int
            pkey: PortKey
            if not n.internal_wiring and not n.children and len(n.input_ports) == 1:
                # True leaf chip — gap row between entry and return for █ block.
                pkey = next(iter(n.input_ports))
                n.entryRows[pkey]  = n.y + 3
                n.returnRows[pkey] = n.y + 5
            else:
                for i, pkey in enumerate(n.input_ports):
                    n.entryRows[pkey] = n.y + 3 + ewOff + spacing * i
                    n.returnRows[pkey] = n.y + 4 + ewOff + spacing * i

        # Set legacy single-port shortcuts from first port (backward compat)
        if n.entryRows:
            n.entryRow = next(iter(n.entryRows.values()))
        if n.returnRows:
            n.returnRow = next(iter(n.returnRows.values()))

        # Stage 2: resolve positional geometry now that y and wall rows are known
        n.geometry.resolve(n, n.y, n.entryRows, n.returnRows)
