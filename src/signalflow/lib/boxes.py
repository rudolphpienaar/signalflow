"""Module box computation and rendering."""

from signalflow.config import MB_OUTER, MB_TOP, MB_PAD
from signalflow.models import Canvas, ModuleBox


def moduleBox_compute(nodes: list) -> list:
    """Compute snug module box grouping all same-module chips."""
    groups: dict = {}
    for n in nodes:
        groups.setdefault(n.module, []).append(n)

    boxes = []
    for module, mnodes in groups.items():
        min_chip_x   = min(nd.x for nd in mnodes)
        min_chip_y   = min(nd.y for nd in mnodes)
        max_chip_rx  = max(nd.x + nd.ow for nd in mnodes)
        max_chip_bot = max(nd.y + nd.chip_h for nd in mnodes)

        # Only expand the box if a vertical staggered channel is INTRA-MODULE
        max_content_x = max_chip_rx
        for n in mnodes:
            # Check every connection from this parent
            for child in n.children:
                if child.module == n.module:
                    # Stagger logic from wires.py
                    max_child_lbl = 0
                    for c in n.children:
                        if c.input_ports:
                            p = c.input_ports.get(id(n))
                            if p:
                                lbl_f = len(p.signal) if p.signal else 0
                                lbl_r = len(p.ret) if p.ret else 0
                                max_child_lbl = max(max_child_lbl, lbl_f, lbl_r)
                    
                    stagger_start = max_child_lbl + 3
                    p_idx = list(n.output_ports.keys()).index(id(child))
                    c_idx = list(child.input_ports.keys()).index(id(n))
                    stagger_idx = max(p_idx, c_idx)
                    
                    # Target-Wall relative channel X
                    chan_x = child.x - stagger_start - 2 * stagger_idx
                    # If this vertical wire is inside our box's span, we must include it
                    max_content_x = max(max_content_x, chan_x + 1)

        ox0 = max(0, min_chip_x - MB_PAD)
        oy0 = max(0, min_chip_y - MB_TOP)
        ox1 = max_content_x + MB_PAD - 1
        oy1 = max_chip_bot + MB_PAD - 1

        boxes.append(ModuleBox(
            label=module,
            ox0=ox0, oy0=oy0, ox1=ox1, oy1=oy1,
        ))

    return boxes


def moduleBox_render(canvas: Canvas, box: ModuleBox, nodes: list) -> None:
    """Write single double-line module box border with label in top border."""
    x0, y0, x1, y1 = box.ox0, box.oy0, box.ox1, box.oy1
    inner_w = x1 - x0 - 1
    if inner_w <= 0:
        return

    # Top border: ╔═ label ════...════╗
    canvas.set(x0, y0, '╔')
    fill = ('═ ' + box.label + ' ').ljust(inner_w, '═')[:inner_w]
    for i, ch in enumerate(fill):
        canvas.set(x0 + 1 + i, y0, ch)
    canvas.set(x1, y0, '╗')

    # Side borders
    for y in range(y0 + 1, y1):
        canvas.set(x0, y, '║')
        canvas.set(x1, y, '║')

    # Bottom border: ╚════...════╝
    canvas.set(x0, y1, '╚')
    for x in range(x0 + 1, x1):
        canvas.set(x, y1, '═')
    canvas.set(x1, y1, '╝')
