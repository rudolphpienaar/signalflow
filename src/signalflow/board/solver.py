"""Board-domain algebraic solve helpers.

This module is intentionally narrow. It does not own global routing search. It
owns the board-local algebraic path mapping for the quarantine symbolic REPL
surface so that lane counts and board sense come from the first-class board
model rather than the legacy kernel region set.
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.board import Board
from signalflow.models import (
    ChipTerminalSide,
    RoutingLaneAttachmentSense,
    RoutingZoneChannelSense,
    ZoneLocalGeometryKind,
)
from signalflow.notation import (
    WTE_INTRA_FORWARD,
    WTE_INTRA_RETURN,
    WTE_OUTER_EASTBOUND_ARC,
    WTE_OUTER_EASTSIDE_UTURN,
    WTE_OUTER_WESTBOUND_ARC,
    WTE_OUTER_WESTSIDE_UTURN,
    AlgebraicPath,
    LaneSense,
    PathHop,
    PathSolutionBuilder,
    WiringSolution,
    sfN,
)

_WTE_INTRA_ANTICLOCKWISE_FORWARD: PathSolutionBuilder = PathSolutionBuilder(
    "wte_intra_anticlockwise_forward"
).hops_set(
    PathHop(sfN.Wfi),
    PathHop(sfN.Wi, LaneSense.FORWARD),
    PathHop(sfN.Si, LaneSense.FORWARD),
    PathHop(sfN.Ei, LaneSense.FORWARD),
    PathHop(sfN.Efi),
)

_WTE_INTRA_ANTICLOCKWISE_RETURN: PathSolutionBuilder = PathSolutionBuilder(
    "wte_intra_anticlockwise_return"
).hops_set(
    PathHop(sfN.Efi),
    PathHop(sfN.Ei, LaneSense.FORWARD),
    PathHop(sfN.Ni, LaneSense.REVERSE),
    PathHop(sfN.Wi, LaneSense.REVERSE),
    PathHop(sfN.Wfi),
)


@dataclass(frozen=True)
class SolverWireInput:
    """Minimal board-local algebraic solve input for one directed wire."""

    sourceEndpointText: str
    destinationEndpointText: str
    sourceTerminalSide: ChipTerminalSide
    zoneLocalGeometryKind: ZoneLocalGeometryKind | None
    callingStackDelta: int | None
    isReturn: bool


def boardChannelLaneCounts_build(board: Board) -> dict[str, int]:
    """Return symbolic channel lane counts derived from board geometry."""

    regionFramesByName = board.geometry.regionFramesByName
    laneCounts: dict[str, int] = {}
    _longitudeMembers = {sfN.Wi, sfN.Ei, sfN.We, sfN.Ee}
    _latitudeMembers = {sfN.Ni, sfN.Si, sfN.Ne, sfN.Se}
    for regionName, frame in regionFramesByName.items():
        baseKey = regionName.split(":")[
            0
        ]  # strip :upper / :lower subdivision suffix
        member = sfN.from_region_key(baseKey)
        if member is None or member.channel_name is None:
            continue
        channelName = member.channel_name
        if member in _longitudeMembers:
            laneCounts[channelName] = max(
                laneCounts.get(channelName, 0), frame.horizontalSpan
            )
        elif member in _latitudeMembers:
            laneCounts[channelName] = max(
                laneCounts.get(channelName, 0), frame.verticalSpan
            )
    return laneCounts


def boardChannelLaneCounts_buildBySfN(board: Board) -> dict[sfN, int]:
    """Return channel lane counts keyed by sfN member.

    Equivalent to ``boardChannelLaneCounts_build`` but keyed by ``sfN``
    instead of string channel name.
    """

    strCounts = boardChannelLaneCounts_build(board)
    result: dict[sfN, int] = {}
    for channelName, count in strCounts.items():
        member = sfN.from_channel_name(channelName)
        if member is not None:
            result[member] = count
    return result


def boardWireAlgebraicPath_build(
    *,
    board: Board,
    allWires: tuple[SolverWireInput, ...],
    wire: SolverWireInput,
    rotationSense: RoutingZoneChannelSense,
    laneFillSense: RoutingLaneAttachmentSense,
) -> str:
    """Build one board-local algebraic path from board geometry and policy."""

    if rotationSense not in {
        RoutingZoneChannelSense.CLOCKWISE,
        RoutingZoneChannelSense.ANTICLOCKWISE,
    }:
        return (
            "<unsupported algebraic solve: unknown rotationSense "
            f"{rotationSense}>"
        )
    if laneFillSense not in {
        RoutingLaneAttachmentSense.FROM_START,
        RoutingLaneAttachmentSense.FROM_END,
    }:
        return (
            "<unsupported algebraic solve: unknown laneFillSense "
            f"{laneFillSense}>"
        )
    if board.side not in {"intra", "internal"}:
        return (
            "<unsupported algebraic solve: only intra/internal "
            "kernel quarantine solve is implemented>"
        )
    if board.doctrine.sense.value != "WTE":
        return (
            "<unsupported algebraic solve: only west_to_east intra kernel "
            "quarantine solve is implemented>"
        )

    laneCounts = boardChannelLaneCounts_build(board)
    wLongCount = laneCounts.get("wLong")
    nLatCount = laneCounts.get("nLat")
    eLongCount = laneCounts.get("eLong")
    sLatCount = laneCounts.get("sLat")
    if (
        wLongCount is None
        or nLatCount is None
        or eLongCount is None
        or sLatCount is None
    ):
        return (
            "<unsupported algebraic solve: expected intra WTE channels absent>"
        )

    solutionByWire: dict[int, tuple[WiringSolution, int]] = (
        _wiringSolutionByWireIndex_build(
            allWires=allWires,
            laneCounts=laneCounts,
            rotationSense=rotationSense,
            laneFillSense=laneFillSense,
        )
    )
    wireGlobalIndex: int = allWires.index(wire)
    matched = solutionByWire.get(wireGlobalIndex)
    if matched is None:
        return "<unsupported algebraic solve: wire topology selection failed>"
    wiringSolution, wireIndex = matched
    laneMap = wiringSolution.laneMap_get(wireIndex)
    return _algebraicPathText_build(
        algebraicPath=wiringSolution.paths_get()[wireIndex],
        laneMap=laneMap,
        laneBaseByArea={},
    )


def wireTopology_build(
    wire: SolverWireInput,
    rotationSense: RoutingZoneChannelSense,
) -> PathSolutionBuilder:
    """Return the selected WTE topology for one wire.

    Args:
        wire: Directed wire plus semantic topology metadata.
        rotationSense: Active intra rotation policy for fallback selection.

    Returns:
        Selected path-solution builder for this wire.
    """

    zoneLocalGeometryKind: ZoneLocalGeometryKind | None = (
        wire.zoneLocalGeometryKind
    )
    if zoneLocalGeometryKind is ZoneLocalGeometryKind.OUTER_CHILD_TOPARENT:
        if wire.callingStackDelta is not None and wire.callingStackDelta < 0:
            return WTE_OUTER_WESTBOUND_ARC
        if wire.callingStackDelta is not None and wire.callingStackDelta > 0:
            return WTE_OUTER_EASTBOUND_ARC
        if wire.isReturn:
            return WTE_OUTER_WESTBOUND_ARC
        return WTE_OUTER_EASTBOUND_ARC
    if zoneLocalGeometryKind is ZoneLocalGeometryKind.OUTER_CHILD_UTURN:
        if wire.isReturn:
            return WTE_OUTER_WESTSIDE_UTURN
        return WTE_OUTER_EASTSIDE_UTURN
    if zoneLocalGeometryKind is ZoneLocalGeometryKind.OUTER_PARENT_UTURN:
        if wire.isReturn:
            return WTE_OUTER_EASTSIDE_UTURN
        return WTE_OUTER_WESTSIDE_UTURN

    if rotationSense is RoutingZoneChannelSense.CLOCKWISE:
        if wire.isReturn:
            return WTE_INTRA_RETURN
        return WTE_INTRA_FORWARD
    if wire.isReturn:
        return _WTE_INTRA_ANTICLOCKWISE_RETURN
    return _WTE_INTRA_ANTICLOCKWISE_FORWARD


def _wiringSolutionByWireIndex_build(
    *,
    allWires: tuple[SolverWireInput, ...],
    laneCounts: dict[str, int],
    rotationSense: RoutingZoneChannelSense,
    laneFillSense: RoutingLaneAttachmentSense,
) -> dict[int, tuple[WiringSolution, int]]:
    """Build grouped wiring solutions keyed by original wire index."""

    wireIndicesByTopologyName: dict[str, list[int]] = {}
    topologyByName: dict[str, PathSolutionBuilder] = {}
    wireIndex: int
    wire: SolverWireInput
    for wireIndex, wire in enumerate(allWires):
        topology: PathSolutionBuilder = wireTopology_build(
            wire=wire,
            rotationSense=rotationSense,
        )
        topologyName: str = topology.name_get()
        wireIndicesByTopologyName.setdefault(
            topologyName, []
        ).append(wireIndex)
        topologyByName[topologyName] = topology

    solutionByWireIndex: dict[int, tuple[WiringSolution, int]] = {}
    topologyName: str
    for topologyName, wireIndices in wireIndicesByTopologyName.items():
        wiringSolution = WiringSolution(
            topology=topologyByName[topologyName],
            channelLaneCounts=laneCounts,
        )
        insertionOrder: tuple[int, ...]
        if laneFillSense is RoutingLaneAttachmentSense.FROM_END:
            insertionOrder = tuple(reversed(wireIndices))
        else:
            insertionOrder = tuple(wireIndices)
        localWireIndex: int
        originalWireIndex: int
        for localWireIndex, originalWireIndex in enumerate(insertionOrder):
            wire = allWires[originalWireIndex]
            wiringSolution.wire_add(
                source=wire.sourceEndpointText,
                sink=wire.destinationEndpointText,
            )
            solutionByWireIndex[originalWireIndex] = (
                wiringSolution,
                localWireIndex,
            )
    return solutionByWireIndex


def _algebraicPathText_build(
    *,
    algebraicPath: AlgebraicPath,
    laneMap: dict[sfN, int],
    laneBaseByArea: dict[sfN, int],
) -> str:
    """Serialize one structured path plus lane state to compatibility text."""

    parts: list[str] = [algebraicPath.source]
    for hop in algebraicPath.hops:
        token = hop.area.channel_name or ""
        if hop.laneSense is LaneSense.FIXED:
            parts.append(f"{token}[0]")
            continue
        laneIndex = laneMap.get(hop.area, 0) + laneBaseByArea.get(hop.area, 0)
        parts.append(f"{token}[{laneIndex}]")
    parts.append(algebraicPath.sink)
    return "::".join(parts)
