from __future__ import annotations

from typing import Any, Mapping, TypedDict


class SignalFlowDocumentDict(TypedDict, total=False):
    """Structural schema for one SignalFlow YAML document."""

    title: str
    tree: Mapping[str, Any]
    world: Mapping[str, Any]
