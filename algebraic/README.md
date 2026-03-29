# Algebraic Routing

This directory is the active design home for the `symbolic-kernel-routing` branch.

Its purpose is to define and drive the algebraic re-architecture of kernel routing:

- geometry builds the board
- the symbolic solver chooses the unique algebraic path on that board
- the materializer converts the algebraic path into realized routing geometry

This directory is intentionally separate from:

- `agentic/`
  - operator and agent guidance
- `legacy/`
  - archived historical documents that are no longer active authority

The first documents here are:

- `DOCTRINE.md`
  - the active architecture truths
- `SUBSTRATE-AND-OPERATORS.md`
  - the substrate/operator split made explicit
- `MIGRATION.md`
  - the replacement plan and anti-zombie rules
- `PLAN.md`
  - the first live quarantine execution order

Future documents should stay focused on the algebraic routing effort itself, not general repo process.
