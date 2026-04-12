"""Tests for the local geometry interpreter (Phase G4).

Verifies interpreter acceptance criteria:

- Ee displacement produces a continuity violation
- violation correctly identifies Efe as west neighbor
- Efe displacement produces no continuity violation
- Et displacement produces no extra-ring violation
- stable_isCheck reflects violation state
- violations_sprint produces readable output
- interpreter works with explicit topology
"""

from __future__ import annotations

import pytest

from signalflow.board.geometry.interpreter import (
    LocalGeometryInterpreter,
    LocalGeometryMutation,
    wteLocalGeometryInterpreter_build,
)
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
def interp() -> LocalGeometryInterpreter:
    """Return the canonical WTE local geometry interpreter."""

    return wteLocalGeometryInterpreter_build()


# ---------------------------------------------------------------------------
# Interpreter construction
# ---------------------------------------------------------------------------


class TestInterpreterConstruction:
    """Verify interpreter builds correctly."""

    def test_interpreter_has_continuity_families(
        self, interp: LocalGeometryInterpreter
    ) -> None:
        """WTE interpreter registers at least one continuity family."""

        assert len(interp.continuityFamilies) >= 1

    def test_builder_accepts_explicit_topology(
        self, schema: BoardTopologySchema
    ) -> None:
        """Builder accepts an explicit topology schema."""

        interp = wteLocalGeometryInterpreter_build(topology=schema)
        assert interp.topology is schema


# ---------------------------------------------------------------------------
# Ee displacement: the primary G4 case
# ---------------------------------------------------------------------------


class TestEeDisplacementViolation:
    """Verify Ee displacement produces a continuity violation."""

    def test_ee_displacement_violation_fields(
        self, interp: LocalGeometryInterpreter
    ) -> None:
        """Moving Ee produces one violation naming extra_ring.

        Coupling targets are NEe and SEe — the corners that must
        co-translate with Ee. Efe is NOT a coupling target; it is a fan
        token outside the ring.
        """

        result = interp.mutation_interpret(
            LocalGeometryMutation(token=sfN.Ee, deltaColumns=5)
        )
        assert not result.stable_isCheck()
        assert len(result.continuityViolations) == 1
        violation = result.continuityViolations[0]
        assert violation.movedToken is sfN.Ee
        assert violation.groupName == "extra_ring"
        assert sfN.NEe in violation.couplingTargets
        assert sfN.SEe in violation.couplingTargets
        assert sfN.Efe not in violation.couplingTargets


# ---------------------------------------------------------------------------
# Non-ring token displacement: no extra-ring violation
# ---------------------------------------------------------------------------


class TestNonRingDisplacement:
    """Verify tokens outside the extra ring produce no ring violations."""

    def test_efe_displacement_is_stable(
        self, interp: LocalGeometryInterpreter
    ) -> None:
        """Moving Efe (east fan extra) is stable — not in extra ring."""

        result = interp.mutation_interpret(
            LocalGeometryMutation(token=sfN.Efe, deltaColumns=5)
        )
        assert result.stable_isCheck()
        assert len(result.continuityViolations) == 0


# ---------------------------------------------------------------------------
# Other ring member displacement: violation expected
# ---------------------------------------------------------------------------


class TestOtherRingMemberDisplacement:
    """Verify other extra-ring members also produce violations."""

    def test_we_displacement_is_not_stable(
        self, interp: LocalGeometryInterpreter
    ) -> None:
        """Moving We (west extra longitude) violates extra ring."""

        result = interp.mutation_interpret(
            LocalGeometryMutation(token=sfN.We, deltaColumns=3)
        )
        assert not result.stable_isCheck()

    def test_ne_displacement_is_not_stable(
        self, interp: LocalGeometryInterpreter
    ) -> None:
        """Moving Ne (north extra latitude) violates extra ring."""

        result = interp.mutation_interpret(
            LocalGeometryMutation(token=sfN.Ne, deltaColumns=0, deltaRows=3)
        )
        assert not result.stable_isCheck()


# ---------------------------------------------------------------------------
# Result text output
# ---------------------------------------------------------------------------


class TestInterpreterResultText:
    """Verify violations_sprint output is human-readable."""

    def test_stable_result_sprint(
        self, interp: LocalGeometryInterpreter
    ) -> None:
        """Stable result sprint contains <stable>."""

        result = interp.mutation_interpret(
            LocalGeometryMutation(token=sfN.Efe, deltaColumns=5)
        )
        assert "<stable>" in result.violations_sprint()

    def test_violation_result_sprint(
        self, interp: LocalGeometryInterpreter
    ) -> None:
        """Violation sprint mentions Ee, extra_ring, and drag targets."""

        result = interp.mutation_interpret(
            LocalGeometryMutation(token=sfN.Ee, deltaColumns=5)
        )
        text = result.violations_sprint()
        assert "Ee" in text
        assert "extra_ring" in text
        assert "NEe" in text
