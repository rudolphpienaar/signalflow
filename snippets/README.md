# Snippets

This directory contains reusable REPL snippet files for live SignalFlow inspection.

Snippets are regular Python files intended to be executed from the debug REPL with:

```python
load("snippets/algebraic/hub_kernel_solver.py")
```

Rules:

- keep each snippet focused on one inspection task
- prefer assigning named variables that remain useful after the snippet runs
- print only the key results needed for quick inspection
- avoid hidden side effects

Current categories:

- `snippets/algebraic/`
  - symbolic-routing and board/algebra inspection snippets
