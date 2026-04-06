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
    RoutingLaneAttachmentSense,
    RoutingZoneChannelSense,
)
from signalflow.notation import (
    WTE_INTRA_FORWARD,
    WTE_INTRA_RETURN,
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
    PathHop(sfN.Ni, LaneSense.FORWARD),
    PathHop(sfN.Wi, LaneSense.FORWARD),
    PathHop(sfN.Wfi),
)


@dataclass(frozen=True)
class SolverWireInput:
    """Minimal board-local algebraic solve input for one directed wire."""

    sourceEndpointText: str
    destinationEndpointText: str
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
        return f"<unsupported algebraic solve: unknown rotationSense {rotationSense}>"
    if laneFillSense not in {
        RoutingLaneAttachmentSense.FROM_START,
        RoutingLaneAttachmentSense.FROM_END,
    }:
        return f"<unsupported algebraic solve: unknown laneFillSense {laneFillSense}>"
    if board.side not in {"intra", "internal"}:
        return (
            "<unsupported algebraic solve: only intra/internal kernel quarantine "
            "solve is implemented>"
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

    forwardWires = tuple(
        candidate for candidate in allWires if not candidate.isReturn
    )
    returnWires = tuple(
        candidate for candidate in allWires if candidate.isReturn
    )
    forwardTopology, returnTopology = _topologies_get(rotationSense)
    forwardWiringSolution = WiringSolution(
        topology=forwardTopology,
        channelLaneCounts=laneCounts,
    )
    returnWiringSolution = WiringSolution(
        topology=returnTopology,
        channelLaneCounts=laneCounts,
    )

    if laneFillSense is RoutingLaneAttachmentSense.FROM_END:
        forwardInsertionOrder = tuple(reversed(range(len(forwardWires))))
    else:
        forwardInsertionOrder = tuple(range(len(forwardWires)))
    forwardWireIndexByShellIndex: dict[int, int] = {}
    for wireIndex, shellIndex in enumerate(forwardInsertionOrder):
        candidate = forwardWires[shellIndex]
        forwardWiringSolution.wire_add(
            source=candidate.sourceEndpointText,
            sink=candidate.destinationEndpointText,
        )
        forwardWireIndexByShellIndex[shellIndex] = wireIndex

    returnWireIndexByShellIndex = {
        shellIndex: shellIndex for shellIndex in range(len(returnWires))
    }
    for candidate in returnWires:
        returnWiringSolution.wire_add(
            source=candidate.sourceEndpointText,
            sink=candidate.destinationEndpointText,
        )

    if not wire.isReturn:
        wireIndex = forwardWireIndexByShellIndex[forwardWires.index(wire)]
        laneMap = forwardWiringSolution.laneMap_get(wireIndex)
        if (
            laneMap.get(sfN.Wi, 0) > wLongCount
            or laneMap.get(sfN.Wi, 0) < 1
            or laneMap.get(sfN.Ei, 0) < 1
            or laneMap.get(sfN.Ei, 0) > eLongCount
            or (
                rotationSense is RoutingZoneChannelSense.CLOCKWISE
                and (
                    laneMap.get(sfN.Ni, 0) > nLatCount
                    or laneMap.get(sfN.Ni, 0) < 1
                )
            )
            or (
                rotationSense is RoutingZoneChannelSense.ANTICLOCKWISE
                and (
                    laneMap.get(sfN.Si, 0) > sLatCount
                    or laneMap.get(sfN.Si, 0) < 1
                )
            )
        ):
            return "<unsupported algebraic solve: forward shell exceeds board>"
        return _algebraicPathText_build(
            algebraicPath=forwardWiringSolution.paths_get()[wireIndex],
            laneMap=laneMap,
            laneBaseByArea={},
        )

    wireIndex = returnWireIndexByShellIndex[returnWires.index(wire)]
    laneMap = returnWiringSolution.laneMap_get(wireIndex)
    latitudeMember = (
        sfN.Si
        if rotationSense is RoutingZoneChannelSense.CLOCKWISE
        else sfN.Ni
    )
    laneBaseByArea: dict[sfN, int]
    if laneFillSense is RoutingLaneAttachmentSense.FROM_START:
        laneBaseByArea = {
            latitudeMember: len(forwardWires),
            sfN.Wi: len(forwardWires),
        }
    else:
        laneBaseByArea = {
            sfN.Ei: eLongCount - len(returnWires),
            latitudeMember: wLongCount - len(returnWires),
            sfN.Wi: wLongCount - len(returnWires),
        }
    shellLaneIndex = laneMap.get(latitudeMember, 0) + laneBaseByArea.get(
        latitudeMember, 0
    )
    eastLaneIndex = laneMap.get(sfN.Ei, 0) + laneBaseByArea.get(sfN.Ei, 0)
    latitudeLaneCount = (
        sLatCount
        if rotationSense is RoutingZoneChannelSense.CLOCKWISE
        else nLatCount
    )
    if (
        shellLaneIndex > wLongCount
        or shellLaneIndex < 1
        or eastLaneIndex > eLongCount
        or shellLaneIndex > latitudeLaneCount
    ):
        return "<unsupported algebraic solve: return shell exceeds board>"
    return _algebraicPathText_build(
        algebraicPath=returnWiringSolution.paths_get()[wireIndex],
        laneMap=laneMap,
        laneBaseByArea=laneBaseByArea,
    )


def _topologies_get(
    rotationSense: RoutingZoneChannelSense,
) -> tuple[PathSolutionBuilder, PathSolutionBuilder]:
    """Return forward and return WTE topologies for the given rotation."""

    if rotationSense is RoutingZoneChannelSense.CLOCKWISE:
        return (WTE_INTRA_FORWARD, WTE_INTRA_RETURN)
    return (
        _WTE_INTRA_ANTICLOCKWISE_FORWARD,
        _WTE_INTRA_ANTICLOCKWISE_RETURN,
    )


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
