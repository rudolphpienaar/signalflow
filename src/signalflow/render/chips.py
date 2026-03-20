"""Chip rendering layer for the new SignalFlow engine.

This module is the canonical render boundary for chip visual output.  It
consumes only ``Chip`` model objects and produces ordered text lines.  No
topology discovery, routing solve, or reclassification occurs here.

The underlying drawing logic lives in ``models.chip.chipDrawLines_build`` so
that the debugger, the planning projection, and this render layer share a
single chip representation.  This module is the stable API surface that the
top-level renderer and the fixture tests address.

Future enhancements (color hints, style themes, width padding) belong here
without touching the chip model.
"""
from __future__ import annotations

from signalflow.models.chip import Chip, chipDrawLines_build


def chipLines_render(chip: Chip) -> tuple[str, ...]:
    """Render one chip to its canonical ASCII text lines.

    Delegates to the single source of truth in ``models.chip`` and returns
    an immutable tuple of strings, one per visual row.  The caller may
    inspect line count and individual rows without further processing.

    A chip with no declared terminals renders as a compact three-row
    title-only box:

        ┌──────────┐
        │ func()   │
        └──────────┘

    A chip with declared terminals renders as a full box with labeled wire
    stubs on the appropriate sides:

         in ─►┤          ├─► out
         ra ◄─┤ func()   │
              ├──────────┤
              └──────────┘

    Args:
        chip: The chip model object to render.

    Returns:
        Ordered tuple of text lines forming the chip's ASCII representation.
        Lines are not padded; widths may vary across the tuple.
    """

    return chipDrawLines_build(chip)
