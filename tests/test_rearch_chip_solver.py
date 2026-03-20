"""Tests for the first chip-local internal-route solver."""
from __future__ import annotations

from pathlib import Path

from yaml import safe_load

from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    ChipInternalRouteClass,
    ChipInternalRouteObligation,
    ChipInternalRouteObligationSet,
    ChipInternalRouteOrientation,
    ChipInternalRouteSemantics,
    ChipInternalRouteSolveKind,
    ChipTerminalSide,
    CircuitDocument,
    chipInternalRouteObligationSetResult_build,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet,
)


def chipInternalRouteObligationSet_buildFromCircuitDocument(
    circuitDocument: CircuitDocument,
) -> ChipInternalRouteObligationSet:
    """Build chip-internal obligations directly from canonical chips."""

    chipInternalRouteObligationsMutable: list[ChipInternalRouteObligation] = []
    for chip in circuitDocument.circuitChipSet.chips:
        for chipInternalWiringDirective in chip.internalWiringDirectiveSet.directives:
            chipInternalRouteObligationsMutable.append(
                ChipInternalRouteObligation(
                    chipRef=chip.chipRef_build(),
                    chipInternalWiringDirective=chipInternalWiringDirective,
                )
            )
    chipInternalRouteObligationSetResult = (
        chipInternalRouteObligationSetResult_build(
            tuple(chipInternalRouteObligationsMutable)
        )
    )
    assert result_isOkCheck(chipInternalRouteObligationSetResult)
    return chipInternalRouteObligationSetResult.value


def chipInternalSolvedRouteSetResult_buildFromDocumentDict(
    documentDict: dict[str, object],
):
    """Build chip-local solved routes through the current pipeline."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(documentDict)
    assert result_isOkCheck(circuitDocumentResult)
    return chipInternalSolvedRouteSetResult_buildFromCircuitDocumentAndObligationSet(
        circuitDocumentResult.value,
        chipInternalRouteObligationSet_buildFromCircuitDocument(
            circuitDocumentResult.value
        ),
    )


class TestChipSolver:
    """Verification of the first chip-local solve layer."""

    def test_chip_solver_builds_bare_transverse_data_route(self) -> None:
        """Bare `src:dst` wiring should infer a transverse data route."""

        diagnosticStack.stack_clear()

        chipInternalSolvedRouteSetResult = (
            chipInternalSolvedRouteSetResult_buildFromDocumentDict(
                {
                    "tree": {
                        "module": "Hub.ts",
                        "func": "process()",
                        "input_ports": [{"signal": "a"}],
                        "output_ports": [{"signal": "b"}],
                        "internal_wiring": ["a:b"],
                        "calls": [],
                    }
                }
            )
        )

        assert result_isOkCheck(chipInternalSolvedRouteSetResult)
        solvedRoute = (
            chipInternalSolvedRouteSetResult.value.chipInternalSolvedRoutes[0]
        )
        assert (
            solvedRoute.chipInternalRouteDirectiveSpec.routeClass
            is ChipInternalRouteClass.DATA
        )
        assert (
            solvedRoute.chipInternalRouteDirectiveSpec.routeOrientation
            is ChipInternalRouteOrientation.WEST_TO_EAST
        )
        assert solvedRoute.chipInternalRouteDirectiveSpec.routeSemantics is None
        assert (
            solvedRoute.solveKind
            is ChipInternalRouteSolveKind.TRANSVERSE_MANIFOLD
        )

    def test_chip_solver_defaults_thread_route_to_compute(self) -> None:
        """Thread-class routes default to compute semantics when omitted."""

        diagnosticStack.stack_clear()

        chipInternalSolvedRouteSetResult = (
            chipInternalSolvedRouteSetResult_buildFromDocumentDict(
                {
                    "tree": {
                        "module": "Hub.ts",
                        "func": "process()",
                        "input_ports": [{"signal": "a"}],
                        "output_ports": [{"signal": "b"}],
                        "internal_wiring": ["a:b:WE:thread:color(red)"],
                        "calls": [],
                    }
                }
            )
        )

        assert result_isOkCheck(chipInternalSolvedRouteSetResult)
        solvedRoute = (
            chipInternalSolvedRouteSetResult.value.chipInternalSolvedRoutes[0]
        )
        assert (
            solvedRoute.chipInternalRouteDirectiveSpec.routeClass
            is ChipInternalRouteClass.THREAD
        )
        assert (
            solvedRoute.chipInternalRouteDirectiveSpec.routeSemantics
            is ChipInternalRouteSemantics.COMPUTE
        )
        assert solvedRoute.chipInternalRouteDirectiveSpec.colorName == "red"

    def test_chip_solver_classifies_same_side_local_routes(self) -> None:
        """Same-side internal routes should be marked as local continuity.

        Both endpoints must land on the same wall.  Two input_ports labels are
        both west terminals, so a wiring directive between them is SAME_SIDE_LOCAL.
        """

        diagnosticStack.stack_clear()

        chipInternalSolvedRouteSetResult = (
            chipInternalSolvedRouteSetResult_buildFromDocumentDict(
                {
                    "tree": {
                        "module": "Hub.ts",
                        "func": "process()",
                        "input_ports": [
                            {"signal": "tick"},
                            {"return": "tock"},
                        ],
                        "internal_wiring": ["tick:tock"],
                        "calls": [],
                    }
                }
            )
        )

        assert result_isOkCheck(chipInternalSolvedRouteSetResult)
        solvedRoute = (
            chipInternalSolvedRouteSetResult.value.chipInternalSolvedRoutes[0]
        )
        assert (
            solvedRoute.sourceTerminal.terminalSide
            is ChipTerminalSide.WEST
        )
        assert (
            solvedRoute.destinationTerminal.terminalSide
            is ChipTerminalSide.WEST
        )
        assert solvedRoute.solveKind is ChipInternalRouteSolveKind.SAME_SIDE_LOCAL
        assert solvedRoute.chipInternalRouteDirectiveSpec.routeOrientation is None

    def test_chip_solver_rejects_unknown_terminal_names(self) -> None:
        """Unknown internal-wiring endpoints should fail through diagnostics."""

        diagnosticStack.stack_clear()

        chipInternalSolvedRouteSetResult = (
            chipInternalSolvedRouteSetResult_buildFromDocumentDict(
                {
                    "tree": {
                        "module": "Hub.ts",
                        "func": "process()",
                        "input_ports": [{"signal": "x"}],
                        "output_ports": [{"signal": "y"}],
                        "internal_wiring": ["missing:y"],
                        "calls": [],
                    }
                }
            )
        )

        assert not result_isOkCheck(chipInternalSolvedRouteSetResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert (
            diagnostics[-1].code
            == "routing.chip_solver.directive.terminal_name_missing"
        )

    def test_chip_solver_uses_explicit_orientation_to_disambiguate(self) -> None:
        """Explicit orientation should resolve same-name opposite-side terminals."""

        diagnosticStack.stack_clear()

        chipInternalSolvedRouteSetResult = (
            chipInternalSolvedRouteSetResult_buildFromDocumentDict(
                {
                    "tree": {
                        "module": "Hub.ts",
                        "func": "process()",
                        "input_ports": [{"signal": "x"}],
                        "output_ports": [{"signal": "x"}],
                        "internal_wiring": ["x:x:WE:thread:compute"],
                        "calls": [],
                    }
                }
            )
        )

        assert result_isOkCheck(chipInternalSolvedRouteSetResult)
        solvedRoute = (
            chipInternalSolvedRouteSetResult.value.chipInternalSolvedRoutes[0]
        )
        assert (
            solvedRoute.chipInternalRouteDirectiveSpec.routeOrientation
            is ChipInternalRouteOrientation.WEST_TO_EAST
        )
        assert solvedRoute.sourceTerminal.terminalSide.value == "west"
        assert solvedRoute.destinationTerminal.terminalSide.value == "east"

    def test_chip_solver_simple_circuit_corpus_solves_declared_internal_routes(
        self,
    ) -> None:
        """Simple-circuit fixtures should all admit chip-local solving."""

        simpleCircuitDir = Path("examples/simple-circuit")
        examplePath: Path
        for examplePath in sorted(simpleCircuitDir.glob("*.yaml")):
            diagnosticStack.stack_clear()
            documentDict = safe_load(examplePath.read_text())
            circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
                documentDict
            )
            assert result_isOkCheck(circuitDocumentResult)
            chipInternalSolvedRouteSetResult = (
                chipInternalSolvedRouteSetResult_buildFromDocumentDict(documentDict)
            )
            assert result_isOkCheck(chipInternalSolvedRouteSetResult), (
                examplePath.name,
                diagnosticStack.diagnosticSet_build().diagnostics_getAll(),
            )
            declaredDirectiveCount: int = sum(
                len(chip.internalWiringDirectiveSet.directives)
                for chip in circuitDocumentResult.value.circuitChipSet.chips
            )
            assert len(
                chipInternalSolvedRouteSetResult.value.chipInternalSolvedRoutes
            ) == declaredDirectiveCount
