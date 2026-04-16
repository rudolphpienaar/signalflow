"""Topology-backed continuity doctrine for board geometry.

This module defines continuity families that are bound to a symbolic topology
schema rather than to concrete region ids. It makes continuity obligations
first-class queryable objects before any interpreter or repair pass runs.

The first concrete case is the extra-ring continuity family:

- ``Ee`` (east extra longitude) participates in the ``extra_ring``
  continuity group.
- Moving ``Ee`` without moving the other ring members may break ring
  continuity.
- This module makes that obligation queryable so that downstream
  interpreter passes can detect and act on it.

Key classes:
    TopologyContinuityExpr: One continuity obligation for a single token.
    TopologyContinuityFamily: Topology-backed coupling family for one ring.

Key builders:
    extraRingContinuityFamily_build: Build the extra-ring continuity family.

Typical usage:
    schema = wteZoneBoardTopologySchema_build()
    family = extraRingContinuityFamily_build(schema)
    family.tokenObligated_isCheck(sfN.Ee)    # → True
    family.tokenObligated_isCheck(sfN.Efe)   # → False
    family.tokenExpressions_get(sfN.Ee)      # → continuity expressions

Dependencies:
    - BoardTopologySchema from signalflow.board.geometry.topology
    - GeometryCouplingOp from signalflow.board.geometry.coupling
    - sfN from signalflow.notation.sfn
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.geometry.coupling import GeometryCouplingOp
from signalflow.board.geometry.topology import (
    BoardTopologySchema,
    wteZoneBoardTopologySchema_build,
)
from signalflow.notation.sfn import sfN


@dataclass(frozen=True)
class TopologyContinuityExpr:
    """One continuity obligation for a single symbolic region token.

    A continuity expression records that a given token participates in a
    named continuity group and must therefore remain connected to the rest
    of that group after any local geometry move.

    Attributes:
        token: The sfN region token subject to the continuity obligation.
        op: Always ``GeometryCouplingOp.CONTINUITY`` (``~~``).
        groupName: Canonical name of the continuity group such as
            ``"extra_ring"``.

    Example:
        >>> expr = TopologyContinuityExpr(
        ...     token=sfN.Ee,
        ...     op=GeometryCouplingOp.CONTINUITY,
        ...     groupName="extra_ring",
        ... )
        >>> expr.token
        <sfN.Ee: 'East Extra Longitude'>
    """

    token: sfN
    op: GeometryCouplingOp
    groupName: str


@dataclass(frozen=True)
class TopologyContinuityFamily:
    """Topology-backed continuity family for one named ring.

    A continuity family collects all ``~~`` obligations for every member of
    a named continuity group in the symbolic topology. It is the doctrinal
    object that downstream interpreter passes query to determine whether a
    proposed geometry move requires continuity repair.

    Attributes:
        continuityGroupName: Canonical name of the continuity group this
            family represents, such as ``"extra_ring"``.
        topology: The symbolic topology schema that owns the named group.
        expressions: All continuity obligations for every member of the
            group, in the group's declared member order.

    Example:
        >>> schema = wteZoneBoardTopologySchema_build()
        >>> family = extraRingContinuityFamily_build(schema)
        >>> family.tokenObligated_isCheck(sfN.Ee)
        True
        >>> family.tokenObligated_isCheck(sfN.Efe)
        False
    """

    continuityGroupName: str
    topology: BoardTopologySchema
    expressions: tuple[TopologyContinuityExpr, ...]

    def tokenObligated_isCheck(self, token: sfN) -> bool:
        """Return whether moving a token triggers a continuity obligation.

        A token is obligated when it belongs to this family's continuity
        group. Moving an obligated token may break ring continuity and
        requires a downstream continuity repair pass.

        Args:
            token: sfN region token to test.

        Returns:
            True when the token is a member of the continuity group and
            therefore subject to continuity obligations, otherwise False.
        """

        return self.topology.regionInContinuityGroup_isCheck(
            token,
            self.continuityGroupName,
        )

    def tokenExpressions_get(
        self,
        token: sfN,
    ) -> tuple[TopologyContinuityExpr, ...]:
        """Return all continuity expressions for a given token.

        Args:
            token: sfN region token to look up.

        Returns:
            Tuple of TopologyContinuityExpr instances for the token. Empty
            tuple when the token has no continuity obligations in this
            family.
        """

        return tuple(
            expr for expr in self.expressions if expr.token is token
        )

    def text_sprint(self) -> str:
        """Return a compact human-readable summary of this family.

        Returns:
            Multi-line text listing each continuity expression.
        """

        lines = [f"continuity family: {self.continuityGroupName}"]
        for expr in self.expressions:
            lines.append(
                f"  {expr.token.name} {expr.op.value} {expr.groupName}"
            )
        return "\n".join(lines)


def extraRingContinuityFamily_build(
    topology: BoardTopologySchema | None = None,
) -> TopologyContinuityFamily:
    """Build the extra-ring continuity family from a topology schema.

    The extra-ring continuity family records a ``~~`` obligation for every
    member of the ``"extra_ring"`` continuity group. This makes it
    queryable whether a proposed geometry move (such as displacing ``Ee``)
    triggers a ring-continuity obligation.

    This is the first topology-backed doctrinal family and the motivating
    case for Phase G3. Downstream phases will use it to:

    - detect that ``Ee`` displacement opens a gap relative to ``Efe``
    - confirm that the extra ring continuity is now at risk
    - trigger repair through the local interpreter

    Args:
        topology: Optional topology schema. When omitted the canonical WTE
            zone schema is used.

    Returns:
        TopologyContinuityFamily covering every member of the extra ring.

    Example:
        >>> family = extraRingContinuityFamily_build()
        >>> family.tokenObligated_isCheck(sfN.Ee)
        True
        >>> family.tokenObligated_isCheck(sfN.Efe)
        False
        >>> len(family.expressions)
        8
    """

    resolvedTopology = (
        topology
        if topology is not None
        else wteZoneBoardTopologySchema_build()
    )
    groupName = "extra_ring"
    cg = resolvedTopology.continuityGroup_get(groupName)
    ringMembers: tuple[sfN, ...] = cg.members if cg is not None else ()
    expressions: tuple[TopologyContinuityExpr, ...] = tuple(
        TopologyContinuityExpr(
            token=member,
            op=GeometryCouplingOp.CONTINUITY,
            groupName=groupName,
        )
        for member in ringMembers
    )
    return TopologyContinuityFamily(
        continuityGroupName=groupName,
        topology=resolvedTopology,
        expressions=expressions,
    )


__all__ = [
    "TopologyContinuityExpr",
    "TopologyContinuityFamily",
    "extraRingContinuityFamily_build",
]
