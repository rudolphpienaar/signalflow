"""Module box computation and rendering."""
from __future__ import annotations

# Standard library
from typing import TYPE_CHECKING

# Local
from signalflow.config import config
from signalflow.models import ModuleBox

if TYPE_CHECKING:
    from signalflow.models import Canvas, Node


def moduleBox_compute(nodes: list[Node]) -> list[ModuleBox]:
    """Compute snug module box boundaries for each unique module in the graph.

    Groups nodes by module and finds the min/max X and Y coordinates required
    to encapsulate all chips and their incoming manifold staggered channels.

    Args:
        nodes: List of all Node instances in the diagram.

    Returns:
        List of ModuleBox instances with computed coordinates.
    """
    modules: dict[str, list[Node]] = {}
    n: Node
    for n in nodes:
        if n.module not in modules:
            modules[n.module] = []
        modules[n.module].append(n)

    boxes: list[ModuleBox] = []
    modName: str
    modNodes: list[Node]
    for modName, modNodes in modules.items():
        # Pure Chip Bounding: Only chips define the module box limits.
        # External wires pierce the box walls reactively.
        minChipX: int = min(n.x for n in modNodes)
        maxChipX: int = max(n.x + n.ow for n in modNodes)
        minChipY: int = min(n.y for n in modNodes)
        maxChipBot: int = max(n.y + n.chipH for n in modNodes)

        ox0: int = max(0, minChipX - config.modulePadding)
        oy0: int = max(0, minChipY - config.moduleTopRows)
        ox1: int = max(maxChipX + config.modulePadding - 1, 0)
        oy1: int = max(maxChipBot + config.modulePadding - 1, 0)

        boxes.append(ModuleBox(modName, ox0, oy0, ox1, oy1))
    return boxes


def moduleBox_render(canvas: Canvas, box: ModuleBox, nodes: list[Node]) -> None:
    """Render double-line module box boundaries onto the canvas.

    Draws corners and walls. Piercings (╫, ╪) are handled reactively
    by the Canvas drawing primitives.

    Args:
        canvas: The canvas to draw on.
        box:    The ModuleBox instance to render.
        nodes:  List of nodes (unused but kept for signature).
    """
    x0: int
    y0: int
    x1: int
    y1: int
    x0, y0, x1, y1 = box.ox0, box.oy0, box.ox1, box.oy1
    innerW: int = (x1 - x0) - 1

    # Top border: ╔═ label ════...════╗
    canvas.set(x0, y0, "╔")
    fill: str = ("═ " + box.label + " ").ljust(innerW, "═")[:innerW]
    i: int
    ch: str
    for i, ch in enumerate(fill):
        canvas.set(x0 + 1 + i, y0, ch)
    canvas.set(x1, y0, "╗")

    # Side walls: ║
    y: int
    for y in range(y0 + 1, y1):
        canvas.set(x0, y, "║")
        canvas.set(x1, y, "║")

    # Bottom border: ╚════...════╝
    canvas.set(x0, y1, "╚")
    x: int
    for x in range(x0 + 1, x1):
        canvas.set(x, y1, "═")
    canvas.set(x1, y1, "╝")
