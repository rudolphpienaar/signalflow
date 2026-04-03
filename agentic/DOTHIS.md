# Next Agent Instructions

Read these first, in order:

1. `agentic/HANDOFF.md`
2. `agentic/NON-NEGOTIABLES.md`
3. `docs/worldscale_geometry.adoc`
4. `papers/new_ways.adoc`

Current branch is `worldscale-extra-routing`. Current version is `5.9.15`.

## What Changed Last Arc

Housekeeping and tooling improvements:

- Pyright error sweep: all non-legacy errors resolved (0 errors, 18/18 tests)
- `NewEngineDebugContext` → `SignalFlowContext`; all `newEngine*` prefixes removed
- `_text()` suffix → `_sprint()` codebase-wide (returns `str`); `_lprint()` reserved for `list[str]`
- `newEngineArtifact_render` → `worldDiagram_lprint`
- New `snippets/algebraic/zone_geometry.py` — standalone zone geometry inspector
- CLI `--` passthrough: snippet-specific args now survive via `sys.argv`
- `source_yaml` injected into every snippet namespace by the runner
- Glyph fix: `EXTRA_TRANSITION` and `INTRA_EXTRA_TRANSFER` east/west corner glyphs swapped
  (west=╔/╚, east=╗/╝ — consistent across both families)

Run this to see the current state:

```
uv run python -m signalflow examples/hub.yaml --run-snippet snippets/algebraic/zone_geometry.py -- --zone 1,1
```

## Immediate Task

`BoardGeometrySpec` implementation. All span defaults are currently scattered
across `placement.py` (constants + demand computation) and `builders.py`
(hardcoded default parameters). There is no single source of truth.

The design doctrine is already established in `agentic/PLAN.md` (Phase 2b).
The task is to implement it:

1. Create `BoardGeometrySpec` in `doctrine.py` with all span knobs as explicit fields
2. Create `ZoneSymbolicInvariants` — reads circuit facts (chip counts, port counts,
   wire demand) from `CircuitDocument` + `RoutingZone` and derives analyzer minimums
3. Have `_extraGeometry_build` in `builders.py` consume a `BoardGeometrySpec` instead
   of hardcoded defaults
4. Have `zone_geometry.py` snippet demonstrate the full derivation path

Do not touch placement.py demand computation yet — that is a separate concern.

## Things Not To Do

- do not revive stale `rearch-zone-grid` milestone assumptions
- do not treat seams/interconnects as the settled next step
- do not overclaim geometry is placement-derived unless you can show the builder path
- do not start new routing work before `BoardGeometrySpec` is implemented
- do not use broad LLM rewrites — surgical changes only
