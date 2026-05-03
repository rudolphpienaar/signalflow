"""CLI entry point for SignalFlow.

This module parses CLI arguments, loads a YAML document, and dispatches to the
selected engine path.

Usage:
    signalflow <input.yaml>
    signalflow <input.yaml> --zones 1,2;1,3 --geometry
    signalflow <input.yaml> --zone 2 --wiring
    signalflow --engine legacy <input.yaml>
    signalflow --engine new examples/root-multi-child.yaml
    signalflow --engine new --repl --load-snippet \
        snippets/algebraic/hub_kernel_solver.py examples/hub.yaml
    signalflow --engine new --run-snippet \
        snippets/algebraic/hub_kernel_solver.py examples/hub.yaml
    signalflow --example
"""

from __future__ import annotations

import argparse
import atexit
import sys

import yaml

from signalflow.config.board_defaults import boardGeometryConfig_load
from signalflow.engine.inspect.repl import repl_run, snippet_run
from signalflow.engine.render import diagram_render
from signalflow.engine.world_render import (
    ModulePolicy,
    RoutingPolicy,
    WorldRenderOptions,
)
from signalflow.legacy.lib.global_config import globalConfig_load
from signalflow.models.diagnostics import DiagnosticLevel, diagnosticStack
from signalflow.models.engine import EngineName


def _diagnostics_dump() -> None:
    for diagnostic in diagnosticStack.diagnostics_getAll():
        prefix = (
            "error" if diagnostic.level is DiagnosticLevel.ERROR else "warning"
        )
        print(
            f"signalflow: {prefix} [{diagnostic.code}]: {diagnostic.message}",
            file=sys.stderr,
        )


atexit.register(_diagnostics_dump)

EXAMPLE_INPUT: dict = {
    "title": "show cohort -- signal flow",
    "tree": {
        "module": "CalypsoCore.ts",
        "func": "command_execute()",
        "signal": '"show cohort"',
        "calls": [
            {
                "module": "CalypsoCore.ts",
                "func": "commandInput_parse()",
                "signal": 'trimmed="show cohort"',
                "calls": [
                    {
                        "module": "WorkflowSession.ts",
                        "func": "resolveCommand()",
                        "signal": "resolution={stage:searchNode}",
                        "calls": [],
                    },
                    {
                        "module": "PluginHost.ts",
                        "func": "plugin_execute()",
                        "signal": "PluginContext",
                        "calls": [
                            {
                                "module": "plugins/search.ts",
                                "func": "cohort_show()",
                                "signal": None,
                                "calls": [],
                            }
                        ],
                    },
                ],
            }
        ],
    },
}


def arguments_parse(
    argv: list[str] | None = None,
) -> tuple[argparse.Namespace, list[str]]:
    """Parse CLI arguments for SignalFlow.

    Args:
        argv: Optional argument vector. When omitted, `sys.argv[1:]` is used.

    Returns:
        Tuple of (parsed CLI namespace, remaining unrecognised args). Remaining
        args are passed through to snippets via ``sys.argv`` so that snippets
        can define their own ``argparse`` arguments after a ``--`` separator.
    """

    argumentParser = argparse.ArgumentParser(
        description=(
            "Render SignalFlow documents with the selected engine path."
        ),
    )
    argumentParser.add_argument(
        "sourcePath",
        nargs="?",
        help="Input YAML path, or '-' to read from stdin.",
    )
    argumentParser.add_argument(
        "--engine",
        choices=[engineName.value for engineName in EngineName],
        default=EngineName.NEW.value,
        help="Engine path to use for rendering.",
    )
    argumentParser.add_argument(
        "--example",
        action="store_true",
        help="Render the built-in example document.",
    )
    zoneModeGroup = argumentParser.add_mutually_exclusive_group()
    zoneModeGroup.add_argument(
        "--zone",
        help=(
            "Render one world zone after full harmonization. "
            "Accepts row/column index like 2 or col,row like 1,2."
        ),
    )
    zoneModeGroup.add_argument(
        "--zones",
        help=(
            "Render selected sequential world zones after full harmonization. "
            "Use semicolon-separated specs like 1,2;1,3."
        ),
    )
    argumentParser.add_argument(
        "--geometry",
        action="store_true",
        help="Show relaxed board geometry for selected world zones.",
    )
    argumentParser.add_argument(
        "--wiring",
        action="store_true",
        help="Show composed world wiring for selected world zones.",
    )
    argumentParser.add_argument(
        "--depthbox",
        action="store_true",
        help=(
            "Show depth-layer boundary boxes. "
            "Ignored if --modulepolicy is also specified."
        ),
    )
    argumentParser.add_argument(
        "--modulepolicy",
        choices=["none", "column", "cross"],
        default=None,
        help=(
            "Module boundary box policy: none=no boxes, "
            "column=per (module, depth) box, "
            "cross=per module across all depths (default when omitted)."
        ),
    )
    argumentParser.add_argument(
        "--routing",
        choices=["manhattan", "none"],
        default="manhattan",
        help=(
            "Routing policy: manhattan=full centroid relaxation (default), "
            "none=skip centroid relaxation."
        ),
    )
    replModeGroup = argumentParser.add_mutually_exclusive_group()
    replModeGroup.add_argument(
        "--repl",
        action="store_true",
        help=(
            "Drop into a Python debug REPL for the current "
            "new-engine pipeline."
        ),
    )
    replModeGroup.add_argument(
        "--run-snippet",
        help=(
            "Snippet path to execute against the new-engine "
            "debug context and then exit."
        ),
    )
    argumentParser.add_argument(
        "--load-snippet",
        help=(
            "Snippet path to execute automatically after the "
            "new-engine REPL starts."
        ),
    )
    return argumentParser.parse_known_args(argv)


def zoneSpec_parse(zoneSpecText: str) -> tuple[int, int]:
    """Parse one CLI world-zone spec."""

    cleanedText: str = zoneSpecText.strip()
    if not cleanedText:
        raise ValueError("empty zone spec")
    if "," not in cleanedText:
        zoneIndex: int = int(cleanedText)
        return (1, zoneIndex)
    columnText, rowText = cleanedText.split(",", maxsplit=1)
    return (int(columnText), int(rowText))


def zoneSpecs_parse(
    zoneText: str | None,
    zonesText: str | None,
) -> tuple[tuple[int, int], ...] | None:
    """Parse CLI zone filter arguments."""

    if zoneText is not None:
        return (zoneSpec_parse(zoneText),)
    if zonesText is None:
        return None
    return tuple(
        zoneSpec_parse(specText)
        for specText in zonesText.split(";")
        if specText.strip()
    )


def document_load(
    sourcePath: str | None,
    useExample: bool,
) -> dict:
    """Load a YAML document from the requested source.

    Args:
        sourcePath: Filesystem path to the YAML file, or `-`
            for stdin.
        useExample: Whether to use the built-in example document instead.

    Returns:
        Parsed YAML document as a dictionary.

    Raises:
        ValueError: If neither an example nor a source path was provided.
    """

    if useExample:
        return EXAMPLE_INPUT
    if sourcePath is None:
        raise ValueError(
            "An input YAML path is required unless --example is used."
        )
    if sourcePath == "-":
        return yaml.safe_load(sys.stdin.read())
    with open(sourcePath, encoding="utf-8") as inputHandle:
        return yaml.safe_load(inputHandle.read())


def main(argv: list[str] | None = None) -> None:
    """Run the SignalFlow CLI.

    Args:
        argv: Optional argument vector. When omitted, `sys.argv[1:]` is used.
    """

    arguments, snippetArgs = arguments_parse(argv)
    engineName: EngineName = EngineName(arguments.engine)

    if engineName is EngineName.LEGACY:
        globalConfig_load()
    else:
        boardGeometryConfig_load()

    try:
        documentData: dict = document_load(
            arguments.sourcePath, arguments.example
        )
    except ValueError as error:
        print(f"signalflow: {error}", file=sys.stderr)
        sys.exit(1)

    try:
        zoneSpecs: tuple[tuple[int, int], ...] | None = zoneSpecs_parse(
            arguments.zone,
            arguments.zones,
        )
    except ValueError as error:
        print(f"signalflow: invalid zone argument: {error}", file=sys.stderr)
        sys.exit(1)

    if arguments.repl:
        if engineName is EngineName.LEGACY:
            print(
                (
                    "signalflow: --repl is currently "
                    "supported only for --engine new"
                ),
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(
            repl_run(
                documentDict=documentData,
                sourcePath=arguments.sourcePath,
                loadSnippetPath=arguments.load_snippet,
            )
        )

    if arguments.run_snippet is not None:
        if engineName is EngineName.LEGACY:
            print(
                (
                    "signalflow: --run-snippet is currently "
                    "supported only for --engine new"
                ),
                file=sys.stderr,
            )
            sys.exit(1)
        cleanSnippetArgs = (
            snippetArgs[1:]
            if snippetArgs and snippetArgs[0] == "--"
            else snippetArgs
        )
        sys.argv = [sys.argv[0]] + cleanSnippetArgs
        sys.exit(
            snippet_run(
                documentDict=documentData,
                snippetPath=arguments.run_snippet,
                sourcePath=arguments.sourcePath,
            )
        )

    title: str = documentData.get("title", "")
    rawModulePolicy: str | None = arguments.modulepolicy
    if rawModulePolicy is not None:
        modulePolicy = ModulePolicy(rawModulePolicy)
        depthBox = False
    else:
        modulePolicy = ModulePolicy.CROSS
        depthBox = arguments.depthbox
    worldRenderOptions = WorldRenderOptions(
        zoneSpecs=zoneSpecs,
        geometryShow=arguments.geometry,
        wiringShow=arguments.wiring or not arguments.geometry,
        modulePolicy=modulePolicy,
        depthBox=depthBox,
        routingPolicy=RoutingPolicy(arguments.routing),
    )
    outputLines: list[str] = diagram_render(
        title=title,
        treeDict=documentData,
        engineName=engineName,
        worldRenderOptions=worldRenderOptions,
    )
    line: str
    for line in outputLines:
        print(line)


if __name__ == "__main__":
    main()
