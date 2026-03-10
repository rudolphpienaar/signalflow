"""Pre-render geometry invariant assertions.

geometry_validate(nodes) is called by diagram_render after layout_compute
and before any drawing.  It fails loudly with a precise diagnostic on the
first violation — converting the silent-wrong-output class of bug into an
immediate AssertionError pointing at the formula.
"""
from __future__ import annotations

from signalflow.models import Node


def _rightWallRows_validate(node: Node) -> None:
    """Assert that every right-wall terminal row lies inside the chip interior."""
    from signalflow.models.chip_geometry import ChipGeometry

    geo: ChipGeometry | None = node.geometry
    assert geo is not None
    port: str
    rows: list[int]
    for port, rows in geo.rightWallRows.items():
        row: int
        for row in rows:
            assert geo.anchorFloor <= row <= geo.interiorMax, (
                f"{node.func}: rightWallRows[{port!r}] row {row} "
                f"outside [{geo.anchorFloor}, {geo.interiorMax}] "
                f"(ewOff={geo.ewOff}, chipH={geo.chipH})"
            )


def _ewZone_validate(node: Node) -> None:
    """Assert that the E→W trunk zone does not overlap right-wall terminals."""
    from signalflow.models.chip_geometry import ChipGeometry

    geo: ChipGeometry | None = node.geometry
    assert geo is not None
    if geo.ewOff <= 0:
        return
    ew_zone: set[int] = set(range(node.y + 3, geo.anchorFloor))
    terminal_rows: set[int] = {
        row for rows in geo.rightWallRows.values() for row in rows
    }
    overlap: set[int] = ew_zone & terminal_rows
    assert not overlap, (
        f"{node.func}: E→W trunk zone {sorted(ew_zone)} "
        f"overlaps right-wall terminal rows {sorted(overlap)}"
    )


def _anchorRows_validate(node: Node) -> None:
    """Assert anchor rows stay inside chip bounds and avoid per-port duplication."""
    from signalflow.models.chip_geometry import ChipGeometry

    geo: ChipGeometry | None = node.geometry
    assert geo is not None
    port: str
    rows: list[int]
    for port, rows in geo.allAnchorRows.items():
        for row in rows:
            assert geo.anchorFloor <= row <= geo.interiorMax, (
                f"{node.func}: allAnchorRows[{port!r}] row {row} "
                f"outside [{geo.anchorFloor}, {geo.interiorMax}]"
            )
        assert len(set(rows)) == len(rows), (
            f"{node.func}: duplicate anchor rows for port {port!r}: {rows}"
        )


def _anchorCounts_validate(node: Node) -> None:
    """Assert anchor-row counts match manifold endpoint density."""
    from signalflow.models.chip_geometry import ChipGeometry

    geo: ChipGeometry | None = node.geometry
    assert geo is not None
    port: str
    cnt: int
    for port, cnt in geo.lCounts.items():
        actual: int = len(geo.allAnchorRows.get(port, []))
        assert actual == cnt, (
            f"{node.func}: lCounts[{port!r}]={cnt} but "
            f"allAnchorRows has {actual} rows"
        )


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
        _rightWallRows_validate(n)
        _ewZone_validate(n)
        _anchorRows_validate(n)
        _anchorCounts_validate(n)
