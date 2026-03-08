"""Tests for global config loading (user + project level)."""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from signalflow.config import config
from signalflow.lib import global_config as gc


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config_and_baseline():
    """Restore config singleton and module-level baseline after each test."""
    saved = {f.name: getattr(config, f.name) for f in fields(config)}
    saved_baseline = dict(gc._baseline)
    yield
    for name, val in saved.items():
        setattr(config, name, val)
    gc._baseline.clear()
    gc._baseline.update(saved_baseline)


# ── _user_config_path ─────────────────────────────────────────────────────────

class TestUserConfigPath:
    def test_returns_none_when_file_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert gc._user_config_path() is None

    def test_returns_path_when_file_exists(self, tmp_path, monkeypatch):
        cfg_dir = tmp_path / "signalflow"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "config.yaml"
        cfg_file.write_text("channelWidth: 50\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert gc._user_config_path() == cfg_file

    def test_uses_xdg_env_var(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom_xdg"
        (custom / "signalflow").mkdir(parents=True)
        (custom / "signalflow" / "config.yaml").write_text("")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(custom))
        assert gc._user_config_path() is not None


# ── _project_config_path ──────────────────────────────────────────────────────

class TestProjectConfigPath:
    def test_finds_config_in_cwd(self, tmp_path, monkeypatch):
        cfg = tmp_path / ".signalflow.yaml"
        cfg.write_text("channelWidth: 40\n")
        monkeypatch.chdir(tmp_path)
        assert gc._project_config_path() == cfg

    def test_finds_config_in_parent(self, tmp_path, monkeypatch):
        cfg = tmp_path / ".signalflow.yaml"
        cfg.write_text("channelWidth: 40\n")
        subdir = tmp_path / "sub"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        assert gc._project_config_path() == cfg

    def test_stops_at_git_root(self, tmp_path, monkeypatch):
        """Config above the git root must not be found."""
        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 99\n")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        subdir = repo / "sub"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        # No .signalflow.yaml inside repo — should return None, not find the one above
        assert gc._project_config_path() is None

    def test_finds_config_at_git_root(self, tmp_path, monkeypatch):
        """Config at the git root itself must be found."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        cfg = repo / ".signalflow.yaml"
        cfg.write_text("channelWidth: 35\n")
        subdir = repo / "sub"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        assert gc._project_config_path() == cfg

    def test_returns_none_when_absent(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        assert gc._project_config_path() is None


# ── global_config_load ────────────────────────────────────────────────────────

class TestGlobalConfigLoad:
    def test_applies_user_config(self, tmp_path, monkeypatch):
        cfg_dir = tmp_path / "signalflow"
        cfg_dir.mkdir()
        (cfg_dir / "config.yaml").write_text("channelWidth: 77\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()
        assert config.channelWidth == 77

    def test_applies_project_config(self, tmp_path, monkeypatch):
        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 55\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()
        assert config.channelWidth == 55

    def test_project_overrides_user(self, tmp_path, monkeypatch):
        """Project config has higher priority than user config."""
        cfg_dir = tmp_path / "signalflow"
        cfg_dir.mkdir()
        (cfg_dir / "config.yaml").write_text("channelWidth: 40\n")
        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 60\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()
        assert config.channelWidth == 60

    def test_captures_baseline_after_load(self, tmp_path, monkeypatch):
        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 45\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()
        assert gc._baseline.get("channelWidth") == 45

    def test_no_files_leaves_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        default_cw = config.channelWidth
        gc.global_config_load()
        assert config.channelWidth == default_cw

    def test_invalid_yaml_warns_and_continues(self, tmp_path, monkeypatch, capsys):
        cfg_dir = tmp_path / "signalflow"
        cfg_dir.mkdir()
        (cfg_dir / "config.yaml").write_text("channelWidth: 50\n")
        (tmp_path / ".signalflow.yaml").write_text(": invalid: yaml: [\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()  # must not raise
        assert config.channelWidth == 50  # user config still applied
        assert "warning" in capsys.readouterr().err.lower()


# ── global_config_reset ───────────────────────────────────────────────────────

class TestGlobalConfigReset:
    def test_noop_when_baseline_empty(self):
        """No-op when global_config_load() was never called."""
        assert gc._baseline == {}
        config.channelWidth = 999
        gc.global_config_reset()
        assert config.channelWidth == 999  # unchanged

    def test_restores_baseline(self, tmp_path, monkeypatch):
        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 33\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()
        assert config.channelWidth == 33
        config.channelWidth = 999   # simulate per-doc override
        gc.global_config_reset()
        assert config.channelWidth == 33  # back to baseline

    def test_per_doc_config_applies_after_reset(self, tmp_path, monkeypatch):
        """diagram_render pattern: reset → per-doc override."""
        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 33\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()
        gc.global_config_reset()
        config.config_update({"channelWidth": 88})  # per-doc
        assert config.channelWidth == 88


# ── end-to-end: diagram_render respects global config ─────────────────────────

class TestDiagramRenderUsesGlobalConfig:
    def test_global_config_applied_before_render(self, tmp_path, monkeypatch):
        """Global anchorLabelMaxWidth is active without per-doc config: section."""
        (tmp_path / ".signalflow.yaml").write_text(
            "internal_wiring:\n  anchorLabelWidth: 3\n"
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()
        assert config.anchorLabelMaxWidth == 3

    def test_per_doc_overrides_global(self, tmp_path, monkeypatch):
        """Per-document config: section wins over global config."""
        from signalflow.engine.render import diagram_render

        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 30\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()

        doc = {
            "title": "test",
            "config": {"channelWidth": 99},
            "tree": {"module": "M", "func": "f()", "calls": []},
        }
        diagram_render("test", doc)
        assert config.channelWidth == 99

    def test_reset_between_renders(self, tmp_path, monkeypatch):
        """Second render must not see first render's per-doc config."""
        from signalflow.engine.render import diagram_render

        (tmp_path / ".signalflow.yaml").write_text("channelWidth: 25\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no_xdg"))
        monkeypatch.chdir(tmp_path)
        gc.global_config_load()

        tree = {"module": "M", "func": "f()", "calls": []}
        diagram_render("r1", {"title": "r1", "config": {"channelWidth": 80}, "tree": tree})
        assert config.channelWidth == 80

        diagram_render("r2", {"title": "r2", "tree": tree})
        # No per-doc config — must reset to global baseline (25)
        assert config.channelWidth == 25
