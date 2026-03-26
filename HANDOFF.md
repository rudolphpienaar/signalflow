# SignalFlow Agent Handoff

**Date:** March 25, 2026
**Status:** MILESTONE 1 COMPLETE — READY FOR MILESTONE 2
**Mission:** Substrate Unification — remove the legacy shunt, delete the ghost set.

---

## 1. What Was Just Done (Milestone 1 — Physics Rescue)

The kernel/interconnect solver had four physics violations. All are now fixed:

| # | Violation | Fix |
|---|-----------|-----|
| 1 | `kernel_solver.py` used INTRA_LATITUDE rows for travel | Use LONGITUDE `verticalStart + i` instead |
| 2 | `interconnect_solver.py` hardcoded EAST/WEST wall sides | Detect axis; use SOUTH/NORTH for NTS seam |
| 3 | INTRA_LATITUDE bands included in mega-kernel regions | Stripped from `megaRegions` (now 7 items) |
| 4 | Source fan `isWestSide` was `wallSrc.side==WEST` (False for EAST fan) | Always `True`; northernmost wire gets innermost peel |

**Result:** `pytest tests/test_rearch_interconnect_solver.py` → **4/4 PASS**

### Orthogonal Crossings — Accepted as Valid Physics

In monotone ribbon packing, a straight-through wire (srcRow==dstRow) spanning the full
horizontal extent will cross the peel verticals of wires routing to other travel rows.
This is geometrically unavoidable and physically valid in ASCII art (drawn as `+`).
`allow_orthogonal_crossings=True` in test 4 reflects this deliberate design choice.

---

## 2. Current State of the Codebase

```
pytest (full suite): 529 passed, 34 failed (all pre-existing, unrelated to kernel work)
ruff: no new violations from this session's changes
```

**New/modified files from this work:**
- `src/signalflow/routing/fan_solver.py` (untracked — new)
- `src/signalflow/routing/kernel_solver.py` (untracked — new)
- `src/signalflow/routing/interconnect_solver.py` (modified)
- `tests/test_rearch_interconnect_solver.py` (modified, calibrated to current physics)

**Still shunted (Milestone 2 work):**
- `src/signalflow/routing/zone_solver.py` — INTRAZONE still uses legacy solver
- `RoutingZone.routingZoneRegionSet` — ghost monolithic set, still alive

---

## 3. Milestone 2: Substrate Unification

### Step A — Remove the zone_solver.py shunt

Find the shunt that routes INTRAZONE obligations to the legacy solver and replace it with
a call to the zone's `intraKernel`. Run the full suite; expect some failures to resolve
as the kernel geometry becomes the source of truth for intra-zone routing.

### Step B — Delete the ghost set

Once the shunt is gone, `RoutingZone.routingZoneRegionSet` has no more callers. Delete it.
Update all downstream lookups (REPL handles, debug views, etc.) to use the 5 kernels.
Delete ~1000 lines of legacy solver code.

### Step C — Fix pre-existing test failures

The 34 pre-existing failures divide roughly into:
- **Routing zone model validation** (2 tests): `routingZone_rejects_*` — validation logic
  not rejecting out-of-bounds regions/placements.
- **Circuit document** (1 test): `chipIoInput.explicit` returning None vs True.
- **Assignment/obligations** (5 tests): `circuitDocumentResult` fails before routing.
- **Debug context** (22 tests): stale debug API assertions, REPL handle changes.
- **Engine boundary/render** (2+1 tests): world canvas rendering issues.

Address these in the order they unblock (assignment/obligations likely gate the others).

---

## 4. REPL Diagnostic Commands

```python
# Check intra-zone routing in zone(1,1)
z = zones.routingZone_get(1, 1)
ke = z.routingKernel_get('east')
ke.kernel_draw()              # Should show clean corridors after Milestone 2
ke.kernel_routesDraw()        # Route ribbon visualization

# Check the seam breakout (interconnect between zones)
z.routingZoneCrossbar_draw()
z.routingZoneAreas_get().draw()
```

---

## 5. Non-Negotiables

See `NON-NEGOTIABLES.md`. Core rules that cannot be overridden:
- No same-direction shared realized cells between distinct routes.
- Longitudinal wires must not route under chip labels or through module boxes.
- Peel verticals must stay strictly inside fanning corridors.
- Orthogonal crossings (EW ↔ NS at same cell) are allowed.
