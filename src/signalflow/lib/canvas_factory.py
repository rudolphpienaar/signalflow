"""Canvas instantiation and initial sizing."""
from __future__ import annotations

# Standard library
from typing import TYPE_CHECKING

# Local
from signalflow.config import config
from signalflow.models import Canvas

if TYPE_CHECKING:
    from signalflow.models import ModuleBox, Node


def canvas_create(nodes: list[Node], cw: int, boxes: list[ModuleBox]) -> Canvas:
    """Instantiate a canvas large enough to hold all nodes and boxes.

    Finds the maximum X and Y coordinates occupied by any element and adds
    padding.

    Args:
        nodes: List of all Node instances.
        cw:    Global channel width (unused but kept for signature).
        boxes: List of all ModuleBox instances.

    Returns:
        A new Canvas instance of appropriate size.
    """
    maxX: int = max(n.x + n.ow for n in nodes) if nodes else 0
    maxY: int = max(n.y + n.chipH for n in nodes) if nodes else 0

    if boxes:
        maxX = max(maxX, max(b.ox1 for b in boxes))
        maxY = max(maxY, max(b.oy1 for b in boxes))

    # Add safety margin for stubs/U-turns
    cols: int = maxX + 10
    rows: int = maxY + config.verticalChipPadding + 4

    return Canvas(rows=rows, cols=cols)
