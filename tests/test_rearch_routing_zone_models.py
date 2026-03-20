"""Tests for the first RoutingZoneGrid model layer.

These tests cover the first-class chip, routing-zone, interconnect, and
routing-zone-grid models introduced by the March 2026 architecture reset.
"""
from __future__ import annotations

from signalflow.models import (
    Chip,
    ChipId,
    ChipPlacement,
    ChipRef,
    ChipTerminal,
    ChipTerminalSet,
    ChipTerminalSide,
    GridCoord,
    RoutingZone,
    RoutingZoneChannelSense,
    RoutingZoneGrid,
    RoutingZoneGridPathPolicy,
    RoutingZoneId,
    RoutingZoneInterconnect,
    RoutingZoneInterconnectAxis,
    RoutingZoneInterconnectId,
    RoutingZoneRegion,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSet,
    RoutingZoneRegionSide,
    RoutingZoneSense,
    chipPlacementSetResult_build,
    diagnosticStack,
    result_isOkCheck,
    routingZoneFrameResult_build,
    routingZoneGridResult_build,
    routingZoneInterconnectFrameResult_build,
    routingZoneInterconnectResult_build,
    routingZoneInterconnectSetResult_build,
    routingZonePathResult_build,
    routingZoneRegionFrameResult_build,
    routingZoneRegionResult_build,
    routingZoneRegionSetResult_build,
    routingZoneResult_build,
    routingZoneSetResult_build,
)


def chipNamed_build(moduleName: str, functionName: str) -> Chip:
    """Build one simple chip for routing-zone model tests."""

    return Chip(
        chipId=ChipId(moduleName=moduleName, functionName=functionName),
        chipTerminalSet=ChipTerminalSet(
            terminals=(
                ChipTerminal(
                    terminalName="in",
                    terminalSide=ChipTerminalSide.WEST,
                ),
                ChipTerminal(
                    terminalName="out",
                    terminalSide=ChipTerminalSide.EAST,
                ),
            )
        ),
        internalRoutingDeclared=True,
    )


def worldZoneId_build(columnIndex: int, rowIndex: int) -> RoutingZoneId:
    """Build one world-grid-addressed routing-zone id for tests."""

    return RoutingZoneId(id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex))


def resultValue_get(result: object):
    """Return the value from one successful result."""

    assert result_isOkCheck(result)
    return result.value


def diagnosticPresent_check(codeSubstring: str) -> bool:
    """Return whether the diagnostic stack contains one matching code."""

    return bool(diagnosticStack.diagnosticSet_build().diagnostics_search(codeSubstring))


def westEastRegionSetForZone_build(
    routingZoneId: RoutingZoneId,
) -> RoutingZoneRegionSet:
    """Build a minimal explicit west-to-east region set for one zone."""

    return resultValue_get(
        routingZoneRegionSetResult_build(
            routingZoneRegions=(
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
                            routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=0,
                                verticalStart=0,
                                horizontalSpan=3,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=3,
                                verticalStart=0,
                                horizontalSpan=1,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=4,
                                verticalStart=0,
                                horizontalSpan=2,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.EAST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=6,
                                verticalStart=0,
                                horizontalSpan=2,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=8,
                                verticalStart=0,
                                horizontalSpan=1,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.EAST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=9,
                                verticalStart=0,
                                horizontalSpan=1,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTER_ROUTING_FAN_IN_OUT
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.EAST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=9,
                                verticalStart=0,
                                horizontalSpan=1,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
                            routingZoneRegionSide=RoutingZoneRegionSide.EAST,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=10,
                                verticalStart=0,
                                horizontalSpan=3,
                                verticalSpan=10,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.NORTH,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=4,
                                verticalStart=2,
                                horizontalSpan=4,
                                verticalSpan=1,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.SOUTH,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=4,
                                verticalStart=3,
                                horizontalSpan=4,
                                verticalSpan=1,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTER_ROUTING_LATITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.NORTH,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=4,
                                verticalStart=4,
                                horizontalSpan=4,
                                verticalSpan=1,
                            )
                        ),
                    )
                ),
                resultValue_get(
                    routingZoneRegionResult_build(
                        routingZoneRegionId=RoutingZoneRegionId(
                            routingZoneId=routingZoneId,
                            routingZoneRegionKind=(
                                RoutingZoneRegionKind.INTER_ROUTING_LATITUDE
                            ),
                            routingZoneRegionSide=RoutingZoneRegionSide.SOUTH,
                        ),
                        routingZoneRegionFrame=resultValue_get(
                            routingZoneRegionFrameResult_build(
                                horizontalStart=4,
                                verticalStart=5,
                                horizontalSpan=4,
                                verticalSpan=1,
                            )
                        ),
                    )
                ),
            )
        )
    )


def routingZone_build(
    columnIndex: int,
    rowIndex: int,
    chipPlacements: tuple[ChipPlacement, ...] = (),
) -> RoutingZone:
    """Build one simple west-to-east routing zone for tests."""

    routingZoneId: RoutingZoneId = worldZoneId_build(columnIndex, rowIndex)
    return resultValue_get(
        routingZoneResult_build(
            routingZoneId=routingZoneId,
            routingZoneSense=RoutingZoneSense.WEST_TO_EAST,
            channelSense=RoutingZoneChannelSense.CLOCKWISE,
            routingZoneFrame=resultValue_get(
                routingZoneFrameResult_build(
                    horizontalStart=0,
                    verticalStart=0,
                    horizontalSpan=13,
                    verticalSpan=10,
                )
            ),
            routingZoneRegionSet=westEastRegionSetForZone_build(routingZoneId),
            chipPlacementSet=resultValue_get(
                chipPlacementSetResult_build(placements=chipPlacements)
            ),
        )
    )


class TestChipModels:
    """Verification of first-class chip models."""

    def test_chipRef_build_wraps_chip_identity(self) -> None:
        """A chip should build a lightweight reference from its identity."""

        chip: Chip = chipNamed_build("alpha.py", "helper()")

        chipRef: ChipRef = chip.chipRef_build()

        assert chipRef.chipId == ChipId("alpha.py", "helper()")

    def test_terminalsOnSide_build_filters_chip_terminals(self) -> None:
        """Terminal filtering should preserve only the requested side."""

        chip: Chip = chipNamed_build("alpha.py", "helper()")

        westTerminalSet: ChipTerminalSet = chip.chipTerminalSet.terminalsOnSide_build(
            ChipTerminalSide.WEST
        )
        eastTerminalSet: ChipTerminalSet = chip.chipTerminalSet.terminalsOnSide_build(
            ChipTerminalSide.EAST
        )

        assert len(westTerminalSet.terminals) == 1
        assert len(eastTerminalSet.terminals) == 1
        assert westTerminalSet.terminals[0].terminalName == "in"
        assert eastTerminalSet.terminals[0].terminalName == "out"


class TestRoutingZoneRegionModels:
    """Verification of explicit zone-region models."""

    def test_routingZoneRegion_rejects_sided_kind_without_side(self) -> None:
        """A chip-terminal region must declare a side."""

        diagnosticStack.stack_clear()

        routingZoneRegionResult = routingZoneRegionResult_build(
            routingZoneRegionId=RoutingZoneRegionId(
                routingZoneId=worldZoneId_build(1, 1),
                routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
            ),
            routingZoneRegionFrame=resultValue_get(
                routingZoneRegionFrameResult_build(
                    horizontalStart=0,
                    verticalStart=0,
                    horizontalSpan=1,
                    verticalSpan=1,
                )
            ),
        )

        assert not result_isOkCheck(routingZoneRegionResult)
        assert diagnosticPresent_check("routing.zone.region.missing_side")

    def test_routingZoneRegion_accepts_sided_longitude(self) -> None:
        """Longitude/latitude regions must carry a cardinal side — accept WEST."""

        diagnosticStack.stack_clear()

        routingZoneRegionResult = routingZoneRegionResult_build(
            routingZoneRegionId=RoutingZoneRegionId(
                routingZoneId=worldZoneId_build(1, 1),
                routingZoneRegionKind=RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE,
                routingZoneRegionSide=RoutingZoneRegionSide.WEST,
            ),
            routingZoneRegionFrame=resultValue_get(
                routingZoneRegionFrameResult_build(
                    horizontalStart=0,
                    verticalStart=0,
                    horizontalSpan=1,
                    verticalSpan=1,
                )
            ),
        )

        assert result_isOkCheck(routingZoneRegionResult)

    def test_routingZoneRegionSet_rejects_duplicate_region_ids(self) -> None:
        """A region set must not contain duplicate region ids."""

        routingZoneRegion: RoutingZoneRegion = resultValue_get(
            routingZoneRegionResult_build(
                routingZoneRegionId=RoutingZoneRegionId(
                    routingZoneId=worldZoneId_build(1, 1),
                    routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
                    routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                ),
                routingZoneRegionFrame=resultValue_get(
                    routingZoneRegionFrameResult_build(
                        horizontalStart=0,
                        verticalStart=0,
                        horizontalSpan=1,
                        verticalSpan=1,
                    )
                ),
            )
        )
        diagnosticStack.stack_clear()

        routingZoneRegionSetResult = routingZoneRegionSetResult_build(
            routingZoneRegions=(routingZoneRegion, routingZoneRegion)
        )

        assert not result_isOkCheck(routingZoneRegionSetResult)
        assert diagnosticPresent_check("routing.zone.region_set.duplicate_region_id")


class TestRoutingZoneModels:
    """Verification of routing-zone and interconnect models."""

    def test_routingZone_allows_chip_internal_zone_identity(self) -> None:
        """A standalone zone may be addressed by one chip id."""

        chipInternalZoneId: RoutingZoneId = RoutingZoneId(
            id=ChipId(moduleName="alpha.py", functionName="helper()")
        )

        routingZone: RoutingZone = resultValue_get(
            routingZoneResult_build(
                routingZoneId=chipInternalZoneId,
                routingZoneSense=RoutingZoneSense.WEST_TO_EAST,
                routingZoneFrame=resultValue_get(
                    routingZoneFrameResult_build(
                        horizontalStart=0,
                        verticalStart=0,
                        horizontalSpan=13,
                        verticalSpan=10,
                    )
                ),
                routingZoneRegionSet=westEastRegionSetForZone_build(chipInternalZoneId),
            )
        )

        assert routingZone.routingZoneId.chipInternalAddress_isPresentCheck()
        chipIdResult = routingZone.routingZoneId.chipIdResult_get()
        assert result_isOkCheck(chipIdResult)
        assert chipIdResult.value == ChipId(
            moduleName="alpha.py",
            functionName="helper()",
        )

    def test_chipPlacementSet_rejects_duplicate_chip_refs(self) -> None:
        """A chip may not be placed more than once in one zone."""

        chipRef: ChipRef = chipNamed_build("alpha.py", "helper()").chipRef_build()
        westChipTerminalRegionId: RoutingZoneRegionId = RoutingZoneRegionId(
            routingZoneId=worldZoneId_build(1, 1),
            routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
            routingZoneRegionSide=RoutingZoneRegionSide.WEST,
        )
        eastChipTerminalRegionId: RoutingZoneRegionId = RoutingZoneRegionId(
            routingZoneId=worldZoneId_build(1, 1),
            routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
            routingZoneRegionSide=RoutingZoneRegionSide.EAST,
        )
        diagnosticStack.stack_clear()

        chipPlacementSetResult = chipPlacementSetResult_build(
            placements=(
                ChipPlacement(
                    chipRef=chipRef,
                    chipTerminalRegionId=westChipTerminalRegionId,
                    orderIndex=0,
                ),
                ChipPlacement(
                    chipRef=chipRef,
                    chipTerminalRegionId=eastChipTerminalRegionId,
                    orderIndex=0,
                ),
            )
        )

        assert not result_isOkCheck(chipPlacementSetResult)
        assert diagnosticPresent_check("routing.zone.placement_set.duplicate_chip")

    def test_routingZone_accepts_north_side_chip_terminal_in_wte_zone(self) -> None:
        """A west-to-east zone accepts NORTH-sided regions (all 4 sides now valid)."""

        routingZoneId: RoutingZoneId = worldZoneId_build(1, 1)

        routingZoneResult = routingZoneResult_build(
            routingZoneId=routingZoneId,
            routingZoneSense=RoutingZoneSense.WEST_TO_EAST,
            routingZoneFrame=resultValue_get(
                routingZoneFrameResult_build(
                    horizontalStart=0,
                    verticalStart=0,
                    horizontalSpan=5,
                    verticalSpan=5,
                )
            ),
            routingZoneRegionSet=resultValue_get(
                routingZoneRegionSetResult_build(
                    routingZoneRegions=(
                        resultValue_get(
                            routingZoneRegionResult_build(
                                routingZoneRegionId=RoutingZoneRegionId(
                                    routingZoneId=routingZoneId,
                                    routingZoneRegionKind=(
                                        RoutingZoneRegionKind.CHIP_TERMINAL
                                    ),
                                    routingZoneRegionSide=RoutingZoneRegionSide.NORTH,
                                ),
                                routingZoneRegionFrame=resultValue_get(
                                    routingZoneRegionFrameResult_build(
                                        horizontalStart=0,
                                        verticalStart=0,
                                        horizontalSpan=2,
                                        verticalSpan=2,
                                    )
                                ),
                            )
                        ),
                    )
                )
            ),
        )

        assert result_isOkCheck(routingZoneResult)

    def test_routingZone_rejects_region_outside_zone_frame(self) -> None:
        """Owned regions must lie fully within the zone frame."""

        routingZoneId: RoutingZoneId = worldZoneId_build(1, 1)
        diagnosticStack.stack_clear()

        routingZoneResult = routingZoneResult_build(
            routingZoneId=routingZoneId,
            routingZoneSense=RoutingZoneSense.WEST_TO_EAST,
            routingZoneFrame=resultValue_get(
                routingZoneFrameResult_build(
                    horizontalStart=0,
                    verticalStart=0,
                    horizontalSpan=5,
                    verticalSpan=5,
                )
            ),
            routingZoneRegionSet=resultValue_get(
                routingZoneRegionSetResult_build(
                    routingZoneRegions=(
                        resultValue_get(
                            routingZoneRegionResult_build(
                                routingZoneRegionId=RoutingZoneRegionId(
                                    routingZoneId=routingZoneId,
                                    routingZoneRegionKind=(
                                        RoutingZoneRegionKind.CHIP_TERMINAL
                                    ),
                                    routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                                ),
                                routingZoneRegionFrame=resultValue_get(
                                    routingZoneRegionFrameResult_build(
                                        horizontalStart=4,
                                        verticalStart=0,
                                        horizontalSpan=2,
                                        verticalSpan=2,
                                    )
                                ),
                            )
                        ),
                    )
                )
            ),
        )

        assert not result_isOkCheck(routingZoneResult)
        assert diagnosticPresent_check("routing.zone.region.outside_zone_frame")

    def test_routingZone_rejects_chip_placement_into_non_terminal_region(self) -> None:
        """Chip placement targets must refer to terminal regions."""

        chipRef: ChipRef = chipNamed_build("alpha.py", "helper()").chipRef_build()
        routingZoneId: RoutingZoneId = worldZoneId_build(1, 1)
        diagnosticStack.stack_clear()

        routingZoneResult = routingZoneResult_build(
            routingZoneId=routingZoneId,
            routingZoneSense=RoutingZoneSense.WEST_TO_EAST,
            routingZoneFrame=resultValue_get(
                routingZoneFrameResult_build(
                    horizontalStart=0,
                    verticalStart=0,
                    horizontalSpan=13,
                    verticalSpan=10,
                )
            ),
            routingZoneRegionSet=westEastRegionSetForZone_build(routingZoneId),
            chipPlacementSet=resultValue_get(
                chipPlacementSetResult_build(
                    placements=(
                        ChipPlacement(
                            chipRef=chipRef,
                            chipTerminalRegionId=RoutingZoneRegionId(
                                routingZoneId=routingZoneId,
                                routingZoneRegionKind=(
                                    RoutingZoneRegionKind.INTER_ROUTING_LONGITUDE
                                ),
                                routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                            ),
                            orderIndex=0,
                        ),
                    )
                )
            ),
        )

        assert not result_isOkCheck(routingZoneResult)
        assert diagnosticPresent_check("routing.zone.placement.invalid_region_kind")

    def test_routingZoneInterconnect_build_derives_horizontal_axis(self) -> None:
        """Adjacent same-row zones should produce a horizontal interconnect."""

        sourceZoneId: RoutingZoneId = worldZoneId_build(1, 1)
        destinationZoneId: RoutingZoneId = worldZoneId_build(2, 1)
        routingZoneInterconnect: RoutingZoneInterconnect = resultValue_get(
            routingZoneInterconnectResult_build(
                routingZoneInterconnectId=RoutingZoneInterconnectId(
                    sourceZoneId=sourceZoneId,
                    destinationZoneId=destinationZoneId,
                ),
                sourceZoneId=sourceZoneId,
                destinationZoneId=destinationZoneId,
                routingZoneInterconnectFrame=resultValue_get(
                    routingZoneInterconnectFrameResult_build(
                        horizontalStart=13,
                        verticalStart=0,
                        horizontalSpan=2,
                        verticalSpan=10,
                    )
                ),
            )
        )

        interconnectAxisResult = routingZoneInterconnect.interconnectAxisResult_get()

        assert result_isOkCheck(interconnectAxisResult)
        assert interconnectAxisResult.value is RoutingZoneInterconnectAxis.HORIZONTAL

    def test_routingZoneInterconnect_rejects_non_neighboring_zones(self) -> None:
        """An interconnect may connect only neighboring zones."""

        sourceZoneId: RoutingZoneId = worldZoneId_build(1, 1)
        destinationZoneId: RoutingZoneId = worldZoneId_build(3, 1)
        diagnosticStack.stack_clear()

        routingZoneInterconnectResult = routingZoneInterconnectResult_build(
            routingZoneInterconnectId=RoutingZoneInterconnectId(
                sourceZoneId=sourceZoneId,
                destinationZoneId=destinationZoneId,
            ),
            sourceZoneId=sourceZoneId,
            destinationZoneId=destinationZoneId,
        )

        assert not result_isOkCheck(routingZoneInterconnectResult)
        assert diagnosticPresent_check("routing.zone.interconnect.non_neighbor")


class TestRoutingZoneGridModels:
    """Verification of world-topology models."""

    def test_routingZoneGrid_rejects_chip_internal_zone_ids(self) -> None:
        """The world grid may contain only world-grid-addressed zones."""

        diagnosticStack.stack_clear()

        routingZoneSetResult = routingZoneSetResult_build(
            routingZones=(
                resultValue_get(
                    routingZoneResult_build(
                        routingZoneId=RoutingZoneId(
                            id=ChipId(
                                moduleName="alpha.py",
                                functionName="helper()",
                            )
                        ),
                        routingZoneSense=RoutingZoneSense.WEST_TO_EAST,
                    )
                ),
            )
        )

        assert not result_isOkCheck(routingZoneSetResult)
        assert diagnosticPresent_check(
            "routing.zone_grid.zone_set.invalid_address_type"
        )

    def test_pathBetweenZones_build_uses_horizontal_first_policy(self) -> None:
        """World topology should build the expected no-zig-zag macro path."""

        routingZoneGrid: RoutingZoneGrid = resultValue_get(
            routingZoneGridResult_build(
                worldSense=RoutingZoneSense.WEST_TO_EAST,
                routingZoneSet=resultValue_get(
                    routingZoneSetResult_build(
                        routingZones=(
                            routingZone_build(3, 3),
                            routingZone_build(2, 3),
                            routingZone_build(1, 3),
                            routingZone_build(1, 2),
                            routingZone_build(1, 1),
                        )
                    )
                ),
                routingZoneInterconnectSet=resultValue_get(
                    routingZoneInterconnectSetResult_build(
                        routingZoneInterconnects=(
                            resultValue_get(
                                routingZoneInterconnectResult_build(
                                    routingZoneInterconnectId=RoutingZoneInterconnectId(
                                        sourceZoneId=worldZoneId_build(3, 3),
                                        destinationZoneId=worldZoneId_build(2, 3),
                                    ),
                                    sourceZoneId=worldZoneId_build(3, 3),
                                    destinationZoneId=worldZoneId_build(2, 3),
                                )
                            ),
                            resultValue_get(
                                routingZoneInterconnectResult_build(
                                    routingZoneInterconnectId=RoutingZoneInterconnectId(
                                        sourceZoneId=worldZoneId_build(2, 3),
                                        destinationZoneId=worldZoneId_build(1, 3),
                                    ),
                                    sourceZoneId=worldZoneId_build(2, 3),
                                    destinationZoneId=worldZoneId_build(1, 3),
                                )
                            ),
                            resultValue_get(
                                routingZoneInterconnectResult_build(
                                    routingZoneInterconnectId=RoutingZoneInterconnectId(
                                        sourceZoneId=worldZoneId_build(1, 3),
                                        destinationZoneId=worldZoneId_build(1, 2),
                                    ),
                                    sourceZoneId=worldZoneId_build(1, 3),
                                    destinationZoneId=worldZoneId_build(1, 2),
                                )
                            ),
                            resultValue_get(
                                routingZoneInterconnectResult_build(
                                    routingZoneInterconnectId=RoutingZoneInterconnectId(
                                        sourceZoneId=worldZoneId_build(1, 2),
                                        destinationZoneId=worldZoneId_build(1, 1),
                                    ),
                                    sourceZoneId=worldZoneId_build(1, 2),
                                    destinationZoneId=worldZoneId_build(1, 1),
                                )
                            ),
                        )
                    )
                ),
            )
        )
        routingZonePathResult = routingZoneGrid.pathBetweenZonesResult_build(
            sourceZoneId=worldZoneId_build(3, 3),
            destinationZoneId=worldZoneId_build(1, 1),
            pathPolicy=RoutingZoneGridPathPolicy.HORIZONTAL_FIRST,
        )
        assert result_isOkCheck(routingZonePathResult)
        routingZonePath = routingZonePathResult.value

        assert routingZonePath.zoneIds == (
            worldZoneId_build(3, 3),
            worldZoneId_build(2, 3),
            worldZoneId_build(1, 3),
            worldZoneId_build(1, 2),
            worldZoneId_build(1, 1),
        )

        interconnectSequenceResult = (
            routingZoneGrid.interconnectSequenceForPathResult_build(
                routingZonePath
            )
        )
        assert result_isOkCheck(interconnectSequenceResult)
        interconnectSequence = interconnectSequenceResult.value

        assert len(interconnectSequence.routingZoneInterconnects) == 4

    def test_routingZonePath_rejects_non_neighbor_step(self) -> None:
        """A macro path must move by neighboring zones."""

        diagnosticStack.stack_clear()

        routingZonePathResult = routingZonePathResult_build(
            zoneIds=(
                worldZoneId_build(1, 1),
                worldZoneId_build(3, 1),
            )
        )

        assert not result_isOkCheck(routingZonePathResult)
        assert diagnosticPresent_check("routing.zone_grid.path.non_neighbor_step")
