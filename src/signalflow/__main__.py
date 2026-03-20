"""CLI entry point for SignalFlow.

This module parses CLI arguments, loads a YAML document, and dispatches to the
selected engine path.

Usage:
    signalflow <input.yaml>
    signalflow --engine legacy <input.yaml>
    signalflow --engine new examples/root-multi-child.yaml
    signalflow --example
"""
from __future__ import annotations

import argparse
import sys

import yaml

from signalflow.engine.debug import newEngineDebugRepl_run
from signalflow.engine.render import diagram_render
from signalflow.legacy.lib.global_config import globalConfig_load
from signalflow.models.engine import EngineName

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


def arguments_parse(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for SignalFlow.

    Args:
        argv: Optional argument vector. When omitted, `sys.argv[1:]` is used.

    Returns:
        Parsed CLI namespace.
    """

    argumentParser = argparse.ArgumentParser(
        description="Render SignalFlow documents with the selected engine path.",
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
    argumentParser.add_argument(
        "--repl",
        action="store_true",
        help="Drop into a Python debug REPL for the current new-engine pipeline.",
    )
    return argumentParser.parse_args(argv)


def document_load(
    sourcePath: str | None,
    useExample: bool,
) -> dict:
    """Load a YAML document from the requested source.

    Args:
        sourcePath: Filesystem path to the YAML file, or `-` for stdin.
        useExample: Whether to use the built-in example document instead.

    Returns:
        Parsed YAML document as a dictionary.

    Raises:
        ValueError: If neither an example nor a source path was provided.
    """

    if useExample:
        return EXAMPLE_INPUT
    if sourcePath is None:
        raise ValueError("An input YAML path is required unless --example is used.")
    if sourcePath == "-":
        return yaml.safe_load(sys.stdin.read())
    with open(sourcePath, encoding="utf-8") as inputHandle:
        return yaml.safe_load(inputHandle.read())


def main(argv: list[str] | None = None) -> None:
    """Run the SignalFlow CLI.

    Args:
        argv: Optional argument vector. When omitted, `sys.argv[1:]` is used.
    """

    arguments = arguments_parse(argv)
    engineName: EngineName = EngineName(arguments.engine)

    if engineName is EngineName.LEGACY:
        globalConfig_load()

    try:
        documentData: dict = document_load(arguments.sourcePath, arguments.example)
    except ValueError as error:
        print(f"signalflow: {error}", file=sys.stderr)
        sys.exit(1)

    if arguments.repl:
        if engineName is EngineName.LEGACY:
            print(
                "signalflow: --repl is currently supported only for --engine new",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(
            newEngineDebugRepl_run(
                documentDict=documentData,
                sourcePath=arguments.sourcePath,
            )
        )

    title: str = documentData.get("title", "")
    outputLines: list[str] = diagram_render(
        title=title,
        treeDict=documentData,
        engineName=engineName,
    )
    line: str
    for line in outputLines:
        print(line)


if __name__ == "__main__":
    main()
