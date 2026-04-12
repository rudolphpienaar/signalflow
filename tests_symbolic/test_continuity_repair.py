"""Tests for the continuity repair pass (Phase G5).

Verifies repair acceptance criteria:

- Ee violation repair produces drag mutations for NEe and SEe
- drag mutations carry same delta as original mutation
- repair produces stretch for Ne.east and Se.east
- stretch operations carry same delta as original mutation
- repair_sprint produces readable output
- repair pass accepts explicit topology
"""

from __future__ import annotations

import pytest

from signalflow.board.geometry.interpreter import (
    LocalGeometryMutation,
    wteLocalGeometryInterpreter_build,
)
from signalflow.board.geometry.repair import (
    ContinuityRepairPass,
    ContinuityRepairPlan,
    wteContinuityRepairPass_build,
)
from signalflow.board.geometry.topology import (
    BoardTopologySchema,
    TopologyFace,
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
def repairPass() -> ContinuityRepairPass:
    """Return the canonical WTE continuity repair pass."""

    return wteContinuityRepairPass_build()


@pytest.fixture
def eePlan(repairPass: ContinuityRepairPass) -> ContinuityRepairPlan:
    """Return the repair plan for Ee += 5."""

    interp = wteLocalGeometryInterpreter_build()
    mut = LocalGeometryMutation(token=sfN.Ee, deltaColumns=5)
    result = interp.mutation_interpret(mut)
    violation = result.continuityViolations[0]
    return repairPass.violation_repair(mut, violation)


# ---------------------------------------------------------------------------
# Repair pass construction
# ---------------------------------------------------------------------------


class TestRepairPassConstruction:
    """Verify repair pass builds correctly."""

    def test_builder_accepts_explicit_topology(
        self, schema: BoardTopologySchema
    ) -> None:
        """Builder accepts an explicit topology schema."""

        rp = wteContinuityRepairPass_build(topology=schema)
        assert rp.topology is schema


# ---------------------------------------------------------------------------
# Drag mutations: direct coupling targets co-translate
# ---------------------------------------------------------------------------


class TestDragMutations:
    """Verify drag mutations for Ee violation."""

    def test_ee_repair_drag_targets_are_nee_and_see(
        self, eePlan: ContinuityRepairPlan
    ) -> None:
        """Ee repair emits drag mutations for NEe and SEe."""

        dragTokens = {m.token for m in eePlan.dragMutations}
        assert sfN.NEe in dragTokens
        assert sfN.SEe in dragTokens

    def test_drag_mutations_carry_original_delta(
        self, eePlan: ContinuityRepairPlan
    ) -> None:
        """Drag mutations carry the same delta as the original mutation."""

        for mut in eePlan.dragMutations:
            assert mut.deltaColumns == 5
            assert mut.deltaRows == 0


# ---------------------------------------------------------------------------
# Stretch operations: cardinal bands re-anchored
# ---------------------------------------------------------------------------


class TestStretchOperations:
    """Verify stretch operations for Ee violation."""

    def test_ee_repair_stretches_ne_east_and_se_east(
        self, eePlan: ContinuityRepairPlan
    ) -> None:
        """Ee repair stretches east face of Ne and east face of Se."""

        stretchMap = {
            (s.token, s.face) for s in eePlan.stretchOperations
        }
        assert (sfN.Ne, TopologyFace.EAST) in stretchMap
        assert (sfN.Se, TopologyFace.EAST) in stretchMap

    def test_stretch_operations_carry_original_delta(
        self, eePlan: ContinuityRepairPlan
    ) -> None:
        """Stretch operations carry the same delta as the original mutation."""

        for stretch in eePlan.stretchOperations:
            assert stretch.deltaColumns == 5
            assert stretch.deltaRows == 0

    def test_efe_not_in_stretch_targets(
        self, eePlan: ContinuityRepairPlan
    ) -> None:
        """Efe does not appear in any stretch operation — fan, not ring."""

        stretchTokens = {s.token for s in eePlan.stretchOperations}
        assert sfN.Efe not in stretchTokens


# ---------------------------------------------------------------------------
# Sprint output
# ---------------------------------------------------------------------------


class TestRepairSprint:
    """Verify repair_sprint output is human-readable."""

    def test_repair_sprint_mentions_moved_token_and_targets(
        self, eePlan: ContinuityRepairPlan
    ) -> None:
        """repair_sprint mentions Ee, NEe, Se, and east."""

        text = eePlan.repair_sprint()
        assert "Ee" in text
        assert "NEe" in text
        assert "Se" in text
        assert "east" in text
