"""Tests for the top-level SignalFlow app-config boundary.

These tests verify that `src/signalflow/config/config.py` is now the public
app-config ingress and that it wraps the routing-world config into one unified
top-level config model.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.config import (
    SignalFlowConfig,
    signalFlowConfigResult_buildFromDocumentDict,
)
from signalflow.models import Result, diagnosticStack, result_isOkCheck


def configFixtureDocument_build(fixtureName: str) -> dict[str, object]:
    """Load one config-only YAML fixture by file name.

    Args:
        fixtureName: File name beneath `examples/configs/`.

    Returns:
        Parsed YAML document for the requested fixture.
    """

    fixturePath: Path = (
        Path(__file__).parent.parent / "examples" / "configs" / fixtureName
    )
    with fixturePath.open(encoding="utf-8") as inputHandle:
        loadedDocument = yaml.safe_load(inputHandle.read())
    assert isinstance(loadedDocument, dict)
    return loadedDocument


class TestSignalFlowConfig:
    """Verification of the top-level app-config boundary."""

    def test_signalFlowConfigResult_buildFromDocumentDict_wraps_explicit_world(
        self,
    ) -> None:
        """Explicit world config should produce a validated top-level config."""

        diagnosticStack.stack_clear()
        configResult: Result[SignalFlowConfig] = (
            signalFlowConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-rectangular-4x4.yaml")
            )
        )

        assert result_isOkCheck(configResult)
        config: SignalFlowConfig = configResult.value
        assert config.routingZoneGridConfig.routingZoneCount_calculate() == 16
        assert (
            config.routingZoneGridConfig.routingZoneInterconnectCount_calculate()
            == 24
        )

    def test_signalFlowConfigResult_buildFromDocumentDict_derives_implicit_world(
        self,
    ) -> None:
        """Implicit world grid should derive cleanly through the app-config layer."""

        diagnosticStack.stack_clear()
        configResult: Result[SignalFlowConfig] = (
            signalFlowConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-implicit-horizontal.yaml"),
                callingDepth=5,
            )
        )

        assert result_isOkCheck(configResult)
        config: SignalFlowConfig = configResult.value
        assert config.routingZoneGridConfig.routingZoneGridDimensions.columnCount == 4
        assert config.routingZoneGridConfig.routingZoneGridDimensions.rowCount == 1

    def test_signalFlowConfigResult_requires_calling_depth_for_implicit_world(
        self,
    ) -> None:
        """Implicit world grid should fail explicitly without calling depth."""

        diagnosticStack.stack_clear()
        configResult: Result[SignalFlowConfig] = (
            signalFlowConfigResult_buildFromDocumentDict(
                configFixtureDocument_build("world-implicit-horizontal.yaml")
            )
        )

        assert not result_isOkCheck(configResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "config.missing_calling_depth"
