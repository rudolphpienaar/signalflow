"""Shared chip-terminal endpoint identity models for routing substrates."""
from __future__ import annotations

from dataclasses import dataclass

from signalflow.models.chip import ChipRef, ChipTerminal, ChipTerminalSide


@dataclass(frozen=True)
class ChipTerminalRef:
    """Owner-qualified identity for one named chip terminal.

    Attributes:
        chipRef: Stable reference to the owning chip.
        terminalSide: Side on which the terminal is exposed.
        terminalName: Stable label of the terminal on the chip.
    """

    chipRef: ChipRef
    terminalSide: ChipTerminalSide
    terminalName: str


def chipTerminalRef_build(
    chipRef: ChipRef,
    chipTerminal: ChipTerminal,
) -> ChipTerminalRef:
    """Build one owner-qualified terminal reference from a chip terminal."""

    return ChipTerminalRef(
        chipRef=chipRef,
        terminalSide=chipTerminal.terminalSide,
        terminalName=chipTerminal.terminalName,
    )
