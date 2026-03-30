# Snippets

This directory contains reusable REPL snippet files for live SignalFlow inspection.

Snippets are regular Python files intended to be executed from the debug REPL with:

```python
load("snippets/algebraic/hub_kernel_solver.py")
```

You can also preload one snippet when launching the REPL:

```bash
signalflow --engine new --repl \
  --load-snippet snippets/algebraic/hub_kernel_solver.py \
  examples/hub.yaml
```

Or run one snippet non-interactively and exit:

```bash
signalflow --engine new \
  --run-snippet snippets/algebraic/hub_kernel_solver.py \
  examples/hub.yaml
```

Rules:

- keep each snippet focused on one inspection task
- prefer assigning named variables that remain useful after the snippet runs
- print only the key results needed for quick inspection
- avoid hidden side effects

Current categories:

- `snippets/algebraic/`
  - symbolic-routing and board/algebra inspection snippets
  - `hub_internal_wiring.py` for the quarantined `Hub.ts.process()` internal board

Current first-class runtime types used by the snippets:

- `BoardZone`
- `BoardKernel`
- `Board`
- `BoardSolver`
- `BoardSolution`
- `BoardMaterializedSolution`
