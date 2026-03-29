"""Tests for first-class chip result-handling boundaries."""
from __future__ import annotations

from signalflow.models import (
    ChipTerminal,
    ChipTerminalSet,
    ChipTerminalSide,
    chipInternalWiringDirectiveResult_build,
    chipPortDeclarationResult_build,
    chipTerminalSetResult_build,
    diagnosticStack,
    result_isOkCheck,
)


class TestChipTerminalSetResults:
    """Verification of chip-terminal result surfaces."""

    def test_chipTerminalSetResult_build_allows_same_name_on_opposite_sides(
        self,
    ) -> None:
        """Opposite-side terminal names should not collide."""

        diagnosticStack.stack_clear()

        chipTerminalSetResult = chipTerminalSetResult_build(
            terminals=(
                ChipTerminal(
                    terminalName="in",
                    terminalSide=ChipTerminalSide.WEST,
                ),
                ChipTerminal(
                    terminalName="in",
                    terminalSide=ChipTerminalSide.EAST,
                ),
            )
        )

        assert result_isOkCheck(chipTerminalSetResult)

    def test_chipTerminalSetResult_build_rejects_duplicate_name_side_pair(
        self,
    ) -> None:
        """Exact duplicate terminal keys should report through Result semantics."""

        diagnosticStack.stack_clear()

        chipTerminalSetResult = chipTerminalSetResult_build(
            terminals=(
                ChipTerminal(
                    terminalName="in",
                    terminalSide=ChipTerminalSide.WEST,
                ),
                ChipTerminal(
                    terminalName="in",
                    terminalSide=ChipTerminalSide.WEST,
                ),
            )
        )

        assert not result_isOkCheck(chipTerminalSetResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "chip.terminal_set.duplicate_terminal_key"

    def test_terminalForNameAndSideResult_get_reports_missing_terminal(self) -> None:
        """Missing terminal keys should report through Result and diagnostics."""

        chipTerminalSet: ChipTerminalSet = ChipTerminalSet(
            terminals=(
                ChipTerminal(
                    terminalName="in",
                    terminalSide=ChipTerminalSide.WEST,
                ),
            )
        )
        diagnosticStack.stack_clear()

        chipTerminalResult = chipTerminalSet.terminalForNameAndSideResult_get(
            terminalName="out",
            terminalSide=ChipTerminalSide.EAST,
        )

        assert not result_isOkCheck(chipTerminalResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "chip.terminal_set.missing_terminal_key"


class TestChipPortAndWiringDeclarations:
    """Verification of deeper chip declaration models."""

    def test_chipPortDeclarationResult_build_rejects_empty_declaration(self) -> None:
        """A chip port declaration must declare at least one name."""

        diagnosticStack.stack_clear()

        chipPortDeclarationResult = chipPortDeclarationResult_build()

        assert not result_isOkCheck(chipPortDeclarationResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "chip.port_declaration.empty"

    def test_chipInternalWiringDirectiveResult_build_rejects_empty_strings(
        self,
    ) -> None:
        """Internal wiring directives must be non-empty strings."""

        diagnosticStack.stack_clear()

        chipInternalWiringDirectiveResult = (
            chipInternalWiringDirectiveResult_build("")
        )

        assert not result_isOkCheck(chipInternalWiringDirectiveResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "chip.internal_wiring.empty_directive"
