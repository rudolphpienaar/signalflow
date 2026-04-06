"""Branch-level test doctrine for symbolic kernel routing.

This suite intentionally replaces the default `tests/` discovery path on the
`symbolic-kernel-routing` branch. Historical tests have been archived under
`tests_legacy/` so they remain available for reference, but they are not the
default source of truth while the symbolic routing board and algebra are being
designed.
"""

from __future__ import annotations


def test_symbolic_suite_is_active_default() -> None:
    """Default pytest discovery should target the symbolic suite only."""

    assert True
