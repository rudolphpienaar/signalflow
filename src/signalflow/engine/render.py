"""Engine-dispatched document rendering for SignalFlow.

This module owns the runtime boundary between the top-level engine path and the
quarantined legacy engine path. The public entry point is `diagram_render`,
which delegates to the selected engine and returns printable output lines.

Key components:
    - diagram_render: Engine-dispatched document render entry point
    - newEngineStatus_render: Human-readable status report for the zone-grid path
"""
from __future__ import annotations

from signalflow.legacy.engine.render import diagram_render as diagramLegacy_render
from signalflow.models.engine import EngineName


def newEngineStatus_render(title: str, treeDict: dict[str, object]) -> list[str]:
    """Render the current new-engine runtime status as a readable report.

    The codebase now contains typed YAML-to-circuit ingress, canonical graph
    modeling, world topology, assignment, placement planning, and the first
    route-obligation layer. It still does not contain the chip/zone/interconnect/
    grid solvers. The runtime boundary should therefore report that status
    honestly instead of pretending that the removed `ChipLayout` prototype is
    still the active new-engine path.

    Args:
        title: Optional document title.
        treeDict: Parsed YAML document. It is accepted only so the public engine
            boundary remains stable while the zone-grid runtime is built.

    Returns:
        Printable output lines describing the current new-engine runtime status.
    """

    del treeDict

    lines: list[str] = []
    if title:
        lines.append(f"== {title} ==")
        lines.append("")
    lines.append("engine: new")
    lines.append("status: pending")
    lines.append("ingress: typed CircuitDocument")
    lines.append("worldModel: RoutingZoneGrid")
    lines.append("localModel: RoutingZone")
    lines.append("seamModel: RoutingZoneInterconnect")
    lines.append("planning: assignment + placement + route obligations")
    lines.append("message: zone-grid solver path is not implemented yet")
    return lines


def diagram_render(
    title: str,
    treeDict: dict[str, object],
    engineName: EngineName = EngineName.NEW,
) -> list[str]:
    """Render one document through the selected engine path.

    Args:
        title: Optional document title.
        treeDict: Parsed YAML document or raw `tree` payload.
        engineName: Explicit engine selector for dispatch.

    Returns:
        Printable output lines for the selected engine.
    """

    if engineName is EngineName.LEGACY:
        return diagramLegacy_render(title, treeDict)
    return newEngineStatus_render(title, treeDict)
