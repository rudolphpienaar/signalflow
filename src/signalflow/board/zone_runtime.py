"""Runtime zone object for the quarantine board surface.

This module exposes the first-class runtime zone object used by the REPL and
debug-facing board workflow. A `BoardZone` is an operator-oriented façade over
placed routing-zone data, routed views, and kernel access.

Key components:
    - BoardZone: Runtime zone object exposing kernels, placements, and routes

Typical usage:
    zone = zones.zone_get(1, 1)
    kernel = zone.kernel_get("intra")
    print(zone.world_text())

Dependencies:
    - Requires canonical routing-zone identity from `signalflow.models`
    - Delegates kernel solve/render work to `BoardKernel`
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from signalflow.models import RoutingZoneId


@dataclass(frozen=True)
class BoardZone:
    """Runtime zone object for operator-facing zone inspection.

    Attributes:
        routingZoneId: Stable zone identity.
        rawProvider: Deferred provider for the raw routing-zone model.
        areasProvider: Deferred provider for area collection access.
        areaProvider: Deferred provider for individual area lookup.
        idProvider: Deferred provider for stable zone identity text/object.
        senseProvider: Deferred provider for routing sense.
        placementsProvider: Deferred provider for chip placement records.
        routesProvider: Deferred provider for solved route objects.
        routesTextProvider: Deferred provider for readable route text.
        schematicProvider: Deferred provider for schematic zone text.
        worldProvider: Deferred provider for rendered world-local zone text.
        kernelsProvider: Deferred provider for all kernels in this zone.
        kernelProvider: Deferred provider for one kernel by side.
        summaryProvider: Deferred provider for zone summary text.
    """

    routingZoneId: RoutingZoneId
    rawProvider: Callable[[], object]
    areasProvider: Callable[[], object]
    areaProvider: Callable[[str, str | None], object]
    idProvider: Callable[[], object]
    senseProvider: Callable[[], object]
    placementsProvider: Callable[[], object]
    routesProvider: Callable[[], object]
    routesTextProvider: Callable[[], str]
    schematicProvider: Callable[[], str]
    worldProvider: Callable[[], str]
    kernelsProvider: Callable[[], dict[str, "BoardKernel"]]
    kernelProvider: Callable[[str], "BoardKernel" | None]
    summaryProvider: Callable[[], str]

    def __dir__(self) -> list[str]:
        """Return the curated public zone inspection surface.

        Returns:
            Public zone methods intended for interactive use.
        """

        return [
            "area_get",
            "areas_get",
            "id_get",
            "kernel_get",
            "kernels_get",
            "placements_get",
            "raw_get",
            "routes_get",
            "routes_text",
            "schematic_text",
            "sense_get",
            "summary_text",
            "world_text",
        ]

    def raw_get(self):
        """Return the raw routing-zone model.

        Returns:
            Underlying placed routing-zone model for this runtime zone.
        """

        return self.rawProvider()

    def areas_get(self):
        """Return the area collection for this zone.

        Returns:
            Area collection/provider output for this zone.
        """

        return self.areasProvider()

    def area_get(self, kindOrKey: str, side: str | None = None):
        """Return one area by kind/key and optional side.

        Args:
            kindOrKey: Area kind or fully qualified area key.
            side: Optional side selector such as `west` or `east`.

        Returns:
            Matching area/provider output when available.
        """

        return self.areaProvider(kindOrKey, side)

    def id_get(self):
        """Return the stable zone id.

        Returns:
            Stable zone id/provider output.
        """

        return self.idProvider()

    def sense_get(self):
        """Return the routing sense of this zone.

        Returns:
            Routing sense/provider output for this zone.
        """

        return self.senseProvider()

    def placements_get(self):
        """Return placement records owned by this zone.

        Returns:
            Placement record/provider output for this zone.
        """

        return self.placementsProvider()

    def routes_get(self):
        """Return solved routes owned by this zone.

        Returns:
            Solved routes/provider output for this zone.
        """

        return self.routesProvider()

    def routes_text(self) -> str:
        """Return a readable text view of this zone's routes.

        Returns:
            Multi-line route text for this zone.
        """

        return self.routesTextProvider()

    def schematic_text(self) -> str:
        """Return a schematic overview of this zone.

        Returns:
            Multi-line schematic text for this zone.
        """

        return self.schematicProvider()

    def world_text(self) -> str:
        """Return the rendered world-local zone view.

        Returns:
            World-local rendered text for this zone.
        """

        return self.worldProvider()

    def kernels_get(self) -> dict[str, "BoardKernel"]:
        """Return all kernels exposed by this zone.

        Returns:
            Mapping from kernel side name to runtime kernel object.
        """

        return self.kernelsProvider()

    def kernel_get(self, side: str = "intra") -> "BoardKernel" | None:
        """Return one kernel by side when present.

        Args:
            side: Kernel side identifier such as `intra`.

        Returns:
            Matching runtime kernel when present, otherwise `None`.
        """

        return self.kernelProvider(side)

    def summary_text(self) -> str:
        """Return a readable summary block for this zone.

        Returns:
            Multi-line summary text for this zone.
        """

        return self.summaryProvider()
