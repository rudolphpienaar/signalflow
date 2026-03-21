"""Route-obligation models for the new SignalFlow engine.

This module defines the first routing-input layer above placement planning.
Obligations describe what connectivity must be realized, not how geometry is
laid out to realize it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.chip import (
    ChipInternalWiringDirective,
    ChipPortDeclaration,
    ChipRef,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import Result, resultErr_build, resultOk_build


class RouteObligationScope(Enum):
    """Geometric scope of one routing obligation."""

    CHIP_INTERNAL = "chip_internal"
    ZONE_LOCAL = "zone_local"
    SEAM_CROSSING = "seam_crossing"
    GRID_LONG_HAUL = "grid_long_haul"


class ZoneLocalGeometryKind(Enum):
    """Geometry owner for one same-zone call obligation."""

    SAME_SIDE_LOCAL = "same_side_local"
    INTRA_TRANSVERSE_FORWARD = "intra_transverse_forward"
    INTER_PERIMETER_BACKEDGE = "inter_perimeter_backedge"


@dataclass(frozen=True)
class CallRouteObligation:
    """Connectivity obligation induced by one parent-to-child call."""

    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    childCallIndex: int
    routeObligationScope: RouteObligationScope
    zoneLocalGeometryKind: ZoneLocalGeometryKind | None = None
    sourcePortDeclaration: ChipPortDeclaration | None = None


@dataclass(frozen=True)
class ChipInternalRouteObligation:
    """Connectivity obligation induced by one chip-internal wiring directive."""

    chipRef: ChipRef
    chipInternalWiringDirective: ChipInternalWiringDirective
    routeObligationScope: RouteObligationScope = RouteObligationScope.CHIP_INTERNAL


@dataclass(frozen=True)
class CallRouteObligationSet:
    """Modeled collection of call-induced routing obligations."""

    callRouteObligations: tuple[CallRouteObligation, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class ChipInternalRouteObligationSet:
    """Modeled collection of chip-internal routing obligations."""

    chipInternalRouteObligations: tuple[ChipInternalRouteObligation, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class RouteObligationSet:
    """Complete routing-obligation set for one circuit solve."""

    callRouteObligationSet: CallRouteObligationSet = field(
        default_factory=CallRouteObligationSet
    )
    chipInternalRouteObligationSet: ChipInternalRouteObligationSet = field(
        default_factory=ChipInternalRouteObligationSet
    )


def callRouteObligationSetResult_build(
    callRouteObligations: tuple[CallRouteObligation, ...],
) -> Result[CallRouteObligationSet]:
    """Build a validated call-route obligation set."""

    obligationKeys: tuple[tuple[ChipRef, ChipRef, int], ...] = tuple(
        (
            callRouteObligation.sourceChipRef,
            callRouteObligation.destinationChipRef,
            callRouteObligation.childCallIndex,
        )
        for callRouteObligation in callRouteObligations
    )
    if len(set(obligationKeys)) != len(obligationKeys):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.obligation.call_set.duplicate_call_obligation",
            message=(
                "Call route obligations must be unique by source, "
                "destination, and child index"
            ),
        )
        return resultErr_build()
    return resultOk_build(
        CallRouteObligationSet(callRouteObligations=callRouteObligations)
    )


def chipInternalRouteObligationSetResult_build(
    chipInternalRouteObligations: tuple[ChipInternalRouteObligation, ...],
) -> Result[ChipInternalRouteObligationSet]:
    """Build a validated chip-internal obligation set."""

    return resultOk_build(
        ChipInternalRouteObligationSet(
            chipInternalRouteObligations=chipInternalRouteObligations
        )
    )


def routeObligationSetResult_build(
    callRouteObligationSet: CallRouteObligationSet,
    chipInternalRouteObligationSet: ChipInternalRouteObligationSet,
) -> Result[RouteObligationSet]:
    """Build the complete route-obligation set."""

    return resultOk_build(
        RouteObligationSet(
            callRouteObligationSet=callRouteObligationSet,
            chipInternalRouteObligationSet=chipInternalRouteObligationSet,
        )
    )
