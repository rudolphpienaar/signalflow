"""Top-level rendering pipeline: parse → layout → render → output."""

from signalflow.lib.boxes import moduleBox_compute, moduleBox_render
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, innerWidth_get, layout_compute
from signalflow.lib.tree import col_assign, tree_flatten
from signalflow.lib.wires import thread_render
from signalflow.models import Node


def diagram_render(title: str, tree_dict: dict) -> list:
    """Parse, layout, render, and return diagram lines.

    Args:
        title:     Diagram title string (may be empty).
        tree_dict: Root node dict from YAML input.

    Returns:
        List of strings forming the rendered diagram.
    """
    root  = Node.node_fromDict(tree_dict)
    nodes = tree_flatten(root)

    col_assign(root)

    iw = innerWidth_get(nodes)
    ow = iw + 2
    cw = channelWidth_compute(root)

    layout_compute(root, ow, cw)
    boxes  = moduleBox_compute(nodes, ow)
    canvas = canvas_create(nodes, ow, cw, boxes)

    for box in boxes:
        moduleBox_render(canvas, box, nodes, ow)

    for n in nodes:
        chip_render(canvas, n, ow)

    thread_render(canvas, root, ow)

    lines = []
    if title:
        lines.append(f'  == {title} ==')
        lines.append('')
    lines.extend(canvas.lines_get())
    return lines
