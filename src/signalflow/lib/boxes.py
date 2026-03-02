"""Module box computation and rendering."""
from __future__ import annotations

# Local
from signalflow.config import config
from signalflow.models import Canvas, ModuleBox


def moduleBox_compute(nodes: list) -> list:
    """Compute snug module box boundaries for each unique module in the graph.

    Groups nodes by module and finds the min/max X and Y coordinates required
    to encapsulate all chips and their incoming manifold staggered channels.

    Args:
        nodes: List of all Node instances in the diagram.

    Returns:
        List of ModuleBox instances with computed coordinates.
    """
    modules = {}
    for n in nodes:
        if n.module not in modules:
            modules[n.module] = []
        modules[n.module].append(n)

    boxes = []
    for mod_name, mod_nodes in modules.items():
        min_chip_x = min(n.x for n in mod_nodes)
        max_content_x = max(n.x + n.ow for n in mod_nodes)
        min_chip_y = min(n.y for n in mod_nodes)
        max_chip_bot = max(n.y + n.chip_h for n in mod_nodes)

        # Expand max_content_x to include manifold staggering
        for n in mod_nodes:
            if n.children:
                max_child_lbl = 0
                for child in n.children:
                    # Only stagger if child is in a DIFFERENT module (external manifold)
                    if child.module != n.module:
                        local_p = child.input_ports.get(id(n))
                        if local_p:
                            lbl_f = len(local_p.signal) if local_p.signal else 0
                            lbl_r = len(local_p.ret) if local_p.ret else 0
                            max_child_lbl = max(max_child_lbl, lbl_f, lbl_r)

                stagger_start = max_child_lbl + 3
                for child in n.children:
                    if child.module != n.module:
                        p_idx = list(n.output_ports.keys()).index(id(child))
                        c_idx = list(child.input_ports.keys()).index(id(n))
                        stagger_idx = max(p_idx, c_idx)

                        # Target-Wall relative channel X
                        chan_x = child.x - stagger_start - 2 * stagger_idx
                        if chan_x > max_content_x:
                            max_content_x = chan_x + 1

        ox0 = max(0, min_chip_x - config.modulePadding)
        oy0 = max(0, min_chip_y - config.moduleTopRows)
        ox1 = max_content_x + config.modulePadding - 1
        oy1 = max_chip_bot + config.modulePadding - 1

        boxes.append(ModuleBox(mod_name, ox0, oy0, ox1, oy1))
    return boxes


def moduleBox_render(canvas: Canvas, box: ModuleBox, nodes: list) -> None:
    """Render double-line module box boundaries onto the canvas.

    Draws corners and walls. Piercings (╫, ╪) are handled reactively
    by the Canvas drawing primitives.

    Args:
        canvas: The canvas to draw on.
        box:    The ModuleBox instance to render.
        nodes:  List of nodes (unused but kept for signature).
    """
    x0, y0, x1, y1 = box.ox0, box.oy0, box.ox1, box.oy1
    inner_w = (x1 - x0) - 1

    # Top border: ╔═ label ════...════╗
    canvas.set(x0, y0, "╔")
    fill = ("═ " + box.label + " ").ljust(inner_w, "═")[:inner_w]
    for i, ch in enumerate(fill):
        canvas.set(x0 + 1 + i, y0, ch)
    canvas.set(x1, y0, "╗")

    # Side walls: ║
    for y in range(y0 + 1, y1):
        canvas.set(x0, y, "║")
        canvas.set(x1, y, "║")

    # Bottom border: ╚════...════╝
    canvas.set(x0, y1, "╚")
    for x in range(x0 + 1, x1):
        canvas.set(x, y1, "═")
    canvas.set(x1, y1, "╝")
