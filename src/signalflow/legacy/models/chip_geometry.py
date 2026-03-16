"""Define the authoritative chip-interior geometry model.

This module is the geometry source of truth for chip-local rendering. It is
where the renderer decides whether a chip can stay in compact non-manifold
mode, whether it requires manifold layout, how tall and wide the chip must be,
which rows belong to wall ports, and where manifold anchor rows and longitude
columns live once layout has assigned absolute positions.

The module is intentionally split into two stages:

1. Stage 1 structural geometry
   ``ChipGeometry.build_structural()`` computes geometry that does not depend on
   the chip's absolute ``y`` position. This includes:
   - ``isExplicit``
   - ``usesManifoldLayout``
   - ``ewOff``
   - ``chipH``
   - ``chipOw``

   If you are debugging why a chip became taller or wider, or why it switched
   from compact layout to manifold layout, start with:
   - ``_usesManifoldLayout_compute()``
   - ``_topRibbonHeight_compute()``
   - ``_bottomRibbonHeight_compute()``
   - ``_chipH_compute()``
   - ``_chipOw_compute()``

2. Stage 2 resolved geometry
   ``ChipGeometry.resolve()`` runs after layout has assigned absolute chip rows.
   This stage resolves:
   - left and right wall rows
   - directive classification into wall continuity, straight, and manifold paths
   - manifold endpoint counts
   - longitude columns
   - anchor rows
   - internal label aliases

   If you are debugging why a specific wire lands on the wrong row, why a pair
   became straight-through versus manifold, or why an anchor column ended up in
   a particular place, start with:
   - ``_leftWallRows_resolve()``
   - ``_rightWallRows_resolve()``
   - ``_directiveLists_resolve()``
   - ``_directivePlacement_resolve()``
   - ``_manifoldGeometry_resolve()``

Important design rules in this module:
- Display labels are not sufficient routing identity for manifold logic.
  Canonical manifold endpoint identity is side + kind + label, built with
  ``_endpoint_key()``.
- Structural classification happens before rendering. The renderer should read
  the resolved ``ChipGeometry`` record rather than re-deriving local geometry.
- Same-wall continuity, straight-through pairs, and true manifold routing are
  separate geometry classes and should stay separate here.

Returns:
    None: This module exports helper functions, dataclasses, and the
        ``ChipGeometry`` model consumed by layout and rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from signalflow.legacy.config import config

if TYPE_CHECKING:
    from signalflow.legacy.models.node import Node


def _anchor_display(name: str) -> str:
    """Compute the visible anchor label text for one port name.

    Args:
        name (str): The full port name before any width truncation.

    Returns:
        str: The displayed anchor text, truncated when
            ``config.anchorLabelMaxWidth`` is positive.
    """
    w: int = config.anchorLabelMaxWidth
    return name[:w] if w > 0 and len(name) > w else name


def _base36_2digit(index: int) -> str:
    """Compute a stable two-character-or-longer base36 token.

    Args:
        index (int): The 1-based alias index to encode.

    Returns:
        str: A zero-padded base36 token suitable for compact aliases.
    """
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
    """Decide whether one manifold endpoint should show an internal label.

    Args:
        count (int): Endpoint density assigned to the manifold endpoint.
        showInternalLabels (bool): Global or per-chip label visibility flag.
        passThroughAllowed (bool): Whether unit-density ports remain wall-flush.

    Returns:
        bool: ``True`` when the endpoint should render an internal label.
    """
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
    """Compute reserved width for one internal anchor label.

    Args:
        displayName (str): The endpoint display label before arrow decoration.
        count (int): Endpoint density assigned to the manifold endpoint.
        showInternalLabels (bool): Global or per-chip label visibility flag.
        aliasInternalLabels (bool): Whether compact aliases replace raw labels.
        passThroughAllowed (bool): Whether unit-density ports remain wall-flush.

    Returns:
        int: Reserved character width, including the direction arrow.
    """
    if not _internal_labelShown(count, showInternalLabels, passThroughAllowed):
        return 0
    if aliasInternalLabels:
        return 4
    return len(_anchor_display(displayName)) + 1


@dataclass(frozen=True)
class WallContinuity:
    """Represent a same-wall local handoff inside one chip.

    This record captures the implicit or explicit continuity used for adjacent
    same-wall transfers without sending them through the full manifold router.

    Attributes:
        side (str): Wall side, typically ``"R"`` for the current continuity
            model.
        src (str): Source label at the wall handoff.
        dst (str): Destination label at the wall handoff.
        srcRow (int): Source wall row.
        dstRow (int): Destination wall row.
        routeClass (str): Route class, ``"data"`` or ``"thread"``.
        routeClassExplicit (bool): Whether the route class was named explicitly.
        isPure (bool): Whether the continuity is relay-only.
        colorName (str | None): Optional explicit presentation color token.
    """

    side: str
    src: str
    dst: str
    srcRow: int
    dstRow: int
    routeClass: str = "data"
    routeClassExplicit: bool = False
    isPure: bool = False
    colorName: str | None = None

    @property
    def gapRow(self) -> int:
        """Return the visual gap row between the continuity endpoints.

        Returns:
            int: The intermediate row between ``srcRow`` and ``dstRow``.
        """
        return self.srcRow + 1 if self.dstRow >= self.srcRow else self.srcRow - 1


@dataclass(frozen=True)
class WiringDirective:
    """Represent one parsed ``internal_wiring`` directive.

    Attributes:
        src (str): Source label token.
        dst (str): Destination label token.
        routeClass (str): Route class, ``"data"`` or ``"thread"``.
        routeClassExplicit (bool): Whether the route class was named explicitly
            in the directive text.
        orientation (str | None): Optional explicit orientation token.
        isPure (bool): Whether the directive suppresses computation markers.
        isCompute (bool): Whether the directive explicitly affirms computation.
        colorName (str | None): Optional presentation color token parsed from
            ``color(name)``.
    """

    src: str
    dst: str
    routeClass: str = "data"
    routeClassExplicit: bool = False
    orientation: str | None = None
    isPure: bool = False
    isCompute: bool = False
    colorName: str | None = None


@dataclass(frozen=True)
class DirectivePlacement:
    """Represent one directive resolved against concrete wall geometry.

    Attributes:
        directive (WiringDirective): Original parsed directive.
        srcSide (str): Source wall side.
        dstSide (str): Destination wall side.
        srcRow (int): Source wall row.
        dstRow (int): Destination wall row.
        srcKind (str): Source endpoint kind, ``"sig"`` or ``"ret"``.
        dstKind (str): Destination endpoint kind, ``"sig"`` or ``"ret"``.
    """

    directive: WiringDirective
    srcSide: str
    dstSide: str
    srcRow: int
    dstRow: int
    srcKind: str
    dstKind: str

    @property
    def srcKey(self) -> str:
        """Return the manifold routing key for the source endpoint.

        Returns:
            str: Wall- and kind-qualified endpoint key.
        """
        return _endpoint_key(self.directive.src, self.srcSide, self.srcKind)

    @property
    def dstKey(self) -> str:
        """Return the manifold routing key for the destination endpoint.

        Returns:
            str: Wall- and kind-qualified endpoint key.
        """
        return _endpoint_key(self.directive.dst, self.dstSide, self.dstKind)


def _endpoint_key(label: str, side: str, kind: str) -> str:
    """Build a manifold-internal endpoint identifier.

    Args:
        label (str): Display label attached to the endpoint.
        side (str): Wall side qualifier.
        kind (str): Endpoint kind qualifier, ``"sig"`` or ``"ret"``.

    Returns:
        str: A wall- and kind-qualified endpoint key.
    """
    return f"{side}|{kind}|{label}"


@dataclass
class ChipGeometry:
    """Store authoritative structural and positional chip geometry.

    Stage 1 stores pre-layout structural geometry such as chip height, width,
    wall-name sets, and manifold usage. Stage 2 stores resolved wall rows,
    manifold zones, anchor rows, and continuity classifications after layout
    assigns vertical positions.

    Attributes:
        ewOff (int): Reserved top ribbon height for E→W manifold trunks.
        rightTopMargin (int): Extra top runway reserved for east-wall fan-in
            structure near the first output signal.
        rightBottomMargin (int): Extra bottom runway reserved for east-wall
            fan-out structure near the last output return.
        chipH (int): Structural chip height in rows.
        chipOw (int): Structural chip width in columns.
        leftNames (set[str]): Distinct labels seen on the west wall.
        rightNames (set[str]): Distinct labels seen on the east wall.
        signalNames (set[str]): Distinct forward-signal labels.
        isExplicit (bool): Effective west input mode after config resolution.
        usesManifoldLayout (bool): Whether the chip requires manifold geometry.
        internalWireColorize (bool): Effective internal colorization flag.
        showInternalLabels (bool): Effective internal-label visibility flag.
        aliasInternalLabels (bool): Effective internal-label alias flag.
        resolved (bool): Whether Stage 2 positional geometry has been computed.
    """

    # ── Stage 1: structural (wiring-only) ─────────────────────────────────
    ewOff: int = 0
    rightTopMargin: int = 0
    rightBottomMargin: int = 0
    chipH: int = 0
    chipOw: int = 0
    leftNames: set[str] = field(default_factory=set)
    rightNames: set[str] = field(default_factory=set)
    signalNames: set[str] = field(default_factory=set)  # port.signal names
    isExplicit: bool = True  # resolved inputExplicit (None → config)
    usesManifoldLayout: bool = False
    internalWireColorize: bool = True
    showInternalLabels: bool = True
    aliasInternalLabels: bool = False

    # ── Stage 2: positional (requires y0) — implemented in Phase 2 ────────
    resolved: bool = False
    y0: int = 0
    leftSignalRows: dict[str, list[int]] = field(default_factory=dict)
    leftReturnRows: dict[str, list[int]] = field(default_factory=dict)
    leftWallRows: dict[str, list[int]] = field(default_factory=dict)
    rightSignalRows: dict[str, list[int]] = field(default_factory=dict)
    rightReturnRows: dict[str, list[int]] = field(default_factory=dict)
    rightWallRows: dict[str, list[int]] = field(default_factory=dict)
    straightDirectives: list[WiringDirective] = field(default_factory=list)
    straightPairs: list[tuple[str, str]] = field(default_factory=list)
    wiringDirectives: list[WiringDirective] = field(default_factory=list)
    wiringPairs: list[tuple[str, str]] = field(default_factory=list)
    wallContinuities: list[WallContinuity] = field(default_factory=list)
    purePairs: set[tuple[str, str]] = field(default_factory=set)
    lCounts: dict[str, int] = field(default_factory=dict)
    unitPorts: set[str] = field(default_factory=set)
    portToX: dict[str, int] = field(default_factory=dict)
    leftZoneInnerX: int = 0
    rightZoneInnerX: int = 0
    anchorFloor: int = 0
    interiorMax: int = 0
    allAnchorRows: dict[str, list[int]] = field(default_factory=dict)
    internalLabelAliases: dict[str, str] = field(default_factory=dict)
    eastEdgeReuseDirectiveIds: set[int] = field(default_factory=set)

    # ── Stage 1 factory ───────────────────────────────────────────────────

    @classmethod
    def build_structural(cls, node: Node) -> ChipGeometry:
        """Build Stage 1 structural geometry for one node.

        Args:
            node (Node): The chip node whose structural geometry is required.

        Returns:
            ChipGeometry: A partially populated geometry record with structural
                height, width, and manifold flags resolved.
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
        geo.ewOff = cls._topRibbonHeight_compute(node)
        (
            geo.rightTopMargin,
            geo.rightBottomMargin,
        ) = cls._rightBoundaryMargins_compute(node, geo.signalNames)
        geo.chipH = cls._chipH_compute(
            node,
            geo.ewOff,
            geo.rightTopMargin,
            geo.rightBottomMargin,
            geo.isExplicit,
            geo.usesManifoldLayout,
        )
        geo.chipOw = cls._chipOw_compute(node, geo.usesManifoldLayout)
        return geo

    # ── Stage 1 helpers ───────────────────────────────────────────────────

    @staticmethod
    def _portSide_resolve(
        name: str,
        prefer: str,
        leftRows: dict[str, list[int]],
        rightRows: dict[str, list[int]],
    ) -> str:
        """Resolve a wall side from structural row maps.

        Args:
            name (str): Port label to resolve.
            prefer (str): Fallback side when the label exists on both walls.
            leftRows (dict[str, list[int]]): Structural left-wall row map.
            rightRows (dict[str, list[int]]): Structural right-wall row map.

        Returns:
            str: ``"L"`` or ``"R"`` for the resolved wall side.
        """
        inL: bool = name in leftRows
        inR: bool = name in rightRows
        if inL and not inR:
            return "L"
        if inR and not inL:
            return "R"
        return prefer

    @staticmethod
    def _directive_parse(node: Node) -> list[WiringDirective]:
        """Parse raw ``internal_wiring`` strings into directives.

        Supported forms:
        - ``src:dst``
        - ``src:dst:pure``
        - ``src:dst:compute``
        - ``src:dst:thread``
        - ``src:dst:data``
        - ``src:dst:EW|WE|NS|SN``
        - ``src:dst:EW|WE|NS|SN:pure``
        - ``src:dst:EW|WE|NS|SN:compute``
        - ``src:dst:...:color(name)``

        Args:
            node (Node): The chip node containing raw wiring strings.

        Returns:
            list[WiringDirective]: Parsed directives in declaration order.
        """

        directives: list[WiringDirective] = []
        validOrientation: set[str] = {"EW", "WE", "NS", "SN"}
        validColorNames: set[str] = {
            "red",
            "green",
            "yellow",
            "blue",
            "magenta",
            "cyan",
            "white",
            "accent",
            "muted",
            "none",
        }
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
            routeClass: str | None = None
            routeClassExplicit: bool = False
            orientation: str | None = None
            isPure: bool = False
            isCompute: bool = False
            colorName: str | None = None
            token: str
            for token in parts[2:]:
                if token in {"thread", "data"}:
                    if routeClass is not None:
                        raise AssertionError(
                            f"internal_wiring {w!r}: multiple route-class tokens"
                        )
                    routeClass = token
                    routeClassExplicit = True
                elif token == "pure":
                    isPure = True
                elif token == "compute":
                    isCompute = True
                elif token in validOrientation:
                    if orientation is not None:
                        raise AssertionError(
                            f"internal_wiring {w!r}: multiple orientation tokens"
                        )
                    orientation = token
                elif token.startswith("color(") and token.endswith(")"):
                    if colorName is not None:
                        raise AssertionError(
                            f"internal_wiring {w!r}: multiple color tokens"
                        )
                    colorName = token[6:-1]
                    if not colorName:
                        raise AssertionError(
                            f"internal_wiring {w!r}: color token must name a color"
                        )
                    if colorName not in validColorNames:
                        raise AssertionError(
                            f"internal_wiring {w!r}: unsupported color {colorName!r}"
                        )
                else:
                    raise AssertionError(
                        f"internal_wiring {w!r}: unsupported directive token {token!r}"
                    )
            if routeClass is None:
                routeClass = "thread" if (isPure or isCompute) else "data"
            if isPure and isCompute:
                raise AssertionError(
                    f"internal_wiring {w!r}: cannot combine pure and compute"
                )
            if routeClass == "thread" and not (isPure or isCompute):
                isCompute = True
            if routeClass == "data" and (isPure or isCompute):
                raise AssertionError(
                    "internal_wiring "
                    f"{w!r}: data routes cannot combine with pure or compute"
                )
            directives.append(
                WiringDirective(
                    src=src,
                    dst=dst,
                    routeClass=routeClass,
                    routeClassExplicit=routeClassExplicit,
                    orientation=orientation,
                    isPure=isPure,
                    isCompute=isCompute,
                    colorName=colorName,
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
        """Compute structural wall rows for compact non-manifold layout.

        Args:
            node (Node): The chip node whose port order defines relative rows.

        Returns:
            tuple[dict[str, list[int]], dict[str, list[int]], dict[str, list[int]],
            dict[str, list[int]]]: Left-signal, left-return, right-signal, and
            right-return row maps using the compact three-row spacing model.
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
        """Resolve oriented directive endpoints against structural row maps.

        Args:
            directive (WiringDirective): Parsed directive with an orientation token.
            leftSignalRows (dict[str, list[int]]): Structural left-signal rows.
            leftReturnRows (dict[str, list[int]]): Structural left-return rows.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            tuple[str, str, int, int]: Source side, destination side, source row,
            and destination row for the oriented directive.
        """

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
        """Resolve structural endpoints for an un-oriented directive.

        Args:
            directive (WiringDirective): Parsed directive without orientation.
            signalNames (set[str]): Labels that represent signal ports.
            leftSignalRows (dict[str, list[int]]): Structural left-signal rows.
            leftReturnRows (dict[str, list[int]]): Structural left-return rows.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            tuple[str, str, int, int]: Source side, destination side, source row,
            and destination row inferred from signal/return semantics.
        """

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
        """Count how often each label appears as a directive endpoint.

        Args:
            directives (list[WiringDirective]): Parsed directives to count.

        Returns:
            tuple[dict[str, int], dict[str, int]]: Source counts and destination
            counts keyed by label text.
        """
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
        """Resolve signal-vs-return kinds for a directive placement.

        Args:
            directive (WiringDirective): Directive being classified.
            signalNames (set[str]): Labels that represent signal ports.
            srcSide (str): Resolved source wall side, ``"L"`` or ``"R"``.
            dstSide (str): Resolved destination wall side, ``"L"`` or ``"R"``.

        Returns:
            tuple[str, str]: Source kind and destination kind, each ``"sig"`` or
            ``"ret"``.
        """
        if directive.orientation == "WE":
            return "sig", "sig"
        if directive.orientation == "EW":
            return "ret", "ret"
        if directive.orientation in {"NS", "SN"}:
            if srcSide == "R":
                return "ret", "sig"
            return "sig", "ret"

        srcKind: str = (
            "sig" if srcSide == "L" and directive.src in signalNames else "ret"
        )
        dstKind: str = (
            "sig" if dstSide == "R" and directive.dst in signalNames else "ret"
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
        """Resolve structural placement details for one directive.

        Args:
            directive (WiringDirective): Directive to resolve.
            signalNames (set[str]): Labels that represent signal ports.
            leftSignalRows (dict[str, list[int]]): Structural left-signal rows.
            leftReturnRows (dict[str, list[int]]): Structural left-return rows.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            DirectivePlacement: Structural side, row, and kind information for the
            directive.
        """
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
        """Classify a resolved directive into one of the supported render modes.

        Args:
            placement (DirectivePlacement): Resolved directive placement.
            srcCounts (dict[str, int]): Source label usage counts.
            dstCounts (dict[str, int]): Destination label usage counts.

        Returns:
            str: One of ``"wall"``, ``"straight"``, or ``"manifold"``.
        """
        directive: WiringDirective = placement.directive
        if directive.orientation in {"NS", "SN"}:
            cls._sameWallOrientation_validate(
                directive,
                placement.srcRow,
                placement.dstRow,
            )
            return (
                "wall" if abs(placement.dstRow - placement.srcRow) == 2 else "manifold"
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
        """Increment aggregate endpoint counts for one manifold placement.

        Args:
            endpointCounts (dict[str, int]): Aggregate endpoint density map.
            placement (DirectivePlacement): Placement whose endpoints are counted.

        Returns:
            None: The aggregate map is updated in place.
        """
        endpointCounts[placement.srcKey] = endpointCounts.get(placement.srcKey, 0) + 1
        endpointCounts[placement.dstKey] = endpointCounts.get(placement.dstKey, 0) + 1

    @staticmethod
    def _wallContinuity_build(placement: DirectivePlacement) -> WallContinuity:
        """Build a same-wall continuity record from one placement.

        Args:
            placement (DirectivePlacement): Placement classified as same-wall
                continuity.

        Returns:
            WallContinuity: Normalized same-wall continuity record.
        """
        directive: WiringDirective = placement.directive
        return WallContinuity(
            side=placement.srcSide,
            src=directive.src,
            dst=directive.dst,
            srcRow=placement.srcRow,
            dstRow=placement.dstRow,
            routeClass=directive.routeClass,
            routeClassExplicit=directive.routeClassExplicit,
            isPure=directive.isPure,
            colorName=directive.colorName,
        )

    @classmethod
    def _manifoldEndpointCounts_structural(
        cls,
        node: Node,
        signalNames: set[str],
    ) -> dict[str, int]:
        """Compute structural manifold endpoint densities before Stage 2.

        Args:
            node (Node): The chip node being analyzed.
            signalNames (set[str]): Labels that represent signal ports.

        Returns:
            dict[str, int]: Structural manifold endpoint counts keyed by endpoint
            identity.
        """
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
        """Determine whether a chip requires full manifold geometry.

        Args:
            node (Node): The chip node being analyzed.
            isExplicit (bool): Whether the chip uses explicit input placement.
            signalNames (set[str]): Labels that represent signal ports.

        Returns:
            bool: ``True`` when any directive requires manifold routing instead of
            compact straight-through or adjacent same-wall handling.
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
        """Determine whether one directive exceeds compact geometry.

        Args:
            directive (WiringDirective): Directive being analyzed.
            signalNames (set[str]): Labels that represent signal ports.
            leftSignalRows (dict[str, list[int]]): Structural left-signal rows.
            leftReturnRows (dict[str, list[int]]): Structural left-return rows.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            bool: ``True`` when the directive must be handled by the manifold.
        """
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
        """Determine whether an oriented directive requires manifold routing.

        Args:
            directive (WiringDirective): Oriented directive being analyzed.
            leftSignalRows (dict[str, list[int]]): Structural left-signal rows.
            leftReturnRows (dict[str, list[int]]): Structural left-return rows.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            bool: ``True`` when the oriented directive cannot be rendered compactly.
        """
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
        """Determine whether an implicit directive requires manifold routing.

        Args:
            directive (WiringDirective): Unoriented directive being analyzed.
            signalNames (set[str]): Labels that represent signal ports.
            leftSignalRows (dict[str, list[int]]): Structural left-signal rows.
            leftReturnRows (dict[str, list[int]]): Structural left-return rows.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            bool: ``True`` when the implicit directive cannot use compact geometry.
        """
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
        """Compute maximum visible internal label widths by wall side.

        Args:
            leftPorts (list[str]): Left-wall manifold endpoint keys.
            rightPorts (list[str]): Right-wall manifold endpoint keys.

        Returns:
            tuple[int, int]: Maximum visible label widths on the left and right
            manifold walls.
        """
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
        routedCounts: dict[str, int],
    ) -> tuple[int, int]:
        """Assign longitude columns to manifold endpoints.

        Args:
            leftPorts (list[str]): Left-wall manifold endpoint keys.
            rightPorts (list[str]): Right-wall manifold endpoint keys.
            leftLongStart (int): First left-wall longitude column.
            rightLongStart (int): First right-wall longitude column.
            routedCounts (dict[str, int]): Endpoint counts that actually enter
                the general routed manifold.

        Returns:
            tuple[int, int]: Total left-side and right-side longitude track counts.
        """
        vTrackL: int = 0
        port: str
        for port in leftPorts:
            self.portToX[port] = leftLongStart + 2 * vTrackL
            vTrackL += routedCounts[port]

        vTrackR: int = 0
        for port in rightPorts:
            self.portToX[port] = rightLongStart - 2 * (vTrackR + routedCounts[port] - 1)
            vTrackR += routedCounts[port]
        return vTrackL, vTrackR

    @staticmethod
    def _sameWallOrientation_validate(
        directive: WiringDirective, srcRow: int, dstRow: int
    ) -> None:
        """Validate row ordering for same-wall oriented directives.

        Args:
            directive (WiringDirective): Oriented same-wall directive to validate.
            srcRow (int): Resolved source row.
            dstRow (int): Resolved destination row.

        Returns:
            None: Validation passes silently or raises ``AssertionError``.
        """
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
        """Check whether a directive matches implicit right-wall continuity.

        Args:
            src (str): Source label.
            dst (str): Destination label.
            srcIsSignal (bool): Whether the source label is a signal.
            dstIsSignal (bool): Whether the destination label is a signal.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            bool: ``True`` when the directive matches the adjacent implicit
            right-wall handoff pattern.
        """
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
        """Check whether a directive matches compact cross-wall pass-through.

        Args:
            src (str): Source label.
            dst (str): Destination label.
            srcIsSignal (bool): Whether the source label is a signal.
            dstIsSignal (bool): Whether the destination label is a signal.
            leftSignalRows (dict[str, list[int]]): Structural left-signal rows.
            leftReturnRows (dict[str, list[int]]): Structural left-return rows.
            rightSignalRows (dict[str, list[int]]): Structural right-signal rows.
            rightReturnRows (dict[str, list[int]]): Structural right-return rows.

        Returns:
            bool: ``True`` when the directive matches one of the compact
            straight-through cases.
        """
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
        """Compute left-wall signal and return density hints from directives.

        Args:
            node (Node): The chip node being analyzed.
            signalNames (set[str]): Labels that represent signal ports.

        Returns:
            tuple[dict[str, int], dict[str, int]]: Left-signal usage counts and
            left-return usage counts keyed by display label.
        """

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
        """Count E->W ribbon rows required above the main wall rows.

        Args:
            node (Node): The chip node whose internal wiring is being analyzed.

        Returns:
            int: Number of top ribbon rows required for E->W trunk traffic.
        """
        if not node.internal_wiring:
            return 0
        rightRetPorts: set[str] = {
            port.ret for port in node.output_ports.values() if port.ret
        }
        rightSignalPorts: set[str] = {
            port.signal for port in node.output_ports.values() if port.signal
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
            # Right-return -> right-signal handoffs are same-wall east-edge
            # continuities. They reuse east-side endpoint geometry and do not
            # consume a top E->W ribbon lane.
            if dst in rightSignalPorts:
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
    def _topRibbonHeight_compute(node: Node) -> int:
        """Return the reserved height of the top E->W ribbon zone.

        Args:
            node (Node): The chip node whose top ribbon height is needed.

        Returns:
            int: Reserved row count for the top ribbon zone.
        """
        return ChipGeometry._ewOff_compute(node)

    @staticmethod
    def _wallPortCount_compute(node: Node, isExplicit: bool) -> int:
        """Return the dominant wall port count used by height formulas.

        Args:
            node (Node): The chip node whose wall counts are being compared.
            isExplicit (bool): Whether the chip uses explicit input placement.

        Returns:
            int: Maximum relevant wall port count for chip-height sizing.
        """
        nLeft: int = len(node.input_ports)
        nRight: int = (
            len(node.output_ports) if node.output_ports else len(node.children)
        )
        if not isExplicit:
            nLeft = 1
        return max(nLeft, nRight)

    @classmethod
    def _rightBoundaryMargins_compute(
        cls,
        node: Node,
        signalNames: set[str],
    ) -> tuple[int, int]:
        """Compute extra east-wall runway needed at the top and bottom edges.

        Args:
            node (Node): The chip node whose east-edge runway is being sized.
            signalNames (set[str]): Labels that represent signal ports.

        Returns:
            tuple[int, int]: Additional top and bottom east-edge margins.
        """
        if not node.internal_wiring or not node.output_ports:
            return 0, 0

        endpointCounts: dict[str, int] = cls._manifoldEndpointCounts_structural(
            node,
            signalNames,
        )
        if not endpointCounts:
            return 0, 0

        outputPorts: list = list(node.output_ports.values())
        firstSignal: str | None = next(
            (port.signal for port in outputPorts if port.signal),
            None,
        )
        lastReturn: str | None = next(
            (port.ret for port in reversed(outputPorts) if port.ret),
            None,
        )

        topCount: int = (
            endpointCounts.get(_endpoint_key(firstSignal, "R", "sig"), 0)
            if firstSignal
            else 0
        )
        bottomCount: int = (
            endpointCounts.get(_endpoint_key(lastReturn, "R", "ret"), 0)
            if lastReturn
            else 0
        )

        if config.passThroughAllowed:
            topCount = 0 if topCount <= 1 else topCount
            bottomCount = 0 if bottomCount <= 1 else bottomCount

        return topCount, bottomCount

    @staticmethod
    def _singlePortChipHeight_compute(node: Node, ewOff: int) -> int:
        """Compute compact chip height for leaf and single-port chips.

        Args:
            node (Node): The chip node being sized.
            ewOff (int): Reserved top ribbon height.

        Returns:
            int: Compact chip height for the node.
        """
        if not node.children:
            return max(config.baseLeafHeight, 7 + ewOff)
        return max(config.baseLeafHeight, 6 + ewOff)

    @staticmethod
    def _manifoldPortCounts_compute(node: Node) -> tuple[dict[str, int], int]:
        """Count directive endpoint usage for manifold height calculations.

        Args:
            node (Node): The chip node being analyzed.

        Returns:
            tuple[dict[str, int], int]: Endpoint usage counts keyed by label text
            and the number of parsed directives.
        """
        portCounts: dict[str, int] = {}
        directives: list[WiringDirective] = ChipGeometry._directive_parse(node)
        directive: WiringDirective
        for directive in directives:
            portCounts[directive.src] = portCounts.get(directive.src, 0) + 1
            portCounts[directive.dst] = portCounts.get(directive.dst, 0) + 1
        return portCounts, len(directives)

    @staticmethod
    def _bottomRibbonHeight_compute(
        node: Node,
        isExplicit: bool,
        wiringCount: int,
    ) -> int:
        """Return the reserved height of the bottom W->E ribbon zone.

        Args:
            node (Node): The chip node whose bottom ribbon height is needed.
            isExplicit (bool): Whether the chip uses explicit input placement.
            wiringCount (int): Number of parsed wiring directives.

        Returns:
            int: Reserved row count for the bottom ribbon zone.
        """
        baseHeight: int
        if isExplicit:
            baseHeight = wiringCount
        else:
            leftNames: set[str] = {
                nm
                for port in node.input_ports.values()
                for nm in (port.signal, port.ret)
                if nm
            }
            baseHeight = sum(
                1
                for directive in ChipGeometry._directive_parse(node)
                if directive.src in leftNames
            )

        return baseHeight

    @staticmethod
    def _explicitManifoldHeight_compute(
        topRibbonHeight: int,
        nPorts: int,
        maxPortDensity: int,
        bottomRibbonHeight: int,
    ) -> int:
        """Compute manifold chip height for explicit-input chips.

        Args:
            topRibbonHeight (int): Reserved height of the top ribbon zone.
            nPorts (int): Dominant wall port count.
            maxPortDensity (int): Maximum endpoint density in the manifold.
            bottomRibbonHeight (int): Reserved height of the bottom ribbon zone.

        Returns:
            int: Total manifold chip height for explicit-input layout.
        """
        spacing: int = config.portVerticalSpacing
        lastWallReturnOffset: int = 3 + topRibbonHeight + spacing * (nPorts - 1) + 1
        return lastWallReturnOffset + maxPortDensity + bottomRibbonHeight + 1

    @staticmethod
    def _sovereignManifoldHeight_compute(
        node: Node,
        topRibbonHeight: int,
        nPorts: int,
        portCounts: dict[str, int],
        bottomRibbonHeight: int,
    ) -> int:
        """Compute manifold chip height for sovereign-input chips.

        Args:
            node (Node): The chip node being sized.
            topRibbonHeight (int): Reserved height of the top ribbon zone.
            nPorts (int): Dominant wall port count.
            portCounts (dict[str, int]): Endpoint usage counts keyed by label.
            bottomRibbonHeight (int): Reserved height of the bottom ribbon zone.

        Returns:
            int: Total manifold chip height for sovereign-input layout.
        """
        spacing: int = config.portVerticalSpacing
        leftNames: set[str] = {
            nm
            for port in node.input_ports.values()
            for nm in (port.signal, port.ret)
            if nm
        }
        lastWallReturnOffset: int = 3 + topRibbonHeight + spacing * (nPorts - 1) + 1
        maxRightDensity: int = max(
            (cnt for prt, cnt in portCounts.items() if prt not in leftNames),
            default=0,
        )
        return lastWallReturnOffset + maxRightDensity + bottomRibbonHeight + 1

    @staticmethod
    def _chipH_compute(
        node: Node,
        ewOff: int,
        rightTopMargin: int,
        rightBottomMargin: int,
        isExplicit: bool,
        usesManifoldLayout: bool,
    ) -> int:
        """Compute total chip height in rows.

        Args:
            node (Node): The chip node being sized.
            ewOff (int): Reserved top ribbon height.
            rightTopMargin (int): Extra top runway reserved for east-wall
                fan-in structure.
            rightBottomMargin (int): Extra bottom runway reserved for east-wall
                fan-out structure.
            isExplicit (bool): Whether the chip uses explicit input placement.
            usesManifoldLayout (bool): Whether the chip needs manifold geometry.

        Returns:
            int: Total chip height in rows.
        """
        n: int = ChipGeometry._wallPortCount_compute(node, isExplicit)

        if n <= 1:
            return ChipGeometry._singlePortChipHeight_compute(node, ewOff)

        if not usesManifoldLayout:
            return 3 * n + 3

        portCounts: dict[str, int]
        wiringCount: int
        portCounts, wiringCount = ChipGeometry._manifoldPortCounts_compute(node)
        topRibbonHeight: int = (
            ChipGeometry._topRibbonHeight_compute(node) + rightTopMargin
        )
        bottomRibbonHeight: int = ChipGeometry._bottomRibbonHeight_compute(
            node,
            isExplicit,
            wiringCount,
        ) + rightBottomMargin
        maxPortDensity: int = max(portCounts.values(), default=0)

        if not isExplicit:
            h: int = ChipGeometry._sovereignManifoldHeight_compute(
                node,
                topRibbonHeight,
                n,
                portCounts,
                bottomRibbonHeight,
            )
            return max(config.baseLeafHeight, h)

        h = ChipGeometry._explicitManifoldHeight_compute(
            topRibbonHeight,
            n,
            maxPortDensity,
            bottomRibbonHeight,
        )
        return max(config.baseLeafHeight, h)

    @staticmethod
    def _endpointCountsBySide_compute(
        endpointCounts: dict[str, int],
    ) -> tuple[int, int]:
        """Sum manifold endpoint density by wall side.

        Args:
            endpointCounts (dict[str, int]): Endpoint densities keyed by endpoint
                identity.

        Returns:
            tuple[int, int]: Total left-side density and total right-side density.
        """
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
        """Compute the maximum visible label width for one wall side.

        Args:
            endpointCounts (dict[str, int]): Endpoint densities keyed by endpoint
                identity.
            side (str): Wall side, ``"L"`` or ``"R"``.
            showInternalLabels (bool): Whether internal labels are displayed.
            aliasInternalLabels (bool): Whether displayed internal labels are
                aliased.

        Returns:
            int: Maximum visible internal label width for the requested side.
        """
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

        Args:
            node (Node): The chip node being sized.
            usesManifoldLayout (bool): Whether the chip needs manifold geometry.

        Returns:
            int: Outer chip width in columns.
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
        """Resolve the wall side for a display label.

        Args:
            name (str): Display label to resolve.
            prefer (str | None): Fallback side when the label exists on both walls.

        Returns:
            str: ``"L"`` or ``"R"`` for the resolved wall side.
        """
        inL: bool = name in self.leftNames
        inR: bool = name in self.rightNames
        if inL and not inR:
            return "L"
        if inR and not inL:
            return "R"
        return prefer if prefer else "L"

    def wiring_side(self, name: str, role: str) -> str:
        """Resolve the wall side for a wiring endpoint.

        Args:
            name (str): Display label for the endpoint.
            role (str): Endpoint role, ``"src"`` or ``"dst"``.

        Returns:
            str: ``"L"`` or ``"R"`` for the resolved wall side.
        """
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
            "L" if (role == "src" and isSig) or (role == "dst" and not isSig) else "R"
        )
        return self.port_side(name, prefer=prefer)

    def is_signal(self, name: str) -> bool:
        """Check whether a display label is a signal label.

        Args:
            name (str): Display label to test.

        Returns:
            bool: ``True`` when the label appears as a signal port.
        """
        return name in self.signalNames

    # ── Stage 2 resolver ─────────────────────────────────────────────────

    def _leftWallRows_resolve(
        self,
        node: Node,
        entryRows: dict[int, int],
        returnRows: dict[int, int],
    ) -> None:
        """Populate left-wall row maps from resolved parent-bound port rows.

        Args:
            node (Node): The chip node whose input ports are being resolved.
            entryRows (dict[int, int]): Resolved west entry rows by parent binding.
            returnRows (dict[int, int]): Resolved west return rows by parent binding.

        Returns:
            None: The left-wall row maps are updated in place.
        """
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
        """Populate right-wall row maps from output occurrence order.

        Args:
            node (Node): The chip node whose outputs are being resolved.
            y0 (int): Absolute top row of the chip.

        Returns:
            None: The right-wall row maps are updated in place.
        """
        spacing: int = config.portVerticalSpacing if self.usesManifoldLayout else 3
        idx: int
        port: object
        for idx, port in enumerate(node.output_ports.values()):
            if port.signal:
                row = y0 + 3 + self.ewOff + self.rightTopMargin + spacing * idx
                self.rightSignalRows.setdefault(port.signal, [])
                self.rightWallRows.setdefault(port.signal, [])
                if row not in self.rightSignalRows[port.signal]:
                    self.rightSignalRows[port.signal].append(row)
                if row not in self.rightWallRows[port.signal]:
                    self.rightWallRows[port.signal].append(row)
            if port.ret:
                row = y0 + 4 + self.ewOff + self.rightTopMargin + spacing * idx
                self.rightReturnRows.setdefault(port.ret, [])
                self.rightWallRows.setdefault(port.ret, [])
                if row not in self.rightReturnRows[port.ret]:
                    self.rightReturnRows[port.ret].append(row)
                if row not in self.rightWallRows[port.ret]:
                    self.rightWallRows[port.ret].append(row)

    def _directiveLists_resolve(self, node: Node) -> None:
        """Classify directives into wall, straight, and manifold collections.

        Args:
            node (Node): The chip node whose directives are being classified.

        Returns:
            None: Classification lists and continuity records are updated in place.
        """
        allPairsRaw: list[WiringDirective] = sorted(
            self._directive_parse(node),
            key=lambda d: (
                d.src,
                d.dst,
                d.routeClass,
                d.orientation or "",
                d.colorName or "",
                "compute" if d.isCompute else "",
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
        """Resolve manifold endpoint densities from classified directives.

        Returns:
            None: Endpoint density counts are updated in place.
        """
        self.eastEdgeReuseDirectiveIds = self._eastEdgeReuseDirectiveIds_compute()
        directive: WiringDirective
        for directive in self.wiringDirectives:
            if id(directive) in self.eastEdgeReuseDirectiveIds:
                continue
            placement: DirectivePlacement = self._directivePlacement_resolve(directive)
            self._endpointCounts_increment(self.lCounts, placement)

    @staticmethod
    def _eastEdgeReusePlacement_matches(placement: DirectivePlacement) -> bool:
        """Return whether one placement uses east-edge manifold reuse.

        Args:
            placement (DirectivePlacement): Resolved directive placement.

        Returns:
            bool: ``True`` when the directive is a right-return to right-signal
            handoff that reuses east-edge endpoint bundles instead of entering
            the general routed manifold.
        """
        return (
            placement.srcSide == placement.dstSide == "R"
            and placement.srcKind == "ret"
            and placement.dstKind == "sig"
        )

    def _eastEdgeReuseDirectiveIds_compute(self) -> set[int]:
        """Resolve which directives should reuse existing east-edge bundles.

        Returns:
            set[int]: ``id()`` values for directives that should render via the
                east-edge reuse pattern instead of consuming general manifold
                endpoint density.
        """
        baseCounts: dict[str, int] = {}
        placementsByDirectiveId: dict[int, DirectivePlacement] = {}
        directive: WiringDirective
        for directive in self.wiringDirectives:
            placement: DirectivePlacement = self._directivePlacement_resolve(directive)
            placementsByDirectiveId[id(directive)] = placement
            if self._eastEdgeReusePlacement_matches(placement):
                continue
            self._endpointCounts_increment(baseCounts, placement)

        reuseIds: set[int] = set()
        directiveId: int
        placement: DirectivePlacement
        for directiveId, placement in placementsByDirectiveId.items():
            if not self._eastEdgeReusePlacement_matches(placement):
                continue
            if (
                baseCounts.get(placement.srcKey, 0) > 0
                and baseCounts.get(placement.dstKey, 0) > 0
            ):
                reuseIds.add(directiveId)
        return reuseIds

    def directive_usesEastEdgeReuse(self, directive: WiringDirective) -> bool:
        """Return whether one resolved directive uses east-edge bundle reuse.

        Args:
            directive (WiringDirective): The directive being queried.

        Returns:
            bool: ``True`` when the directive should bypass general manifold
                endpoint allocation and reuse existing east-edge bundles.
        """
        return id(directive) in self.eastEdgeReuseDirectiveIds

    def _routedEndpointCounts_compute(self) -> dict[str, int]:
        """Compute endpoint counts that actually enter the routed manifold.

        Returns:
            dict[str, int]: Per-endpoint routed longitude counts excluding
            east-edge reuse directives.
        """
        routedCounts: dict[str, int] = {}
        directive: WiringDirective
        for directive in self.wiringDirectives:
            if self.directive_usesEastEdgeReuse(directive):
                continue
            placement: DirectivePlacement = self._directivePlacement_resolve(directive)
            self._endpointCounts_increment(routedCounts, placement)
        return routedCounts

    def _manifoldLongitudes_resolve(self, node: Node) -> None:
        """Assign manifold longitude columns and zone boundaries.

        Args:
            node (Node): The chip node whose manifold columns are being placed.

        Returns:
            None: Longitude columns and zone bounds are updated in place.
        """
        x0: int = node.x
        rx: int = x0 + node.ow - 1
        routedCounts: dict[str, int] = self._routedEndpointCounts_compute()
        leftPorts: list[str] = sorted(
            port for port in routedCounts if self.endpoint_side(port) == "L"
        )
        rightPorts: list[str] = sorted(
            port for port in routedCounts if self.endpoint_side(port) == "R"
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
            routedCounts,
        )

        self.leftZoneInnerX = leftLongStart + 2 * vTrackL
        self.rightZoneInnerX = rightLongStart + 2 - 2 * vTrackR

    def _anchorRows_resolve(self) -> None:
        """Assign anchor rows for each manifold endpoint.

        Returns:
            None: Anchor-row assignments are updated in place.
        """
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
        """Collapse unit-density endpoints to wall-flush pass-through anchors.

        Returns:
            None: Unit-port state and anchor rows are updated in place.
        """
        if config.passThroughAllowed:
            port: str
            for port in self.lCounts:
                if self.lCounts[port] == 1:
                    self.unitPorts.add(port)
                    self.allAnchorRows[port] = [self.endpoint_wallRow(port)]

    def _manifoldGeometry_resolve(self, node: Node) -> None:
        """Resolve manifold-only geometry after directive classification.

        Args:
            node (Node): The chip node whose manifold geometry is being resolved.

        Returns:
            None: Manifold counts, longitudes, anchors, and aliases are updated
            in place.
        """
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
        """Assign stable compact aliases to visible internal labels.

        Returns:
            None: Internal alias assignments are updated in place.
        """
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
        """Resolve all Stage 2 geometry once absolute rows are known.

        Args:
            node (Node): The chip node whose geometry is being finalized.
            y0 (int): Absolute top row of the chip.
            entryRows (dict[int, int]): Resolved west entry rows by parent binding.
            returnRows (dict[int, int]): Resolved west return rows by parent binding.

        Returns:
            None: Stage 2 wall rows, directive classifications, and manifold
            geometry are updated in place.
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
        """Return the wall row for a display label.

        Args:
            port (str): Display label to resolve.
            y0 (int): Absolute top row of the chip, used for fallback.

        Returns:
            int: Resolved wall row for the label.
        """
        side: str = self.port_side(port)
        base = self.leftWallRows if side == "L" else self.rightWallRows
        return (base.get(port) or [y0 + 3])[0]

    def _wiringRow_get(self, name: str, role: str, y0: int) -> int:
        """Resolve a typed source or destination wall row.

        Args:
            name (str): Display label for the endpoint.
            role (str): Endpoint role, ``"src"`` or ``"dst"``.
            y0 (int): Absolute top row of the chip, used for fallback.

        Returns:
            int: Resolved wall row for the typed endpoint.
        """
        side: str = self.wiring_side(name, role)
        base = self.leftWallRows if side == "L" else self.rightWallRows
        return (base.get(name) or [y0 + 3])[0]

    def _directivePlacement_resolve(
        self,
        directive: WiringDirective,
    ) -> DirectivePlacement:
        """Resolve one directive against authoritative Stage 2 wall rows.

        Args:
            directive (WiringDirective): Directive to resolve.

        Returns:
            DirectivePlacement: Stage 2 placement and endpoint-kind information for
            the directive.
        """
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
        """Resolve source and destination sides and rows for a directive.

        Args:
            directive (WiringDirective): Directive whose endpoints are requested.

        Returns:
            tuple[str, str, int, int]: Source side, destination side, source row,
            and destination row.
        """
        placement: DirectivePlacement = self._directivePlacement_resolve(directive)
        return (
            placement.srcSide,
            placement.dstSide,
            placement.srcRow,
            placement.dstRow,
        )

    def directive_endpointKeys(self, directive: WiringDirective) -> tuple[str, str]:
        """Return canonical manifold endpoint keys for a directive.

        Args:
            directive (WiringDirective): Directive whose endpoint keys are needed.

        Returns:
            tuple[str, str]: Source endpoint key and destination endpoint key.
        """
        placement: DirectivePlacement = self._directivePlacement_resolve(directive)
        return placement.srcKey, placement.dstKey

    def directive_routeClass(self, directive: WiringDirective) -> str:
        """Return the route class for a resolved directive.

        Args:
            directive (WiringDirective): Directive whose route class is needed.

        Returns:
            str: Route class, ``"data"`` or ``"thread"``.
        """
        return directive.routeClass

    def directive_isThread(self, directive: WiringDirective) -> bool:
        """Return whether a resolved directive is a thread route.

        Args:
            directive (WiringDirective): Directive whose route class is needed.

        Returns:
            bool: ``True`` when the directive is a thread route.
        """
        return directive.routeClass == "thread"

    def directive_isData(self, directive: WiringDirective) -> bool:
        """Return whether a resolved directive is a data/dependency route.

        Args:
            directive (WiringDirective): Directive whose route class is needed.

        Returns:
            bool: ``True`` when the directive is a data route.
        """
        return directive.routeClass == "data"

    def endpoint_side(self, endpointKey: str) -> str:
        """Return wall side from a manifold endpoint key.

        Args:
            endpointKey (str): Canonical manifold endpoint key.

        Returns:
            str: ``"L"`` or ``"R"`` extracted from the key.
        """
        return endpointKey.split("|", 2)[0]

    def endpoint_kind(self, endpointKey: str) -> str:
        """Return endpoint kind from a manifold endpoint key.

        Args:
            endpointKey (str): Canonical manifold endpoint key.

        Returns:
            str: ``"sig"`` or ``"ret"`` extracted from the key.
        """
        return endpointKey.split("|", 2)[1]

    def endpoint_display(self, endpointKey: str) -> str:
        """Return the visible label from a manifold endpoint key.

        Args:
            endpointKey (str): Canonical manifold endpoint key.

        Returns:
            str: Visible display label extracted from the key.
        """
        return endpointKey.split("|", 2)[2]

    def endpoint_internalDisplay(self, endpointKey: str) -> str:
        """Return the visible internal anchor label for an endpoint key.

        Args:
            endpointKey (str): Canonical manifold endpoint key.

        Returns:
            str: Alias or decorated display label used for internal anchors.
        """
        if self.aliasInternalLabels:
            alias: str | None = self.internalLabelAliases.get(endpointKey)
            if alias is not None:
                return alias
        return _anchor_display(self.endpoint_display(endpointKey))

    def endpoint_isSignal(self, endpointKey: str) -> bool:
        """Check whether an endpoint key represents a signal endpoint.

        Args:
            endpointKey (str): Canonical manifold endpoint key.

        Returns:
            bool: ``True`` when the endpoint kind is ``"sig"``.
        """
        return self.endpoint_kind(endpointKey) == "sig"

    def endpoint_wallRow(self, endpointKey: str) -> int:
        """Return the concrete wall row for a manifold endpoint key.

        Args:
            endpointKey (str): Canonical manifold endpoint key.

        Returns:
            int: Concrete wall row for the endpoint.
        """
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
        """Return the absolute wall row for a label or endpoint key.

        Args:
            name (str): Display label or canonical endpoint key.

        Returns:
            int: Absolute wall row for the requested endpoint.
        """
        if not self.resolved:
            raise RuntimeError("wall_row() requires Stage 2: call resolve() first")
        if "|" in name:
            return self.endpoint_wallRow(name)
        return self._wallRow_get(name, self.y0)

    def wiring_row(self, name: str, role: str) -> int:
        """Return the typed wall row for a source or destination label.

        Args:
            name (str): Display label for the endpoint.
            role (str): Endpoint role, ``"src"`` or ``"dst"``.

        Returns:
            int: Absolute wall row for the typed endpoint.
        """
        if not self.resolved:
            raise RuntimeError("wiring_row() requires Stage 2: call resolve() first")
        return self._wiringRow_get(name, role, self.y0)
