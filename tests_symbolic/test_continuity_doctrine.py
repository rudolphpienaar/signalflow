"""Tests for topology-backed continuity doctrine.

Verifies Phase G3 acceptance criteria:

- CONTINUITY operator exists in GeometryCouplingOp
- extra-ring continuity family is expressible as a symbolic rule bank
- Ee is obligated (in the extra ring)
- Efe is not obligated (fan, not in the ring)
- all eight extra-ring members produce expressions
- ring-neighbor traversal is consistent with continuity membership
"""

from __future__ import annotations

import pytest

from signalflow.board.geometry.continuity import (
    TopologyContinuityFamily,
    extraRingContinuityFamily_build,
)
from signalflow.board.geometry.coupling import GeometryCouplingOp
from signalflow.board.geometry.topology import (
    BoardTopologySchema,
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


@pytest.fixture
def extraRingFamily(schema: BoardTopologySchema) -> TopologyContinuityFamily:
    """Return the extra-ring continuity family."""

    return extraRingContinuityFamily_build(schema)


# ---------------------------------------------------------------------------
# Operator definition
# ---------------------------------------------------------------------------


class TestContinuityOperator:
    """Verify the CONTINUITY operator is declared in GeometryCouplingOp."""

    def test_continuity_op_value_and_distinct(self) -> None:
        """CONTINUITY has canonical ~~ token and is distinct from others."""

        assert GeometryCouplingOp.CONTINUITY.value == "~~"
        others = {
            GeometryCouplingOp.PROPAGATES_DRAG,
            GeometryCouplingOp.PROPAGATES_DISPLACE,
            GeometryCouplingOp.CONTAINS,
        }
        assert GeometryCouplingOp.CONTINUITY not in others


# ---------------------------------------------------------------------------
# Family construction
# ---------------------------------------------------------------------------


class TestExtraRingContinuityFamilyConstruction:
    """Verify extra-ring continuity family is well-formed."""

    def test_family_group_name_and_expression_count(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """Family is named extra_ring and has exactly 4 expressions."""

        assert extraRingFamily.continuityGroupName == "extra_ring"
        # We, Ne, Ee, Se — first-class zones only; corners are derived
        assert len(extraRingFamily.expressions) == 4

    def test_all_expressions_use_continuity_op_and_group(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """Every expression uses CONTINUITY op and names extra_ring."""

        for expr in extraRingFamily.expressions:
            assert expr.op is GeometryCouplingOp.CONTINUITY
            assert expr.groupName == "extra_ring"

    def test_family_default_topology_builds(self) -> None:
        """Builder works without explicit topology argument."""

        family = extraRingContinuityFamily_build()
        assert isinstance(family, TopologyContinuityFamily)
        assert len(family.expressions) == 4

    def test_expression_tokens_match_ring_members(
        self,
        extraRingFamily: TopologyContinuityFamily,
        schema: BoardTopologySchema,
    ) -> None:
        """Expression tokens exactly match the extra_ring continuity group members."""

        exprTokens = {expr.token for expr in extraRingFamily.expressions}
        cg = schema.continuityGroup_get("extra_ring")
        assert cg is not None
        ringMembers = set(cg.members)
        assert exprTokens == ringMembers


# ---------------------------------------------------------------------------
# Obligation queries
# ---------------------------------------------------------------------------


class TestTokenObligationQueries:
    """Verify tokenObligated_isCheck returns correct results."""

    def test_ee_is_obligated(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """Ee (east extra longitude) is obligated — it is in the extra ring."""

        assert extraRingFamily.tokenObligated_isCheck(sfN.Ee)

    def test_corners_are_not_obligated(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """Derived corner tokens are not obligated — they are not ring members."""

        for corner in (sfN.NWe, sfN.NEe, sfN.SEe, sfN.SWe):
            assert not extraRingFamily.tokenObligated_isCheck(corner), (
                f"Corner {corner.name} is derived and must not be obligated"
            )

    def test_efe_is_not_obligated(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """Efe (east fan extra) is not obligated — not in the ring."""

        assert not extraRingFamily.tokenObligated_isCheck(sfN.Efe)


# ---------------------------------------------------------------------------
# Expression retrieval
# ---------------------------------------------------------------------------


class TestTokenExpressionRetrieval:
    """Verify tokenExpressions_get returns correct per-token expressions."""

    def test_ee_expression_fields(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """Ee has exactly one expression with correct token, op, group."""

        exprs = extraRingFamily.tokenExpressions_get(sfN.Ee)
        assert len(exprs) == 1
        assert exprs[0].token is sfN.Ee
        assert exprs[0].op is GeometryCouplingOp.CONTINUITY
        assert exprs[0].groupName == "extra_ring"

    def test_efe_has_no_expressions(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """Efe has no continuity expressions in the extra-ring family."""

        assert len(extraRingFamily.tokenExpressions_get(sfN.Efe)) == 0


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


class TestTextSprint:
    """Verify text_sprint produces readable output."""

    def test_text_sprint_contains_key_tokens(
        self, extraRingFamily: TopologyContinuityFamily
    ) -> None:
        """text_sprint mentions group name, operator, and Ee."""

        text = extraRingFamily.text_sprint()
        assert "extra_ring" in text
        assert "~~" in text
        assert "Ee" in text


# ---------------------------------------------------------------------------
# Topology consistency
# ---------------------------------------------------------------------------


class TestTopologyConsistency:
    """Verify continuity family is consistent with topology queries."""

    def test_obligated_tokens_match_continuity_group(
        self,
        extraRingFamily: TopologyContinuityFamily,
        schema: BoardTopologySchema,
    ) -> None:
        """Every obligated token is also in the topology continuity group."""

        for expr in extraRingFamily.expressions:
            assert schema.regionInContinuityGroup_isCheck(
                expr.token, "extra_ring"
            ), f"{expr.token.name} obligated but not in topology group"

    def test_ee_neighbor_west_efe_is_not_obligated(
        self,
        extraRingFamily: TopologyContinuityFamily,
        schema: BoardTopologySchema,
    ) -> None:
        """Efe is west of Ee but is not ring-obligated — fan, not ring."""

        westOfEe = schema.neighborWest_get(sfN.Ee)
        assert westOfEe is sfN.Efe
        assert not extraRingFamily.tokenObligated_isCheck(sfN.Efe)

    def test_topology_continuity_group_ee_ring_traversal(
        self, schema: BoardTopologySchema
    ) -> None:
        """Ring traversal from Ee reaches all 4 first-class extra-ring members."""

        cg = schema.continuityGroup_get("extra_ring")
        assert cg is not None
        visited: set[sfN] = set()
        current = sfN.Ee
        for _ in range(len(cg.members)):
            visited.add(current)
            nxt = cg.ringNeighborCW_get(current)
            assert nxt is not None
            current = nxt
        assert len(visited) == 4
