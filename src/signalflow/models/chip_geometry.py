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


def _anchor_display(name: str) -> str:
    """Return the display form of a port name, truncated if anchorLabelMaxWidth is set.
    """
    w: int = config.anchorLabelMaxWidth
    return name[:w] if w > 0 and len(name) > w else name


@dataclass(frozen=True)
class WallContinuity:
    """A local chip-internal handoff that stays on the same wall.

    This captures the existing implicit right-wall sequential continuity so it
    can be reused when the same handoff is declared explicitly in
    ``internal_wiring``.
    """

    side: str
    src: str
    dst: str
    srcRow: int
    dstRow: int
    isPure: bool = False

    @property
    def gapRow(self) -> int:
        """The visual gap row between source and destination terminals."""
        return self.srcRow + 1 if self.dstRow >= self.srcRow else self.srcRow - 1


@dataclass(frozen=True)
class WiringDirective:
    """Parsed internal-wiring directive with optional orientation override."""

    src: str
    dst: str
    orientation: str | None = None
    isPure: bool = False


def _endpoint_key(label: str, side: str, kind: str) -> str:
    """Build a manifold-internal endpoint key distinct from the display label."""
    return f"{side}|{kind}|{label}"


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
    usesManifoldLayout: bool = False

    # ── Stage 2: positional (requires y0) — implemented in Phase 2 ────────
    resolved:        bool                  = False
    y0:              int                   = 0
    leftSignalRows:  dict[str, list[int]]  = field(default_factory=dict)
    leftReturnRows:  dict[str, list[int]]  = field(default_factory=dict)
    leftWallRows:    dict[str, list[int]]  = field(default_factory=dict)
    rightSignalRows: dict[str, list[int]]  = field(default_factory=dict)
    rightReturnRows: dict[str, list[int]]  = field(default_factory=dict)
    rightWallRows:   dict[str, list[int]]  = field(default_factory=dict)
    straightDirectives: list[WiringDirective] = field(default_factory=list)
    straightPairs:   list[tuple[str, str]] = field(default_factory=list)
    wiringDirectives: list[WiringDirective] = field(default_factory=list)
    wiringPairs:     list[tuple[str, str]] = field(default_factory=list)
    wallContinuities: list[WallContinuity] = field(default_factory=list)
    purePairs:       set[tuple[str, str]]  = field(default_factory=set)
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

        geo.usesManifoldLayout = cls._usesManifoldLayout_compute(
            node, geo.isExplicit, geo.signalNames
        )
        geo.ewOff  = cls._ewOff_compute(node)
        geo.chipH  = cls._chipH_compute(
            node, geo.ewOff, geo.isExplicit, geo.usesManifoldLayout
        )
        geo.chipOw = cls._chipOw_compute(
            node, geo.leftNames, geo.rightNames, geo.usesManifoldLayout
        )
        return geo

    # ── Stage 1 helpers ───────────────────────────────────────────────────

    @staticmethod
    def _directive_parse(node: Node) -> list[WiringDirective]:
        """Parse internal wiring strings into directives.

        Supported forms:
        - ``src:dst``
        - ``src:dst:pure``
        - ``src:dst:EW|WE|NS|SN``
        - ``src:dst:EW|WE|NS|SN:pure``
        """

        directives: list[WiringDirective] = []
        validOrientation: set[str] = {"EW", "WE", "NS", "SN"}
        w: str
        parts: list[str]
        for w in node.internal_wiring:
            if ":" not in w:
                continue
            parts = w.split(":")
            if len(parts) < 2:
                continue
            src: str = parts[0]
            dst: str = parts[1]
            orientation: str | None = None
            isPure: bool = False
            token: str
            for token in parts[2:]:
                if token == "pure":
                    isPure = True
                elif token in validOrientation:
                    if orientation is not None:
                        raise AssertionError(
                            f"internal_wiring {w!r}: multiple orientation tokens"
                        )
                    orientation = token
                else:
                    raise AssertionError(
                        f"internal_wiring {w!r}: unsupported directive token {token!r}"
                    )
            directives.append(
                WiringDirective(
                    src=src,
                    dst=dst,
                    orientation=orientation,
                    isPure=isPure,
                )
            )
        return directives

    @staticmethod
    def _basicWallRows_compute(
        node: Node,
    ) -> tuple[
        dict[str, list[int]],
        dict[str, list[int]],
        dict[str, list[int]],
        dict[str, list[int]],
    ]:
        """Compute non-manifold relative wall rows from port order.

        This matches the implicit sequential chip layout: spacing is fixed at 3.
        """

        leftSignalRows: dict[str, list[int]] = {}
        leftReturnRows: dict[str, list[int]] = {}
        rightSignalRows: dict[str, list[int]] = {}
        rightReturnRows: dict[str, list[int]] = {}

        i: int
        port: object
        for i, port in enumerate(node.input_ports.values()):
            if port.signal:
                leftSignalRows.setdefault(port.signal, []).append(3 * i)
            if port.ret:
                leftReturnRows.setdefault(port.ret, []).append(3 * i + 1)

        for i, port in enumerate(node.output_ports.values()):
            if port.signal:
                rightSignalRows.setdefault(port.signal, []).append(3 * i)
            if port.ret:
                rightReturnRows.setdefault(port.ret, []).append(3 * i + 1)

        return leftSignalRows, leftReturnRows, rightSignalRows, rightReturnRows

    @staticmethod
    def _explicitSidesAndRows_structural(
        directive: WiringDirective,
        leftSignalRows: dict[str, list[int]],
        leftReturnRows: dict[str, list[int]],
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> tuple[str, str, int, int]:
        """Resolve explicit orientation tokens against structural wall rows."""

        src: str = directive.src
        dst: str = directive.dst
        orientation: str = directive.orientation or ""

        if orientation == "WE":
            assert src in leftSignalRows, (
                f"internal_wiring {src}:{dst}:WE: source must be a west/left signal"
            )
            assert dst in rightSignalRows, (
                f"internal_wiring {src}:{dst}:WE: destination must be an "
                "east/right signal"
            )
            return "L", "R", leftSignalRows[src][0], rightSignalRows[dst][0]

        if orientation == "EW":
            assert src in rightReturnRows, (
                f"internal_wiring {src}:{dst}:EW: source must be an east/right return"
            )
            assert dst in leftReturnRows, (
                f"internal_wiring {src}:{dst}:EW: destination must be a "
                "west/left return"
            )
            return "R", "L", rightReturnRows[src][0], leftReturnRows[dst][0]

        if orientation in {"NS", "SN"}:
            rightPossible: bool = src in rightReturnRows and dst in rightSignalRows
            leftPossible: bool = src in leftSignalRows and dst in leftReturnRows
            assert rightPossible ^ leftPossible, (
                f"internal_wiring {src}:{dst}:{orientation}: "
                "same-wall direction requires a unique right-return->right-signal "
                "or left-signal->left-return interpretation"
            )
            if rightPossible:
                return "R", "R", rightReturnRows[src][0], rightSignalRows[dst][0]
            return "L", "L", leftSignalRows[src][0], leftReturnRows[dst][0]

        raise AssertionError(
            f"internal_wiring {src}:{dst}:{orientation}: unsupported orientation"
        )

    @classmethod
    def _usesManifoldLayout_compute(
        cls,
        node: Node,
        isExplicit: bool,
        signalNames: set[str],
    ) -> bool:
        """True when any wiring requires true manifold geometry.

        A chip can keep the compact implicit layout when every internal pair is
        either:
        - a typed straight-through cross-wall pair, or
        - an adjacent right-wall return→signal handoff that matches the
          existing implicit sequential continuity.
        """

        if not node.internal_wiring:
            return False
        if not isExplicit:
            return True

        (
            leftSignalRows,
            leftReturnRows,
            rightSignalRows,
            rightReturnRows,
        ) = cls._basicWallRows_compute(node)

        directive: WiringDirective
        for directive in cls._directive_parse(node):
            src: str = directive.src
            dst: str = directive.dst

            if directive.orientation is not None:
                sSide: str
                dSide: str
                sRow: int
                dRow: int
                sSide, dSide, sRow, dRow = cls._explicitSidesAndRows_structural(
                    directive,
                    leftSignalRows,
                    leftReturnRows,
                    rightSignalRows,
                    rightReturnRows,
                )
                if directive.orientation in {"NS", "SN"}:
                    if directive.orientation == "NS":
                        assert sRow < dRow, (
                            f"internal_wiring {src}:{dst}:NS: source row must be above "
                            f"destination row, got {sRow}>{dRow}"
                        )
                    else:
                        assert sRow > dRow, (
                            f"internal_wiring {src}:{dst}:SN: source row must be below "
                            f"destination row, got {sRow}<{dRow}"
                        )
                    if abs(dRow - sRow) == 2:
                        continue
                    return True

                if sRow == dRow:
                    continue
                return True

            srcIsSignal: bool = src in signalNames
            dstIsSignal: bool = dst in signalNames

            # Explicit right-wall handoff: ret_i -> sig_(i+1), same as the
            # existing implicit sequential continuity.
            if (
                not srcIsSignal
                and dstIsSignal
                and src in rightReturnRows
                and dst in rightSignalRows
                and len(rightReturnRows[src]) == 1
                and len(rightSignalRows[dst]) == 1
                and rightSignalRows[dst][0] == rightReturnRows[src][0] + 2
            ):
                continue

            # Typed straight-through forward pair: left signal -> right signal.
            if (
                srcIsSignal
                and dstIsSignal
                and src in leftSignalRows
                and dst in rightSignalRows
                and len(leftSignalRows[src]) == 1
                and len(rightSignalRows[dst]) == 1
                and leftSignalRows[src][0] == rightSignalRows[dst][0]
            ):
                continue

            # Typed straight-through return pair: right return -> left return.
            if (
                not srcIsSignal
                and not dstIsSignal
                and src in rightReturnRows
                and dst in leftReturnRows
                and len(rightReturnRows[src]) == 1
                and len(leftReturnRows[dst]) == 1
                and rightReturnRows[src][0] == leftReturnRows[dst][0]
            ):
                continue

            return True

        return False

    @classmethod
    def leftEndpointDensityHints_compute(
        cls,
        node: Node,
        signalNames: set[str],
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Count left-wall signal and return usage from declared directives."""

        leftSignalRows, leftReturnRows, rightSignalRows, rightReturnRows = (
            cls._basicWallRows_compute(node)
        )
        leftSignalCounts: dict[str, int] = {}
        leftReturnCounts: dict[str, int] = {}

        directive: WiringDirective
        for directive in cls._directive_parse(node):
            src: str = directive.src
            dst: str = directive.dst

            if directive.orientation is not None:
                srcSide: str
                dstSide: str
                _srcRow: int
                _dstRow: int
                srcSide, dstSide, _srcRow, _dstRow = cls._explicitSidesAndRows_structural(
                    directive,
                    leftSignalRows,
                    leftReturnRows,
                    rightSignalRows,
                    rightReturnRows,
                )
                if srcSide == "L" and src in leftSignalRows:
                    leftSignalCounts[src] = leftSignalCounts.get(src, 0) + 1
                if dstSide == "L" and dst in leftReturnRows:
                    leftReturnCounts[dst] = leftReturnCounts.get(dst, 0) + 1
                continue

            if src in signalNames and src in leftSignalRows:
                leftSignalCounts[src] = leftSignalCounts.get(src, 0) + 1
            if dst not in signalNames and dst in leftReturnRows:
                leftReturnCounts[dst] = leftReturnCounts.get(dst, 0) + 1

        return leftSignalCounts, leftReturnCounts

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
        parts: list[str]
        for w in node.internal_wiring:
            if ":" not in w:
                continue
            src: str
            dst: str
            parts = w.split(":")
            src, dst = parts[0], parts[1]
            srcCounts[src] = srcCounts.get(src, 0) + 1
            dstCounts[dst] = dstCounts.get(dst, 0) + 1
        total: int = 0
        for w in node.internal_wiring:
            if ":" not in w:
                continue
            parts = w.split(":")
            src, dst = parts[0], parts[1]
            if src not in rightRetPorts:
                continue
            # Straight-through candidates route as a plain hline — no trunk needed.
            # When passThroughAllowed=False, ALL pairs go through the manifold,
            # so the exclusion must not apply.
            if (config.passThroughAllowed
                    and srcCounts[src] == 1
                    and dstCounts[dst] == 1):
                continue
            total += 1
        return total

    @staticmethod
    def _chipH_compute(
        node: Node, ewOff: int, isExplicit: bool, usesManifoldLayout: bool
    ) -> int:
        """Compute chip height in rows.

        Mirrors chipH_precompute using the pre-resolved ewOff and isExplicit
        so those values are not re-derived from node fields.
        """
        nLeft: int  = len(node.input_ports)
        nRight: int = (
            len(node.output_ports) if node.output_ports else len(node.children)
        )
        if not isExplicit:
            nLeft = 1
        n: int = max(nLeft, nRight)

        if n <= 1:
            if not node.children:
                # True leaf chip — gap row between entry and return needs 7 rows.
                # Minimum: top(1) + label(1) + sep(1) + entry(1) + gap(1)
                #          + return(1) + bottom(1) = 7; ewOff shifts entry down.
                return max(config.baseLeafHeight, 7 + ewOff)
            # Non-leaf single-port chip (parent with one child, no manifold)
            return max(config.baseLeafHeight, 6 + ewOff)

        if not usesManifoldLayout:
            return 3 * n + 3

        spacing: int = config.portVerticalSpacing
        portCounts: dict[str, int] = {}
        wiringCount: int = 0
        parts: list[str]
        for w in node.internal_wiring:
            if ":" not in w:
                continue
            wiringCount += 1
            src: str
            dst: str
            parts = w.split(":")
            src, dst = parts[0], parts[1]
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
        node: Node,
        leftNames: set[str],
        rightNames: set[str],
        usesManifoldLayout: bool,
    ) -> int:
        """Compute chip outer width.

        Mirrors chipOw_compute using the pre-built leftNames/rightNames.
        """
        labelW: int = len(node.func) + config.chipPaddingX * 2

        if not usesManifoldLayout:
            return labelW + 2

        lCounts: dict[str, int] = {}
        parts: list[str]
        for wirePair in node.internal_wiring:
            if ":" not in wirePair:
                continue
            src: str
            dst: str
            parts = wirePair.split(":")
            src, dst = parts[0], parts[1]
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
            parts = wirePair.split(":")
            src, dst = parts[0], parts[1]
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

        maxLeftLabel: int = max(
            (len(_anchor_display(n)) + 1 for n in leftNames  if n in lCounts), default=0
        )
        maxRightLabel: int = max(
            (len(_anchor_display(n)) + 1 for n in rightNames if n in lCounts), default=0
        )

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

    def wiring_side(self, name: str, role: str) -> str:
        """Resolve source/destination wall side using signal-vs-return semantics."""
        isSig: bool = self.is_signal(name)
        if role == "src":
            if isSig and name in self.leftWallRows:
                return "L"
            if not isSig and name in self.rightWallRows:
                return "R"
        else:
            if isSig and name in self.rightWallRows:
                return "R"
            if not isSig and name in self.leftWallRows:
                return "L"

        prefer: str = (
            "L"
            if (role == "src" and isSig) or (role == "dst" and not isSig)
            else "R"
        )
        return self.port_side(name, prefer=prefer)

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
        parentId: object  # PortKey = tuple[int,int] at runtime
        port: object  # Node.Port at runtime
        for parentId, port in node.input_ports.items():
            if port.signal:
                row = entryRows[parentId]
                self.leftSignalRows.setdefault(port.signal, [])
                self.leftWallRows.setdefault(port.signal, [])
                if row not in self.leftSignalRows[port.signal]:
                    self.leftSignalRows[port.signal].append(row)
                if row not in self.leftWallRows[port.signal]:
                    self.leftWallRows[port.signal].append(row)
            if port.ret:
                row = returnRows[parentId]
                self.leftReturnRows.setdefault(port.ret, [])
                self.leftWallRows.setdefault(port.ret, [])
                if row not in self.leftReturnRows[port.ret]:
                    self.leftReturnRows[port.ret].append(row)
                if row not in self.leftWallRows[port.ret]:
                    self.leftWallRows[port.ret].append(row)

        # ── rightWallRows (mirrors chips.py rightBaseRows) ────────────────
        # High-Resolution Rule: only manifold chips use portVerticalSpacing;
        # non-manifold chips always use spacing=3 (matches layout_compute).
        spacing: int = config.portVerticalSpacing if self.usesManifoldLayout else 3
        i: int
        for i, port in enumerate(node.output_ports.values()):
            if port.signal:
                row = y0 + 3 + self.ewOff + spacing * i
                self.rightSignalRows.setdefault(port.signal, [])
                self.rightWallRows.setdefault(port.signal, [])
                if row not in self.rightSignalRows[port.signal]:
                    self.rightSignalRows[port.signal].append(row)
                if row not in self.rightWallRows[port.signal]:
                    self.rightWallRows[port.signal].append(row)
            if port.ret:
                row = y0 + 4 + self.ewOff + spacing * i
                self.rightReturnRows.setdefault(port.ret, [])
                self.rightWallRows.setdefault(port.ret, [])
                if row not in self.rightReturnRows[port.ret]:
                    self.rightReturnRows[port.ret].append(row)
                if row not in self.rightWallRows[port.ret]:
                    self.rightWallRows[port.ret].append(row)

        if not node.internal_wiring:
            self.resolved = True
            return

        # ── Classify wiring pairs (mirrors chips.py section 2.1) ─────────
        # Sort deterministically so render order stays stable.
        allPairsRaw: list[WiringDirective] = sorted(
            self._directive_parse(node),
            key=lambda d: (
                d.src,
                d.dst,
                d.orientation or "",
                "pure" if d.isPure else "",
            ),
        )

        srcCounts: dict[str, int] = {}
        dstCounts: dict[str, int] = {}
        directive: WiringDirective
        for directive in allPairsRaw:
            src = directive.src
            dst = directive.dst
            srcCounts[src] = srcCounts.get(src, 0) + 1
            dstCounts[dst] = dstCounts.get(dst, 0) + 1

        straightDirectiveList: list[WiringDirective] = []
        straightPairsList: list[tuple[str, str]] = []
        wiringDirectiveList: list[WiringDirective] = []
        wiringPairsList:   list[tuple[str, str]] = []

        for directive in allPairsRaw:
            src = directive.src
            dst = directive.dst
            isPure = directive.isPure
            if directive.orientation is not None:
                sSide, dSide, sRow, dRow = self._explicitSidesAndRows_structural(
                    directive,
                    self.leftSignalRows,
                    self.leftReturnRows,
                    self.rightSignalRows,
                    self.rightReturnRows,
                )
            else:
                sSide = self.wiring_side(src, "src")
                dSide = self.wiring_side(dst, "dst")
                sRow = self._wiringRow_get(src, "src", y0)
                dRow = self._wiringRow_get(dst, "dst", y0)

            if directive.orientation in {"NS", "SN"}:
                if directive.orientation == "NS":
                    assert sRow < dRow, (
                        f"internal_wiring {src}:{dst}:NS: source row must be above "
                        f"destination row, got {sRow}>{dRow}"
                    )
                else:
                    assert sRow > dRow, (
                        f"internal_wiring {src}:{dst}:SN: source row must be below "
                        f"destination row, got {sRow}<{dRow}"
                    )
                if abs(dRow - sRow) == 2:
                    self.wallContinuities.append(
                        WallContinuity(
                            side=sSide,
                            src=src,
                            dst=dst,
                            srcRow=sRow,
                            dstRow=dRow,
                            isPure=isPure,
                        )
                    )
                    continue
                wiringPairsList.append((src, dst))
                continue

            if (
                sSide == dSide == "R"
                and not self.is_signal(src)
                and self.is_signal(dst)
                and dRow == sRow + 2
            ):
                self.wallContinuities.append(
                    WallContinuity(
                        side="R",
                        src=src,
                        dst=dst,
                        srcRow=sRow,
                        dstRow=dRow,
                        isPure=isPure,
                    )
                )
                continue

            if (
                sSide != dSide
                and srcCounts.get(src, 0) == 1
                and dstCounts.get(dst, 0) == 1
                and sRow == dRow
            ):
                straightPairsList.append((src, dst))
                straightDirectiveList.append(directive)
                if isPure:
                    self.purePairs.add((src, dst))
                continue
            wiringDirectiveList.append(directive)
            wiringPairsList.append((src, dst))

        self.straightDirectives = straightDirectiveList
        self.straightPairs = straightPairsList
        self.wiringDirectives = wiringDirectiveList
        self.wiringPairs   = wiringPairsList

        if not wiringPairsList:
            self.resolved = True
            return

        # ── lCounts (manifold-only, mirrors chips.py section 2.4) ────────
        for directive in wiringDirectiveList:
            srcKey: str
            dstKey: str
            srcKey, dstKey = self.directive_endpointKeys(directive)
            self.lCounts[srcKey] = self.lCounts.get(srcKey, 0) + 1
            self.lCounts[dstKey] = self.lCounts.get(dstKey, 0) + 1

        # ── portToX, zone boundaries (mirrors chips.py section 2.4) ──────
        x0: int = node.x
        rx: int = x0 + node.ow - 1

        leftPorts: list[str] = sorted(
            p for p in self.lCounts if self.endpoint_side(p) == "L"
        )
        rightPorts: list[str] = sorted(
            p for p in self.lCounts if self.endpoint_side(p) == "R"
        )

        maxLeftLabel: int = max(
            (len(_anchor_display(self.endpoint_display(p))) + 1 for p in leftPorts),
            default=0,
        )
        maxRightLabel: int = max(
            (len(_anchor_display(self.endpoint_display(p))) + 1 for p in rightPorts),
            default=0,
        )
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
            wallRow: int  = self.endpoint_wallRow(p)
            isSig: bool   = self.endpoint_isSignal(p)
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
                    self.allAnchorRows[p] = [self.endpoint_wallRow(p)]

        self.resolved = True

    # ── Internal helpers ──────────────────────────────────────────────────

    def _wallRow_get(self, port: str, y0: int) -> int:
        """Return the wall row for a port (from leftWallRows or rightWallRows)."""
        side: str = self.port_side(port)
        base = self.leftWallRows if side == "L" else self.rightWallRows
        return (base.get(port) or [y0 + 3])[0]

    def _wiringRow_get(self, name: str, role: str, y0: int) -> int:
        """Resolve a source/destination wall row during or after Stage 2."""
        side: str = self.wiring_side(name, role)
        base = self.leftWallRows if side == "L" else self.rightWallRows
        return (base.get(name) or [y0 + 3])[0]

    def directive_endpoints(
        self, directive: WiringDirective
    ) -> tuple[str, str, int, int]:
        """Resolve source/destination sides and rows for a parsed directive."""
        if directive.orientation is not None:
            return self._explicitSidesAndRows_structural(
                directive,
                self.leftSignalRows,
                self.leftReturnRows,
                self.rightSignalRows,
                self.rightReturnRows,
            )

        src: str = directive.src
        dst: str = directive.dst
        return (
            self.wiring_side(src, "src"),
            self.wiring_side(dst, "dst"),
            self._wiringRow_get(src, "src", self.y0),
            self._wiringRow_get(dst, "dst", self.y0),
        )

    def directive_endpointKeys(self, directive: WiringDirective) -> tuple[str, str]:
        """Return manifold-internal endpoint keys for a directive."""
        srcSide: str
        dstSide: str
        _srcRow: int
        _dstRow: int
        srcSide, dstSide, _srcRow, _dstRow = self.directive_endpoints(directive)

        if directive.orientation == "WE":
            srcKind = "sig"
            dstKind = "sig"
        elif directive.orientation == "EW":
            srcKind = "ret"
            dstKind = "ret"
        elif directive.orientation in {"NS", "SN"}:
            if srcSide == "R":
                srcKind = "ret"
                dstKind = "sig"
            else:
                srcKind = "sig"
                dstKind = "ret"
        else:
            srcKind = (
                "sig"
                if srcSide == "L" and self.is_signal(directive.src)
                else "ret"
            )
            dstKind = (
                "sig"
                if dstSide == "R" and self.is_signal(directive.dst)
                else "ret"
            )

        return (
            _endpoint_key(directive.src, srcSide, srcKind),
            _endpoint_key(directive.dst, dstSide, dstKind),
        )

    def endpoint_side(self, endpointKey: str) -> str:
        """Return wall side from a manifold endpoint key."""
        return endpointKey.split("|", 2)[0]

    def endpoint_kind(self, endpointKey: str) -> str:
        """Return endpoint kind ('sig' or 'ret') from a manifold endpoint key."""
        return endpointKey.split("|", 2)[1]

    def endpoint_display(self, endpointKey: str) -> str:
        """Return the visible label from a manifold endpoint key."""
        return endpointKey.split("|", 2)[2]

    def endpoint_isSignal(self, endpointKey: str) -> bool:
        """True if endpoint key is a signal endpoint."""
        return self.endpoint_kind(endpointKey) == "sig"

    def endpoint_wallRow(self, endpointKey: str) -> int:
        """Return the concrete wall row for a manifold endpoint key."""
        side: str = self.endpoint_side(endpointKey)
        kind: str = self.endpoint_kind(endpointKey)
        label: str = self.endpoint_display(endpointKey)
        if side == "L" and kind == "sig":
            return self.leftSignalRows[label][0]
        if side == "L" and kind == "ret":
            return self.leftReturnRows[label][0]
        if side == "R" and kind == "sig":
            return self.rightSignalRows[label][0]
        return self.rightReturnRows[label][0]

    def wall_row(self, name: str) -> int:
        """Return the absolute wall row for a port name. Requires Stage 2."""
        if not self.resolved:
            raise RuntimeError("wall_row() requires Stage 2: call resolve() first")
        if "|" in name:
            return self.endpoint_wallRow(name)
        return self._wallRow_get(name, self.y0)

    def wiring_row(self, name: str, role: str) -> int:
        """Return the source/destination wall row using typed side resolution."""
        if not self.resolved:
            raise RuntimeError("wiring_row() requires Stage 2: call resolve() first")
        return self._wiringRow_get(name, role, self.y0)
