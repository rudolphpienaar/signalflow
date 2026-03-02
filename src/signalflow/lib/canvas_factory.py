"""Canvas instantiation and initial sizing."""
from __future__ import annotations

# Local
from signalflow.config import config
from signalflow.models import Canvas


def canvas_create(nodes: list, cw: int, boxes: list) -> Canvas:
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
    max_x = max(n.x + n.ow for n in nodes) if nodes else 0
    max_y = max(n.y + n.chip_h for n in nodes) if nodes else 0

    if boxes:
        max_x = max(max_x, max(b.ox1 for b in boxes))
        max_y = max(max_y, max(b.oy1 for b in boxes))

    # Add safety margin for stubs/U-turns
    cols = max_x + 10
    rows = max_y + config.verticalChipPadding + 4

    return Canvas(rows=rows, cols=cols)
