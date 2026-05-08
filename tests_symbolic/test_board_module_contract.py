"""Contract tests for the first-class board package."""

from __future__ import annotations

from signalflow.board import (
    Board,
    BoardDoctrine,
    BoardGeometry,
    BoardRegionId,
    BoardSense,
    BoardSide,
    BoardSubstrate,
    RegionFamily,
    WorldFrame,
    WorldPoint,
    boardProblems_get,
    boardRegionId_buildFromRoutingZoneRegionId,
    realizedGeometry_sprint,
)
from signalflow.models import (
    Chip,
    ChipId,
    ChipPortDeclaration,
    ChipPortDeclarationSet,
    ChipTerminal,
    ChipTerminalSet,
    ChipTerminalSide,
    GridCoord,
    RoutingZoneId,
    RoutingZoneRegionFrame,
    RoutingZoneRegionId,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
    chipDrawGeometry_build,
    chipDrawLines_build,
)
from signalflow.models.geometry_scope import (
    BoardGeometryScope,
    BoardGeometryScopeKind,
)


def test_board_package_exposes_first_class_models() -> None:
    """The symbolic branch should expose a top-level board boundary."""

    assert Board.__name__ == "Board"
    assert BoardGeometry.__name__ == "BoardGeometry"
    assert WorldPoint == tuple[int, int]


def test_board_geometry_can_render_world_true_region_sprint() -> None:
    """The new board module should do useful work immediately.

    The first concrete capability we want from the first-class board
    boundary is the ability to render the board substrate directly
    from canonical geometry frames, without needing debug-layer
    region handles.
    """

    geometry = BoardGeometry(
        regionFramesById={
            BoardRegionId(
                family=RegionFamily.CHIP_TERMINAL,
                side=BoardSide.WEST,
            ): RoutingZoneRegionFrame(
                horizontalStart=22,
                verticalStart=5,
                horizontalSpan=12,
                verticalSpan=4,
            ),
            BoardRegionId(
                family=RegionFamily.INTRA_LATITUDE,
                side=BoardSide.NORTH,
            ): RoutingZoneRegionFrame(
                horizontalStart=38,
                verticalStart=10,
                horizontalSpan=10,
                verticalSpan=2,
            ),
            BoardRegionId(
                family=RegionFamily.CHIP_TERMINAL,
                side=BoardSide.EAST,
            ): RoutingZoneRegionFrame(
                horizontalStart=72,
                verticalStart=5,
                horizontalSpan=12,
                verticalSpan=4,
            ),
        }
    )

    board = Board(
        routingZoneId=RoutingZoneId(
            id=GridCoord(columnIndex=1, rowIndex=1),
        ),
        side="intra",
        worldFrame=WorldFrame(topLeft=(0, 0), bottomRight=(99, 99)),
        doctrine=BoardDoctrine(
            sense=BoardSense.WEST_TO_EAST,
            minimumCrossbarSpan=10,
        ),
        substrate=BoardSubstrate(
            sense=BoardSense.WEST_TO_EAST,
            regionFramesById=geometry.regionFramesById,
        ),
        geometry=geometry,
    )

    rendered = board.geometry_sprint(columnOffset=0)

    assert " 0:" in rendered
    assert "10:" in rendered
    assert "legend:" in rendered
    assert "north/intra_routing_latitude" in rendered
    assert "west/chip_terminal" in rendered


def test_board_geometry_keeps_layout_boundaries_and_exact_terminals_separate(
) -> None:
    """Board geometry must carry both layout and attach-point truth.

    The board object needs to support padded effective boundaries for layout
    while still preserving exact terminal attach points for realization. This
    test locks in that both facts can coexist without being merged into one
    ambiguous coordinate source.
    """

    effectiveBoundary = RoutingZoneRegionFrame(
        horizontalStart=10,
        verticalStart=20,
        horizontalSpan=30,
        verticalSpan=8,
    )
    geometry = BoardGeometry(
        geometryScopes=(
            BoardGeometryScope(
                scopeId="layer/0",
                kind=BoardGeometryScopeKind.DEPTH_LAYER,
                label="layer/0",
                drawable=True,
                frame=effectiveBoundary,
            ),
        ),
        exactTerminalWorldPositionsByChip={
            "App.ts.main()": {
                "s1": (33, 9),
                "r1": (33, 10),
            }
        },
    )

    assert (
        geometry.effectiveBoundaryFrame_get("layer/0")
        == effectiveBoundary
    )
    assert geometry.exactTerminalWorldPosition_get("App.ts.main()", "s1") == (
        33,
        9,
    )
    assert geometry.exactTerminalWorldPosition_get("App.ts.main()", "r1") == (
        33,
        10,
    )
    assert (
        geometry.exactTerminalWorldPosition_get("App.ts.main()", "missing")
        is None
    )


def test_board_validators_accept_consistent_board() -> None:
    """Board validators should treat coherent board state as problem-free."""

    routingZoneId = RoutingZoneId(
        id=GridCoord(columnIndex=1, rowIndex=1),
    )
    geometry = BoardGeometry(
        regionFramesById={
            BoardRegionId(
                family=RegionFamily.CHIP_TERMINAL,
                side=BoardSide.WEST,
            ): RoutingZoneRegionFrame(
                horizontalStart=22,
                verticalStart=5,
                horizontalSpan=12,
                verticalSpan=40,
            ),
        },
        routingZoneRegionIdsById={
            boardRegionId_buildFromRoutingZoneRegionId(
                RoutingZoneRegionId(
                    routingZoneId=routingZoneId,
                    routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
                    routingZoneRegionSide=RoutingZoneRegionSide.WEST,
                )
            ): RoutingZoneRegionId(
                routingZoneId=routingZoneId,
                routingZoneRegionKind=RoutingZoneRegionKind.CHIP_TERMINAL,
                routingZoneRegionSide=RoutingZoneRegionSide.WEST,
            ),
        },
        exactTerminalWorldPositionsByChip={
            "App.ts.main()": {
                "s1": (33, 9),
            }
        },
    )
    board = Board(
        routingZoneId=routingZoneId,
        side="intra",
        worldFrame=WorldFrame(topLeft=(22, 5), bottomRight=(33, 44)),
        doctrine=BoardDoctrine(
            sense=BoardSense.WEST_TO_EAST,
            minimumCrossbarSpan=10,
        ),
        substrate=BoardSubstrate(
            sense=BoardSense.WEST_TO_EAST,
            regionFramesById=geometry.regionFramesById,
        ),
        geometry=geometry,
    )

    assert boardProblems_get(board) == ()


def test_board_can_distinguish_effective_and_substrate_views() -> None:
    """The board surface should preserve substrate/effective distinction.

    The operational board defaults to the effective view, but users still need
    an explicit substrate escape hatch for comparison when doctrine-derived
    boundaries are under inspection.
    """

    geometry = BoardGeometry(
        geometryScopes=(
            BoardGeometryScope(
                scopeId="layer/0",
                kind=BoardGeometryScopeKind.DEPTH_LAYER,
                label="layer/0",
                drawable=True,
                frame=RoutingZoneRegionFrame(
                    horizontalStart=10,
                    verticalStart=20,
                    horizontalSpan=30,
                    verticalSpan=8,
                ),
            ),
        ),
    )
    effectiveBoard = Board(
        routingZoneId=RoutingZoneId(
            id=GridCoord(columnIndex=1, rowIndex=1),
        ),
        side="intra",
        worldFrame=WorldFrame(topLeft=(0, 0), bottomRight=(99, 99)),
        doctrine=BoardDoctrine(
            sense=BoardSense.WEST_TO_EAST,
            minimumCrossbarSpan=10,
        ),
        substrate=BoardSubstrate(
            sense=BoardSense.WEST_TO_EAST,
            regionFramesById={},
        ),
        geometry=geometry,
    )

    substrateBoard = effectiveBoard.substrate_get()

    assert effectiveBoard.effective_get() is effectiveBoard
    assert substrateBoard is not effectiveBoard
    assert substrateBoard.geometry.effectiveBoundaryFramesByName == {}


def test_board_render_can_crop_realized_geometry_sprint() -> None:
    """Board render should own the realized geometry crop-and-label step."""

    baseCanvasLines = [
        " " * 20,
        "    ┌──┐            ",
        "    │  ├────┐       ",
        "    └──┘    │       ",
        "            └──┐    ",
        "               │    ",
        "               └──┘ ",
    ]
    rendered = realizedGeometry_sprint(
        baseCanvasLines=baseCanvasLines,
        routeCells={
            (8, 2),
            (9, 2),
            (10, 2),
            (11, 2),
            (12, 2),
            (12, 3),
            (12, 4),
        },
        extraFrames=(WorldFrame(topLeft=(4, 1), bottomRight=(7, 3)),),
        wiringLegendLines=("", "wires:", "  demo"),
        horizontalMargin=1,
        verticalMargin=1,
    )

    assert rendered.splitlines()[0].lstrip().startswith("0:")
    assert "wires:" in rendered
    assert "demo" in rendered


def test_chip_draw_geometry_exposes_semantic_offsets_without_changing_lines(
) -> None:
    """Semantic chip geometry should replace whitespace parsing, not output."""

    chip = Chip(
        chipId=ChipId(moduleName="Proxy.ts", functionName="p1()"),
        chipTerminalSet=ChipTerminalSet(
            terminals=(
                ChipTerminal("s1", ChipTerminalSide.WEST),
                ChipTerminal("r1", ChipTerminalSide.WEST),
            )
        ),
        inputPortDeclarationSet=ChipPortDeclarationSet(
            portDeclarations=(
                ChipPortDeclaration(signalName="s1", returnName="r1"),
            )
        ),
    )

    drawGeometry = chipDrawGeometry_build(chip)

    assert drawGeometry.drawLines == chipDrawLines_build(chip)
    assert drawGeometry.boxLeftColumnOffset == 4
    assert drawGeometry.visibleLeftColumnOffset == 0
    assert drawGeometry.westTerminalLineOffsets == (("s1", 3), ("r1", 4))
    westAnnotationWidths = tuple(
        span.width for span in drawGeometry.westTerminalAnnotationSpans
    )
    assert westAnnotationWidths == (4, 4)


def test_chip_draw_geometry_compacts_omitted_return_ports() -> None:
    """Omitted returns should not reserve blank paired rows."""

    chip = Chip(
        chipId=ChipId(moduleName="Network.ts", functionName="network()"),
        chipTerminalSet=ChipTerminalSet(
            terminals=(
                ChipTerminal("a", ChipTerminalSide.EAST),
                ChipTerminal("b", ChipTerminalSide.EAST),
                ChipTerminal("rb", ChipTerminalSide.EAST),
                ChipTerminal("c", ChipTerminalSide.EAST),
            )
        ),
        outputPortDeclarationSet=ChipPortDeclarationSet(
            portDeclarations=(
                ChipPortDeclaration(signalName="a"),
                ChipPortDeclaration(signalName="b", returnName="rb"),
                ChipPortDeclaration(signalName="c"),
            )
        ),
    )

    drawGeometry = chipDrawGeometry_build(chip)
    drawText = "\n".join(drawGeometry.drawLines)

    assert drawGeometry.eastTerminalLineOffsets == (
        ("a", 3),
        ("b", 4),
        ("rb", 5),
        ("c", 6),
    )
    eastAnnotationWidths = tuple(
        span.width for span in drawGeometry.eastTerminalAnnotationSpans
    )
    assert eastAnnotationWidths == (4, 4, 4, 4)
    assert drawText.index("─►a") < drawText.index("─►b")
    assert drawText.index("─►b") < drawText.index("◄─rb")
    assert drawText.index("◄─rb") < drawText.index("─►c")
