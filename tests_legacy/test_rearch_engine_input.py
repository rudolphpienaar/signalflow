"""Tests for typed YAML ingress into the new engine circuit model."""
from __future__ import annotations

from pathlib import Path

import yaml

from signalflow.engine import circuitDocumentResult_buildFromDocumentDict
from signalflow.models import ChipId, CircuitDocument, diagnosticStack, result_isOkCheck


def chipNames_getAll(circuitDocument: CircuitDocument) -> tuple[tuple[str, str], ...]:
    """Return canonical chip identities in stable declaration order."""

    return tuple(
        (chip.chipId.moduleName, chip.chipId.functionName)
        for chip in circuitDocument.circuitChipSet.chips
    )


def outgoingTargetsForChip_getAll(
    circuitDocument: CircuitDocument,
    moduleName: str,
    functionName: str,
) -> tuple[tuple[str, str], ...]:
    """Return ordered outgoing call targets for one canonical chip."""

    return tuple(
        (
            circuitCall.destinationChipRef.chipId.moduleName,
            circuitCall.destinationChipRef.chipId.functionName,
        )
        for circuitCall in circuitDocument.circuitCallSet.outgoingCallsForChip_get(
            chipId=ChipId(moduleName=moduleName, functionName=functionName)
        )
    )


class TestCircuitIngress:
    """Verification of the new typed circuit ingress layer."""

    def test_circuitDocumentResult_buildFromDocumentDict_parses_canonical_tree(
        self,
    ) -> None:
        """Canonical `tree` documents should parse into graph-shaped models."""

        diagnosticStack.stack_clear()

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "title": "pipeline",
                "tree": {
                    "module": "Pipeline.ts",
                    "func": "pipeline()",
                    "output_ports": [
                        {"signal": "rawData", "return": "parsed"},
                        {"signal": "parsed", "return": "validated"},
                    ],
                    "calls": [
                        {
                            "module": "Pipeline.ts",
                            "func": "parse()",
                            "input_ports": [
                                {"signal": "rawData", "return": "parsed"}
                            ],
                            "calls": [],
                        },
                        {
                            "module": "Pipeline.ts",
                            "func": "validate()",
                            "input_ports": [
                                {"signal": "parsed", "return": "validated"}
                            ],
                            "calls": [],
                        },
                    ],
                },
            }
        )

        assert result_isOkCheck(circuitDocumentResult)
        circuitDocument: CircuitDocument = circuitDocumentResult.value
        assert circuitDocument.callingDepth_calculate() == 2
        assert circuitDocument.rootChipRef.chipId.moduleName == "Pipeline.ts"
        assert circuitDocument.rootChipRef.chipId.functionName == "pipeline()"
        assert chipNames_getAll(circuitDocument) == (
            ("Pipeline.ts", "pipeline()"),
            ("Pipeline.ts", "parse()"),
            ("Pipeline.ts", "validate()"),
        )
        assert outgoingTargetsForChip_getAll(
            circuitDocument,
            moduleName="Pipeline.ts",
            functionName="pipeline()",
        ) == (("Pipeline.ts", "parse()"), ("Pipeline.ts", "validate()"))

        rootChipResult = circuitDocument.rootChipResult_get()
        assert result_isOkCheck(rootChipResult)
        # output_ports → all east terminals; duplicate name "parsed" (appears as
        # both return of port[0] and signal of port[1]) deduplicates to one entry.
        assert {
            (terminal.terminalName, terminal.terminalSide.value)
            for terminal in rootChipResult.value.chipTerminalSet.terminals
        } == {
            ("rawData", "east"),
            ("parsed", "east"),
            ("validated", "east"),
        }

    def test_circuitDocumentResult_buildFromDocumentDict_normalizes_port_shorthand(
        self,
    ) -> None:
        """Backward-compatible port shorthand should normalize into one port record."""

        diagnosticStack.stack_clear()

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "module": "App.ts",
                "func": "main()",
                "output_signal": "args",
                "output_return": "result",
                "calls": [
                    {
                        "module": "App.ts",
                        "func": "run()",
                        "input_signal": "args",
                        "input_return": "result",
                        "calls": [],
                    }
                ],
            }
        )

        assert result_isOkCheck(circuitDocumentResult)
        circuitDocument = circuitDocumentResult.value
        rootChipResult = circuitDocument.rootChipResult_get()
        assert result_isOkCheck(rootChipResult)
        assert len(rootChipResult.value.outputPortDeclarationSet.portDeclarations) == 1
        childChipResult = circuitDocument.circuitChipSet.chipResult_get(
            chipId=ChipId(moduleName="App.ts", functionName="run()")
        )
        assert result_isOkCheck(childChipResult)
        assert len(childChipResult.value.inputPortDeclarationSet.portDeclarations) == 1

    def test_circuitDocumentResult_buildFromDocumentDict_canonicalizes_reused_nodes(
        self,
    ) -> None:
        """Repeated short references should target one canonical chip declaration."""

        examplePath: Path = (
            Path(__file__).resolve().parents[1] / "examples" / "explicit-hub.yaml"
        )
        with examplePath.open(encoding="utf-8") as inputHandle:
            documentDict = yaml.safe_load(inputHandle.read())

        diagnosticStack.stack_clear()
        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(circuitDocumentResult)
        circuitDocument = circuitDocumentResult.value
        assert len(circuitDocument.circuitChipSet.chips) == 12
        assert chipNames_getAll(circuitDocument) == (
            ("App.ts", "main()"),
            ("Proxy.ts", "p1()"),
            ("Hub.ts", "process()"),
            ("Sink.ts", "c1()"),
            ("Sink.ts", "c2()"),
            ("Sink.ts", "c3()"),
            ("Sink.ts", "c4()"),
            ("Sink.ts", "c5()"),
            ("Proxy.ts", "p2()"),
            ("Proxy.ts", "p3()"),
            ("Proxy.ts", "p4()"),
            ("Proxy.ts", "p5()"),
        )
        assert outgoingTargetsForChip_getAll(
            circuitDocument,
            moduleName="App.ts",
            functionName="main()",
        ) == (
            ("Proxy.ts", "p1()"),
            ("Proxy.ts", "p2()"),
            ("Proxy.ts", "p3()"),
            ("Proxy.ts", "p4()"),
            ("Proxy.ts", "p5()"),
        )
        assert outgoingTargetsForChip_getAll(
            circuitDocument,
            moduleName="Proxy.ts",
            functionName="p2()",
        ) == (("Hub.ts", "process()"),)
        processChipResult = circuitDocument.circuitChipSet.chipResult_get(
            chipId=ChipId(moduleName="Hub.ts", functionName="process()")
        )
        assert result_isOkCheck(processChipResult)
        assert processChipResult.value.internalRoutingDeclared is True
        assert processChipResult.value.chipIo.chipIoInput.explicit is True
        assert len(processChipResult.value.internalWiringDirectiveSet.directives) > 1
        assert outgoingTargetsForChip_getAll(
            circuitDocument,
            moduleName="Hub.ts",
            functionName="process()",
        ) == (
            ("Sink.ts", "c1()"),
            ("Sink.ts", "c2()"),
            ("Sink.ts", "c3()"),
            ("Sink.ts", "c4()"),
            ("Sink.ts", "c5()"),
        )

    def test_circuitDocumentResult_buildFromDocumentDict_models_self_reference(
        self,
    ) -> None:
        """A self call should become one canonical chip with a self edge."""

        diagnosticStack.stack_clear()

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "Hub.ts",
                    "func": "process()",
                    "input_ports": [{"signal": "tick", "return": "tock"}],
                    "output_ports": [{"signal": "tick", "return": "tock"}],
                    "calls": [{"module": "Hub.ts", "func": "process()"}],
                }
            }
        )

        assert result_isOkCheck(circuitDocumentResult)
        circuitDocument = circuitDocumentResult.value
        assert len(circuitDocument.circuitChipSet.chips) == 1
        assert circuitDocument.callingDepth_calculate() == 1
        assert outgoingTargetsForChip_getAll(
            circuitDocument,
            moduleName="Hub.ts",
            functionName="process()",
        ) == (("Hub.ts", "process()"),)

    def test_circuitDocumentResult_buildFromDocumentDict_rejects_mixed_port_syntax(
        self,
    ) -> None:
        """Port list syntax and shorthand should not mix on one node."""

        diagnosticStack.stack_clear()

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "module": "App.ts",
                "func": "main()",
                "output_signal": "args",
                "output_ports": [{"signal": "args"}],
                "calls": [],
            }
        )

        assert not result_isOkCheck(circuitDocumentResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "engine.input.node.mixed_port_syntax"

    def test_circuitDocumentResult_buildFromDocumentDict_rejects_conflicting_reuse(
        self,
    ) -> None:
        """Repeated node declarations may not redefine previously declared metadata."""

        diagnosticStack.stack_clear()

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "main()",
                    "calls": [
                        {
                            "module": "Hub.ts",
                            "func": "process()",
                            "input_ports": [{"signal": "a"}],
                            "calls": [],
                        },
                        {
                            "module": "Hub.ts",
                            "func": "process()",
                            "input_ports": [{"signal": "b"}],
                            "calls": [],
                        },
                    ],
                }
            }
        )

        assert not result_isOkCheck(circuitDocumentResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "engine.input.node.conflicting_reuse_declaration"

    def test_rejects_backedge_source_without_explicit_output_ports(
        self,
    ) -> None:
        """Backedge sources may not rely on derived output declarations."""

        diagnosticStack.stack_clear()

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "caller()",
                    "input_ports": [{"signal": "sig", "return": "ret"}],
                    "output_ports": [{"signal": "sig", "return": "ret"}],
                    "calls": [
                        {
                            "module": "App.ts",
                            "func": "callee()",
                            "input_ports": [{"signal": "sig", "return": "ret"}],
                            "calls": [{"module": "App.ts", "func": "caller()"}],
                        }
                    ],
                }
            }
        )

        assert not result_isOkCheck(circuitDocumentResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "engine.input.node.missing_explicit_output_ports"
        assert diagnostics[0].context == ("App.ts", "callee()")

    def test_rejects_backedge_target_without_explicit_input_ports(
        self,
    ) -> None:
        """Root chips lose the no-input exemption once a backedge targets them."""

        diagnosticStack.stack_clear()

        circuitDocumentResult = circuitDocumentResult_buildFromDocumentDict(
            {
                "tree": {
                    "module": "App.ts",
                    "func": "caller()",
                    "output_ports": [{"signal": "sig", "return": "ret"}],
                    "calls": [
                        {
                            "module": "App.ts",
                            "func": "callee()",
                            "input_ports": [{"signal": "sig", "return": "ret"}],
                            "output_ports": [{"signal": "sig", "return": "ret"}],
                            "calls": [{"module": "App.ts", "func": "caller()"}],
                        }
                    ],
                }
            }
        )

        assert not result_isOkCheck(circuitDocumentResult)
        diagnostics = diagnosticStack.diagnosticSet_build().diagnostics_getAll()
        assert diagnostics[0].code == "engine.input.node.missing_explicit_input_ports"
        assert diagnostics[0].context == ("App.ts", "caller()")
