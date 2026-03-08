"""Pre-render geometry invariant assertions.

geometry_validate(nodes) is called by diagram_render after layout_compute
and before any drawing.  It fails loudly with a precise diagnostic on the
first violation — converting the silent-wrong-output class of bug into an
immediate AssertionError pointing at the formula.
"""
from __future__ import annotations

from signalflow.models import Node


def geometry_validate(nodes: list[Node]) -> None:
    """Assert all geometry invariants before rendering begins.

    Raises AssertionError with a diagnostic on the first violation.
    """
    n: Node
    for n in nodes:
        from signalflow.models.chip_geometry import ChipGeometry
        geo: ChipGeometry | None = n.geometry
        assert geo is not None and geo.resolved, (
            f"{n.func}: geometry not resolved — layout_compute must run first"
        )

        # 1. Every right-wall port row lies within [anchorFloor, interiorMax]
        port: str
        rows: list[int]
        for port, rows in geo.rightWallRows.items():
            row: int
            for row in rows:
                assert geo.anchorFloor <= row <= geo.interiorMax, (
                    f"{n.func}: rightWallRows[{port!r}] row {row} "
                    f"outside [{geo.anchorFloor}, {geo.interiorMax}] "
                    f"(ewOff={geo.ewOff}, chipH={geo.chipH})"
                )

        # 2. E→W trunk zone [y+3, anchorFloor) must not overlap wall terminals
        if geo.ewOff > 0:
            ew_zone: set[int] = set(range(n.y + 3, geo.anchorFloor))
            terminal_rows: set[int] = {r for rs in geo.rightWallRows.values() for r in rs}
            overlap: set[int] = ew_zone & terminal_rows
            assert not overlap, (
                f"{n.func}: E→W trunk zone {sorted(ew_zone)} "
                f"overlaps right-wall terminal rows {sorted(overlap)}"
            )

        # 3. All anchor rows lie within [anchorFloor, interiorMax]
        for port, rows in geo.allAnchorRows.items():
            for row in rows:
                assert geo.anchorFloor <= row <= geo.interiorMax, (
                    f"{n.func}: allAnchorRows[{port!r}] row {row} "
                    f"outside [{geo.anchorFloor}, {geo.interiorMax}]"
                )

        # 4. No duplicate anchor rows per port
        for port, rows in geo.allAnchorRows.items():
            assert len(set(rows)) == len(rows), (
                f"{n.func}: duplicate anchor rows for port {port!r}: {rows}"
            )

        # 5. Anchor row count matches lCounts
        cnt: int
        for port, cnt in geo.lCounts.items():
            actual: int = len(geo.allAnchorRows.get(port, []))
            assert actual == cnt, (
                f"{n.func}: lCounts[{port!r}]={cnt} but "
                f"allAnchorRows has {actual} rows"
            )
