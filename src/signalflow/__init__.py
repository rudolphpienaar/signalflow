"""SignalFlow package root for the re-architecture transition.

The top-level `signalflow` namespace is now reserved for the new architecture.
The pre-existing implementation lives under `signalflow.legacy` as an explicit
compatibility and reference tree. New subsystems should be added at the package
top level rather than under `signalflow.legacy`.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _version_build() -> str:
    try:
        return version("signalflow")
    except PackageNotFoundError:
        pyprojectPath = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyprojectPath.open("rb") as handle:
            pyproject = tomllib.load(handle)
        return str(pyproject["project"]["version"])


__version__ = _version_build()
