"""New-era board geometry configuration singleton.

Single importable source of startup defaults for board geometry spans.
Import `boardGeometryConfig` to read current values; call
`boardGeometryConfig_load()` once at CLI startup to apply user and project
overrides.

Priority chain (lowest → highest):

    ``BoardGeometryConfig`` dataclass defaults
    < ``~/.config/signalflow/config.yaml``  (XDG user preferences)
    < ``.signalflow.yaml``                  (project config, walks to git root)

YAML shape::

    world:
      geometry:
        intra:
          wTerminalSpan: 1
          wFanSpan: 4
          eFanSpan: 4
          eTerminalSpan: 1
        extra:
          wLongSpan: 2
          wFanSpan: 4
          nSpan: 2
          sSpan: 2
          eLongSpan: 2
          eFanSpan: 4

Only non-zero policy fields are settable. Solver-derived fields (intra
``wLongSpan``, ``eLongSpan``, ``nSpan``, ``sSpan``) are not exposed here —
those are owned by the placement solver and ``ZoneSymbolicInvariants``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class BoardGeometryConfig:
    """Mutable board geometry defaults populated from startup config files.

    Intra fields cover only the non-zero policy floors (terminal + fan).
    Solver-derived intra fields (long spans, lat spans) are not represented
    here — they are owned by the placement solver and ZoneSymbolicInvariants.
    Extra fields cover all non-terminal policy spans.

    Attributes:
        intraWTerminalSpan: West chip terminal column width floor (intra ring).
        intraWFanSpan: West fan in/out column width floor (intra ring).
        intraEFanSpan: East fan in/out column width floor (intra ring).
        intraETerminalSpan: East chip terminal column width floor (intra ring).
        extraWLongSpan: West longitude column width (extra ring).
        extraWFanSpan: West fan in/out column width (extra ring).
        extraNSpan: North band row height (extra ring).
        extraSSpan: South band row height (extra ring).
        extraELongSpan: East longitude column width (extra ring).
        extraEFanSpan: East fan in/out column width (extra ring).
    """

    # intra ring — non-zero policy floors only
    intraWTerminalSpan: int = 1
    intraWFanSpan: int = 4
    intraEFanSpan: int = 4
    intraETerminalSpan: int = 1

    # extra ring — all non-terminal policy spans
    extraWLongSpan: int = 2
    extraWFanSpan: int = 4
    extraNSpan: int = 2
    extraSSpan: int = 2
    extraELongSpan: int = 2
    extraEFanSpan: int = 4

    # module boundary box padding (world cells)
    moduleBoxPadding: int = 2

    def geometry_update(self, data: dict[str, object]) -> None:
        """Apply a parsed ``world.geometry`` config dict.

        Ignores unknown keys silently. Only non-zero policy fields are
        accepted; sentinel-zero solver-derived fields are not settable.

        Args:
            data: Parsed ``world.geometry`` dictionary from a config YAML file.
        """
        intraData = data.get("intra")
        if isinstance(intraData, dict):
            if "wTerminalSpan" in intraData:
                self.intraWTerminalSpan = int(intraData["wTerminalSpan"])  # type: ignore[arg-type]
            if "wFanSpan" in intraData:
                self.intraWFanSpan = int(intraData["wFanSpan"])  # type: ignore[arg-type]
            if "eFanSpan" in intraData:
                self.intraEFanSpan = int(intraData["eFanSpan"])  # type: ignore[arg-type]
            if "eTerminalSpan" in intraData:
                self.intraETerminalSpan = int(intraData["eTerminalSpan"])  # type: ignore[arg-type]

        extraData = data.get("extra")
        if isinstance(extraData, dict):
            if "wLongSpan" in extraData:
                self.extraWLongSpan = int(extraData["wLongSpan"])  # type: ignore[arg-type]
            if "wFanSpan" in extraData:
                self.extraWFanSpan = int(extraData["wFanSpan"])  # type: ignore[arg-type]
            if "nSpan" in extraData:
                self.extraNSpan = int(extraData["nSpan"])  # type: ignore[arg-type]
            if "sSpan" in extraData:
                self.extraSSpan = int(extraData["sSpan"])  # type: ignore[arg-type]
            if "eLongSpan" in extraData:
                self.extraELongSpan = int(extraData["eLongSpan"])  # type: ignore[arg-type]
            if "eFanSpan" in extraData:
                self.extraEFanSpan = int(extraData["eFanSpan"])  # type: ignore[arg-type]

        if "moduleBoxPadding" in data:
            self.moduleBoxPadding = int(data["moduleBoxPadding"])  # type: ignore[arg-type]


boardGeometryConfig: BoardGeometryConfig = BoardGeometryConfig()
"""Process-level singleton.

Mutated once at startup by `boardGeometryConfig_load()`.
"""


def _userConfigPath_get() -> Path | None:
    """Return the XDG user config path if it exists.

    Returns:
        Path to ``~/.config/signalflow/config.yaml`` (or ``$XDG_CONFIG_HOME``
        equivalent) when the file exists, otherwise ``None``.
    """
    xdg: str | None = os.environ.get("XDG_CONFIG_HOME")
    base: Path = Path(xdg) if xdg else Path.home() / ".config"
    candidate: Path = base / "signalflow" / "config.yaml"
    return candidate if candidate.is_file() else None


def _projectConfigPath_get() -> Path | None:
    """Return the nearest ``.signalflow.yaml``, walking up to the git root.

    Starts from the current working directory and walks toward the filesystem
    root, stopping after the directory that contains ``.git`` so the search
    never crosses a repository boundary.

    Returns:
        Path to the nearest ``.signalflow.yaml`` when found,
        otherwise ``None``.
    """
    current: Path = Path.cwd()
    while True:
        candidate: Path = current / ".signalflow.yaml"
        if candidate.is_file():
            return candidate
        parent: Path = current.parent
        if parent == current:
            break
        if (current / ".git").exists():
            break
        current = parent
    return None


def boardGeometryConfig_load() -> None:
    """Load user and project geometry configs into the singleton.

    Call once at CLI startup, before any ``BoardGeometrySpec()`` is
    constructed. Applies both config files in priority order (user first,
    project second) so project settings win over user preferences.
    Warns to stderr on parse errors but never raises.
    """
    for path in (_userConfigPath_get(), _projectConfigPath_get()):
        if path is None:
            continue
        try:
            with open(path) as fh:
                data: object = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                continue
            geometry: object = data.get("world", {})  # type: ignore[union-attr]
            if isinstance(geometry, dict):
                geometry = geometry.get("geometry")
            if isinstance(geometry, dict):
                boardGeometryConfig.geometry_update(geometry)
        except Exception as exc:
            print(
                (
                    "signalflow: warning: could not load "
                    f"geometry config {path}: {exc}"
                ),
                file=sys.stderr,
            )
