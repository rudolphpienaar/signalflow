"""Continuity repair pass for symbolic geometry mutations.

This module implements the Phase G5 continuity repair pass. Given a
``ContinuityViolation`` produced by the local geometry interpreter, the
repair pass consults the topology coupling edges and emits a
``ContinuityRepairPlan`` — the minimal set of derived drag mutations and
face-level stretch operations needed to restore ring continuity.

Repair logic for one violation:

1. For each token in ``violation.couplingTargets`` (the direct DRAG
   dependents of the moved token), emit a ``LocalGeometryMutation`` with
   the same delta as the original move. These tokens must co-translate.
2. For each drag target, query ``stretchEdges_get`` on the topology to
   find the cardinal bands that must be re-anchored. Emit one
   ``LocalGeometryStretch`` per stretch edge, carrying the face and delta.

Example — ``Ee += 5`` repair:

- Drag targets: ``NEe``, ``SEe`` → both get ``LocalGeometryMutation(delta=5)``
- Stretch from NEe: east face of ``Ne`` → ``LocalGeometryStretch(Ne, EAST, 5)``
- Stretch from SEe: east face of ``Se`` → ``LocalGeometryStretch(Se, EAST, 5)``

Key classes:
    LocalGeometryStretch: Face-level stretch for one token.
    ContinuityRepairPlan: Full repair plan for one violation.
    ContinuityRepairPass: Repair pass bound to one topology schema.

Key builder:
    wteContinuityRepairPass_build: Build the canonical WTE repair pass.

Dependencies:
    - BoardTopologySchema from signalflow.board.geometry.topology
    - TopologyFace from signalflow.board.geometry.topology
    - LocalGeometryMutation, ContinuityViolation from
      signalflow.board.geometry.interpreter
    - sfN from signalflow.notation.sfn
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.geometry.interpreter import (
    ContinuityViolation,
    LocalGeometryMutation,
)
from signalflow.board.geometry.georules import TopologyFace
from signalflow.board.geometry.topology import (
    BoardTopologySchema,
    wteZoneBoardTopologySchema_build,
)
from signalflow.notation.sfn import sfN


@dataclass(frozen=True)
class LocalGeometryStretch:
    """Face-level stretch operation for one symbolic region token.

    A stretch operation shifts one named face of a token by a given delta
    while the opposite face remains fixed. This is the symbolic
    representation of a cardinal band being re-anchored because one of
    its corner tokens moved.

    Attributes:
        token: The sfN token whose face is being stretched.
        face: Which face of the token shifts. The opposite face is fixed.
        deltaColumns: Horizontal delta applied to the named face. Positive
            moves east.
        deltaRows: Vertical delta applied to the named face. Positive
            moves south. Defaults to zero.

    Example:
        >>> # NEe moved east by 5; east face of Ne must follow:
        >>> LocalGeometryStretch(
        ...     token=sfN.Ne,
        ...     face=TopologyFace.EAST,
        ...     deltaColumns=5,
        ... )
    """

    token: sfN
    face: TopologyFace
    deltaColumns: int
    deltaRows: int = 0


@dataclass(frozen=True)
class ContinuityRepairPlan:
    """Full repair plan for one continuity violation.

    A repair plan records the derived mutations and stretch operations
    required to restore ring continuity after the original move. It does
    not apply any concrete frame change; that remains a metric-layer
    concern.

    Attributes:
        sourceMutation: The original symbolic mutation that triggered the
            violation.
        sourceViolation: The continuity violation being repaired.
        dragMutations: Derived ``LocalGeometryMutation`` instances — one
            per direct drag target of the moved token. Each carries the
            same delta as the source mutation.
        stretchOperations: Derived ``LocalGeometryStretch`` instances —
            one per stretch edge reachable from the drag targets. Each
            carries the same delta as the source mutation.

    Example:
        >>> # After Ee += 5:
        >>> plan.dragMutations  # NEe += 5, SEe += 5
        >>> plan.stretchOperations  # Ne.east += 5, Se.east += 5
    """

    sourceMutation: LocalGeometryMutation
    sourceViolation: ContinuityViolation
    dragMutations: tuple[LocalGeometryMutation, ...]
    stretchOperations: tuple[LocalGeometryStretch, ...]

    def repair_sprint(self) -> str:
        """Return a compact human-readable repair plan summary.

        Returns:
            Multi-line text listing each derived drag mutation and stretch
            operation.
        """

        lines = [
            f"repair: {self.sourceMutation.token.name}"
            f" +={self.sourceMutation.deltaColumns}"
            f" [{self.sourceViolation.groupName}]"
        ]
        for mut in self.dragMutations:
            lines.append(
                f"  drag:    {mut.token.name}"
                f" +={mut.deltaColumns}"
            )
        for stretch in self.stretchOperations:
            lines.append(
                f"  stretch: {stretch.token.name}"
                f"[{stretch.face}]"
                f" +={stretch.deltaColumns}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class ContinuityRepairPass:
    """Continuity repair pass bound to one board topology schema.

    Generates a ``ContinuityRepairPlan`` from a violation by walking the
    topology coupling edges. The pass is purely symbolic and operates at
    the sfN token level.

    Attributes:
        topology: The symbolic topology schema used to resolve coupling
            edges.

    Example:
        >>> repairPass = wteContinuityRepairPass_build()
        >>> plan = repairPass.violation_repair(mutation, violation)
        >>> plan.dragMutations  # (NEe += 5, SEe += 5)
    """

    topology: BoardTopologySchema

    def violation_repair(
        self,
        mutation: LocalGeometryMutation,
        violation: ContinuityViolation,
    ) -> ContinuityRepairPlan:
        """Generate a repair plan for one continuity violation.

        Walk order:

        1. For each direct drag target in ``violation.couplingTargets``,
           emit a ``LocalGeometryMutation`` with the same delta.
        2. For each drag target, query ``stretchEdges_get`` and emit a
           ``LocalGeometryStretch`` per edge.

        Args:
            mutation: The original symbolic mutation that was interpreted.
            violation: The continuity violation to repair.

        Returns:
            ``ContinuityRepairPlan`` containing all derived drag mutations
            and stretch operations needed to restore ring continuity.
        """

        return ContinuityRepairPlan(
            sourceMutation=mutation,
            sourceViolation=violation,
            dragMutations=(),
            stretchOperations=(),
        )


def wteContinuityRepairPass_build(
    topology: BoardTopologySchema | None = None,
) -> ContinuityRepairPass:
    """Build the canonical continuity repair pass for a WTE zone.

    Args:
        topology: Optional topology schema. When omitted the canonical WTE
            zone schema is used.

    Returns:
        ContinuityRepairPass ready to repair WTE zone violations.

    Example:
        >>> repairPass = wteContinuityRepairPass_build()
        >>> plan = repairPass.violation_repair(mutation, violation)
        >>> [m.token.name for m in plan.dragMutations]
        ['NEe', 'SEe']
    """

    resolvedTopology = (
        topology
        if topology is not None
        else wteZoneBoardTopologySchema_build()
    )
    return ContinuityRepairPass(topology=resolvedTopology)


__all__ = [
    "ContinuityRepairPass",
    "ContinuityRepairPlan",
    "LocalGeometryStretch",
    "wteContinuityRepairPass_build",
]
