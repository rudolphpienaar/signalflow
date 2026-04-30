"""Lightweight debug handle/data wrappers shared across debug surfaces."""

from __future__ import annotations

from collections.abc import ItemsView, Iterator, KeysView, ValuesView
from dataclasses import dataclass

from signalflow.board import Board as DomainBoard
from signalflow.board import boardProblems_get
from signalflow.board.geometry import regionByName_get
from signalflow.board.types import BoardSense, WorldFrame, WorldPoint
from signalflow.models import (
    ChipRef,
    ChipTerminalSide,
    GridCoord,
    RoutingZoneId,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
)


@dataclass(frozen=True)
class ZoneRegionHandle:
    """Interactive handle for one region inside a placed routing zone."""

    routingZoneRegionId: RoutingZoneRegionId
    routingZoneRegionFrame: RoutingZoneRegionFrame

    def __dir__(self) -> list[str]:
        return ["kind", "side", "name", "frame"]

    def __repr__(self) -> str:
        frame = self.routingZoneRegionFrame
        return (
            f"<area {self.name}"
            f"  col={frame.horizontalStart}..{frame.horizontalEnd_calculate()}"
            f"  row={frame.verticalStart}..{frame.verticalEnd_calculate()}>"
        )

    @property
    def kind(self) -> str:
        return self.routingZoneRegionId.routingZoneRegionKind.value

    @property
    def side(self) -> str | None:
        side = self.routingZoneRegionId.routingZoneRegionSide
        return side.value if side is not None else None

    @property
    def name(self) -> str:
        return f"{self.side}/{self.kind}" if self.side else self.kind

    @property
    def _tagged_name(self) -> str:
        baseName = self.name
        tag = self.routingZoneRegionId.routingZoneRegionTag
        return f"{baseName}:{tag}" if tag else baseName

    @property
    def frame(self) -> str:
        frame = self.routingZoneRegionFrame
        return (
            f"col={frame.horizontalStart}..{frame.horizontalEnd_calculate()}"
            f"  row={frame.verticalStart}..{frame.verticalEnd_calculate()}"
            f"  span=({frame.horizontalSpan}w x {frame.verticalSpan}h)"
        )

    @property
    def _geometry(self) -> RoutingZoneRegionFrame:
        return self.routingZoneRegionFrame


@dataclass(frozen=True)
class ZoneRegionSetHandle:
    """Interactive handle for the full set of regions in one placed zone."""

    _regions: tuple[ZoneRegionHandle, ...]

    def __dir__(self) -> list[str]:
        return ["all_get", "area_get", "grid_text", "info_text", "names_get"]

    def __repr__(self) -> str:
        return f"<zone.areas  {len(self._regions)} regions>"

    def __iter__(self) -> Iterator[ZoneRegionHandle]:
        return iter(self._regions)

    def __len__(self) -> int:
        return len(self._regions)

    def all_get(self) -> tuple[ZoneRegionHandle, ...]:
        return self._regions

    def area_get(
        self, kindOrKey: str, side: str | None = None
    ) -> ZoneRegionHandle | None:
        taggedName = kindOrKey
        for handle in self._regions:
            if handle._tagged_name == taggedName:
                return handle
        return regionByName_get(
            {handle._tagged_name: handle for handle in self._regions},
            kindOrKey,
            side,
        )

    def names_get(self) -> tuple[str, ...]:
        return tuple(handle.name for handle in self._regions)

    def info_sprint(self) -> str:
        lines: list[str] = []
        for handle in self._regions:
            lines.append(f"  {handle.name}")
            lines.append(f"    kind     : {handle.kind}")
            lines.append(f"    side     : {handle.side}")
            lines.append(f"    frame    : {handle.frame}")
            lines.append(f"    geometry : {handle._geometry}")
        return "\n".join(lines)

    def grid_sprint(
        self, mode: str = "pixel", columnOffset: int | None = None
    ) -> str:
        from .geometry import regionDrawGrid_build, regionSymbol_get

        regions = self._regions
        if not regions:
            return "<no regions>"
        labels = [regionSymbol_get(region.name) for region in regions]
        gridLines = regionDrawGrid_build(
            regions,
            labels,
            mode,
            columnOffset=columnOffset,
        )
        legendLines: list[str] = ["", "legend:"]
        for index, region in enumerate(regions):
            horizontalEndInclusive = (
                region.routingZoneRegionFrame.horizontalEnd_calculate() - 1
            )
            verticalEndInclusive = (
                region.routingZoneRegionFrame.verticalEnd_calculate() - 1
            )
            legendLines.append(
                "  "
                f"{labels[index]}   {region._tagged_name}  "
                "[col="
                f"{region.routingZoneRegionFrame.horizontalStart}.."
                f"{horizontalEndInclusive}  "
                "row="
                f"{region.routingZoneRegionFrame.verticalStart}.."
                f"{verticalEndInclusive}  "
                f"span=({region.routingZoneRegionFrame.horizontalSpan}w x "
                f"{region.routingZoneRegionFrame.verticalSpan}h)]"
            )
        return "\n".join(gridLines + legendLines)


@dataclass(frozen=True)
class ZoneAreaView:
    """Dictionary-like view over partitioned zone regions with draw support."""

    _kernel_map: dict[str, ZoneRegionSetHandle]

    def __dir__(self) -> list[str]:
        return list(self._kernel_map.keys()) + ["grid_text"]

    def __getitem__(self, key: str) -> ZoneRegionSetHandle:
        return self._kernel_map[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._kernel_map)

    def keys(self) -> KeysView[str]:
        return self._kernel_map.keys()

    def values(self) -> ValuesView[ZoneRegionSetHandle]:
        return self._kernel_map.values()

    def items(self) -> ItemsView[str, ZoneRegionSetHandle]:
        return self._kernel_map.items()

    def __repr__(self) -> str:
        return f"<partitioned-areas: {list(self._kernel_map.keys())}>"

    def grid_sprint(
        self, mode: str = "pixel", columnOffset: int | None = None
    ) -> str:
        all_regions = []
        for handle in self._kernel_map.values():
            all_regions.extend(handle._regions)
        return ZoneRegionSetHandle(_regions=tuple(all_regions)).grid_sprint(
            mode=mode,
            columnOffset=columnOffset,
        )


@dataclass(frozen=True)
class KernelWire:
    """One directed symbolic wire entry in a kernel wiring scope."""

    sourceEndpointText: str
    destinationEndpointText: str
    sourceChipRef: ChipRef
    destinationChipRef: ChipRef
    sourceTerminalName: str
    destinationTerminalName: str
    sourceTerminalSide: ChipTerminalSide
    destinationTerminalSide: ChipTerminalSide
    sourceDisplayEndpointText: str | None = None
    destinationDisplayEndpointText: str | None = None
    isReturn: bool = False

    @staticmethod
    def _endpointDisplayText_build(
        endpointText: str,
        displayEndpointText: str | None,
    ) -> str:
        """Build one endpoint text with explicit canonical id annotation."""

        if displayEndpointText is None:
            displayEndpointText = endpointText
        terminalId = endpointText.split(".")[-1]
        return f"{displayEndpointText} [id={terminalId}]"

    def wireText_get(self) -> str:
        sourceText = self._endpointDisplayText_build(
            self.sourceEndpointText,
            self.sourceDisplayEndpointText,
        )
        destinationText = self._endpointDisplayText_build(
            self.destinationEndpointText,
            self.destinationDisplayEndpointText,
        )
        return f"{sourceText}:{destinationText}"

    def __str__(self) -> str:
        return self.wireText_get()


@dataclass(frozen=True)
class KernelLaneHandle:
    channelName: str
    laneIndex: int

    def __dir__(self) -> list[str]:
        return ["canonicalName_get", "index_get"]

    def __repr__(self) -> str:
        return f"<lane {self.channelName}[{self.laneIndex}]>"

    def canonicalName_get(self) -> str:
        return f"{self.channelName}[{self.laneIndex}]"

    def index_get(self) -> int:
        return self.laneIndex


@dataclass(frozen=True)
class KernelLanesHandle:
    channelName: str
    laneCount: int

    def __dir__(self) -> list[str]:
        return ["all_get", "count_get", "lane_get", "list_text"]

    def __repr__(self) -> str:
        return f"<lanes {self.channelName} x{self.laneCount}>"

    def all_get(self) -> tuple[KernelLaneHandle, ...]:
        return tuple(
            KernelLaneHandle(channelName=self.channelName, laneIndex=laneIndex)
            for laneIndex in range(1, self.laneCount + 1)
        )

    def count_get(self) -> int:
        return self.laneCount

    def lane_get(self, laneIndex: int) -> KernelLaneHandle | None:
        if laneIndex < 1 or laneIndex > self.laneCount:
            return None
        return KernelLaneHandle(
            channelName=self.channelName, laneIndex=laneIndex
        )

    def list_sprint(self) -> str:
        return "\n".join(
            laneHandle.canonicalName_get() for laneHandle in self.all_get()
        )


@dataclass(frozen=True)
class KernelChannelHandle:
    channelName: str
    laneCount: int

    def __dir__(self) -> list[str]:
        return ["lanes_get", "name_get", "summary_text"]

    def __repr__(self) -> str:
        return f"<channel {self.channelName} x{self.laneCount}>"

    def lanes_get(self) -> KernelLanesHandle:
        return KernelLanesHandle(
            channelName=self.channelName, laneCount=self.laneCount
        )

    def name_get(self) -> str:
        return self.channelName

    def summary_sprint(self) -> str:
        return f"{self.channelName} ({self.laneCount} lanes)"


@dataclass(frozen=True)
class KernelChannelsHandle:
    _channelsByName: dict[str, KernelChannelHandle]

    def __dir__(self) -> list[str]:
        return ["all_get", "channel_get", "list_text"]

    def __repr__(self) -> str:
        return f"<channels {list(self._channelsByName.keys())}>"

    def all_get(self) -> tuple[KernelChannelHandle, ...]:
        return tuple(self._channelsByName.values())

    def channel_get(self, channelName: str) -> KernelChannelHandle | None:
        return self._channelsByName.get(channelName)

    def list_sprint(self) -> str:
        return "\n".join(
            channelHandle.summary_sprint() for channelHandle in self.all_get()
        )


@dataclass(frozen=True)
class KernelBoardHandle:
    """Inspectable symbolic board for one kernel scope."""

    routingZoneId: RoutingZoneId
    side: str
    boardBackend: str
    boardModel: DomainBoard
    channels: KernelChannelsHandle

    def __dir__(self) -> list[str]:
        return [
            "boundaries_get",
            "boundary_get",
            "backend_get",
            "channels_get",
            "effective_get",
            "geometry_get",
            "geometry_text",
            "minimumCrossbarSpan_get",
            "model_get",
            "problems_get",
            "sense_get",
            "substrate_get",
            "summary_text",
            "terminal_get",
            "terminals_get",
            "validation_text",
            "worldFrame_get",
            "worldGridCoord_get",
        ]

    def __repr__(self) -> str:
        return f"<board {self.side} of {self.routingZoneId.id}>"

    def channels_get(self) -> KernelChannelsHandle:
        return self.channels

    def backend_get(self) -> str:
        return self.boardBackend

    def model_get(self) -> DomainBoard:
        return self.boardModel

    def substrate_get(self) -> KernelBoardHandle:
        return KernelBoardHandle(
            routingZoneId=self.routingZoneId,
            side=self.side,
            boardBackend=self.boardBackend,
            boardModel=self.boardModel.substrate_get(),
            channels=self.channels,
        )

    def effective_get(self) -> KernelBoardHandle:
        if self.boardModel is self.boardModel.effective_get():
            return self
        return KernelBoardHandle(
            routingZoneId=self.routingZoneId,
            side=self.side,
            boardBackend=self.boardBackend,
            boardModel=self.boardModel.effective_get(),
            channels=self.channels,
        )

    def worldGridCoord_get(self) -> GridCoord:
        return self.boardModel.routingZoneId.id

    def worldFrame_get(self) -> WorldFrame:
        return self.boardModel.worldFrame_get()

    def sense_get(self) -> BoardSense:
        return self.boardModel.doctrine.sense

    def minimumCrossbarSpan_get(self) -> int:
        return self.boardModel.doctrine.minimumCrossbarSpan

    def boundaries_get(self) -> dict[str, RoutingZoneRegionFrame]:
        return dict(self.boardModel.geometry.effectiveBoundaryFramesByName)

    def boundary_get(self, boundaryName: str) -> RoutingZoneRegionFrame | None:
        return self.boardModel.geometry.effectiveBoundaryFrame_get(
            boundaryName
        )

    def terminals_get(self) -> dict[str, dict[str, WorldPoint]]:
        return {
            chipName: dict(terminalPositions)
            for chipName, terminalPositions in (
                self.boardModel.geometry.exactTerminalWorldPositionsByChip.items()
            )
        }

    def terminal_get(
        self, chipName: str, terminalName: str
    ) -> tuple[int, int] | None:
        return self.boardModel.geometry.exactTerminalWorldPosition_get(
            chipName, terminalName
        )

    def problems_get(self) -> tuple[str, ...]:
        return boardProblems_get(self.boardModel)

    def validation_sprint(self) -> str:
        problems = self.problems_get()
        if not problems:
            return "board validation:\n  <none>"
        return "board validation:\n" + "\n".join(
            f"  {problem}" for problem in problems
        )

    def geometry_get(self) -> ZoneRegionSetHandle:
        return ZoneRegionSetHandle(
            _regions=tuple(
                ZoneRegionHandle(
                    routingZoneRegionId=self.boardModel.geometry.regionIdsByName[
                        regionName
                    ],
                    routingZoneRegionFrame=regionFrame,
                )
                for regionName, regionFrame in (
                    self.boardModel.geometry.regionFramesByName.items()
                )
            )
        )

    def geometry_sprint(
        self, mode: str = "pixel", columnOffset: int | None = None
    ) -> str:
        if self.boardBackend == "legacy" or mode != "pixel":
            return self.geometry_get().grid_sprint(
                mode=mode, columnOffset=columnOffset
            )
        return self.boardModel.geometry_sprint(columnOffset=columnOffset)

    def summary_sprint(self) -> str:
        return "\n".join(
            [
                f"board {self.side} of {self.routingZoneId.id}",
                f"worldFrame {self.boardModel.worldFrame_get()}",
                self.channels.list_sprint(),
            ]
        )


DebugZoneRegionHandle = ZoneRegionHandle
DebugZoneRegionSetHandle = ZoneRegionSetHandle
DebugZoneAreaView = ZoneAreaView
DebugKernelWire = KernelWire
DebugKernelLaneHandle = KernelLaneHandle
DebugKernelLanesHandle = KernelLanesHandle
DebugKernelChannelHandle = KernelChannelHandle
DebugKernelChannelsHandle = KernelChannelsHandle
DebugKernelBoardHandle = KernelBoardHandle


__all__ = [
    "DebugKernelBoardHandle",
    "DebugKernelChannelHandle",
    "DebugKernelChannelsHandle",
    "DebugKernelLaneHandle",
    "DebugKernelLanesHandle",
    "DebugKernelWire",
    "DebugZoneAreaView",
    "DebugZoneRegionHandle",
    "DebugZoneRegionSetHandle",
    "KernelBoardHandle",
    "KernelChannelHandle",
    "KernelChannelsHandle",
    "KernelLaneHandle",
    "KernelLanesHandle",
    "KernelWire",
    "ZoneAreaView",
    "ZoneRegionHandle",
    "ZoneRegionSetHandle",
]
