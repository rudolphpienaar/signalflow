"""Tests for shared diagnostics and result models.

These tests cover the explicit result union and structured diagnostic stack
used for subsystem-boundary control flow and issue accumulation.

Key components:
    - Result helpers and type guard behavior
    - DiagnosticSet query helpers
    - DiagnosticStack lifecycle and severity tracking

Typical usage:
    pytest tests/test_rearch_result.py
"""
from __future__ import annotations

from signalflow.models import (
    Diagnostic,
    DiagnosticLevel,
    DiagnosticPhase,
    DiagnosticSet,
    DiagnosticStack,
    ResultErr,
    ResultOk,
    diagnosticStack,
    result_isErrCheck,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)


class TestResultModels:
    """Verification of explicit success and failure results."""

    def test_resultOk_build_wraps_value(self) -> None:
        """Successful results should carry the provided value."""

        result = resultOk_build(7)

        assert result_isOkCheck(result)
        assert isinstance(result, ResultOk)
        assert result.value == 7

    def test_resultErr_build_has_no_value(self) -> None:
        """Failed results should not expose a success value."""

        result = resultErr_build()

        assert result_isErrCheck(result)
        assert isinstance(result, ResultErr)
        assert result.ok is False


class TestDiagnosticSet:
    """Verification of immutable diagnostic set behavior."""

    def test_diagnostics_search_matches_code_message_and_context(self) -> None:
        """Search should match across code, message, and context values."""

        diagnosticSet: DiagnosticSet = DiagnosticSet(
            diagnostics=(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    phase=DiagnosticPhase.LAYOUT,
                    code="layout.node.missing_name",
                    message="Node function name is required",
                    context=("family.c", "main()"),
                ),
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    phase=DiagnosticPhase.ROUTING,
                    code="routing.edge.slow_path",
                    message="Fallback lane ordering applied",
                    context=("edge-1",),
                ),
            )
        )

        codeMatches = diagnosticSet.diagnostics_search("missing_name")
        messageMatches = diagnosticSet.diagnostics_search("fallback lane")
        contextMatches = diagnosticSet.diagnostics_search("family.c")

        assert len(codeMatches) == 1
        assert len(messageMatches) == 1
        assert len(contextMatches) == 1

    def test_diagnosticsOfLevel_get_filters_by_severity(self) -> None:
        """Severity filters should return only matching diagnostics."""

        diagnosticSet: DiagnosticSet = DiagnosticSet(
            diagnostics=(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    phase=DiagnosticPhase.LAYOUT,
                    code="layout.error",
                    message="Layout error",
                ),
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    phase=DiagnosticPhase.LAYOUT,
                    code="layout.warning",
                    message="Layout warning",
                ),
            )
        )

        errors = diagnosticSet.diagnosticsOfLevel_get(DiagnosticLevel.ERROR)
        warnings = diagnosticSet.diagnosticsOfLevel_get(DiagnosticLevel.WARNING)

        assert len(errors) == 1
        assert len(warnings) == 1
        assert errors[0].code == "layout.error"
        assert warnings[0].code == "layout.warning"


class TestDiagnosticStack:
    """Verification of mutable diagnostic stack behavior."""

    def test_stack_builds_immutable_snapshot(self) -> None:
        """Snapshot building should preserve the current diagnostic order."""

        stack: DiagnosticStack = DiagnosticStack()
        stack.error_push(
            phase=DiagnosticPhase.LAYOUT,
            code="layout.node.error",
            message="Layout failed",
            context=("family.c",),
        )
        stack.warning_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.edge.warning",
            message="Routing warning",
        )

        diagnosticSet = stack.diagnosticSet_build()

        assert diagnosticSet.diagnostics_has()
        assert len(diagnosticSet.diagnostics_getAll()) == 2
        assert diagnosticSet.diagnostics_getAll()[0].code == "layout.node.error"

    def test_stack_clear_resets_module_global_stack(self) -> None:
        """The module-global stack should support an explicit clear lifecycle."""

        diagnosticStack.stack_clear()
        diagnosticStack.error_push(
            phase=DiagnosticPhase.GENERAL,
            code="general.error",
            message="Example error",
        )

        assert diagnosticStack.diagnostics_has()
        assert diagnosticStack.diagnosticsOfLevel_has(DiagnosticLevel.ERROR)

        diagnosticStack.stack_clear()

        assert not diagnosticStack.diagnostics_has()
