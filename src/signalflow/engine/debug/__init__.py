"""Compatibility shim for the renamed `signalflow.engine.inspect` package."""

from __future__ import annotations

from signalflow.engine import inspect as _inspect


def __getattr__(name: str):
    return getattr(_inspect, name)
