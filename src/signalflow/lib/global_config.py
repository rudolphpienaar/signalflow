"""Global configuration loading — user and project level.

Priority chain (lowest → highest):
  Config dataclass defaults
  < ~/.config/signalflow/config.yaml   (user preferences, XDG)
  < .signalflow.yaml                   (project/repo, walks up to git root)
  < config: section in wiring YAML     (per-document overrides)

Usage:
  globalConfig_load()   — called once at CLI startup
  globalConfig_reset()  — called by diagram_render before per-doc config,
                          so documents do not bleed config into each other
"""
from __future__ import annotations

import os
import sys
from dataclasses import fields
from pathlib import Path

import yaml

from signalflow.config import config

# Snapshot captured after startup global configs are applied.
# Empty dict means globalConfig_load() was never called (e.g. in tests),
# in which case globalConfig_reset() is a safe no-op.
_baseline: dict = {}


def _userConfigPath_get() -> Path | None:
    """Return the XDG user config path if it exists."""
    xdg: str | None = os.environ.get("XDG_CONFIG_HOME")
    base: Path = Path(xdg) if xdg else Path.home() / ".config"
    candidate: Path = base / "signalflow" / "config.yaml"
    return candidate if candidate.is_file() else None


def _projectConfigPath_get() -> Path | None:
    """Return the nearest .signalflow.yaml, searching up to the git root.

    Starts from the current working directory.  Checks each directory for
    .signalflow.yaml before deciding whether to continue upward.  Stops
    after checking the git root (directory containing .git) so the search
    never crosses a repository boundary.
    """
    current: Path = Path.cwd()
    while True:
        candidate: Path = current / ".signalflow.yaml"
        if candidate.is_file():
            return candidate
        parent: Path = current.parent
        if parent == current:
            # Reached filesystem root
            break
        if (current / ".git").exists():
            # This is the git root; we've already checked it above, stop here
            break
        current = parent
    return None


def _configFile_load(path: Path) -> None:
    """Load a single config YAML file into the singleton.  Warns on error."""
    try:
        with open(path) as fh:
            data: dict = yaml.safe_load(fh) or {}
        config.config_update(data)
    except Exception as exc:
        print(
            f"signalflow: warning: could not load config {path}: {exc}",
            file=sys.stderr,
        )


def globalConfig_load() -> None:
    """Load user and project configs, then capture the result as the baseline.

    Call this once at CLI startup.  After this call, globalConfig_reset()
    restores the singleton to the post-global-load state, letting per-document
    config: sections apply cleanly without bleeding into subsequent renders.
    """
    global _baseline

    for path in (_userConfigPath_get(), _projectConfigPath_get()):
        if path is not None:
            _configFile_load(path)

    _baseline = {f.name: getattr(config, f.name) for f in fields(config)}


def globalConfig_reset() -> None:
    """Reset the config singleton to the startup baseline.

    No-op if globalConfig_load() was never called (e.g. in tests).
    Called by diagram_render before applying the per-document config: section.
    """
    if _baseline:
        for name, val in _baseline.items():
            setattr(config, name, val)
