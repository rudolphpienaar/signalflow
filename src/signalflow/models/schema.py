from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict


class SignalFlowDocumentDict(TypedDict, total=False):
    """Structural schema for one SignalFlow YAML document."""

    title: str
    tree: Mapping[str, Any]
    world: Mapping[str, Any]
