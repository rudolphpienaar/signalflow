"""Legacy SignalFlow implementation namespace.

This package quarantines the pre-re-architecture implementation so the new
layout, routing, render, and engine subsystems can evolve under the top-level
`signalflow` namespace with a clear boundary. Code inside this package is the
compatibility path and reference implementation, not the target architecture.

Key components:
    - config: Legacy rendering and layout configuration
    - engine: Legacy end-to-end rendering pipeline and router
    - lib: Legacy layout, drawing, and helper modules
    - models: Legacy mutable node/canvas/geometry models
    - scanner: Legacy source scanners
"""
from __future__ import annotations

