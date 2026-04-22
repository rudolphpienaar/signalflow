"""Structured algebraic path representation for routing solutions.

An algebraic path is the symbolic solver output for one routed wire. It names
the sequence of geometry regions a wire traverses from source chip terminal
to destination chip terminal, expressed entirely in sfN notation. The path
is a pure topology descriptor and carries no lane integers.

Lane assignment is the responsibility of ``WiringSolution``. It groups a
bundle of ``AlgebraicPath`` instances, owns the lane count, and resolves
each wire's concrete lane index from its position in the bundle plus each
hop's ``LaneSense``.

Key components:
    - LaneSense: Index mapping sense used per-hop.
    - PathHop: One region traversal with a lane sense.
    - AlgebraicPath: Topology-only source-to-sink path as an ordered hop
      sequence.
    - PathSolutionBuilder: Named mutable topology for user-defined solutions.
    - WiringSolution: Ordered group of paths for one wire bundle; owns lane
      state.

Typical usage — accumulate a WTE intra forward bundle::

    wteIntra.wire_add(source="App.ts.main().s1", sink="Proxy.ts.p1().s1")
    wteIntra.wire_add(source="App.ts.main().s2", sink="Proxy.ts.p1().s2")
    laneMap = wteIntra.laneMap_get(0)

Typical usage — user-defined topology::

    sol = PathSolutionBuilder("south_bend_wte_intra")
    sol.hop_add(sfN.Wfi)
    sol.hop_add(sfN.Wi,  LaneSense.FORWARD)
    sol.hop_add(sfN.Si,  LaneSense.FORWARD)
    sol.hop_add(sfN.Ei,  LaneSense.REVERSE)
    sol.hop_add(sfN.Efi)
    path = sol.resolve(source="App.ts.main().s1", sink="Proxy.ts.p1().s1")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.notation.sfn import sfN

_FAN_CHANNEL_NAMES: frozenset[str] = frozenset({"wf", "ef", "nf", "sf"})


class LaneSense(Enum):
    """Lane index mapping sense for one routing hop.

    ``LaneSense`` controls how a wire's index maps to a lane as the ribbon
    passes through a geometry region. Forward preserves order; reverse
    inverts it.

    Attributes:
        FIXED:   Not a routed lane — fan and transition hops only. No index
                 mapping applies.
        FORWARD: Wire index maps directly to lane index. Wire 1 → lane 1,
                 wire N → lane N.
        REVERSE: Wire index maps in inverted order. Wire 1 → lane N,
                 wire N → lane 1. Required at corners where the routing
                 geometry would otherwise force crossings.
    """

    FIXED = "fixed"
    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True)
class PathHop:
    """One region traversal in an algebraic routing path.

    A hop names a geometry region by its sfN member and carries the lane sense
    for that traversal. Fan and transition hops use ``LaneSense.FIXED``;
    routing channel hops use ``FORWARD`` or ``REVERSE``. No lane integer is
    stored here — lane assignment is the responsibility of ``WiringSolution``.

    Attributes:
        area: sfN region this hop traverses.
        laneSense: Index mapping sense for this hop. ``FIXED`` for
            fan/transition hops; ``FORWARD`` when wire order is preserved;
            ``REVERSE`` when wire order inverts to prevent corner crossings.

    Examples:
        Fan entry::

            PathHop(sfN.Wfi)

        Longitude hop — forward order::

            PathHop(sfN.Wi, LaneSense.FORWARD)

        Longitude hop — inverted at corner::

            PathHop(sfN.Ei, LaneSense.REVERSE)
    """

    area: sfN
    laneSense: LaneSense = LaneSense.FIXED

    def token_sprint(self) -> Result[str]:
        """Return the sfN channel name token for this hop as a result.

        Returns:
            ``ResultOk`` wrapping the channel name token such as ``wf`` or
            ``wLong``; ``ResultErr`` when the area has no path token defined
            in sfN (diagnostic pushed to ``diagnosticStack``).
        """

        token = self.area.channel_name
        if token is None:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="notation.path.hop.no_token",
                message=(
                    f"sfN.{self.area.name} "
                    f"({self.area.value!r}) has no path token "
                    "and cannot appear in an algebraic path"
                ),
                context=(self.area.name,),
            )
            return resultErr_build()
        return resultOk_build(token)


@dataclass(frozen=True)
class AlgebraicPath:
    """Topology-only symbolic routing path from source terminal to sink.

    An algebraic path names the sequence of geometry regions and lane senses a
    wire traverses. It carries no lane integers — those are owned by
    ``WiringSolution`` at the bundle level.

    The string form (``::``-delimited channel names) is a serialization for
    display and introspection.

    Attributes:
        source: Canonical source chip terminal identifier.
        hops: Ordered region traversals from source fan to sink fan.
        sink: Canonical sink chip terminal identifier.

    Examples:
        Forward WTE intra path::

            path = WTE_INTRA_FORWARD.resolve(
                source="App.ts.main().s1",
                sink="Proxy.ts.p1().s1",
            )
    """

    source: str
    hops: tuple[PathHop, ...]
    sink: str

    def text_sprint(self) -> Result[str]:
        """Serialize to the canonical ``::``-delimited path string as a result.

        Returns:
            ``ResultOk`` wrapping the full ``::``-delimited path string;
            ``ResultErr`` when any hop's area has no path token defined
            (diagnostic pushed to ``diagnosticStack``).
        """

        parts: list[str] = [self.source]
        for hop in self.hops:
            hopResult = hop.token_sprint()
            if not result_isOkCheck(hopResult):
                return resultErr_build()
            parts.append(hopResult.value)
        parts.append(self.sink)
        return resultOk_build("::".join(parts))

    @classmethod
    def fromText_build(cls, text: str) -> Result[AlgebraicPath]:
        """Deserialize a ``::``-delimited path string into a path.

        Interior tokens are matched against sfN channel names. Unrecognised
        tokens are skipped. Lane sense is inferred as ``FIXED`` for fan tokens
        and ``FORWARD`` for routing channel tokens; ``REVERSE`` is not
        preserved through serialization — use ``PathSolutionBuilder`` to
        retain full lane sense semantics.

        Args:
            text: ``::``-delimited algebraic path string such as produced by
                ``text_sprint()``.

        Returns:
            ``ResultOk`` wrapping a parsed ``AlgebraicPath``; ``ResultErr``
            when ``text`` contains fewer than two ``::`` separators (diagnostic
            pushed to ``diagnosticStack``).
        """

        tokens = text.split("::")
        if len(tokens) < 2:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.ROUTING,
                code="notation.path.parse.missing_separators",
                message=(
                    "Path text has no '::' separators; "
                    "expected at least source::sink"
                ),
                context=(text,),
            )
            return resultErr_build()
        source = tokens[0]
        sink = tokens[-1]
        hops: list[PathHop] = []
        for token in tokens[1:-1]:
            if re.fullmatch(r"[A-Za-z]+", token) is None:
                continue
            member = sfN.from_channel_name(token)
            if member is None:
                continue
            sense = (
                LaneSense.FIXED
                if token in _FAN_CHANNEL_NAMES
                else LaneSense.FORWARD
            )
            hops.append(PathHop(area=member, laneSense=sense))
        return resultOk_build(cls(source=source, hops=tuple(hops), sink=sink))

    def channelHops_get(self) -> tuple[PathHop, ...]:
        """Return only the routing channel hops, excluding fan/transition hops.

        Returns:
            Hops with ``FORWARD`` or ``REVERSE`` lane sense.
        """

        return tuple(
            hop for hop in self.hops if hop.laneSense is not LaneSense.FIXED
        )

    def fanHops_get(self) -> tuple[PathHop, ...]:
        """Return only the fan and transition hops.

        Returns:
            Hops with ``FIXED`` lane sense.
        """

        return tuple(
            hop for hop in self.hops if hop.laneSense is LaneSense.FIXED
        )


@dataclass
class PathSolutionBuilder:
    """Named mutable path solution topology for user-defined routing solutions.

    A ``PathSolutionBuilder`` records an ordered sequence of sfN regions with
    per-hop lane senses. It is the extension point for supplying alternative
    routing topologies. Call ``resolve`` to produce an ``AlgebraicPath``, or
    pass this builder to a ``WiringSolution`` to accumulate a full wire bundle.

    Attributes:
        name: Human-readable identifier for this solution topology.

    Examples:
        Build a custom topology and resolve::

            sol = PathSolutionBuilder("south_bend_wte_intra")
            sol.hop_add(sfN.Wfi)
            sol.hop_add(sfN.Wi,  LaneSense.FORWARD)
            sol.hop_add(sfN.Si,  LaneSense.FORWARD)
            sol.hop_add(sfN.Ei,  LaneSense.REVERSE)
            sol.hop_add(sfN.Efi)
            path = sol.resolve(
                source="App.ts.main().s1",
                sink="Proxy.ts.p1().s1",
            )

        One-shot via ``hops_set``::

            path = PathSolutionBuilder("south_bend_wte_intra").hops_set(
                PathHop(sfN.Wfi),
                PathHop(sfN.Wi,  LaneSense.FORWARD),
                PathHop(sfN.Si,  LaneSense.FORWARD),
                PathHop(sfN.Ei,  LaneSense.REVERSE),
                PathHop(sfN.Efi),
            ).resolve(source="App.ts.main().s1", sink="Proxy.ts.p1().s1")
    """

    name: str
    _hops: list[PathHop] = field(default_factory=list)

    def hop_add(
        self,
        area: sfN,
        laneSense: LaneSense = LaneSense.FIXED,
    ) -> PathSolutionBuilder:
        """Append one hop to the topology.

        Args:
            area: sfN region for this hop.
            laneSense: Index mapping sense. Defaults to ``FIXED`` for fan
                hops. Use ``FORWARD`` or ``REVERSE`` for routing channel hops.

        Returns:
            This builder, for optional fluent chaining.
        """

        self._hops.append(PathHop(area=area, laneSense=laneSense))
        return self

    def hops_set(self, *hops: PathHop) -> PathSolutionBuilder:
        """Replace the entire hop sequence in one call.

        Args:
            hops: Ordered ``PathHop`` objects defining the full topology.

        Returns:
            This builder, for optional fluent chaining.
        """

        self._hops = list(hops)
        return self

    def topology_get(self) -> tuple[PathHop, ...]:
        """Return the current hop sequence as an immutable tuple.

        Returns:
            Ordered ``PathHop`` objects representing the current topology.
        """

        return tuple(self._hops)

    def name_get(self) -> str:
        """Return the name of this solution topology.

        Returns:
            Human-readable topology name assigned at construction.
        """

        return self.name

    def resolve(self, source: str, sink: str) -> AlgebraicPath:
        """Produce a resolved ``AlgebraicPath`` for the given terminals.

        Args:
            source: Canonical source chip terminal identifier.
            sink: Canonical sink chip terminal identifier.

        Returns:
            ``AlgebraicPath`` with this topology's hop sequence and the
            provided source and sink terminals.
        """

        return AlgebraicPath(source=source, hops=tuple(self._hops), sink=sink)


@dataclass
class WiringSolution:
    """Ordered group of algebraic paths for one wire bundle; owns lane state.

    A ``WiringSolution`` binds a routing topology to board channel capacities
    and accumulates the ``AlgebraicPath`` for each wire in the bundle. Each
    wire's concrete lane index is resolved from its insertion position and the
    per-hop ``LaneSense`` carried by the topology.

    Attributes:
        topology: Named routing topology used to produce each path.
        channelLaneCounts: Board lane capacities keyed by legacy channel name.
        kernel_wiring: Upstream source-to-sink wire descriptions in insertion
            order.

    Examples:
        WTE intra forward bundle::

            wteIntra.wire_add(
                source="App.ts.main().s1",
                sink="Proxy.ts.p1().s1",
            )
            wteIntra.wire_add(
                source="App.ts.main().s2",
                sink="Proxy.ts.p1().s2",
            )
            laneMap = wteIntra.laneMap_get(0)
    """

    topology: PathSolutionBuilder
    channelLaneCounts: dict[str, int] = field(default_factory=dict)
    kernel_wiring: list[str] = field(default_factory=list)
    _paths: list[AlgebraicPath] = field(default_factory=list)
    _laneCount: int = 0

    def channelLaneCounts_set(
        self,
        channelLaneCounts: dict[str, int],
    ) -> WiringSolution:
        """Set per-channel lane capacities for concrete lane assignment.

        Args:
            channelLaneCounts: Mapping from legacy channel name token such as
                ``"eLong"`` to board lane capacity for that channel.

        Returns:
            This solution, for optional fluent chaining.
        """

        self.channelLaneCounts = dict(channelLaneCounts)
        return self

    def wire_add(self, source: str, sink: str) -> WiringSolution:
        """Resolve and append one wire to the bundle.

        Args:
            source: Canonical source chip terminal identifier.
            sink: Canonical sink chip terminal identifier.

        Returns:
            This solution, for optional fluent chaining.
        """

        self._paths.append(self.topology.resolve(source=source, sink=sink))
        self.kernel_wiring.append(f"{source} -> {sink}")
        self._laneCount += 1
        return self

    def paths_get(self) -> tuple[AlgebraicPath, ...]:
        """Return all paths in their insertion order.

        Returns:
            Ordered ``AlgebraicPath`` instances for this bundle.
        """

        return tuple(self._paths)

    def laneCount_get(self) -> int:
        """Return the explicit number of wires added to this bundle."""

        return self._laneCount

    def laneMap_get(self, wireIndex: int) -> dict[sfN, int]:
        """Return concrete per-channel lane indices for one wire.

        Args:
            wireIndex: Zero-based insertion position of the wire in this
                bundle.

        Returns:
            Mapping from routing-channel sfN member to its concrete lane
            number for the requested wire.
        """

        result: dict[sfN, int] = {}
        for hop in self.topology.topology_get():
            if hop.laneSense is LaneSense.FIXED:
                continue
            if hop.laneSense is LaneSense.FORWARD:
                result[hop.area] = wireIndex + 1
                continue
            channelName = hop.area.channel_name
            capacity = (
                self.channelLaneCounts.get(channelName, self._laneCount)
                if channelName is not None
                else self._laneCount
            )
            result[hop.area] = capacity - wireIndex
        return result


#: Default named topology for the WTE intra forward solution.
WTE_INTRA_FORWARD: PathSolutionBuilder = PathSolutionBuilder(
    "wte_intra_forward"
).hops_set(
    PathHop(sfN.Wfi),
    PathHop(sfN.Wi, LaneSense.FORWARD),
    PathHop(sfN.Ni, LaneSense.FORWARD),
    PathHop(sfN.Ei, LaneSense.REVERSE),
    PathHop(sfN.Efi),
)

#: Default named topology for the WTE intra return solution.
WTE_INTRA_RETURN: PathSolutionBuilder = PathSolutionBuilder(
    "wte_intra_return"
).hops_set(
    PathHop(sfN.Efi),
    PathHop(sfN.Ei, LaneSense.FORWARD),
    PathHop(sfN.Si, LaneSense.REVERSE),
    PathHop(sfN.Wi, LaneSense.REVERSE),
    PathHop(sfN.Wfi),
)


WTE_OUTER_EASTBOUND_ARC: PathSolutionBuilder = PathSolutionBuilder(
    "wte_outer_eastbound_arc"
).hops_set(
    PathHop(sfN.Wfe),
    PathHop(sfN.We, LaneSense.FORWARD),
    PathHop(sfN.Se, LaneSense.FORWARD),
    PathHop(sfN.Ee, LaneSense.REVERSE),
    PathHop(sfN.Efe),
)


WTE_OUTER_WESTBOUND_ARC: PathSolutionBuilder = PathSolutionBuilder(
    "wte_outer_westbound_arc"
).hops_set(
    PathHop(sfN.Efe),
    PathHop(sfN.Ee, LaneSense.FORWARD),
    PathHop(sfN.Ne, LaneSense.FORWARD),
    PathHop(sfN.We, LaneSense.REVERSE),
    PathHop(sfN.Wfe),
)


#: Et→Et same-side U-turn via east medial longitude: Efe → Ee → Ne → Em → Efi.
WTE_OUTER_EASTSIGNAL_UTURN: PathSolutionBuilder = PathSolutionBuilder(
    "wte_outer_eastsignal_uturn"
).hops_set(
    PathHop(sfN.Efe),
    PathHop(sfN.Ee, LaneSense.FORWARD),
    PathHop(sfN.Ne, LaneSense.FORWARD),
    PathHop(sfN.Em, LaneSense.FORWARD),
    PathHop(sfN.Efi),
)

#: Et→Et same-side U-turn via east medial longitude: Efe → Ee → Ne → Em → Efi.
WTE_OUTER_EASTRETURN_UTURN: PathSolutionBuilder = PathSolutionBuilder(
    "wte_outer_eastreturn_uturn"
).hops_set(
    PathHop(sfN.Efi),
    PathHop(sfN.Em, LaneSense.FORWARD),
    PathHop(sfN.Se, LaneSense.FORWARD),
    PathHop(sfN.Ee, LaneSense.FORWARD),
    PathHop(sfN.Efe),
)


#: Wt→Wt same-side U-turn via west medial longitude: Wfi → Wm → Ne → We → Wfe.
WTE_OUTER_WESTSIGNAL_UTURN: PathSolutionBuilder = PathSolutionBuilder(
    "wte_outer_westsignal_uturn"
).hops_set(
    PathHop(sfN.Wfi),
    PathHop(sfN.Wm, LaneSense.FORWARD),
    PathHop(sfN.Ne, LaneSense.FORWARD),
    PathHop(sfN.We, LaneSense.FORWARD),
    PathHop(sfN.Wfe),
)

#: Wt→Wt same-side U-turn via west medial longitude: Wfi → Wm → Ne → We → Wfe.
WTE_OUTER_WESTRETURN_UTURN: PathSolutionBuilder = PathSolutionBuilder(
    "wte_outer_westreturn_uturn"
).hops_set(
    PathHop(sfN.Wfe),
    PathHop(sfN.We, LaneSense.FORWARD),
    PathHop(sfN.Se, LaneSense.FORWARD),
    PathHop(sfN.Wm, LaneSense.FORWARD),
    PathHop(sfN.Wfi),
)
