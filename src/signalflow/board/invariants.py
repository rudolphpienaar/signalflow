"""Board-owned symbolic geometry invariants for one routing zone.

`ZoneSymbolicInvariants` derives the minimum geometry constraints needed by
`BoardGeometrySpec.with_invariants()`. These values are now owned by the
board layer rather than lifted from `RoutingZone.intraKernel`.

Two categories of fact live here:

Circuit-derived:
    - `maxLabelLength` — from terminal names in `CircuitDocument`
    - `wireDemand` — from intra-zone call edges in `CircuitDocument`
    - `latRows` — minimum latitude rows needed to host the directed wires
    - `minWLongSpan` / `minELongSpan` — minimum west/east longitude width

Policy-derived:
    - terminal and fan minima — from `boardGeometryConfig`
"""

from __future__ import annotations

from dataclasses import dataclass

from signalflow.config.board_defaults import boardGeometryConfig
from signalflow.models.assignment import RoutingZoneAssignmentSet
from signalflow.models.circuit import CircuitDocument
from signalflow.models.routing_zone import RoutingZone


@dataclass(frozen=True)
class ZoneSymbolicInvariants:
    """Minimum geometry constraints for one routing zone.

    Circuit-derived fields are computed solely from `CircuitDocument` and
    `RoutingZoneAssignmentSet` without consulting placed geometry. Policy
    minima come from `boardGeometryConfig`.

    Attributes:
        maxLabelLength: Maximum terminal label character width across all
            chips assigned to this zone. Drives the chip terminal column
            floor. Circuit-derived.
        wireDemand: Total intra-zone directed wire count (signal + return
            wires). Each intra circuit call contributes 2. Circuit-derived.
        latRows: Lat row count per band (nLat = sLat = latRows). Derived from
            directed wire demand with a floor of 1. Circuit-derived.
        minWChipTerminalSpan: West chip terminal column width floor. Policy-
            derived from `boardGeometryConfig`.
        minEChipTerminalSpan: East chip terminal column width floor. Policy-
            derived from `boardGeometryConfig`.
        minWFanSpan: West fan in/out column width floor. Policy-derived from
            `boardGeometryConfig`.
        minEFanSpan: East fan in/out column width floor. Policy-derived from
            `boardGeometryConfig`.
        minWLongSpan: West longitude column width floor. Derived from directed
            wire demand with a floor of 1. Circuit-derived.
        minELongSpan: East longitude column width floor. Derived from directed
            wire demand with a floor of 1. Circuit-derived.
    """

    # circuit-derived
    maxLabelLength: int
    wireDemand: int

    # board-owned minima
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
            routingZone: Placed routing zone. Used only for its zone id; this
                builder no longer reads `routingZone.intraKernel`.
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
                maxLabelLength = max(
                    maxLabelLength, len(terminal.terminalName)
                )

        wireDemand: int = 0
        for call in circuitDocument.circuitCallSet.circuitCalls:
            if (
                call.sourceChipRef.chipId in zoneChipIds
                and call.destinationChipRef.chipId in zoneChipIds
            ):
                wireDemand += 2  # signal wire + return wire

        # --- board-owned minima ---

        latRows = max(1, wireDemand)
        minWChipTerminalSpan = boardGeometryConfig.intraWTerminalSpan
        minEChipTerminalSpan = boardGeometryConfig.intraETerminalSpan
        minWFanSpan = boardGeometryConfig.intraWFanSpan
        minEFanSpan = boardGeometryConfig.intraEFanSpan
        minWLongSpan = max(1, wireDemand)
        minELongSpan = max(1, wireDemand)

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
        circuitTag = "[circuit-derived]"
        policyTag = "[policy-derived]"
        return "\n".join(
            [
                "ZoneSymbolicInvariants:",
                f"  maxLabelLength       : {self.maxLabelLength}  "
                f"{circuitTag}",
                f"  wireDemand           : {self.wireDemand}  "
                f"{circuitTag}",
                f"  latRows              : {self.latRows}  {circuitTag}",
                f"  minWChipTerminalSpan : {self.minWChipTerminalSpan}  "
                f"{policyTag}",
                f"  minEChipTerminalSpan : {self.minEChipTerminalSpan}  "
                f"{policyTag}",
                f"  minWFanSpan          : {self.minWFanSpan}  "
                f"{policyTag}",
                f"  minEFanSpan          : {self.minEFanSpan}  "
                f"{policyTag}",
                f"  minWLongSpan         : {self.minWLongSpan}  "
                f"{circuitTag}",
                f"  minELongSpan         : {self.minELongSpan}  "
                f"{circuitTag}",
            ]
        )
