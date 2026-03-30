"""Runtime channel objects derived from canonical board geometry.

This module exposes the operator-facing lane and channel vocabulary used by the
quarantine board runtime surface. The objects here are thin runtime wrappers
over lane counts already implied by `BoardGeometry`; they do not perform solve
or render work themselves.

Key components:
    - BoardLane: One concrete lane inside a symbolic board channel
    - BoardLanes: Collection of lanes exposed by one channel
    - BoardChannel: One named symbolic channel with a lane count
    - BoardChannels: Ordered channel collection derived from one board

Typical usage:
    board = kernel.board_get()
    channels = board.channels_get()
    north = channels.channel_get("nLat")
    lanes = north.lanes_get() if north is not None else None

Dependencies:
    - Requires `Board` from `signalflow.board.board`
    - Derives lane counts through `boardChannelLaneCounts_build`
"""
from __future__ import annotations

from dataclasses import dataclass

from signalflow.board.board import Board
from signalflow.board.solver import boardChannelLaneCounts_build


@dataclass(frozen=True)
class BoardLane:
    """One resolved lane inside one symbolic board channel.

    Attributes:
        channelName: Canonical symbolic channel name such as `nLat`.
        laneIndex: One-based lane index inside that channel.
    """

    channelName: str
    laneIndex: int

    def canonicalName_get(self) -> str:
        """Return the canonical `channel[index]` text for this lane.

        Returns:
            Canonical lane text such as `nLat[3]`.
        """

        return f"{self.channelName}[{self.laneIndex}]"

    def index_get(self) -> int:
        """Return the one-based index of this lane.

        Returns:
            One-based lane index inside the owning channel.
        """

        return self.laneIndex


@dataclass(frozen=True)
class BoardLanes:
    """Collection of lanes exposed by one symbolic board channel.

    Attributes:
        channelName: Canonical symbolic channel name shared by all lanes here.
        laneCount: Number of lanes currently exposed by the channel.
    """

    channelName: str
    laneCount: int

    def all_get(self) -> tuple[BoardLane, ...]:
        """Return all lanes in ascending one-based index order.

        Returns:
            Tuple of `BoardLane` objects from index `1` through `laneCount`.
        """

        return tuple(
            BoardLane(channelName=self.channelName, laneIndex=laneIndex)
            for laneIndex in range(1, self.laneCount + 1)
        )

    def count_get(self) -> int:
        """Return the number of lanes in this channel.

        Returns:
            Lane count for the owning channel.
        """

        return self.laneCount

    def lane_get(self, laneIndex: int) -> BoardLane | None:
        """Return one lane by one-based index when it exists.

        Args:
            laneIndex: One-based lane index to retrieve.

        Returns:
            Matching `BoardLane` when the index is valid, otherwise `None`.
        """

        if laneIndex < 1 or laneIndex > self.laneCount:
            return None
        return BoardLane(channelName=self.channelName, laneIndex=laneIndex)

    def list_text(self) -> str:
        """Return one canonical lane name per line.

        Returns:
            Multi-line text containing one lane name per line.
        """

        return "\n".join(lane.canonicalName_get() for lane in self.all_get())


@dataclass(frozen=True)
class BoardChannel:
    """One symbolic channel visible on a board.

    Attributes:
        channelName: Canonical channel name such as `wLong` or `nLat`.
        laneCount: Number of lanes currently exposed by this channel.
    """

    channelName: str
    laneCount: int

    def lanes_get(self) -> BoardLanes:
        """Return the lane collection for this channel.

        Returns:
            `BoardLanes` collection representing this channel's lanes.
        """

        return BoardLanes(channelName=self.channelName, laneCount=self.laneCount)

    def name_get(self) -> str:
        """Return the canonical channel name.

        Returns:
            Stable symbolic channel name.
        """

        return self.channelName

    def summary_text(self) -> str:
        """Return a concise summary of this channel and its lane count.

        Returns:
            Human-readable summary such as `nLat (10 lanes)`.
        """

        return f"{self.channelName} ({self.laneCount} lanes)"


@dataclass(frozen=True)
class BoardChannels:
    """Collection of symbolic channels derived from one board.

    Attributes:
        _channelsByName: Ordered mapping from canonical channel name to runtime
            channel object.

    Example:
        >>> channels = BoardChannels.build(board)
        >>> channels.channel_get("wLong").summary_text()
        'wLong (10 lanes)'
    """

    _channelsByName: dict[str, BoardChannel]

    @classmethod
    def build(cls, board: Board) -> BoardChannels:
        """Build the ordered channel collection for one board.

        Args:
            board: Board whose geometry defines the available channel lanes.

        Returns:
            `BoardChannels` ordered for stable operator display.
        """

        laneCountByChannelName = boardChannelLaneCounts_build(board)
        preferredChannelOrder: tuple[str, ...] = (
            "wLong",
            "nLat",
            "eLong",
            "sLat",
            "wLat",
            "nLong",
            "eLat",
            "sLong",
        )
        orderedChannelsByName: dict[str, BoardChannel] = {}
        for channelName in preferredChannelOrder:
            laneCount = laneCountByChannelName.get(channelName)
            if laneCount is None:
                continue
            orderedChannelsByName[channelName] = BoardChannel(
                channelName=channelName,
                laneCount=laneCount,
            )
        for channelName in sorted(laneCountByChannelName):
            if channelName in orderedChannelsByName:
                continue
            orderedChannelsByName[channelName] = BoardChannel(
                channelName=channelName,
                laneCount=laneCountByChannelName[channelName],
            )
        return cls(_channelsByName=orderedChannelsByName)

    def all_get(self) -> tuple[BoardChannel, ...]:
        """Return all channels in stable display order.

        Returns:
            Tuple of all runtime channels owned by this collection.
        """

        return tuple(self._channelsByName.values())

    def channel_get(self, channelName: str) -> BoardChannel | None:
        """Return one channel by canonical name when present.

        Args:
            channelName: Canonical channel name such as `eLong`.

        Returns:
            Matching `BoardChannel` when present, otherwise `None`.
        """

        return self._channelsByName.get(channelName)

    def list_text(self) -> str:
        """Return one channel summary per line.

        Returns:
            Multi-line text containing one channel summary per line.
        """

        return "\n".join(channel.summary_text() for channel in self.all_get())
