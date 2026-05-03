"""Board-domain geometric doctrine.

This module is the intended home for invariant board layout and routing rules.
The board package now carries enough geometry responsibility that boundary
policy must also live here explicitly:

- routing sense
- minimum cross-bar span
- effective boundary policy
- explicit padding used after the furthest visible label/stub extent
- canonical zone geometry specification (`BoardGeometrySpec`)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.board.invariants import ZoneSymbolicInvariants
from signalflow.board.types import BoardSense
from signalflow.config.board_defaults import boardGeometryConfig


class EffectiveBoundaryMode(str, Enum):
    """Policy for computing effective routed module boundaries.

    `CONTENT_ONLY`
        Boundaries hug only the literal chip box content. This is useful as a
        low-level fallback but is generally not what users want visually.

    `LABEL_AWARE_MODULE_BOX`
        Boundaries are built from the full placed chip drawing extents, which
        already include terminal labels and stubs, then expanded by configured
        padding. This matches the current world-render module-box behavior while
        making it first-class board geometry.
    """

    CONTENT_ONLY = "content_only"
    LABEL_AWARE_MODULE_BOX = "label_aware_module_box"


class BoardChipPlacementPolicy(str, Enum):
    """Policy for positioning chip stacks within one terminal-side band.

    `NORTH`
        Pack the chip stack from the north/top edge of the terminal band.

    `SOUTH`
        Pack the chip stack from the south/bottom edge of the terminal band.

    `CENTROIDAL`
        Center the used chip stack within the available terminal band.
    """

    NORTH = "north"
    SOUTH = "south"
    CENTROIDAL = "centroidal"


class BoardRelaxationSymmetry(str, Enum):
    """Policy for realization-time paired-band movement.

    `MINIMAL`
        Move only the band family required to relieve current pressure.

    `SYMMETRIC`
        When one paired band family moves, move the opposite family by the
        mirrored amount as well.
    """

    MINIMAL = "minimal"
    SYMMETRIC = "symmetric"


@dataclass(frozen=True)
class BoardMaterializePolicy:
    """Policy object controlling board realization-time behavior.

    Attributes:
        relaxationSymmetry: Whether paired latitude bands should relax in a
            minimal one-sided manner or as a mirrored symmetric pair.
        skipRelaxation: When True, centroid relaxation is skipped entirely and
            the initial region frames are used as-is for realization.
    """

    relaxationSymmetry: BoardRelaxationSymmetry = (
        BoardRelaxationSymmetry.MINIMAL
    )
    skipRelaxation: bool = False


@dataclass(frozen=True)
class BoardAreaGeometry:
    """One named region with its computed position in the board geometry stack.

    Produced by `BoardGeometrySpec.wteLayout_build()`. Each instance
    represents one named band or region with its world-coordinate horizontal
    position derived from the cascade arithmetic of the owning spec.

    Vertical extent is zero until `ZoneSymbolicInvariants` is available to
    supply chip-driven vertical bounds.
    """

    name: str
    horizontalStart: int
    horizontalSpan: int
    verticalStart: int = 0
    verticalSpan: int = 0

    @property
    def horizontalEnd(self) -> int:
        """Inclusive horizontal end coordinate."""
        return self.horizontalStart + self.horizontalSpan - 1

    @property
    def verticalEnd(self) -> int:
        """Inclusive vertical end coordinate."""
        return self.verticalStart + self.verticalSpan - 1

    def span_sprint(self) -> str:
        """Return a single-line human-readable span description."""
        return (
            f"{self.name:42} "
            f"col={self.horizontalStart:4}..{self.horizontalEnd:4}  "
            f"span={self.horizontalSpan}w"
        )


@dataclass(frozen=True)
class RingGeometrySpec:
    """Span knobs for one routing ring (intra or extra).

    Both the intra substrate and the extra perimeter ring share the same
    structural shape:

        wTerminal | wFan | wLong | [content] | eLong | eFan | eTerminal
                          ↑______ nSpan / sSpan ______↑

    Field names are compass-relative (world coordinates), not sense-relative.
    The routing role of nSpan/sSpan depends on the kernel sense:

    - WTE / ETW: wLong/eLong are longitude channels; nSpan/sSpan are latitude
    - NTS / STN: nSpan/sSpan are longitude channels; wLong/eLong are latitude

    For the intra ring, wTerminalSpan/eTerminalSpan and wFanSpan/eFanSpan are
    simple policy floors (placement constants _TERMINAL_SPAN, _FAN_IN_OUT_SPAN).
    wLongSpan, eLongSpan, nSpan and sSpan default to 0 — sentinel meaning
    "solver-derived": the placement solver and ZoneSymbolicInvariants own those
    floors and will supply the real values.

    For the extra ring wTerminalSpan and eTerminalSpan are 0 — there is no
    chip terminal layer in the extra perimeter.
    """

    wTerminalSpan: int = 0
    wFanSpan: int = 0
    wLongSpan: int = 0
    nSpan: int = 0
    sSpan: int = 0
    eLongSpan: int = 0
    eFanSpan: int = 0
    eTerminalSpan: int = 0

    def ring_sprint(self, indent: str = "  ") -> str:
        """Return a human-readable summary of all span knobs."""
        i = indent
        return "\n".join(
            [
                f"{i}wTerminalSpan : {self.wTerminalSpan}",
                f"{i}wFanSpan      : {self.wFanSpan}",
                f"{i}wLongSpan     : {self.wLongSpan}",
                f"{i}nSpan         : {self.nSpan}",
                f"{i}sSpan         : {self.sSpan}",
                f"{i}eLongSpan     : {self.eLongSpan}",
                f"{i}eFanSpan      : {self.eFanSpan}",
                f"{i}eTerminalSpan : {self.eTerminalSpan}",
            ]
        )


def _intraRingFromConfig() -> RingGeometrySpec:
    """Build intra ring defaults from the geometry config singleton."""
    c = boardGeometryConfig
    return RingGeometrySpec(
        wTerminalSpan=c.intraWTerminalSpan,
        wFanSpan=c.intraWFanSpan,
        wLongSpan=0,  # sentinel: routing-demand floor owned by placement solver
        nSpan=0,  # sentinel: derived from signal count by ZoneSymbolicInvariants
        sSpan=0,  # sentinel: derived from signal count by ZoneSymbolicInvariants
        eLongSpan=0,  # sentinel: routing-demand floor owned by placement solver
        eFanSpan=c.intraEFanSpan,
        eTerminalSpan=c.intraETerminalSpan,
    )


def _extraRingFromConfig() -> RingGeometrySpec:
    """Build extra ring defaults from the geometry config singleton."""
    c = boardGeometryConfig
    return RingGeometrySpec(
        wTerminalSpan=0,
        wFanSpan=c.extraWFanSpan,
        wLongSpan=c.extraWLongSpan,
        nSpan=c.extraNSpan,
        sSpan=c.extraSSpan,
        eLongSpan=c.extraELongSpan,
        eFanSpan=c.extraEFanSpan,
        eTerminalSpan=0,
    )


@dataclass(frozen=True)
class BoardGeometrySpec:
    """Single authoritative source of truth for zone geometry spans.

    Composes an intra ring and an extra ring, each described by a
    `RingGeometrySpec`. The intra ring holds placement-policy floors
    (solver may widen them). The extra ring holds pure policy constants.

    Full horizontal stack for a WTE zone (west → east):

        extra.wLong | extra.wFan |
        intra.wTerminal | intra.wFan | intra.wLong | [courtyard] |
        intra.eLong | intra.eFan | intra.eTerminal |
        extra.eFan | extra.eLong

        ↑_____________ extra.nSpan / extra.sSpan row span ______________↑
    """

    intra: RingGeometrySpec = field(default_factory=_intraRingFromConfig)
    extra: RingGeometrySpec = field(default_factory=_extraRingFromConfig)

    def layout_build(
        self,
        sense: BoardSense,
        xAnchor: int = 0,
        intraWidth: int = 0,
    ) -> list[BoardAreaGeometry]:
        """Derive the horizontal layout as an ordered list of named areas.

        Accumulates spans rightward from `xAnchor`. The intra substrate is
        decomposed into its constituent ring columns. When `intraWidth` is
        non-zero the courtyard (innermost gap between wLong and eLong) is
        derived as the residual; when zero the courtyard area is omitted.

        Args:
            sense: Routing sense — WTE/ETW produce a horizontal west→east
                stack. NTS/STN raises `NotImplementedError` (vertical layout
                is a future extension).
            xAnchor: World column anchoring the west edge of `extra.wLong`.
                Pass `0` for relative/diagnostic output.
            intraWidth: Total column span of the intra substrate (between the
                two extra fan bands). When non-zero the courtyard is derived
                as the residual after all other intra columns are subtracted.

        Returns:
            Ordered list of `BoardAreaGeometry` from west to east.
        """
        if sense in (BoardSense.NORTH_TO_SOUTH, BoardSense.SOUTH_TO_NORTH):
            raise NotImplementedError(
                f"layout_build for {sense} not yet implemented"
            )

        areas: list[BoardAreaGeometry] = []
        cursor: int = xAnchor
        e = self.extra
        i = self.intra

        def _add(name: str, span: int) -> None:
            nonlocal cursor
            areas.append(
                BoardAreaGeometry(
                    name=name,
                    horizontalStart=cursor,
                    horizontalSpan=span,
                )
            )
            cursor += span

        _add("extra/wLong", e.wLongSpan)
        _add("extra/wFan", e.wFanSpan)
        _add("intra/wTerminal", i.wTerminalSpan)
        _add("intra/wFan", i.wFanSpan)
        _add("intra/wLong", i.wLongSpan)

        if intraWidth > 0:
            fixed = (
                i.wTerminalSpan
                + i.wFanSpan
                + i.wLongSpan
                + i.eLongSpan
                + i.eFanSpan
                + i.eTerminalSpan
            )
            courtyard = intraWidth - fixed
            if courtyard > 0:
                _add("intra/courtyard", courtyard)

        _add("intra/eLong", i.eLongSpan)
        _add("intra/eFan", i.eFanSpan)
        _add("intra/eTerminal", i.eTerminalSpan)
        _add("extra/eFan", e.eFanSpan)
        _add("extra/eLong", e.eLongSpan)

        return areas

    def with_invariants(
        self, invariants: ZoneSymbolicInvariants
    ) -> BoardGeometrySpec:
        """Return a new spec with intra solver-derived fields lifted from invariants.

        The 0-sentinel fields in the intra ring (wLongSpan, eLongSpan, nSpan,
        sSpan) are replaced by the corresponding placement-lifted minimums from
        `ZoneSymbolicInvariants`. Policy floors (terminal, fan) are unchanged.
        The extra ring is carried through unmodified.

        Args:
            invariants: Circuit-derived and placement-lifted zone constraints
                from `ZoneSymbolicInvariants.build()`.

        Returns:
            New `BoardGeometrySpec` with intra ring solver-derived spans
            populated. Policy floors are preserved via `max()`.
        """
        i = self.intra
        upgraded_intra = RingGeometrySpec(
            wTerminalSpan=i.wTerminalSpan,
            wFanSpan=i.wFanSpan,
            wLongSpan=max(i.wLongSpan, invariants.minWLongSpan),
            nSpan=max(i.nSpan, invariants.latRows),
            sSpan=max(i.sSpan, invariants.latRows),
            eLongSpan=max(i.eLongSpan, invariants.minELongSpan),
            eFanSpan=i.eFanSpan,
            eTerminalSpan=i.eTerminalSpan,
        )
        return BoardGeometrySpec(intra=upgraded_intra, extra=self.extra)

    def areas_sprint(self) -> str:
        """Return a human-readable summary of both ring specs."""
        lines: list[str] = [
            "BoardGeometrySpec:",
            "  intra:",
            self.intra.ring_sprint(indent="    "),
            "  extra:",
            self.extra.ring_sprint(indent="    "),
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class BoardDoctrine:
    """Geometric doctrine that constrains board layout and realization."""

    sense: BoardSense
    minimumCrossbarSpan: int = 0
    effectiveBoundaryMode: EffectiveBoundaryMode = (
        EffectiveBoundaryMode.LABEL_AWARE_MODULE_BOX
    )
    moduleBoundaryPaddingCells: int = 1
    chipPlacementPolicy: BoardChipPlacementPolicy = (
        BoardChipPlacementPolicy.CENTROIDAL
    )
    """Explicit padding used around effective terminal/module envelopes.

    This single value is the board-domain source of truth for the clearance
    inserted after visible terminal labels/stubs. The effective-board builder
    uses it for both:
    - outward expansion of effective module boundaries
    - inward routing-facing chip inset inside those boundaries

    That keeps visible label clearance out of incidental draw-line whitespace.
    """
