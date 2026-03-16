"""Structured diagnostics models and stack for SignalFlow.

This module provides explicit diagnostic modeling for warnings and errors
produced by SignalFlow subsystems. It separates the control-flow question
("did the operation succeed") from the diagnostics question ("what was
observed during the operation").

Key components:
    - DiagnosticLevel: Severity of one diagnostic
    - DiagnosticPhase: Engine phase that produced the diagnostic
    - Diagnostic: One structured warning or error
    - DiagnosticSet: Modeled collection of diagnostics
    - DiagnosticStack: Mutable accumulator for the current run
    - diagnosticStack: Module-global stack used as the default accumulator

Typical usage:
    diagnosticStack.stack_clear()
    diagnosticStack.error_push(
        phase=DiagnosticPhase.LAYOUT,
        code="layout.node.missing_name",
        message="Node function name is required",
        context=("family.c",),
    )
    diagnostics = diagnosticStack.diagnosticSet_build()

Dependencies:
    - Uses only standard-library dataclasses and enums
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DiagnosticLevel(Enum):
    """Severity level for one diagnostic.

    Attributes:
        ERROR: A diagnostic that should cause the current operation to fail.
        WARNING: A diagnostic that should be surfaced but does not necessarily
            make the current operation unusable.

    Example:
        >>> level = DiagnosticLevel.ERROR
    """

    ERROR = "error"
    WARNING = "warning"


class DiagnosticPhase(Enum):
    """Engine phase that produced one diagnostic.

    Attributes:
        VALIDATION: Input normalization or contract validation.
        LAYOUT: Chip/module placement phase.
        ROUTING: Edge classification or path realization phase.
        RENDER: Final projection and drawing phase.
        GENERAL: Diagnostic not owned by a more specific phase.

    Example:
        >>> phase = DiagnosticPhase.LAYOUT
    """

    VALIDATION = "validation"
    LAYOUT = "layout"
    ROUTING = "routing"
    RENDER = "render"
    GENERAL = "general"


@dataclass(frozen=True)
class Diagnostic:
    """One structured warning or error.

    A diagnostic is meant to be machine-filterable and human-readable. The
    `code` is stable enough for tests and filtering, while the `message` is the
    explanatory text intended for operators or developers.

    Attributes:
        level: Severity of the diagnostic.
        phase: Engine phase that emitted the diagnostic.
        code: Stable short code describing the diagnostic kind.
        message: Human-readable explanation of the issue.
        context: Optional ordered context strings such as module name, node id,
            or fixture name.

    Example:
        >>> diagnostic = Diagnostic(
        ...     level=DiagnosticLevel.ERROR,
        ...     phase=DiagnosticPhase.LAYOUT,
        ...     code="layout.node.missing_name",
        ...     message="Node function name is required",
        ...     context=("family.c",),
        ... )
    """

    level: DiagnosticLevel
    phase: DiagnosticPhase
    code: str
    message: str
    context: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticSet:
    """Modeled collection of diagnostics.

    This wrapper exists because the complete set of diagnostics produced by one
    operation is itself a domain concept. The set exposes domain-oriented query
    helpers rather than requiring callers to manipulate a raw tuple directly.

    Attributes:
        diagnostics: Ordered diagnostics captured for one operation.

    Example:
        >>> diagnosticSet = DiagnosticSet(diagnostics=())
    """

    diagnostics: tuple[Diagnostic, ...]

    def diagnostics_getAll(self) -> tuple[Diagnostic, ...]:
        """Return all diagnostics in their recorded order.

        Returns:
            Ordered diagnostics for this set.
        """

        return self.diagnostics

    def diagnosticsOfLevel_get(
        self, level: DiagnosticLevel
    ) -> tuple[Diagnostic, ...]:
        """Return diagnostics for one severity level.

        Args:
            level: Severity level to filter by.

        Returns:
            Ordered diagnostics matching the requested severity.
        """

        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.level is level
        )

    def diagnosticsOfPhase_get(
        self, phase: DiagnosticPhase
    ) -> tuple[Diagnostic, ...]:
        """Return diagnostics for one engine phase.

        Args:
            phase: Phase to filter by.

        Returns:
            Ordered diagnostics matching the requested phase.
        """

        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.phase is phase
        )

    def diagnostics_search(self, substring: str) -> tuple[Diagnostic, ...]:
        """Search diagnostics by case-insensitive substring.

        Args:
            substring: Text fragment to search for within code, message, and
                context values.

        Returns:
            Ordered diagnostics containing the requested text fragment.
        """

        needleLower: str = substring.lower()
        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if self._diagnosticMatchesSubstring_check(diagnostic, needleLower)
        )

    def diagnostics_has(self) -> bool:
        """Return whether this set contains any diagnostics.

        Returns:
            `True` when the set is non-empty.
        """

        return bool(self.diagnostics)

    def diagnosticsOfLevel_has(self, level: DiagnosticLevel) -> bool:
        """Return whether this set contains diagnostics of one severity.

        Args:
            level: Severity level to test for.

        Returns:
            `True` when at least one diagnostic has the requested severity.
        """

        return any(
            diagnostic.level is level for diagnostic in self.diagnostics
        )

    @classmethod
    def _diagnosticMatchesSubstring_check(
        cls,
        diagnostic: Diagnostic,
        needleLower: str,
    ) -> bool:
        """Return whether one diagnostic matches a search substring.

        Args:
            diagnostic: Diagnostic being checked.
            needleLower: Lower-cased search substring.

        Returns:
            `True` when the substring appears in the code, message, or context.
        """

        haystacks: tuple[str, ...] = (
            diagnostic.code,
            diagnostic.message,
            *diagnostic.context,
        )
        return any(needleLower in haystack.lower() for haystack in haystacks)


@dataclass
class DiagnosticStack:
    """Mutable accumulator for diagnostics produced during one run.

    The stack provides a simple module-global accumulation surface while keeping
    the diagnostic payloads structured. The intended lifecycle is explicit:
    clear the stack at the start of an operation, accumulate diagnostics during
    execution, and convert the stack into a `DiagnosticSet` at a defined
    boundary.

    Attributes:
        diagnosticsMutable: Internal ordered diagnostic storage.

    Example:
        >>> stack = DiagnosticStack()
        >>> stack.warning_push(
        ...     phase=DiagnosticPhase.GENERAL,
        ...     code="general.note",
        ...     message="Example warning",
        ... )
    """

    diagnosticsMutable: list[Diagnostic] = field(default_factory=list)

    def diagnostic_push(self, diagnostic: Diagnostic) -> None:
        """Push one pre-built diagnostic onto the stack.

        Args:
            diagnostic: Structured diagnostic to append.
        """

        self.diagnosticsMutable.append(diagnostic)

    def error_push(
        self,
        phase: DiagnosticPhase,
        code: str,
        message: str,
        context: tuple[str, ...] = (),
    ) -> None:
        """Push one error diagnostic onto the stack.

        Args:
            phase: Engine phase that emitted the error.
            code: Stable short code describing the error kind.
            message: Human-readable explanation of the error.
            context: Optional ordered context strings.
        """

        self.diagnostic_push(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                phase=phase,
                code=code,
                message=message,
                context=context,
            )
        )

    def warning_push(
        self,
        phase: DiagnosticPhase,
        code: str,
        message: str,
        context: tuple[str, ...] = (),
    ) -> None:
        """Push one warning diagnostic onto the stack.

        Args:
            phase: Engine phase that emitted the warning.
            code: Stable short code describing the warning kind.
            message: Human-readable explanation of the warning.
            context: Optional ordered context strings.
        """

        self.diagnostic_push(
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                phase=phase,
                code=code,
                message=message,
                context=context,
            )
        )

    def diagnosticSet_build(self) -> DiagnosticSet:
        """Build an immutable diagnostic set from the current stack contents.

        Returns:
            Immutable `DiagnosticSet` snapshot of the current stack.
        """

        return DiagnosticSet(diagnostics=tuple(self.diagnosticsMutable))

    def stack_pop(self) -> Diagnostic | None:
        """Pop the most recently pushed diagnostic.

        Returns:
            The last pushed diagnostic, or `None` when the stack is empty.
        """

        if not self.diagnosticsMutable:
            return None
        return self.diagnosticsMutable.pop()

    def stack_clear(self) -> None:
        """Clear all diagnostics from the stack."""

        self.diagnosticsMutable.clear()

    def diagnostics_has(self) -> bool:
        """Return whether the stack currently contains any diagnostics.

        Returns:
            `True` when the stack is non-empty.
        """

        return bool(self.diagnosticsMutable)

    def diagnosticsOfLevel_has(self, level: DiagnosticLevel) -> bool:
        """Return whether the stack contains diagnostics of one severity.

        Args:
            level: Severity level to test for.

        Returns:
            `True` when at least one diagnostic has the requested severity.
        """

        return any(
            diagnostic.level is level
            for diagnostic in self.diagnosticsMutable
        )

    def diagnostics_getAll(self) -> tuple[Diagnostic, ...]:
        """Return all diagnostics in their recorded order.

        Returns:
            Ordered diagnostics currently held in the stack.
        """

        return tuple(self.diagnosticsMutable)


diagnosticStack: DiagnosticStack = DiagnosticStack()
