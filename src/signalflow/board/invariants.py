"""Circuit-derived and placement-lifted zone geometry invariants.

`ZoneSymbolicInvariants` derives the minimum geometry constraints for one
routing zone. Two categories of fact live here:

Circuit-derived (purely symbolic, no placed geometry needed):
    - `maxLabelLength` — from terminal names in `CircuitDocument`
    - `wireDemand` — from intra-zone call edges in `CircuitDocument`

Placement-lifted (read from the solver's already-placed region frames):
    - all span minimums and `latRows` — from `RoutingZone.intraKernel`

The placement-lifted values will be progressively replaced by direct
circuit derivation as `ZoneSymbolicInvariants` matures (Phase C+). Until
then the placed frames are the authoritative minimum — the solver has
already done the right arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass

from signalflow.models.assignment import RoutingZoneAssignmentSet
from signalflow.models.circuit import CircuitDocument
from signalflow.models.routing_zone import (
    RoutingZone,
    RoutingZoneRegionKind,
    RoutingZoneRegionSide,
)


@dataclass(frozen=True)
class ZoneSymbolicInvariants:
    """Minimum geometry constraints for one routing zone.

    Circuit-derived fields are computed solely from `CircuitDocument` and
    `RoutingZoneAssignmentSet` without consulting placed geometry.
    Placement-lifted fields read the already-solved region frames from
    `RoutingZone.intraKernel`; they are 0 when no kernel is present.

    Attributes:
        maxLabelLength: Maximum terminal label character width across all
            chips assigned to this zone. Drives the chip terminal column
            floor. Circuit-derived.
        wireDemand: Total intra-zone directed wire count (signal + return
            wires). Each intra circuit call contributes 2. Circuit-derived.
        latRows: Lat row count per band (nLat = sLat = latRows). Read from
            the placed north latitude region verticalSpan. 0 if no kernel.
        minWChipTerminalSpan: West chip terminal column width. Placement-lifted.
        minEChipTerminalSpan: East chip terminal column width. Placement-lifted.
        minWFanSpan: West fan in/out column width. Placement-lifted.
        minEFanSpan: East fan in/out column width. Placement-lifted.
        minWLongSpan: West longitude column width. Placement-lifted.
        minELongSpan: East longitude column width. Placement-lifted.
    """

    # circuit-derived
    maxLabelLength: int
    wireDemand: int

    # placement-lifted
    latRows: int
    minWChipTerminalSpan: int
    minEChipTerminalSpan: int
    minWFanSpan: int
    minEFanSpan: int
    minWLongSpan: int
    minELongSpan: int

    @classmethod
    def build(
        cls,
        circuitDocument: CircuitDocument,
        routingZone: RoutingZone,
        assignmentSet: RoutingZoneAssignmentSet,
    ) -> ZoneSymbolicInvariants:
        """Derive invariants for one routing zone.

        Args:
            circuitDocument: Validated circuit graph (chips + call edges).
            routingZone: Placed routing zone, including the intra kernel
                whose region frames supply placement-lifted minimums.
            assignmentSet: Zone assignment map used to identify which chips
                belong to this zone.

        Returns:
            Populated `ZoneSymbolicInvariants` instance.
        """
        zoneId = routingZone.routingZoneId
        zoneAssignments = assignmentSet.assignmentsForZone_get(zoneId)
        zoneChipIds = {a.chipRef.chipId for a in zoneAssignments}

        # --- circuit-derived ---

        maxLabelLength: int = 0
        for chip in circuitDocument.circuitChipSet.chips:
            if chip.chipId not in zoneChipIds:
                continue
            for terminal in chip.chipTerminalSet.terminals:
                maxLabelLength = max(maxLabelLength, len(terminal.terminalName))

        wireDemand: int = 0
        for call in circuitDocument.circuitCallSet.circuitCalls:
            if (
                call.sourceChipRef.chipId in zoneChipIds
                and call.destinationChipRef.chipId in zoneChipIds
            ):
                wireDemand += 2  # signal wire + return wire

        # --- placement-lifted ---

        latRows: int = 0
        minWChipTerminalSpan: int = 0
        minEChipTerminalSpan: int = 0
        minWFanSpan: int = 0
        minEFanSpan: int = 0
        minWLongSpan: int = 0
        minELongSpan: int = 0

        kernel = routingZone.intraKernel
        if kernel is not None:
            for region in kernel.routingZoneRegionSet.routingZoneRegions:
                rid = region.routingZoneRegionId
                kind = rid.routingZoneRegionKind
                side = rid.routingZoneRegionSide
                hspan = region.routingZoneRegionFrame.horizontalSpan
                vspan = region.routingZoneRegionFrame.verticalSpan

                if kind is RoutingZoneRegionKind.CHIP_TERMINAL:
                    if side is RoutingZoneRegionSide.WEST:
                        minWChipTerminalSpan = max(minWChipTerminalSpan, hspan)
                    elif side is RoutingZoneRegionSide.EAST:
                        minEChipTerminalSpan = max(minEChipTerminalSpan, hspan)

                elif kind is RoutingZoneRegionKind.INTRA_ROUTING_FAN_IN_OUT:
                    if side is RoutingZoneRegionSide.WEST:
                        minWFanSpan = max(minWFanSpan, hspan)
                    elif side is RoutingZoneRegionSide.EAST:
                        minEFanSpan = max(minEFanSpan, hspan)

                elif kind is RoutingZoneRegionKind.INTRA_ROUTING_LONGITUDE:
                    if side is RoutingZoneRegionSide.WEST:
                        minWLongSpan = max(minWLongSpan, hspan)
                    elif side is RoutingZoneRegionSide.EAST:
                        minELongSpan = max(minELongSpan, hspan)

                elif kind is RoutingZoneRegionKind.INTRA_ROUTING_LATITUDE:
                    if side is RoutingZoneRegionSide.NORTH:
                        latRows = max(latRows, vspan)

        return cls(
            maxLabelLength=maxLabelLength,
            wireDemand=wireDemand,
            latRows=latRows,
            minWChipTerminalSpan=minWChipTerminalSpan,
            minEChipTerminalSpan=minEChipTerminalSpan,
            minWFanSpan=minWFanSpan,
            minEFanSpan=minEFanSpan,
            minWLongSpan=minWLongSpan,
            minELongSpan=minELongSpan,
        )

    def invariants_sprint(self) -> str:
        """Return a human-readable summary of all invariant values."""
        return "\n".join([
            "ZoneSymbolicInvariants:",
            f"  maxLabelLength       : {self.maxLabelLength}  [circuit-derived]",
            f"  wireDemand           : {self.wireDemand}  [circuit-derived]",
            f"  latRows              : {self.latRows}  [placement-lifted]",
            f"  minWChipTerminalSpan : {self.minWChipTerminalSpan}  [placement-lifted]",
            f"  minEChipTerminalSpan : {self.minEChipTerminalSpan}  [placement-lifted]",
            f"  minWFanSpan          : {self.minWFanSpan}  [placement-lifted]",
            f"  minEFanSpan          : {self.minEFanSpan}  [placement-lifted]",
            f"  minWLongSpan         : {self.minWLongSpan}  [placement-lifted]",
            f"  minELongSpan         : {self.minELongSpan}  [placement-lifted]",
        ])
