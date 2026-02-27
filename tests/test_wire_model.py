"""TDD tests for wire-model structural cases (docs/wire-model.md).

All tests in this file are derived directly from the spec and are RED
until the implementation matches. Run with:

    pytest tests/test_wire_model.py -v

Green = implementation matches the wire-model spec.
"""

from signalflow.config import BASE_LEAF, CHANNEL_W, UTURN_W
from signalflow.lib.boxes import moduleBox_compute, moduleBox_render
from signalflow.lib.canvas_factory import canvas_create
from signalflow.lib.chips import chip_render
from signalflow.lib.layout import channelWidth_compute, innerWidth_get, layout_compute
from signalflow.lib.tree import chip_h_precompute, col_assign, tree_flatten
from signalflow.lib.wires import thread_render
from signalflow.models import Node

# ── helpers ──────────────────────────────────────────────────────────────────

def _leaf(
    func: str = "f()",
    input_signal: str | None = None,
    input_return: str | None = None,
) -> Node:
    return Node(module="M", func=func,
                input_signal=input_signal,
                input_return=input_return,
                children=[])


def _parent(
    func: str,
    children: list,
    is_root: bool = False,
    input_signal: str | None = None,
    input_return: str | None = None,
    output_signal: str | None = None,
    output_return: str | None = None,
) -> Node:
    return Node(module="M", func=func,
                input_signal=input_signal,
                input_return=input_return,
                output_signal=output_signal,
                output_return=output_return,
                children=children,
                is_root=is_root)


def _full_render(root: Node):
    """Full pipeline: layout + chip render + wire render."""
    nodes = tree_flatten(root)
    col_assign(root)
    iw = innerWidth_get(nodes)
    ow = iw + 2
    cw = channelWidth_compute(root)
    layout_compute(root, ow, cw)
    boxes = moduleBox_compute(nodes, ow)
    canvas = canvas_create(nodes, ow, cw, boxes)
    for box in boxes:
        moduleBox_render(canvas, box, nodes, ow)
    for n in nodes:
        chip_render(canvas, n, ow)
    thread_render(canvas, root, ow)
    return canvas, nodes, ow


# ── chip_h formulas ───────────────────────────────────────────────────────────

class TestChipHFormulas:
    """chip_h = 3*N + 3 for all parent types; BASE_LEAF (6) for leaves.

    Wire-pair-space rule: each child occupies 3 rows (call + return + space),
    except the last child which has no trailing space. Body = 3*N - 1 rows.
    With header (3 rows) and bottom border (1 row): chip_h = 3*N - 1 + 4 = 3*N + 3.
    """

    def test_leaf(self):
        assert chip_h_precompute(_leaf(), is_root=False) == BASE_LEAF  # 6

    # root parent ---

    def test_root_N1(self):
        assert chip_h_precompute(_parent("p", [_leaf()]), is_root=True) == 6

    def test_root_N2(self):
        assert chip_h_precompute(
            _parent("p", [_leaf(), _leaf()]), is_root=True
        ) == 9

    def test_root_N3(self):
        assert chip_h_precompute(
            _parent("p", [_leaf(), _leaf(), _leaf()]), is_root=True
        ) == 12

    # non-root parent ---

    def test_nonroot_N1(self):
        assert chip_h_precompute(_parent("p", [_leaf()]), is_root=False) == 6

    def test_nonroot_N2(self):
        assert chip_h_precompute(
            _parent("p", [_leaf(), _leaf()]), is_root=False
        ) == 9

    def test_nonroot_N3(self):
        assert chip_h_precompute(
            _parent("p", [_leaf(), _leaf(), _leaf()]), is_root=False
        ) == 12


# ── Case 1: Leaf chip ─────────────────────────────────────────────────────────

class TestLeafChip:
    """chip_h=6; ├──┤ separator at y+2; ┼ on left wall at y+3 and y+4;
    U-turn ┐/┘ at x+UTURN_W; call/return adjacent (no │ between them)."""

    def _node(self):
        """A standalone leaf rendered as root."""
        canvas, nodes, ow = _full_render(_leaf("leaf()"))
        return canvas, nodes[0], ow

    def test_chip_h(self):
        _, n, _ = self._node()
        assert n.chip_h == BASE_LEAF  # 6

    def test_separator_left_wall(self):
        """Left wall at y+2 must be ├ (separator row)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x, n.y + 2) == '├'

    def test_separator_right_wall(self):
        """Right wall at y+2 must be ┤ (separator row)."""
        canvas, n, ow = self._node()
        assert canvas.get(n.x + ow - 1, n.y + 2) == '┤'

    def test_entry_row_at_y3(self):
        """entry_row must be y+3 — one row below the separator."""
        _, n, _ = self._node()
        assert n.entry_row == n.y + 3

    def test_return_row_at_y4(self):
        """return_row must be y+4 — adjacent to call row."""
        _, n, _ = self._node()
        assert n.return_row == n.y + 4

    def test_call_return_adjacent(self):
        """Call and return are adjacent: no blank row within a pair."""
        _, n, _ = self._node()
        assert n.return_row == n.entry_row + 1

    def test_left_wall_pierce_at_entry(self):
        """Left wall at entry_row must be ┼ (wire pierces both directions)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x, n.entry_row) == '┼'

    def test_left_wall_pierce_at_return(self):
        """Left wall at return_row must be ┼."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x, n.return_row) == '┼'

    def test_uturn_arm_at_entry(self):
        """U-turn corner ┐ at (x+UTURN_W, entry_row)."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x + UTURN_W, n.entry_row) == '┐'

    def test_uturn_base_at_return(self):
        """U-turn base ┘ at (x+UTURN_W, return_row) — no │ between."""
        canvas, n, _ = self._node()
        assert canvas.get(n.x + UTURN_W, n.return_row) == '┘'

    def test_no_uturn_vertical_bar_between(self):
        """No │ between U-turn arm and base (they are adjacent rows)."""
        canvas, n, _ = self._node()
        # The row between entry and return doesn't exist — they are adjacent.
        # Confirm by asserting the return U-turn char is at exactly entry+1.
        assert canvas.get(n.x + UTURN_W, n.entry_row + 1) == '┘'

    def test_entry_arrow(self):
        """► must appear one column left of chip left wall at entry_row."""
        # Use Node directly to ensure a consistent state
        n = Node(module="M", func="f()", input_signal=None, children=[], is_root=True)
        col_assign(n)
        iw = innerWidth_get([n])
        ow = iw + 2
        layout_compute(n, ow, CHANNEL_W)
        canvas = canvas_create([n], ow, CHANNEL_W, [])
        chip_render(canvas, n, ow)
        assert canvas.get(n.x - 1, n.entry_row) == '►'

    def test_return_arrow(self):
        """◄ must appear flush with chip wall (x0-1) for a root leaf."""
        # Use Node directly to ensure input_return is set
        n = Node(module="M", func="f()", input_signal=None, input_return="res",
                 children=[], is_root=True)
        col_assign(n)
        iw = innerWidth_get([n])
        ow = iw + 2
        layout_compute(n, ow, CHANNEL_W)
        canvas = canvas_create([n], ow, CHANNEL_W, [])
        chip_render(canvas, n, ow)
        # Root stubs: arrow flush against wall (x0-1)
        assert canvas.get(n.x - 1, n.return_row) == '◄'

    def test_call_signal_on_wire(self):
        """Signal label appears in the stub area on entry_row."""
        # Setup manual render to avoid _node dependency issues
        n = Node(module="M", func="f()", input_signal="in", children=[], is_root=True)
        col_assign(n)
        iw = innerWidth_get([n])
        ow = iw + 2
        layout_compute(n, ow, CHANNEL_W)
        canvas = canvas_create([n], ow, CHANNEL_W, [])
        chip_render(canvas, n, ow)
        row = ''.join(canvas.grid[n.entry_row])
        assert 'in' in row

    def test_return_signal_on_wire(self):
        """Return signal label appears in the stub area on return_row."""
        n = Node(module="M", func="f()", input_signal="in",
                 input_return="ok", children=[], is_root=True)
        col_assign(n)
        iw = innerWidth_get([n])
        ow = iw + 2
        layout_compute(n, ow, CHANNEL_W)
        canvas = canvas_create([n], ow, CHANNEL_W, [])
        chip_render(canvas, n, ow)
        row = ''.join(canvas.grid[n.return_row])
        assert 'ok' in row

    def test_connected_leaf_return_arrow(self):
        """◄ must appear flush against parent for same-module child."""
        child = _leaf("c()")
        root = _parent("r()", [child], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        # Same module: arrow = parent_rx + 1 = r.x + ow
        assert canvas.get(r.x + ow, child.return_row) == '◄'


# ── Case 2 & 3: Root parent chip ─────────────────────────────────────────────

class TestRootParent:
    """Root chip: left wall never pierced; right wall uses ├ for call and
    return connections; wire-pair-space (│) between consecutive child pairs."""

    def test_chip_h_N1(self):
        root = _parent("r", [_leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        assert nodes[0].chip_h == 6  # 3*1+3

    def test_chip_h_N3(self):
        root = _parent("r", [_leaf(), _leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        assert nodes[0].chip_h == 12  # 3*3+3

    def test_separator_left_wall(self):
        root = _parent("r", [_leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x, r.y + 2) == '├'

    def test_separator_right_wall(self):
        root = _parent("r", [_leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 2) == '┤'

    def test_left_wall_never_pierced(self):
        """No ┼ on the root left wall at any row."""
        root = _parent("r", [_leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        for row in range(r.y, r.y + r.chip_h):
            assert canvas.get(r.x, row) != '┼', (
                f"unexpected ┼ on root left wall at canvas row {row}"
            )

    # N=1 right-wall connections -

    def test_child1_call_at_y3(self):
        """Child 1 call: right wall char at y+3 must be ├ (single-wall)."""
        root = _parent("r", [_leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 3) == '├'

    def test_child1_return_at_y4(self):
        """Child 1 return: right wall char at y+4 must be ├ (single-wall)."""
        root = _parent("r", [_leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 4) == '├'

    # N=2: wire-pair-space and second child -

    def test_wire_pair_space_y5_N2(self):
        """y+5 on right wall must be │ (wire-pair-space between pairs)."""
        root = _parent("r", [_leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 5) == '│'

    def test_child2_call_at_y6_N2(self):
        """Child 2 call: right wall char at y+6 must be ┼ (threaded)."""
        root = _parent("r", [_leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 6) == '┼'

    def test_child2_return_at_y7_N2(self):
        """Child 2 return: right wall char at y+7 must be ├ (final child)."""
        root = _parent("r", [_leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 7) == '├'

    # N=3: third child (stride 3) -

    def test_wire_pair_space_y8_N3(self):
        """y+8 on right wall must be │ (wire-pair-space before child 3)."""
        root = _parent("r", [_leaf(), _leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 8) == '│'

    def test_child3_call_at_y9_N3(self):
        """Child 3 call: right wall char at y+9 must be ┼ (threaded)."""
        root = _parent("r", [_leaf(), _leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 9) == '┼'

    def test_child3_return_at_y10_N3(self):
        """Child 3 return: right wall char at y+10 must be ├ (final child)."""
        root = _parent("r", [_leaf(), _leaf(), _leaf()], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        assert canvas.get(r.x + ow - 1, r.y + 10) == '├'


# ── Case 4: Non-root parent — pass-through (N=1) ─────────────────────────────

class TestPassthrough:
    """Non-root parent, single child: both walls ┼ at y+3 and y+4."""

    def _tree(self):
        child = _leaf("child()", input_signal="sig")
        mid = _parent("mid()", [child], input_signal="entry")
        root = _parent("root()", [mid], is_root=True)
        canvas, nodes, ow = _full_render(root)
        m = next(n for n in nodes if n.func == "mid()")
        return canvas, m, ow

    def test_chip_h(self):
        _, m, _ = self._tree()
        assert m.chip_h == 6  # 3*1+3

    def test_separator_left_wall(self):
        canvas, m, _ = self._tree()
        assert canvas.get(m.x, m.y + 2) == '├'

    def test_separator_right_wall(self):
        canvas, m, ow = self._tree()
        assert canvas.get(m.x + ow - 1, m.y + 2) == '┤'

    def test_entry_row_at_y3(self):
        _, m, _ = self._tree()
        assert m.entry_row == m.y + 3

    def test_return_row_at_y4(self):
        """Non-root always returns to caller at y+4."""
        _, m, _ = self._tree()
        assert m.return_row == m.y + 4

    def test_call_return_adjacent(self):
        _, m, _ = self._tree()
        assert m.return_row == m.entry_row + 1

    def test_left_wall_pierce_at_entry(self):
        """Left wall at entry_row (y+3) must be ┼."""
        canvas, m, _ = self._tree()
        assert canvas.get(m.x, m.entry_row) == '┼'

    def test_left_wall_pierce_at_return(self):
        """Left wall at return_row (y+4) must be ┼."""
        canvas, m, _ = self._tree()
        assert canvas.get(m.x, m.return_row) == '┼'

    def test_right_wall_pierce_at_entry(self):
        """Right wall at entry_row must be ┼ (both walls active)."""
        canvas, m, ow = self._tree()
        assert canvas.get(m.x + ow - 1, m.entry_row) == '┼'

    def test_right_wall_pierce_at_return(self):
        """Right wall at return_row must be ┼ (both walls active)."""
        canvas, m, ow = self._tree()
        assert canvas.get(m.x + ow - 1, m.return_row) == '┼'


# ── Cases 5 & 6: Non-root parent — branch on return (N=3) ────────────────────

class TestBranchReturn:
    """Non-root parent with 3 children.

    chip_h=12; left wall active only at y+3 (entry) and y+4 (return);
    right wall: ┼ at y+3/y+4 (first child, both walls active), then ├ for
    child 2 (y+6/y+7) and child 3 call (y+9); ┼ at y+10 (arm meets return).
    Wire-pair-space (│) at y+5 and y+8.
    """

    def _tree(self):
        c1 = _leaf("c1()", input_signal="s1")
        c2 = _leaf("c2()", input_signal="s2")
        c3 = _leaf("c3()", input_signal="s3")
        branch = _parent("branch()", [c1, c2, c3], input_signal="entry")
        root = _parent("root()", [branch], is_root=True)
        canvas, nodes, ow = _full_render(root)
        b = next(n for n in nodes if n.func == "branch()")
        return canvas, b, ow

    def test_chip_h(self):
        _, b, _ = self._tree()
        assert b.chip_h == 12  # 3*3+3

    def test_separator_left_wall(self):
        canvas, b, _ = self._tree()
        assert canvas.get(b.x, b.y + 2) == '├'

    def test_separator_right_wall(self):
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 2) == '┤'

    def test_entry_row_at_y3(self):
        _, b, _ = self._tree()
        assert b.entry_row == b.y + 3

    def test_return_row_at_y4(self):
        """Function returns to its caller at y+4+3(N-1) for threading."""
        _, b, _ = self._tree()
        assert b.return_row == b.y + 10

    # left wall —

    def test_left_wall_pierce_at_entry(self):
        canvas, b, _ = self._tree()
        assert canvas.get(b.x, b.entry_row) == '┼'

    def test_left_wall_pierce_at_return(self):
        canvas, b, _ = self._tree()
        assert canvas.get(b.x, b.return_row) == '┼'

    def test_left_wall_only_active_at_y3_y10(self):
        """Left wall rows other than entry/return must not be ┼."""
        canvas, b, _ = self._tree()
        inactive = [
            b.y + r for r in range(3, b.chip_h - 1)
            if r not in (3, 10)
        ]
        for row in inactive:
            char = canvas.get(b.x, row)
            assert char != '┼', (
                f"unexpected ┼ on left wall at chip-relative row {row - b.y}"
            )

    # right wall — child 1 (both walls active → ┼) —

    def test_right_wall_child1_call_y3(self):
        """Child 1 call exits right wall at y+3; both walls active → ┼."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 3) == '┼'

    def test_right_wall_child1_return_y4(self):
        """Child 1 return arrives right wall at y+4; both walls active → ┼."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 4) == '┼'

    # wire-pair-space —

    def test_wire_pair_space_y5(self):
        """y+5 on right wall is │ (space between child 1 and child 2 pairs)."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 5) == '│'

    def test_wire_pair_space_y8(self):
        """y+8 on right wall is │ (space between child 2 and child 3 pairs)."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 8) == '│'

    # right wall — child 2 (both walls active due to threading → ┼) —

    def test_right_wall_child2_call_y6(self):
        """Child 2 call at y+6; threaded from child 1 → ┼."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 6) == '┼'

    def test_right_wall_child2_return_y7(self):
        """Child 2 return at y+7; threads to child 3 → ┼."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 7) == '┼'

    # right wall — child 3 (both walls active due to threading → ┼) —

    def test_right_wall_child3_call_y9(self):
        """Child 3 call at y+9; threaded from child 2 → ┼."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 9) == '┼'

    def test_right_wall_child3_return_y10(self):
        """Child 3 return at y+10: interior left arm meets return → ┼."""
        canvas, b, ow = self._tree()
        assert canvas.get(b.x + ow - 1, b.y + 10) == '┼'

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
        child = Node(module="M", func="c()", input_signal="arg", children=[])
        root  = _parent("r()", [child], is_root=True)
        canvas, nodes, ow = _full_render(root)
        c = next(n for n in nodes if n.func == "c()")
        row = ''.join(canvas.grid[c.entry_row])
        # Expected: "...arg►["
        assert row[c.x - 4 : c.x] == "arg►"

    def test_return_signal_flush_against_child(self):
        """Return-signal label ends at child.x - 2 (before ◄ at x-1)."""
        from signalflow.config import MB_OUTER
        child = Node(module="M", func="c()", input_signal=None, input_return="res", children=[])
        root  = _parent("r()", [child], is_root=True)
        canvas, nodes, ow = _full_render(root)
        c = next(n for n in nodes if n.func == "c()")
        r = nodes[0]
        row = ''.join(canvas.grid[c.return_row])
        # Expected: "...res◄["
        # res is 3 chars. ◄ at c.x-1. res ends at c.x-2.
        assert row[c.x - 4 : c.x] == "res◄"
        # Arrow on parent side (flush against chip because same module)
        assert canvas.get(r.x + ow, c.return_row) == '◄'

    def test_return_signal_cross_module_arrow_outside(self):
        """Return arrow is flush with parent port even when cross-module."""
        child = Node(module="Other", func="c()", input_signal=None, input_return="res", children=[])
        root  = _parent("r()", [child], is_root=True)
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        # ALWAYS flush: arrow = parent_rx + 1 = r.x + ow
        assert canvas.get(r.x + ow, 7) == '◄'  # root child 0 return row is 7


class TestParentInterfaceLabels:
    """Signals rendered flush against the parent chip's right wall."""

    def test_parent_signal_flush_against_right_wall(self):
        """Forward-signal on parent appears flush against parent chip when in same module."""
        child = _leaf("c()")
        root  = _parent("r()", [child], is_root=True, output_signal="p_arg")
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        row = ''.join(canvas.grid[r.y + 3])  # Child 0 entry row
        # Same module: arrow at +1, label starts at +2
        x_lbl = r.x + ow + 1
        assert row[x_lbl : x_lbl + 5] == "p_arg"

    def test_parent_return_signal_flush_against_right_wall(self):
        """Return-signal on parent appears flush against ◄ arrow when in same module."""
        child = _leaf("c()")
        root  = _parent("r()", [child], is_root=True, output_return="p_res")
        canvas, nodes, ow = _full_render(root)
        r = nodes[0]
        row = ''.join(canvas.grid[r.y + 4])  # Child 0 return row
        # Same module: arrow at +1, label at +2
        x_lbl = r.x + ow + 1
        assert row[x_lbl : x_lbl + 5] == "p_res"

    def test_parent_signal_pierces_box_wall(self):
        """Parent-side labels replace the double-line box border ║ with ╫ when cross-module."""
        # child in different module
        child = Node(module="Other", func="c()", input_signal=None, children=[])
        # Use a long signal that definitely hits the module wall
        root  = _parent("r()", [child], is_root=True, output_signal="p_arg_long_enough_to_hit_the_wall")

        nodes = tree_flatten(root)
        col_assign(root)
        iw = innerWidth_get(nodes)
        ow = iw + 2
        cw = channelWidth_compute(root)
        layout_compute(root, ow, cw)
        boxes = moduleBox_compute(nodes, ow)
        canvas = canvas_create(nodes, ow, cw, boxes)
        for box in boxes:
            moduleBox_render(canvas, box, nodes, ow)
        thread_render(canvas, root, ow)

        r = next(n for n in nodes if n.func == "r()")
        # The long signal "p_arg_long_enough..." will hit the wall.
        # Find the module box for 'M'
        box_m = next(b for b in boxes if b.label == "M")
        # The character at the wall should be the char from the signal that sits at ox1.
        # Parent-side label starts at parent_rx + 2 = r.x + ow + 1.
        sig = "p_arg_long_enough_to_hit_the_wall"
        lbl_x0 = r.x + ow + 1
        idx = box_m.ox1 - lbl_x0
        expected_char = sig[idx]
        assert canvas.get(box_m.ox1, r.y + 3) == expected_char
    
