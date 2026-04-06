"""Board backend toggle helpers for debug surfaces."""

from __future__ import annotations

import os

_BOARD_BACKEND: str = (
    os.getenv("SIGNALFLOW_BOARD_BACKEND", "new").strip().lower()
)


def boardBackend_resolved_build(candidate: str | None = None) -> str:
    """Return the normalized board backend name."""

    normalized = (
        (_BOARD_BACKEND if candidate is None else candidate).strip().lower()
    )
    if normalized not in {"legacy", "new"}:
        return "new"
    return normalized


def boardBackend_get() -> str:
    """Return the active board backend name."""

    return boardBackend_resolved_build()


def boardBackend_set(backendName: str) -> str:
    """Set the active board backend and return the resolved backend name."""

    global _BOARD_BACKEND
    _BOARD_BACKEND = boardBackend_resolved_build(backendName)
    return _BOARD_BACKEND


__all__ = [
    "boardBackend_get",
    "boardBackend_resolved_build",
    "boardBackend_set",
]
