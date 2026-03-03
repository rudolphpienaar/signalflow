"""Top-level rendering pipeline: parse → layout → render → output."""

from signalflow.lib.boxes import moduleBox_compute, moduleBox_render
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, col_assign, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.lib.wires import thread_render
from signalflow.models import Node


def diagram_render(title: str, tree_dict: dict) -> list:
    """Parse, layout, render, and return diagram lines."""
    from signalflow.config import config
    
    # 1. Apply YAML-based config overrides
    if 'config' in tree_dict:
        config.config_update(tree_dict['config'])

    # 2. Parse tree into Graph
    root  = Node.node_fromDict(tree_dict.get('tree', tree_dict))
    nodes = tree_flatten(root)

    col_assign(root)
    cw = channelWidth_compute(root)
    layout_compute(root, cw)

    boxes  = moduleBox_compute(nodes)
    canvas = canvas_create(nodes, cw, boxes)

    for box in boxes:
        moduleBox_render(canvas, box, nodes)

    for n in nodes:
        chip_render(canvas, n)

    # Enable algebraic merge for external wire piercings
    canvas.mode_merge = True
    thread_render(canvas, root)
    canvas.mode_merge = False

    lines = []
    if title:
        lines.append(f'  == {title} ==')
        lines.append('')
    lines.extend(canvas.lines_get())
    return lines
