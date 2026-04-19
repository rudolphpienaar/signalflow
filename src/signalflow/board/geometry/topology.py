"""Symbolic topology schema for board geometry.

This module defines the top-layer symbolic geometry topology for one
board zone.
It makes region order, adjacency, family membership, and continuity group
membership first-class queryable concepts, independent of concrete frame
coordinates.

The intended stack is:

1. symbolic topology schema (this module)
2. coupling and constraint doctrine
3. local geometry interpreter
4. concrete metric realization

Key classes:
    TopologyFamily: Named group of symbolic regions that share a geometry role.
    ContinuityGroup: Named group of symbolic regions that must stay connected.
    BoardTopologySchema: Top-layer symbolic topology for one board zone.

Typical usage:
    schema = wteZoneBoardTopologySchema_build()
    westOfEe = schema.neighborWest_get(sfN.Ee)   # → sfN.Efe
    extraRing = schema.familyMembers_get("extra_ring")
    groups = schema.regionContinuityGroups_get(sfN.Ee)

Dependencies:
    - sfN from signalflow.notation.sfn for all region tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from signalflow.notation.sfn import sfN



@dataclass(frozen=True)
class TopologyFamily:
    """Named group of symbolic geometry regions that share a geometry role.

    A topology family groups regions that play the same architectural role
    within a board zone. Examples include the extra routing ring, the
    chip-terminal bands, and the intra routing bands.

    Attributes:
        name: Canonical family name such as ``"extra_ring"`` or
            ``"chip_terminal"``.
        members: Ordered tuple of sfN tokens belonging to this family.
            Order is significant: queries that need ordered members respect
            the position here.

    Example:
        >>> fam = TopologyFamily(
        ...     name="extra_longitude",
        ...     members=(sfN.We, sfN.Ee),
        ... )
        >>> sfN.Ee in fam.members
        True
    """

    name: str
    members: tuple[sfN, ...]

    def member_isCheck(self, token: sfN) -> bool:
        """Return whether a symbolic token belongs to this family.

        Args:
            token: sfN region token to test.

        Returns:
            True when the token is a member of this family, otherwise False.
        """

        return token in self.members


@dataclass(frozen=True)
class ContinuityGroup:
    """Named group of symbolic regions that must remain connected.

    A continuity group defines which regions form a connected routing family.
    When any member moves, the group's continuity obligations must be
    re-evaluated and repaired if broken.

    Attributes:
        name: Canonical group name such as ``"extra_ring"``.
        members: Ordered tuple of sfN tokens in the group. For ring groups
            the order is the traversal order around the ring so that clockwise
            and counter-clockwise neighbor queries are well-defined.
        isRing: True when the members form a closed ring. The last member
            connects back to the first.

    Example:
        >>> cg = ContinuityGroup(
        ...     name="extra_ring",
        ...     members=(
        ...         sfN.We, sfN.NWe, sfN.Ne, sfN.NEe,
        ...         sfN.Ee, sfN.SEe, sfN.Se, sfN.SWe,
        ...     ),
        ...     isRing=True,
        ... )
        >>> cg.member_isCheck(sfN.Ee)
        True
    """

    name: str
    members: tuple[sfN, ...]
    isRing: bool = False

    def member_isCheck(self, token: sfN) -> bool:
        """Return whether a symbolic token belongs to this continuity group.

        Args:
            token: sfN region token to test.

        Returns:
            True when the token is a member of this group, otherwise False.
        """

        return token in self.members

    def ringNeighborCW_get(self, token: sfN) -> sfN | None:
        """Return the clockwise ring neighbor of a token.

        Only meaningful when ``isRing`` is True. The traversal order of
        ``members`` defines clockwise direction.

        Args:
            token: sfN region token to find the neighbor for.

        Returns:
            The clockwise neighbor token when the token is present and
            ``isRing`` is True, otherwise None.
        """

        if not self.isRing or token not in self.members:
            return None
        idx = self.members.index(token)
        return self.members[(idx + 1) % len(self.members)]

    def ringNeighborCCW_get(self, token: sfN) -> sfN | None:
        """Return the counter-clockwise ring neighbor of a token.

        Only meaningful when ``isRing`` is True. The traversal order of
        ``members`` defines clockwise direction, so counter-clockwise is its
        reverse.

        Args:
            token: sfN region token to find the neighbor for.

        Returns:
            The counter-clockwise neighbor token when the token is present
            and ``isRing`` is True, otherwise None.
        """

        if not self.isRing or token not in self.members:
            return None
        idx = self.members.index(token)
        return self.members[(idx - 1) % len(self.members)]


@dataclass(frozen=True)
class BoardTopologySchema:
    """Symbolic topology schema for one board zone.

    This is the top-layer geometry definition for a board zone. It expresses
    region order, adjacency, family membership, and continuity group membership
    as first-class queryable facts, without consulting concrete frame
    coordinates.

    Attributes:
        horizontalOrder: Symbolic region tokens in west-to-east order for the
            main horizontal axis. Includes all regions with a primary
            horizontal position: extra longitude, extra fan, chip terminal,
            intra fan, intra longitude, and the intra courtyard.
        verticalOrder: Symbolic region tokens in north-to-south order for the
            main vertical axis. Includes all regions with a primary vertical
            position.
        families: Named topology families for this zone. A token may belong
            to more than one family.
        continuityGroups: Named continuity groups for this zone. A token may
            belong to more than one continuity group.

    Example:
        >>> schema = wteZoneBoardTopologySchema_build()
        >>> schema.neighborWest_get(sfN.Ee)
        <sfN.Efe: 'East Fan Extra'>
        >>> schema.regionInContinuityGroup_isCheck(sfN.Ee, "extra_ring")
        True
    """

    horizontalOrder: tuple[sfN, ...]
    verticalOrder: tuple[sfN, ...]
    families: tuple[TopologyFamily, ...]
    continuityGroups: tuple[ContinuityGroup, ...]

    def neighborWest_get(self, token: sfN) -> sfN | None:
        """Return the immediate west neighbor of a token in horizontal order.

        Args:
            token: sfN region token to look up.

        Returns:
            The sfN token immediately west (left) in the horizontal order,
            or None when the token is absent from the horizontal order or is
            already the westmost token.
        """

        if token not in self.horizontalOrder:
            return None
        idx = self.horizontalOrder.index(token)
        if idx == 0:
            return None
        return self.horizontalOrder[idx - 1]

    def neighborEast_get(self, token: sfN) -> sfN | None:
        """Return the immediate east neighbor of a token in horizontal order.

        Args:
            token: sfN region token to look up.

        Returns:
            The sfN token immediately east (right) in the horizontal order,
            or None when the token is absent from the horizontal order or is
            already the eastmost token.
        """

        if token not in self.horizontalOrder:
            return None
        idx = self.horizontalOrder.index(token)
        if idx == len(self.horizontalOrder) - 1:
            return None
        return self.horizontalOrder[idx + 1]

    def neighborNorth_get(self, token: sfN) -> sfN | None:
        """Return the immediate north neighbor of a token in vertical order.

        Args:
            token: sfN region token to look up.

        Returns:
            The sfN token immediately north (up) in the vertical order,
            or None when the token is absent from the vertical order or is
            already the northmost token.
        """

        if token not in self.verticalOrder:
            return None
        idx = self.verticalOrder.index(token)
        if idx == 0:
            return None
        return self.verticalOrder[idx - 1]

    def neighborSouth_get(self, token: sfN) -> sfN | None:
        """Return the immediate south neighbor of a token in vertical order.

        Args:
            token: sfN region token to look up.

        Returns:
            The sfN token immediately south (down) in the vertical order,
            or None when the token is absent from the vertical order or is
            already the southmost token.
        """

        if token not in self.verticalOrder:
            return None
        idx = self.verticalOrder.index(token)
        if idx == len(self.verticalOrder) - 1:
            return None
        return self.verticalOrder[idx + 1]

    def familyMembers_get(self, familyName: str) -> tuple[sfN, ...]:
        """Return members of a named topology family.

        Args:
            familyName: Canonical family name such as ``"extra_ring"``.

        Returns:
            Ordered tuple of sfN tokens in the named family, or an empty
            tuple when the family name is not present in this schema.
        """

        for fam in self.families:
            if fam.name == familyName:
                return fam.members
        return ()

    def regionFamilies_get(self, token: sfN) -> tuple[TopologyFamily, ...]:
        """Return all topology families that contain a given token.

        Args:
            token: sfN region token to look up.

        Returns:
            Tuple of TopologyFamily instances that contain the token. Empty
            tuple when the token belongs to no declared family.
        """

        return tuple(fam for fam in self.families if fam.member_isCheck(token))

    def regionContinuityGroups_get(
        self,
        token: sfN,
    ) -> tuple[ContinuityGroup, ...]:
        """Return all continuity groups that contain a given token.

        Args:
            token: sfN region token to look up.

        Returns:
            Tuple of ContinuityGroup instances that contain the token. Empty
            tuple when the token belongs to no declared continuity group.
        """

        return tuple(
            cg for cg in self.continuityGroups if cg.member_isCheck(token)
        )

    def regionInContinuityGroup_isCheck(
        self,
        token: sfN,
        groupName: str,
    ) -> bool:
        """Return whether a token belongs to a named continuity group.

        Args:
            token: sfN region token to test.
            groupName: Canonical continuity group name.

        Returns:
            True when the token is a member of the named group, otherwise
            False.
        """

        for cg in self.continuityGroups:
            if cg.name == groupName and cg.member_isCheck(token):
                return True
        return False

    def continuityGroup_get(self, groupName: str) -> ContinuityGroup | None:
        """Return a continuity group by name.

        Args:
            groupName: Canonical continuity group name.

        Returns:
            The ContinuityGroup when present in this schema, otherwise None.
        """

        for cg in self.continuityGroups:
            if cg.name == groupName:
                return cg
        return None


@cache
def wteZoneBoardTopologySchema_build() -> BoardTopologySchema:
    """Build the canonical symbolic topology schema for a WTE board zone.

    The WTE (West-Terminal-East) zone is the standard intra-plus-extra routing
    zone layout. This schema encodes the west-to-east and north-to-south region
    ordering, named geometry families, and continuity group obligations
    for that zone type.

    The horizontal order matches the doc sketch::

        We | Wfe | Wt | Wfi | Wi | Ci | Ei | Efi | Et | Efe | Ee

    The extra ring continuity group runs clockwise::

        We → NWe → Ne → NEe → Ee → SEe → Se → SWe → (back to We)

    The result is cached: repeated calls return the same instance.

    Returns:
        Canonical BoardTopologySchema for the WTE zone type.

    Example:
        >>> schema = wteZoneBoardTopologySchema_build()
        >>> schema.neighborWest_get(sfN.Ee)
        <sfN.Efe: 'East Fan Extra'>
        >>> schema.regionInContinuityGroup_isCheck(sfN.Ee, "extra_ring")
        True
        >>> schema.continuityGroup_get("extra_ring").isRing
        True
    """

    # West-to-east horizontal order for the main routing axis.
    # Matches doc sketch: We | Wfe | Wt | Wm | Wfi | Wi | Ci | Ei | Efi | Em | Et | Efe | Ee
    horizontalOrder: tuple[sfN, ...] = (
        sfN.We,
        sfN.Wfe,
        sfN.Wt,
        sfN.Wm,
        sfN.Wfi,
        sfN.Wi,
        sfN.Ci,
        sfN.Ei,
        sfN.Efi,
        sfN.Em,
        sfN.Et,
        sfN.Efe,
        sfN.Ee,
    )

    # North-to-south vertical order for the main routing axis.
    verticalOrder: tuple[sfN, ...] = (
        sfN.Ne,
        sfN.Nfe,
        sfN.Nt,
        sfN.Nfi,
        sfN.Ni,
        sfN.Ci,
        sfN.Si,
        sfN.Sfi,
        sfN.St,
        sfN.Sfe,
        sfN.Se,
    )

    # Named topology families.
    families: tuple[TopologyFamily, ...] = (
        # The full extra routing ring including corners.
        TopologyFamily(
            name="extra_ring",
            members=(
                sfN.We,
                sfN.NWe,
                sfN.Ne,
                sfN.NEe,
                sfN.Ee,
                sfN.SEe,
                sfN.Se,
                sfN.SWe,
            ),
        ),
        # East-side extra family: the east extra longitude and its corners.
        TopologyFamily(
            name="east_extra",
            members=(sfN.Ee, sfN.NEe, sfN.SEe),
        ),
        # West-side extra family: the west extra longitude and its corners.
        TopologyFamily(
            name="west_extra",
            members=(sfN.We, sfN.NWe, sfN.SWe),
        ),
        # Extra longitude bands only (no corners).
        TopologyFamily(
            name="extra_longitude",
            members=(sfN.We, sfN.Ee),
        ),
        # Extra latitude bands only (no corners).
        TopologyFamily(
            name="extra_latitude",
            members=(sfN.Ne, sfN.Se),
        ),
        # Extra corner regions.
        TopologyFamily(
            name="extra_corner",
            members=(sfN.NWe, sfN.NEe, sfN.SEe, sfN.SWe),
        ),
        # Extra fan regions (bridge between chip terminal and extra routing).
        TopologyFamily(
            name="extra_fan",
            members=(sfN.Wfe, sfN.Efe, sfN.Nfe, sfN.Sfe),
        ),
        # The full intra routing ring including corners.
        TopologyFamily(
            name="intra_ring",
            members=(
                sfN.Wi,
                sfN.NWi,
                sfN.Ni,
                sfN.NEi,
                sfN.Ei,
                sfN.SEi,
                sfN.Si,
                sfN.SWi,
            ),
        ),
        # Intra longitude bands only (no corners).
        TopologyFamily(
            name="intra_longitude",
            members=(sfN.Wi, sfN.Ei),
        ),
        # Intra latitude bands only (no corners).
        TopologyFamily(
            name="intra_latitude",
            members=(sfN.Ni, sfN.Si),
        ),
        # Intra fan regions (bridge between chip terminal and intra routing).
        TopologyFamily(
            name="intra_fan",
            members=(sfN.Wfi, sfN.Efi, sfN.Nfi, sfN.Sfi),
        ),
        # Chip terminal bands on all four sides.
        TopologyFamily(
            name="chip_terminal",
            members=(sfN.Wt, sfN.Et, sfN.Nt, sfN.St),
        ),
        # Medial longitude pillars: inner extra columns enabling same-side U-turns.
        TopologyFamily(
            name="medial_longitude",
            members=(sfN.Wm, sfN.Em),
        ),
    )

    # Continuity groups: regions that must remain connected when any member
    # moves. The extra ring is the first doctrinal continuity group; it is
    # the motivating case for the Ee displacement problem.
    continuityGroups: tuple[ContinuityGroup, ...] = (
        ContinuityGroup(
            name="extra_ring",
            members=(sfN.We, sfN.Ne, sfN.Ee, sfN.Se),
            isRing=True,
        ),
        ContinuityGroup(
            name="intra_ring",
            members=(sfN.Wi, sfN.Ni, sfN.Ei, sfN.Si),
            isRing=True,
        ),
    )

    return BoardTopologySchema(
        horizontalOrder=horizontalOrder,
        verticalOrder=verticalOrder,
        families=families,
        continuityGroups=continuityGroups,
    )


__all__ = [
    "BoardTopologySchema",
    "ContinuityGroup",
    "TopologyFamily",
    "wteZoneBoardTopologySchema_build",
]
