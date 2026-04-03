"""Runtime chip object for the quarantine board surface.

This module exposes the first-class chip runtime object used by the REPL and
debug-facing board workflow. A `BoardChip` is an operator-oriented façade over
canonical chip facts, chip-local geometry, placement lookups, and chip-internal
harmonization entry points. It does not own board placement or solve policy.

Key components:
    - BoardChip: Runtime chip object with geometry, placement, and child access

Typical usage:
    chip = chips.chip_get("App.ts", "main()")
    print(chip.geometry_sprint())
    kernel = chip.internalBoard_get()

Dependencies:
    - Requires canonical chip geometry from `signalflow.models.chip`
    - Delegates actual board solving to `BoardKernel` and related runtime types
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from signalflow.board.types import ChipTerminalPositions
from signalflow.models import ChipDrawGeometry, ChipId

if TYPE_CHECKING:
    from signalflow.board.kernel_runtime import BoardKernel


@dataclass(frozen=True)
class BoardChip:
    """Runtime chip object for operator-facing chip inspection.

    Attributes:
        chipId: Stable identity of the chip.
        rawProvider: Deferred provider for the raw chip lookup result.
        titleProvider: Deferred provider for the stable display title.
        geometryProvider: Deferred provider for canonical chip-local geometry.
        sizeProvider: Deferred provider for rendered width and height.
        terminalsProvider: Deferred provider for terminal counts by side.
        localTerminalPositionsProvider: Deferred provider for local terminal positions.
        worldTerminalPositionsProvider: Deferred provider for placed world positions.
        placementProvider: Deferred provider for the primary placement result.
        locationProvider: Deferred provider for the primary location record.
        locationsProvider: Deferred provider for all location records.
        routesProvider: Deferred provider for solved chip-local routes.
        internalBoardProvider: Deferred provider for the harmonized internal board kernel.
        worldFrameProvider: Deferred provider for the chip world frame.
        childrenProvider: Deferred provider for outgoing call target chips.
        schematicProvider: Deferred provider for schematic text.
        summaryProvider: Deferred provider for summary text.

    Example:
        >>> chip = chips.chip_get("Hub.ts", "process()")
        >>> chip.title_get()
        'Hub.ts:process()'
    """

    chipId: ChipId
    rawProvider: Callable[[], object]
    titleProvider: Callable[[], str]
    geometryProvider: Callable[[], ChipDrawGeometry]
    sizeProvider: Callable[[], tuple[int, int]]
    terminalsProvider: Callable[[], dict[str, int]]
    localTerminalPositionsProvider: Callable[[str], ChipTerminalPositions]
    worldTerminalPositionsProvider: Callable[[str], ChipTerminalPositions]
    placementProvider: Callable[[], object]
    locationProvider: Callable[[], object]
    locationsProvider: Callable[[], object]
    routesProvider: Callable[[], object]
    internalBoardProvider: Callable[[], "BoardKernel"]
    worldFrameProvider: Callable[[], object]
    childrenProvider: Callable[[], tuple["BoardChip", ...]]
    schematicProvider: Callable[[], str]
    summaryProvider: Callable[[], str]

    def __dir__(self) -> list[str]:
        """Return the curated public chip inspection surface.

        Returns:
            Public chip methods intended for interactive use.
        """

        return [
            "child_get",
            "children_get",
            "dimensions_get",
            "geometry_get",
            "geometry_text",
            "height_get",
            "internalBoard_get",
            "location_get",
            "locations_get",
            "placement_get",
            "raw_get",
            "routes_get",
            "schematic_text",
            "size_get",
            "summary_text",
            "terminals_get",
            "terminals_getLocalPositions",
            "terminals_getWorldPositions",
            "title_get",
            "worldFrame_get",
            "width_get",
        ]

    def __repr__(self) -> str:
        """Return a concise interactive representation.

        Returns:
            Short runtime label for this chip.
        """

        return f"<chip {self.title_get()}>"

    def raw_get(self):
        """Return the raw chip lookup result behind this runtime chip.

        Returns:
            Raw chip result/provider output used by the debug bridge.
        """

        return self.rawProvider()

    def title_get(self) -> str:
        """Return the stable human-readable chip title.

        Returns:
            Canonical `module:function` display title.
        """

        return self.titleProvider()

    def geometry_get(self) -> ChipDrawGeometry:
        """Return the canonical chip-local geometry object.

        Returns:
            `ChipDrawGeometry` carrying canonical local draw truth.
        """

        return self.geometryProvider()

    def geometry_sprint(self) -> str:
        """Render the canonical chip-local geometry as text.

        Returns:
            Multi-line text representation of the chip-local geometry.
        """

        return "\n".join(self.geometry_get().drawLines)

    def size_get(self) -> tuple[int, int]:
        """Return the rendered chip width and height in local cells.

        Returns:
            `(widthColumns, heightRows)` tuple for the chip-local geometry.
        """

        return self.sizeProvider()

    def dimensions_get(self) -> dict[str, int]:
        """Return rendered chip dimensions with explicit field names.

        Returns:
            Mapping with `widthColumns` and `heightRows`.
        """

        widthColumns, heightRows = self.size_get()
        return {
            "widthColumns": widthColumns,
            "heightRows": heightRows,
        }

    def width_get(self) -> int:
        """Return the rendered chip width in columns.

        Returns:
            Width of the chip-local geometry in columns.
        """

        return self.size_get()[0]

    def height_get(self) -> int:
        """Return the rendered chip height in rows.

        Returns:
            Height of the chip-local geometry in rows.
        """

        return self.size_get()[1]

    def terminals_get(self) -> dict[str, int]:
        """Return terminal counts by side.

        Returns:
            Mapping from side name to terminal count.
        """

        return self.terminalsProvider()

    def terminals_getLocalPositions(self, wall: str) -> ChipTerminalPositions:
        """Return local terminal positions for one wall.

        Args:
            wall: Lowercase wall name such as `west` or `east`.

        Returns:
            Mapping from terminal name to local `(columnIndex, rowIndex)`.
        """

        return self.localTerminalPositionsProvider(wall)

    def terminals_getWorldPositions(self, wall: str) -> ChipTerminalPositions:
        """Return world terminal positions for one wall when placed.

        Args:
            wall: Lowercase wall name such as `west` or `east`.

        Returns:
            Mapping from terminal name to world `(columnIndex, rowIndex)`.
        """

        return self.worldTerminalPositionsProvider(wall)

    def placement_get(self):
        """Return the primary raw placement result for this chip.

        Returns:
            Placement result/provider output for the chip.
        """

        return self.placementProvider()

    def location_get(self):
        """Return the primary location record for this chip.

        Returns:
            Primary location record when present, otherwise `None`.
        """

        return self.locationProvider()

    def locations_get(self):
        """Return all location records for this chip.

        Returns:
            Full collection of location records owned by this chip.
        """

        return self.locationsProvider()

    def routes_get(self):
        """Return solved chip-internal routes for this chip.

        Returns:
            Chip-local solved routes/provider output for this chip.
        """

        return self.routesProvider()

    def internalBoard_get(self) -> "BoardKernel":
        """Return the harmonized internal board kernel for this chip.

        Returns:
            `BoardKernel` representing the chip's internal wiring as a board problem.
        """

        return self.internalBoardProvider()

    def worldFrame_get(self):
        """Return the placed world frame for this chip when available.

        Returns:
            World-frame object/provider output when the chip is placed.
        """

        return self.worldFrameProvider()

    def children_get(self) -> tuple["BoardChip", ...]:
        """Return outgoing call targets as runtime chip objects.

        Returns:
            Tuple of child chips reached by outgoing calls.
        """

        return self.childrenProvider()

    def child_get(self, childIndex: int) -> "BoardChip":
        """Return one child chip by outgoing-call index.

        Args:
            childIndex: Zero-based outgoing call index to retrieve.

        Returns:
            Child chip at the requested outgoing-call index.
        """

        return self.children_get()[childIndex]

    def schematic_sprint(self) -> str:
        """Return the chip schematic text from canonical geometry.

        Returns:
            Multi-line schematic text for this chip.
        """

        return self.geometry_sprint()

    def summary_sprint(self) -> str:
        """Return a readable summary block for this chip.

        Returns:
            Multi-line summary text for this chip.
        """

        return self.summaryProvider()
