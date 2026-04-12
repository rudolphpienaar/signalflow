"""Tests for symbolic topology coupling edges (Phase G5).

Verifies that the WTE topology schema declares the correct directed
coupling invariants between extra-ring tokens:

- Ee drags NEe and SEe (east face drag)
- We drags NWe and SWe (west face drag)
- NEe stretches east face of Ne
- SEe stretches east face of Se
- NWe stretches west face of Ne
- SWe stretches west face of Se
- tokens outside the coupling graph have no targets
"""

from __future__ import annotations

import pytest

from signalflow.board.geometry.topology import (
    BoardTopologySchema,
    TopologyCouplingKind,
    TopologyFace,
    wteZoneBoardTopologySchema_build,
)
from signalflow.notation.sfn import sfN


@pytest.fixture
def schema() -> BoardTopologySchema:
    """Return the canonical WTE zone topology schema."""

    return wteZoneBoardTopologySchema_build()


# ---------------------------------------------------------------------------
# Drag coupling: face tokens drag corners
# ---------------------------------------------------------------------------


class TestDragCoupling:
    """Verify DRAG edges: face tokens rigidly drag their corner tokens."""

    def test_ee_drags_nee_and_see(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ee moving east drags NEe and SEe — both east corners."""

        targets = schema.dragTargets_get(sfN.Ee)
        assert sfN.NEe in targets
        assert sfN.SEe in targets

    def test_we_drags_nwe_and_swe(
        self, schema: BoardTopologySchema
    ) -> None:
        """We moving west drags NWe and SWe — both west corners."""

        targets = schema.dragTargets_get(sfN.We)
        assert sfN.NWe in targets
        assert sfN.SWe in targets

    def test_efe_has_no_drag_targets(
        self, schema: BoardTopologySchema
    ) -> None:
        """Efe is a fan token — no outgoing drag edges."""

        assert schema.dragTargets_get(sfN.Efe) == ()

    def test_ne_drags_corners(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ne moving north drags NWe and NEe (G6 vertical coupling)."""

        targets = schema.dragTargets_get(sfN.Ne)
        assert sfN.NWe in targets
        assert sfN.NEe in targets


# ---------------------------------------------------------------------------
# Stretch coupling: corners stretch cardinal bands
# ---------------------------------------------------------------------------


class TestStretchCoupling:
    """Verify STRETCH edges: corner tokens stretch cardinal band extents."""

    def test_nee_stretches_ne_east_face(
        self, schema: BoardTopologySchema
    ) -> None:
        """NEe stretches east face of Ne (also stretches north face of Ee)."""

        edges = schema.stretchEdges_get(sfN.NEe)
        dependents = {(e.dependent, e.dependentFace) for e in edges}
        assert (sfN.Ne, TopologyFace.EAST) in dependents
        assert all(e.kind is TopologyCouplingKind.STRETCH for e in edges)

    def test_see_stretches_se_east_face(
        self, schema: BoardTopologySchema
    ) -> None:
        """SEe stretches east face of Se (also stretches south face of Ee)."""

        edges = schema.stretchEdges_get(sfN.SEe)
        dependents = {(e.dependent, e.dependentFace) for e in edges}
        assert (sfN.Se, TopologyFace.EAST) in dependents

    def test_nwe_stretches_ne_west_face(
        self, schema: BoardTopologySchema
    ) -> None:
        """NWe stretches west face of Ne (also stretches north face of We)."""

        edges = schema.stretchEdges_get(sfN.NWe)
        dependents = {(e.dependent, e.dependentFace) for e in edges}
        assert (sfN.Ne, TopologyFace.WEST) in dependents

    def test_swe_stretches_se_west_face(
        self, schema: BoardTopologySchema
    ) -> None:
        """SWe stretches west face of Se (also stretches south face of We)."""

        edges = schema.stretchEdges_get(sfN.SWe)
        dependents = {(e.dependent, e.dependentFace) for e in edges}
        assert (sfN.Se, TopologyFace.WEST) in dependents

    def test_ee_has_no_stretch_edges(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ee has no outgoing stretch edges — it only drags corners."""

        assert schema.stretchEdges_get(sfN.Ee) == ()


# ---------------------------------------------------------------------------
# Ne has two stretch inputs
# ---------------------------------------------------------------------------


class TestNeStretchInputs:
    """Verify Ne receives stretch from both east and west corners."""

    def test_ne_east_extent_anchored_to_nee(
        self, schema: BoardTopologySchema
    ) -> None:
        """NEe is the east anchor for Ne; NWe is the west anchor."""

        eastEdges = schema.stretchEdges_get(sfN.NEe)
        westEdges = schema.stretchEdges_get(sfN.NWe)
        neEastTargets = [e for e in eastEdges if e.dependent is sfN.Ne]
        neWestTargets = [e for e in westEdges if e.dependent is sfN.Ne]
        assert len(neEastTargets) == 1
        assert len(neWestTargets) == 1
        assert neEastTargets[0].dependentFace is TopologyFace.EAST
        assert neWestTargets[0].dependentFace is TopologyFace.WEST


# ---------------------------------------------------------------------------
# Extra ring — vertical coupling (G6)
# ---------------------------------------------------------------------------


class TestExtraRingVerticalCoupling:
    """Verify Ne/Se drag corners and corners stretch Ee/We faces."""

    def test_ne_drags_nwe_and_nee(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ne moving north drags NWe and NEe."""

        targets = schema.dragTargets_get(sfN.Ne)
        assert sfN.NWe in targets
        assert sfN.NEe in targets

    def test_nee_stretches_ee_north_face(
        self, schema: BoardTopologySchema
    ) -> None:
        """NEe moving north stretches north face of Ee."""

        edges = schema.stretchEdges_get(sfN.NEe)
        eeNorthEdges = [
            e for e in edges
            if e.dependent is sfN.Ee
            and e.dependentFace is TopologyFace.NORTH
        ]
        assert len(eeNorthEdges) == 1

    def test_se_drags_see_and_swe(
        self, schema: BoardTopologySchema
    ) -> None:
        """Se moving south drags SEe and SWe."""

        targets = schema.dragTargets_get(sfN.Se)
        assert sfN.SEe in targets
        assert sfN.SWe in targets


# ---------------------------------------------------------------------------
# Intra ring coupling (G6)
# ---------------------------------------------------------------------------


class TestIntraRingCoupling:
    """Verify intra ring has same drag/stretch structure as extra ring."""

    def test_ei_drags_nei_and_sei(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ei moving east drags NEi and SEi."""

        targets = schema.dragTargets_get(sfN.Ei)
        assert sfN.NEi in targets
        assert sfN.SEi in targets

    def test_wi_drags_nwi_and_swi(
        self, schema: BoardTopologySchema
    ) -> None:
        """Wi moving west drags NWi and SWi."""

        targets = schema.dragTargets_get(sfN.Wi)
        assert sfN.NWi in targets
        assert sfN.SWi in targets

    def test_nei_stretches_ni_east_and_ei_north(
        self, schema: BoardTopologySchema
    ) -> None:
        """NEi stretches east face of Ni and north face of Ei."""

        edges = schema.stretchEdges_get(sfN.NEi)
        dependents = {(e.dependent, e.dependentFace) for e in edges}
        assert (sfN.Ni, TopologyFace.EAST) in dependents
        assert (sfN.Ei, TopologyFace.NORTH) in dependents

    def test_ni_drags_nwi_and_nei(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ni moving north drags NWi and NEi."""

        targets = schema.dragTargets_get(sfN.Ni)
        assert sfN.NWi in targets
        assert sfN.NEi in targets

    def test_intra_ring_total_edge_count(
        self, schema: BoardTopologySchema
    ) -> None:
        """Intra ring contributes 16 coupling edges (mirrors extra ring)."""

        intraAnchors = {
            sfN.Ei, sfN.Wi, sfN.Ni, sfN.Si,
            sfN.NEi, sfN.SEi, sfN.NWi, sfN.SWi,
        }
        intraEdges = [
            e for e in schema.couplingEdges
            if e.anchor in intraAnchors
        ]
        assert len(intraEdges) == 16


# ---------------------------------------------------------------------------
# Terminal-fan cluster coupling (Rule 3)
# ---------------------------------------------------------------------------


class TestTerminalFanCoupling:
    """Terminal tokens rigidly drag both adjacent fan tokens."""

    def test_et_drags_efe_and_efi(
        self, schema: BoardTopologySchema
    ) -> None:
        """Et drags Efe (extra-side fan) and Efi (intra-side fan)."""

        targets = schema.dragTargets_get(sfN.Et)
        assert sfN.Efe in targets
        assert sfN.Efi in targets

    def test_wt_drags_wfe_and_wfi(
        self, schema: BoardTopologySchema
    ) -> None:
        """Wt drags Wfe and Wfi."""

        targets = schema.dragTargets_get(sfN.Wt)
        assert sfN.Wfe in targets
        assert sfN.Wfi in targets

    def test_nt_drags_nfe_and_nfi(
        self, schema: BoardTopologySchema
    ) -> None:
        """Nt drags Nfe and Nfi."""

        targets = schema.dragTargets_get(sfN.Nt)
        assert sfN.Nfe in targets
        assert sfN.Nfi in targets

    def test_st_drags_sfe_and_sfi(
        self, schema: BoardTopologySchema
    ) -> None:
        """St drags Sfe and Sfi."""

        targets = schema.dragTargets_get(sfN.St)
        assert sfN.Sfe in targets
        assert sfN.Sfi in targets

    def test_terminal_fan_edge_count(
        self, schema: BoardTopologySchema
    ) -> None:
        """Four terminals × two fans each = 8 terminal-fan DRAG edges."""

        terminals = {sfN.Et, sfN.Wt, sfN.Nt, sfN.St}
        terminalEdges = [
            e for e in schema.couplingEdges
            if e.anchor in terminals
        ]
        assert len(terminalEdges) == 8

    def test_total_edge_count(
        self, schema: BoardTopologySchema
    ) -> None:
        """Total: 16 extra ring + 16 intra ring + 8 terminal-fan = 40."""

        assert len(schema.couplingEdges) == 40
