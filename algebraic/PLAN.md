# Plan

This file defines the execution order for the first live symbolic-kernel-routing implementation.

## Goal

The first implementation target is not production cutover.

The first implementation target is a live quarantine solver that can operate in isolation from the production kernel solver.

## Quarantine Principle

The quarantine solver must:

- consume real wiring
- consume real board-like geometry data
- consume real packing doctrine
- produce algebraic paths
- remain inspectable from the REPL

The quarantine solver must not replace the production kernel solver until the symbolic board and path surfaces are trustworthy.

## Why REPL First

The REPL is the right live harness because the immediate design questions are inspectability questions:

- what is the wiring in this kernel
- what are the channels
- how many lanes are in each channel
- what algebraic path does the solver choose
- do the chosen labels and lane indices make sense

That means the first useful implementation is debug-facing, not renderer-facing.

## Phase 1

Materialize the first board-like symbolic inspection surface in the REPL.

This phase should expose:

- `kernel.wiring_get()`
- `wiring.channels_get()`
- `channels.channel_get(name)`
- `channel.lanes_get()`
- `lanes.lane_get(index)`

This phase does not require production route solving changes.

## Phase 2

Implement the first isolated symbolic solver inside the debug quarantine layer.

This phase should:

- solve from wiring plus board plus packing doctrine
- emit algebraic path text
- stay limited to the current supported board shape first
- prefer explicit unsupported-context messages over fake generality

Initial target:

- intra kernel
- west-to-east zone sense
- forward and return shell packing

## Phase 3

Add symbolic-suite tests that treat the quarantine solver as the active authority for symbolic path generation.

These tests should verify:

- channel names
- lane counts
- lane ordering
- canonical symbolic names
- forward algebraic path generation
- return algebraic path generation

## Phase 4

Once the quarantine solver is trustworthy, add a materializer that turns algebraic paths into route points.

Only after that should the production kernel solver be replaced.

## Non-Goals For This First Step

Do not:

- replace the production kernel solver yet
- preserve legacy tests as default authority
- implement every kernel shape at once
- hide unsupported contexts behind fake generic behavior

## Anti-Zombie Rule

If the quarantine implementation starts duplicating large pieces of production route realization, stop and refactor the boundary.

The quarantine layer is allowed to be additive.

It is not allowed to become a second permanent solver stack.
