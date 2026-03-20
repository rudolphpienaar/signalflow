"""Top-level engine dispatch and ingress for SignalFlow.

This package owns the runtime boundary between selectable engine paths.

Key components:
    - diagram_render: Engine-dispatched document render entry point
    - circuitDocumentResult_buildFromDocumentDict: Typed YAML ingress entry point
    - newEngineDebugContextResult_buildFromDocumentDict: Materialize current
      new-engine pipeline state for debugging
"""
from __future__ import annotations

from signalflow.engine.debug import (
    newEngineDebugContextResult_buildFromDocumentDict,
    newEngineDebugRepl_run,
)
from signalflow.engine.input import (
    circuitDocumentResult_buildFromDocumentDict,
    circuitDocumentResult_buildFromSource,
    circuitDocumentSourceResult_buildFromDocumentDict,
)
from signalflow.engine.render import diagram_render

__all__: list[str] = [
    "circuitDocumentResult_buildFromDocumentDict",
    "circuitDocumentResult_buildFromSource",
    "circuitDocumentSourceResult_buildFromDocumentDict",
    "diagram_render",
    "newEngineDebugContextResult_buildFromDocumentDict",
    "newEngineDebugRepl_run",
]
