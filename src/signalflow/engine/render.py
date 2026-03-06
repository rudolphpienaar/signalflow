"""Top-level rendering pipeline: parse → layout → render → output."""

from signalflow.lib.boxes import moduleBox_compute, moduleBox_render
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, col_assign, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.lib.wires import thread_render
from signalflow.models import Canvas, Node


def diagram_render(title: str, treeDict: dict) -> list[str]:
    """Parse, layout, render, and return diagram lines."""
    from signalflow.config import config

    # 1. Apply YAML-based config overrides
    if 'config' in treeDict:
        config.config_update(treeDict['config'])

    # 2. Parse tree into Graph
    root: Node = Node.node_fromDict(treeDict.get('tree', treeDict))
    nodes: list[Node] = tree_flatten(root)

    col_assign(root)
    cw: int = channelWidth_compute(root)
    layout_compute(root, cw)

    from signalflow.models import ModuleBox
    boxes: list[ModuleBox] = moduleBox_compute(nodes)
    canvas: Canvas = canvas_create(nodes, cw, boxes)

    box: ModuleBox
    for box in boxes:
        moduleBox_render(canvas, box, nodes)

    n: Node
    for n in nodes:
        chip_render(canvas, n)

    # Enable algebraic merge for external wire piercings
    canvas.modeMerge = True
    thread_render(canvas, root)
    canvas.modeMerge = False

    lines: list[str] = []
    if title:
        lines.append(f'  == {title} ==')
        lines.append('')
    lines.extend(canvas.lines_get())
    return lines
