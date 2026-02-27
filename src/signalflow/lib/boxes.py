"""Module box computation and rendering."""

from signalflow.config import MB_OUTER, MB_TOP
from signalflow.models import Canvas, ModuleBox


def moduleBox_compute(nodes: list, ow: int) -> list:
    """Compute single module box grouping all same-module chips.

    The box sits MB_OUTER columns from the chip on every side.  Signal labels
    and approach wires appear to the LEFT of the box, in the open canvas area.
    """
    groups: dict = {}
    for n in nodes:
        groups.setdefault(n.module, []).append(n)

    boxes = []
    for module, mnodes in groups.items():
        min_chip_x   = min(nd.x for nd in mnodes)
        min_chip_y   = min(nd.y for nd in mnodes)
        max_chip_rx  = max(nd.x + ow for nd in mnodes)
        max_chip_bot = max(nd.y + nd.chip_h for nd in mnodes)

        # Account for staggered channels if they extend beyond the chip
        max_chan_x = max_chip_rx
        for n in mnodes:
            if n.children:
                # channel_x = parent_rx + 2 + 2*child_idx [+ 1 for return]
                # parent_rx = n.x + ow - 1
                chan_x = n.x + ow - 1 + 2 + 2 * (len(n.children) - 1) + 1
                max_chan_x = max(max_chan_x, chan_x)

        ox0 = max(0, min_chip_x - MB_OUTER)
        oy0 = max(0, min_chip_y - MB_TOP)
        ox1 = max_chan_x + MB_OUTER - 1
        oy1 = max_chip_bot + MB_OUTER - 1

        boxes.append(ModuleBox(
            label=module,
            ox0=ox0, oy0=oy0, ox1=ox1, oy1=oy1,
        ))

    return boxes


def moduleBox_render(canvas: Canvas, box: ModuleBox, nodes: list, ow: int) -> None:
    """Write single double-line module box border with label in top border."""
    x0, y0, x1, y1 = box.ox0, box.oy0, box.ox1, box.oy1
    inner_w = x1 - x0 - 1
    if inner_w <= 0:
        return

    # Map nodes to parents to check cross-module entry wires
    parent_map = {}
    for p in nodes:
        for c in p.children:
            parent_map[id(c)] = p

    # Proactively identify rows/cols that must pierce the borders.
    pierce_left   = set()
    pierce_right  = set()
    pierce_bottom = set()

    for n in nodes:
        if n.module == box.label:
            parent = parent_map.get(id(n))
            # Left wall (x0) is pierced if:
            # 1. Node is root AND has stub signals (incoming from outside).
            # 2. Caller is in a different module.
            if n.is_root:
                if not n.children:
                    if n.input_signal: pierce_left.add(n.y + 3)
                    if n.input_return: pierce_left.add(n.y + 4)
            elif parent and parent.module != n.module:
                pierce_left.add(n.entry_row)
                pierce_left.add(n.return_row)

            # Right/Bottom walls are pierced if a child is below/outside.
            for i, child in enumerate(n.children):
                parent_rx = n.x + ow - 1
                # Forward channel at rx+2+2i, Return channel at rx+2+2i+1
                chan_f = parent_rx + 2 + 2 * i
                chan_r = parent_rx + 3 + 2 * i

                if child.module != n.module:
                    if n.is_root:
                        pierce_right.add(n.y + 3 + 3 * i)
                        pierce_right.add(n.y + 4 + 3 * i)
                    else:
                        pierce_right.add(n.entry_row + 3 * i)
                        pierce_right.add(n.entry_row + 1 + 3 * i)
                
                # A vertical wire exists if exit_y != entry_y.
                # If the child's entry is BELOW the box bottom (y1), 
                # then these channels must pierce the bottom wall.
                if child.entry_row > y1:
                    pierce_bottom.add(chan_f)
                    pierce_bottom.add(chan_r)

    # Top border: ╔═ label ════...════╗
    canvas.set(x0, y0, '╔')
    fill = ('═ ' + box.label + ' ').ljust(inner_w, '═')[:inner_w]
    for i, ch in enumerate(fill):
        canvas.set(x0 + 1 + i, y0, ch)
    canvas.set(x1, y0, '╗')

    # Side borders
    for y in range(y0 + 1, y1):
        canvas.set(x0, y, '╫' if y in pierce_left  else '║')
        canvas.set(x1, y, '╫' if y in pierce_right else '║')

    # Bottom border: ╚════...════╝
    canvas.set(x0, y1, '╚')
    for x in range(x0 + 1, x1):
        canvas.set(x, y1, '╪' if x in pierce_bottom else '═')
    canvas.set(x1, y1, '╝')
