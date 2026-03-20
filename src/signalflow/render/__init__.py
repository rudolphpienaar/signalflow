"""Render layer for the new SignalFlow engine.

This package is the canonical render boundary.  Every module here consumes
only pre-built model objects and produces text output.  No topology
discovery, routing, or reclassification occurs in this package.

Modules
-------
chips   : Chip box rendering from Chip model objects.
routes  : World-canvas projection from RealizedRouteSet objects.
world   : Full world-canvas compositor (chips + routes into one grid).
"""
from __future__ import annotations

from signalflow.render.chips import chipLines_render
from signalflow.render.routes import RouteCanvasSize, routeWorldCanvas_render
from signalflow.render.world import worldCanvas_render

__all__: list[str] = [
    "chipLines_render",
    "RouteCanvasSize",
    "routeWorldCanvas_render",
    "worldCanvas_render",
]
