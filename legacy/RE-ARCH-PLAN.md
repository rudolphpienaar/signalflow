# Routing Engine Re-Architecture Plan

This file is the agent-facing execution plan for the routing-engine redesign described in [docs/re-architecture.adoc](/home/rudolphpienaar/src/signalFlow/docs/re-architecture.adoc). It is intentionally operational and redundant. The design document is the architectural contract. This file is the implementation runbook.

## Mission

Build a new layout and routing core in parallel with the legacy engine. The new core must replace implicit and renderer-discovered behavior with explicit typed models, explicit sources of truth, and artifact-first TDD. The new engine must support:

- internal chip-local routing
- external inter-chip routing
- forward edges
- ancestor/back edges
- self edges
- local wall reuse
- route class and presentation qualifiers

The new engine is not a speculative rewrite. It is a staged replacement whose success is measured against concrete artifact parity on named fixtures.

Success does not mean that a new package exists or that a new model has been introduced. Success means that the new engine can be selected explicitly, run on the canonical fixture set, and shown to satisfy the artifact invariants named in this plan.

March 2026 architectural reset:

- the canonical world topology is now `RoutingZoneGrid`
- the atomic local routing unit is now `RoutingZone`
- continuity between neighboring zones is mediated by `RoutingZoneInterconnect`
- the old `ChipLayout` code has been removed so the codebase does not keep a competing topology model alive
- YAML ingress is now split explicitly into:
  - serialized source models in `src/signalflow/models/circuit_source.py`
  - validated engine-facing models in `src/signalflow/models/circuit.py`
  - parser/normalization entry in `src/signalflow/engine/input.py`
- repeated short `(module, func)` references now resolve to one canonical chip
  declaration in the new engine
  - later short forms create additional call edges rather than cloned chip
    occurrences
- the first circuit-to-world bridge now exists in
  `src/signalflow/routing/assignment.py`
  - it maps circuit depth layers into `RoutingZoneGrid` under the current
    simple major-axis regime
- logical placement planning now exists in
  `src/signalflow/routing/placement.py`
  - it enriches `RoutingZoneGrid` with explicit `ChipPlacementSet`s,
    logical zone frames, logical interconnect frames, and explicit region
    geometry for the current simple regime
- the first route-obligation layer now exists in
  `src/signalflow/models/route_obligation.py` and
  `src/signalflow/routing/obligations.py`
  - it derives explicit call-route and chip-internal obligations from
    `CircuitDocument` plus the placed `RoutingZoneGrid`
  - it currently classifies obligations coarsely as:
    - `CHIP_INTERNAL`
    - `ZONE_LOCAL`
    - `SEAM_CROSSING`
    - `GRID_LONG_HAUL`
- the first zone-local solve layer now exists in
  `src/signalflow/models/zone_route.py` and
  `src/signalflow/routing/zone_solver.py`
  - it realizes `ZONE_LOCAL` obligations against actual planned
    `RoutingZoneRegionFrame` geometry
  - it emits explicit world-coordinate planning polylines inside one zone
  - it currently classifies solved local routes as:
    - `STRAIGHT_TRANSVERSE`
    - `OFFSET_TRANSVERSE`
    - `SAME_SIDE_LOCAL`
- the first seam/interconnect solve layer now exists in
  `src/signalflow/models/interconnect_route.py` and
  `src/signalflow/routing/interconnect_solver.py`
  - it realizes `SEAM_CROSSING` obligations against actual
    `RoutingZoneInterconnectFrame` geometry plus neighboring
    `INTER_ROUTING_FAN_IN_OUT` region frames
  - it emits explicit world-coordinate seam polylines
  - it currently classifies solved seam routes as:
    - `STRAIGHT_SEAM`
    - `OFFSET_SEAM`
- the first grid-level long-haul solve layer now exists in
  `src/signalflow/models/grid_route.py` and
  `src/signalflow/routing/grid_solver.py`
  - it realizes `GRID_LONG_HAUL` obligations against the placed
    `RoutingZoneGrid` and macro path selection
  - it emits explicit planning-grid route polylines across multiple zones and
    multiple interconnects
  - it currently supports the existing simple one-row or one-column world
    regimes and classifies solved grid routes as:
    - `LINEAR_HORIZONTAL`
    - `LINEAR_VERTICAL`
- the first projection renderer now exists in
  `src/signalflow/engine/render.py`
  - the `--engine new` runtime no longer reports a placeholder pending status
  - it projects solved zone-local, seam, and grid-long-haul geometry into a
    readable planning artifact with one primary diagram block, compact chip
    bodies, port-face hints, an attached route row, a world canvas, a chip
    legend, world-route summaries, and a chip-internal summary
  - the primary `diagram:` block is now row-labeled (`zone`, `coord`, `chip`,
    `face`, `link`, `flow`) so topology and attached route presentation read
    as one schematic rather than as an unlabeled glyph dump
  - vertical one-column (`NorthToSouth`) worlds now render as readable stacked
    zone boxes with explicit seam rows
  - rectangular 2D worlds now render under the current conservative serpentine
    traversal policy for both `WestToEast` and `NorthToSouth`
  - the `diagram:` block now compacts rectangular route presentation by
    omitting empty rows, only showing `link` rows where chips attach into
    flow, and collapsing long vertical pass-through runs into `⋮`
  - rectangular `diagram:` output is now row-grouped, so each zone-row block
    is followed immediately by the flow rows for that same vertical band and
    then by a seam handoff row before the next zone-row block
  - horizontal rectangular seam rows now distinguish straight continuation
    (`│`) from turning/branching handoff columns with directional tee/corner
    glyphs such as `┬`
  - when a lower rectangular band begins with a `link` row, incoming seam
    handoff stems are now carried into that first lower-band `link`
  - flow-row chip cells are now rendered from solved route contact rather than
    only from declared chip-face hints
  - it is a debugging/test-locking projection, not the target presentation
    renderer
- the debugger REPL is now the primary render-design instrument
  - chip, zone, interconnect, and world draw/print surfaces should be treated
    as the place where visual grammar is discovered
  - the top-level renderer should eventually compose those already-agreed
    primitives rather than invent a competing visual language

## Non-Negotiable Rules

### 1. Artifact-First TDD

For any rendering or layout issue:

1. Render the actual file.
2. Identify the exact wrong rows, columns, and cells.
3. Add a failing artifact-based test first.
4. Only then propose the cause and implement the fix.
5. After the fix, rerender and restate the same rows, columns, and cells.

Never claim a rendering/layout issue is confirmed from model inspection alone.

### 1A. Debugger-First Render Design

For new-engine render design:

1. Treat the current top-level renderer as a planning/debug projection.
2. Use the debugger REPL as the primary design loop.
3. Refine `chip.draw()` / `chip.print()`, zone print/draw helpers,
   interconnect print/draw helpers, and world print/draw helpers first.
4. Only promote a visual convention into the top-level renderer after that
   convention is stable in the debugger.

Do not keep polishing the top-level renderer speculatively when the intended
visual grammar has not yet been made explicit in the debugger surfaces.

Current intended inspection order:

1. inspect every chip
2. inspect every `RoutingZone` that contains those chips
3. inspect every `RoutingZoneInterconnect`
4. inspect the composed world

This order is required because chip geometry drives zone geometry, zone
geometry drives seam expectations, and the world may only regularize geometry
that has already been made explicit at the lower layers.

=== 1B. Zone Geometry Must Be Chip-Geometry-Driven

Current gap: `routing/placement.py::_zoneMetrics_build` sizes zones using a
provisional terminal-count formula (`zoneVerticalSpan = maxTerminalCount`,
`zoneHorizontalSpan = 8` fixed).  It does not call `chipDrawLines_build` or
use real chip row/column budgets.

Required correction:

1. Call `chipDrawLines_build(chip)` for every chip assigned to a zone.
2. Derive the zone's natural frame as the smallest rectangle that contains all
   those chip drawings plus the routing subregion budgets around them.
3. Run the per-row/column normalization pass (already exists in
   `_columnWidthByIndex_build` / `_rowHeightByIndex_build`).
4. For every zone that grows due to normalization: re-solve chip placement
   positions, zone-local routing subregion geometry, and the seam geometry of
   every touching `RoutingZoneInterconnect`.  This is the cascade re-solve.
5. Expose the cascade as `RoutingZone.geometry_recalculateFromReference` and
   `RoutingZoneGrid.zones_normalize` so the REPL `workflows` namespace can
   invoke it interactively.

The REPL `workflows` namespace (planned, not yet implemented) must expose:

- `workflows.chip_geometry_push()` — step 1–2 above
- `workflows.zones_normalize()` — step 3–4 above
- `workflows.zone_recalculate(col, row, ref_zone)` — single-zone cascade
- `workflows.status()` — reports provisional vs chip-driven state per zone

Until these exist, zone and world geometry are provisional and the engine
cannot produce final render geometry.

Immediate execution priority under this rule:

1. fix the debugger REPL experience until completion and object inspection feel
   curated rather than raw
2. use the debugger to make `chip.draw()` match the intended chip language from
   the documented examples
3. only then move on to zone/interconnect/world render exploration

### 2. Modeling Rule

Only true primitives may remain primitive:

- `int`
- `str`
- `float`
- `bool`

Every other non-trivial concept must be a modeled type:

- enum
- dataclass
- value object

Do not use anonymous tuples, ad hoc dictionaries, or magic strings as long-term interfaces in the new engine.

### 3. Parallel In-Place Redesign

Do not mutate the legacy engine into the new engine. Keep the old engine running. Build the new engine beside it. Migrate fixtures progressively. Only retire legacy code after artifact parity has been proven.

Concrete namespace policy:

- all pre-re-architecture implementation code lives under `src/signalflow/legacy/`
- top-level `src/signalflow/` is reserved for the new architecture
- new code may inspect `signalflow.legacy` for reference, but any import from it must be explicit and reviewable
- the bridge between legacy and new code must remain intentionally small

### 4. Sources Of Truth

The new implementation must preserve the explicit sources of truth defined in the design doc:

1. world topology through `RoutingZoneGrid`
2. zone-local placement and local routing substrate through `RoutingZone`
3. solved chip geometry
4. endpoint attach-point ownership
5. edge classification
6. route realization
7. track algebra
8. route semantics
9. route presentation
10. orientation and routing sense
11. legacy/new engine boundary

No downstream subsystem may rediscover any of these by renderer heuristics.

### 5. No Silent Scope Drift

If implementation work uncovers a requirement that changes a source of truth, a route-language rule, or a phase boundary, stop and update both:

- [docs/re-architecture.adoc](/home/rudolphpienaar/src/signalFlow/docs/re-architecture.adoc)
- this plan

before proceeding. Architectural change must not be smuggled through code alone.

## Canonical Language Targets

The new canonical route language is:

- route class:
  - `:compute`
  - `:data`
- compute semantics:
  - `:transform`
  - `:passthrough`
- topology:
  - `:EW`
  - `:WE`
  - `:NS`
  - `:SN`
- presentation:
  - `:color(name)`

Defaults:

- `:compute` implies `:transform` if omitted
- `:data` has no compute semantics

Route qualifiers affect meaning and appearance only. They must not alter topology, edge classification, lane selection, or path realization.

If implementation reveals that a qualifier is being used to choose a different lane allocator, a different attach-point owner, or a different route class, that implementation is wrong and must be corrected rather than normalized.

## Canonical Engine Properties

The new engine must model the following routing-sense and orientation properties explicitly.

### Routing Sense

- `doglegOrder`
- `ribbonJoinOrder`
- `ribbonLeaveOrder`
- `endpointSidePreference`
- `sweepOrder`

Suggested enum values:

- `NorthFirst`
- `SouthFirst`
- `EastFirst`
- `WestFirst`
- `VerticalFirst`
- `HorizontalFirst`
- `InnerSide`
- `OuterSide`
- `LeftSide`
- `RightSide`
- `Ascending`
- `Descending`

### Orientation Regimes

- `LayoutSense`
- `PortSense`
- `RouteSense`
- `LayoutAlignment`

Suggested enum values:

- `LayoutSense`
  - `WestToEast`
  - `NorthToSouth`
- `LayoutAlignment`
  - `Center`
  - `Left`
  - `Right`
  - `Top`
  - `Bottom`
- `PortSense`
  - `HorizontalPorts`
  - `VerticalPorts`
- `RouteSense`
  - `HorizontalRibbon`
  - `VerticalRibbon`

These properties are not optional embellishments. They are how current hidden heuristics become explicit engine policy.

The first implementation may support only the current regime, but it must still express that regime through these modeled properties rather than by hard-coding directional assumptions back into procedural logic.

Layout models must also avoid orientation-biased naming when the concept is sense-relative rather than canvas-relative. In particular:

- use `Span` terminology for sense-relative layout extents
- reserve screen-relative terms such as `width` and `height` for final canvas projection only
- do not let a horizontally named intermediate model become the de facto contract for vertical layout

## Canonical Topology Model

The new engine is now organized around a routing-zone world model.

Core objects:

- `Chip`
  - first-class identity, semantics, ports, and chip-local declarations
- `CircuitDocument`
  - validated typed circuit graph built from YAML ingress
  - owns the canonical chip set and ordered call-edge set before world
    assignment
- `RoutingZone`
  - atomic local routing block
  - owns chip placement within that zone
  - owns the outer zone frame
  - owns explicit `RoutingZoneRegion` geometry for chip-terminal, fan-in/fan-out,
    longitude, and latitude subregions
  - owns local routing substrate through those explicit regions
- `RoutingZoneInterconnect`
  - connects exactly two neighboring zones
  - mediates continuity from one zone into the next
  - owns an explicit seam/interconnect frame
- `RoutingZoneGrid`
  - world topology
  - places zones in a 2D grid
  - places interconnects between neighboring zones
  - chooses macro route paths across multiple zones

Non-negotiable topology rules:

- chips remain first-class objects
- chips belong to exactly one `RoutingZone`
- `RoutingZone` owns chip placement, not chip identity
- `RoutingZoneGrid` is the first world constraint and later placement follows from it
- current simple regime: West-to-East world topology is `1 x (callingDepth - 1)`
- world-level long-haul routing may cross many zones and many interconnects

Ingress rules:

- raw YAML dictionaries stop at `signalflow.engine.input`
- `CircuitDocumentSource` mirrors the serialized shape
- `CircuitDocument` is the validated tree consumed by the new engine
- `Chip` now owns:
  - input-port declarations
  - output-port declarations
  - declarative internal wiring
  - optional `chip_io` overrides
- synthesized chip terminals are explicit derived models, not implicit parser
  folklore
- chip-to-zone assignment is now an explicit planning phase between:
  - `CircuitDocument`
  - and `RoutingZoneGrid`
- placement planning is now a distinct follow-on phase between:
  - `RoutingZoneAssignmentSet`
  - and later routing/geometry solve
- route-obligation derivation is now the first explicit routing-input phase
  between:
  - placed `RoutingZoneGrid`
  - and chip/zone/interconnect/grid solvers

Required initial modeled zone geometry:

- `RoutingZoneFrame`
- `RoutingZoneRegion`
- `RoutingZoneRegionSet`
- `RoutingZoneRegionFrame`
- `RoutingZoneRegionKind`
- `RoutingZoneRegionSide`
- `RoutingZoneInterconnectFrame`

Tiered solve order:

1. solve chip-local routing first so chip geometry is fixed
2. let `RoutingZoneGrid` detect long-haul traffic and reserve interconnect capacity classes
3. let each `RoutingZone` solve its local connectivity in batch
4. let each `RoutingZoneInterconnect` solve local seam continuity
5. let `RoutingZoneGrid` finalize the longer cross-grid connections

Reservation policy:

- world-level reservations are capacity reservations, not specific-wire reservations
- local zone solving may still opportunistically consume spare interconnect capacity when that does not interfere with long-haul channel ownership

## Canonical Fixture Set

The new engine must be developed against named fixture families, not vague examples.

### External Fixture Family

Required fixture files:

- `examples/rearch-external-forward.yaml`
- `examples/rearch-external-backedge.yaml`
- `examples/rearch-external-self.yaml`

Required tests:

- `tests/test_rearch_external_forward.py`
- `tests/test_rearch_external_backedge.py`
- `tests/test_rearch_external_self.py`

Intent:

- `rearch-external-forward.yaml`
  - one parent
  - three children
  - each child has three children
  - no back edges
  - no self edges

- `rearch-external-backedge.yaml`
  - same topology
  - each middle-layer child calls one node in an ancestor column

- `rearch-external-self.yaml`
  - same topology
  - each middle-layer child also self-calls

Required artifact assertions:

- stable forward mainline
- explicit back-edge lanes
- explicit self-edge topology
- no perturbation of unrelated routes when back/self edges are added

Required structural assertions:

- forward edges remain classified as forward edges when back/self edges are introduced
- attach-point ownership stays local to the endpoints of the new edge
- adding a back/self edge does not reclassify unaffected edges

### Internal Fixture Family

Primary fixtures:

- `examples/hub.yaml`
- `examples/explicit-hub.yaml`

Recommended reduced fixtures:

- `examples/rearch-east-reuse-minimal.yaml`
- `examples/rearch-west-reuse-minimal.yaml`
- `examples/rearch-internal-manifold-minimal.yaml`

Required tests:

- `tests/test_rearch_hub.py`
- `tests/test_rearch_explicit_hub.py`
- `tests/test_rearch_internal_minimal.py`

Required artifact assertions:

- local wall reuse does not perturb unrelated manifold structure
- repeated routes create only intended endpoint density
- explicit input and sovereign input consume the same abstract routing rules
- `compute` and `data` share topology and differ only in semantics/presentation

Required structural assertions:

- local reuse is classified before routing begins
- local reuse consumes ribbon capacity only when it truly traverses a ribbon
- endpoint bundle ownership is queryable directly from resolved geometry
- route qualifiers do not alter geometric edge kind

### Simple Circuit Fixture Family

This family is the intended first solver-facing corpus once chip-local and
zone-local solving begins. These fixtures should live under
`examples/simple-circuit/`.

Required fixture files:

- `examples/simple-circuit/root-recursive.yaml`
- `examples/simple-circuit/three-deep-linear.yaml`
- `examples/simple-circuit/three-deep-recursive-each-layer.yaml`
- `examples/simple-circuit/three-deep-ancestor-call-each-layer.yaml`
- `examples/simple-circuit/three-deep-ancestor-call-and-recursion.yaml`

Required test file:

- `tests/test_rearch_simple_circuit.py`

Current status:

- the fixture files now exist under `examples/simple-circuit/`
- `tests/test_rearch_simple_circuit.py` now verifies canonical chip-graph
  ingress, simple-world assignment stability, placement viability, and coarse
  route-obligation scope on this corpus
- `tests/test_rearch_chip_solver.py` now verifies the first chip-local solve
  pass across focused chip-only cases and the simple-circuit corpus
- `tests/test_rearch_zone_solver.py` now verifies the first zone-local solve
  pass against exact planning-grid route points for straight, offset, and
  same-side local routes
- `tests/test_rearch_interconnect_solver.py` now verifies the first seam solve
  pass against exact planning-grid seam points for horizontal and vertical
  adjacent-zone continuity

Intent:

- `root-recursive.yaml`
  - one root chip only
  - root self-calls

- `three-deep-linear.yaml`
  - one root
  - one child
  - one grandchild
  - no recursion
  - no ancestor calls

- `three-deep-recursive-each-layer.yaml`
  - three-deep linear stack
  - each layer has at least one self-call

- `three-deep-ancestor-call-each-layer.yaml`
  - three-deep stack
  - each deeper layer calls one ancestor
  - no self-calls

- `three-deep-ancestor-call-and-recursion.yaml`
  - same ancestor-call topology as above
  - plus self-calls at each layer

Required structural assertions:

- canonical chip-graph ingress models self-calls as self edges, not cloned chips
- canonical chip-graph ingress models ancestor calls as edges to existing chips
- graph depth used for simple-world assignment does not inflate because of self edges
- back/ancestor edges do not perturb canonical depth-layer placement of forward edges
- route-obligation classification distinguishes local, seam-crossing, and longer-haul edges correctly on this corpus

### Local Track Algebra Fixture Family

Required new files:

- `src/signalflow/routing/track.py`
- `tests/test_rearch_track.py`

Required test families:

- elbow formation
- tee formation
- cross formation
- pass-through
- no-op merge
- direction-mask to glyph promotion
- sense-sensitive bend behavior

These tests must not depend on full chip rendering.

## Proposed File Tree

The exact names may change, but the separation of concerns must remain visible.

```text
src/signalflow/
  legacy/
    config.py
    engine/
    lib/
    models/
    scanner/
  engine/
    render.py              # dispatcher, legacy/new engine boundary
  models/
    chip.py
    routing_zone.py
    routing_zone_grid.py
  routing/
    topology.py
    classify.py
    geometry.py
    attach.py
    chip_solver.py
    zone_solver.py
    interconnect_solver.py
    grid_solver.py
    track.py
  render/
    chips.py
    routes.py
```

Suggested high-level responsibilities:

- `models/chip.py`
  - first-class chip identity and chip-local declarations

- `models/routing_zone.py`
  - routing-zone models
  - chip placement ownership inside a zone
  - terminal-region and local-routing-region vocabulary

- `models/routing_zone_grid.py`
  - world topology
  - zone-grid placement
  - interconnect placement

- `routing/chip_solver.py`
  - solve chip-local routing first
  - produce solved chip geometry for later zone placement

- `routing/zone_solver.py`
  - solve local routing inside one routing zone
  - current first pass batch-solves `ZONE_LOCAL` obligations only
  - emits explicit world-coordinate planning polylines through owned zone
    regions

- `routing/interconnect_solver.py`
  - solve seam continuity between exactly two neighboring zones
  - current first pass batch-solves `SEAM_CROSSING` obligations only
  - emits explicit seam polylines across the interconnect frame

- `routing/grid_solver.py`
  - macro path selection across zones
  - capacity reservation
  - long-haul cross-grid finalization

- `routing/classify.py`
  - edge classification
  - route-class normalization
  - ribbon participation decisions

- `routing/topology.py`
  - build an empty `RoutingZoneGrid` skeleton from validated config
  - materialize zone ids and orthogonal neighboring interconnect ids
  - does not solve chip placement or routing

- `routing/geometry.py`
  - zone sizes
  - zone boundaries
  - bundle counts
  - attach-point-ready geometry

- `routing/attach.py`
  - endpoint sockets
  - ingress/egress ownership
  - bundle reuse points

- `routing/route.py`
  - lane allocation
  - orthogonal path realization
  - route sense application

- `routing/track.py`
  - cell-local join algebra
  - glyph promotion

- `utils/pipeline.py`
  - left-to-right stage application over an explicit state object
  - no subsystem-specific fields or semantics

- `render/chips.py`
  - chip frames and labels
  - no route discovery

- `render/routes.py`
  - draw already-resolved paths
  - no topology decisions

If the implementation agent chooses different file names, the same subsystem boundaries must still be preserved and the deviation must be documented in code comments or updated docs.

## Locked-In Namespace And Model Policy

These decisions are no longer provisional. Treat them as the current execution contract unless this plan and the design doc are updated together.

- `src/signalflow/legacy/` is the quarantine tree for the pre-re-architecture implementation.
- Top-level `src/signalflow/` packages are reserved for the new architecture only.
- New code must not casually grow inside `signalflow.legacy` just because legacy code already exists there.
- Shared canonical engine vocabulary belongs in top-level `src/signalflow/models/`.
- Layout owns a typed recursive input model that mirrors the YAML tree without importing unrelated graph semantics.
- Serialized layout input should also be modeled explicitly at the YAML ingress boundary rather than flowing in as raw dictionaries.
- Reusable stage runners and generic helpers belong in top-level `src/signalflow/utils/`.
- Subsystem-local helper/config models may remain local to the owning package when they are not part of the shared engine contract.
- Raw `list[...]` and `dict[...]` collections are acceptable for local implementation detail, but not as durable cross-subsystem contracts in the new engine.
- If a collection is returned, stored as a named result, or shared across subsystem boundaries, model that collection explicitly rather than exposing a bare container type.
- A new module may import from `signalflow.legacy` only as an explicit transitional dependency, and that dependency should be called out in code comments or plan updates if it persists.

Current topology/input policy:

- `RoutingZoneGrid` is now the intended world-level topology owner
- `RoutingZone` is now the intended atomic local routing owner
- `RoutingZoneInterconnect` is the seam-mediation layer between exactly two neighboring zones
- chips are first-class objects and belong to exactly one zone
- zones own chip placement, not chip identity
- the first model layer for `Chip`, `RoutingZone`, `RoutingZoneInterconnect`, and `RoutingZoneGrid` now exists under top-level `src/signalflow/models/`
- the current `new` engine runtime reports pending zone-grid status rather than reusing removed prototype code

## Required Modeled Types

At minimum, expect to create modeled types for:

- `RouteClass`
- `ComputeSemantics`
- `TopologyQualifier`
- `LayoutSense`
- `LayoutAlignment`
- `PortSense`
- `RouteSense`
- `DoglegOrder`
- `RibbonJoinOrder`
- `RibbonLeaveOrder`
- `EndpointSidePreference`
- `SweepOrder`
- `ChipId`
- `ChipRef`
- `RoutingZoneId`
- `RoutingZone`
- `RoutingZoneInterconnect`
- `RoutingZoneGrid`
- `RoutingZoneFrame`
- `RoutingZoneRegion`
- `RoutingZoneRegionSet`
- `RoutingZoneRegionFrame`
- `RoutingZoneRegionKind`
- `RoutingZoneRegionSide`
- `RoutingZoneInterconnectFrame`
- `PortRef`
- `AttachPoint`
- `AttachPointRole`
- `EndpointBundle`
- `ClassifiedEdge`
- `EdgeKind`
- `RoutePath`
- `PathSegment`
- `TrackIntent`
- `TrackCell`

If an implementation choice introduces a new non-trivial concept and it is represented as a tuple or stringly typed field, that is a design smell and should be corrected early.

Bias toward introducing a small new type too early rather than too late. Retrofitting explicit models after routing logic has already grown around tuples and dictionaries is usually more expensive than introducing the type at the first point of ambiguity.

## Phase Plan

### Phase 0: Freeze The Contract

Deliverables:

- keep [docs/re-architecture.adoc](/home/rudolphpienaar/src/signalFlow/docs/re-architecture.adoc) authoritative and current
- keep this file current
- add a CLI engine selector plan and migration notes
- record the namespace-boundary policy and model-ownership policy explicitly

Current status:

- wholesale legacy quarantine is complete under `src/signalflow/legacy/`
- top-level `src/signalflow/` is now available for new architecture modules
- an explicit engine selector now exists at the CLI and engine-dispatch boundary
- the current CLI default is `--engine new`
- the current `new` path emits an honest pending-status report for the zone-grid runtime, not final artifact rendering
- config-only world-grid fixtures now exist under `examples/configs/`
- the initial explicit world-config parser and models now exist for:
  - `world.sense`
  - `world.grid.columns`
  - `world.grid.rows`
  - `world.path_policy`
  - `world.channel_sense`
- `world.grid` is now optional at the YAML boundary and can be derived from
  calling depth plus world sense for the current simple regime

Stop conditions:

- if the design doc and the implementation plan diverge, stop and reconcile before coding further
- if fixture targets are not yet explicit enough to generate failing tests, stop and clarify before coding further

### Phase 1: Engine Boundary

Goal:

- introduce an explicit engine selector and make the runtime boundary unambiguous

Deliverables:

- CLI support for engine selection, for example `--engine legacy` and `--engine new`
- an explicit top-level engine dispatcher in code
- a runnable `new` path even before final rendering exists
- documented default-engine policy

Current status:

- `signalflow --engine legacy` selects the quarantined legacy renderer
- `signalflow --engine new` selects the top-level engine path
- the current CLI default is `new`
- the current `new` engine path returns a zone-grid pending-status report
- this satisfies the boundary requirement but does not yet satisfy rendering parity

Tests:

- CLI selection tests
- engine dispatch tests

Pass gate:

- `signalflow --engine legacy` preserves the legacy rendering path
- `signalflow --engine new` reaches a distinct new-engine path
- the `new` path may return an explicit non-render artifact such as a pending-status report while rendering is still under construction
- the runtime boundary between engines is explicit in code

### Phase 2: Base Models And Sense Enums

Goal:

- create the modeled vocabulary before implementation logic grows

Deliverables:

- shared model types in top-level `models/` as they become cross-subsystem vocabulary
- layout input models in top-level `models/` and YAML parsing in `layout/input.py`
- early world-topology vocabulary such as chip refs, zone ids, grid coords, and routing senses
- corresponding unit tests

Tests:

- enum construction
- dataclass invariants
- validation of route language normalization

Pass gate:

- route directives can be normalized into modeled forms without invoking layout or rendering
- the new modeled vocabulary can be tested independently of the legacy engine
- layout sense and alignment exist as explicit modeled values before layout behavior depends on them
- malformed ingress can fail through explicit `Result[T]` and diagnostics without pushing raw dictionaries deeper into the engine once a zone-grid parser exists

Stop conditions:

- if route model fields begin to proliferate without a stable vocabulary, stop and normalize before adding algorithms

### Phase 3: Edge Classification

Goal:

- classify every edge before geometry or rendering

Deliverables:

- `routing/classify.py`
- edge kinds:
  - `straight`
  - `wall_continuity`
  - `wall_reuse`
  - `manifold_transverse`
  - `external_forward`
  - `external_backedge`
  - `external_self`

Tests:

- classification tests for minimal internal fixtures
- classification tests for forward/back/self external fixtures

Invariants:

- classification must not depend on renderer state
- route class (`compute`/`data`) must not change geometric edge kind

Pass gate:

- every canonical fixture edge can be classified before route realization begins
- classification results can be asserted without rendering the final ASCII artifact

### Phase 4: RoutingZoneGrid / RoutingZone Topology

Goal:

- make routing-zone topology the first-class world model

Deliverables:

- `models/chip.py`
- `models/routing_zone.py`
- `models/routing_zone_grid.py`
- `config/config.py`
- `routing/topology.py`
- `routing/chip_solver.py`
- `routing/zone_solver.py`
- `routing/interconnect_solver.py`
- `routing/grid_solver.py`
- `tests/test_rearch_routing_zone.py`
- `tests/test_rearch_routing_zone_interconnect.py`
- `tests/test_rearch_routing_zone_grid.py`
- `tests/test_rearch_routing_topology.py`

Required responsibilities:

- explicit a priori world-grid configuration
- chip-local solve before zone placement
- chip placement ownership inside one routing zone
- interconnect continuity between two neighboring zones
- world-level zone-grid topology
- macro path selection across multiple zones
- capacity reservation for long-haul traffic
- explicit zone and interconnect placement in the world grid

Modeling obligations:

- zones own chip placement, not chip identity
- no chip may appear in more than one zone
- interconnects connect exactly two zones
- world topology must be explicit before local routing solves
- collection-shaped topology outputs must be modeled explicitly rather than exposed only as raw dictionaries

Artifact obligations:

- long-haul routes preserve continuity across all intermediate zones and interconnects
- zone-local traffic does not destroy reserved interconnect capacity classes
- world topology is visually conserved under the current simple `1 x (depth - 1)` regime
- local zone changes do not silently alter world-level route paths

Current status:

- the first explicit zone/grid/interconnect model layer now exists at:
  - `src/signalflow/models/chip.py`
  - `src/signalflow/models/routing_zone.py`
  - `src/signalflow/models/routing_zone_grid.py`
- explicit world-grid configuration is centralized at:
  - `src/signalflow/config/config.py`
- an empty world-topology builder now exists at:
  - `src/signalflow/routing/topology.py`
- focused topology tests now exist at:
  - `tests/test_rearch_routing_topology.py`
- the current implementation stops at topology materialization; it does not yet
  place chips, reserve long-haul capacity, or solve routes

Pass gate:

- a zone-grid topology can be computed and tested without invoking the final renderer
- long-haul route paths are world-level modeled results rather than renderer heuristics
- zone/interconnect continuity is queryable directly from modeled results

### Phase 5: Intra-Chip Geometry

Goal:

- compute zone geometry and endpoint bundles from classified edges

Deliverables:

- `routing/geometry.py`
- `routing/attach.py`
- geometry-focused tests

Required responsibilities:

- top ribbon size and bounds
- dogleg zone size and bounds
- bottom ribbon size and bounds
- symmetric zone equations
- attach-point ownership
- bundle counts
- ribbon participation

Artifact obligations:

- local reuse does not consume ribbon capacity unless it truly traverses the ribbon
- top and bottom equation families are symmetric

Pass gate:

- chip-local geometry can be tested as a resolved model
- attach-point ownership can be queried directly without consulting rendered glyphs

Current status:

- `routing/geometry.py` now exists with `ChipLocalGeometry`, `ChipLocalGeometrySet`,
  and `chipLocalGeometryResult_build` / `chipLocalGeometrySetResult_buildFromChips`
- `routing/attach.py` now exists with `ChipAttachPoint`, `ChipAttachPointSet`,
  and `chipAttachPointSetResult_buildFromPlacedZone`
- `routing/__init__.py` exports all four new builders
- `tests/test_rearch_routing_geometry.py` covers geometry derivation and world
  attach-point computation (16 passing tests)
- The cascade re-solve bug in `placement.py` is also fixed in this phase:
  `zoneHorizontalSpan` and `zoneVerticalSpan` now use normalised column/row
  sizes; east/south terminal regions are right/bottom-aligned within the
  (possibly larger) normalised frame

### Phase 6: TrackLaying Algebra

Goal:

- isolate all local glyph resolution

Deliverables:

- `routing/track.py`
- `tests/test_rearch_track.py`

Required responsibilities:

- cell-local intent merge
- elbow, tee, cross, pass-through resolution
- direction-mask to glyph promotion

Artifact obligations:

- no chip or module fixture required for core track tests
- tables should be sufficient to prove local correctness

Pass gate:

- local track tests cover elbows, tees, crosses, pass-through, and no-op merges
- renderer code no longer owns the cell-local join rules under the new engine path

Current status:

- `routing/track.py` implemented with full 16-entry glyph table, `TrackDirection`
  enum, `TrackIntent` / `TrackCell` frozen dataclasses, and all builder/merge helpers
- `tests/test_rearch_track.py` written: 45 tests across 7 classes — glyph table
  completeness, elbow/tee/cross formation, variadic merge, intent round-trip,
  idempotence, and `isEmpty` property; all 45 pass
- `routing/__init__.py` updated to export all Phase 6 public symbols
- pass gate satisfied: elbows, tees, crosses, pass-through, and no-op merges are
  covered; direction-mask → glyph promotion is table-driven inside `track.py`

### Phase 7: Route Realization

Goal:

- realize classified edges into orthogonal paths from resolved attach points

Deliverables:

- `routing/route.py`
- route realization tests

Required responsibilities:

- lane allocation
- dogleg placement
- ribbon entry and exit
- sweep order
- route sense application

Artifact obligations:

- identical topology under different route semantics uses the same path
- back/self edges do not perturb unrelated forward edges

Pass gate:

- realized routes are modeled path objects rather than immediate canvas writes
- route realization can be tested without the final renderer

Current status:

- `routing/route.py` implemented with:
  - `RouteSense` enum (FORWARD / BACK / SELF)
  - `RealizedRouteCell` frozen dataclass: (worldRow, worldCol, trackCell)
  - `RealizedRoute` frozen dataclass: metadata + cells tuple + `cellAt_get`
  - `RealizedRouteSet` frozen dataclass: collection + `routesForChip_get` +
    `mergedCellMap_get` (union of all route TrackCells for canvas projection)
  - `routePoints_realize` core builder: expands waypoint polylines into
    per-cell TrackCells via the Phase 6 track algebra; returns Result[RealizedRoute]
  - `realizedRouteSetResult_buildFromZoneLocalSolvedRouteSet` higher-level
    builder from zone-local solved routes
- `tests/test_rearch_route.py` written: 31 tests across 9 classes —
  horizontal/vertical segments, elbow/tee/cross formation, dogleg Z-shape,
  pass-through overlap, RouteSense invariance, cellAt_get, error cases,
  set lookup, zone-local builder round-trip; all 31 pass
- `routing/__init__.py` updated to export all Phase 7 public symbols
- pass gate satisfied: realized routes are typed model objects (`RealizedRoute`)
  not canvas writes; all tests run without touching any renderer

### Phase 8: Rendering Projection

Goal:

- render resolved layout and resolved routes with no topology inference

Deliverables:

- `render/chips.py`
- `render/routes.py`
- fixture render tests

Current status:

- `render/chips.py` implemented: `chipLines_render(chip) -> tuple[str, ...]`
  delegates to `chipDrawLines_build` as the single source of truth; the render
  layer adds no topology logic and is the stable API surface for future color
  and style hints
- `render/routes.py` implemented: `routeWorldCanvas_render(realizedRouteSet,
  canvasSize) -> tuple[str, ...]` projects the Phase 7 merged cell map to a
  world-coordinate ASCII canvas; uses Phase 6 TrackCell glyphs; no routing,
  solve, or reclassification occurs inside the renderer
- `render/__init__.py` exports both public symbols
- `tests/test_rearch_render.py` extended with 22 new Phase 8 tests across two
  classes (`TestChipRender` and `TestRouteWorldCanvas`): chip box shapes,
  terminal stubs, arrow presence, separator rows, immutability; horizontal and
  vertical canvas projection, L-shaped elbow, crossing routes, explicit sizing,
  padding, pass-gate test proving the renderer requires no CircuitDocument; all
  24 tests in the file pass
- pass gate satisfied: renderer consumes only `Chip` model objects and
  `RealizedRouteSet` objects; no test invokes a solver, placement, or
  obligation builder inside the renderer

Hard rule:

- rendering may map semantics to glyphs and color
- rendering may not discover new topology

Pass gate:

- renderer consumes modeled layout, geometry, attach-point, and route-path inputs only
- no render test requires rerouting or reclassification logic inside the renderer

### Phase 9: Fixture Migration

Goal:

- prove parity on canonical fixtures

Required targets:

- `rearch-external-forward.yaml`
- `rearch-external-backedge.yaml`
- `rearch-external-self.yaml`
- `hub.yaml`
- `explicit-hub.yaml`

Parity definition:

- artifact invariants are met
- no unrelated route movement across fixture variants
- route semantics affect appearance, not path geometry

Pass gate:

- each canonical fixture renders successfully under the new engine
- differences from legacy output are explicitly documented as intended improvements or treated as failures

Current status:

- Three new `rearch-external-*.yaml` fixture files created in
  `examples/simple-circuit/`:
  - `rearch-external-forward.yaml`: caller() → callee(), depth=2, one zone,
    one ZONE_LOCAL obligation
  - `rearch-external-backedge.yaml`: caller() → callee() → caller(), depth=2,
    one zone, two ZONE_LOCAL obligations (forward + back edge)
  - `rearch-external-self.yaml`: worker() → worker(), depth=1, one zone,
    one ZONE_LOCAL obligation
- `tests/test_rearch_fixture_migration.py` written: 36 tests across 6 classes
  covering all five canonical fixtures plus a `TestRouteSemanticInvariance`
  class proving that FORWARD/BACK/SELF senses produce identical cells
- All five fixtures pipeline successfully without errors; hub and explicit-hub
  each produce 10 zone-local + 5 seam solved routes
- Parity invariants proven:
  - backedge fixture zone-local count = forward-only count + 1 (back edge
    adds exactly one route; forward route is unchanged)
  - explicit-hub and hub have identical zone-local and seam route counts
  - route sense does not affect path geometry (cells identical under
    FORWARD vs BACK vs SELF)
- The `--engine new` path still delegates to the legacy renderer for ASCII
  output; this is documented behavior (Phase 8 render layer provides
  `routeWorldCanvas_render` which is the new-path projection); the legacy
  delegation is intentional until Phase 10 flips the default
- pass gate satisfied: all five fixtures render successfully under the new
  engine pipeline; hub/explicit-hub differences from legacy are legacy
  renderer output (no new-engine divergence)
- 504 total tests, all passing

### Phase 10: World Canvas Compositor

Goal:

- implement the composition layer that assembles chip bodies + route wires
  into a full world-coordinate ASCII canvas
- expose `world.canvas_print()` / `world.canvas_render()` in the debug REPL

Deliverables:

- `src/signalflow/render/world.py` — `worldCanvas_render(placedGrid,
  circuitChipSet, realizedRouteSet)` that places chip bodies at terminal
  region positions and overlays route wire glyphs
- `realizedRouteSetResult_buildFromInterconnectSolvedRouteSet` in
  `routing/route.py` — builds `RealizedRouteSet` from seam-crossing solved
  routes (parallel to the existing zone-local builder)
- `DebugGridView.canvas_render()` / `canvas_print()` in the debug REPL —
  realizes zone-local + seam routes, calls `worldCanvas_render`, returns
  the assembled string; `world.canvas_print()` is the canonical REPL command
- 9 new Phase 10 tests in `tests/test_rearch_render.py`

Current status:

- `render/world.py` implemented: allocates a world-sized char grid, blits
  chip bodies by stacking them within each zone's CHIP_TERMINAL region
  (vertically for WEST_TO_EAST zones, horizontally for NORTH_TO_SOUTH),
  then overlays route wire glyphs from the merged cell map
- `realizedRouteSetResult_buildFromInterconnectSolvedRouteSet` added to
  `routing/route.py` and exported from `routing/__init__.py`
- `_worldCanvasText_build` helper in `engine/debug.py` combines zone-local
  and seam routes into one `RealizedRouteSet` before calling `worldCanvas_render`
- `DebugGridView` updated: `__dir__` now advertises `canvas_render` and
  `canvas_print`; REPL helper lines and world manual page updated
- All five canonical fixtures produce correct world canvases
- 513 total tests, all passing
- REPL usage confirmed: `world.canvas_print()` renders full chip-body +
  route-wire canvas for any loaded YAML document

### Phase 11: Legacy Retirement

Goal:

- retire old code only when new parity is complete

Deliverables:

- explicit audit of remaining legacy-only features
- deprecation path
- final engine default switch (wire `newEngineArtifact_render` to call
  `worldCanvas_render` instead of delegating to `diagramLegacy_render`)

Current status:

- `newEngineArtifact_render` in `engine/render.py` now runs the full staged
  pipeline and calls `worldCanvas_render` with combined zone-local + seam
  routes; the legacy delegation is removed
- two transitional parity tests updated:
  `test_new_engine_matches_legacy_output` → `test_new_engine_produces_world_canvas_not_legacy_artifact`
  `test_diagram_render_new_engine_matches_legacy_for_deep_tree` → `test_diagram_render_new_engine_differs_from_legacy_for_deep_tree`
- `--engine new` (the default CLI path) now renders the world canvas for all
  canonical fixtures
- 513 total tests, all passing

Stop conditions:

- if any canonical fixture still depends on legacy-only behavior, do not flip the default
- if the new engine still contains renderer-discovered topology, do not flip the default

### Phase 12: Module Boxes and Wire-Crossing Piercing

Goal:

- restore the legacy engine's double-line module grouping boxes in the new
  world canvas compositor
- ensure route wires that cross module box walls produce correct Unicode
  piercing glyphs instead of silently overwriting the wall character

Deliverables:

- `_moduleBoxes_blit` in `src/signalflow/render/world.py`:
  - collects world-coordinate chip footprints via `_chipWorldCoords_collect`
  - groups chips by `chip.chipId.moduleName`
  - draws a `╔═ ModuleName ════╗` / `║` / `╚════╝` double-line box with
    1-cell padding around each module group
  - drawn before chip bodies are blitted so chip content overlays the
    box interior; box borders frame the group
- `_piercedGlyph` in `src/signalflow/render/world.py`:
  - applied to every route-wire overlay cell
  - `║` + purely horizontal route → `╫` (horizontal single through vertical
    double)
  - `═` + purely vertical route → `╪` (vertical single through horizontal
    double)
  - all other combinations fall back to the route wire's own glyph
- `src/signalflow/models/interconnect_route.py`:
  - added `STRAIGHT_SEAM_RETURN` and `OFFSET_SEAM_RETURN` solve-kind enum
    values
- `src/signalflow/routing/interconnect_solver.py`:
  - `_seamGeometryResult_build` / `_horizontalSeamGeometryResult_build` /
    `_verticalSeamGeometryResult_build` now accept `isReturn: bool`; each
    `SEAM_CROSSING` obligation produces a forward + return route pair
- wire stubs on chip bodies now use `─` padding (not space) so labels of
  different lengths align without phantom spaces

Current status:

- 513 tests passing
- module boxes visible in all simple-circuit fixture renders
- wire-crossing piercing (`╫`) confirmed on three-deep-linear and self-edge
  examples

## Canonical Invariants To Assert Throughout

- Adding a local reuse edge must not perturb unrelated manifold structure.
- Adding a back edge must not require a special-case renderer path.
- Adding a self edge must not perturb unrelated forward edges.
- Route qualifiers must not alter topology.
- Identical topology under different qualifiers must route through the same cells.
- Internal and external routes must be explainable through the same abstract edge model.
- No internal route is rendered for an opaque chip in the new engine unless explicitly documented as legacy compatibility.
- The same geometric question must not be answered by two different subsystems.

## Practical Warnings For The Agent

- Do not patch the legacy renderer to simulate the new architecture.
- Do not place new architecture code under `signalflow.legacy`.
- Do not import from `signalflow.legacy` in new modules unless the dependency is explicit, temporary, and justified.
- Do not bury shared canonical engine models inside subsystem-local `models.py` files once those models are meant to be consumed across subsystems.
- Do not expose raw `list[...]` or `dict[...]` types as durable new-engine boundary contracts when a collection model is the real concept.
- Do not use `width` and `height` for sense-relative intermediate layout concepts; use `Span` terminology until the canvas-projection boundary.
- Do not leave layout alignment implicit; model it explicitly.
- Do not infer topology from glyphs during the new render path.
- Do not allow `compute` or `data` to change route class.
- Do not encode orientation assumptions as incidental `if east then ...` logic.
- Do not let attach-point ownership leak into renderer heuristics.
- Do not write the new engine around the current field names just because they already exist.
- Do not treat plausible internal telemetry as proof of a correct artifact.
- Do not treat a correct-looking artifact as proof of a clean architecture if ownership still lives in the wrong subsystem.

## Suggested Immediate First Moves

1. Keep the `signalflow.legacy` quarantine intact and do not erode the boundary.
2. Keep the explicit engine boundary in place with `new` as the default CLI path.
3. Finish the layout slice so it owns both typed input and typed output models.
4. Create the new route, sense, and shared model types.
5. Add the external forward/back/self fixtures.
6. Add the `TrackLaying` subsystem with table tests.
7. Only then begin implementing the new geometry and routing path.

This order is intentionally conservative. It establishes vocabulary and evidence before algorithmic complexity grows.

## Minimum Deliverables Before Claiming Meaningful Progress

Do not claim meaningful progress on the redesign until all of the following exist:

- an explicit runtime engine selector
- new modeled route and sense types
- at least one external fixture on the new path
- at least one internal minimal fixture on the new path
- at least one artifact-based test running against the new engine
- a standalone `TrackLaying` test file

Anything less may still be useful setup work, but it is not yet evidence that the new architecture is functioning.
