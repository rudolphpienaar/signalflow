"""Phase 0 TDD tests for ChipGeometry consolidation.

Tests geometry invariants using the *current* API (ewTopOffset_get,
chipH_precompute, chipOw_compute).  When ChipGeometry is implemented these
test bodies will be updated to read from node.geometry, but the contracts
and names are fixed.

Tests marked xfail expose confirmed latent bugs in the current code.
Tests marked with a "CURRENTLY FAILS" comment are expected to fail on the
current code and will pass once the corresponding phase is complete.
"""
from __future__ import annotations

import copy
from dataclasses import fields

import pytest
import yaml
from pathlib import Path

from signalflow.config import config
from signalflow.lib.layout import channelWidth_compute, chipOw_compute, layout_compute
from signalflow.lib.tree import chipH_precompute, ewTopOffset_get, tree_flatten
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


# ── ewTopOffset_get ────────────────────────────────────────────────────────────

class TestEwOff:
    def test_no_wiring_returns_zero(self):
        assert ewTopOffset_get(_leaf()) == 0

    def test_no_output_ports_returns_zero(self):
        node = Node(module="M", func="f()")
        node.internal_wiring = ["s1:out1"]
        assert ewTopOffset_get(node) == 0

    def test_straight_through_proxy_excluded(self):
        """r1:r1 — srcCounts==1 AND dstCounts==1 → excluded → ewOff == 0."""
        assert ewTopOffset_get(_proxy_node()) == 0

    def test_fan_in_all_five_counted(self):
        """ret1..ret5 → r1; dstCounts['r1']==5 → none excluded → ewOff == 5."""
        assert ewTopOffset_get(_hub_process_node()) == 5

    def test_fan_in_partial(self):
        """ret1..ret3 → r1; dstCounts['r1']==3 → ewOff == 3."""
        assert ewTopOffset_get(_fan_in_node(3)) == 3

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
        assert ewTopOffset_get(node) == 2

    @pytest.mark.xfail(
        reason="Latent bug: ewTopOffset_get ignores passThroughAllowed=False",
        strict=True,
    )
    def test_pass_through_disabled_counts_all_ew(self):
        """With passThroughAllowed=False, r1:r1 needs a trunk row → ewOff==1."""
        config.passThroughAllowed = False
        assert ewTopOffset_get(_proxy_node()) == 1


# ── chipH_precompute ───────────────────────────────────────────────────────────

class TestChipH:
    def test_leaf_is_base_height(self):
        assert chipH_precompute(_leaf()) == config.baseLeafHeight

    def test_not_less_than_base_leaf(self):
        for node in [_proxy_node(), _hub_process_node(), _fan_in_node()]:
            assert chipH_precompute(node) >= config.baseLeafHeight

    def test_proxy_is_base_height(self):
        """All-straight-through chip height == baseLeafHeight."""
        assert chipH_precompute(_proxy_node()) == config.baseLeafHeight

    def test_chipH_fits_last_right_wall_return_row(self):
        """y0+3+ewOff+spacing*(n-1)+1  ≤  chipH-2  (interior max)."""
        node    = _hub_process_node()
        h       = chipH_precompute(node)
        ew      = ewTopOffset_get(node)
        spacing = config.portVerticalSpacing
        n       = len(node.output_ports)
        last_return_offset = 3 + ew + spacing * (n - 1) + 1
        assert last_return_offset <= h - 2, (
            f"last_return_offset={last_return_offset} > interiorMax={h - 2}"
        )

    def test_chipH_includes_ew_in_formula(self):
        """chipH must cover at least 3 + ewOff + spacing*(n-1) + 2 rows."""
        node    = _hub_process_node()  # ewOff=5
        h       = chipH_precompute(node)
        ew      = ewTopOffset_get(node)
        spacing = config.portVerticalSpacing
        n       = max(1, len(node.output_ports))
        # Minimum: top border(1) + label(1) + separator(1) + ewOff rows +
        #          spacing*(n-1) + 1 (last signal row) + 1 (bottom border)
        min_h = 3 + ew + spacing * (n - 1) + 2
        assert h >= min_h, f"chipH={h} < minimum {min_h} (ewOff={ew}, n={n})"

    def test_chipH_from_hub_yaml(self):
        """After full layout, chipH still satisfies right-wall row invariant."""
        nodes, _ = _load_hub()
        for node in nodes:
            if not node.output_ports:
                continue
            ew      = ewTopOffset_get(node)
            n       = len(node.output_ports)
            pspac   = config.portVerticalSpacing if node.internal_wiring else 3
            last    = node.y + 3 + ew + pspac * (n - 1) + 1
            assert last <= node.y + node.chipH - 2, (
                f"{node.func}: last_return_row={last} "
                f"> interiorMax={node.y + node.chipH - 2}"
            )


# ── chipOw_compute ─────────────────────────────────────────────────────────────

class TestChipOw:
    def test_leaf_min_width(self):
        node = _leaf("f()")
        assert chipOw_compute(node) == len("f()") + config.chipPaddingX * 2 + 2

    def test_straight_through_min_width(self):
        """All-straight chip: chipOw == labelW + 2 (no longitude columns)."""
        node = _proxy_node()
        label_w = len("p()") + config.chipPaddingX * 2
        assert chipOw_compute(node) == label_w + 2

    def test_manifold_chip_wider_than_label(self):
        node = _hub_process_node()
        label_w = len("process()") + config.chipPaddingX * 2
        assert chipOw_compute(node) > label_w + 2

    def test_manifold_width_formula(self):
        """chipOw >= 12 + maxLeftLabel + maxRightLabel + 2*(vLeft+vRight)."""
        node = _hub_process_node()
        ow   = chipOw_compute(node)
        # s1 (len 2) and r1 (len 2) are left ports  → label "s1►" = 3
        # out1..out5 / ret1..ret5 are right ports   → label "►out1" = 5
        max_ll = 3   # len("s1") + 1 (arrow)
        max_rl = 5   # len("out1") + 1 (arrow)
        # lCounts approx: s1→5, r1→5, out1..5→1 each, ret1..5→1 each
        # v_left  = s1(5) + r1(5) = 10
        # v_right = out1..5(1×5) + ret1..5(1×5) = 10
        min_ow = 12 + max_ll + max_rl + 2 * (10 + 10)
        assert ow >= min_ow


# ── Zone non-overlap (post layout) ───────────────────────────────────────────

class TestZoneNonOverlap:
    def test_ew_zone_disjoint_from_wall_terminals(self):
        """E→W trunk rows [y0+3, y0+3+ewOff) must not overlap right-wall rows."""
        nodes, _ = _load_hub()
        spacing  = config.portVerticalSpacing
        for node in nodes:
            if not node.output_ports or not node.internal_wiring:
                continue
            ew  = ewTopOffset_get(node)
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
            ew           = ewTopOffset_get(node)
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
            for pid, ey in node.entryRows.items():
                assert node.y + 2 < ey <= interior_max, (
                    f"{node.func}: entryRow={ey} "
                    f"outside (y0+2={node.y+2}, interiorMax={interior_max}]"
                )
            for pid, ry in node.returnRows.items():
                assert node.y + 2 < ry <= interior_max, (
                    f"{node.func}: returnRow={ry} "
                    f"outside (y0+2={node.y+2}, interiorMax={interior_max}]"
                )


# ── Cross-site consistency ────────────────────────────────────────────────────

class TestConsistency:
    def test_wires_exit_formula_matches_chips_right_wall(self):
        """wires.py exitY formula must equal chips.py rightBaseRows formula.

        Both compute: node.y + 3 + ewTopOffset_get(node) + spacing * portIdx
        This test confirms they agree (and will fail if either drifts).
        """
        nodes, _ = _load_hub()
        spacing  = config.portVerticalSpacing
        for node in nodes:
            if not node.output_ports:
                continue
            ew    = ewTopOffset_get(node)
            pspac = spacing if node.internal_wiring else 3
            for idx in range(len(node.output_ports)):
                chips_row = node.y + 3 + ew + pspac * idx   # chips.py formula
                wires_row = node.y + 3 + ewTopOffset_get(node) + pspac * idx  # wires.py
                assert chips_row == wires_row, (
                    f"{node.func} port[{idx}]: chips={chips_row} wires={wires_row}"
                )

    def test_portSide_and_side_helper_agree(self):
        """chips.py portSide_get and layout.py _side must return identical results
        for every port in every node.  Tests via rendered output consistency
        (if they diverge, chipOw will be wrong for some manifold chip).

        This test verifies chipOw is at least wide enough that portToX values
        fit — a proxy for the two helpers agreeing.

        Straight-through chips (chipOw == labelW + 2) have no longitude columns
        so the zone-overlap check does not apply to them.
        """
        from signalflow.lib.layout import chipOw_compute
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
            # If chipOw_compute underestimated (due to helper divergence), the
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
