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


def _base36_2digit(index: int) -> str:
    """Return a stable minimum-2-digit base36 token for alias generation."""
    digits: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    value: int = index
    chars: list[str] = []
    while value > 0:
        value, rem = divmod(value, 36)
        chars.append(digits[rem])
    token: str = "".join(reversed(chars or ["0"]))
    return token.rjust(2, "0")


def _internal_labelShown(
    count: int, showInternalLabels: bool, passThroughAllowed: bool
) -> bool:
    """True when a manifold endpoint should draw an internal anchor label."""
    if not showInternalLabels:
        return False
    return not (passThroughAllowed and count == 1)


def _internal_labelWidth(
    displayName: str,
    count: int,
    showInternalLabels: bool,
    aliasInternalLabels: bool,
    passThroughAllowed: bool,
) -> int:
    """Return width reserved for one visible internal label, including arrow."""
    if not _internal_labelShown(count, showInternalLabels, passThroughAllowed):
        return 0
    if aliasInternalLabels:
        return 4
    return len(_anchor_display(displayName)) + 1


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


@dataclass(frozen=True)
class DirectivePlacement:
    """Resolved directive endpoints with wall, row, and endpoint-kind identity."""

    directive: WiringDirective
    srcSide: str
    dstSide: str
    srcRow: int
    dstRow: int
    srcKind: str
    dstKind: str

    @property
    def srcKey(self) -> str:
        """Return the source endpoint key used by manifold routing."""
        return _endpoint_key(self.directive.src, self.srcSide, self.srcKind)

    @property
    def dstKey(self) -> str:
        """Return the destination endpoint key used by manifold routing."""
        return _endpoint_key(self.directive.dst, self.dstSide, self.dstKind)


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
    internalWireColorize: bool = True
    showInternalLabels: bool = True
    aliasInternalLabels: bool = False

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
    internalLabelAliases: dict[str, str]   = field(default_factory=dict)

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
        geo.internalWireColorize = node.internalWireColorizeResolved
        geo.showInternalLabels = node.showInternalLabelsResolved
        geo.aliasInternalLabels = node.aliasInternalLabelsResolved

        geo.usesManifoldLayout = cls._usesManifoldLayout_compute(
            node, geo.isExplicit, geo.signalNames
        )
        geo.ewOff  = cls._ewOff_compute(node)
        geo.chipH  = cls._chipH_compute(
            node, geo.ewOff, geo.isExplicit, geo.usesManifoldLayout
        )
        geo.chipOw = cls._chipOw_compute(
            node, geo.usesManifoldLayout
        )
        return geo

    # ── Stage 1 helpers ───────────────────────────────────────────────────

    @staticmethod
    def _portSide_resolve(
        name: str,
        prefer: str,
        leftRows: dict[str, list[int]],
        rightRows: dict[str, list[int]],
    ) -> str:
        """Resolve a wall side from row maps, falling back to the preferred side."""
        inL: bool = name in leftRows
        inR: bool = name in rightRows
        if inL and not inR:
            return "L"
        if inR and not inL:
            return "R"
        return prefer

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

    @staticmethod
    def _implicitSidesAndRows_structural(
        directive: WiringDirective,
        signalNames: set[str],
        leftSignalRows: dict[str, list[int]],
        leftReturnRows: dict[str, list[int]],
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> tuple[str, str, int, int]:
        """Resolve structural endpoints for an un-oriented directive."""

        src: str = directive.src
        dst: str = directive.dst
        srcIsSignal: bool = src in signalNames
        dstIsSignal: bool = dst in signalNames

        if srcIsSignal:
            srcSide: str = ChipGeometry._portSide_resolve(
                src, "L", leftSignalRows, rightSignalRows
            )
            srcRows = leftSignalRows if srcSide == "L" else rightSignalRows
        else:
            srcSide = ChipGeometry._portSide_resolve(
                src, "R", leftReturnRows, rightReturnRows
            )
            srcRows = leftReturnRows if srcSide == "L" else rightReturnRows

        if dstIsSignal:
            dstSide: str = ChipGeometry._portSide_resolve(
                dst, "R", leftSignalRows, rightSignalRows
            )
            dstRows = leftSignalRows if dstSide == "L" else rightSignalRows
        else:
            dstSide = ChipGeometry._portSide_resolve(
                dst, "L", leftReturnRows, rightReturnRows
            )
            dstRows = leftReturnRows if dstSide == "L" else rightReturnRows

        return (
            srcSide,
            dstSide,
            (srcRows.get(src) or [0])[0],
            (dstRows.get(dst) or [0])[0],
        )

    @classmethod
    def _directiveCounts_compute(
        cls,
        directives: list[WiringDirective],
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Count how often each label appears as a source or destination."""
        srcCounts: dict[str, int] = {}
        dstCounts: dict[str, int] = {}
        directive: WiringDirective
        for directive in directives:
            srcCounts[directive.src] = srcCounts.get(directive.src, 0) + 1
            dstCounts[directive.dst] = dstCounts.get(directive.dst, 0) + 1
        return srcCounts, dstCounts

    @staticmethod
    def _directiveKinds_compute(
        directive: WiringDirective,
        signalNames: set[str],
        srcSide: str,
        dstSide: str,
    ) -> tuple[str, str]:
        """Resolve manifold endpoint kinds for one directive."""
        if directive.orientation == "WE":
            return "sig", "sig"
        if directive.orientation == "EW":
            return "ret", "ret"
        if directive.orientation in {"NS", "SN"}:
            if srcSide == "R":
                return "ret", "sig"
            return "sig", "ret"

        srcKind: str = (
            "sig"
            if srcSide == "L" and directive.src in signalNames
            else "ret"
        )
        dstKind: str = (
            "sig"
            if dstSide == "R" and directive.dst in signalNames
            else "ret"
        )
        return srcKind, dstKind

    @classmethod
    def _directivePlacement_structural(
        cls,
        directive: WiringDirective,
        signalNames: set[str],
        leftSignalRows: dict[str, list[int]],
        leftReturnRows: dict[str, list[int]],
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> DirectivePlacement:
        """Resolve structural rows and endpoint kinds for one directive."""
        srcSide: str
        dstSide: str
        srcRow: int
        dstRow: int
        if directive.orientation is not None:
            srcSide, dstSide, srcRow, dstRow = cls._explicitSidesAndRows_structural(
                directive,
                leftSignalRows,
                leftReturnRows,
                rightSignalRows,
                rightReturnRows,
            )
        else:
            srcSide, dstSide, srcRow, dstRow = cls._implicitSidesAndRows_structural(
                directive,
                signalNames,
                leftSignalRows,
                leftReturnRows,
                rightSignalRows,
                rightReturnRows,
            )

        srcKind: str
        dstKind: str
        srcKind, dstKind = cls._directiveKinds_compute(
            directive,
            signalNames,
            srcSide,
            dstSide,
        )
        return DirectivePlacement(
            directive=directive,
            srcSide=srcSide,
            dstSide=dstSide,
            srcRow=srcRow,
            dstRow=dstRow,
            srcKind=srcKind,
            dstKind=dstKind,
        )

    @classmethod
    def _directiveClassification_get(
        cls,
        placement: DirectivePlacement,
        srcCounts: dict[str, int],
        dstCounts: dict[str, int],
    ) -> str:
        """Classify one resolved directive as wall continuity, straight, or manifold."""
        directive: WiringDirective = placement.directive
        if directive.orientation in {"NS", "SN"}:
            cls._sameWallOrientation_validate(
                directive,
                placement.srcRow,
                placement.dstRow,
            )
            return (
                "wall"
                if abs(placement.dstRow - placement.srcRow) == 2
                else "manifold"
            )

        if (
            directive.orientation is None
            and placement.srcSide == placement.dstSide == "R"
            and placement.srcKind == "ret"
            and placement.dstKind == "sig"
            and placement.dstRow == placement.srcRow + 2
        ):
            return "wall"

        if (
            placement.srcSide != placement.dstSide
            and srcCounts.get(directive.src, 0) == 1
            and dstCounts.get(directive.dst, 0) == 1
            and placement.srcRow == placement.dstRow
        ):
            return "straight"

        return "manifold"

    @staticmethod
    def _endpointCounts_increment(
        endpointCounts: dict[str, int],
        placement: DirectivePlacement,
    ) -> None:
        """Add one manifold directive's endpoint usage to the aggregate counts."""
        endpointCounts[placement.srcKey] = endpointCounts.get(placement.srcKey, 0) + 1
        endpointCounts[placement.dstKey] = endpointCounts.get(placement.dstKey, 0) + 1

    @staticmethod
    def _wallContinuity_build(placement: DirectivePlacement) -> WallContinuity:
        """Build a same-wall continuity record from a resolved directive placement."""
        directive: WiringDirective = placement.directive
        return WallContinuity(
            side=placement.srcSide,
            src=directive.src,
            dst=directive.dst,
            srcRow=placement.srcRow,
            dstRow=placement.dstRow,
            isPure=directive.isPure,
        )

    @classmethod
    def _manifoldEndpointCounts_structural(
        cls,
        node: Node,
        signalNames: set[str],
    ) -> dict[str, int]:
        """Approximate manifold-only endpoint counts before Stage 2 resolve."""
        (
            leftSignalRows,
            leftReturnRows,
            rightSignalRows,
            rightReturnRows,
        ) = cls._basicWallRows_compute(node)
        directives: list[WiringDirective] = cls._directive_parse(node)
        srcCounts: dict[str, int]
        dstCounts: dict[str, int]
        srcCounts, dstCounts = cls._directiveCounts_compute(directives)

        endpointCounts: dict[str, int] = {}
        directive: WiringDirective
        for directive in directives:
            placement: DirectivePlacement = cls._directivePlacement_structural(
                directive,
                signalNames,
                leftSignalRows,
                leftReturnRows,
                rightSignalRows,
                rightReturnRows,
            )
            if (
                cls._directiveClassification_get(
                    placement,
                    srcCounts,
                    dstCounts,
                )
                != "manifold"
            ):
                continue
            cls._endpointCounts_increment(endpointCounts, placement)

        return endpointCounts

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

        leftSignalRows, leftReturnRows, rightSignalRows, rightReturnRows = (
            cls._basicWallRows_compute(node)
        )

        directive: WiringDirective
        for directive in cls._directive_parse(node):
            if cls._directiveNeedsManifold_compute(
                directive,
                signalNames,
                leftSignalRows,
                leftReturnRows,
                rightSignalRows,
                rightReturnRows,
            ):
                return True

        return False

    @classmethod
    def _directiveNeedsManifold_compute(
        cls,
        directive: WiringDirective,
        signalNames: set[str],
        leftSignalRows: dict[str, list[int]],
        leftReturnRows: dict[str, list[int]],
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> bool:
        """True when one directive cannot use compact non-manifold geometry."""
        if directive.orientation is not None:
            return cls._orientedDirectiveNeedsManifold_compute(
                directive,
                leftSignalRows,
                leftReturnRows,
                rightSignalRows,
                rightReturnRows,
            )

        return cls._implicitDirectiveNeedsManifold_compute(
            directive,
            signalNames,
            leftSignalRows,
            leftReturnRows,
            rightSignalRows,
            rightReturnRows,
        )

    @classmethod
    def _orientedDirectiveNeedsManifold_compute(
        cls,
        directive: WiringDirective,
        leftSignalRows: dict[str, list[int]],
        leftReturnRows: dict[str, list[int]],
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> bool:
        """Return whether an explicitly oriented directive exceeds compact geometry."""
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
            cls._sameWallOrientation_validate(directive, sRow, dRow)
            return abs(dRow - sRow) != 2
        return sRow != dRow

    @classmethod
    def _implicitDirectiveNeedsManifold_compute(
        cls,
        directive: WiringDirective,
        signalNames: set[str],
        leftSignalRows: dict[str, list[int]],
        leftReturnRows: dict[str, list[int]],
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> bool:
        """Return whether an implicit directive exceeds compact geometry."""
        src: str = directive.src
        dst: str = directive.dst
        srcIsSignal: bool = src in signalNames
        dstIsSignal: bool = dst in signalNames

        if cls._rightWallHandoff_matches(
            src,
            dst,
            srcIsSignal,
            dstIsSignal,
            rightSignalRows,
            rightReturnRows,
        ):
            return False

        return not cls._crossWallStraight_matches(
            src,
            dst,
            srcIsSignal,
            dstIsSignal,
            leftSignalRows,
            leftReturnRows,
            rightSignalRows,
            rightReturnRows,
        )

    def _manifoldLabelWidths_compute(
        self,
        leftPorts: list[str],
        rightPorts: list[str],
    ) -> tuple[int, int]:
        """Return maximum visible internal label widths on each manifold wall."""
        maxLeftLabel: int = max(
            (
                _internal_labelWidth(
                    self.endpoint_display(port),
                    self.lCounts[port],
                    self.showInternalLabels,
                    self.aliasInternalLabels,
                    config.passThroughAllowed,
                )
                for port in leftPorts
            ),
            default=0,
        )
        maxRightLabel: int = max(
            (
                _internal_labelWidth(
                    self.endpoint_display(port),
                    self.lCounts[port],
                    self.showInternalLabels,
                    self.aliasInternalLabels,
                    config.passThroughAllowed,
                )
                for port in rightPorts
            ),
            default=0,
        )
        return maxLeftLabel, maxRightLabel

    def _longitudeColumns_assign(
        self,
        leftPorts: list[str],
        rightPorts: list[str],
        leftLongStart: int,
        rightLongStart: int,
    ) -> tuple[int, int]:
        """Assign manifold longitude columns and return left/right track totals."""
        vTrackL: int = 0
        port: str
        for port in leftPorts:
            self.portToX[port] = leftLongStart + 2 * vTrackL
            vTrackL += self.lCounts[port]

        vTrackR: int = 0
        for port in rightPorts:
            self.portToX[port] = (
                rightLongStart - 2 * (vTrackR + self.lCounts[port] - 1)
            )
            vTrackR += self.lCounts[port]
        return vTrackL, vTrackR

    @staticmethod
    def _sameWallOrientation_validate(
        directive: WiringDirective, srcRow: int, dstRow: int
    ) -> None:
        """Validate the relative row ordering for explicit `NS` and `SN` directives."""
        src: str = directive.src
        dst: str = directive.dst
        if directive.orientation == "NS":
            assert srcRow < dstRow, (
                f"internal_wiring {src}:{dst}:NS: source row must be above "
                f"destination row, got {srcRow}>{dstRow}"
            )
            return
        assert srcRow > dstRow, (
            f"internal_wiring {src}:{dst}:SN: source row must be below "
            f"destination row, got {srcRow}<{dstRow}"
        )

    @staticmethod
    def _rightWallHandoff_matches(
        src: str,
        dst: str,
        srcIsSignal: bool,
        dstIsSignal: bool,
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> bool:
        """True when the directive matches the legacy implicit right-wall handoff."""
        return (
            not srcIsSignal
            and dstIsSignal
            and src in rightReturnRows
            and dst in rightSignalRows
            and len(rightReturnRows[src]) == 1
            and len(rightSignalRows[dst]) == 1
            and rightSignalRows[dst][0] == rightReturnRows[src][0] + 2
        )

    @staticmethod
    def _crossWallStraight_matches(
        src: str,
        dst: str,
        srcIsSignal: bool,
        dstIsSignal: bool,
        leftSignalRows: dict[str, list[int]],
        leftReturnRows: dict[str, list[int]],
        rightSignalRows: dict[str, list[int]],
        rightReturnRows: dict[str, list[int]],
    ) -> bool:
        """True when the directive matches one of the compact straight-through cases."""
        if (
            srcIsSignal
            and dstIsSignal
            and src in leftSignalRows
            and dst in rightSignalRows
            and len(leftSignalRows[src]) == 1
            and len(rightSignalRows[dst]) == 1
            and leftSignalRows[src][0] == rightSignalRows[dst][0]
        ):
            return True

        return (
            not srcIsSignal
            and not dstIsSignal
            and src in rightReturnRows
            and dst in leftReturnRows
            and len(rightReturnRows[src]) == 1
            and len(leftReturnRows[dst]) == 1
            and rightReturnRows[src][0] == leftReturnRows[dst][0]
        )

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
                (
                    srcSide,
                    dstSide,
                    _srcRow,
                    _dstRow,
                ) = cls._explicitSidesAndRows_structural(
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
        directives: list[WiringDirective] = ChipGeometry._directive_parse(node)
        srcCounts: dict[str, int]
        dstCounts: dict[str, int]
        srcCounts, dstCounts = ChipGeometry._directiveCounts_compute(directives)
        total: int = 0
        directive: WiringDirective
        for directive in directives:
            src: str = directive.src
            dst: str = directive.dst
            if src not in rightRetPorts:
                continue
            # Straight-through candidates route as a plain hline — no trunk needed.
            # When passThroughAllowed=False, ALL pairs go through the manifold,
            # so the exclusion must not apply.
            if (
                config.passThroughAllowed
                and srcCounts[src] == 1
                and dstCounts[dst] == 1
            ):
                continue
            total += 1
        return total

    @staticmethod
    def _wallPortCount_compute(node: Node, isExplicit: bool) -> int:
        """Return the dominant wall port count used by chip-height formulas."""
        nLeft: int = len(node.input_ports)
        nRight: int = (
            len(node.output_ports) if node.output_ports else len(node.children)
        )
        if not isExplicit:
            nLeft = 1
        return max(nLeft, nRight)

    @staticmethod
    def _singlePortChipHeight_compute(node: Node, ewOff: int) -> int:
        """Return the compact chip height for leaf and single-port chips."""
        if not node.children:
            return max(config.baseLeafHeight, 7 + ewOff)
        return max(config.baseLeafHeight, 6 + ewOff)

    @staticmethod
    def _manifoldPortCounts_compute(node: Node) -> tuple[dict[str, int], int]:
        """Return manifold endpoint densities and declared directive count."""
        portCounts: dict[str, int] = {}
        directives: list[WiringDirective] = ChipGeometry._directive_parse(node)
        directive: WiringDirective
        for directive in directives:
            portCounts[directive.src] = portCounts.get(directive.src, 0) + 1
            portCounts[directive.dst] = portCounts.get(directive.dst, 0) + 1
        return portCounts, len(directives)

    @staticmethod
    def _explicitManifoldHeight_compute(
        ewOff: int,
        nPorts: int,
        maxPortDensity: int,
        wiringCount: int,
    ) -> int:
        """Return explicit-input manifold height from density and directive counts."""
        spacing: int = config.portVerticalSpacing
        lastWallReturnOffset: int = 3 + ewOff + spacing * (nPorts - 1) + 1
        return lastWallReturnOffset + maxPortDensity + wiringCount + 2

    @staticmethod
    def _sovereignManifoldHeight_compute(
        node: Node,
        ewOff: int,
        nPorts: int,
        portCounts: dict[str, int],
    ) -> int:
        """Return sovereign-input manifold height from right density and WE trunks."""
        spacing: int = config.portVerticalSpacing
        leftNames: set[str] = {
            nm
            for port in node.input_ports.values()
            for nm in (port.signal, port.ret)
            if nm
        }
        lastWallReturnOffset: int = 3 + ewOff + spacing * (nPorts - 1) + 1
        maxRightDensity: int = max(
            (cnt for prt, cnt in portCounts.items() if prt not in leftNames),
            default=0,
        )
        weTrunkCount: int = sum(
            1
            for directive in ChipGeometry._directive_parse(node)
            if directive.src in leftNames
        )
        return lastWallReturnOffset + maxRightDensity + weTrunkCount + 2

    @staticmethod
    def _chipH_compute(
        node: Node, ewOff: int, isExplicit: bool, usesManifoldLayout: bool
    ) -> int:
        """Compute chip height in rows.

        Mirrors chipH_precompute using the pre-resolved ewOff and isExplicit
        so those values are not re-derived from node fields.
        """
        n: int = ChipGeometry._wallPortCount_compute(node, isExplicit)

        if n <= 1:
            return ChipGeometry._singlePortChipHeight_compute(node, ewOff)

        if not usesManifoldLayout:
            return 3 * n + 3

        portCounts: dict[str, int]
        wiringCount: int
        portCounts, wiringCount = ChipGeometry._manifoldPortCounts_compute(node)
        maxPortDensity: int = max(portCounts.values(), default=0)

        if not isExplicit:
            h: int = ChipGeometry._sovereignManifoldHeight_compute(
                node,
                ewOff,
                n,
                portCounts,
            )
            return max(config.baseLeafHeight, h)

        h = ChipGeometry._explicitManifoldHeight_compute(
            ewOff,
            n,
            maxPortDensity,
            wiringCount,
        )
        return max(config.baseLeafHeight, h)

    @staticmethod
    def _endpointCountsBySide_compute(
        endpointCounts: dict[str, int],
    ) -> tuple[int, int]:
        """Return total left and right manifold endpoint density."""
        vLeft: int = sum(
            cnt
            for endpointKey, cnt in endpointCounts.items()
            if endpointKey.startswith("L|")
        )
        vRight: int = sum(
            cnt
            for endpointKey, cnt in endpointCounts.items()
            if endpointKey.startswith("R|")
        )
        return vLeft, vRight

    @staticmethod
    def _endpointLabelWidthMax_compute(
        endpointCounts: dict[str, int],
        side: str,
        showInternalLabels: bool,
        aliasInternalLabels: bool,
    ) -> int:
        """Return the maximum visible label width for one manifold wall side."""
        return max(
            (
                _internal_labelWidth(
                    endpointKey.split("|", 2)[2],
                    cnt,
                    showInternalLabels,
                    aliasInternalLabels,
                    config.passThroughAllowed,
                )
                for endpointKey, cnt in endpointCounts.items()
                if endpointKey.startswith(f"{side}|")
            ),
            default=0,
        )

    @staticmethod
    def _chipOw_compute(
        node: Node,
        usesManifoldLayout: bool,
    ) -> int:
        """Compute chip outer width.

        Mirrors chipOw_compute using the pre-built leftNames/rightNames.
        """
        labelW: int = len(node.func) + config.chipPaddingX * 2

        if not usesManifoldLayout:
            return labelW + 2

        endpointCounts: dict[str, int] = (
            ChipGeometry._manifoldEndpointCounts_structural(
                node,
                {
                    port.signal
                    for ports_dict in (node.input_ports, node.output_ports)
                    for port in ports_dict.values()
                    if port.signal
                },
            )
        )
        if not endpointCounts:
            return labelW + 2

        vLeft: int
        vRight: int
        vLeft, vRight = ChipGeometry._endpointCountsBySide_compute(endpointCounts)
        maxLeftLabel: int = ChipGeometry._endpointLabelWidthMax_compute(
            endpointCounts,
            "L",
            node.showInternalLabelsResolved,
            node.aliasInternalLabelsResolved,
        )
        maxRightLabel: int = ChipGeometry._endpointLabelWidthMax_compute(
            endpointCounts,
            "R",
            node.showInternalLabelsResolved,
            node.aliasInternalLabelsResolved,
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

    def _leftWallRows_resolve(
        self,
        node: Node,
        entryRows: dict[int, int],
        returnRows: dict[int, int],
    ) -> None:
        """Populate left-wall signal/return row maps from bound parent keys."""
        parentId: object
        port: object
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

    def _rightWallRows_resolve(self, node: Node, y0: int) -> None:
        """Populate right-wall signal/return row maps from output occurrence order."""
        spacing: int = config.portVerticalSpacing if self.usesManifoldLayout else 3
        idx: int
        port: object
        for idx, port in enumerate(node.output_ports.values()):
            if port.signal:
                row = y0 + 3 + self.ewOff + spacing * idx
                self.rightSignalRows.setdefault(port.signal, [])
                self.rightWallRows.setdefault(port.signal, [])
                if row not in self.rightSignalRows[port.signal]:
                    self.rightSignalRows[port.signal].append(row)
                if row not in self.rightWallRows[port.signal]:
                    self.rightWallRows[port.signal].append(row)
            if port.ret:
                row = y0 + 4 + self.ewOff + spacing * idx
                self.rightReturnRows.setdefault(port.ret, [])
                self.rightWallRows.setdefault(port.ret, [])
                if row not in self.rightReturnRows[port.ret]:
                    self.rightReturnRows[port.ret].append(row)
                if row not in self.rightWallRows[port.ret]:
                    self.rightWallRows[port.ret].append(row)

    def _directiveLists_resolve(self, node: Node) -> None:
        """Classify directives into straight-through, same-wall, and manifold lists."""
        allPairsRaw: list[WiringDirective] = sorted(
            self._directive_parse(node),
            key=lambda d: (
                d.src,
                d.dst,
                d.orientation or "",
                "pure" if d.isPure else "",
            ),
        )

        srcCounts: dict[str, int]
        dstCounts: dict[str, int]
        srcCounts, dstCounts = self._directiveCounts_compute(allPairsRaw)

        straightDirectiveList: list[WiringDirective] = []
        straightPairsList: list[tuple[str, str]] = []
        wiringDirectiveList: list[WiringDirective] = []
        wiringPairsList: list[tuple[str, str]] = []

        directive: WiringDirective
        for directive in allPairsRaw:
            placement: DirectivePlacement = self._directivePlacement_resolve(directive)
            classification: str = self._directiveClassification_get(
                placement,
                srcCounts,
                dstCounts,
            )
            if classification == "wall":
                self.wallContinuities.append(self._wallContinuity_build(placement))
                continue
            if classification == "straight":
                straightPairsList.append((directive.src, directive.dst))
                straightDirectiveList.append(directive)
                if directive.isPure:
                    self.purePairs.add((directive.src, directive.dst))
                continue

            wiringDirectiveList.append(directive)
            wiringPairsList.append((directive.src, directive.dst))

        self.straightDirectives = straightDirectiveList
        self.straightPairs = straightPairsList
        self.wiringDirectives = wiringDirectiveList
        self.wiringPairs = wiringPairsList

    def _manifoldCounts_resolve(self) -> None:
        """Resolve manifold endpoint densities from classified wiring directives."""
        directive: WiringDirective
        for directive in self.wiringDirectives:
            placement: DirectivePlacement = self._directivePlacement_resolve(directive)
            self._endpointCounts_increment(self.lCounts, placement)

    def _manifoldLongitudes_resolve(self, node: Node) -> None:
        """Assign longitudinal columns and zone boundaries for manifold endpoints."""
        x0: int = node.x
        rx: int = x0 + node.ow - 1
        leftPorts: list[str] = sorted(
            port for port in self.lCounts if self.endpoint_side(port) == "L"
        )
        rightPorts: list[str] = sorted(
            port for port in self.lCounts if self.endpoint_side(port) == "R"
        )

        maxLeftLabel: int
        maxRightLabel: int
        maxLeftLabel, maxRightLabel = self._manifoldLabelWidths_compute(
            leftPorts,
            rightPorts,
        )
        leftLongStart: int = x0 + 4 + maxLeftLabel
        rightLongStart: int = rx - 4 - maxRightLabel

        vTrackL: int
        vTrackR: int
        vTrackL, vTrackR = self._longitudeColumns_assign(
            leftPorts,
            rightPorts,
            leftLongStart,
            rightLongStart,
        )

        self.leftZoneInnerX = leftLongStart + 2 * vTrackL
        self.rightZoneInnerX = rightLongStart + 2 - 2 * vTrackR

    def _anchorRows_resolve(self) -> None:
        """Assign anchor rows for each manifold endpoint from wall rows and density."""
        port: str
        for port in self.lCounts:
            density: int = self.lCounts[port]
            wallRow: int = self.endpoint_wallRow(port)
            isSig: bool = self.endpoint_isSignal(port)
            rows: list[int]
            if isSig:
                rows = [wallRow - 1 - step for step in range(density)]
                if rows and min(rows) < self.anchorFloor:
                    rows = [wallRow + 1 + step for step in range(density)]
            else:
                rows = [wallRow + 1 + step for step in range(density)]
                if rows and max(rows) > self.interiorMax:
                    rows = [wallRow - 1 - step for step in range(density)]
            rows = [max(self.anchorFloor, min(self.interiorMax, row)) for row in rows]
            self.allAnchorRows[port] = rows

    def _unitPorts_apply(self) -> None:
        """Collapse single-density endpoints to wall-flush pass-through anchors."""
        if config.passThroughAllowed:
            port: str
            for port in self.lCounts:
                if self.lCounts[port] == 1:
                    self.unitPorts.add(port)
                    self.allAnchorRows[port] = [self.endpoint_wallRow(port)]

    def _manifoldGeometry_resolve(self, node: Node) -> None:
        """Resolve manifold-only endpoint counts, tracks, and anchor rows."""
        if not self.wiringPairs:
            return

        self._manifoldCounts_resolve()
        self._manifoldLongitudes_resolve(node)
        self._anchorRows_resolve()
        self._unitPorts_apply()

        self.internalLabelAliases.clear()
        if self.showInternalLabels and self.aliasInternalLabels:
            self._internalAliases_resolve()

    def _internalAliases_resolve(self) -> None:
        """Assign stable compact aliases to visible internal labels."""
        aliasGroups: list[tuple[str, str, str]] = [
            ("L", "sig", "i"),
            ("L", "ret", "o"),
            ("R", "sig", "c"),
            ("R", "ret", "r"),
        ]
        side: str
        kind: str
        prefix: str
        for side, kind, prefix in aliasGroups:
            endpoints: list[str] = sorted(
                port
                for port in self.lCounts
                if self.endpoint_side(port) == side
                and self.endpoint_kind(port) == kind
                and _internal_labelShown(
                    self.lCounts[port],
                    self.showInternalLabels,
                    config.passThroughAllowed,
                )
            )
            idx: int
            endpointKey: str
            for idx, endpointKey in enumerate(endpoints, start=1):
                self.internalLabelAliases[endpointKey] = (
                    f"{prefix}{_base36_2digit(idx)}"
                )

    def resolve(
        self,
        node: Node,
        y0: int,
        entryRows: dict[int, int],
        returnRows: dict[int, int],
    ) -> None:
        """Compute all positional geometry once y is known.

        Must be called after layout_compute has assigned y, entryRows, and
        returnRows so downstream rendering can read authoritative geometry
        without recomputing any chip-local state.
        """
        self.y0 = y0
        self.anchorFloor = y0 + 3 + self.ewOff
        self.interiorMax = y0 + self.chipH - 2
        self._leftWallRows_resolve(node, entryRows, returnRows)
        self._rightWallRows_resolve(node, y0)

        if not node.internal_wiring:
            self.resolved = True
            return
        self._directiveLists_resolve(node)
        if not self.wiringPairs:
            self.resolved = True
            return
        self._manifoldGeometry_resolve(node)
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

    def _directivePlacement_resolve(
        self,
        directive: WiringDirective,
    ) -> DirectivePlacement:
        """Resolve one directive against Stage-2 wall rows and endpoint kinds."""
        srcSide: str
        dstSide: str
        srcRow: int
        dstRow: int
        if directive.orientation is not None:
            srcSide, dstSide, srcRow, dstRow = self._explicitSidesAndRows_structural(
                directive,
                self.leftSignalRows,
                self.leftReturnRows,
                self.rightSignalRows,
                self.rightReturnRows,
            )
        else:
            srcSide = self.wiring_side(directive.src, "src")
            dstSide = self.wiring_side(directive.dst, "dst")
            srcRow = self._wiringRow_get(directive.src, "src", self.y0)
            dstRow = self._wiringRow_get(directive.dst, "dst", self.y0)

        srcKind: str
        dstKind: str
        srcKind, dstKind = self._directiveKinds_compute(
            directive,
            self.signalNames,
            srcSide,
            dstSide,
        )
        return DirectivePlacement(
            directive=directive,
            srcSide=srcSide,
            dstSide=dstSide,
            srcRow=srcRow,
            dstRow=dstRow,
            srcKind=srcKind,
            dstKind=dstKind,
        )

    def directive_endpoints(
        self, directive: WiringDirective
    ) -> tuple[str, str, int, int]:
        """Resolve source/destination sides and rows for a parsed directive."""
        placement: DirectivePlacement = self._directivePlacement_resolve(directive)
        return (
            placement.srcSide,
            placement.dstSide,
            placement.srcRow,
            placement.dstRow,
        )

    def directive_endpointKeys(self, directive: WiringDirective) -> tuple[str, str]:
        """Return manifold-internal endpoint keys for a directive."""
        placement: DirectivePlacement = self._directivePlacement_resolve(directive)
        return placement.srcKey, placement.dstKey

    def endpoint_side(self, endpointKey: str) -> str:
        """Return wall side from a manifold endpoint key."""
        return endpointKey.split("|", 2)[0]

    def endpoint_kind(self, endpointKey: str) -> str:
        """Return endpoint kind ('sig' or 'ret') from a manifold endpoint key."""
        return endpointKey.split("|", 2)[1]

    def endpoint_display(self, endpointKey: str) -> str:
        """Return the visible label from a manifold endpoint key."""
        return endpointKey.split("|", 2)[2]

    def endpoint_internalDisplay(self, endpointKey: str) -> str:
        """Return the internal anchor label text for a manifold endpoint key."""
        if self.aliasInternalLabels:
            alias: str | None = self.internalLabelAliases.get(endpointKey)
            if alias is not None:
                return alias
        return _anchor_display(self.endpoint_display(endpointKey))

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
