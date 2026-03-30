"""Board-domain algebraic solve helpers.

This module is intentionally narrow. It does not own global routing search. It
owns the board-local algebraic path mapping for the quarantine symbolic REPL
surface so that lane counts and board sense come from the first-class board
model rather than the legacy kernel region set.
"""
from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.board import Board
from signalflow.models import RoutingLaneAttachmentSense, RoutingZoneChannelSense


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
    for regionName, frame in regionFramesByName.items():
        if (
            regionName.endswith("intra_routing_longitude:upper")
            or regionName.endswith("intra_routing_longitude:lower")
            or regionName.endswith("intra_routing_longitude")
            or regionName.endswith("inter_routing_longitude")
        ):
            prefix = regionName.split("/", 1)[0]
            laneCounts[f"{prefix[0]}Long"] = max(
                laneCounts.get(f"{prefix[0]}Long", 0),
                frame.horizontalSpan,
            )
            continue
        if regionName.endswith("intra_routing_latitude") or regionName.endswith(
            "inter_routing_latitude"
        ):
            prefix = regionName.split("/", 1)[0]
            laneCounts[f"{prefix[0]}Lat"] = max(
                laneCounts.get(f"{prefix[0]}Lat", 0),
                frame.verticalSpan,
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
        return "<unsupported algebraic solve: expected intra WTE channels absent>"

    forwardWires = tuple(candidate for candidate in allWires if not candidate.isReturn)
    returnWires = tuple(candidate for candidate in allWires if candidate.isReturn)
    forwardLaneBase = (
        1 if laneFillSense is RoutingLaneAttachmentSense.FROM_START else len(forwardWires)
    )
    forwardLaneStep = 1 if laneFillSense is RoutingLaneAttachmentSense.FROM_START else -1

    if not wire.isReturn:
        forwardShellIndex = forwardWires.index(wire)
        forwardIndex = forwardLaneBase + forwardLaneStep * forwardShellIndex
        if rotationSense is RoutingZoneChannelSense.CLOCKWISE:
            latitudeChannelName = "nLat"
            latitudeLaneIndex = forwardIndex
            eastLaneIndex = eLongCount - forwardIndex + 1
            latitudeLaneCount = nLatCount
        else:
            latitudeChannelName = "sLat"
            latitudeLaneIndex = forwardIndex
            eastLaneIndex = forwardIndex
            latitudeLaneCount = sLatCount
        if (
            forwardIndex > wLongCount
            or forwardIndex < 1
            or latitudeLaneIndex > latitudeLaneCount
            or latitudeLaneIndex < 1
            or eastLaneIndex < 1
            or eastLaneIndex > eLongCount
        ):
            return "<unsupported algebraic solve: forward shell exceeds board>"
        return (
            f"{wire.sourceEndpointText}::wf[0]::wLong[{forwardIndex}]::"
            f"{latitudeChannelName}[{latitudeLaneIndex}]::"
            f"eLong[{eastLaneIndex}]::ef[0]::"
            f"{wire.destinationEndpointText}"
        )

    returnShellIndex = returnWires.index(wire)
    if laneFillSense is RoutingLaneAttachmentSense.FROM_START:
        shellLaneIndex = len(forwardWires) + returnShellIndex + 1
        eastLaneIndex = returnShellIndex + 1
    else:
        shellLaneIndex = wLongCount - len(returnWires) + returnShellIndex + 1
        eastLaneIndex = eLongCount - len(returnWires) + returnShellIndex + 1
    latitudeChannelName = (
        "sLat" if rotationSense is RoutingZoneChannelSense.CLOCKWISE else "nLat"
    )
    latitudeLaneCount = (
        sLatCount if rotationSense is RoutingZoneChannelSense.CLOCKWISE else nLatCount
    )
    if (
        shellLaneIndex > wLongCount
        or shellLaneIndex < 1
        or eastLaneIndex > eLongCount
        or shellLaneIndex > latitudeLaneCount
    ):
        return "<unsupported algebraic solve: return shell exceeds board>"
    return (
        f"{wire.sourceEndpointText}::ef[0]::eLong[{eastLaneIndex}]::"
        f"{latitudeChannelName}[{shellLaneIndex}]::"
        f"wLong[{shellLaneIndex}]::wf[0]::"
        f"{wire.destinationEndpointText}"
    )
