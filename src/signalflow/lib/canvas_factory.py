"""Canvas allocation: size from nodes + module boxes."""

from signalflow.config import ROW_GAP
from signalflow.models import Canvas


def canvas_create(nodes: list, ow: int, cw: int, boxes: list) -> Canvas:
    """Allocate a blank canvas large enough for all chips, boxes, and wires."""
    max_x = 0
    max_y = 0
    for n in nodes:
        max_x = max(max_x, n.x + ow)
        max_y = max(max_y, n.y + n.chip_h)
    for b in boxes:
        max_x = max(max_x, b.ox1 + 2)
        max_y = max(max_y, b.oy1 + 2)

    cols = max_x + cw + 8
    rows = max_y + ROW_GAP + 4
    return Canvas(rows=rows, cols=cols)
