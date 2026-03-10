"""TDD tests for ChipGeometry consolidation.

Phase 0: geometry invariants via ChipGeometry.build_structural (ewOff, chipH, chipOw).
Phase 2: Stage-2 resolve() tests (wall rows, anchors, straight-through classification).

Tests marked xfail expose confirmed latent bugs scheduled for later phases.
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from signalflow.config import config
from signalflow.lib.layout import channelWidth_compute, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.models.chip_geometry import ChipGeometry
from signalflow.models.node import Node, Port

# ── config fixture ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    """Restore singleton config to its state before each test."""
    saved = {f.name: getattr(config, f.name) for f in fields(config)}
    yield
    for name, val in saved.items():
        setattr(config, name, val)


# ── node builders ─────────────────────────────────────────────────────────────

def _leaf(func: str = "leaf()") -> Node:
    return Node(module="M", func=func)


def _proxy_node(sig: str = "s1", ret: str = "r1") -> Node:
    """Proxy chip: 1 input, 1 output, straight-through wiring (sX:sX, rX:rX)."""
    parent = Node(module="App", func="main()")
    hub    = Node(module="Hub", func="process()")
    node   = Node(module="Proxy", func="p()")
    node.input_ports[id(parent)]  = Port(signal=sig, ret=ret)
    node.output_ports[id(hub)]    = Port(signal=sig, ret=ret)
    node.internal_wiring          = [f"{sig}:{sig}", f"{ret}:{ret}"]
    node.children                 = [hub]
    return node


def _hub_process_node() -> Node:
    """Hub process(): 5 sovereign inputs, 5 outputs, s1→out1..5, ret1..5→r1."""
    node = Node(module="Hub", func="process()")
    node.inputExplicit = False
    parents  = [Node(module="Proxy", func=f"p{i+1}()") for i in range(5)]
    children = [Node(module="Sink",  func=f"c{i+1}()") for i in range(5)]
    for i, p in enumerate(parents):
        node.input_ports[id(p)]  = Port(signal=f"s{i+1}", ret=f"r{i+1}")
    for i, c in enumerate(children):
        node.output_ports[id(c)] = Port(signal=f"out{i+1}", ret=f"ret{i+1}")
    node.internal_wiring = (
        [f"s1:out{i+1}" for i in range(5)] +
        [f"ret{i+1}:r1" for i in range(5)]
    )
    node.children = children
    return node


def _fan_in_node(n_sources: int = 3) -> Node:
    """n_sources retX ports all converge to one r1 destination."""
    node = Node(module="M", func="f()")
    parent = Node(module="A", func="a()")
    node.input_ports[id(parent)] = Port(signal="s", ret="r1")
    children = [Node(module="B", func=f"c{i}()") for i in range(n_sources)]
    for i, c in enumerate(children):
        node.output_ports[id(c)] = Port(signal=f"out{i}", ret=f"ret{i}")
    node.internal_wiring = [f"ret{i}:r1" for i in range(n_sources)]
    node.children = children
    return node


def _explicit_output_handoff_node() -> Node:
    """Two-child chip with one explicit right-wall ret→signal handoff."""
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="receiverClassDecl_resolve()")
    c2 = Node(module="C", func="classMethod_find()")
    node = Node(module="M", func="callTargetFromConstruction_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret="constructedDecl")
    node.output_ports[(id(c1), 0)] = Port(signal="checker", ret="receiverDecl")
    node.output_ports[(id(c2), 0)] = Port(signal="classDecl", ret="constructedDecl")
    node.internal_wiring = [
        "checker:checker:pure",
        "receiverDecl:classDecl",
        "constructedDecl:constructedDecl:pure",
    ]
    node.children = [c1, c2]
    return node


def _same_name_crosswall_node(orientation: str) -> Node:
    """One label used for both signal and return on both walls."""
    parent = Node(module="App", func="main()")
    child = Node(module="C", func="child()")
    node = Node(module="M", func="ambiguous()")
    node.input_ports[(id(parent), 0)] = Port(signal="wire", ret="wire")
    node.output_ports[(id(child), 0)] = Port(signal="wire", ret="wire")
    node.internal_wiring = [f"wire:wire:{orientation}:pure"]
    node.children = [child]
    return node


def _same_name_right_wall_node(orientation: str) -> Node:
    """Return on one output pair feeds the next output signal with same label."""
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="child1()")
    c2 = Node(module="C", func="child2()")
    node = Node(module="M", func="sameName()")
    node.input_ports[(id(parent), 0)] = Port(signal="input", ret="done")
    node.output_ports[(id(c1), 0)] = Port(signal="first", ret="color")
    node.output_ports[(id(c2), 0)] = Port(signal="color", ret="done")
    node.internal_wiring = [f"color:color:{orientation}"]
    node.children = [c1, c2]
    return node


def _left_dense_explicit_node() -> Node:
    """Explicit-input manifold with left-side fanout and fanin density 2."""
    parent = Node(module="App", func="main()")
    c1 = Node(module="C", func="classDeclarationFromNewExpr_resolve()")
    c2 = Node(module="C", func="classDeclarationFromNewExpr_resolve_2()")
    node = Node(module="M", func="receiverClassDecl_resolve()")
    node.input_ports[(id(parent), 0)] = Port(signal="checker", ret="receiverDecl")
    node.output_ports[(id(c1), 0)] = Port(
        signal="checker_classDeclarationFromNewExpr_resolve",
        ret="receiverDecl",
    )
    node.output_ports[(id(c2), 0)] = Port(
        signal="checker_classDeclarationFromNewExpr_resolve_2",
        ret="classDecl",
    )
    node.internal_wiring = [
        "checker:checker_classDeclarationFromNewExpr_resolve:WE",
        "checker:checker_classDeclarationFromNewExpr_resolve_2:WE",
        "classDecl:receiverDecl:EW",
        "receiverDecl:receiverDecl:EW:pure",
    ]
    node.children = [c1, c2]
    return node


def _load_hub(spacing: int = 10) -> tuple[list[Node], Node]:
    """Load, configure, and lay out examples/hub.yaml."""
    path = Path(__file__).parent.parent / "examples" / "hub.yaml"
    with open(path) as fh:
        data = yaml.safe_load(fh)
    config.config_update(data.get("config", {}))
    if spacing != 10:
        config.portVerticalSpacing = spacing
    root  = Node.node_fromDict(data.get("tree", data))
    nodes = tree_flatten(root)
    cw    = channelWidth_compute(root)
    layout_compute(root, cw)
    return nodes, root


# ── ChipGeometry.ewOff ─────────────────────────────────────────────────────────

class TestEwOff:
    """Tests for the pre-layout E→W trunk-row count."""

    def test_no_wiring_returns_zero(self):
        """No internal wiring should require zero reserved E→W rows."""
        assert ChipGeometry.build_structural(_leaf()).ewOff == 0

    def test_no_output_ports_returns_zero(self):
        """A chip without outputs should never reserve E→W rows."""
        node = Node(module="M", func="f()")
        node.internal_wiring = ["s1:out1"]
        assert ChipGeometry.build_structural(node).ewOff == 0

    def test_straight_through_proxy_excluded(self):
        """r1:r1 — srcCounts==1 AND dstCounts==1 → excluded → ewOff == 0."""
        assert ChipGeometry.build_structural(_proxy_node()).ewOff == 0

    def test_fan_in_all_five_counted(self):
        """ret1..ret5 → r1; dstCounts['r1']==5 → none excluded → ewOff == 5."""
        assert ChipGeometry.build_structural(_hub_process_node()).ewOff == 5

    def test_fan_in_partial(self):
        """ret1..ret3 → r1; dstCounts['r1']==3 → ewOff == 3."""
        assert ChipGeometry.build_structural(_fan_in_node(3)).ewOff == 3

    def test_single_ew_pair_not_excluded_when_multi_dst(self):
        """Single retX → r1 where dstCounts['r1']==2 is NOT straight-through."""
        node = Node(module="M", func="f()")
        parent = Node(module="A", func="a()")
        c1 = Node(module="B", func="c1()")
        c2 = Node(module="C", func="c2()")
        node.input_ports[id(parent)]  = Port(signal="s", ret="r1")
        node.output_ports[id(c1)]     = Port(signal="out1", ret="ret1")
        node.output_ports[id(c2)]     = Port(signal="out2", ret="ret2")
        node.internal_wiring          = ["ret1:r1", "ret2:r1"]
        node.children                 = [c1, c2]
        assert ChipGeometry.build_structural(node).ewOff == 2

    def test_pass_through_disabled_counts_all_ew(self):
        """With passThroughAllowed=False, r1:r1 needs a trunk row → ewOff==1."""
        config.passThroughAllowed = False
        assert ChipGeometry.build_structural(_proxy_node()).ewOff == 1


# ── ChipGeometry.chipH ─────────────────────────────────────────────────────────

class TestChipH:
    """Tests for structural chip-height computation."""

    def test_leaf_is_base_height(self):
        """Leaf chips should use the 7-row minimum with a computation gap."""
        # Leaf chips need 7 rows for the computation gap (entry + gap + return).
        assert ChipGeometry.build_structural(_leaf()).chipH == 7

    def test_not_less_than_base_leaf(self):
        """Non-leaf chips should never shrink below the configured base height."""
        for node in [_proxy_node(), _hub_process_node(), _fan_in_node()]:
            assert ChipGeometry.build_structural(node).chipH >= config.baseLeafHeight

    def test_proxy_is_base_height(self):
        """All-straight-through chip height == baseLeafHeight."""
        assert (
            ChipGeometry.build_structural(_proxy_node()).chipH
            == config.baseLeafHeight
        )

    def test_chipH_fits_last_right_wall_return_row(self):
        """y0+3+ewOff+spacing*(n-1)+1  ≤  chipH-2  (interior max)."""
        node    = _hub_process_node()
        geo     = ChipGeometry.build_structural(node)
        spacing = config.portVerticalSpacing
        n       = len(node.output_ports)
        last_return_offset = 3 + geo.ewOff + spacing * (n - 1) + 1
        assert last_return_offset <= geo.chipH - 2, (
            f"last_return_offset={last_return_offset} > interiorMax={geo.chipH - 2}"
        )

    def test_chipH_includes_ew_in_formula(self):
        """chipH must cover at least 3 + ewOff + spacing*(n-1) + 2 rows."""
        node    = _hub_process_node()  # ewOff=5
        geo     = ChipGeometry.build_structural(node)
        spacing = config.portVerticalSpacing
        n       = max(1, len(node.output_ports))
        # Minimum: top border(1) + label(1) + separator(1) + ewOff rows +
        #          spacing*(n-1) + 1 (last signal row) + 1 (bottom border)
        min_h = 3 + geo.ewOff + spacing * (n - 1) + 2
        assert geo.chipH >= min_h, (
            f"chipH={geo.chipH} < minimum {min_h} (ewOff={geo.ewOff}, n={n})"
        )

    def test_chipH_from_hub_yaml(self):
        """After full layout, chipH still satisfies right-wall row invariant."""
        nodes, _ = _load_hub()
        for node in nodes:
            if not node.output_ports:
                continue
            ew      = node.geometry.ewOff
            n       = len(node.output_ports)
            pspac   = config.portVerticalSpacing if node.internal_wiring else 3
            last    = node.y + 3 + ew + pspac * (n - 1) + 1
            assert last <= node.y + node.chipH - 2, (
                f"{node.func}: last_return_row={last} "
                f"> interiorMax={node.y + node.chipH - 2}"
            )


# ── ChipGeometry.chipOw ────────────────────────────────────────────────────────

class TestChipOw:
    """Tests for structural chip-width computation."""

    def test_leaf_min_width(self):
        """Leaf width should be driven by the function label plus borders."""
        node = _leaf("f()")
        assert ChipGeometry.build_structural(node).chipOw == (
            len("f()") + config.chipPaddingX * 2 + 2
        )

    def test_straight_through_min_width(self):
        """All-straight chip: chipOw == labelW + 2 (no longitude columns)."""
        node = _proxy_node()
        label_w = len("p()") + config.chipPaddingX * 2
        assert ChipGeometry.build_structural(node).chipOw == label_w + 2

    def test_manifold_chip_wider_than_label(self):
        """A manifold chip should allocate more width than its title alone requires."""
        node = _hub_process_node()
        label_w = len("process()") + config.chipPaddingX * 2
        assert ChipGeometry.build_structural(node).chipOw > label_w + 2

    def test_manifold_width_formula(self):
        """chipOw uses visible internal-label widths plus all routing tracks."""
        node = _hub_process_node()
        ow   = ChipGeometry.build_structural(node).chipOw
        # s1 (len 2) and r1 (len 2) are left ports  → label "s1►" = 3
        # out1..out5 / ret1..ret5 are unit-density pass-through endpoints on the
        # right, so their internal labels are hidden and contribute width 0.
        max_ll = 3   # len("s1") + 1 (arrow)
        max_rl = 0
        # lCounts approx: s1→5, r1→5, out1..5→1 each, ret1..5→1 each
        # v_left  = s1(5) + r1(5) = 10
        # v_right = out1..5(1×5) + ret1..5(1×5) = 10
        min_ow = 12 + max_ll + max_rl + 2 * (10 + 10)
        assert ow >= min_ow


# ── Zone non-overlap (post layout) ───────────────────────────────────────────

class TestZoneNonOverlap:
    """Post-layout zone separation and interior-boundary checks."""

    def test_ew_zone_disjoint_from_wall_terminals(self):
        """E→W trunk rows [y0+3, y0+3+ewOff) must not overlap right-wall rows."""
        nodes, _ = _load_hub()
        spacing  = config.portVerticalSpacing
        for node in nodes:
            if not node.output_ports or not node.internal_wiring:
                continue
            ew  = node.geometry.ewOff
            if ew == 0:
                continue
            ew_zone = set(range(node.y + 3, node.y + 3 + ew))
            terminal_rows: set[int] = set()
            for i in range(len(node.output_ports)):
                terminal_rows.add(node.y + 3 + ew + spacing * i)      # signal
                terminal_rows.add(node.y + 3 + ew + spacing * i + 1)  # return
            overlap = ew_zone & terminal_rows
            assert not overlap, (
                f"{node.func}: E→W zone {sorted(ew_zone)} "
                f"overlaps terminal rows {sorted(overlap)}"
            )

    def test_right_wall_terminals_inside_chip_interior(self):
        """Every right-wall port row fits within [y0+3, y0+chipH-2]."""
        nodes, _ = _load_hub()
        for node in nodes:
            if not node.output_ports:
                continue
            ew           = node.geometry.ewOff
            pspac        = config.portVerticalSpacing if node.internal_wiring else 3
            interior_max = node.y + node.chipH - 2
            for i in range(len(node.output_ports)):
                ret_row = node.y + 3 + ew + pspac * i + 1
                assert ret_row <= interior_max, (
                    f"{node.func}: ret_row[{i}]={ret_row} "
                    f"> interiorMax={interior_max} "
                    f"(chipH={node.chipH}, ewOff={ew})"
                )

    def test_entry_rows_inside_chip_interior(self):
        """Every left-wall entryRow fits within (y0+2, y0+chipH-2]."""
        nodes, _ = _load_hub()
        for node in nodes:
            interior_max = node.y + node.chipH - 2
            for _pid, ey in node.entryRows.items():
                assert node.y + 2 < ey <= interior_max, (
                    f"{node.func}: entryRow={ey} "
                    f"outside (y0+2={node.y+2}, interiorMax={interior_max}]"
                )
            for _pid, ry in node.returnRows.items():
                assert node.y + 2 < ry <= interior_max, (
                    f"{node.func}: returnRow={ry} "
                    f"outside (y0+2={node.y+2}, interiorMax={interior_max}]"
                )


# ── Cross-site consistency ────────────────────────────────────────────────────

class TestConsistency:
    """Consistency checks between duplicated formulas across subsystems."""

    def test_wires_exit_formula_matches_chips_right_wall(self):
        """wires.py exitY formula must equal chips.py rightBaseRows formula.

        Both compute: node.y + 3 + node.geometry.ewOff + spacing * portIdx
        This test confirms they agree (and will fail if either drifts).
        """
        nodes, _ = _load_hub()
        spacing  = config.portVerticalSpacing
        for node in nodes:
            if not node.output_ports:
                continue
            ew    = node.geometry.ewOff
            pspac = spacing if node.internal_wiring else 3
            for idx in range(len(node.output_ports)):
                chips_row = node.y + 3 + ew + pspac * idx   # chips.py formula
                wires_row = node.y + 3 + ew + pspac * idx   # wires.py formula
                assert chips_row == wires_row, (
                    f"{node.func} port[{idx}]: chips={chips_row} wires={wires_row}"
                )

    def test_portSide_and_side_helper_agree(self):
        """ChipGeometry.port_side must agree with the chipOw computation.

        This test verifies chipOw is at least wide enough that portToX values
        fit — confirming that port-side classification is consistent throughout.

        Straight-through chips (chipOw == labelW + 2) have no longitude columns
        so the zone-overlap check does not apply to them.
        """
        nodes, _ = _load_hub()
        for node in nodes:
            if not node.internal_wiring:
                continue
            # Skip chips whose wiring is entirely straight-through (no manifold)
            label_w = len(node.func) + config.chipPaddingX * 2
            if node.ow <= label_w + 2:
                continue
            ow = node.ow
            rx = node.x + ow - 1
            # Every manifold port's longitude column must lie strictly inside rx
            # If chipOw underestimated (due to port-side divergence), the
            # portToX assignment in chips.py would overflow
            left_label  = max((len(n)+1 for port in node.input_ports.values()
                               for n in (port.signal, port.ret) if n), default=0)
            right_label = max((len(n)+1 for port in node.output_ports.values()
                               for n in (port.signal, port.ret) if n), default=0)
            min_inner_left  = node.x + 4 + left_label
            max_inner_right = rx     - 4 - right_label
            assert min_inner_left <= max_inner_right, (
                f"{node.func}: longitude zones overlap "
                f"(leftStart={min_inner_left} > rightStart={max_inner_right}, ow={ow})"
            )


# ── Phase 2: Stage-2 resolve() helpers ────────────────────────────────────────

def _geo_resolve(
    node: Node,
    y0: int,
    entryRows: dict,
    returnRows: dict,
) -> ChipGeometry:
    """Build Stage-1 geometry, attach to node, then resolve Stage 2."""
    geo = ChipGeometry.build_structural(node)
    node.geometry = geo
    node.x  = 0
    node.ow = geo.chipOw
    geo.resolve(node, y0, entryRows, returnRows)
    return geo


# ── TestWallRows ───────────────────────────────────────────────────────────────

class TestWallRows:
    """Tests for Stage-2 wall-row population."""

    def test_left_wall_rows_match_entry_rows(self):
        """leftWallRows[signal] and [ret] contain the entryRow/returnRow from layout."""
        nodes, _ = _load_hub()
        for node in nodes:
            if not node.geometry or not node.geometry.resolved:
                continue
            geo = node.geometry
            for pid, port in node.input_ports.items():
                if port.signal and pid in node.entryRows:
                    assert node.entryRows[pid] in geo.leftWallRows.get(
                        port.signal,
                        [],
                    ), (
                        f"{node.func}: entryRow {node.entryRows[pid]} "
                        "not in "
                        f"leftWallRows[{port.signal!r}]="
                        f"{geo.leftWallRows.get(port.signal)}"
                    )
                if port.ret and pid in node.returnRows:
                    assert node.returnRows[pid] in geo.leftWallRows.get(
                        port.ret,
                        [],
                    ), (
                        f"{node.func}: returnRow {node.returnRows[pid]} "
                        "not in "
                        f"leftWallRows[{port.ret!r}]={geo.leftWallRows.get(port.ret)}"
                    )

    def test_right_wall_rows_start_at_ew_offset(self):
        """First output port signal row == y0 + 3 + ewOff."""
        nodes, _ = _load_hub()
        for node in nodes:
            if not node.output_ports or not node.internal_wiring:
                continue
            geo = node.geometry
            assert geo and geo.resolved
            first_port = next(iter(node.output_ports.values()))
            if not first_port.signal:
                continue
            expected = node.y + 3 + geo.ewOff
            actual = geo.rightWallRows.get(first_port.signal, [None])[0]
            assert actual == expected, (
                f"{node.func}: rightWallRows[{first_port.signal!r}][0]={actual} "
                f"!= y0+3+ewOff={expected}"
            )

    def test_right_wall_rows_formula_matches_chips(self):
        """rightWallRows matches the formula chips.py uses for rightBaseRows."""
        nodes, _ = _load_hub()
        spacing = config.portVerticalSpacing
        for node in nodes:
            if not node.output_ports or not node.internal_wiring:
                continue
            geo = node.geometry
            assert geo and geo.resolved
            for i, port in enumerate(node.output_ports.values()):
                for name, offset in ((port.signal, 0), (port.ret, 1)):
                    if not name:
                        continue
                    expected = node.y + 3 + geo.ewOff + spacing * i + offset
                    rows = geo.rightWallRows.get(name, [])
                    assert expected in rows, (
                        f"{node.func} port[{i}] {name!r}: "
                        f"expected row {expected} in rightWallRows={rows}"
                    )

    def test_explicit_left_dense_manifold_lowers_west_terminal_pair(self):
        """Explicit-input manifold reserves left-wall headroom for fanout/fanin."""
        node = _left_dense_explicit_node()
        cw = channelWidth_compute(node)
        layout_compute(node, cw)

        pid = next(iter(node.input_ports))
        geo = node.geometry
        assert geo and geo.resolved

        assert node.entryRows[pid] == geo.anchorFloor + 2
        assert node.returnRows[pid] == node.entryRows[pid] + 1

        leftSignalAnchors = geo.allAnchorRows["L|sig|checker"]
        leftReturnAnchors = geo.allAnchorRows["L|ret|receiverDecl"]

        assert set(leftSignalAnchors).isdisjoint(leftReturnAnchors)
        assert min(leftSignalAnchors) >= geo.anchorFloor
        assert max(leftSignalAnchors) < node.returnRows[pid]


# ── TestStraightThrough ────────────────────────────────────────────────────────

class TestStraightThrough:
    """Tests for straight-through, wall-continuity, and manifold classification."""

    def test_proxy_node_all_straight(self):
        """All-straight proxy chip: all pairs in straightPairs, wiringPairs empty."""
        node = _proxy_node()
        pid  = next(iter(node.input_ports))
        geo  = _geo_resolve(node, y0=5,
                             entryRows={pid: 8}, returnRows={pid: 9})
        assert len(geo.wiringPairs) == 0, (
            f"Expected no wiringPairs, got {geo.wiringPairs}"
        )
        assert len(geo.straightPairs) == 2, (
            f"Expected 2 straightPairs, got {geo.straightPairs}"
        )

    def test_row_mismatch_sends_pair_to_manifold(self):
        """A pair with sRow != dRow is NOT straight-through, goes to wiringPairs."""
        node = _proxy_node()
        pid  = next(iter(node.input_ports))
        # Force entry rows to differ from rightWallRows (y0+3+0+3*0=8, +1=9)
        geo  = _geo_resolve(node, y0=5,
                             entryRows={pid: 15}, returnRows={pid: 16})
        # rightWallRows["s1"][0]=8, leftWallRows["s1"][0]=15 → sRow!=dRow → manifold
        assert len(geo.wiringPairs) > 0, (
            "Expected pairs in wiringPairs when rows are misaligned"
        )

    def test_manifold_chip_has_wiring_pairs(self):
        """Hub process() fan-in topology: all pairs go to wiringPairs (no straight)."""
        nodes, _ = _load_hub()
        for node in nodes:
            if node.func == "process()":
                geo = node.geometry
                assert geo and geo.resolved
                assert len(geo.wiringPairs) > 0, (
                    "process() should have manifold wiring pairs"
                )
                assert len(geo.straightPairs) == 0, (
                    "process() has no straight-through pairs"
                )
                return
        pytest.skip("process() not found in hub.yaml")

    def test_proxy_chips_in_hub_are_all_straight(self):
        """pX() proxy chips in hub.yaml have no manifold pairs."""
        nodes, _ = _load_hub()
        for node in nodes:
            if (
                node.func.startswith("p")
                and node.func.endswith("()")
                and node.func != "process()"
            ):
                geo = node.geometry
                assert geo and geo.resolved
                assert len(geo.wiringPairs) == 0, (
                    f"{node.func}: expected all-straight, "
                    f"got wiringPairs={geo.wiringPairs}"
                )

    def test_explicit_output_handoff_uses_wall_continuity(self):
        """Adjacent right-wall ret→signal handoff is not routed as manifold."""
        node = _explicit_output_handoff_node()
        pid = next(iter(node.input_ports))
        geo = _geo_resolve(node, y0=5, entryRows={pid: 8}, returnRows={pid: 9})

        assert ("receiverDecl", "classDecl") not in geo.wiringPairs
        assert ("checker", "checker") in geo.straightPairs
        assert ("constructedDecl", "constructedDecl") in geo.wiringPairs
        assert len(geo.wallContinuities) == 1

        continuity = geo.wallContinuities[0]
        assert continuity.src == "receiverDecl"
        assert continuity.dst == "classDecl"

    def test_explicit_same_name_crosswall_ew_disambiguates_return_pair(self):
        """EW forces a same-name pair to resolve as right-return -> left-return."""
        node = _same_name_crosswall_node("EW")
        pid = next(iter(node.input_ports))
        geo = _geo_resolve(node, y0=5, entryRows={pid: 8}, returnRows={pid: 9})

        assert ("wire", "wire") in geo.straightPairs
        directive = geo.straightDirectives[0]
        srcSide, dstSide, srcRow, dstRow = geo.directive_endpoints(directive)
        assert (srcSide, dstSide) == ("R", "L")
        assert (srcRow, dstRow) == (9, 9)

    def test_explicit_same_name_right_wall_ns_uses_wall_continuity(self):
        """NS disambiguates a same-name right-wall return->signal handoff."""
        node = _same_name_right_wall_node("NS")
        pid = next(iter(node.input_ports))
        geo = _geo_resolve(node, y0=5, entryRows={pid: 8}, returnRows={pid: 9})

        assert len(geo.wallContinuities) == 1
        continuity = geo.wallContinuities[0]
        assert continuity.side == "R"
        assert continuity.src == "color"
        assert continuity.dst == "color"
        assert continuity.srcRow < continuity.dstRow

    def test_explicit_same_name_right_wall_sn_raises(self):
        """SN should fail when the resolved same-name right-wall path runs top-down."""
        node = _same_name_right_wall_node("SN")
        pid = next(iter(node.input_ports))
        with pytest.raises(AssertionError, match="source row must be below"):
            _geo_resolve(node, y0=5, entryRows={pid: 8}, returnRows={pid: 9})


# ── TestAnchorRows ─────────────────────────────────────────────────────────────

class TestAnchorRows:
    """Tests for resolved anchor-row placement and counts."""

    def test_anchor_floor_respected(self):
        """All anchor rows >= anchorFloor = y0 + 3 + ewOff."""
        nodes, _ = _load_hub()
        for node in nodes:
            geo = node.geometry
            if not geo or not geo.resolved or not geo.allAnchorRows:
                continue
            for port, rows in geo.allAnchorRows.items():
                for row in rows:
                    assert row >= geo.anchorFloor, (
                        f"{node.func} port {port!r}: anchor row {row} "
                        f"< anchorFloor {geo.anchorFloor}"
                    )

    def test_interior_max_respected(self):
        """All anchor rows <= interiorMax = y0 + chipH - 2."""
        nodes, _ = _load_hub()
        for node in nodes:
            geo = node.geometry
            if not geo or not geo.resolved or not geo.allAnchorRows:
                continue
            for port, rows in geo.allAnchorRows.items():
                for row in rows:
                    assert row <= geo.interiorMax, (
                        f"{node.func} port {port!r}: anchor row {row} "
                        f"> interiorMax {geo.interiorMax}"
                    )

    def test_no_duplicate_anchor_rows(self):
        """Each port has no duplicate anchor rows."""
        nodes, _ = _load_hub()
        for node in nodes:
            geo = node.geometry
            if not geo or not geo.resolved:
                continue
            for port, rows in geo.allAnchorRows.items():
                assert len(set(rows)) == len(rows), (
                    f"{node.func} port {port!r}: duplicate anchor rows {rows}"
                )

    def test_anchor_count_matches_lcount(self):
        """len(allAnchorRows[port]) == lCounts[port] for every manifold port."""
        nodes, _ = _load_hub()
        for node in nodes:
            geo = node.geometry
            if not geo or not geo.resolved or not geo.lCounts:
                continue
            for port, cnt in geo.lCounts.items():
                actual = len(geo.allAnchorRows.get(port, []))
                assert actual == cnt, (
                    f"{node.func} port {port!r}: lCounts={cnt} "
                    f"but allAnchorRows has {actual} rows"
                )

    def test_unit_port_anchor_equals_wall_row(self):
        """unitPort anchor row == the port's wall row (no offset)."""
        nodes, _ = _load_hub()
        for node in nodes:
            geo = node.geometry
            if not geo or not geo.resolved or not geo.unitPorts:
                continue
            for port in geo.unitPorts:
                expected_wall = geo.wall_row(port)
                anchor_rows = geo.allAnchorRows.get(port, [])
                assert len(anchor_rows) == 1, (
                    f"{node.func} unitPort {port!r}: "
                    f"expected 1 anchor, got {anchor_rows}"
                )
                assert anchor_rows[0] == expected_wall, (
                    f"{node.func} unitPort {port!r}: anchor {anchor_rows[0]} "
                    f"!= wallRow {expected_wall}"
                )


# ── TestAnchorLabelWidth ───────────────────────────────────────────────────────

class TestAnchorLabelWidth:
    """config.anchorLabelMaxWidth caps the label width used in chipOw and resolve().

    Uses a fan-in topology (two child returns → one parent return port) because
    straight-through chips have no anchor labels and are unaffected by this setting.
    The fan-in creates dstCounts["long_return_channel"]==2, forcing manifold routing.
    """

    def _fan_in_long_names(self) -> Node:
        """Fan-in chip with two long child returns that merge on the left wall."""
        parent = Node(module="A", func="caller()")
        c1     = Node(module="B", func="c1()")
        c2     = Node(module="C", func="c2()")
        node   = Node(module="M", func="hub()")
        node.input_ports[(id(parent), 0)] = Port(
            signal="fwdSig",
            ret="long_return_channel",
        )
        node.output_ports[(id(c1), 0)] = Port(
            signal="out1",
            ret="longReturnFromFirst",
        )
        node.output_ports[(id(c2), 0)] = Port(
            signal="out2",
            ret="longReturnFromSecond",
        )
        # Both child returns fan into the same parent return port.
        node.internal_wiring = [
            "longReturnFromFirst:long_return_channel",
            "longReturnFromSecond:long_return_channel",
        ]
        node.children = [c1, c2]
        return node

    def test_unlimited_uses_full_label_width(self):
        """With anchorLabelMaxWidth=0, chipOw reflects the full port name lengths."""
        node = self._fan_in_long_names()
        geo = ChipGeometry.build_structural(node)
        # "long_return_channel" = 19 chars, so the anchor label width is 20.
        label_w = len("hub()") + config.chipPaddingX * 2
        assert geo.chipOw > label_w + 2, (
            f"Expected manifold chipOw > min ({label_w + 2}), got {geo.chipOw}"
        )

    def test_truncated_chipOw_is_narrower(self):
        """anchorLabelMaxWidth=6 produces a narrower chip than the unlimited case."""
        node = self._fan_in_long_names()
        ow_unlimited = ChipGeometry.build_structural(node).chipOw
        config.anchorLabelMaxWidth = 6
        ow_truncated = ChipGeometry.build_structural(node).chipOw
        assert ow_truncated < ow_unlimited, (
            f"Expected truncated ({ow_truncated}) < unlimited ({ow_unlimited})"
        )

    def test_truncated_chipOw_formula(self):
        """chipOw only reserves visible internal-label width, not hidden unit ports."""
        node = self._fan_in_long_names()
        config.anchorLabelMaxWidth = 6
        geo = ChipGeometry.build_structural(node)
        # left port: "long_return_channel" capped to "long_r" → label width = 7
        # right ports are unit-density with passThroughAllowed=True, so their
        # internal labels do not materialize and contribute width 0.
        # endpointCounts:
        #   L|ret|long_return_channel = 2
        #   R|ret|longReturnFromFirst = 1
        #   R|ret|longReturnFromSecond = 1
        # vLeft = 2, vRight = 1+1 = 2
        # manifoldMinOw = 12 + 7 + 0 + 2*(2+2) = 27
        assert geo.chipOw == 12 + 7 + 2 * (2 + 2)

    def test_hidden_internal_labels_drop_label_zone_width(self):
        """showInternalLabels=False removes all internal label-zone width."""
        node = self._fan_in_long_names()
        config.showInternalLabels = False
        geo = ChipGeometry.build_structural(node)
        assert geo.chipOw == 12 + 2 * (2 + 2)

    def test_aliased_internal_labels_use_fixed_small_width(self):
        """aliasInternalLabels=True uses fixed-width internal aliases for chipOw."""
        node = self._fan_in_long_names()
        config.aliasInternalLabels = True
        config.anchorLabelMaxWidth = 1
        geo = ChipGeometry.build_structural(node)
        assert geo.chipOw == 12 + 4 + 2 * (2 + 2)

    def test_anchor_label_rendered_truncated(self):
        """Full render: anchor text is truncated; external wire label is not."""
        from signalflow.engine.render import diagram_render
        d = {
            "module": "App",
            "func": "main()",
            "calls": [{
                "module": "Hub",
                "func": "hub()",
                "input_ports":  [{"signal": "fwdSig", "return": "long_return_channel"}],
                "output_ports": [
                    {"signal": "out1", "return": "longReturnFromFirst"},
                    {"signal": "out2", "return": "longReturnFromSecond"},
                ],
                "internal_wiring": [
                    "longReturnFromFirst:long_return_channel",
                    "longReturnFromSecond:long_return_channel",
                ],
                "calls": [
                    {
                        "module": "Sink",
                        "func": "c1()",
                        "input_ports": [
                            {
                                "signal": "out1",
                                "return": "longReturnFromFirst",
                            }
                        ],
                    },
                    {
                        "module": "Sink",
                        "func": "c2()",
                        "input_ports": [
                            {
                                "signal": "out2",
                                "return": "longReturnFromSecond",
                            }
                        ],
                    },
                ],
            }],
        }
        config.anchorLabelMaxWidth = 6
        lines = diagram_render("anchor test", d)
        combined = "\n".join(lines)
        # "long_r◄" (arrow immediately after the 6-char cap) is specific to the
        # truncated anchor label.  "long_return_channel◄" cannot contain "long_r◄"
        # as a substring because after "long_r" comes "eturn…" not "◄".
        assert "long_r◄" in combined, (
            "Truncated anchor 'long_r◄' must appear inside the chip"
        )
        # Full name still on external wire (rendered as label adjacent to wire arrow)
        assert "long_return_channel" in combined, (
            "Full name must still appear on the external return wire"
        )

    def test_anchor_label_rendered_aliased(self):
        """Aliased internal labels use compact per-side/role aliases."""
        from signalflow.engine.render import diagram_render

        d = {
            "module": "App",
            "func": "main()",
            "calls": [{
                "module": "Hub",
                "func": "hub()",
                "input_ports": [{"signal": "fwdSig", "return": "long_return_channel"}],
                "output_ports": [
                    {"signal": "out1", "return": "longReturnFromFirst"},
                    {"signal": "out2", "return": "longReturnFromSecond"},
                ],
                "internal_wiring": [
                    "longReturnFromFirst:long_return_channel",
                    "longReturnFromSecond:long_return_channel",
                ],
                "calls": [
                    {
                        "module": "Sink",
                        "func": "c1()",
                        "input_ports": [
                            {
                                "signal": "out1",
                                "return": "longReturnFromFirst",
                            }
                        ],
                    },
                    {
                        "module": "Sink",
                        "func": "c2()",
                        "input_ports": [
                            {
                                "signal": "out2",
                                "return": "longReturnFromSecond",
                            }
                        ],
                    },
                ],
            }],
        }
        config.aliasInternalLabels = True
        lines = diagram_render("anchor alias test", d)
        combined = "\n".join(lines)
        assert "o01◄" in combined

    def test_anchor_label_hidden_not_rendered(self):
        """Hidden internal labels do not appear inside the chip."""
        from signalflow.engine.render import diagram_render

        d = {
            "module": "App",
            "func": "main()",
            "calls": [{
                "module": "Hub",
                "func": "hub()",
                "input_ports": [{"signal": "fwdSig", "return": "long_return_channel"}],
                "output_ports": [
                    {"signal": "out1", "return": "longReturnFromFirst"},
                    {"signal": "out2", "return": "longReturnFromSecond"},
                ],
                "internal_wiring": [
                    "longReturnFromFirst:long_return_channel",
                    "longReturnFromSecond:long_return_channel",
                ],
                "calls": [
                    {
                        "module": "Sink",
                        "func": "c1()",
                        "input_ports": [
                            {
                                "signal": "out1",
                                "return": "longReturnFromFirst",
                            }
                        ],
                    },
                    {
                        "module": "Sink",
                        "func": "c2()",
                        "input_ports": [
                            {
                                "signal": "out2",
                                "return": "longReturnFromSecond",
                            }
                        ],
                    },
                ],
            }],
        }
        config.showInternalLabels = False
        lines = diagram_render("anchor hidden test", d)
        combined = "\n".join(lines)
        assert "long_r◄" not in combined
        assert "o01◄" not in combined
        assert "long_return_channel" in combined

    def test_per_chip_hide_override_beats_global_default(self):
        """A chip-local hide override wins over the document/global default."""
        node = self._fan_in_long_names()
        config.showInternalLabels = True
        node.showInternalLabelsOverride = False
        geo = ChipGeometry.build_structural(node)
        assert geo.showInternalLabels is False
        assert geo.chipOw == 12 + 2 * (2 + 2)

    def test_per_chip_alias_override_beats_global_default(self):
        """A chip-local alias override wins over the document/global default."""
        node = self._fan_in_long_names()
        config.aliasInternalLabels = False
        node.aliasInternalLabelsOverride = True
        geo = ChipGeometry.build_structural(node)
        assert geo.aliasInternalLabels is True
        assert geo.chipOw == 12 + 4 + 2 * (2 + 2)
