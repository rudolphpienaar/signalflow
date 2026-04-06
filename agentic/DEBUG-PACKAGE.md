# Inspect Package Map

`src/signalflow/engine/inspect/` is the new-engine inspection surface package. It is no
longer a monolithic `debug.py`, and it no longer carries a duplicate solve or
materialize runtime.

## Module Roles

- `context.py`
  - Shared inspect context and workflow-level surface types.
  - Owns `SignalFlowContext`.

- `build.py`
  - Builds inspect context from parsed documents and assembles inspect artifacts.
  - This is the main package bootstrap layer.

- `repl.py`
  - REPL entry points, snippet loading, locals bootstrap, prompt handling, and
    display hook plumbing.

- `views.py`
  - Human-facing display surfaces and `*_sprint()` presentation helpers.
  - Also owns the manual/display formatting layer.

- `geometry.py`
  - Board/world text rendering helpers and geometric text-layout helpers.

- `backend.py`
  - Inspect board-backend selection helpers.

- `terminal.py`
  - Narrow terminal/readline/history state and ANSI constants.

- `primitives.py`
  - Lightweight debug wrapper types for region and kernel board primitives.

- `surfaces.py`
  - Higher-level interactive chip/kernel/zone handles built on top of the
    primitive wrappers.

- `handles.py`
  - Transitional compatibility home for the small amount of handle glue that
    did not merit its own module.

- `kernel_runtime.py`
  - Inspect helpers that project kernel/board runtime structures into the inspect
    package surfaces.

- `chip_helpers.py`
  - Chip and zone helper builders plus chip/world-frame helper logic.

- `manual.py`
  - Help/manual text content for the REPL and debug display surfaces.

## Boundaries

- The authoritative solve/materialize runtime lives under `src/signalflow/board/`.
- `src/signalflow/engine/inspect/` should project that runtime for inspection.
- If a new debug helper starts recomputing solve state or materialized state, it
  is probably being added in the wrong place.

## Done State

The meaningful refactor is complete when:

- there is no duplicate runtime architecture inside `engine/inspect`
- shared code has an explicit module home
- remaining local imports are only targeted cycle breaks, not diffuse centers of
  truth
