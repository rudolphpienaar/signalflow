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
            # Straight-through candidates route as a plain hline — no trunk needed
            if srcCounts[src] == 1 and dstCounts[dst] == 1:
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

    # ── Stage 2 resolver (Phase 2) ────────────────────────────────────────

    def resolve(
        self,
        y0: int,
        entryRows: dict[int, int],
        returnRows: dict[int, int],
    ) -> None:
        """Compute positional geometry once y is known. Implemented in Phase 2."""
        raise NotImplementedError("Stage 2 resolve() is implemented in Phase 2")

    def wall_row(self, name: str) -> int:
        """Return the absolute wall row for a port name. Requires Stage 2."""
        raise NotImplementedError("wall_row() requires Stage 2 resolve()")
