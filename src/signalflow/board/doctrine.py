"""Board-domain geometric doctrine.

This module is the intended home for invariant board layout and routing rules.
The board package now carries enough geometry responsibility that boundary
policy must also live here explicitly:

- routing sense
- minimum cross-bar span
- effective boundary policy
- explicit padding used after the furthest visible label/stub extent
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from signalflow.board.types import BoardSense


class EffectiveBoundaryMode(str, Enum):
    """Policy for computing effective routed module boundaries.

    `CONTENT_ONLY`
        Boundaries hug only the literal chip box content. This is useful as a
        low-level fallback but is generally not what users want visually.

    `LABEL_AWARE_MODULE_BOX`
        Boundaries are built from the full placed chip drawing extents, which
        already include terminal labels and stubs, then expanded by configured
        padding. This matches the current world-render module-box behavior while
        making it first-class board geometry.
    """

    CONTENT_ONLY = "content_only"
    LABEL_AWARE_MODULE_BOX = "label_aware_module_box"


@dataclass(frozen=True)
class BoardDoctrine:
    """Geometric doctrine that constrains board layout and realization."""

    sense: BoardSense
    minimumCrossbarSpan: int = 0
    effectiveBoundaryMode: EffectiveBoundaryMode = (
        EffectiveBoundaryMode.LABEL_AWARE_MODULE_BOX
    )
    moduleBoundaryPaddingCells: int = 1
    """Explicit padding used around effective terminal/module envelopes.

    This single value is the board-domain source of truth for the clearance
    inserted after visible terminal labels/stubs. The effective-board builder
    uses it for both:
    - outward expansion of effective module boundaries
    - inward routing-facing chip inset inside those boundaries

    That keeps visible label clearance out of incidental draw-line whitespace.
    """
