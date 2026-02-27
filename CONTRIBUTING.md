# Contributing

Contributions are welcome. Please open an issue before submitting a pull request
for anything beyond a trivial fix.

## Development setup

```bash
git clone https://github.com/rudolphpienaar/signalFlow
cd signalFlow
pip install -e ".[dev]"
pytest
```

## Style

- Python 3.10+, standard library only (plus `pyyaml`).
- RPN naming convention: `noun_verb()` (e.g. `layout_compute`, `canvas_create`).
- All public functions have a one-line docstring minimum.
- Tests live in `tests/` and must pass before any PR is merged.

## Commit messages

Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`.
