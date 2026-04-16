"""Tests for the geo-zone displacement rule bank and engine.

Covers:
- Frame face-stretch helpers (all four faces)
- Frame translate helper
- rules_apply: Ee displacement cascades to Ne/Se east-face stretch
- rules_apply: We displacement — Z global translate + Ne/Se west stretch
- rules_apply: sfN.Z applies translate to every zone
- geometry_change: success, GeoArg error, unknown anchor, missing zone
- RULES completeness: Ee and We present; removed speculative entries absent
"""

from __future__ import annotations

import pytest

from signalflow.board.geometry.georules import (
    GeoArgScalar,
    GeoArgScaled,
    GeoChange,
    GeoEffect,
    GeoOp,
    RULES,
    TopologyFace,
    _frameFaceStretched_build,
    _frameTranslated_build,
    geometry_change,
    rules_apply,
)
from signalflow.board.geometry.mutation import boardRegionIdResult_fromSfN
from signalflow.board.geometry.zones import BoardGeometry, GeometryZone
from signalflow.models import RoutingZoneRegionFrame, result_isOkCheck
from signalflow.models.result import result_isErrCheck
from signalflow.notation.sfn import sfN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frame_build(
    hStart: int,
    vStart: int,
    hSpan: int,
    vSpan: int,
) -> RoutingZoneRegionFrame:
    return RoutingZoneRegionFrame(
        horizontalStart=hStart,
        verticalStart=vStart,
        horizontalSpan=hSpan,
        verticalSpan=vSpan,
    )


def _zone_build(token: sfN, frame: RoutingZoneRegionFrame) -> GeometryZone:
    ridResult = boardRegionIdResult_fromSfN(token)
    assert result_isOkCheck(ridResult), (
        f"no BoardRegionId for {token.name}"
    )
    return GeometryZone(regionId=ridResult.value, frame=frame)


def _minimalGeometry_build(
    tokens: list[sfN],
    frames: list[RoutingZoneRegionFrame],
) -> BoardGeometry:
    zonesById = {}
    for token, frame in zip(tokens, frames):
        zone: GeometryZone = _zone_build(token, frame)
        zonesById[zone.regionId] = zone
    return BoardGeometry(
        geometryZonesById=zonesById,
        effectiveBoundaryFramesByName={},
    )


# ---------------------------------------------------------------------------
# sfN.Z sentinel
# ---------------------------------------------------------------------------


class TestSfNZ:
    """sfN.Z exists, has no region_key, resolves to Err."""

    def test_z_member_exists(self) -> None:
        assert sfN.Z is sfN.Z

    def test_z_has_no_region_key(self) -> None:
        assert sfN.Z.region_key is None

    def test_z_boardregionid_is_err(self) -> None:
        result = boardRegionIdResult_fromSfN(sfN.Z)
        assert result_isErrCheck(result)


# ---------------------------------------------------------------------------
# _frameFaceStretched_build
# ---------------------------------------------------------------------------


class TestFrameFaceStretched:
    """Frame face-stretch helper applies delta to correct fields."""

    def test_east_extends_horizontal_span(self) -> None:
        frame: RoutingZoneRegionFrame = _frame_build(10, 20, 30, 40)
        result: RoutingZoneRegionFrame = _frameFaceStretched_build(
            frame, TopologyFace.EAST, 5
        )
        assert result.horizontalStart == 10
        assert result.horizontalSpan == 35

    def test_west_shifts_start_and_shrinks_span(self) -> None:
        frame: RoutingZoneRegionFrame = _frame_build(10, 20, 30, 40)
        result: RoutingZoneRegionFrame = _frameFaceStretched_build(
            frame, TopologyFace.WEST, -5
        )
        assert result.horizontalStart == 5
        assert result.horizontalSpan == 35

    def test_south_extends_vertical_span(self) -> None:
        frame: RoutingZoneRegionFrame = _frame_build(10, 20, 30, 40)
        result: RoutingZoneRegionFrame = _frameFaceStretched_build(
            frame, TopologyFace.SOUTH, 8
        )
        assert result.verticalStart == 20
        assert result.verticalSpan == 48

    def test_north_shifts_start_and_shrinks_span(self) -> None:
        frame: RoutingZoneRegionFrame = _frame_build(10, 20, 30, 40)
        result: RoutingZoneRegionFrame = _frameFaceStretched_build(
            frame, TopologyFace.NORTH, -6
        )
        assert result.verticalStart == 14
        assert result.verticalSpan == 46


# ---------------------------------------------------------------------------
# _frameTranslated_build
# ---------------------------------------------------------------------------


class TestFrameTranslated:
    """Frame translate helper shifts start coords, preserves spans."""

    def test_translate_shifts_start(self) -> None:
        frame: RoutingZoneRegionFrame = _frame_build(10, 20, 30, 40)
        result: RoutingZoneRegionFrame = _frameTranslated_build(frame, 3, 7)
        assert result.horizontalStart == 13
        assert result.verticalStart == 27
        assert result.horizontalSpan == 30
        assert result.verticalSpan == 40

    def test_translate_negative(self) -> None:
        frame: RoutingZoneRegionFrame = _frame_build(10, 20, 30, 40)
        result: RoutingZoneRegionFrame = _frameTranslated_build(
            frame, -2, -4
        )
        assert result.horizontalStart == 8
        assert result.verticalStart == 16


# ---------------------------------------------------------------------------
# rules_apply — Ee
# ---------------------------------------------------------------------------


class TestRulesApplyEe:
    """Ee displacement cascades to Ne/Se east-face stretch."""

    def _geo(self) -> BoardGeometry:
        return _minimalGeometry_build(
            [sfN.Ee, sfN.Ne, sfN.Se],
            [
                _frame_build(50, 10, 5, 80),   # Ee
                _frame_build(0, 0, 55, 10),    # Ne
                _frame_build(0, 90, 55, 10),   # Se
            ],
        )

    def test_ee_displace_stretches_ne_east_face(self) -> None:
        geo: BoardGeometry = self._geo()
        after: BoardGeometry = rules_apply(
            sfN.Ee, GeoOp.DISPLACE, 5, 0, geo
        )
        ridResult = boardRegionIdResult_fromSfN(sfN.Ne)
        assert result_isOkCheck(ridResult)
        neZone: GeometryZone | None = after.geometryZonesById.get(
            ridResult.value
        )
        assert neZone is not None
        assert neZone.frame.horizontalSpan == 60
        assert neZone.frame.horizontalStart == 0

    def test_ee_displace_stretches_se_east_face(self) -> None:
        geo: BoardGeometry = self._geo()
        after: BoardGeometry = rules_apply(
            sfN.Ee, GeoOp.DISPLACE, 5, 0, geo
        )
        ridResult = boardRegionIdResult_fromSfN(sfN.Se)
        assert result_isOkCheck(ridResult)
        seZone: GeometryZone | None = after.geometryZonesById.get(
            ridResult.value
        )
        assert seZone is not None
        assert seZone.frame.horizontalSpan == 60

    def test_ee_itself_translated_by_rules_apply(self) -> None:
        """Ee rule includes explicit self-translate — Ee moves."""
        geo: BoardGeometry = self._geo()
        after: BoardGeometry = rules_apply(
            sfN.Ee, GeoOp.DISPLACE, 5, 0, geo
        )
        ridResult = boardRegionIdResult_fromSfN(sfN.Ee)
        assert result_isOkCheck(ridResult)
        eeZone: GeometryZone | None = after.geometryZonesById.get(
            ridResult.value
        )
        assert eeZone is not None
        assert eeZone.frame.horizontalStart == 55  # translated by rule

    def test_no_matching_rule_returns_same_geometry(self) -> None:
        geo: BoardGeometry = self._geo()
        after: BoardGeometry = rules_apply(
            sfN.Ci, GeoOp.DISPLACE, 5, 0, geo
        )
        assert after is geo


# ---------------------------------------------------------------------------
# rules_apply — We (Z translate + Ne/Se west stretch)
# ---------------------------------------------------------------------------


class TestRulesApplyWe:
    """We displacement: Z shifts all zones east, Ne/Se west faces follow."""

    def _geo(self) -> BoardGeometry:
        # We at col 1 (floor), Ne/Se span full width, Wfe is an "other" zone
        return _minimalGeometry_build(
            [sfN.We, sfN.Ne, sfN.Se, sfN.Wfe],
            [
                _frame_build(1,  10, 5,  80),   # We: [1, 6)
                _frame_build(1,  0,  55, 10),   # Ne: [1, 56)
                _frame_build(1,  90, 55, 10),   # Se: [1, 56)
                _frame_build(6,  10, 3,  80),   # Wfe: [6, 9)
            ],
        )

    def test_we_displace_z_shifts_all_zones_east(self) -> None:
        """Z rule with factor=-1 and dCols=-3 → all zones +3 east."""
        geo: BoardGeometry = self._geo()
        # anchor-translate happens in geometry_change, not rules_apply.
        # Call rules_apply directly with dCols=-3.
        after: BoardGeometry = rules_apply(
            sfN.We, GeoOp.DISPLACE, -3, 0, geo
        )
        # Wfe (not in any stretch rule) must shift east by 3.
        wfeRid = boardRegionIdResult_fromSfN(sfN.Wfe).value
        wfeAfter: GeometryZone = after.geometryZonesById[wfeRid]
        assert wfeAfter.frame.horizontalStart == 9   # 6 + 3

    def test_we_displace_ne_west_face_stretches(self) -> None:
        geo: BoardGeometry = self._geo()
        after: BoardGeometry = rules_apply(
            sfN.We, GeoOp.DISPLACE, -3, 0, geo
        )
        neRid = boardRegionIdResult_fromSfN(sfN.Ne).value
        neAfter: GeometryZone = after.geometryZonesById[neRid]
        # Z shifted Ne to start=4. STRETCH west by -3: start=4-3=1, span+=3.
        assert neAfter.frame.horizontalStart == 1
        assert neAfter.frame.horizontalSpan == 58   # 55 + 3

    def test_we_displace_se_west_face_stretches(self) -> None:
        geo: BoardGeometry = self._geo()
        after: BoardGeometry = rules_apply(
            sfN.We, GeoOp.DISPLACE, -3, 0, geo
        )
        seRid = boardRegionIdResult_fromSfN(sfN.Se).value
        seAfter: GeometryZone = after.geometryZonesById[seRid]
        assert seAfter.frame.horizontalStart == 1
        assert seAfter.frame.horizontalSpan == 58


# ---------------------------------------------------------------------------
# geometry_change
# ---------------------------------------------------------------------------


class TestGeometryChange:
    """geometry_change translates anchor and cascades rules."""

    def _geoEe(self) -> BoardGeometry:
        return _minimalGeometry_build(
            [sfN.Ee, sfN.Ne, sfN.Se],
            [
                _frame_build(50, 10, 5, 80),
                _frame_build(0, 0, 55, 10),
                _frame_build(0, 90, 55, 10),
            ],
        )

    def test_ee_translate_and_cascade(self) -> None:
        geo: BoardGeometry = self._geoEe()
        changes: list[GeoChange] = [
            (sfN.Ee, GeoArgScalar(5), GeoOp.DISPLACE),
        ]
        afterResult = geometry_change(changes, geo)
        assert result_isOkCheck(afterResult)
        after: BoardGeometry = afterResult.value

        eeRid = boardRegionIdResult_fromSfN(sfN.Ee).value
        neRid = boardRegionIdResult_fromSfN(sfN.Ne).value

        # Ee rule includes explicit TRANSLATE +1 entry
        assert after.geometryZonesById[eeRid].frame.horizontalStart == 55
        assert after.geometryZonesById[neRid].frame.horizontalSpan == 60

    def test_we_geometry_change_net_position(self) -> None:
        """After We -= 3: We back at original pos, Wfe shifted east."""
        geo: BoardGeometry = _minimalGeometry_build(
            [sfN.We, sfN.Ne, sfN.Se, sfN.Wfe],
            [
                _frame_build(1,  10, 5,  80),
                _frame_build(1,  0,  55, 10),
                _frame_build(1,  90, 55, 10),
                _frame_build(6,  10, 3,  80),
            ],
        )
        changes: list[GeoChange] = [
            (sfN.We, GeoArgScalar(-3), GeoOp.DISPLACE),
        ]
        afterResult = geometry_change(changes, geo)
        assert result_isOkCheck(afterResult)
        after: BoardGeometry = afterResult.value

        weRid = boardRegionIdResult_fromSfN(sfN.We).value
        wfeRid = boardRegionIdResult_fromSfN(sfN.Wfe).value
        neRid = boardRegionIdResult_fromSfN(sfN.Ne).value

        # We: anchor-translate -3 then Z +3 → net 0, same position
        assert after.geometryZonesById[weRid].frame.horizontalStart == 1
        assert after.geometryZonesById[weRid].frame.horizontalSpan == 5
        # Wfe: Z shifted east by 3
        assert after.geometryZonesById[wfeRid].frame.horizontalStart == 9
        # Ne: Z +3 then west-face stretch -3 → start back to 1, span grows
        assert after.geometryZonesById[neRid].frame.horizontalStart == 1
        assert after.geometryZonesById[neRid].frame.horizontalSpan == 58

    def test_string_op_accepted(self) -> None:
        geo: BoardGeometry = self._geoEe()
        changes: list[GeoChange] = [
            (sfN.Ee, GeoArgScalar(3), "+="),
        ]
        afterResult = geometry_change(changes, geo)
        assert result_isOkCheck(afterResult)

    def test_unsupported_arg_type_returns_err(self) -> None:
        geo: BoardGeometry = self._geoEe()
        changes: list[GeoChange] = [
            (sfN.Ee, GeoArgScaled(factor=0.5, reference=sfN.Ee), "+="),
        ]
        afterResult = geometry_change(changes, geo)
        assert result_isErrCheck(afterResult)
        assert "GeoArgScaled" in afterResult.reason

    def test_anchor_with_no_rules_returns_err(self) -> None:
        """Anchor not in RULES bank → Err."""
        geo: BoardGeometry = self._geoEe()
        changes: list[GeoChange] = [
            (sfN.Ci, GeoArgScalar(5), GeoOp.DISPLACE),
        ]
        afterResult = geometry_change(changes, geo)
        assert result_isErrCheck(afterResult)
        assert "Ci" in afterResult.reason


# ---------------------------------------------------------------------------
# RULES bank structure
# ---------------------------------------------------------------------------


class TestRulesBank:
    """Only Ee and We defined; speculative entries absent."""

    def test_ee_in_rules(self) -> None:
        assert sfN.Ee in RULES
        assert GeoOp.DISPLACE in RULES[sfN.Ee]

    def test_we_in_rules(self) -> None:
        assert sfN.We in RULES
        assert GeoOp.DISPLACE in RULES[sfN.We]

    @pytest.mark.parametrize(
        "anchor",
        [sfN.Ne, sfN.Se, sfN.Ei, sfN.Wi, sfN.Ni, sfN.Si],
    )
    def test_speculative_anchors_absent(self, anchor: sfN) -> None:
        assert anchor not in RULES

    def test_ee_rule_includes_self_translate(self) -> None:
        entries = RULES[sfN.Ee][GeoOp.DISPLACE]
        selfEntries = [
            (t, f, e, fac) for t, f, e, fac in entries
            if t is sfN.Ee
        ]
        assert len(selfEntries) == 1
        _, _, effect, factor = selfEntries[0]
        assert effect is GeoEffect.TRANSLATE
        assert factor == +1

    def test_ee_rule_targets_ne_se_east(self) -> None:
        entries = RULES[sfN.Ee][GeoOp.DISPLACE]
        stretchEntries = [
            (t, f, e, fac) for t, f, e, fac in entries
            if t is not sfN.Ee
        ]
        targets = {t for t, _, _, _ in stretchEntries}
        faces = {f for _, f, _, _ in stretchEntries}
        factors = {fac for _, _, _, fac in stretchEntries}
        assert targets == {sfN.Ne, sfN.Se}
        assert faces == {TopologyFace.EAST}
        assert factors == {+1}

    def test_we_rule_has_z_translate_factor_minus1(self) -> None:
        entries = RULES[sfN.We][GeoOp.DISPLACE]
        zEntries = [
            (t, f, e, fac)
            for t, f, e, fac in entries
            if t is sfN.Z
        ]
        assert len(zEntries) == 1
        _, _, effect, factor = zEntries[0]
        assert effect is GeoEffect.TRANSLATE
        assert factor == -1

    def test_we_rule_includes_self_translate(self) -> None:
        entries = RULES[sfN.We][GeoOp.DISPLACE]
        selfEntries = [
            (t, f, e, fac) for t, f, e, fac in entries
            if t is sfN.We
        ]
        assert len(selfEntries) == 1
        _, _, effect, factor = selfEntries[0]
        assert effect is GeoEffect.TRANSLATE
        assert factor == +1

    def test_we_rule_stretches_ne_se_west(self) -> None:
        entries = RULES[sfN.We][GeoOp.DISPLACE]
        stretchEntries = [
            (t, f, e, fac)
            for t, f, e, fac in entries
            if t not in (sfN.Z, sfN.We)
        ]
        targets = {t for t, _, _, _ in stretchEntries}
        faces = {f for _, f, _, _ in stretchEntries}
        factors = {fac for _, _, _, fac in stretchEntries}
        assert targets == {sfN.Ne, sfN.Se}
        assert faces == {TopologyFace.WEST}
        assert factors == {+1}
