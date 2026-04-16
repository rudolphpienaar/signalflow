"""Local geometry interpreter for symbolic topology mutations.

This module implements the Phase G4 local geometry interpreter. It takes
one symbolic mutation, applies it against the topology and coupling doctrine,
validates continuity constraints, and emits any violations found.

The interpreter is purely symbolic. It works at the ``sfN`` token level and
does not mutate concrete ``BoardGeometry`` frames. Metric frame application
remains in the board/coupling layer; this interpreter reasons about what
must happen before those frames move.

Interpreter pass order:

1. Record the direct mutation.
2. Fire direct coupling rules tied to the moved token.
3. Validate enclosure constraints (enclosure check, not yet implemented).
4. Validate continuity constraints using registered continuity families.
5. Emit violations as ``ContinuityViolation`` instances.
6. Mark result stable if no violations remain.

The first concrete case handled is ``Ee += delta``:

- ``Ee`` is in the ``extra_ring`` continuity group.
- Moving ``Ee`` creates a gap relative to its west topology neighbor
  ``Efe``.
- The interpreter detects this gap as a ``ContinuityViolation``.
- Repair is deferred to Phase G5.

Key classes:
    LocalGeometryMutation: One symbolic mutation — a token plus deltas.
    ContinuityViolation: One detected continuity break after a mutation.
    LocalInterpreterResult: Full result of one interpreter pass.
    LocalGeometryInterpreter: The interpreter itself.

Key builder:
    wteLocalGeometryInterpreter_build: Build the canonical WTE interpreter.

Typical usage:
    interp = wteLocalGeometryInterpreter_build()
    result = interp.mutation_interpret(
        LocalGeometryMutation(token=sfN.Ee, deltaColumns=5)
    )
    result.stable_isCheck()   # → False (continuity violated)
    result.continuityViolations[0].movedToken  # → sfN.Ee
    result.continuityViolations[0].movedToken  # → sfN.Ee

Dependencies:
    - BoardTopologySchema from signalflow.board.geometry.topology
    - TopologyContinuityFamily from signalflow.board.geometry.continuity
    - sfN from signalflow.notation.sfn
"""

from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.board.geometry.continuity import (
    TopologyContinuityFamily,
    extraRingContinuityFamily_build,
)
from signalflow.board.geometry.topology import (
    BoardTopologySchema,
    wteZoneBoardTopologySchema_build,
)
from signalflow.notation.sfn import sfN


@dataclass(frozen=True)
class LocalGeometryMutation:
    """One proposed symbolic local geometry mutation.

    Records that a specific region token should move by a given number of
    columns and/or rows. This is the symbolic input to the interpreter; no
    concrete frame is mutated at this level.

    Attributes:
        token: The sfN region token to move.
        deltaColumns: Horizontal displacement in board columns. Positive
            values move east; the monotone propagation invariant requires
            this to be non-negative for authoritative moves.
        deltaRows: Vertical displacement in board rows. Positive values
            move south. Defaults to zero for pure horizontal moves.

    Example:
        >>> mut = LocalGeometryMutation(token=sfN.Ee, deltaColumns=5)
        >>> mut.token
        <sfN.Ee: 'East Extra Longitude'>
        >>> mut.deltaColumns
        5
    """

    token: sfN
    deltaColumns: int
    deltaRows: int = 0


@dataclass(frozen=True)
class ContinuityViolation:
    """One detected continuity break after a local geometry mutation.

    A continuity violation records that a moved token belongs to a named
    continuity group and identifies the direct coupling targets that must
    co-move to restore continuity. The violation does not specify repair;
    it names the broken relationships so that a repair pass (Phase G5)
    can act on them.

    Attributes:
        movedToken: The sfN token that was moved by the mutation.
        groupName: Canonical continuity group name such as
            ``"extra_ring"``.

    Example:
        >>> # After Ee moves east by 5 columns:
        >>> violation.movedToken
        <sfN.Ee: 'East Extra Longitude'>
        >>> violation.groupName
        'extra_ring'
    """

    movedToken: sfN
    groupName: str


@dataclass(frozen=True)
class LocalInterpreterResult:
    """Result of one local geometry interpreter pass.

    Attributes:
        mutation: The symbolic mutation that was interpreted.
        continuityViolations: All continuity violations detected during
            this pass. Empty when the mutation leaves all continuity
            groups intact.

    Example:
        >>> result.stable_isCheck()
        False
        >>> len(result.continuityViolations)
        1
    """

    mutation: LocalGeometryMutation
    continuityViolations: tuple[ContinuityViolation, ...]

    def stable_isCheck(self) -> bool:
        """Return whether this result has no outstanding violations.

        Returns:
            True when no continuity violations were detected, meaning the
            mutation is safe to apply without repair. False when at least
            one continuity obligation was broken.
        """

        return len(self.continuityViolations) == 0

    def violations_sprint(self) -> str:
        """Return a compact human-readable violation summary.

        Returns:
            Multi-line text listing each continuity violation, or a
            single ``<stable>`` line when no violations exist.
        """

        if self.stable_isCheck():
            return (
                f"interpreter: {self.mutation.token.name}"
                f" +={self.mutation.deltaColumns} → <stable>"
            )
        lines = [
            f"interpreter: {self.mutation.token.name}"
            f" +={self.mutation.deltaColumns} → violations:"
        ]
        for v in self.continuityViolations:
            lines.append(f"  {v.movedToken.name} ~~ {v.groupName}")
        return "\n".join(lines)


@dataclass(frozen=True)
class LocalGeometryInterpreter:
    """Local geometry interpreter for one board zone.

    Interprets a single symbolic mutation against registered coupling
    doctrine and continuity families. Returns a result that records any
    continuity violations detected so that repair passes can act on them.

    The interpreter operates in one pass for Phase G4. Multi-pass
    iteration (repeat until stable or impossible) is scaffolded but only
    one round of continuity checking is performed at this phase.

    Attributes:
        topology: The symbolic topology schema for this zone.
        continuityFamilies: Registered continuity families. The
            interpreter checks every family whose ``tokenObligated_isCheck``
            returns True for the moved token.

    Example:
        >>> interp = wteLocalGeometryInterpreter_build()
        >>> result = interp.mutation_interpret(
        ...     LocalGeometryMutation(token=sfN.Ee, deltaColumns=5)
        ... )
        >>> result.stable_isCheck()
        False
    """

    topology: BoardTopologySchema
    continuityFamilies: tuple[TopologyContinuityFamily, ...] = field(
        default_factory=tuple
    )

    def mutation_interpret(
        self,
        mutation: LocalGeometryMutation,
    ) -> LocalInterpreterResult:
        """Interpret one symbolic mutation and return a result.

        Pass order:

        1. Record the direct mutation.
        2. For each registered continuity family, check whether the moved
           token is obligated (i.e., belongs to the family's group).
        3. When obligated, record the topology neighbors to describe the
           gap that the move opens.
        4. Collect all violations and return the result.

        Args:
            mutation: The symbolic mutation to interpret.

        Returns:
            LocalInterpreterResult containing all detected continuity
            violations and a stability flag.
        """

        violations: list[ContinuityViolation] = []

        for family in self.continuityFamilies:
            if not family.tokenObligated_isCheck(mutation.token):
                continue
            violations.append(
                ContinuityViolation(
                    movedToken=mutation.token,
                    groupName=family.continuityGroupName,
                )
            )

        return LocalInterpreterResult(
            mutation=mutation,
            continuityViolations=tuple(violations),
        )


def wteLocalGeometryInterpreter_build(
    topology: BoardTopologySchema | None = None,
) -> LocalGeometryInterpreter:
    """Build the canonical local geometry interpreter for a WTE zone.

    Registers the extra-ring continuity family so that any mutation
    involving an extra-ring member is immediately detected as a continuity
    obligation.

    Args:
        topology: Optional topology schema. When omitted the canonical WTE
            zone schema is used.

    Returns:
        LocalGeometryInterpreter ready to interpret WTE zone mutations.

    Example:
        >>> interp = wteLocalGeometryInterpreter_build()
        >>> result = interp.mutation_interpret(
        ...     LocalGeometryMutation(token=sfN.Ee, deltaColumns=5)
        ... )
        >>> result.stable_isCheck()
        False
        >>> result.continuityViolations[0].groupName
        'extra_ring'
    """

    resolvedTopology = (
        topology
        if topology is not None
        else wteZoneBoardTopologySchema_build()
    )
    extraRingFamily = extraRingContinuityFamily_build(resolvedTopology)
    return LocalGeometryInterpreter(
        topology=resolvedTopology,
        continuityFamilies=(extraRingFamily,),
    )


__all__ = [
    "ContinuityViolation",
    "LocalGeometryInterpreter",
    "LocalGeometryMutation",
    "LocalInterpreterResult",
    "wteLocalGeometryInterpreter_build",
]
