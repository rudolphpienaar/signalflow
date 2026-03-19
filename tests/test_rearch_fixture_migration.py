"""Phase 9: Fixture migration tests.

Verifies that each canonical fixture runs successfully through the full new
engine pipeline (circuit parse → placement → obligations → zone solve →
realize → render) and satisfies the Phase 9 parity invariants:

  - artifact invariants are met (pipeline produces no errors)
  - no unrelated route movement across fixture variants
  - route semantics affect appearance, not path geometry

Canonical fixture targets:
  - rearch-external-forward.yaml     (forward edge only)
  - rearch-external-backedge.yaml    (forward + ancestor back edge)
  - rearch-external-self.yaml        (self edge)
  - hub.yaml                         (multi-proxy hub)
  - explicit-hub.yaml                (explicit hub variant)

Pass gate: each fixture builds a successful debug context (no pipeline
errors) and the Phase 7 + Phase 8 render layer produces non-empty output.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from signalflow.engine.debug import newEngineDebugContextResult_buildFromDocumentDict
from signalflow.models import (
    RouteObligationScope,
    result_isOkCheck,
    diagnosticStack,
)
from signalflow.render.routes import routeWorldCanvas_render
from signalflow.routing.route import (
    RouteSense,
    realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet,
)


# ---------------------------------------------------------------------------
# Fixture loading helpers
# ---------------------------------------------------------------------------

_EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
_SIMPLE_DIR = _EXAMPLES_DIR / "simple-circuit"


def _loadDocument(path: Path) -> dict[str, object]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def _pipelineContext(path: Path):
    """Run the full new-engine pipeline for one fixture and return the context."""
    diagnosticStack.stack_clear()
    result = newEngineDebugContextResult_buildFromDocumentDict(_loadDocument(path))
    assert result_isOkCheck(result), (
        f"Pipeline failed for {path.name}: "
        + "; ".join(
            f"{d.code}: {d.message}"
            for d in diagnosticStack.diagnosticSet_build().diagnostics_getAll()
            if d.level.value == "error"
        )
    )
    return result.value


def _obligationScopes(ctx) -> tuple[RouteObligationScope, ...]:
    return tuple(
        ob.routeObligationScope
        for ob in ctx.routeObligationSet.callRouteObligationSet.callRouteObligations
    )


def _zoneLocalCount(ctx) -> int:
    return len(ctx.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes)


def _seamCount(ctx) -> int:
    return len(
        ctx.routingZoneInterconnectSolvedRouteSet
        .routingZoneInterconnectSolvedRoutes
    )


def _realizeAndRender(ctx) -> tuple[str, ...]:
    """Realize zone-local routes and project to a world canvas."""
    realizedResult = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
        ctx.routingZoneLocalSolvedRouteSet,
        defaultRouteSense=RouteSense.FORWARD,
    )
    assert result_isOkCheck(realizedResult)
    return routeWorldCanvas_render(realizedResult.value)


# ---------------------------------------------------------------------------
# rearch-external-forward.yaml
# ---------------------------------------------------------------------------


class TestRearchExternalForward:
    """Minimal forward-edge fixture: caller() → callee()."""

    @pytest.fixture(autouse=True)
    def ctx(self):
        self._ctx = _pipelineContext(_SIMPLE_DIR / "rearch-external-forward.yaml")

    def test_pipeline_builds_without_errors(self) -> None:
        # Covered by fixture setup — any pipeline error aborts the test.
        assert self._ctx is not None

    def test_two_canonical_chips(self) -> None:
        assert len(self._ctx.circuitDocument.circuitChipSet.chips) == 2

    def test_one_call(self) -> None:
        assert len(self._ctx.circuitDocument.circuitCallSet.circuitCalls) == 1

    def test_obligation_scope_is_zone_local(self) -> None:
        scopes = _obligationScopes(self._ctx)
        assert scopes == (RouteObligationScope.ZONE_LOCAL,)

    def test_one_zone_local_solved_route(self) -> None:
        # One ZONE_LOCAL obligation → 2 routes (CLOCKWISE_INTRA_FORWARD + RETURN).
        assert _zoneLocalCount(self._ctx) == 2

    def test_no_seam_routes(self) -> None:
        assert _seamCount(self._ctx) == 0

    def test_render_produces_non_empty_canvas(self) -> None:
        canvas = _realizeAndRender(self._ctx)
        assert len(canvas) > 0
        assert any(ch != " " for row in canvas for ch in row)

    def test_render_does_not_require_circuit_document(self) -> None:
        # Pass gate: render layer sees only the RealizedRouteSet, no topology.
        canvas = _realizeAndRender(self._ctx)
        assert isinstance(canvas, tuple)


# ---------------------------------------------------------------------------
# rearch-external-backedge.yaml
# ---------------------------------------------------------------------------


class TestRearchExternalBackedge:
    """Forward + ancestor back edge: caller() → callee() → caller()."""

    @pytest.fixture(autouse=True)
    def ctx(self):
        self._ctx = _pipelineContext(_SIMPLE_DIR / "rearch-external-backedge.yaml")

    def test_pipeline_builds_without_errors(self) -> None:
        assert self._ctx is not None

    def test_two_canonical_chips(self) -> None:
        assert len(self._ctx.circuitDocument.circuitChipSet.chips) == 2

    def test_two_calls(self) -> None:
        assert len(self._ctx.circuitDocument.circuitCallSet.circuitCalls) == 2

    def test_both_obligations_are_zone_local(self) -> None:
        scopes = _obligationScopes(self._ctx)
        assert set(scopes) == {RouteObligationScope.ZONE_LOCAL}

    def test_two_zone_local_solved_routes(self) -> None:
        # Two ZONE_LOCAL obligations → 4 routes (2 forward + 2 return).
        assert _zoneLocalCount(self._ctx) == 4

    # Parity invariant: backedge has one extra obligation beyond forward-only.
    def test_forward_route_count_equals_forward_only_fixture(self) -> None:
        fwdCtx = _pipelineContext(_SIMPLE_DIR / "rearch-external-forward.yaml")
        # backedge = fwd obligation + back obligation → fwd_count + 2 routes.
        assert _zoneLocalCount(self._ctx) == _zoneLocalCount(fwdCtx) + 2

    def test_render_produces_non_empty_canvas(self) -> None:
        canvas = _realizeAndRender(self._ctx)
        assert len(canvas) > 0
        assert any(ch != " " for row in canvas for ch in row)


# ---------------------------------------------------------------------------
# rearch-external-self.yaml
# ---------------------------------------------------------------------------


class TestRearchExternalSelf:
    """Self-loop fixture: worker() → worker()."""

    @pytest.fixture(autouse=True)
    def ctx(self):
        self._ctx = _pipelineContext(_SIMPLE_DIR / "rearch-external-self.yaml")

    def test_pipeline_builds_without_errors(self) -> None:
        assert self._ctx is not None

    def test_one_canonical_chip(self) -> None:
        assert len(self._ctx.circuitDocument.circuitChipSet.chips) == 1

    def test_one_call(self) -> None:
        assert len(self._ctx.circuitDocument.circuitCallSet.circuitCalls) == 1

    def test_obligation_scope_is_zone_local(self) -> None:
        scopes = _obligationScopes(self._ctx)
        assert scopes == (RouteObligationScope.ZONE_LOCAL,)

    def test_one_zone_local_solved_route(self) -> None:
        assert _zoneLocalCount(self._ctx) == 1

    def test_render_produces_non_empty_canvas(self) -> None:
        canvas = _realizeAndRender(self._ctx)
        assert len(canvas) > 0

    # Parity invariant: self edge route geometry stays in one zone.
    # Adding a self edge must not produce seam routes.
    def test_no_seam_routes(self) -> None:
        assert _seamCount(self._ctx) == 0


# ---------------------------------------------------------------------------
# Route-semantics invariant across the three rearch-external fixtures
# ---------------------------------------------------------------------------


class TestRouteSemanticInvariance:
    """Same route topology under different senses must occupy the same cells."""

    def test_forward_and_back_senses_produce_same_cells_for_same_route(self) -> None:
        ctx = _pipelineContext(_SIMPLE_DIR / "rearch-external-forward.yaml")
        fwdResult = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
            ctx.routingZoneLocalSolvedRouteSet,
            defaultRouteSense=RouteSense.FORWARD,
        )
        bckResult = realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
            ctx.routingZoneLocalSolvedRouteSet,
            defaultRouteSense=RouteSense.BACK,
        )
        assert result_isOkCheck(fwdResult)
        assert result_isOkCheck(bckResult)
        fwdCells = {
            (c.worldRow, c.worldCol): c.trackCell
            for r in fwdResult.value.realizedRoutes
            for c in r.cells
        }
        bckCells = {
            (c.worldRow, c.worldCol): c.trackCell
            for r in bckResult.value.realizedRoutes
            for c in r.cells
        }
        assert fwdCells == bckCells, (
            "Route cells differ between FORWARD and BACK senses — "
            "route semantics must not affect path geometry"
        )

    def test_forward_canvas_identical_to_self_canvas_for_self_fixture(self) -> None:
        ctx = _pipelineContext(_SIMPLE_DIR / "rearch-external-self.yaml")
        fwdCanvas = routeWorldCanvas_render(
            realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
                ctx.routingZoneLocalSolvedRouteSet,
                defaultRouteSense=RouteSense.FORWARD,
            ).value
        )
        selfCanvas = routeWorldCanvas_render(
            realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet(
                ctx.routingZoneLocalSolvedRouteSet,
                defaultRouteSense=RouteSense.SELF,
            ).value
        )
        assert fwdCanvas == selfCanvas


# ---------------------------------------------------------------------------
# hub.yaml
# ---------------------------------------------------------------------------


class TestHubFixture:
    """hub.yaml: multi-proxy hub with 5 proxies and 5 sinks."""

    @pytest.fixture(autouse=True)
    def ctx(self):
        self._ctx = _pipelineContext(_EXAMPLES_DIR / "hub.yaml")

    def test_pipeline_builds_without_errors(self) -> None:
        assert self._ctx is not None

    def test_has_zone_local_routes(self) -> None:
        assert _zoneLocalCount(self._ctx) > 0

    def test_has_seam_routes(self) -> None:
        assert _seamCount(self._ctx) > 0

    def test_render_produces_non_empty_canvas(self) -> None:
        canvas = _realizeAndRender(self._ctx)
        assert len(canvas) > 0

    def test_zone_local_route_count_is_twenty(self) -> None:
        # 10 ZONE_LOCAL obligations × 2 routes each (forward + return) = 20
        assert _zoneLocalCount(self._ctx) == 20

    def test_seam_route_count_is_five(self) -> None:
        assert _seamCount(self._ctx) == 5


# ---------------------------------------------------------------------------
# explicit-hub.yaml
# ---------------------------------------------------------------------------


class TestExplicitHubFixture:
    """explicit-hub.yaml: same topology as hub with explicit port declarations."""

    @pytest.fixture(autouse=True)
    def ctx(self):
        self._ctx = _pipelineContext(_EXAMPLES_DIR / "explicit-hub.yaml")

    def test_pipeline_builds_without_errors(self) -> None:
        assert self._ctx is not None

    def test_has_zone_local_routes(self) -> None:
        assert _zoneLocalCount(self._ctx) > 0

    def test_has_seam_routes(self) -> None:
        assert _seamCount(self._ctx) > 0

    def test_render_produces_non_empty_canvas(self) -> None:
        canvas = _realizeAndRender(self._ctx)
        assert len(canvas) > 0

    # Parity invariant: explicit-hub and hub have identical route topology.
    def test_matches_hub_zone_local_route_count(self) -> None:
        hubCtx = _pipelineContext(_EXAMPLES_DIR / "hub.yaml")
        assert _zoneLocalCount(self._ctx) == _zoneLocalCount(hubCtx)

    def test_matches_hub_seam_route_count(self) -> None:
        hubCtx = _pipelineContext(_EXAMPLES_DIR / "hub.yaml")
        assert _seamCount(self._ctx) == _seamCount(hubCtx)
