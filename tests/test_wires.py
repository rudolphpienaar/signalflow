"""Tests for wire_forward_render and wire_return_render."""

from signalflow.lib.boxes import moduleBox_compute
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, innerWidth_get, layout_compute
from signalflow.lib.tree import col_assign, tree_flatten
from signalflow.lib.wires import thread_render
from signalflow.models import Node


def _full_render(root: Node):
    nodes = tree_flatten(root)
    col_assign(root)
    iw = innerWidth_get(nodes)
    ow = iw + 2
    cw = channelWidth_compute(root)
    layout_compute(root, ow, cw)
    boxes  = moduleBox_compute(nodes, ow)
    canvas = canvas_create(nodes, ow, cw, boxes)
    for n in nodes:
        chip_render(canvas, n, ow)
    thread_render(canvas, root, ow)
    return canvas, nodes, ow


class TestForwardWire:
    def test_forward_wire_places_entry_glyph(self):
        child = Node(module="M", func="child()", input_signal=None, children=[])
        root  = Node(module="M", func="root()", input_signal=None, children=[child])
        canvas, nodes, ow = _full_render(root)
        c = nodes[1]
        # ► is placed one column before the child left wall; wall itself keeps ┼
        assert canvas.get(c.x - 1, c.entry_row) == '►'
        assert canvas.get(c.x, c.entry_row) == '┼'

    def test_signal_label_present(self):
        child = Node(module="M", func="child()", input_signal="mySignal", children=[])
        root  = Node(module="M", func="root()", input_signal=None, children=[child])
        canvas, nodes, ow = _full_render(root)
        lines = canvas.lines_get()
        assert any('mySignal' in line for line in lines)


class TestReturnWire:
    def test_return_wire_connects(self):
        child = Node(module="M", func="child()", input_signal=None, children=[])
        root  = Node(module="M", func="root()", input_signal=None, children=[child])
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        rx = r.x + ow - 1
        # Root right wall return row (y+4) uses ├ (single-wall connection)
        assert canvas.get(rx, r.y + 4) == '├'


class TestRoutingInvariants:
    """Topological rules for wire routing."""

    def test_double_helix_invariant(self):
        """For staggered wires, Argument (Forward) is strictly to the RIGHT of Return."""
        c1 = Node(module="M", func="c1()", children=[])
        c2 = Node(module="M", func="c2()", children=[])
        root = Node(module="M", func="root()", children=[c1, c2])
        
        canvas, nodes, ow = _full_render(root)
        
        # Child 1 (index 0) will be staggered because it's not the last child?
        # Actually, in our new logic, all children use child.x - offset.
        # Let's check Child 1.
        
        # Forward channel for Child 1 (idx 0) row y+3
        # We need to find the column of the vertical segment.
        # Scan row y+3 from parent_rx+2 until we hit a turn Wire.RD (┐).
        r = nodes[0]
        rx = r.x + ow - 1
        
        def find_vchan(y, start_x):
            for x in range(start_x, start_x + 100):
                if canvas.get(x, y) in ('┐', '┘'):
                    return x
            return -1

        chan_f = find_vchan(r.y + 6, rx + 2)
        chan_r = find_vchan(r.y + 7, rx + 2)
        
        assert chan_f != -1, "Forward channel not found for staggered child 1"
        assert chan_r != -1, "Return channel not found for staggered child 1"
        # Argument (Forward) Right of Return
        assert chan_f > chan_r, f"Violation: Forward channel {chan_f} is not to the right of Return channel {chan_r}"
