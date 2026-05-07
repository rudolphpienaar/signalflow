"""Semantic wiring invariant tests.

These tests verify structural correctness of rendered world-grid output
rather than exact string equality.  They survive layout changes and catch
rendering algebra bugs (wrong crossing characters, orphaned half-junctions)
that snapshot tests cannot see.

Invariants checked:

1. Double-line crossing characters (╫, ╪) appear only next to a module-box
   border glyph (║ or ═) in the same row or column.

2. Every single-line junction character (├ ┤ ┬ ┴ ┼) has at least two
   neighbours that are compatible box-drawing chars.  An isolated junction
   would indicate a half-wire left over from bad crossing algebra.

3. Horizontal wire continuity: every interior ─ cell has both a left and a
   right neighbour that are box-drawing glyphs (not a plain space).

4. Vertical wire continuity: every interior │ cell has both an above and a
   below neighbour that are box-drawing glyphs.

These invariants are example-agnostic and can be applied to any rendered
wiring grid.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from signalflow.engine.world_render import worldMaterializedSolution_build
from signalflow.board.world_runtime import BoardWorldMaterializedSolution


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _exampleDict_load(name: str) -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parent.parent / "examples" / name
    )
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


import re as _re

_ROW_LINE: _re.Pattern[str] = _re.compile(r"^\s*(\d+): (.*)$")


def _wiringGrid_build(exampleName: str) -> list[list[str]]:
    """Return the rendered world-wiring grid for an example as a 2-D char list.

    The returned list is indexed by *world row* (sparse rows are empty lists).
    """
    docDict = _exampleDict_load(exampleName)
    solution: BoardWorldMaterializedSolution = (
        worldMaterializedSolution_build(docDict)
    )
    indexes = sorted(solution.materializedByIndex)
    rendered: str = solution.wiring_sprint(indexes)
    # Build a sparse dict from world-row-index → list[str]
    rowByIndex: dict[int, list[str]] = {}
    for line in rendered.splitlines():
        m = _ROW_LINE.match(line)
        if m:
            rowByIndex[int(m.group(1))] = list(m.group(2))
    if not rowByIndex:
        return []
    maxRow = max(rowByIndex)
    return [rowByIndex.get(r, []) for r in range(maxRow + 1)]


# ---------------------------------------------------------------------------
# Character taxonomy
# ---------------------------------------------------------------------------

_DOUBLE_CROSS_V = "╫"   # double-vertical × single-horizontal
_DOUBLE_CROSS_H = "╪"   # single-vertical × double-horizontal

_MODULE_BORDER_V = "║"  # double-vertical (module box wall)
_MODULE_BORDER_H = "═"  # double-horizontal (module box wall)

_BOX_DRAWING: frozenset[str] = frozenset(
    "─│┌┐└┘├┤┬┴┼║═╫╪╔╗╚╝╠╣╦╩╬◄►"
)

_JUNCTION: frozenset[str] = frozenset("├┤┬┴┼")

# ---------------------------------------------------------------------------
# Invariant check functions
# ---------------------------------------------------------------------------

def _doubleCross_adjacency_check(
    grid: list[list[str]],
) -> list[str]:
    """╫ must appear only in a column that also contains ║.
    ╪ must appear only in a row that also contains ═.

    When multiple routes cross one module-box border, a run of consecutive
    ╫ cells forms (each surrounded only by other ╫ cells), so direct
    neighbour checks are insufficient.  The column/row scope check is
    layout-agnostic and catches any ╫/╪ that is not part of a real module
    box crossing.
    """
    # Build per-column set of characters for the ╫ check.
    max_cols = max((len(row) for row in grid), default=0)
    cols_chars: list[set[str]] = [set() for _ in range(max_cols)]
    for row in grid:
        for c, ch in enumerate(row):
            cols_chars[c].add(ch)

    violations: list[str] = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch == _DOUBLE_CROSS_V:
                if _MODULE_BORDER_V not in cols_chars[c]:
                    violations.append(
                        f"  row {r} col {c}: '╫' in column with no '║' — "
                        f"not a module-box crossing"
                    )
            elif ch == _DOUBLE_CROSS_H:
                if _MODULE_BORDER_H not in {row[cc] for cc in range(len(row))}:
                    violations.append(
                        f"  row {r} col {c}: '╪' in row with no '═' — "
                        f"not a module-box crossing"
                    )
    return violations


def _junction_connectivity_check(
    grid: list[list[str]],
) -> list[str]:
    """Every T/cross junction must have ≥ 2 box-drawing neighbours."""
    violations: list[str] = []
    rows = len(grid)
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch not in _JUNCTION:
                continue
            line = row
            cols = len(line)
            neighbours: list[str] = []
            if c > 0:
                neighbours.append(line[c - 1])
            if c + 1 < cols:
                neighbours.append(line[c + 1])
            if r > 0 and c < len(grid[r - 1]):
                neighbours.append(grid[r - 1][c])
            if r + 1 < rows and c < len(grid[r + 1]):
                neighbours.append(grid[r + 1][c])
            count = sum(1 for n in neighbours if n in _BOX_DRAWING)
            if count < 2:
                violations.append(
                    f"  row {r} col {c}: '{ch}' has only {count} box-drawing "
                    f"neighbour(s) — orphaned junction"
                )
    return violations


def _horizontalWire_continuity_check(
    grid: list[list[str]],
) -> list[str]:
    """Interior ─ cells must have a box-drawing char on both sides."""
    violations: list[str] = []
    for r, row in enumerate(grid):
        cols = len(row)
        for c, ch in enumerate(row):
            if ch != "─":
                continue
            if c == 0 or c == cols - 1:
                continue  # edge cells are allowed to terminate
            left  = row[c - 1]
            right = row[c + 1]
            if left == " " or right == " ":
                violations.append(
                    f"  row {r} col {c}: '─' has blank neighbour "
                    f"(left='{left}' right='{right}') — broken H-wire"
                )
    return violations


def _verticalWire_continuity_check(
    grid: list[list[str]],
) -> list[str]:
    """Interior │ cells must have a box-drawing char above and below."""
    violations: list[str] = []
    rows = len(grid)
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch != "│":
                continue
            if r == 0 or r == rows - 1:
                continue
            above = (
                grid[r - 1][c]
                if c < len(grid[r - 1]) else " "
            )
            below = (
                grid[r + 1][c]
                if c < len(grid[r + 1]) else " "
            )
            if above == " " or below == " ":
                violations.append(
                    f"  row {r} col {c}: '│' has blank neighbour "
                    f"(above='{above}' below='{below}') — broken V-wire"
                )
    return violations


# ---------------------------------------------------------------------------
# Parametrized examples
# ---------------------------------------------------------------------------

_EXAMPLES: list[str] = [
    "simple-circuit/back-and-forth.yaml",
    "simple-circuit/three-deep-linear.yaml",
    "simple-circuit/neural-network.yaml",
    "simple-circuit/rearch-external-forward.yaml",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

import pytest


@pytest.mark.parametrize("example", _EXAMPLES)
def test_double_cross_chars_only_at_module_borders(example: str) -> None:
    """╫ and ╪ must appear only where a module-box border (║ or ═) is adjacent."""
    grid = _wiringGrid_build(example)
    violations = _doubleCross_adjacency_check(grid)
    assert not violations, (
        f"{example}: spurious double-cross characters found:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize("example", _EXAMPLES)
def test_junction_chars_have_two_box_drawing_neighbours(example: str) -> None:
    """Every T/cross junction glyph must connect to at least two box-drawing neighbours."""
    grid = _wiringGrid_build(example)
    violations = _junction_connectivity_check(grid)
    assert not violations, (
        f"{example}: orphaned junction characters found:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize("example", _EXAMPLES)
def test_horizontal_wires_are_continuous(example: str) -> None:
    """Interior ─ cells must not have a blank space on either side."""
    grid = _wiringGrid_build(example)
    violations = _horizontalWire_continuity_check(grid)
    assert not violations, (
        f"{example}: broken horizontal wire segments:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize("example", _EXAMPLES)
def test_vertical_wires_are_continuous(example: str) -> None:
    """Interior │ cells must not have a blank space above or below."""
    grid = _wiringGrid_build(example)
    violations = _verticalWire_continuity_check(grid)
    assert not violations, (
        f"{example}: broken vertical wire segments:\n"
        + "\n".join(violations)
    )
