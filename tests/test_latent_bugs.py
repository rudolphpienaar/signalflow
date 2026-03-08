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

    @pytest.mark.xfail(
        reason="Bug §1.12: ewOff ignores passThroughAllowed=False",
        strict=True,
    )
    def test_proxy_ewoff_is_one_when_pass_through_disabled(self):
        config.passThroughAllowed = False
        node = _proxy_node()
        ewOff = ChipGeometry.build_structural(node).ewOff
        assert ewOff == 1, (
            f"Expected ewOff=1 with passThroughAllowed=False, got {ewOff}"
        )

    @pytest.mark.xfail(
        reason="Bug §1.12: chipH underestimates because ewOff is wrong (0 instead of 1)",
        strict=True,
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


# ── §1.13 list.index() repeated-child misbinding ────────────────────────────

class TestRepeatedChildPortBinding:
    """Bug §1.13 — fixed in Phase 6d.

    node_fromDict uses list.index(cDict) which returns the FIRST occurrence.
    If a parent calls the same child twice, both calls get childIdx=0 and
    bind to the same output port.  The second call is silently mis-wired.
    """

    @pytest.mark.xfail(
        reason="Bug §1.13: list.index() binds repeated children to same port",
        strict=True,
    )
    def test_repeated_child_gets_distinct_output_ports(self):
        """A parent that calls the same child twice must get two distinct ports."""
        tree_dict = {
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
        root = Node.node_fromDict(tree_dict)
        # root.output_ports should have two distinct Port objects, one per call
        assert len(root.output_ports) == 2, (
            f"Expected 2 output ports (one per call), got {len(root.output_ports)}"
        )
        port_signals = [p.signal for p in root.output_ports.values()]
        assert "s1" in port_signals and "s2" in port_signals, (
            f"Expected both s1 and s2, got {port_signals}"
        )


# ── §1.11 vline flow dead code (documentation) ───────────────────────────────

class TestVlineFlowConfirmedDead:
    """Bug §1.11 — confirmed dead code, removed in Phase 6c.

    This is NOT xfail — it documents that the bug IS present and tests that
    the dead-code property holds (both branches identical).  The test in
    test_invariants.py:TestVlineFlowDeadCode confirms the same thing.

    When Phase 6c removes the flow parameter, this test should be deleted.
    """

    def test_flow_parameter_has_no_effect(self):
        """Confirm flow='up' and flow='down' produce byte-identical output."""
        from signalflow.models.canvas import Canvas
        c1 = Canvas(rows=15, cols=5)
        c2 = Canvas(rows=15, cols=5)
        c1.modeMerge = True
        c2.modeMerge = True
        c1.vline(2, 2, 12, flow="down")
        c2.vline(2, 2, 12, flow="up")
        mismatches = [
            (y, c1.get(2, y), c2.get(2, y))
            for y in range(2, 12)
            if c1.get(2, y) != c2.get(2, y)
        ]
        assert not mismatches, (
            f"flow= parameter has effect at rows: {mismatches} — "
            "branches are NOT identical (unexpected)"
        )
