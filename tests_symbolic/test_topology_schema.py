"""Tests for the symbolic topology schema.

Verifies that the WTE zone topology schema answers the key Phase G1 questions:

- neighbor adjacency: what is west/east of a given region
- family membership: which family does a region belong to
- continuity group membership: which continuity groups contain a region
- ring neighbor traversal: clockwise and counter-clockwise ring neighbors
"""

from __future__ import annotations

import pytest

from signalflow.board.geometry.topology import (
    BoardTopologySchema,
    ContinuityGroup,
    TopologyFamily,
    wteZoneBoardTopologySchema_build,
)
from signalflow.notation.sfn import sfN

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def schema() -> BoardTopologySchema:
    """Return the canonical WTE zone topology schema."""

    return wteZoneBoardTopologySchema_build()


# ---------------------------------------------------------------------------
# Schema construction
# ---------------------------------------------------------------------------


class TestWteZoneBoardTopologySchemaConstruction:
    """Verify that the WTE topology schema is well-formed."""

    def test_schema_is_cached(self) -> None:
        """Repeated calls return the identical cached instance."""

        assert wteZoneBoardTopologySchema_build() is (
            wteZoneBoardTopologySchema_build()
        )

    def test_schema_orders_and_groups_populated(
        self, schema: BoardTopologySchema
    ) -> None:
        """Schema has non-empty horizontal order, vertical order,
        families, and continuity groups."""

        assert len(schema.horizontalOrder) > 0
        assert len(schema.verticalOrder) > 0
        assert len(schema.families) > 0
        assert len(schema.continuityGroups) > 0


# ---------------------------------------------------------------------------
# Horizontal adjacency: west/east neighbor queries
# ---------------------------------------------------------------------------


class TestHorizontalNeighborQueries:
    """Verify west/east neighbor resolution from horizontal order."""

    def test_neighbor_west_of_ee_is_efe(
        self, schema: BoardTopologySchema
    ) -> None:
        """West neighbor of Ee is Efe — primary G1 doctrinal query.

        Moving Ee east opens a gap relative to Efe; topology must name it.
        """

        assert schema.neighborWest_get(sfN.Ee) is sfN.Efe

    def test_horizontal_boundary_tokens_have_no_outer_neighbor(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ee has no east neighbor; We has no west neighbor."""

        assert schema.neighborEast_get(sfN.Ee) is None
        assert schema.neighborWest_get(sfN.We) is None

    def test_token_absent_from_horizontal_returns_none(
        self, schema: BoardTopologySchema
    ) -> None:
        """Token not in horizontal order returns None for both directions."""

        assert schema.neighborWest_get(sfN.NWe) is None
        assert schema.neighborEast_get(sfN.NWe) is None


# ---------------------------------------------------------------------------
# Vertical adjacency: north/south neighbor queries
# ---------------------------------------------------------------------------


class TestVerticalNeighborQueries:
    """Verify north/south neighbor resolution from vertical order."""

    def test_vertical_boundary_tokens_have_no_outer_neighbor(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ne has no north neighbor; Se has no south neighbor."""

        assert schema.neighborNorth_get(sfN.Ne) is None
        assert schema.neighborSouth_get(sfN.Se) is None

    def test_neighbor_south_of_ne_is_nfe(
        self, schema: BoardTopologySchema
    ) -> None:
        """South neighbor of Ne (north extra lat) is Nfe (north fan extra)."""

        assert schema.neighborSouth_get(sfN.Ne) is sfN.Nfe


# ---------------------------------------------------------------------------
# Family membership queries
# ---------------------------------------------------------------------------


class TestFamilyMembershipQueries:
    """Verify topology family membership queries."""

    def test_extra_ring_family_contains_all_ring_members(
        self, schema: BoardTopologySchema
    ) -> None:
        """Extra ring family includes cardinal members and all four corners."""

        members = schema.familyMembers_get("extra_ring")
        for token in (sfN.Ee, sfN.We, sfN.Ne, sfN.Se,
                      sfN.NWe, sfN.NEe, sfN.SEe, sfN.SWe):
            assert token in members, (
                f"Extra ring missing {token.name}"
            )

    def test_family_members_unknown_returns_empty(
        self, schema: BoardTopologySchema
    ) -> None:
        """Unknown family name returns empty tuple."""

        assert schema.familyMembers_get("does_not_exist") == ()

    def test_region_families_ee_multi_membership(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ee belongs to both extra_ring and east_extra families."""

        famNames = {fam.name for fam in schema.regionFamilies_get(sfN.Ee)}
        assert "extra_ring" in famNames
        assert "east_extra" in famNames

    def test_region_families_et_chip_terminal(
        self, schema: BoardTopologySchema
    ) -> None:
        """Et belongs to the chip_terminal family."""

        famNames = {fam.name for fam in schema.regionFamilies_get(sfN.Et)}
        assert "chip_terminal" in famNames

    def test_topology_family_member_is_check(self) -> None:
        """TopologyFamily.member_isCheck returns correct results."""

        fam = TopologyFamily(name="test", members=(sfN.Ee, sfN.We))
        assert fam.member_isCheck(sfN.Ee) is True
        assert fam.member_isCheck(sfN.Ne) is False


# ---------------------------------------------------------------------------
# Continuity group queries
# ---------------------------------------------------------------------------


class TestContinuityGroupQueries:
    """Verify continuity group membership and ring traversal queries."""

    def test_ee_in_extra_ring_continuity_group(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ee belongs to the extra_ring continuity group."""

        assert schema.regionInContinuityGroup_isCheck(sfN.Ee, "extra_ring")

    def test_efe_not_in_extra_ring_continuity_group(
        self, schema: BoardTopologySchema
    ) -> None:
        """Efe (fan extra) not in the extra_ring continuity group."""

        assert not schema.regionInContinuityGroup_isCheck(
            sfN.Efe, "extra_ring"
        )

    def test_continuity_group_extra_ring_is_ring(
        self, schema: BoardTopologySchema
    ) -> None:
        """The extra_ring continuity group is declared as a closed ring."""

        cg = schema.continuityGroup_get("extra_ring")
        assert cg is not None
        assert cg.isRing is True

    def test_continuity_group_unknown_returns_none(
        self, schema: BoardTopologySchema
    ) -> None:
        """Unknown continuity group name returns None."""

        assert schema.continuityGroup_get("does_not_exist") is None

    def test_region_continuity_groups_wi_intra_ring(
        self, schema: BoardTopologySchema
    ) -> None:
        """Wi belongs to the intra_ring continuity group."""

        groupNames = {
            cg.name for cg in schema.regionContinuityGroups_get(sfN.Wi)
        }
        assert "intra_ring" in groupNames


# ---------------------------------------------------------------------------
# Ring neighbor traversal
# ---------------------------------------------------------------------------


class TestRingNeighborTraversal:
    """Verify clockwise and counter-clockwise ring neighbor queries."""

    def test_extra_ring_cw_neighbor_of_ee_is_se(
        self, schema: BoardTopologySchema
    ) -> None:
        """Clockwise ring neighbor of Ee in extra_ring is Se."""

        cg = schema.continuityGroup_get("extra_ring")
        assert cg is not None
        assert cg.ringNeighborCW_get(sfN.Ee) is sfN.Se

    def test_extra_ring_ccw_neighbor_of_ee_is_ne(
        self, schema: BoardTopologySchema
    ) -> None:
        """Counter-clockwise ring neighbor of Ee in extra_ring is Ne."""

        cg = schema.continuityGroup_get("extra_ring")
        assert cg is not None
        assert cg.ringNeighborCCW_get(sfN.Ee) is sfN.Ne

    def test_extra_ring_cw_full_traversal_returns_to_start(
        self, schema: BoardTopologySchema
    ) -> None:
        """Full clockwise traversal of extra_ring returns to starting token."""

        cg = schema.continuityGroup_get("extra_ring")
        assert cg is not None
        startToken = sfN.We
        currentToken: sfN = startToken
        for _ in range(len(cg.members)):
            nextToken = cg.ringNeighborCW_get(currentToken)
            assert nextToken is not None
            currentToken = nextToken
        assert currentToken is startToken

    def test_ring_neighbor_non_member_returns_none(self) -> None:
        """Ring neighbor query for a non-member token returns None."""

        cg = ContinuityGroup(
            name="test_ring",
            members=(sfN.We, sfN.Ne, sfN.Ee, sfN.Se),
            isRing=True,
        )
        assert cg.ringNeighborCW_get(sfN.NWe) is None
        assert cg.ringNeighborCCW_get(sfN.NWe) is None

    def test_ring_neighbor_on_non_ring_group_returns_none(self) -> None:
        """Ring neighbor query on a non-ring group returns None."""

        cg = ContinuityGroup(
            name="test_sequence",
            members=(sfN.We, sfN.Ne, sfN.Ee),
            isRing=False,
        )
        assert cg.ringNeighborCW_get(sfN.We) is None
        assert cg.ringNeighborCCW_get(sfN.We) is None
