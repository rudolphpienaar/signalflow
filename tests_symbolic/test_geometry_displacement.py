"""Focused tests for local geometry displacement behavior."""

from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.board import BoardGeometry, GeometryZone
from signalflow.engine import context_buildFromDocument
from signalflow.engine.inspect import SignalFlowContext
from signalflow.models import Result, RoutingZoneRegionFrame, result_isOkCheck


def _hubDocumentDict_build() -> dict:
    """Build the parsed `examples/hub.yaml` document."""

    hubPath = Path(__file__).resolve().parent.parent / "examples" / "hub.yaml"
    with hubPath.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _routingZoneRegionFrameShifted_build(
    frame: RoutingZoneRegionFrame,
    *,
    deltaColumns: int,
) -> RoutingZoneRegionFrame:
    """Build a routing-zone region frame shifted horizontally."""

    return RoutingZoneRegionFrame(
        horizontalStart=frame.horizontalStart + deltaColumns,
        verticalStart=frame.verticalStart,
        horizontalSpan=frame.horizontalSpan,
        verticalSpan=frame.verticalSpan,
    )


def test_east_extra_long_displacement_opens_gap_from_extra_fan() -> None:
    """Moving only east extra-long should expose open space from east fan."""

    debugContextResult: Result[SignalFlowContext] = context_buildFromDocument(
        _hubDocumentDict_build()
    )

    assert result_isOkCheck(debugContextResult)
    kernel = debugContextResult.value.zones.zone_get(1, 1).kernel_get("intra")
    assert kernel is not None
    board = kernel.board_get()
    geometry = board.geometry_get()

    eastExtraFan: GeometryZone | None = geometry.zone_get(
        "extra_routing_fan_in_out",
        "east",
    )
    eastExtraLong: GeometryZone | None = geometry.zone_get(
        "extra_routing_longitude",
        "east",
    )
    assert eastExtraFan is not None
    assert eastExtraLong is not None

    beforeGap = (
        eastExtraLong.frame.horizontalStart
        - eastExtraFan.frame.horizontalEnd_calculate()
    )

    shiftedGeometryZonesById = dict(geometry.geometryZonesById)
    shiftedGeometryZonesById[eastExtraLong.regionId] = GeometryZone(
        regionId=eastExtraLong.regionId,
        frame=_routingZoneRegionFrameShifted_build(
            eastExtraLong.frame,
            deltaColumns=5,
        ),
        routingZoneRegionId=eastExtraLong.routingZoneRegionId,
        chipDrawPlacementsByChip=eastExtraLong.chipDrawPlacementsByChip,
        exactTerminalWorldPositionsByChip=(
            eastExtraLong.exactTerminalWorldPositionsByChip
        ),
    )
    shiftedGeometry = BoardGeometry(
        geometryZonesById=shiftedGeometryZonesById,
        effectiveBoundaryFramesByName=geometry.effectiveBoundaryFramesByName,
    )
    shiftedExtraFan = shiftedGeometry.zone_get(
        "extra_routing_fan_in_out",
        "east",
    )
    shiftedExtraLong = shiftedGeometry.zone_get(
        "extra_routing_longitude",
        "east",
    )
    assert shiftedExtraFan is not None
    assert shiftedExtraLong is not None

    afterGap = (
        shiftedExtraLong.frame.horizontalStart
        - shiftedExtraFan.frame.horizontalEnd_calculate()
    )

    assert shiftedExtraFan.frame == eastExtraFan.frame
    assert (
        shiftedExtraLong.frame.horizontalStart
        == eastExtraLong.frame.horizontalStart + 5
    )
    assert afterGap == beforeGap + 5
