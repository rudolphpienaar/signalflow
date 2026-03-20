"""Tests for chip-local geometry and world attach-point models (Phase 5)."""
from __future__ import annotations

from signalflow.config import signalFlowConfigResult_buildFromDocumentDict
from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import (
    Chip,
    ChipId,
    ChipRef,
    ChipTerminal,
    ChipTerminalSide,
    GridCoord,
    Result,
    RoutingZoneGrid,
    chipDrawLines_build,
    chipResult_build,
    chipTerminalSetResult_build,
    diagnosticStack,
    result_isOkCheck,
)
from signalflow.routing import (
    chipAttachPointSetResult_buildFromPlacedZone,
    chipLocalGeometryResult_build,
    chipLocalGeometrySetResult_buildFromChips,
    routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid,
    routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid,
    routingZoneGridResult_buildFromSignalFlowConfig,
)


def _chip_build(
    module: str,
    func: str,
    west: list[str] | None = None,
    east: list[str] | None = None,
) -> Chip:
    """Build a minimal chip with named terminals on given sides."""

    terminalsMutable: list[ChipTerminal] = []
    for name in west or []:
        terminalsMutable.append(ChipTerminal(name, ChipTerminalSide.WEST))
    for name in east or []:
        terminalsMutable.append(ChipTerminal(name, ChipTerminalSide.EAST))
    terminalSetResult = chipTerminalSetResult_build(tuple(terminalsMutable))
    assert result_isOkCheck(terminalSetResult)
    chipBuildResult = chipResult_build(
        chipId=ChipId(moduleName=module, functionName=func),
        chipTerminalSet=terminalSetResult.value,
    )
    assert result_isOkCheck(chipBuildResult)
    return chipBuildResult.value


def _placedGrid_buildFromDocumentDict(documentDict: dict[str, object]):
    """Build a placed routing-zone grid through the full pipeline."""

    circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(documentDict)
    assert result_isOkCheck(circuitDocumentResult)
    signalFlowConfigResult = signalFlowConfigResult_buildFromDocumentDict(
        {"world": {"sense": "west_to_east"}},
        callingDepth=circuitDocumentResult.value.callingDepth_calculate(),
    )
    assert result_isOkCheck(signalFlowConfigResult)
    routingZoneGridResult: Result[RoutingZoneGrid] = (
        routingZoneGridResult_buildFromSignalFlowConfig(signalFlowConfigResult.value)
    )
    assert result_isOkCheck(routingZoneGridResult)
    assignmentSetResult = (
        routingZoneAssignmentSetResult_buildFromCircuitDocumentAndGrid(
            circuitDocumentResult.value,
            routingZoneGridResult.value,
        )
    )
    assert result_isOkCheck(assignmentSetResult)
    placedGridResult = routingZoneGridPlacementPlanResult_buildFromAssignmentSetAndGrid(
        assignmentSetResult.value,
        routingZoneGridResult.value,
        circuitDocumentResult.value,
    )
    assert result_isOkCheck(placedGridResult)
    return circuitDocumentResult.value, placedGridResult.value


class TestChipLocalGeometry:
    """Verification of chip-local drawing geometry derivation."""

    def test_no_terminal_chip_has_three_lines(self) -> None:
        """A chip with no terminals should take exactly 3 drawing lines."""

        chip = _chip_build("Empty.ts", "noop()")
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        geo = geoResult.value
        assert geo.lineCount == 3
        assert geo.terminalLineOffsets == ()

    def test_no_terminal_chip_linecount_matches_draw_output(self) -> None:
        """lineCount must equal len(chipDrawLines_build(chip))."""

        chip = _chip_build("Empty.ts", "noop()")
        lines = chipDrawLines_build(chip)

        geoResult = chipLocalGeometryResult_build(chip)
        assert result_isOkCheck(geoResult)
        assert geoResult.value.lineCount == len(lines)

    def test_west_and_east_terminal_chip_line_count(self) -> None:
        """A chip with 1 west + 1 east terminal should have 6 drawing lines."""

        chip = _chip_build("App.ts", "main()", west=["a", "ra"], east=["b"])
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        assert geoResult.value.lineCount == len(chipDrawLines_build(chip))

    def test_west_terminal_attaches_at_first_body_row(self) -> None:
        """First west terminal should report bodyStart line offset 3."""

        chip = _chip_build("App.ts", "main()", west=["a"])
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        offsetResult = geoResult.value.lineOffsetForTerminalResult_get(
            ChipTerminalSide.WEST, "a"
        )
        assert result_isOkCheck(offsetResult)
        assert offsetResult.value == 3

    def test_second_west_terminal_attaches_at_second_body_row(self) -> None:
        """Second west terminal (return label) must report lineOffset == 4."""

        chip = _chip_build("App.ts", "main()", west=["a", "ra"])
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        offsetResult = geoResult.value.lineOffsetForTerminalResult_get(
            ChipTerminalSide.WEST, "ra"
        )
        assert result_isOkCheck(offsetResult)
        assert offsetResult.value == 4

    def test_east_terminal_attaches_at_first_body_row(self) -> None:
        """First east terminal must report lineOffset == 3."""

        chip = _chip_build("Worker.ts", "run()", east=["out"])
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        offsetResult = geoResult.value.lineOffsetForTerminalResult_get(
            ChipTerminalSide.EAST, "out"
        )
        assert result_isOkCheck(offsetResult)
        assert offsetResult.value == 3

    def test_second_east_terminal_attaches_at_second_body_row(self) -> None:
        """Second east terminal must report lineOffset == 4."""

        chip = _chip_build("Multi.ts", "multi()", east=["out0", "out1"])
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        offset0 = geoResult.value.lineOffsetForTerminalResult_get(
            ChipTerminalSide.EAST, "out0"
        )
        offset1 = geoResult.value.lineOffsetForTerminalResult_get(
            ChipTerminalSide.EAST, "out1"
        )
        assert result_isOkCheck(offset0)
        assert result_isOkCheck(offset1)
        assert offset0.value == 3
        assert offset1.value == 4

    def test_missing_terminal_returns_err(self) -> None:
        """Looking up a non-existent terminal must return a failed result."""

        chip = _chip_build("App.ts", "main()", west=["a"])
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        diagnosticStack.stack_clear()
        missingResult = geoResult.value.lineOffsetForTerminalResult_get(
            ChipTerminalSide.EAST, "missing"
        )
        assert not result_isOkCheck(missingResult)

    def test_linecount_matches_actual_drawing_for_multi_east(self) -> None:
        """lineCount must equal len(chipDrawLines_build(chip)) for multi-east chips."""

        chip = _chip_build("Hub.ts", "hub()", east=["a", "b", "c", "d"])
        lines = chipDrawLines_build(chip)
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        assert geoResult.value.lineCount == len(lines)

    def test_chipref_is_stable(self) -> None:
        """ChipLocalGeometry.chipRef must equal the chip's own chipRef."""

        chip = _chip_build("App.ts", "fn()", west=["x"])
        geoResult = chipLocalGeometryResult_build(chip)

        assert result_isOkCheck(geoResult)
        assert geoResult.value.chipRef == chip.chipRef_build()


class TestChipLocalGeometrySet:
    """Verification of collection-level geometry building."""

    def test_geometry_set_builds_for_two_chips(self) -> None:
        """Geometry set should contain one entry per input chip."""

        chip_a = _chip_build("A.ts", "a()", west=["x"])
        chip_b = _chip_build("B.ts", "b()", east=["y"])
        setResult = chipLocalGeometrySetResult_buildFromChips((chip_a, chip_b))

        assert result_isOkCheck(setResult)
        geoSet = setResult.value
        assert len(geoSet.chipLocalGeometries) == 2

    def test_geometry_set_lookup_by_chipref(self) -> None:
        """geometryForChipResult_get should return the correct entry."""

        chip_a = _chip_build("A.ts", "a()", west=["x"])
        chip_b = _chip_build("B.ts", "b()", east=["y"])
        setResult = chipLocalGeometrySetResult_buildFromChips((chip_a, chip_b))

        assert result_isOkCheck(setResult)
        geoSet = setResult.value
        geoB = geoSet.geometryForChipResult_get(chip_b.chipRef_build())

        assert result_isOkCheck(geoB)
        assert geoB.value.chipRef == chip_b.chipRef_build()


class TestChipAttachPoints:
    """Verification of world-coordinate attach-point derivation."""

    def test_attach_points_build_for_simple_we_zone(self) -> None:
        """Attach point set should build without error for a simple WE zone."""

        diagnosticStack.stack_clear()

        circuitDocument, placedGrid = _placedGrid_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {
                            "module": "Worker.ts",
                            "func": "run()",
                            "calls": [],
                        }
                    ],
                }
            }
        )
        zoneResult = placedGrid.zoneAtCoordResult_get(GridCoord(1, 1))
        assert result_isOkCheck(zoneResult)

        allChips = tuple(circuitDocument.circuitChipSet.chips)
        geoSetResult = chipLocalGeometrySetResult_buildFromChips(allChips)
        assert result_isOkCheck(geoSetResult)

        attachSetResult = chipAttachPointSetResult_buildFromPlacedZone(
            zone=zoneResult.value,
            chipLocalGeometrySet=geoSetResult.value,
            circuitDocument=circuitDocument,
        )
        assert result_isOkCheck(attachSetResult)

    def test_attach_points_row_is_chip_geometry_driven(self) -> None:
        """West terminal worldRow must equal terminalRegionStart + bodyStart (== 3)."""

        diagnosticStack.stack_clear()

        # mid() has west terminals (input_ports) → placed in west region of zone [1,1]
        circuitDocument, placedGrid = _placedGrid_buildFromDocumentDict(
            {
                "tree": {
                    "module": "Root.ts",
                    "func": "root()",
                    "output_ports": [{"signal": "a", "return": "ra"}],
                    "calls": [
                        {
                            "module": "Mid.ts",
                            "func": "mid()",
                            "input_ports": [{"signal": "a", "return": "ra"}],
                            "calls": [],
                        }
                    ],
                }
            }
        )
        zoneResult = placedGrid.zoneAtCoordResult_get(GridCoord(1, 1))
        assert result_isOkCheck(zoneResult)

        allChips = tuple(circuitDocument.circuitChipSet.chips)
        geoSetResult = chipLocalGeometrySetResult_buildFromChips(allChips)
        assert result_isOkCheck(geoSetResult)

        attachSetResult = chipAttachPointSetResult_buildFromPlacedZone(
            zone=zoneResult.value,
            chipLocalGeometrySet=geoSetResult.value,
            circuitDocument=circuitDocument,
        )
        assert result_isOkCheck(attachSetResult)
        attachSet = attachSetResult.value

        # mid() is in the east terminal region — find its west attach points
        midRef = ChipRef(ChipId("Mid.ts", "mid()"))
        midAttachPoints = attachSet.attachPointsForChip_get(midRef)
        westPoints = [
            point
            for point in midAttachPoints
            if point.terminalSide is ChipTerminalSide.WEST
        ]

        # Zone starts at verticalStart=0; terminalRegion.verticalStart=5 (crossbar);
        # first chip stack offset=0; bodyStart=3 → worldRow = 5 + 0 + 3 = 8
        assert len(westPoints) >= 1
        assert westPoints[0].worldRow == 8

    def test_second_chip_east_attach_row_accounts_for_stack_offset(self) -> None:
        """Second east-side chip worldRow must include the first chip's lineCount."""

        diagnosticStack.stack_clear()

        # main() calls both a() and b(); a() and b() are placed in the east band.
        # Both declare input_ports so they have west terminals in the east region.
        circuitDocument, placedGrid = _placedGrid_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "output_ports": [{"signal": "x"}, {"signal": "y"}],
                    "calls": [
                        {
                            "module": "A.ts",
                            "func": "a()",
                            "input_ports": [{"signal": "x"}],
                            "calls": [],
                        },
                        {
                            "module": "B.ts",
                            "func": "b()",
                            "input_ports": [{"signal": "y"}],
                            "calls": [],
                        },
                    ],
                }
            }
        )
        zoneResult = placedGrid.zoneAtCoordResult_get(GridCoord(1, 1))
        assert result_isOkCheck(zoneResult)

        allChips = tuple(circuitDocument.circuitChipSet.chips)
        geoSetResult = chipLocalGeometrySetResult_buildFromChips(allChips)
        assert result_isOkCheck(geoSetResult)

        aRef = ChipRef(ChipId("A.ts", "a()"))
        bRef = ChipRef(ChipId("B.ts", "b()"))
        aGeoResult = geoSetResult.value.geometryForChipResult_get(aRef)
        assert result_isOkCheck(aGeoResult)
        aLineCount: int = aGeoResult.value.lineCount

        attachSetResult = chipAttachPointSetResult_buildFromPlacedZone(
            zone=zoneResult.value,
            chipLocalGeometrySet=geoSetResult.value,
            circuitDocument=circuitDocument,
        )
        assert result_isOkCheck(attachSetResult)
        attachSet = attachSetResult.value

        # b() is in the east terminal region (east side of zone [1,1]).
        # Its west attach point row is terminalRegionVerticalStart(5) +
        # aLineCount + bodyStart(3).
        bAttachPoints = attachSet.attachPointsForChip_get(bRef)
        westPoints = [
            point
            for point in bAttachPoints
            if point.terminalSide is ChipTerminalSide.WEST
        ]

        assert len(westPoints) >= 1
        assert westPoints[0].worldRow == aLineCount + 8

    def test_attach_point_column_matches_terminal_region_horizontal_start(
        self,
    ) -> None:
        """Attach point worldColumn must equal the terminal region horizontalStart."""

        diagnosticStack.stack_clear()

        # mid() has west terminals → placed in east terminal region of zone [1,1].
        circuitDocument, placedGrid = _placedGrid_buildFromDocumentDict(
            {
                "tree": {
                    "module": "Root.ts",
                    "func": "root()",
                    "output_ports": [{"signal": "a"}],
                    "calls": [
                        {
                            "module": "Mid.ts",
                            "func": "mid()",
                            "input_ports": [{"signal": "a"}],
                            "calls": [],
                        }
                    ],
                }
            }
        )
        zoneResult = placedGrid.zoneAtCoordResult_get(GridCoord(1, 1))
        assert result_isOkCheck(zoneResult)
        zone = zoneResult.value

        from signalflow.models import RoutingZoneRegionKind, RoutingZoneRegionSide

        # mid() is in the east terminal region of zone [1,1].
        eastRegionResult = zone.routingZoneRegionSet.regionForKindAndSideResult_get(
            RoutingZoneRegionKind.CHIP_TERMINAL,
            RoutingZoneRegionSide.EAST,
        )
        assert result_isOkCheck(eastRegionResult)
        expectedColumn: int = (
            eastRegionResult.value.routingZoneRegionFrame.horizontalStart
        )

        allChips = tuple(circuitDocument.circuitChipSet.chips)
        geoSetResult = chipLocalGeometrySetResult_buildFromChips(allChips)
        assert result_isOkCheck(geoSetResult)

        attachSetResult = chipAttachPointSetResult_buildFromPlacedZone(
            zone=zone,
            chipLocalGeometrySet=geoSetResult.value,
            circuitDocument=circuitDocument,
        )
        assert result_isOkCheck(attachSetResult)

        midRef = ChipRef(ChipId("Mid.ts", "mid()"))
        midAttachPoints = attachSetResult.value.attachPointsForChip_get(midRef)
        # mid() has WEST terminals (input_ports → WEST side)
        westPoints = [
            point
            for point in midAttachPoints
            if point.terminalSide is ChipTerminalSide.WEST
        ]

        assert len(westPoints) >= 1
        assert westPoints[0].worldColumn == expectedColumn
