"""Geometry-scope models for board-level boundary ownership.

This module defines the typed vocabulary for board geometry scopes. A geometry
scope is a named grouping of chip references that owns a load-bearing geometry
boundary. Geometry scopes are always present even when they are not drawn.

Key components:
    - BoardGeometryScopeKind: Explicit kind discriminant for scope variants
    - BoardGeometryScope: First-class geometry scope with chip membership,
      stable id, kind, label, and drawable policy

Typical usage:
    Builders generate depth-layer scopes from CallingStack depth bands.
    Render layers filter to drawable scopes. World harmonization locates
    the scope that contains a given chip ref via chip membership lookup.

Dependencies:
    - Requires ChipRef from signalflow.models.chip
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from signalflow.models.chip import ChipRef
from signalflow.models.routing_zone import RoutingZoneRegionFrame


class BoardGeometryScopeKind(Enum):
    """Discriminant for board geometry scope variants.

    Attributes:
        DEPTH_LAYER: Implicit call-depth geometry layer. Always present;
            non-drawable by default. Scope id uses the ``layer/N`` prefix.
    """

    DEPTH_LAYER = auto()


@dataclass(frozen=True)
class BoardGeometryScope:
    """One named, typed geometry scope owning a set of chip references.

    A geometry scope groups chip references into a load-bearing geometric
    boundary. The scope always exists in geometry even when it is not drawn.
    Drawability is a separate policy flag, not proof of geometric existence.

    Attributes:
        scopeId: Stable scope identifier. Depth-layer scopes use the
            ``layer/N`` prefix (e.g. ``layer/0``, ``layer/1``).
        kind: Explicit kind discriminant distinguishing depth-layer scopes
            from future source-module or user-group scope variants.
        label: Human-readable label used for debug display and legend output.
        chipRefs: Ordered chip occurrences assigned to this scope.
        drawable: Whether this scope renders as a visible boundary box.
            Depth-layer scopes default to ``False``.
        frame: Computed bounding-box frame enclosing all chip placements in
            this scope. Present even for non-drawable scopes so that canvas
            sizing and world harmonization can use it. ``None`` when no chip
            placements are available at construction time.

    Example:
        >>> scope = BoardGeometryScope(
        ...     scopeId="layer/0",
        ...     kind=BoardGeometryScopeKind.DEPTH_LAYER,
        ...     label="layer/0",
        ...     chipRefs=(ChipRef(chipId=someChipId),),
        ...     drawable=False,
        ... )
    """

    scopeId: str
    kind: BoardGeometryScopeKind
    label: str
    chipRefs: tuple[ChipRef, ...] = field(default_factory=tuple)
    drawable: bool = False
    frame: RoutingZoneRegionFrame | None = None

    def chipRef_containsCheck(self, chipRef: ChipRef) -> bool:
        """Return True when this scope contains the given chip reference.

        Args:
            chipRef: Chip occurrence to test for membership.

        Returns:
            True if chipRef is a member of this scope, False otherwise.
        """

        return chipRef in self.chipRefs
