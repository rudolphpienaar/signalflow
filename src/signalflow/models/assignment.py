"""Assignment models bridging circuits into routing-zone worlds.

This module defines the planning layer that ties validated circuit graphs to
world topology. Assignment answers which canonical chip belongs to which
routing zone and on which terminal side of that zone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.models.calling_stack import (
    CallingStack,
    callingStackResult_buildFromCircuitDocument,
)
from signalflow.models.chip import ChipId, ChipRef
from signalflow.models.circuit import CircuitDocument
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.models.routing_zone import RoutingZoneId, RoutingZoneRegionSide


@dataclass(frozen=True)
class RoutingZoneLayer:
    """One graph-depth layer of canonical chips."""

    depthIndex: int
    chipRefs: tuple[ChipRef, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RoutingZoneLayerSet:
    """Modeled collection of graph-depth layers."""

    routingZoneLayers: tuple[RoutingZoneLayer, ...] = field(
        default_factory=tuple
    )

    def layerForDepthResult_get(
        self, depthIndex: int
    ) -> Result[RoutingZoneLayer]:
        """Get one depth layer by depth index."""

        routingZoneLayer: RoutingZoneLayer
        for routingZoneLayer in self.routingZoneLayers:
            if routingZoneLayer.depthIndex == depthIndex:
                return resultOk_build(routingZoneLayer)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.assignment.layer_set.missing_depth_layer",
            message="Requested RoutingZoneLayer is absent from the layer set",
            context=(str(depthIndex),),
        )
        return resultErr_build()


@dataclass(frozen=True)
class RoutingZoneAssignment:
    """Assignment of one canonical chip into one routing zone."""

    chipRef: ChipRef
    routingZoneId: RoutingZoneId
    terminalSide: RoutingZoneRegionSide


@dataclass(frozen=True)
class RoutingZoneAssignmentSet:
    """Modeled collection of routing-zone assignments for one circuit."""

    routingZoneAssignments: tuple[RoutingZoneAssignment, ...] = field(
        default_factory=tuple
    )

    def assignmentForChipResult_get(
        self,
        chipId: ChipId,
    ) -> Result[RoutingZoneAssignment]:
        """Get one zone assignment for one canonical chip."""

        routingZoneAssignment: RoutingZoneAssignment
        for routingZoneAssignment in self.routingZoneAssignments:
            if routingZoneAssignment.chipRef.chipId == chipId:
                return resultOk_build(routingZoneAssignment)
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.assignment.assignment_set.missing_chip_assignment",
            message="Requested chip is absent from the assignment set",
            context=(chipId.moduleName, chipId.functionName),
        )
        return resultErr_build()

    def assignmentsForZone_get(
        self,
        routingZoneId: RoutingZoneId,
    ) -> tuple[RoutingZoneAssignment, ...]:
        """Return assignments belonging to one routing zone."""

        return tuple(
            routingZoneAssignment
            for routingZoneAssignment in self.routingZoneAssignments
            if routingZoneAssignment.routingZoneId == routingZoneId
        )

    def assignmentsForZoneAndSide_get(
        self,
        routingZoneId: RoutingZoneId,
        terminalSide: RoutingZoneRegionSide,
    ) -> tuple[RoutingZoneAssignment, ...]:
        """Return assignments in one zone on one terminal side."""

        return tuple(
            routingZoneAssignment
            for routingZoneAssignment in self.routingZoneAssignments
            if (
                routingZoneAssignment.routingZoneId == routingZoneId
                and routingZoneAssignment.terminalSide is terminalSide
            )
        )


def routingZoneLayerSetResult_buildFromCircuitDocument(
    circuitDocument: CircuitDocument,
) -> Result[RoutingZoneLayerSet]:
    """Build routing-zone layers from one validated circuit document."""

    callingStackResult: Result[CallingStack] = (
        callingStackResult_buildFromCircuitDocument(circuitDocument)
    )
    if not result_isOkCheck(callingStackResult):
        return resultErr_build()
    return routingZoneLayerSetResult_build(
        routingZoneLayers=tuple(
            RoutingZoneLayer(
                depthIndex=level.depthIndex,
                chipRefs=level.chipRefs,
            )
            for level in callingStackResult.value.levels
        )
    )


def routingZoneLayerSetResult_build(
    routingZoneLayers: tuple[RoutingZoneLayer, ...],
) -> Result[RoutingZoneLayerSet]:
    """Build a validated routing-zone layer set."""

    depthIndices: tuple[int, ...] = tuple(
        routingZoneLayer.depthIndex for routingZoneLayer in routingZoneLayers
    )
    if len(set(depthIndices)) != len(depthIndices):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.assignment.layer_set.duplicate_depth_index",
            message="RoutingZoneLayer depth indices must be unique",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneLayerSet(routingZoneLayers=routingZoneLayers)
    )


def routingZoneAssignmentSetResult_build(
    routingZoneAssignments: tuple[RoutingZoneAssignment, ...],
) -> Result[RoutingZoneAssignmentSet]:
    """Build a validated routing-zone assignment set."""

    chipIds: tuple[ChipId, ...] = tuple(
        routingZoneAssignment.chipRef.chipId
        for routingZoneAssignment in routingZoneAssignments
    )
    if len(set(chipIds)) != len(chipIds):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.ROUTING,
            code="routing.assignment.assignment_set.duplicate_chip_assignment",
            message="Each chip may be assigned to only one routing zone",
        )
        return resultErr_build()
    return resultOk_build(
        RoutingZoneAssignmentSet(routingZoneAssignments=routingZoneAssignments)
    )
