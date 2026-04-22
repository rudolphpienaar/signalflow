"""Chip-local internal-route solving for the new SignalFlow engine."""

from __future__ import annotations

from signalflow.models import (
    Chip,
    ChipInternalRouteClass,
    ChipInternalRouteDirectiveSpec,
    ChipInternalRouteObligation,
    ChipInternalRouteObligationSet,
    ChipInternalRouteOrientation,
    ChipInternalRouteSemantics,
    ChipInternalRouteSolveKind,
    ChipInternalSolvedRoute,
    ChipInternalSolvedRouteSet,
    ChipTerminal,
    ChipTerminalSide,
    CircuitDocument,
    DirectionalOrientation,
    Result,
    chipInternalRouteDirectiveSpecResult_build,
    chipInternalSolvedRouteResult_build,
    chipInternalSolvedRouteSetResult_build,
    chipLocalRoutingOwner_build,
    destinationSideForDirectionalOrientation_get,
    directionalOrientationResult_buildFromSides,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
    sourceSideForDirectionalOrientation_get,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.routing.attach_side import (
    AttachEndpointRole,
    preferredTerminalSidesForEndpoint_get,
)


def chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet(
    circuitDocument: CircuitDocument,
    chipInternalRouteObligationSet: ChipInternalRouteObligationSet,
) -> Result[ChipInternalSolvedRouteSet]:
    """Build solved chip-local routes from internal-wiring obligations."""

    chipInternalSolvedRoutesMutable: list[ChipInternalSolvedRoute] = []
    chipInternalRouteObligation: ChipInternalRouteObligation
    for (
        chipInternalRouteObligation
    ) in chipInternalRouteObligationSet.chipInternalRouteObligations:
        chipInternalSolvedRouteResult = (
            _chipInternalSolvedRouteResult_buildFromObligation(
                circuitDocument=circuitDocument,
                chipInternalRouteObligation=chipInternalRouteObligation,
            )
        )
        if not result_isOkCheck(chipInternalSolvedRouteResult):
            return resultErr_build()
        chipInternalSolvedRoutesMutable.append(
            chipInternalSolvedRouteResult.value
        )
    return chipInternalSolvedRouteSetResult_build(
        chipInternalSolvedRoutes=tuple(chipInternalSolvedRoutesMutable)
    )


def _chipInternalSolvedRouteResult_buildFromObligation(
    circuitDocument: CircuitDocument,
    chipInternalRouteObligation: ChipInternalRouteObligation,
) -> Result[ChipInternalSolvedRoute]:
    """Build one solved chip-local route from one internal obligation."""

    chipResult = circuitDocument.circuitChipSet.chipResult_get(
        chipInternalRouteObligation.chipRef.chipId
    )
    if not result_isOkCheck(chipResult):
        return resultErr_build()

    chipInternalRouteDirectiveSpecResult: Result[
        ChipInternalRouteDirectiveSpec
    ] = _chipInternalRouteDirectiveSpecResult_buildFromObligation(
        chipInternalRouteObligation=chipInternalRouteObligation
    )
    if not result_isOkCheck(chipInternalRouteDirectiveSpecResult):
        return resultErr_build()

    sourceTerminalResult = _terminalResult_buildForDirectiveEndpoint(
        chip=chipResult.value,
        terminalName=chipInternalRouteDirectiveSpecResult.value.sourceTerminalName,
        explicitTerminalSide=_sourceSide_buildForOrientation(
            chipInternalRouteDirectiveSpecResult.value.routeOrientation
        ),
        sourceEndpoint=True,
        directiveText=(
            chipInternalRouteDirectiveSpecResult.value.chipInternalWiringDirective.wiringDeclaration
        ),
    )
    if not result_isOkCheck(sourceTerminalResult):
        return resultErr_build()

    destinationTerminalResult = _terminalResult_buildForDirectiveEndpoint(
        chip=chipResult.value,
        terminalName=(
            chipInternalRouteDirectiveSpecResult.value.destinationTerminalName
        ),
        explicitTerminalSide=_destinationSide_buildForOrientation(
            chipInternalRouteDirectiveSpecResult.value.routeOrientation
        ),
        sourceEndpoint=False,
        directiveText=(
            chipInternalRouteDirectiveSpecResult.value.chipInternalWiringDirective.wiringDeclaration
        ),
    )
    if not result_isOkCheck(destinationTerminalResult):
        return resultErr_build()

    inferredOrientationResult = _routeOrientationResult_buildFromTerminals(
        sourceTerminal=sourceTerminalResult.value,
        destinationTerminal=destinationTerminalResult.value,
    )
    if not result_isOkCheck(inferredOrientationResult):
        return resultErr_build()

    if (
        chipInternalRouteDirectiveSpecResult.value.routeOrientation is not None
        and inferredOrientationResult.value is not None
        and chipInternalRouteDirectiveSpecResult.value.routeOrientation
        is not inferredOrientationResult.value
    ):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.directive.orientation_terminal_mismatch",
            message=(
                "Explicit chip-internal route orientation does not match the "
                "resolved terminal sides"
            ),
            context=(
                chipInternalRouteDirectiveSpecResult.value.chipInternalWiringDirective.wiringDeclaration,
                chipInternalRouteDirectiveSpecResult.value.routeOrientation.value,
            ),
        )
        return resultErr_build()

    solveKind: ChipInternalRouteSolveKind = _solveKind_buildFromTerminals(
        sourceTerminal=sourceTerminalResult.value,
        destinationTerminal=destinationTerminalResult.value,
    )
    routeOrientation: ChipInternalRouteOrientation | None = (
        chipInternalRouteDirectiveSpecResult.value.routeOrientation
        or inferredOrientationResult.value
    )
    normalizedDirectiveSpecResult = chipInternalRouteDirectiveSpecResult_build(
        chipInternalWiringDirective=(
            chipInternalRouteDirectiveSpecResult.value.chipInternalWiringDirective
        ),
        sourceTerminalName=chipInternalRouteDirectiveSpecResult.value.sourceTerminalName,
        destinationTerminalName=(
            chipInternalRouteDirectiveSpecResult.value.destinationTerminalName
        ),
        routeOrientation=routeOrientation,
        routeClass=chipInternalRouteDirectiveSpecResult.value.routeClass,
        routeSemantics=chipInternalRouteDirectiveSpecResult.value.routeSemantics,
        colorName=chipInternalRouteDirectiveSpecResult.value.colorName,
    )
    if not result_isOkCheck(normalizedDirectiveSpecResult):
        return resultErr_build()

    return chipInternalSolvedRouteResult_build(
        chipRef=chipInternalRouteObligation.chipRef,
        owningChipLocalRoutingOwner=chipLocalRoutingOwner_build(
            chipInternalRouteObligation.chipRef
        ),
        chipInternalRouteDirectiveSpec=normalizedDirectiveSpecResult.value,
        sourceTerminal=sourceTerminalResult.value,
        destinationTerminal=destinationTerminalResult.value,
        solveKind=solveKind,
    )


def _chipInternalRouteDirectiveSpecResult_buildFromObligation(
    chipInternalRouteObligation: ChipInternalRouteObligation,
) -> Result[ChipInternalRouteDirectiveSpec]:
    """Parse one raw internal-wiring directive into typed directive spec."""

    directiveText: str = chipInternalRouteObligation.chipInternalWiringDirective.wiringDeclaration
    directiveParts: list[str] = directiveText.split(":")
    if len(directiveParts) < 2:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.directive.too_few_parts",
            message=(
                "Chip-internal wiring directives must declare at least src and dst"
            ),
            context=(directiveText,),
        )
        return resultErr_build()

    routeOrientation: ChipInternalRouteOrientation | None = None
    routeClass: ChipInternalRouteClass = ChipInternalRouteClass.DATA
    routeSemantics: ChipInternalRouteSemantics | None = None
    colorName: str | None = None
    modifierToken: str
    for modifierToken in directiveParts[2:]:
        if modifierToken in {"WE", "EW", "NS", "SN"}:
            if routeOrientation is not None:
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.chip_solver.directive.duplicate_orientation",
                    message=(
                        "Chip-internal wiring directives may declare at most one "
                        "orientation token"
                    ),
                    context=(directiveText,),
                )
                return resultErr_build()
            routeOrientation = ChipInternalRouteOrientation(modifierToken)
            continue
        if modifierToken in {"data", "thread"}:
            if routeClass is not ChipInternalRouteClass.DATA:
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.chip_solver.directive.duplicate_route_class",
                    message=(
                        "Chip-internal wiring directives may declare at most one "
                        "route class"
                    ),
                    context=(directiveText,),
                )
                return resultErr_build()
            routeClass = ChipInternalRouteClass(modifierToken)
            continue
        if modifierToken in {"pure", "compute"}:
            if routeSemantics is not None:
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.chip_solver.directive.duplicate_route_semantics",
                    message=(
                        "Chip-internal wiring directives may declare at most one "
                        "route semantics token"
                    ),
                    context=(directiveText,),
                )
                return resultErr_build()
            routeSemantics = ChipInternalRouteSemantics(modifierToken)
            continue
        if modifierToken.startswith("color(") and modifierToken.endswith(")"):
            if colorName is not None:
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.chip_solver.directive.duplicate_color_modifier",
                    message=(
                        "Chip-internal wiring directives may declare at most one "
                        "color modifier"
                    ),
                    context=(directiveText,),
                )
                return resultErr_build()
            colorName = modifierToken[6:-1]
            if not colorName:
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.chip_solver.directive.invalid_color_modifier",
                    message="Chip-internal route color modifiers must be non-empty",
                    context=(directiveText,),
                )
                return resultErr_build()
            continue
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.directive.unknown_modifier",
            message="Chip-internal wiring directive contains an unknown modifier",
            context=(directiveText, modifierToken),
        )
        return resultErr_build()

    return chipInternalRouteDirectiveSpecResult_build(
        chipInternalWiringDirective=(
            chipInternalRouteObligation.chipInternalWiringDirective
        ),
        sourceTerminalName=directiveParts[0],
        destinationTerminalName=directiveParts[1],
        routeOrientation=routeOrientation,
        routeClass=routeClass,
        routeSemantics=routeSemantics,
        colorName=colorName,
    )


def _terminalResult_buildForDirectiveEndpoint(
    chip: Chip,
    terminalName: str,
    explicitTerminalSide: ChipTerminalSide | None,
    sourceEndpoint: bool,
    directiveText: str,
) -> Result[ChipTerminal]:
    """Resolve one directive endpoint against one canonical chip terminal set."""

    if explicitTerminalSide is not None:
        terminalResult = chip.chipTerminalSet.terminalForNameAndSideResult_get(
            terminalName=terminalName,
            terminalSide=explicitTerminalSide,
        )
        if not result_isOkCheck(terminalResult):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="routing.chip_solver.directive.explicit_side_terminal_missing",
                message=(
                    "Explicit chip-internal route orientation does not match an "
                    "available terminal"
                ),
                context=(
                    directiveText,
                    terminalName,
                    explicitTerminalSide.value,
                ),
            )
            return resultErr_build()
        return terminalResult

    preferredSides: tuple[ChipTerminalSide, ...] = (
        _preferredSides_buildForEndpoint(
            chip=chip,
            terminalName=terminalName,
            sourceEndpoint=sourceEndpoint,
        )
    )
    if len(preferredSides) == 1:
        return chip.chipTerminalSet.terminalForNameAndSideResult_get(
            terminalName=terminalName,
            terminalSide=preferredSides[0],
        )
    if len(preferredSides) > 1:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.directive.ambiguous_terminal_name_without_orientation",
            message=(
                "Chip-internal route endpoint is ambiguous without an explicit "
                "orientation token"
            ),
            context=(directiveText, terminalName),
        )
        return resultErr_build()

    matchingTerminals: tuple[ChipTerminal, ...] = (
        chip.chipTerminalSet.terminalsNamed_getAll(terminalName)
    )
    if not matchingTerminals:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.directive.terminal_name_missing",
            message="Chip-internal route references an unknown terminal name",
            context=(directiveText, terminalName),
        )
        return resultErr_build()
    if len(matchingTerminals) > 1:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.chip_solver.directive.ambiguous_terminal_name_without_orientation",
            message=(
                "Chip-internal route endpoint is ambiguous without an explicit "
                "orientation token"
            ),
            context=(directiveText, terminalName),
        )
        return resultErr_build()
    return resultOk_build(matchingTerminals[0])  # type: ignore[index]


def _preferredSides_buildForEndpoint(
    chip: Chip,
    terminalName: str,
    sourceEndpoint: bool,
) -> tuple[ChipTerminalSide, ...]:
    """Build preferred terminal sides from chip declaration roles.

    Both signal and return labels within one port declaration belong to the
    same wall as the port itself: input_ports → WEST, output_ports → EAST.
    """

    endpointRole: AttachEndpointRole = (
        AttachEndpointRole.SOURCE
        if sourceEndpoint
        else AttachEndpointRole.DESTINATION
    )
    return preferredTerminalSidesForEndpoint_get(
        chip=chip,
        terminalName=terminalName,
        endpointRole=endpointRole,
    )


def _sourceSide_buildForOrientation(
    routeOrientation: ChipInternalRouteOrientation | None,
) -> ChipTerminalSide | None:
    """Build the source-side constraint induced by one route orientation."""

    if routeOrientation is not None:
        return sourceSideForDirectionalOrientation_get(routeOrientation)
    return None


def _destinationSide_buildForOrientation(
    routeOrientation: ChipInternalRouteOrientation | None,
) -> ChipTerminalSide | None:
    """Build the destination-side constraint induced by one route orientation."""

    if routeOrientation is not None:
        return destinationSideForDirectionalOrientation_get(routeOrientation)
    return None


def _routeOrientationResult_buildFromTerminals(
    sourceTerminal: ChipTerminal,
    destinationTerminal: ChipTerminal,
) -> Result[ChipInternalRouteOrientation | None]:
    """Infer route orientation from resolved terminals when possible."""

    orientationResult: Result[DirectionalOrientation | None] = (
        directionalOrientationResult_buildFromSides(
            sourceSide=sourceTerminal.terminalSide,
            destinationSide=destinationTerminal.terminalSide,
        )
    )
    if not result_isOkCheck(orientationResult):
        return resultErr_build()
    return resultOk_build(orientationResult.value)


def _solveKind_buildFromTerminals(
    sourceTerminal: ChipTerminal,
    destinationTerminal: ChipTerminal,
) -> ChipInternalRouteSolveKind:
    """Build the first local route-shape classification from terminal sides."""

    if sourceTerminal.terminalSide is destinationTerminal.terminalSide:
        return ChipInternalRouteSolveKind.SAME_SIDE_INTERNAL
    return ChipInternalRouteSolveKind.TRANSVERSE_MANIFOLD
