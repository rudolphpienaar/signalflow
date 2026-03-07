"""Layout computation: column positions, chip sizes, channel widths.

Computes geometry for every node in the call tree before any rendering takes
place. All canvas coordinates are integers (column, row) with (0,0) at the
top-left.
"""
from __future__ import annotations

# Standard library
# Local
from signalflow.config import config
from signalflow.models import Node
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
        for child in node.children:
            localP: Node.Port | None = child.input_ports.get(id(node))
            if localP:
                lblF: int = len(localP.signal) if localP.signal else 0
                lblR: int = len(localP.ret) if localP.ret else 0
                maxChildLbl = max(maxChildLbl, lblF, lblR)

        # Max space needed for parent-side label in this group (RIGHT wall of parent)
        maxParentLbl: int = 0
        for child in node.children:
            pPort: Node.Port | None = node.output_ports.get(id(child))
            if pPort:
                lblFP: int = len(pPort.signal) if pPort.signal else 0
                lblRP: int = len(pPort.ret) if pPort.ret else 0
                maxParentLbl = max(maxParentLbl, lblFP, lblRP)

        # Total width = [Exit(1)]+[ParentLabel]+[Bus(2N)]+[ChildLabel]+[Entry(1)]
        # We also need at least 1 column gap between label and bus.
        busW: int = 2 * nCh
        total: int = 1 + maxParentLbl + 1 + busW + 1 + maxChildLbl + 1

        # Module box padding if applicable
        total += 2 * config.moduleOuterWidth

        if total > minCw:
            minCw = total

        for child in node.children:
            _scan(child)

    _scan(root)
    return minCw


def chipOw_compute(node: Node) -> int:
    """Compute the specific outer width needed for this chip.

    Scales based on the total longitude zone density required on each wall so
    that the left and right zones never overlap and the latitude zone in
    between always has at least 4 columns.

    Args:
        node: The node to compute width for.

    Returns:
        The calculated outer width as an integer.
    """
    labelW: int = len(node.func) + config.chipPaddingX * 2

    if not node.internal_wiring:
        return labelW + 2

    # Build per-port connection density (mirrors chips.py section 2.4 logic)
    lCounts: dict[str, int] = {}
    wirePair: str
    for wirePair in node.internal_wiring:
        if ":" not in wirePair:
            continue
        src: str
        dst: str
        src, dst = wirePair.split(":")
        lCounts[src] = lCounts.get(src, 0) + 1
        lCounts[dst] = lCounts.get(dst, 0) + 1

    leftNames: set[str] = {
        name
        for port in node.input_ports.values()
        for name in (port.signal, port.ret)
        if name
    }
    rightNames: set[str] = {
        name
        for port in node.output_ports.values()
        for name in (port.signal, port.ret)
        if name
    }

    # If every wiring pair is a density-1 cross-wall pair it will be rendered
    # as a straight-through hline in chips.py — no manifold columns needed.
    # Mirrors the prefer="R" disambiguation from chips.py portSide_get so that
    # same-name pass-through pairs (e.g. "s1:s1") resolve src→L, dst→R.
    def _side(name: str, prefer: str) -> str:
        inL: bool = name in leftNames
        inR: bool = name in rightNames
        if inL and not inR:
            return "L"
        if inR and not inL:
            return "R"
        return prefer  # ambiguous same-name port: use caller's preference

    srcCounts: dict[str, int] = {}
    dstCounts: dict[str, int] = {}
    allPairs: list[tuple[str, str]] = []
    for wirePair in node.internal_wiring:
        if ":" not in wirePair:
            continue
        src, dst = wirePair.split(":")
        srcCounts[src] = srcCounts.get(src, 0) + 1
        dstCounts[dst] = dstCounts.get(dst, 0) + 1
        allPairs.append((src, dst))

    allStraight: bool = all(
        srcCounts.get(s, 0) == 1
        and dstCounts.get(d, 0) == 1
        and _side(s, "L") != _side(d, "R")  # cross-wall with disambiguation
        for s, d in allPairs
    )
    if allStraight:
        return labelW + 2

    vLeft: int = sum(cnt for name, cnt in lCounts.items() if name in leftNames)
    vRight: int = sum(cnt for name, cnt in lCounts.items() if name in rightNames)

    # Anchor labels: "{port}►/◄" on left, "►/◄{port}" on right — len = len(name)+1
    maxLeftLabel: int = max((len(n) + 1 for n in leftNames if n in lCounts), default=0)
    maxRightLabel: int = max(
        (len(n) + 1 for n in rightNames if n in lCounts), default=0
    )

    # 1+1+1+LL+1 + 2*vL + ≥4(lat) + 2*vR + 1+RL+1+1+1 = 12 + LL + RL + 2*(vL+vR)
    manifoldMinOw: int = 12 + maxLeftLabel + maxRightLabel + 2 * (vLeft + vRight)
    return max(labelW + 2, manifoldMinOw)


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
            parent_id: int
            for parent_id in n.input_ports:
                n.entryRows[parent_id] = centeredEntry
                n.returnRows[parent_id] = centeredReturn
        else:
            ewOff: int = n.geometry.ewOff
            i: int
            pid: int
            for i, pid in enumerate(n.input_ports):
                n.entryRows[pid] = n.y + 3 + ewOff + spacing * i
                n.returnRows[pid] = n.y + 4 + ewOff + spacing * i

        # Set legacy single-port shortcuts from first port (backward compat)
        if n.entryRows:
            n.entryRow = next(iter(n.entryRows.values()))
        if n.returnRows:
            n.returnRow = next(iter(n.returnRows.values()))

        # Note: output_ports are also mapped relative to the same spacing in chips.py
        # but we compute the node's internal state here for reference.
