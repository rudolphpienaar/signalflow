"""Shared engine-boundary models for SignalFlow.

This module defines the small typed vocabulary needed to make the engine
boundary explicit in code. The current boundary is between the `legacy` path
and the top-level SignalFlow engine path.

Key components:
    - EngineName: Explicit engine selector for render dispatch
"""
from __future__ import annotations

from enum import Enum


class EngineName(Enum):
    """Explicit engine selector for render dispatch.

    Attributes:
        NEW: Top-level SignalFlow engine path.
        LEGACY: Quarantined compatibility engine path.

    Example:
        >>> engineName = EngineName.NEW
    """

    NEW = "new"
    LEGACY = "legacy"
