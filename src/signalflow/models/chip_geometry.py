"""Authoritative chip-interior geometry — single source of truth.

Stage 1 (build_structural): computed from wiring only, before y is assigned.
Stage 2 (resolve):          computed from y and wall rows, after layout.
All rendering code reads from this record; no downstream code recomputes
geometry from node fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from signalflow.config import config

if TYPE_CHECKING:
    from signalflow.models.node import Node


@dataclass
class ChipGeometry:
    """Single authoritative source for all chip-interior geometry.

    Lifecycle
    ---------
    Stage 1  (pre-y, structural):
        ChipGeometry.build_structural(node) → sets ewOff, chipH, chipOw,
        leftNames, rightNames, signalNames, isExplicit.  Called during
        layout_compute before y is assigned.

    Stage 2  (post-y, positional):
        geo.resolve(y0, entryRows, returnRows) → sets leftWallRows,
        rightWallRows, straightPairs, wiringPairs, lCounts, unitPorts,
        portToX, anchorFloor, interiorMax, allAnchorRows.
        Implemented in Phase 2.
    """

    # ── Stage 1: structural (wiring-only) ─────────────────────────────────
    ewOff:       int      = 0
    chipH:       int      = 0
    chipOw:      int      = 0
    leftNames:   set[str] = field(default_factory=set)
    rightNames:  set[str] = field(default_factory=set)
    signalNames: set[str] = field(default_factory=set)  # port.signal names
    isExplicit:  bool     = True   # resolved inputExplicit (None → config)

    # ── Stage 2: positional (requires y0) — implemented in Phase 2 ────────
    resolved:        bool                  = False
    y0:              int                   = 0
    leftWallRows:    dict[str, list[int]]  = field(default_factory=dict)
    rightWallRows:   dict[str, list[int]]  = field(default_factory=dict)
    straightPairs:   list[tuple[str, str]] = field(default_factory=list)
    wiringPairs:     list[tuple[str, str]] = field(default_factory=list)
    lCounts:         dict[str, int]        = field(default_factory=dict)
    unitPorts:       set[str]              = field(default_factory=set)
    portToX:         dict[str, int]        = field(default_factory=dict)
    leftZoneInnerX:  int                   = 0
    rightZoneInnerX: int                   = 0
    anchorFloor:     int                   = 0
    interiorMax:     int                   = 0
    allAnchorRows:   dict[str, list[int]]  = field(default_factory=dict)

    # ── Stage 1 factory ───────────────────────────────────────────────────

    @classmethod
    def build_structural(cls, node: Node) -> ChipGeometry:
        """Compute wiring-only geometry before y is known.

        Consolidates ewTopOffset_get, chipH_precompute, chipOw_compute.
        """
        geo = cls()

        geo.leftNames = {
            name
            for port in node.input_ports.values()
            for name in (port.signal, port.ret)
            if name
        }
        geo.rightNames = {
            name
            for port in node.output_ports.values()
            for name in (port.signal, port.ret)
            if name
        }
        geo.signalNames = {
            port.signal
            for ports_dict in (node.input_ports, node.output_ports)
            for port in ports_dict.values()
            if port.signal
        }

        # Resolve inputExplicit: None defers to global config
        if node.inputExplicit is None:
            geo.isExplicit = config.chipIoInputExplicit
        else:
            geo.isExplicit = bool(node.inputExplicit)

        geo.ewOff  = cls._ewOff_compute(node)
        geo.chipH  = cls._chipH_compute(node, geo.ewOff, geo.isExplicit)
        geo.chipOw = cls._chipOw_compute(node, geo.leftNames, geo.rightNames)
        return geo

    # ── Stage 1 helpers ───────────────────────────────────────────────────

    @staticmethod
    def _ewOff_compute(node: Node) -> int:
        """Count E→W trunk rows needed at top of chip interior.

        Mirrors ewTopOffset_get: E→W pairs whose src is on the right wall,
        excluding straight-through candidates (srcCounts==1 AND dstCounts==1).
        """
        if not node.internal_wiring:
            return 0
        rightRetPorts: set[str] = {
            port.ret
            for port in node.output_ports.values()
            if port.ret
        }
        srcCounts: dict[str, int] = {}
        dstCounts: dict[str, int] = {}
        w: str
        for w in node.internal_wiring:
            if ":" not in w:
                continue
            src: str
            dst: str
            src, dst = w.split(":", 1)
            srcCounts[src] = srcCounts.get(src, 0) + 1
            dstCounts[dst] = dstCounts.get(dst, 0) + 1
        total: int = 0
        for w in node.internal_wiring:
            if ":" not in w:
                continue
            src, dst = w.split(":", 1)
            if src not in rightRetPorts:
                continue
            # Straight-through candidates route as a plain hline — no trunk needed.
            # When passThroughAllowed=False, ALL pairs go through the manifold,
            # so the exclusion must not apply.
            if config.passThroughAllowed and srcCounts[src] == 1 and dstCounts[dst] == 1:
                continue
            total += 1
        return total

    @staticmethod
    def _chipH_compute(node: Node, ewOff: int, isExplicit: bool) -> int:
        """Compute chip height in rows.

        Mirrors chipH_precompute using the pre-resolved ewOff and isExplicit
        so those values are not re-derived from node fields.
        """
        nLeft: int  = len(node.input_ports)
        nRight: int = len(node.output_ports) if node.output_ports else len(node.children)
        if not isExplicit:
            nLeft = 1
        n: int = max(nLeft, nRight)

        if n <= 1:
            return config.baseLeafHeight

        if not node.internal_wiring:
            return 3 * n + 3

        spacing: int = config.portVerticalSpacing
        portCounts: dict[str, int] = {}
        wiringCount: int = 0
        for w in node.internal_wiring:
            if ":" not in w:
                continue
            wiringCount += 1
            src: str
            dst: str
            src, dst = w.split(":")
            portCounts[src] = portCounts.get(src, 0) + 1
            portCounts[dst] = portCounts.get(dst, 0) + 1

        maxPortDensity: int = max(portCounts.values(), default=0)
        lastWallReturnOffset: int = 3 + ewOff + spacing * (n - 1) + 1

        h: int
        if not isExplicit:
            leftNames: set[str] = {
                nm
                for port in node.input_ports.values()
                for nm in (port.signal, port.ret)
                if nm
            }
            maxRightDensity: int = max(
                (cnt for prt, cnt in portCounts.items() if prt not in leftNames),
                default=0,
            )
            weTrunkCount: int = sum(
                1 for _w in node.internal_wiring
                if ":" in _w and _w.split(":")[0] in leftNames
            )
            h = lastWallReturnOffset + maxRightDensity + weTrunkCount + 2
        else:
            h = lastWallReturnOffset + maxPortDensity + wiringCount + 2
        return max(config.baseLeafHeight, h)

    @staticmethod
    def _chipOw_compute(
        node: Node, leftNames: set[str], rightNames: set[str]
    ) -> int:
        """Compute chip outer width.

        Mirrors chipOw_compute using the pre-built leftNames/rightNames.
        """
        labelW: int = len(node.func) + config.chipPaddingX * 2

        if not node.internal_wiring:
            return labelW + 2

        lCounts: dict[str, int] = {}
        for wirePair in node.internal_wiring:
            if ":" not in wirePair:
                continue
            src: str
            dst: str
            src, dst = wirePair.split(":")
            lCounts[src] = lCounts.get(src, 0) + 1
            lCounts[dst] = lCounts.get(dst, 0) + 1

        def _side(name: str, prefer: str) -> str:
            inL: bool = name in leftNames
            inR: bool = name in rightNames
            if inL and not inR:
                return "L"
            if inR and not inL:
                return "R"
            return prefer

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
            and _side(s, "L") != _side(d, "R")
            for s, d in allPairs
        )
        if allStraight:
            return labelW + 2

        vLeft: int  = sum(cnt for name, cnt in lCounts.items() if name in leftNames)
        vRight: int = sum(cnt for name, cnt in lCounts.items() if name in rightNames)

        maxLeftLabel: int  = max((len(n) + 1 for n in leftNames  if n in lCounts), default=0)
        maxRightLabel: int = max((len(n) + 1 for n in rightNames if n in lCounts), default=0)

        manifoldMinOw: int = 12 + maxLeftLabel + maxRightLabel + 2 * (vLeft + vRight)
        return max(labelW + 2, manifoldMinOw)

    # ── Canonical queries ─────────────────────────────────────────────────

    def port_side(self, name: str, prefer: str | None = None) -> str:
        """Return 'L' or 'R' for a port name. Single authoritative implementation."""
        inL: bool = name in self.leftNames
        inR: bool = name in self.rightNames
        if inL and not inR:
            return "L"
        if inR and not inL:
            return "R"
        return prefer if prefer else "L"

    def is_signal(self, name: str) -> bool:
        """True if name is a forward signal (appears in port.signal)."""
        return name in self.signalNames

    # ── Stage 2 resolver ─────────────────────────────────────────────────

    def resolve(
        self,
        node: Node,
        y0: int,
        entryRows: dict[int, int],
        returnRows: dict[int, int],
    ) -> None:
        """Compute all positional geometry once y is known.

        Must be called after layout_compute has assigned y, entryRows, and
        returnRows.  Replicates every geometry block in chip_render so that
        rendering code can read from node.geometry instead of recomputing.
        """
        self.y0          = y0
        self.anchorFloor = y0 + 3 + self.ewOff
        self.interiorMax = y0 + self.chipH - 2

        # ── leftWallRows (from entryRows/returnRows) ──────────────────────
        parentId: int
        port: object  # Node.Port at runtime
        name: str | None
        for parentId, port in node.input_ports.items():
            for name in (port.signal, port.ret):
                if name:
                    self.leftWallRows.setdefault(name, [])
                    row: int = (
                        entryRows[parentId]
                        if port.signal == name
                        else returnRows[parentId]
                    )
                    if row not in self.leftWallRows[name]:
                        self.leftWallRows[name].append(row)

        # ── rightWallRows (mirrors chips.py rightBaseRows) ────────────────
        # High-Resolution Rule: only manifold chips use portVerticalSpacing;
        # non-manifold chips always use spacing=3 (matches layout_compute).
        spacing: int = config.portVerticalSpacing if node.internal_wiring else 3
        i: int
        for i, port in enumerate(node.output_ports.values()):
            offset: int
            for name, offset in ((port.signal, 0), (port.ret, 1)):
                if name:
                    self.rightWallRows.setdefault(name, [])
                    row = y0 + 3 + self.ewOff + spacing * i + offset
                    if row not in self.rightWallRows[name]:
                        self.rightWallRows[name].append(row)

        if not node.internal_wiring:
            self.resolved = True
            return

        # ── Classify wiring pairs (mirrors chips.py section 2.1) ─────────
        # sorted() matches the sort in chips.py to ensure identical ordering.
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
        for src, dst in allPairsRaw:
            srcCounts[src] = srcCounts.get(src, 0) + 1
            dstCounts[dst] = dstCounts.get(dst, 0) + 1

        straightPairsList: list[tuple[str, str]] = []
        wiringPairsList:   list[tuple[str, str]] = []

        for src, dst in allPairsRaw:
            sSide: str = self.port_side(src)
            dSide: str = self.port_side(dst, prefer="R" if sSide == "L" else "L")
            if (
                sSide != dSide
                and srcCounts.get(src, 0) == 1
                and dstCounts.get(dst, 0) == 1
            ):
                sRows = self.leftWallRows if sSide == "L" else self.rightWallRows
                dRows = self.rightWallRows if dSide == "R" else self.leftWallRows
                sRow: int = (sRows.get(src) or [y0 + 3])[0]
                dRow: int = (dRows.get(dst) or [y0 + 3])[0]
                if sRow == dRow:
                    straightPairsList.append((src, dst))
                    continue
            wiringPairsList.append((src, dst))

        self.straightPairs = straightPairsList
        self.wiringPairs   = wiringPairsList

        if not wiringPairsList:
            self.resolved = True
            return

        # ── lCounts (manifold-only, mirrors chips.py section 2.4) ────────
        for src, dst in wiringPairsList:
            self.lCounts[src] = self.lCounts.get(src, 0) + 1
            self.lCounts[dst] = self.lCounts.get(dst, 0) + 1

        # ── portToX, zone boundaries (mirrors chips.py section 2.4) ──────
        x0: int = node.x
        rx: int = x0 + node.ow - 1

        leftPorts: list[str] = sorted(
            p for p in self.lCounts
            if p in self.leftNames and p not in self.rightNames
        )
        rightPorts: list[str] = sorted(
            p for p in self.lCounts
            if p in self.rightNames
        )

        maxLeftLabel: int  = max((len(p) + 1 for p in leftPorts),  default=0)
        maxRightLabel: int = max((len(p) + 1 for p in rightPorts), default=0)
        leftLongStart: int  = x0 + 4 + maxLeftLabel
        rightLongStart: int = rx - 4 - maxRightLabel

        vTrackL: int = 0
        vTrackR: int = 0

        p: str
        for p in leftPorts:
            self.portToX[p] = leftLongStart + 2 * vTrackL
            vTrackL += self.lCounts[p]

        for p in rightPorts:
            self.portToX[p] = rightLongStart - 2 * (vTrackR + self.lCounts[p] - 1)
            vTrackR += self.lCounts[p]

        self.leftZoneInnerX  = leftLongStart + 2 * vTrackL
        self.rightZoneInnerX = rightLongStart + 2 - 2 * vTrackR

        # ── allAnchorRows (mirrors chips.py section 2.5.pre) ─────────────
        for p in self.lCounts:
            density: int  = self.lCounts[p]
            wallRow: int  = self._wallRow_get(p, y0)
            isSig: bool   = self.is_signal(p)
            rows: list[int]
            if isSig:
                rows = [wallRow - 1 - k for k in range(density)]
                if rows and min(rows) < self.anchorFloor:
                    rows = [wallRow + 1 + k for k in range(density)]
            else:
                rows = [wallRow + 1 + k for k in range(density)]
                if rows and max(rows) > self.interiorMax:
                    rows = [wallRow - 1 - k for k in range(density)]
            rows = [max(self.anchorFloor, min(self.interiorMax, r)) for r in rows]
            self.allAnchorRows[p] = rows

        # ── unitPorts (mirrors chips.py section 2.5.1) ────────────────────
        if config.passThroughAllowed:
            for p in self.lCounts:
                if self.lCounts[p] == 1:
                    self.unitPorts.add(p)
                    self.allAnchorRows[p] = [self._wallRow_get(p, y0)]

        self.resolved = True

    # ── Internal helpers ──────────────────────────────────────────────────

    def _wallRow_get(self, port: str, y0: int) -> int:
        """Return the wall row for a port (from leftWallRows or rightWallRows)."""
        side: str = self.port_side(port)
        base = self.leftWallRows if side == "L" else self.rightWallRows
        return (base.get(port) or [y0 + 3])[0]

    def wall_row(self, name: str) -> int:
        """Return the absolute wall row for a port name. Requires Stage 2."""
        if not self.resolved:
            raise RuntimeError("wall_row() requires Stage 2: call resolve() first")
        return self._wallRow_get(name, self.y0)
