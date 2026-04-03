"""Top-level engine dispatch and ingress for SignalFlow.

This package owns the runtime boundary between selectable engine paths.

Key components:
    - diagram_render: Engine-dispatched document render entry point
    - circuitDocumentResult_buildFromDocumentDict: Typed YAML ingress entry point
    - context_buildFromDocument: Materialize current
      new-engine pipeline state for debugging
"""
from __future__ import annotations

from signalflow.engine.input import (
    circuitDocumentResult_buildFromDocumentDict,
    circuitDocumentResult_buildFromSource,
    circuitDocumentSourceResult_buildFromDocumentDict,
)


def diagram_render(
    title,
    documentDict,
    *,
    engineName=None,
):
    """Render one document lazily through the selected engine.

    This wrapper keeps `signalflow.engine` import-safe for `signalflow.board`
    by deferring the `engine.render` import until call time.

    Args:
        title: Render title shown in the output block.
        documentDict: Parsed YAML document dictionary to render.
        engineName: Optional explicit engine selector.

    Returns:
        List of printable output lines from the selected engine renderer.
    """

    from signalflow.engine.render import diagram_render as _impl

    if engineName is None:
        return _impl(title, documentDict)
    return _impl(title, documentDict, engineName=engineName)


def context_buildFromDocument(documentDict):
    """Build the new-engine debug context lazily.

    This wrapper avoids importing `signalflow.engine.debug` during package
    initialization, which would otherwise create a cycle with
    `signalflow.board`.

    Args:
        documentDict: Parsed YAML document dictionary to inspect.

    Returns:
        Result containing the assembled `SignalFlowContext`.
    """

    from signalflow.engine.debug import (
        context_buildFromDocument as _impl,
    )

    return _impl(documentDict)


def repl_run(
    documentDict,
    sourcePath: str | None = None,
    loadSnippetPath: str | None = None,
) -> int:
    """Run the new-engine debug REPL lazily.

    Args:
        documentDict: Parsed YAML document dictionary to inspect.
        sourcePath: Optional filesystem/source label shown in the banner.
        loadSnippetPath: Optional snippet file loaded before interactive entry.

    Returns:
        Process-style exit code from the REPL session.
    """

    from signalflow.engine.debug import repl_run as _impl

    return _impl(
        documentDict=documentDict,
        sourcePath=sourcePath,
        loadSnippetPath=loadSnippetPath,
    )

__all__: list[str] = [
    "circuitDocumentResult_buildFromDocumentDict",
    "circuitDocumentResult_buildFromSource",
    "circuitDocumentSourceResult_buildFromDocumentDict",
    "diagram_render",
    "context_buildFromDocument",
    "repl_run",
]
