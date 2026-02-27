"""CLI entry point: python -m signalflow <input.yaml>"""

import sys

import yaml

from signalflow.engine.render import diagram_render

EXAMPLE_INPUT = {
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
                        "calls": []
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
                                "calls": []
                            }
                        ]
                    }
                ]
            }
        ]
    }
}


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(
            'usage: signalflow <input.yaml>  |  signalflow -  |  signalflow --example',
            file=sys.stderr,
        )
        sys.exit(1)

    src = sys.argv[1]

    if src == '--example':
        data = EXAMPLE_INPUT
    elif src == '-':
        data = yaml.safe_load(sys.stdin.read())
    else:
        with open(src) as fh:
            data = yaml.safe_load(fh.read())

    title     = data.get('title', '')
    tree_dict = data.get('tree', {})

    for line in diagram_render(title, tree_dict):
        print(line)


if __name__ == '__main__':
    main()
