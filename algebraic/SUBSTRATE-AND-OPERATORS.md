# Substrate And Operators

This file records an architectural doctrine that has become explicit through the symbolic kernel routing work.

## Core Idea

The system should be understood as a stable substrate plus explicit operators that act on that substrate.

The substrate is the stateful, inspectable, doctrine-bearing part of the system.

The operators are the executable transforms that consume the substrate and produce new symbolic or realized results.

Operators must not secretly redefine the substrate they act on.

## Signalflow Mapping

In the current routing re-architecture, the substrate side includes:

- world
- zones
- routing kernels
- realized geometry areas
- board
- channels
- lanes
- canonical symbolic names
- enum-governed doctrine

The operator side includes:

- symbolic solver
- materializer
- validators
- REPL snippets
- other execution surfaces that work over board and wiring state

This means the solver is not the source of the board.

The board is upstream.

The solver consumes the board.

## Why This Matters

This split reduces hidden coupling.

It makes the state of the routing problem inspectable before any solve occurs.

It makes operators replayable and comparable against the same substrate.

It keeps the solver from becoming a hidden geometry engine that both defines and consumes its own world.

It also keeps the REPL honest.

The REPL may simplify the architecture, but it must still expose real substrate objects and real operators over those objects.

## Architectural Consequence

The active routing architecture should be read as:

1. geometry exists
2. board is built from geometry
3. wiring exists in that board context
4. solver operates on board plus wiring plus doctrine
5. materializer converts symbolic paths into realized route geometry

This ordering is load-bearing.

The operator is downstream of the substrate.

## Relation To Other Systems

This doctrine is not accidental.

It reflects a recurring architectural pattern in systems where truth must remain explicit and inspectable.

The same general split appeared in ChRIS-derived thinking and in ARGUS, where state-bearing substrate and executable guest logic were deliberately separated.

The important point here is the architectural principle, not the word `plugin`.

Signalflow does not need plugin machinery to benefit from the same separation.

It needs explicit substrate models and explicit operators over those models.

## Non-Goal

This doctrine does not require over-abstracting every transform into a dynamic plugin mechanism.

Simple typed operators and builder functions are acceptable when they preserve the substrate/operator split clearly.

## Current Practical Rule

When introducing a new routing concept, ask two questions:

1. Is this a substrate object that should exist and be inspectable before solving?
2. Or is this an operator that consumes substrate and produces a result?

If the code cannot answer that cleanly, the boundary is probably wrong.
