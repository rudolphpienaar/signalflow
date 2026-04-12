"""First-order geometry coupling doctrine for board-owned geometry.

This module defines explicit coupling rules between one anchor geometry zone
and the dependent geometry that must move or remain enclosed when that anchor
changes. The first concrete family is the chip-terminal family.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from signalflow.board.geometry.mutation import boardRegionId_buildFromNotation
from signalflow.board.geometry.symbolic import RegionOperand
from signalflow.board.geometry.zones import BoardGeometry, GeometryZone
from signalflow.board.types import (
    BoardChipDrawPlacement,
    BoardRegionId,
    BoardSide,
    RegionFamily,
    TerminalPositionsByChip,
    WorldPoint,
)
from signalflow.models import RoutingZoneRegionFrame
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.notation.sfn import sfN


class GeometryCouplingOp(StrEnum):
    """Geometry coupling operators.

    Operators:
        PROPAGATES_DRAG: Anchor move rigidly drags dependent with it (``~=>``).
        PROPAGATES_DISPLACE: Anchor move opens space, dependent may shift
            downstream (``~->``).
        PROPAGATES_STRETCH: Anchor move shifts one named face of the dependent
            token, leaving the opposite face fixed (``~+>``). Used when a
            corner token moves and stretches an adjacent cardinal band.
        CONTAINS: Dependent must remain enclosed by anchor at all times
            (``[]=``).
        CONTINUITY: Token must remain topologically connected inside a named
            continuity group after any move (``~~``). This is the first
            topology-backed operator; it is evaluated against a
            ``BoardTopologySchema`` rather than against concrete region ids.
    """

    PROPAGATES_DRAG = "~=>"
    PROPAGATES_DISPLACE = "~->"
    PROPAGATES_STRETCH = "~+>"
    CONTAINS = "[]="
    CONTINUITY = "~~"


class GeometryDependentKind(StrEnum):
    """Kinds of dependent geometry addressed by coupling doctrine."""

    CHIPS = "chips"
    TERMINALS = "terminals"
    MODULE = "module"
    GEOMETRY_ZONE = "geometry_zone"


@dataclass(frozen=True)
class GeometryCollectionOperand:
    """Symbolic dependent operand for a zone-owned collection."""

    zoneRef: str
    kind: GeometryDependentKind


@dataclass(frozen=True)
class GeometryModuleOperand:
    """Symbolic dependent operand for one module boundary."""

    zoneRef: str
    moduleName: str


@dataclass(frozen=True)
class GeometryCouplingZoneOperand:
    """Symbolic zone root for coupling tuple expressions."""

    label: str

    def __getattr__(self, name: str) -> RegionOperand:
        region = sfN.__members__.get(name)
        if region is None:
            raise AttributeError(
                f"{self.__class__.__name__!s} has no symbolic region {name!r}"
            )
        return RegionOperand(zoneRef=self.label, region=region)

    @property
    def chips(self) -> GeometryCollectionOperand:
        """Return symbolic chips dependent operand."""

        return GeometryCollectionOperand(
            zoneRef=self.label,
            kind=GeometryDependentKind.CHIPS,
        )

    @property
    def terminals(self) -> GeometryCollectionOperand:
        """Return symbolic terminals dependent operand."""

        return GeometryCollectionOperand(
            zoneRef=self.label,
            kind=GeometryDependentKind.TERMINALS,
        )

    def moduleOperand_build(self, moduleName: str) -> GeometryModuleOperand:
        """Return symbolic module-boundary operand."""

        return GeometryModuleOperand(
            zoneRef=self.label,
            moduleName=moduleName,
        )


GeometryCouplingSymbolicRhs: TypeAlias = (
    RegionOperand | GeometryCollectionOperand | GeometryModuleOperand
)
GeometryCouplingSymbolicExpr: TypeAlias = tuple[
    RegionOperand,
    str | GeometryCouplingOp,
    GeometryCouplingSymbolicRhs,
]


def zoneCouplingOperandResult_build(
    label: str,
) -> Result[GeometryCouplingZoneOperand]:
    """Build one symbolic zone root for coupling tuples."""

    if not label:
        return resultErr_build()
    return resultOk_build(GeometryCouplingZoneOperand(label=label))


def zoneCouplingOperandsResult_build(
    *labels: str,
) -> Result[tuple[GeometryCouplingZoneOperand, ...]]:
    """Build symbolic coupling-zone roots."""

    operands: list[GeometryCouplingZoneOperand] = []
    for label in labels:
        operandResult = zoneCouplingOperandResult_build(label)
        if not result_isOkCheck(operandResult):
            return resultErr_build()
        operands.append(operandResult.value)
    return resultOk_build(tuple(operands))


@dataclass(frozen=True)
class GeometryDependentRef:
    """One dependent target in a coupling rule."""

    kind: GeometryDependentKind
    moduleName: str | None = None
    regionId: BoardRegionId | None = None

    def label_sprint(self) -> str:
        """Return compact human-readable dependent text."""

        if self.kind is GeometryDependentKind.MODULE:
            return f"module/{self.moduleName}"
        if self.kind is GeometryDependentKind.GEOMETRY_ZONE:
            if self.regionId is None:
                return self.kind.value
            return self.regionId.label_build()
        return self.kind.value


@dataclass(frozen=True)
class GeometryCouplingExpr:
    """One coupling relation from an anchor zone to one dependent."""

    anchorRegionId: BoardRegionId
    op: GeometryCouplingOp
    dependent: GeometryDependentRef

    def text_sprint(self) -> str:
        """Return compact symbolic text for this coupling expression."""

        return (
            f"{self.anchorRegionId.label_build()} "
            f"{self.op.value} "
            f"{self.dependent.label_sprint()}"
        )


@dataclass(frozen=True)
class GeometryCouplingFamily:
    """One explicit coupling family rooted at an anchor geometry zone."""

    anchorRegionId: BoardRegionId
    expressions: tuple[GeometryCouplingExpr, ...]

    def text_sprint(self) -> str:
        """Return readable multi-line coupling doctrine text."""

        return "\n".join(expr.text_sprint() for expr in self.expressions)


@dataclass(frozen=True)
class GeometryCouplingApplied:
    """Applied geometry state after one coupling family shift."""

    family: GeometryCouplingFamily
    geometry: BoardGeometry


def _worldPointShifted_build(
    worldPoint: WorldPoint,
    *,
    deltaColumns: int,
    deltaRows: int,
) -> WorldPoint:
    """Build one shifted world point."""

    return (worldPoint[0] + deltaColumns, worldPoint[1] + deltaRows)


def _routingZoneRegionFrameShifted_build(
    frame: RoutingZoneRegionFrame,
    *,
    deltaColumns: int,
    deltaRows: int,
) -> RoutingZoneRegionFrame:
    """Build one shifted routing-zone region frame."""

    return RoutingZoneRegionFrame(
        horizontalStart=frame.horizontalStart + deltaColumns,
        verticalStart=frame.verticalStart + deltaRows,
        horizontalSpan=frame.horizontalSpan,
        verticalSpan=frame.verticalSpan,
    )


def _chipPlacementsShifted_build(
    chipPlacementsByChip: dict[str, BoardChipDrawPlacement],
    *,
    deltaColumns: int,
    deltaRows: int,
) -> dict[str, BoardChipDrawPlacement]:
    """Build shifted chip draw placements."""

    return {
        chipName: BoardChipDrawPlacement(
            chipName=chipPlacement.chipName,
            moduleName=chipPlacement.moduleName,
            side=chipPlacement.side,
            drawTopLeft=_worldPointShifted_build(
                chipPlacement.drawTopLeft,
                deltaColumns=deltaColumns,
                deltaRows=deltaRows,
            ),
            drawLines=chipPlacement.drawLines,
        )
        for chipName, chipPlacement in chipPlacementsByChip.items()
    }


def _terminalPositionsShifted_build(
    terminalPositionsByChip: TerminalPositionsByChip,
    *,
    deltaColumns: int,
    deltaRows: int,
) -> TerminalPositionsByChip:
    """Build shifted exact terminal positions."""

    return {
        chipName: {
            terminalName: _worldPointShifted_build(
                worldPoint,
                deltaColumns=deltaColumns,
                deltaRows=deltaRows,
            )
            for terminalName, worldPoint in terminalPositions.items()
        }
        for chipName, terminalPositions in terminalPositionsByChip.items()
    }


def _anchorNotation_build(side: BoardSide) -> sfN:
    """Return chip-terminal notation token for one side."""

    return {
        BoardSide.WEST: sfN.Wt,
        BoardSide.EAST: sfN.Et,
        BoardSide.NORTH: sfN.Nt,
        BoardSide.SOUTH: sfN.St,
    }[side]


def _downstreamNotations_build(side: BoardSide) -> tuple[sfN, ...]:
    """Return downstream notation tokens for one terminal side."""

    return {
        BoardSide.WEST: (sfN.Wfe, sfN.We),
        BoardSide.EAST: (sfN.Efe, sfN.Ee),
        BoardSide.NORTH: (sfN.Nfe, sfN.Ne),
        BoardSide.SOUTH: (sfN.Sfe, sfN.Se),
    }[side]


def geometryCouplingExpr_buildFromSymbolic(
    expr: GeometryCouplingSymbolicExpr,
) -> Result[GeometryCouplingExpr]:
    """Lower one symbolic coupling tuple into typed coupling doctrine."""

    lhs, op, rhs = expr
    opValue = op.value if isinstance(op, GeometryCouplingOp) else op
    rhsZoneRef = getattr(rhs, "zoneRef", lhs.zoneRef)
    if lhs.zoneRef != rhsZoneRef:
        return resultErr_build()

    if isinstance(rhs, RegionOperand):
        dependent = GeometryDependentRef(
            kind=GeometryDependentKind.GEOMETRY_ZONE,
            regionId=boardRegionId_buildFromNotation(rhs.region),
        )
    elif isinstance(rhs, GeometryCollectionOperand):
        dependent = GeometryDependentRef(kind=rhs.kind)
    elif isinstance(rhs, GeometryModuleOperand):
        dependent = GeometryDependentRef(
            kind=GeometryDependentKind.MODULE,
            moduleName=rhs.moduleName,
        )
    else:
        return resultErr_build()

    opByValue = {
        GeometryCouplingOp.PROPAGATES_DRAG.value:
            GeometryCouplingOp.PROPAGATES_DRAG,
        GeometryCouplingOp.PROPAGATES_DISPLACE.value:
            GeometryCouplingOp.PROPAGATES_DISPLACE,
        GeometryCouplingOp.CONTAINS.value: GeometryCouplingOp.CONTAINS,
    }
    typedOp = opByValue.get(opValue)
    if typedOp is None:
        return resultErr_build()

    return resultOk_build(
        GeometryCouplingExpr(
            anchorRegionId=boardRegionId_buildFromNotation(lhs.region),
            op=typedOp,
            dependent=dependent,
        )
    )


def chipTerminalCouplingSymbolicExprsResult_build(
    geometry: BoardGeometry,
    side: Literal["west", "east", "north", "south"] | BoardSide,
) -> Result[tuple[GeometryCouplingSymbolicExpr, ...]]:
    """Build symbolic coupling rules for one chip-terminal family."""

    boardSide = side if isinstance(side, BoardSide) else BoardSide(side)
    anchorRegionId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL,
        side=boardSide,
    )
    anchorZone = geometry.geometryZonesById.get(anchorRegionId)
    if anchorZone is None:
        return resultErr_build()

    operandResult = zoneCouplingOperandResult_build("A")
    if not result_isOkCheck(operandResult):
        return resultErr_build()
    A = operandResult.value
    anchor = getattr(A, _anchorNotation_build(boardSide).name)

    exprs: list[GeometryCouplingSymbolicExpr] = [
        (anchor, "~=>", A.chips),
        (anchor, "~=>", A.terminals),
        (anchor, "[]=", A.chips),
        (anchor, "[]=", A.terminals),
    ]
    for moduleName in sorted(
        {
            chipPlacement.moduleName
            for chipPlacement in anchorZone.chips_get()
        }
    ):
        module = A.moduleOperand_build(moduleName)
        exprs.extend(
            (
                (anchor, "~=>", module),
                (anchor, "[]=", module),
            )
        )
    for notation in _downstreamNotations_build(boardSide):
        exprs.append((anchor, "~->", getattr(A, notation.name)))
    return resultOk_build(tuple(exprs))


def chipTerminalCouplingFamilyResult_build(
    geometry: BoardGeometry,
    side: Literal["west", "east", "north", "south"] | BoardSide,
) -> Result[GeometryCouplingFamily]:
    """Build the first-order coupling family for one chip-terminal zone."""

    boardSide = side if isinstance(side, BoardSide) else BoardSide(side)
    anchorRegionId = BoardRegionId(
        family=RegionFamily.CHIP_TERMINAL,
        side=boardSide,
    )
    if anchorRegionId not in geometry.geometryZonesById:
        return resultErr_build()

    symbolicExprsResult = chipTerminalCouplingSymbolicExprsResult_build(
        geometry,
        boardSide,
    )
    if not result_isOkCheck(symbolicExprsResult):
        return resultErr_build()

    expressions: list[GeometryCouplingExpr] = []
    for symbolicExpr in symbolicExprsResult.value:
        exprResult = geometryCouplingExpr_buildFromSymbolic(symbolicExpr)
        if not result_isOkCheck(exprResult):
            return resultErr_build()
        expressions.append(exprResult.value)

    return resultOk_build(
        GeometryCouplingFamily(
            anchorRegionId=anchorRegionId,
            expressions=tuple(expressions),
        )
    )


def geometryCouplingAppliedResult_build(
    geometry: BoardGeometry,
    family: GeometryCouplingFamily,
    *,
    deltaColumns: int,
    deltaRows: int = 0,
) -> Result[GeometryCouplingApplied]:
    """Apply one rigid move through a first-order coupling family."""

    anchorZone = geometry.geometryZonesById.get(family.anchorRegionId)
    if anchorZone is None:
        return resultErr_build()

    geometryZonesById = dict(geometry.geometryZonesById)
    effectiveBoundaryFramesByName = dict(
        geometry.effectiveBoundaryFramesByName
    )

    shiftedAnchorZone = GeometryZone(
        regionId=anchorZone.regionId,
        frame=_routingZoneRegionFrameShifted_build(
            anchorZone.frame,
            deltaColumns=deltaColumns,
            deltaRows=deltaRows,
        ),
        routingZoneRegionId=anchorZone.routingZoneRegionId,
        chipDrawPlacementsByChip=_chipPlacementsShifted_build(
            anchorZone.chipDrawPlacementsByChip,
            deltaColumns=deltaColumns,
            deltaRows=deltaRows,
        ),
        exactTerminalWorldPositionsByChip=_terminalPositionsShifted_build(
            anchorZone.exactTerminalWorldPositionsByChip,
            deltaColumns=deltaColumns,
            deltaRows=deltaRows,
        ),
    )
    geometryZonesById[family.anchorRegionId] = shiftedAnchorZone

    for expr in family.expressions:
        if expr.op not in {
            GeometryCouplingOp.PROPAGATES_DRAG,
            GeometryCouplingOp.PROPAGATES_DISPLACE,
        }:
            continue
        dependent = expr.dependent
        if dependent.kind is GeometryDependentKind.MODULE:
            if dependent.moduleName is None:
                continue
            boundaryName = f"module/{dependent.moduleName}"
            boundaryFrame = effectiveBoundaryFramesByName.get(boundaryName)
            if boundaryFrame is None:
                continue
            effectiveBoundaryFramesByName[boundaryName] = (
                _routingZoneRegionFrameShifted_build(
                    boundaryFrame,
                    deltaColumns=deltaColumns,
                    deltaRows=deltaRows,
                )
            )
            continue
        if dependent.kind is not GeometryDependentKind.GEOMETRY_ZONE:
            continue
        if dependent.regionId is None:
            continue
        dependentZone = geometryZonesById.get(dependent.regionId)
        if dependentZone is None:
            continue
        geometryZonesById[dependent.regionId] = GeometryZone(
            regionId=dependentZone.regionId,
            frame=_routingZoneRegionFrameShifted_build(
                dependentZone.frame,
                deltaColumns=deltaColumns,
                deltaRows=deltaRows,
            ),
            routingZoneRegionId=dependentZone.routingZoneRegionId,
            chipDrawPlacementsByChip=dependentZone.chipDrawPlacementsByChip,
            exactTerminalWorldPositionsByChip=(
                dependentZone.exactTerminalWorldPositionsByChip
            ),
        )

    return resultOk_build(
        GeometryCouplingApplied(
            family=family,
            geometry=BoardGeometry(
                geometryZonesById=geometryZonesById,
                effectiveBoundaryFramesByName=effectiveBoundaryFramesByName,
            ),
        )
    )


def chipTerminalCouplingAppliedResult_build(
    geometry: BoardGeometry,
    side: Literal["west", "east", "north", "south"] | BoardSide,
    *,
    deltaColumns: int,
    deltaRows: int = 0,
) -> Result[GeometryCouplingApplied]:
    """Build and apply the chip-terminal coupling family for one side."""

    familyResult = chipTerminalCouplingFamilyResult_build(geometry, side)
    if not result_isOkCheck(familyResult):
        return resultErr_build()
    return geometryCouplingAppliedResult_build(
        geometry,
        familyResult.value,
        deltaColumns=deltaColumns,
        deltaRows=deltaRows,
    )


__all__ = [
    "GeometryCollectionOperand",
    "GeometryCouplingApplied",
    "GeometryCouplingExpr",
    "GeometryCouplingFamily",
    "GeometryCouplingOp",
    "GeometryCouplingSymbolicExpr",
    "GeometryCouplingZoneOperand",
    "GeometryDependentKind",
    "GeometryDependentRef",
    "GeometryModuleOperand",
    "chipTerminalCouplingAppliedResult_build",
    "chipTerminalCouplingFamilyResult_build",
    "chipTerminalCouplingSymbolicExprsResult_build",
    "geometryCouplingAppliedResult_build",
    "geometryCouplingExpr_buildFromSymbolic",
    "zoneCouplingOperandResult_build",
    "zoneCouplingOperandsResult_build",
]
