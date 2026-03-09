"""Phase 0 TDD: tests that expose confirmed latent bugs.

All tests in this file are currently expected to fail (xfail) because they
test behaviour that is broken in the current code.  They will pass once the
corresponding fix phase is complete, at which point the xfail markers should
be removed and the tests become regression guards.

Each test documents:
  - The bug reference (§1.x in PLAN.md)
  - Which phase fixes it
  - The exact failure mode
"""
from __future__ import annotations

from dataclasses import fields

import pytest

from signalflow.config import config
from signalflow.engine.render import diagram_render
from signalflow.lib.layout import channelWidth_compute, layout_compute
from signalflow.lib.tree import tree_flatten
from signalflow.models.chip_geometry import ChipGeometry
from signalflow.models.node import Node, Port


# ── config fixture ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    saved = {f.name: getattr(config, f.name) for f in fields(config)}
    yield
    for name, val in saved.items():
        setattr(config, name, val)


# ── helpers ───────────────────────────────────────────────────────────────────

def _proxy_node(sig: str = "s1", ret: str = "r1") -> Node:
    parent = Node(module="App", func="main()")
    hub    = Node(module="Hub", func="process()")
    node   = Node(module="Proxy", func="p()")
    node.input_ports[id(parent)]  = Port(signal=sig, ret=ret)
    node.output_ports[id(hub)]    = Port(signal=sig, ret=ret)
    node.internal_wiring          = [f"{sig}:{sig}", f"{ret}:{ret}"]
    node.children                 = [hub]
    return node


# ── §1.12 passThroughAllowed=False ────────────────────────────────────────────

class TestPassThroughDisabled:
    """Bug §1.12 — fixed in Phase 6a.

    When passThroughAllowed=False, chips.py routes ALL pairs through the
    manifold (no unit-port bypass).  Therefore a proxy chip with r1:r1 needs
    one E→W trunk row — ewOff should be 1.  But ChipGeometry._ewOff_compute
    currently applies the srcCounts==1 AND dstCounts==1 exclusion regardless
    of the flag, returning 0 instead of 1.
    """

    def test_proxy_ewoff_is_one_when_pass_through_disabled(self):
        config.passThroughAllowed = False
        node = _proxy_node()
        ewOff = ChipGeometry.build_structural(node).ewOff
        assert ewOff == 1, (
            f"Expected ewOff=1 with passThroughAllowed=False, got {ewOff}"
        )

    def test_proxy_chipH_fits_rows_when_pass_through_disabled(self):
        """With passThroughAllowed=False, ewOff=1 so chipH must be >= 7.

        The anchor stack for r1 occupies rows y0+4 and y0+5 (signal+return).
        interiorMax = y0 + chipH - 2.  For both to fit, chipH >= 7.
        Currently ewOff returns 0 (bug §1.12), so chipH stays at 6
        (baseLeafHeight), and the assertion below correctly fails.
        """
        config.passThroughAllowed = False
        node = _proxy_node()
        geo = ChipGeometry.build_structural(node)
        # When ewOff is correctly 1: last anchor row offset = 3+1+0+1 = 5,
        # interiorMax offset = chipH-2 = 5 → chipH must be >= 7.
        assert geo.chipH >= 7, (
            f"chipH={geo.chipH} < 7: too small to fit anchor rows when ewOff=1 "
            f"(current ewOff={geo.ewOff}, should be 1)"
        )


# ── §1.8 inputExplicit three-valued logic ────────────────────────────────────

class TestInputExplicitResolution:
    """Bug §1.8 — fixed in Phase 1 (isInputExplicit property added to Node).

    Node.inputExplicit can be None (meaning "defer to config").  The property
    `isInputExplicit` resolves None → config.chipIoInputExplicit.
    """

    def test_none_defers_to_config_false(self):
        """Node with inputExplicit=None and global config False → isInputExplicit=False."""
        config.chipIoInputExplicit = False
        node = Node(module="M", func="f()")
        assert node.inputExplicit is None
        assert node.isInputExplicit is False

    def test_none_defers_to_config_true(self):
        config.chipIoInputExplicit = True
        node = Node(module="M", func="f()")
        assert node.isInputExplicit is True

    def test_explicit_true_overrides_config_false(self):
        config.chipIoInputExplicit = False
        node = Node(module="M", func="f()")
        node.inputExplicit = True
        assert node.isInputExplicit is True

    def test_explicit_false_overrides_config_true(self):
        config.chipIoInputExplicit = True
        node = Node(module="M", func="f()")
        node.inputExplicit = False
        assert node.isInputExplicit is False


# ── §1.13 repeated-child port binding ────────────────────────────────────────

def _repeated_child_dict() -> dict:
    """YAML-equivalent dict: main() calls work() twice with distinct port labels."""
    return {
        "module": "App",
        "func": "main()",
        "output_ports": [
            {"signal": "s1", "return": "r1"},
            {"signal": "s2", "return": "r2"},
        ],
        "calls": [
            {
                "module": "Worker",
                "func": "work()",
                "input_ports": [{"signal": "s1", "return": "r1"}],
            },
            {
                "module": "Worker",
                "func": "work()",
                "input_ports": [{"signal": "s2", "return": "r2"}],
            },
        ],
    }


class TestRepeatedChildPortBinding:
    """Bug §1.13 — root cause: output_ports and input_ports keyed by id(node).

    When a parent calls the same child function twice, both calls return the
    identical Node object from the registry.  id(child) is therefore the same
    for both calls and the second write into output_ports[id(child)] silently
    overwrites the first.  The same collision occurs in child.input_ports and
    in child.entryRows / child.returnRows.

    Fix (§1.13 plan): change port-dict key type from int to PortKey =
    tuple[int, int] = (id(node), call_index), so each call occurrence gets
    a unique slot.  Tracked in PLAN.md.
    """

    def test_repeated_child_gets_distinct_output_ports(self):
        """Parent that calls the same child twice must have two output port slots."""
        root = Node.node_fromDict(_repeated_child_dict())
        assert len(root.output_ports) == 2, (
            f"Expected 2 output ports (one per call), got {len(root.output_ports)}"
        )
        signals = [p.signal for p in root.output_ports.values()]
        assert "s1" in signals and "s2" in signals, (
            f"Expected both s1 and s2, got {signals}"
        )

    def test_repeated_child_gets_distinct_input_ports(self):
        """The canonical work() node must have two input port slots — one per call."""
        root = Node.node_fromDict(_repeated_child_dict())
        nodes = tree_flatten(root)
        work = next(n for n in nodes if n.func == "work()")
        assert len(work.input_ports) == 2, (
            f"Expected 2 input ports on work(), got {len(work.input_ports)}"
        )
        signals = [p.signal for p in work.input_ports.values()]
        assert "s1" in signals and "s2" in signals, (
            f"Expected both s1 and s2, got {signals}"
        )

    def test_parent_call_sequence_has_two_entries(self):
        """root.call_sequence must record both calls in YAML order."""
        root = Node.node_fromDict(_repeated_child_dict())
        assert len(root.call_sequence) == 2, (
            f"Expected 2 entries in call_sequence, got {len(root.call_sequence)}"
        )
        children_in_seq = [child for child, *_ in root.call_sequence]
        work = children_in_seq[0]
        assert children_in_seq[0] is children_in_seq[1], (
            "Both entries must reference the same canonical Node"
        )
        assert work.func == "work()"

    def test_repeated_child_has_distinct_entry_rows(self):
        """After layout, work() must have two distinct entryRows — one per call."""
        config.chipIoInputExplicit = True
        root = Node.node_fromDict(_repeated_child_dict())
        cw = channelWidth_compute(root)
        layout_compute(root, cw)
        nodes = tree_flatten(root)
        work = next(n for n in nodes if n.func == "work()")
        assert len(work.entryRows) == 2, (
            f"Expected 2 entryRows on work(), got {work.entryRows}"
        )
        rows = list(work.entryRows.values())
        assert rows[0] != rows[1], (
            f"entryRows must be distinct; both are {rows[0]}"
        )

    def test_repeated_child_render_shows_both_signals(self):
        """Full render must contain both signal labels s1 and s2."""
        lines = diagram_render("§1.13 test", _repeated_child_dict())
        combined = "\n".join(lines)
        assert "s1" in combined and "s2" in combined, (
            "Both signal labels must appear in the rendered output"
        )


# ── §1.11 vline flow dead code (documentation) ───────────────────────────────
