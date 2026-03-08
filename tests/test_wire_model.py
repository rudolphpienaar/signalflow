"""TDD tests for wire-model structural cases (docs/wire-model.md).

All tests in this file are derived directly from the spec and are RED
until the implementation matches. Run with:

    pytest tests/test_wire_model.py -v

Green = implementation matches the wire-model spec.
"""

from signalflow.config import config
from signalflow.lib.boxes import moduleBox_compute, moduleBox_render
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.models.chip_geometry import ChipGeometry
from signalflow.lib.wires import thread_render
from signalflow.models import Node, PortKey
from signalflow.models.node import Port

# ── helpers ──────────────────────────────────────────────────────────────────

def _leaf(
    func: str = "f()",
    inputSignal: str | None = None,
    inputReturn: str | None = None,
) -> Node:
    ports = [Port(inputSignal, inputReturn)] if (inputSignal or inputReturn) else []
    return Node(module="M", func=func, unbound_inputs=ports, children=[])


def _parent(
    func: str,
    children: list,
    isRoot: bool = False,
    inputSignal: str | None = None,
    inputReturn: str | None = None,
    outputSignal: str | None = None,
    outputReturn: str | None = None,
) -> Node:
    inPorts = [Port(inputSignal, inputReturn)] if (inputSignal or inputReturn) else []
    outPorts = [Port(outputSignal, outputReturn)] if (outputSignal or outputReturn) else []
    return Node(module="M", func=func,
                unbound_inputs=inPorts,
                unbound_outputs=outPorts,
                children=children)


def _bind_ports(root: Node) -> None:
    """Bind parent/child ports so layout assigns entryRows correctly."""
    for child in root.children:
        # call_index = 0 for every edge (test trees call each child at most once)
        in_key:  PortKey = (id(root),  0)
        out_key: PortKey = (id(child), 0)
        if in_key not in child.input_ports:
            p = child.unbound_inputs[0] if child.unbound_inputs else Port()
            child.input_ports[in_key] = p
        if out_key not in root.output_ports:
            slot = len(root.output_ports)
            p = root.unbound_outputs[slot] if slot < len(root.unbound_outputs) else Port()
            root.output_ports[out_key] = p
        if not any(c is child for c, *_ in root.call_sequence):
            root.call_sequence.append((child, out_key, in_key))
        _bind_ports(child)


def _full_render(root: Node):
    """Full pipeline: layout + chip render + wire render."""
    _bind_ports(root)
    nodes = tree_flatten(root)
    cw = channelWidth_compute(root)
    layout_compute(root, cw)
    boxes = moduleBox_compute(nodes)
    canvas = canvas_create(nodes, cw, boxes)
    for box in boxes:
        moduleBox_render(canvas, box, nodes)
    for n in nodes:
        chip_render(canvas, n)
    thread_render(canvas, root)
    # For compatibility: return root.ow as the global ow estimate
    ow = root.ow
    return canvas, nodes, ow


# ── chipH formulas ───────────────────────────────────────────────────────────

class TestChipHFormulas:
    """chipH = 3*N + 3 for all parent types; config.baseLeafHeight (6) for leaves.

    Wire-pair-space rule: each child occupies 3 rows (call + return + space),
    except the last child which has no trailing space. Body = 3*N - 1 rows.
    With header (3 rows) and bottom border (1 row): chipH = 3*N - 1 + 4 = 3*N + 3.
    """

    def test_leaf(self):
        assert ChipGeometry.build_structural(_leaf()).chipH == 7  # gap row bumps min

    # root parent ---

    def test_root_N1(self):
        assert ChipGeometry.build_structural(_parent("p", [_leaf()])).chipH == 6

    def test_root_N2(self):
        assert ChipGeometry.build_structural(
            _parent("p", [_leaf(), _leaf()])
        ).chipH == 9

    def test_root_N3(self):
        assert ChipGeometry.build_structural(
            _parent("p", [_leaf(), _leaf(), _leaf()])
        ).chipH == 12

    # non-root parent ---

    def test_nonroot_N1(self):
        assert ChipGeometry.build_structural(_parent("p", [_leaf()])).chipH == 6

    def test_nonroot_N2(self):
        assert ChipGeometry.build_structural(
            _parent("p", [_leaf(), _leaf()])
        ).chipH == 9

    def test_nonroot_N3(self):
        assert ChipGeometry.build_structural(
            _parent("p", [_leaf(), _leaf(), _leaf()])
        ).chipH == 12


# ── Case 1: Leaf chip ─────────────────────────────────────────────────────────

class TestLeafChip:
    """chipH=6; ├──┤ separator at y+2; ┼ on left wall at y+3 and y+4;
    U-turn ┐/┘ at x+config.uTurnWidth; call/return adjacent (no │ between them)."""

    def _node(self):
        """Leaf rendered as child of a root parent (so entryRows are populated)."""
        child = _leaf("leaf()")
        root = _parent("r()", [child])
        canvas, nodes, ow = _full_render(root)
        n = next(nd for nd in nodes if nd.func == "leaf()")
        return canvas, n, n.ow

    def test_chipH(self):
        _, n, _ = self._node()
        assert n.chipH == 7   # gap row between entry and return bumps leaf minimum

    def test_separator_left_wall(self):
        """Left wall at y+2 must be ├ (separator row)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x, n.y + 2) == '├'

    def test_separator_right_wall(self):
        """Right wall at y+2 must be ┤ (separator row)."""
        canvas, n, ow = self._node()
        assert canvas.get(n.x + ow - 1, n.y + 2) == '┤'

    def test_entryRow_at_y3(self):
        """entryRow must be y+3 — one row below the separator."""
        _, n, _ = self._node()
        assert n.entryRow == n.y + 3

    def test_returnRow_at_y5(self):
        """returnRow must be y+5 — one gap row below entryRow."""
        _, n, _ = self._node()
        assert n.returnRow == n.y + 5

    def test_call_return_gap_is_two(self):
        """One gap row separates call and return: returnRow == entryRow + 2."""
        _, n, _ = self._node()
        assert n.returnRow == n.entryRow + 2

    def test_left_wall_pierce_at_entry(self):
        """Left wall at entryRow must be │ (no reactive piercing for external arrow)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x, n.entryRow) == '│'

    def test_left_wall_pierce_at_return(self):
        """Left wall at returnRow must be │."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x, n.returnRow) == '│'

    def test_uturn_arm_at_entry(self):
        """U-turn corner ┐ at (x+config.uTurnWidth, entryRow)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x + config.uTurnWidth, n.entryRow) == '┐'

    def test_uturn_base_at_return(self):
        """U-turn base ┘ at (x+config.uTurnWidth, returnRow) — no │ between."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x + config.uTurnWidth, n.returnRow) == '┘'

    def test_computation_block_in_gap_row(self):
        """Gap row (entryRow+1) holds █ when implicitThread='block' (default)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x + config.uTurnWidth, n.entryRow + 1) == '█'

    def test_uturn_base_still_at_return_row(self):
        """U-turn base ┘ is at returnRow (now entryRow+2)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x + config.uTurnWidth, n.returnRow) == '┘'

    def test_connected_leaf_return_arrow(self):
        """◄ must appear on the parent's right wall at the parent's return slot."""
        child = _leaf("c()")
        root = _parent("r()", [child])
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        # parentRetY = r.y + 4 (ewOff=0, spacing=3, pIdx=0 for the single child)
        assert canvas.get(r.x + r.ow, r.y + 4) == '◄'


# ── Case 2 & 3: Root parent chip ─────────────────────────────────────────────

class TestRootParent:
    """Root chip: left wall never pierced; right wall uses ├ for call and
    return connections; wire-pair-space (│) between consecutive child pairs."""

    def test_chipH_N1(self):
        root = _parent("r", [_leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        assert nodes[0].chipH == 6  # 3*1+3

    def test_chipH_N3(self):
        root = _parent("r", [_leaf(), _leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        assert nodes[0].chipH == 12  # 3*3+3

    def test_separator_left_wall(self):
        root = _parent("r", [_leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x, r.y + 2) == '├'

    def test_separator_right_wall(self):
        root = _parent("r", [_leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 2) == '┤'

    def test_left_wall_never_pierced(self):
        """No ┼ on the root left wall at any row."""
        root = _parent("r", [_leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        for row in range(r.y, r.y + r.chipH):
            assert canvas.get(r.x, row) != '┼', (
                f"unexpected ┼ on root left wall at canvas row {row}"
            )

    # N=1 right-wall connections -

    def test_child1_call_at_y3(self):
        """Child 1 call: right wall char at y+3 must be │ (arrow is at rx+1)."""
        root = _parent("r", [_leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 3) == '│'

    def test_child1_return_at_y4(self):
        """Child 1 return: right wall char at y+4 must be │."""
        root = _parent("r", [_leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 4) == '│'

    # N=2: wire-pair-space and second child -

    def test_wire_pair_space_y5_N2(self):
        """y+5 on right wall must be │ (wire-pair-space between pairs)."""
        root = _parent("r", [_leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 5) == '│'

    def test_child2_call_at_y6_N2(self):
        """Child 2 call: right wall char at y+6 must be │."""
        root = _parent("r", [_leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 6) == '│'

    def test_child2_return_at_y7_N2(self):
        """Child 2 return: right wall char at y+7 must be │."""
        root = _parent("r", [_leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 7) == '│'

    # N=3: third child (stride 3) -

    def test_wire_pair_space_y8_N3(self):
        """y+8 on right wall must be │ (wire-pair-space before child 3)."""
        root = _parent("r", [_leaf(), _leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 8) == '│'

    def test_child3_call_at_y9_N3(self):
        """Child 3 call: right wall char at y+9 must be │."""
        root = _parent("r", [_leaf(), _leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 9) == '│'

    def test_child3_return_at_y10_N3(self):
        """Child 3 return: right wall char at y+10 must be │."""
        root = _parent("r", [_leaf(), _leaf(), _leaf()], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + r.ow - 1, r.y + 10) == '│'


# ── Case 4: Non-root parent — pass-through (N=1) ─────────────────────────────

class TestPassthrough:
    """Non-root parent, single child: both walls ┼ at y+3 and y+4."""

    def _tree(self):
        child = _leaf("child()", inputSignal="sig")
        mid = _parent("mid()", [child], inputSignal="entry")
        root = _parent("root()", [mid], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        m = next(n for n in nodes if n.func == "mid()")
        return canvas, m, ow

    def test_chipH(self):
        _, m, _ = self._tree()
        assert m.chipH == 6  # 3*1+3

    def test_separator_left_wall(self):
        canvas, m, _ = self._tree()
        assert canvas.get(m.x, m.y + 2) == '├'

    def test_separator_right_wall(self):
        canvas, m, ow = self._tree()
        assert canvas.get(m.x + m.ow - 1, m.y + 2) == '┤'

    def test_entryRow_at_y3(self):
        _, m, _ = self._tree()
        assert m.entryRow == m.y + 3

    def test_returnRow_at_y4(self):
        """Non-root always returns to caller at y+4."""
        _, m, _ = self._tree()
        assert m.returnRow == m.y + 4

    def test_call_return_adjacent(self):
        _, m, _ = self._tree()
        assert m.returnRow == m.entryRow + 1

    def test_left_wall_pierce_at_entry(self):
        """Left wall at entryRow (y+3) must be │."""
        canvas, m, _ = self._tree()
        assert canvas.get(m.x, m.entryRow) == '│'

    def test_left_wall_pierce_at_return(self):
        """Left wall at returnRow (y+4) must be │."""
        canvas, m, _ = self._tree()
        assert canvas.get(m.x, m.returnRow) == '│'

    def test_right_wall_pierce_at_entry(self):
        """Right wall at entryRow must be │."""
        canvas, m, ow = self._tree()
        assert canvas.get(m.x + m.ow - 1, m.entryRow) == '│'

    def test_right_wall_pierce_at_return(self):
        """Right wall at returnRow must be │."""
        canvas, m, ow = self._tree()
        assert canvas.get(m.x + m.ow - 1, m.returnRow) == '│'


# ── Cases 5 & 6: Non-root parent — branch on return (N=3) ────────────────────

class TestBranchReturn:
    """Non-root parent with 3 children.

    chipH=12; left wall remains │ (external arrows don't pierce);
    right wall remains │ (external arrows don't pierce).
    Wire-pair-space (│) at y+5 and y+8.
    """

    def _tree(self):
        c1 = _leaf("c1()", inputSignal="s1")
        c2 = _leaf("c2()", inputSignal="s2")
        c3 = _leaf("c3()", inputSignal="s3")
        branch = _parent("branch()", [c1, c2, c3], inputSignal="entry")
        root = _parent("root()", [branch], isRoot=True)
        canvas, nodes, ow = _full_render(root)
        b = next(n for n in nodes if n.func == "branch()")
        return canvas, b, ow

    def test_chipH(self):
        _, b, _ = self._tree()
        assert b.chipH == 12  # 3*3+3

    def test_separator_left_wall(self):
        canvas, b, _ = self._tree()
        assert canvas.get(b.x, b.y + 2) == '├'

    def test_separator_right_wall(self):
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 2) == '┤'

    def test_entryRow_at_y3(self):
        _, b, _ = self._tree()
        assert b.entryRow == b.y + 3

    def test_returnRow_at_y4(self):
        """Function returns to its caller at y+4 (first port)."""
        _, b, _ = self._tree()
        assert b.returnRow == b.y + 4

    # left wall —

    def test_left_wall_pierce_at_entry(self):
        canvas, b, _ = self._tree()
        assert canvas.get(b.x, b.entryRow) == '│'

    def test_left_wall_pierce_at_return(self):
        canvas, b, _ = self._tree()
        assert canvas.get(b.x, b.returnRow) == '│'

    def test_left_wall_only_active_at_y3_y4(self):
        """Left wall rows should all be │ for simple branch."""
        canvas, b, _ = self._tree()
        for row in range(b.y + 3, b.y + b.chipH - 1):
            char = canvas.get(b.x, row)
            assert char == '│', (
                f"unexpected {char} on left wall at chip-relative row {row - b.y}"
            )

    # right wall — child 1 —

    def test_right_wall_child1_call_y3(self):
        """Child 1 call exits right wall at y+3; arrow at rx+1 → │."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 3) == '│'

    def test_right_wall_child1_return_y4(self):
        """Child 1 return arrives right wall at y+4; arrow at rx+1 → │."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 4) == '│'

    # wire-pair-space —

    def test_wire_pair_space_y5(self):
        """y+5 on right wall is │ (space between child 1 and child 2 pairs)."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 5) == '│'

    def test_wire_pair_space_y8(self):
        """y+8 on right wall is │ (space between child 2 and child 3 pairs)."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 8) == '│'

    # right wall — child 2 —

    def test_right_wall_child2_call_y6(self):
        """Child 2 call at y+6 → │."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 6) == '│'

    def test_right_wall_child2_return_y7(self):
        """Child 2 return at y+7 → │."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 7) == '│'

    # right wall — child 3 —

    def test_right_wall_child3_call_y9(self):
        """Child 3 call at y+9 → │."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 9) == '│'

    def test_right_wall_child3_return_y10(self):
        """Child 3 return at y+10 → │."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + b.ow - 1, b.y + 10) == '│'

    # signal labels —

    def test_signal_labels_in_output(self):
        """Each child's signal label must appear somewhere on the canvas."""
        canvas, b, _ = self._tree()
        lines = canvas.lines_get()
        joined = '\n'.join(lines)
        assert 's1' in joined
        assert 's2' in joined
        assert 's3' in joined


# ── Interface Labels (Flush) ────────────────────────────────────────────────

class TestConnectedInterfaceLabels:
    """Signals rendered flush against the child chip's left wall."""

    def test_forward_signal_flush_against_child(self):
        """Forward-signal label ends at child.x - 2 (just before ► at x-1)."""
        child = _leaf("c()", inputSignal="arg")
        root  = _parent("r()", [child])
        canvas, nodes, ow = _full_render(root)
        c = next(n for n in nodes if n.func == "c()")
        row = ''.join(cell[0] for cell in canvas.grid[c.entryRow])
        # Expected: "...arg►["
        assert row[c.x - 4 : c.x] == "arg►"

    def test_return_signal_flush_against_child(self):
        """Return-signal label near child left wall at child.returnRow."""
        child = _leaf("c()", inputReturn="res")
        root  = _parent("r()", [child])
        canvas, nodes, ow = _full_render(root)
        c = next(n for n in nodes if n.func == "c()")
        r = nodes[0]
        row = ''.join(cell[0] for cell in canvas.grid[c.returnRow])
        # ◄ at child.x-1 with label to its left
        assert row[c.x - 4 : c.x] == "res◄"
        # Arrow on parent side lands at r.y+4 (parentRetY for pIdx=0, ewOff=0)
        assert canvas.get(r.x + r.ow, r.y + 4) == '◄'

    def test_return_signal_cross_module_arrow_outside(self):
        """Return arrow is flush with parent port even when cross-module."""
        child = Node(module="Other", func="c()", unbound_inputs=[Port(None, "res")], children=[])
        root  = _parent("r()", [child])
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        # ALWAYS flush: arrow = parent_rx + 1 = r.x + r.ow
        assert canvas.get(r.x + r.ow, 7) == '◄'  # root child 0 return row is 7


class TestParentInterfaceLabels:
    """Signals rendered flush against the parent chip's right wall."""

    def test_parent_signal_flush_against_right_wall(self):
        """Forward-signal on parent appears flush against parent chip when in same module."""
        child = _leaf("c()")
        root  = _parent("r()", [child], isRoot=True, outputSignal="p_arg")
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        row = ''.join(cell[0] for cell in canvas.grid[r.y + 3])  # Child 0 entry row
        # Same module: arrow at +1, label starts at +2
        x_lbl = r.x + r.ow + 1
        assert row[x_lbl : x_lbl + 5] == "p_arg"

    def test_parent_return_signal_flush_against_right_wall(self):
        """Return-signal on parent appears flush against ◄ arrow when in same module."""
        child = _leaf("c()")
        root  = _parent("r()", [child], isRoot=True, outputReturn="p_res")
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        row = ''.join(cell[0] for cell in canvas.grid[r.y + 4])  # Child 0 return row
        # Same module: arrow at +1, label at +2
        x_lbl = r.x + r.ow + 1
        assert row[x_lbl : x_lbl + 5] == "p_res"

    def test_parent_signal_pierces_box_wall(self):
        """Parent-side labels replace the double-line box border ║ with ╫ when cross-module."""
        # child in different module
        child = Node(module="Other", func="c()", children=[])
        # Use a long signal that definitely hits the module wall
        root  = _parent("r()", [child], outputSignal="p_arg_long_enough_to_hit_the_wall")

        canvas, nodes, ow = _full_render(root)

        r = next(n for n in nodes if n.func == "r()")
        boxes = moduleBox_compute(nodes)
        # The long signal "p_arg_long_enough..." will hit the wall.
        # Find the module box for 'M'
        box_m = next(b for b in boxes if b.label == "M")
        # The character at the wall should be the char from the signal that sits at ox1.
        # Parent-side label starts at parent_rx + 2 = r.x + r.ow + 1.
        sig = "p_arg_long_enough_to_hit_the_wall"
        lbl_x0 = r.x + r.ow + 1
        idx = box_m.ox1 - lbl_x0
        expected_char = sig[idx]
        assert canvas.get(box_m.ox1, r.y + 3) == expected_char

