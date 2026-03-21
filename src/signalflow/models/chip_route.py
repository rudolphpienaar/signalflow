"""Chip-internal routing models for the new SignalFlow engine.

This module defines the first solved artifact below `internal_wiring`
obligations. It intentionally stops short of cell-by-cell render geometry. The
goal of this layer is to parse one declarative internal-wiring directive,
resolve it against canonical chip terminals, and classify the local route kind
that later geometry solvers will realize.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.chip import (
    ChipInternalWiringDirective,
    ChipRef,
    ChipTerminal,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.directional_orientation import DirectionalOrientation
from signalflow.models.result import (
    Result,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.routing_owner import ChipLocalRoutingOwner

ChipInternalRouteOrientation = DirectionalOrientation


class ChipInternalRouteClass(Enum):
    """Declared internal route class."""

    DATA = "data"
    THREAD = "thread"


class ChipInternalRouteSemantics(Enum):
    """Declared internal route semantics for thread-class routes."""

    PURE = "pure"
    COMPUTE = "compute"


class ChipInternalRouteSolveKind(Enum):
    """Local geometric class for one solved chip-internal route."""

    TRANSVERSE_MANIFOLD = "transverse_manifold"
    SAME_SIDE_LOCAL = "same_side_local"


@dataclass(frozen=True)
class ChipInternalRouteDirectiveSpec:
    """Parsed directive specification for one `internal_wiring` statement."""

    chipInternalWiringDirective: ChipInternalWiringDirective
    sourceTerminalName: str
    destinationTerminalName: str
    routeOrientation: ChipInternalRouteOrientation | None = None
    routeClass: ChipInternalRouteClass = ChipInternalRouteClass.DATA
    routeSemantics: ChipInternalRouteSemantics | None = None
    colorName: str | None = None


@dataclass(frozen=True)
class ChipInternalSolvedRoute:
    """First solved chip-internal route artifact."""

    chipRef: ChipRef
    owningChipLocalRoutingOwner: ChipLocalRoutingOwner
    chipInternalRouteDirectiveSpec: ChipInternalRouteDirectiveSpec
    sourceTerminal: ChipTerminal
    destinationTerminal: ChipTerminal
    solveKind: ChipInternalRouteSolveKind


@dataclass(frozen=True)
class ChipInternalSolvedRouteSet:
    """Modeled collection of solved chip-internal routes."""

    chipInternalSolvedRoutes: tuple[ChipInternalSolvedRoute, ...] = field(
        default_factory=tuple
    )

    def routesForChip_get(
        self,
        chipRef: ChipRef,
    ) -> tuple[ChipInternalSolvedRoute, ...]:
        """Return all solved internal routes for one chip."""

        return tuple(
            chipInternalSolvedRoute
            for chipInternalSolvedRoute in self.chipInternalSolvedRoutes
            if chipInternalSolvedRoute.chipRef == chipRef
        )


def chipInternalRouteDirectiveSpecResult_build(
    chipInternalWiringDirective: ChipInternalWiringDirective,
    sourceTerminalName: str,
    destinationTerminalName: str,
    routeOrientation: ChipInternalRouteOrientation | None = None,
    routeClass: ChipInternalRouteClass = ChipInternalRouteClass.DATA,
    routeSemantics: ChipInternalRouteSemantics | None = None,
    colorName: str | None = None,
) -> Result[ChipInternalRouteDirectiveSpec]:
    """Build one validated parsed internal-route directive spec."""

    resolvedRouteSemantics: ChipInternalRouteSemantics | None = routeSemantics
    if routeClass is ChipInternalRouteClass.THREAD and resolvedRouteSemantics is None:
        resolvedRouteSemantics = ChipInternalRouteSemantics.COMPUTE
    if routeClass is ChipInternalRouteClass.DATA and resolvedRouteSemantics is not None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.directive.data_route_has_thread_semantics",
            message="Data-class internal routes may not declare thread semantics",
            context=(
                chipInternalWiringDirective.wiringDeclaration,
                resolvedRouteSemantics.value,
            ),
        )
        return resultErr_build()
    return resultOk_build(
        ChipInternalRouteDirectiveSpec(
            chipInternalWiringDirective=chipInternalWiringDirective,
            sourceTerminalName=sourceTerminalName,
            destinationTerminalName=destinationTerminalName,
            routeOrientation=routeOrientation,
            routeClass=routeClass,
            routeSemantics=resolvedRouteSemantics,
            colorName=colorName,
        )
    )


def chipInternalSolvedRouteResult_build(
    chipRef: ChipRef,
    owningChipLocalRoutingOwner: ChipLocalRoutingOwner,
    chipInternalRouteDirectiveSpec: ChipInternalRouteDirectiveSpec,
    sourceTerminal: ChipTerminal,
    destinationTerminal: ChipTerminal,
    solveKind: ChipInternalRouteSolveKind,
) -> Result[ChipInternalSolvedRoute]:
    """Build one validated solved chip-internal route."""

    if owningChipLocalRoutingOwner.chipRef != chipRef:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.solved_route.owner_chip_mismatch",
            message=(
                "Chip-internal solved route must be owned by the same chip-local "
                "routing owner"
            ),
            context=(
                chipRef.chipId.moduleName,
                chipRef.chipId.functionName,
            ),
        )
        return resultErr_build()
    return resultOk_build(
        ChipInternalSolvedRoute(
            chipRef=chipRef,
            owningChipLocalRoutingOwner=owningChipLocalRoutingOwner,
            chipInternalRouteDirectiveSpec=chipInternalRouteDirectiveSpec,
            sourceTerminal=sourceTerminal,
            destinationTerminal=destinationTerminal,
            solveKind=solveKind,
        )
    )


def chipInternalSolvedRouteSetResult_build(
    chipInternalSolvedRoutes: tuple[ChipInternalSolvedRoute, ...],
) -> Result[ChipInternalSolvedRouteSet]:
    """Build the solved chip-internal route set."""

    return resultOk_build(
        ChipInternalSolvedRouteSet(
            chipInternalSolvedRoutes=chipInternalSolvedRoutes
        )
    )
