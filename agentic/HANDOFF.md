# Handoff: `worldscale-extra-routing`

## Branch And Version

- Branch: `worldscale-extra-routing`
- Version: `5.9.15`
- Branch point commit: `07c46b4` (`Add papers and worldscale geometry notes`)

## What Just Happened

### v5.9.15 — housekeeping, naming, tooling

#### Pyright Clean Sweep

All non-legacy pyright errors resolved. 0 errors, 18/18 tests passing.
Fixes were surgical: missing imports, None guards, type casts at data
boundaries, `# type: ignore` only for genuine false positives.

#### Naming Cleanup

- `NewEngineDebugContext` → `SignalFlowContext`
- `newEngineDebugContextResult_buildFromDocumentDict` → `context_buildFromDocument`
- `newEngineDebugRepl_run` → `repl_run`
- `newEngineDebugSnippet_run` → `snippet_run`
- `newEngineArtifact_render` → `worldDiagram_lprint`
- `_text()` suffix → `_sprint()` codebase-wide (str return convention)
- `_lprint()` reserved for `list[str]` returns

#### Snippet Infrastructure

- New `snippets/algebraic/zone_geometry.py` — standalone zone geometry inspector
  that works without REPL injection
- CLI `--` passthrough: `signalflow ... --run-snippet foo.py -- --zone 1,1`
  passes `--zone 1,1` into the snippet's `sys.argv`
- `source_yaml` injected into every snippet namespace by the runner
  (path to the YAML file on the CLI)
- `result_isOkCheck` aliasable as `OK` — emerging snippet convention

#### Glyph Fix

`EXTRA_TRANSITION` and `INTRA_EXTRA_TRANSFER` corner glyphs were swapped
east/west. Corrected in `board/render.py`:
- west corners: `╔` (north) / `╚` (south)
- east corners: `╗` (north) / `╝` (south)
Both families now consistent.

### v5.9.14 — geometry doctrine correction

Three doctrine errors from v5.9.13 corrected:

1. **Removed ╠ re-entry transfer** — transition zones exist only at lat/long
   corners. The xwLong→wChipTerminal face has no lat crossing, so no
   transition. `RegionBranch.EAST`/`WEST` removed from `types.py`.
   `╠`/`╣` entries removed from `render.py`.

2. **Added extra-side fan regions** — chips have fan in/out on both faces in
   the routing sense direction. New `EXTRA_FAN` family:
   - `west/extra_routing_fan_in_out`: col 15..18, row 5..44 (between xwLong
     and wChipTerminal)
   - `east/extra_routing_fan_in_out`: col 105..108, row 3..46 (between east
     module boundary and xeLong)
   `xwLong` shifted left to col 9..14; `xeLong` shifted right to col 109..114.

3. **Fixed N/S dummy terminal stacking** — N/S chip terminal and fan frames
   were between xnLat/xsLat and the intra longitude bands, blocking path
   continuity. Corrected in `_extraGeometry_build`: `intraNorthTop` now
   anchors on `westChipTerminalFrame.verticalStart` (intra long top), and
   N/S dummy frames are re-stacked outside xnLat/xsLat. Result:
   - `xnLat` row=1..4 adjacent to `wLong:upper` top (row=3)
   - N/S dummies at row=−1 (north terminal), row=0 (north fan), row=49
     (south fan), row=50 (south terminal)

#### Eight transition zones — complete statement

| Ring | NW | NE | SW | SE |
|---|---|---|---|---|
| Intra | wLong∩nLat | eLong∩nLat | wLong∩sLat | eLong∩sLat |
| Extra | xwLong∩xnLat (╔) | xeLong∩xnLat (╗) | xwLong∩xsLat (╚) | xeLong∩xsLat (╝) |

No other transition zones. Chip faces are plain adjacency.

### v5.9.13 — sf1 re-entry transfer and path verification

Added the missing `xwLong → wChipTerminal` lateral re-entry transfer and
verified both sf1 path variants through the placed region frames.

### v5.9.12 — `intra ↔ extra` transfer regions

Four explicit transfer regions placed at the corners where intra longitude
bands meet the extra latitude bands.

### v5.9.11 — `extra` perimeter frame placement

The four `extra` region families are now live in the board geometry for
WTE/ETW kernels.

### v5.9.10 — Board geometry flush + `extra` doctrine

## The Most Important Current Runtime APIs

- `chip: BoardChip = chips.chip_get("Hub.ts", "process()")`
- `kernel: BoardKernel = chip.internalBoard_get()`
- `board: Board = kernel.board_get(chipPlacementPolicy=...)`
- `solver: BoardSolver = kernel.solver_get(board)`
- `solution: BoardSolution = solver.solution_get()`
- `materialized: BoardMaterializedSolution = solution.board_materialize(board, policy=...)`
- `zones.zone_get(1, 1).kernel_get("intra")` → `BoardKernel`
- `context_buildFromDocument(documentDict)` → `Result[SignalFlowContext]`

## Snippets

- `snippets/algebraic/hub_internal_geometry.py` — internal chip board geometry
- `snippets/algebraic/zone_1_1_geometry.py` — zone (1,1) intra board geometry (REPL)
- `snippets/algebraic/zone_geometry.py` — zone geometry standalone (CLI with `--zone`)
- `snippets/algebraic/hub_internal_wiring.py` — internal chip wiring + collisions

## Current Design Direction

Geometry substrate is correct. Span defaults are scattered — `BoardGeometrySpec`
is the immediate next implementation task. See `agentic/DOTHIS.md`.

## Hard Problem Still Unresolved

Child-to-self routing. A route leaving `p4()` into `extra` must preserve
enough row/layer identity to return specifically to `p4()`, not to the
parent-facing side of the zone. Do not hand-wave this.

## What Not To Trust

Stale `agentic/` notes mentioning `rearch-zone-grid`, `566/0`, seam kernels
as the settled next milestone, or chip-internal kernel as the singular concern.

## Operating Discipline

- if you are guessing, say so
- if something is partial, say so
- if a property is claimed, point to the runtime path or snippet output
- if the user says `DNC`, do not code
