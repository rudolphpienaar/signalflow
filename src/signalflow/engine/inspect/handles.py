"""Core inspect context and workflow surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board import (
    ChipInternalBoardSchema,
    chipInternalBoardSchema_build,
)
from signalflow.models import (
    ChipId,
    result_isOkCheck,
)

from .chip_helpers import (
    _chipTitleText_build,
)
from .context import (
    ChipWorldFrame,
    DebugChipWorldFrame,
    DebugWorkflowView,
    SignalFlowContext,
    WorkflowView,
)


def _summary_print(text: str) -> None:
    from .repl import _summary_print as _impl

    _impl(text)


@dataclass(frozen=True)
class ChipInternalBoardHandle:
    """Interactive handle for one chip-local board harmonization artifact."""

    debugContext: SignalFlowContext
    chipId: ChipId

    def __dir__(self) -> list[str]:
        return ["raw_get", "schema_get", "summary_text", "wiring_text"]

    def __repr__(self) -> str:
        return f"<chip-internal-board {_chipTitleText_build(self.chipId)}>"

    def raw_get(self):
        return self.debugContext.chipResult_get(self.chipId)

    def schema_get(self) -> ChipInternalBoardSchema:
        chipResult = self.debugContext.chipResult_get(self.chipId)
        assert result_isOkCheck(chipResult)
        return chipInternalBoardSchema_build(chipResult.value)

    def wiring_sprint(self) -> str:
        schema = self.schema_get()
        if not schema.wires:
            return "chip-internal board wiring:\n  <none>"
        lines = ["chip-internal board wiring:"]
        for wire in schema.wires:
            lines.append(
                "  "
                f"{wire.sourceTerminalName}:{wire.destinationTerminalName}"
                f"  ({wire.wiringDeclaration})"
            )
        return "\n".join(lines)

    def summary_sprint(self) -> str:
        schema = self.schema_get()
        lines = [
            f"chip-internal board for {schema.chipTitle}",
            f"  sense: {schema.sense.value}",
            "  west terminals: "
            + (
                ", ".join(schema.westTerminalNames)
                if schema.westTerminalNames
                else "<none>"
            ),
            "  east terminals: "
            + (
                ", ".join(schema.eastTerminalNames)
                if schema.eastTerminalNames
                else "<none>"
            ),
            f"  wires: {len(schema.wires)}",
        ]
        return "\n".join(lines)


DebugChipInternalBoardHandle = ChipInternalBoardHandle


__all__: list[str] = [
    "ChipInternalBoardHandle",
    "ChipWorldFrame",
    "DebugChipInternalBoardHandle",
    "DebugChipWorldFrame",
    "DebugWorkflowView",
    "WorkflowView",
    "SignalFlowContext",
]
