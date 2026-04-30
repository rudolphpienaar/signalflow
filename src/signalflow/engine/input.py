"""Typed YAML ingress for the new SignalFlow engine.

This module owns the boundary from raw YAML document dictionaries into the new
engine's typed source and validated circuit models. It preserves the current
document surface while removing raw dicts from the rest of the engine.
"""

from __future__ import annotations

from signalflow.models.chip import (
    ChipId,
    ChipInternalWiringDirective,
    ChipInternalWiringDirectiveSet,
    ChipIo,
    ChipIoInput,
    ChipIoInternalWiring,
    ChipPortDeclaration,
    ChipPortDeclarationSet,
    ChipRef,
    ChipTerminal,
    ChipTerminalSet,
    ChipTerminalSide,
    chipInternalWiringDirectiveResult_build,
    chipInternalWiringDirectiveSetResult_build,
    chipPortDeclarationResult_build,
    chipPortDeclarationSetResult_build,
    chipResult_build,
    chipTerminalSetResult_build,
)
from signalflow.models.circuit import (
    CircuitCall,
    CircuitCallSet,
    CircuitChipSet,
    CircuitDocument,
    circuitCallSetResult_build,
    circuitChipSetResult_build,
    circuitDocumentResult_build,
)
from signalflow.models.circuit_source import (
    CircuitChildCallSource,
    CircuitChipIoInputSource,
    CircuitChipIoInternalWiringSource,
    CircuitChipIoSource,
    CircuitDocumentSource,
    CircuitNodeSource,
    CircuitNodeSourceChildren,
    CircuitPortDeclarationSource,
    CircuitPortDeclarationSourceSet,
    CircuitWiringDirectiveSource,
    CircuitWiringDirectiveSourceSet,
)
from signalflow.models.diagnostics import DiagnosticPhase, diagnosticStack
from signalflow.models.result import (
    Result,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)

_CONFLICTING_REUSE_MESSAGE = (
    "Repeated node declarations may not redefine existing metadata"
)


def circuitDocumentSourceResult_buildFromDocumentDict(
    documentDict: dict[str, object],
) -> Result[CircuitDocumentSource]:
    """Build typed source document from one raw YAML document dictionary."""

    titleObject: object = documentDict.get("title", "")
    if not isinstance(titleObject, str):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.document.invalid_title",
            message="SignalFlow document title must be a string",
            context=("title",),
        )
        return resultErr_build()

    rootNodeDictResult: Result[dict[str, object]] = _rootNodeDictResult_build(
        documentDict
    )
    if not result_isOkCheck(rootNodeDictResult):
        return resultErr_build()

    rootNodeSourceResult: Result[CircuitNodeSource] = (
        _circuitNodeSourceResult_buildFromNodeDict(
            rootNodeDictResult.value,
            nodeContext="tree",
        )
    )
    if not result_isOkCheck(rootNodeSourceResult):
        return resultErr_build()

    return resultOk_build(
        CircuitDocumentSource(
            title=titleObject,
            rootNodeSource=rootNodeSourceResult.value,
        )
    )


def circuitDocumentResult_buildFromSource(
    circuitDocumentSource: CircuitDocumentSource,
) -> Result[CircuitDocument]:
    """Build validated circuit document from typed source document."""

    if circuitDocumentSource.rootNodeSource is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.document.missing_root_node",
            message="CircuitDocumentSource must contain a root node source",
        )
        return resultErr_build()

    declarationRegistryMutable: dict[tuple[str, str], CircuitNodeSource] = {}
    if not _nodeDeclarations_collectCheck(
        circuitNodeSource=circuitDocumentSource.rootNodeSource,
        declarationRegistryMutable=declarationRegistryMutable,
    ):
        return resultErr_build()

    circuitChipSetResult: Result[CircuitChipSet] = (
        _circuitChipSetResult_buildFromDeclarationRegistry(
            declarationRegistryMutable=declarationRegistryMutable
        )
    )
    if not result_isOkCheck(circuitChipSetResult):
        return resultErr_build()
    circuitCallSetResult: Result[CircuitCallSet] = (
        _circuitCallSetResult_buildFromDeclarationRegistry(
            declarationRegistryMutable=declarationRegistryMutable
        )
    )
    if not result_isOkCheck(circuitCallSetResult):
        return resultErr_build()
    if not _chipPortContracts_validateCheck(
        declarationRegistryMutable=declarationRegistryMutable,
        circuitCallSet=circuitCallSetResult.value,
        rootNodeSource=circuitDocumentSource.rootNodeSource,
    ):
        return resultErr_build()

    return circuitDocumentResult_build(
        title=circuitDocumentSource.title,
        rootChipRef=ChipRef(
            chipId=ChipId(
                moduleName=circuitDocumentSource.rootNodeSource.moduleName,
                functionName=circuitDocumentSource.rootNodeSource.functionName,
            )
        ),
        circuitChipSet=circuitChipSetResult.value,
        circuitCallSet=circuitCallSetResult.value,
    )


def circuitDocumentResult_buildFromDocumentDict(
    documentDict: dict[str, object],
) -> Result[CircuitDocument]:
    """Build a validated circuit document from one raw YAML dictionary."""

    circuitDocumentSourceResult: Result[CircuitDocumentSource] = (
        circuitDocumentSourceResult_buildFromDocumentDict(documentDict)
    )
    if not result_isOkCheck(circuitDocumentSourceResult):
        return resultErr_build()
    return circuitDocumentResult_buildFromSource(
        circuitDocumentSourceResult.value
    )


def _rootNodeDictResult_build(
    documentDict: dict[str, object],
) -> Result[dict[str, object]]:
    """Get the root node mapping from one raw document dictionary."""

    treeObject: object | None = documentDict.get("tree")
    if treeObject is not None:
        if not isinstance(treeObject, dict):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.document.invalid_tree",
                message="SignalFlow document tree must be a mapping",
                context=("tree",),
            )
            return resultErr_build()
        return resultOk_build(treeObject)

    if "module" in documentDict and "func" in documentDict:
        return resultOk_build(documentDict)

    diagnosticStack.error_push(
        phase=DiagnosticPhase.VALIDATION,
        code="engine.input.document.missing_tree",
        message=(
            "SignalFlow document must contain a root tree or top-level node"
        ),
    )
    return resultErr_build()


def _circuitNodeSourceResult_buildFromNodeDict(
    nodeDict: dict[str, object],
    nodeContext: str,
) -> Result[CircuitNodeSource]:
    """Build one typed node source from a raw node dictionary.

    Accepts both the canonical new-engine port syntax (``input_ports``,
    ``output_ports``, ``input_signal``, ``output_signal``) and the legacy
    bare ``signal``/``return`` shorthand used in older YAML fixtures:

    - bare ``signal`` on a node is treated as ``input_signal`` (the call
      signal arriving at this chip from its caller)
    - bare ``return`` on a node is treated as ``input_return``
    - when no ``output_ports``/``output_signal`` are declared, output port
      declarations are derived from the input signals of child nodes for
      legacy normalization only; later validation still requires explicit
      output declarations for chips that originate inter-chip calls
    """

    moduleNameResult: Result[str] = _requiredStringResult_build(
        nodeDict,
        "module",
        nodeContext=nodeContext,
    )
    if not result_isOkCheck(moduleNameResult):
        return resultErr_build()
    functionNameResult: Result[str] = _requiredStringResult_build(
        nodeDict,
        "func",
        nodeContext=nodeContext,
    )
    if not result_isOkCheck(functionNameResult):
        return resultErr_build()

    # Translate legacy bare 'signal'/'return' keys to
    # 'input_signal'/'input_return' so the rest of the parser sees only
    # the canonical key names.
    portDict: dict[str, object] = _legacyPortKeys_normalize(nodeDict)

    inputPortDeclarationSourceSetResult: Result[
        CircuitPortDeclarationSourceSet
    ] = _portDeclarationSourceSetResult_buildFromNodeDict(
        portDict,
        nodeContext=nodeContext,
        portPrefix="input",
    )
    if not result_isOkCheck(inputPortDeclarationSourceSetResult):
        return resultErr_build()

    # Parse children first so we can derive output ports from them when the
    # parent has no explicit output port declarations.
    childNodeSourcesResult: Result[CircuitNodeSourceChildren] = (
        _childNodeSourcesResult_buildFromNodeDict(
            nodeDict,
            nodeContext=nodeContext,
        )
    )
    if not result_isOkCheck(childNodeSourcesResult):
        return resultErr_build()

    hasExplicitOutputPorts: bool = (
        "output_signal" in portDict
        or "output_return" in portDict
        or "output_ports" in portDict
    )
    hasExplicitInputPorts: bool = (
        "input_signal" in portDict
        or "input_return" in portDict
        or "input_ports" in portDict
    )
    if hasExplicitOutputPorts:
        outputPortDeclarationSourceSetResult: Result[
            CircuitPortDeclarationSourceSet
        ] = _portDeclarationSourceSetResult_buildFromNodeDict(
            portDict,
            nodeContext=nodeContext,
            portPrefix="output",
        )
    else:
        outputPortDeclarationSourceSetResult = (
            _legacyOutputPorts_buildFromChildren(childNodeSourcesResult.value)
        )
    if not result_isOkCheck(outputPortDeclarationSourceSetResult):
        return resultErr_build()

    wiringDirectiveSourceSetResult: Result[CircuitWiringDirectiveSourceSet] = (
        _wiringDirectiveSourceSetResult_buildFromNodeDict(
            nodeDict,
            nodeContext=nodeContext,
        )
    )
    if not result_isOkCheck(wiringDirectiveSourceSetResult):
        return resultErr_build()
    chipIoSourceResult: Result[CircuitChipIoSource | None] = (
        _chipIoSourceResult_buildFromNodeDict(
            nodeDict,
            nodeContext=nodeContext,
        )
    )
    if not result_isOkCheck(chipIoSourceResult):
        return resultErr_build()

    return resultOk_build(
        CircuitNodeSource(
            moduleName=moduleNameResult.value,
            functionName=functionNameResult.value,
            hasExplicitInputPorts=hasExplicitInputPorts,
            hasExplicitOutputPorts=hasExplicitOutputPorts,
            inputPortDeclarationSourceSet=inputPortDeclarationSourceSetResult.value,
            outputPortDeclarationSourceSet=outputPortDeclarationSourceSetResult.value,
            wiringDirectiveSourceSet=wiringDirectiveSourceSetResult.value,
            chipIoSource=chipIoSourceResult.value,
            childNodeSources=childNodeSourcesResult.value,
        )
    )


def _requiredStringResult_build(
    mappingDict: dict[str, object],
    key: str,
    nodeContext: str,
) -> Result[str]:
    """Build required string field from one mapping."""

    valueObject: object | None = mappingDict.get(key)
    if not isinstance(valueObject, str) or not valueObject:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.invalid_required_string",
            message=(
                "Circuit node required string fields must be non-empty strings"
            ),
            context=(nodeContext, key),
        )
        return resultErr_build()
    return resultOk_build(valueObject)


def _optionalStringResult_build(
    mappingDict: dict[str, object],
    key: str,
    nodeContext: str,
) -> Result[str | None]:
    """Build optional string field from one mapping."""

    if key not in mappingDict:
        return resultOk_build(None)
    valueObject: object = mappingDict[key]
    if not isinstance(valueObject, str):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.invalid_optional_string",
            message="Optional string fields must be strings when present",
            context=(nodeContext, key),
        )
        return resultErr_build()
    if valueObject == "":
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.empty_optional_string",
            message="Optional string fields must be non-empty when present",
            context=(nodeContext, key),
        )
        return resultErr_build()
    return resultOk_build(valueObject)


def _optionalBoolResult_build(
    mappingDict: dict[str, object],
    key: str,
    nodeContext: str,
) -> Result[bool | None]:
    """Build optional bool field from one mapping."""

    if key not in mappingDict:
        return resultOk_build(None)
    valueObject: object = mappingDict[key]
    if not isinstance(valueObject, bool):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.invalid_optional_bool",
            message="Optional boolean fields must be bool when present",
            context=(nodeContext, key),
        )
        return resultErr_build()
    return resultOk_build(valueObject)


def _portDeclarationSourceSetResult_buildFromNodeDict(
    nodeDict: dict[str, object],
    nodeContext: str,
    portPrefix: str,
) -> Result[CircuitPortDeclarationSourceSet]:
    """Build one typed port source set from a raw node dictionary."""

    portListKey: str = f"{portPrefix}_ports"
    signalKey: str = f"{portPrefix}_signal"
    returnKey: str = f"{portPrefix}_return"
    if portListKey in nodeDict and (
        signalKey in nodeDict or returnKey in nodeDict
    ):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.mixed_port_syntax",
            message=(
                "Port list syntax and backward-compatible shorthand "
                "may not be "
                "mixed on one node"
            ),
            context=(nodeContext, portPrefix),
        )
        return resultErr_build()

    portDeclarationSourcesMutable: list[CircuitPortDeclarationSource] = []
    if portListKey in nodeDict:
        portListObject: object = nodeDict[portListKey]
        if not isinstance(portListObject, list):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.invalid_port_list",
                message="Port declaration lists must be YAML sequences",
                context=(nodeContext, portListKey),
            )
            return resultErr_build()
        portIndex: int
        portObject: object
        for portIndex, portObject in enumerate(portListObject):
            if not isinstance(portObject, dict):
                diagnosticStack.error_push(
                    phase=DiagnosticPhase.VALIDATION,
                    code="engine.input.node.invalid_port_entry",
                    message="Port declarations must be mappings",
                    context=(nodeContext, f"{portListKey}[{portIndex}]"),
                )
                return resultErr_build()
            portSourceResult: Result[CircuitPortDeclarationSource] = (
                _portDeclarationSourceResult_buildFromPortDict(
                    portObject,
                    nodeContext=f"{nodeContext}.{portListKey}[{portIndex}]",
                )
            )
            if not result_isOkCheck(portSourceResult):
                return resultErr_build()
            portDeclarationSourcesMutable.append(portSourceResult.value)
    else:
        signalNameResult: Result[str | None] = _optionalStringResult_build(
            nodeDict,
            signalKey,
            nodeContext=nodeContext,
        )
        if not result_isOkCheck(signalNameResult):
            return resultErr_build()
        returnNameResult: Result[str | None] = _optionalStringResult_build(
            nodeDict,
            returnKey,
            nodeContext=nodeContext,
        )
        if not result_isOkCheck(returnNameResult):
            return resultErr_build()
        if (
            signalNameResult.value is not None
            or returnNameResult.value is not None
        ):
            portDeclarationSourcesMutable.append(
                CircuitPortDeclarationSource(
                    signalName=signalNameResult.value,
                    returnName=returnNameResult.value,
                )
            )

    return resultOk_build(
        CircuitPortDeclarationSourceSet(
            portDeclarationSources=tuple(portDeclarationSourcesMutable)
        )
    )


def _portDeclarationSourceResult_buildFromPortDict(
    portDict: dict[str, object],
    nodeContext: str,
) -> Result[CircuitPortDeclarationSource]:
    """Build one typed port source from a raw port dictionary."""

    signalNameResult: Result[str | None] = _optionalStringResult_build(
        portDict,
        "signal",
        nodeContext=nodeContext,
    )
    if not result_isOkCheck(signalNameResult):
        return resultErr_build()
    returnNameResult: Result[str | None] = _optionalStringResult_build(
        portDict,
        "return",
        nodeContext=nodeContext,
    )
    if not result_isOkCheck(returnNameResult):
        return resultErr_build()
    if signalNameResult.value is None and returnNameResult.value is None:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.empty_port_declaration",
            message=(
                "Port declarations must declare signal and/or return labels"
            ),
            context=(nodeContext,),
        )
        return resultErr_build()
    return resultOk_build(
        CircuitPortDeclarationSource(
            signalName=signalNameResult.value,
            returnName=returnNameResult.value,
        )
    )


def _callBindOutputPortDeclarationSourceOrNoneResult_build(
    nodeDict: dict[str, object],
    nodeContext: str,
) -> Result[CircuitPortDeclarationSource | None]:
    """Build optional parent-output binding from one child node dict."""

    if "bind_output" not in nodeDict:
        return resultOk_build(None)
    bindOutputObject: object = nodeDict["bind_output"]
    if not isinstance(bindOutputObject, dict):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.invalid_bind_output",
            message="bind_output must be a mapping",
            context=(nodeContext, "bind_output"),
        )
        return resultErr_build()
    return _portDeclarationSourceResult_buildFromPortDict(  # type: ignore[return-value]
        bindOutputObject,
        nodeContext=f"{nodeContext}.bind_output",
    )


def _wiringDirectiveSourceSetResult_buildFromNodeDict(
    nodeDict: dict[str, object],
    nodeContext: str,
) -> Result[CircuitWiringDirectiveSourceSet]:
    """Build typed internal-wiring directive sources from one node."""

    if "internal_wiring" not in nodeDict:
        return resultOk_build(CircuitWiringDirectiveSourceSet())

    wiringListObject: object = nodeDict["internal_wiring"]
    if not isinstance(wiringListObject, list):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.invalid_internal_wiring_list",
            message="internal_wiring must be a YAML sequence",
            context=(nodeContext, "internal_wiring"),
        )
        return resultErr_build()

    wiringDirectiveSourcesMutable: list[CircuitWiringDirectiveSource] = []
    wiringIndex: int
    wiringObject: object
    for wiringIndex, wiringObject in enumerate(wiringListObject):
        if not isinstance(wiringObject, str) or not wiringObject:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.invalid_internal_wiring_entry",
                message="internal_wiring entries must be non-empty strings",
                context=(nodeContext, f"internal_wiring[{wiringIndex}]"),
            )
            return resultErr_build()
        wiringDirectiveSourcesMutable.append(
            CircuitWiringDirectiveSource(wiringDeclaration=wiringObject)
        )

    return resultOk_build(
        CircuitWiringDirectiveSourceSet(
            wiringDirectiveSources=tuple(wiringDirectiveSourcesMutable)
        )
    )


def _chipIoSourceResult_buildFromNodeDict(
    nodeDict: dict[str, object],
    nodeContext: str,
) -> Result[CircuitChipIoSource | None]:
    """Build typed `chip_io` source from one node dictionary."""

    if "chip_io" not in nodeDict:
        return resultOk_build(None)
    chipIoObject: object = nodeDict["chip_io"]
    if not isinstance(chipIoObject, dict):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.invalid_chip_io",
            message="chip_io must be a mapping",
            context=(nodeContext, "chip_io"),
        )
        return resultErr_build()

    chipIoInputSource: CircuitChipIoInputSource | None = None
    if "input" in chipIoObject:
        inputObject: object = chipIoObject["input"]
        if not isinstance(inputObject, dict):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.invalid_chip_io_input",
                message="chip_io.input must be a mapping",
                context=(nodeContext, "chip_io.input"),
            )
            return resultErr_build()
        explicitResult: Result[bool | None] = _optionalBoolResult_build(
            inputObject,
            "explicit",
            nodeContext=f"{nodeContext}.chip_io.input",
        )
        if not result_isOkCheck(explicitResult):
            return resultErr_build()
        chipIoInputSource = CircuitChipIoInputSource(
            explicit=explicitResult.value
        )

    chipIoInternalWiringSource: CircuitChipIoInternalWiringSource | None = None
    if "internal_wiring" in chipIoObject:
        internalWiringObject: object = chipIoObject["internal_wiring"]
        if not isinstance(internalWiringObject, dict):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.invalid_chip_io_internal_wiring",
                message="chip_io.internal_wiring must be a mapping",
                context=(nodeContext, "chip_io.internal_wiring"),
            )
            return resultErr_build()
        colorizeResult: Result[bool | None] = _optionalBoolResult_build(
            internalWiringObject,
            "colorize",
            nodeContext=f"{nodeContext}.chip_io.internal_wiring",
        )
        if not result_isOkCheck(colorizeResult):
            return resultErr_build()
        showInternalLabelsResult: Result[bool | None] = (
            _optionalBoolResult_build(
                internalWiringObject,
                "showInternalLabels",
                nodeContext=f"{nodeContext}.chip_io.internal_wiring",
            )
        )
        if not result_isOkCheck(showInternalLabelsResult):
            return resultErr_build()
        aliasInternalLabelsResult: Result[bool | None] = (
            _optionalBoolResult_build(
                internalWiringObject,
                "aliasInternalLabels",
                nodeContext=f"{nodeContext}.chip_io.internal_wiring",
            )
        )
        if not result_isOkCheck(aliasInternalLabelsResult):
            return resultErr_build()
        chipIoInternalWiringSource = CircuitChipIoInternalWiringSource(
            colorize=colorizeResult.value,
            showInternalLabels=showInternalLabelsResult.value,
            aliasInternalLabels=aliasInternalLabelsResult.value,
        )

    return resultOk_build(
        CircuitChipIoSource(
            chipIoInputSource=chipIoInputSource,
            chipIoInternalWiringSource=chipIoInternalWiringSource,
        )
    )


def _childNodeSourcesResult_buildFromNodeDict(
    nodeDict: dict[str, object],
    nodeContext: str,
) -> Result[CircuitNodeSourceChildren]:
    """Build typed child node sources from one node dictionary."""

    if "calls" not in nodeDict:
        return resultOk_build(CircuitNodeSourceChildren())
    callsObject: object = nodeDict["calls"]
    if not isinstance(callsObject, list):
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.invalid_calls_list",
            message="calls must be a YAML sequence",
            context=(nodeContext, "calls"),
        )
        return resultErr_build()
    childCallSourcesMutable: list[CircuitChildCallSource] = []
    childIndex: int
    childObject: object
    for childIndex, childObject in enumerate(callsObject):
        if not isinstance(childObject, dict):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.invalid_call_entry",
                message="calls entries must be mappings",
                context=(nodeContext, f"calls[{childIndex}]"),
            )
            return resultErr_build()
        childNodeSourceResult: Result[CircuitNodeSource] = (
            _circuitNodeSourceResult_buildFromNodeDict(
                childObject,
                nodeContext=f"{nodeContext}.calls[{childIndex}]",
            )
        )
        if not result_isOkCheck(childNodeSourceResult):
            return resultErr_build()
        bindOutputPortDeclarationSourceResult = (
            _callBindOutputPortDeclarationSourceOrNoneResult_build(
                childObject,
                nodeContext=f"{nodeContext}.calls[{childIndex}]",
            )
        )
        if not result_isOkCheck(bindOutputPortDeclarationSourceResult):
            return resultErr_build()
        childCallSourcesMutable.append(
            CircuitChildCallSource(
                childNodeSource=childNodeSourceResult.value,
                bindOutputPortDeclarationSource=(
                    bindOutputPortDeclarationSourceResult.value
                ),
            )
        )
    return resultOk_build(
        CircuitNodeSourceChildren(
            childCallSources=tuple(childCallSourcesMutable)
        )
    )


def _nodeDeclarations_collectCheck(
    circuitNodeSource: CircuitNodeSource,
    declarationRegistryMutable: dict[tuple[str, str], CircuitNodeSource],
) -> bool:
    """Collect and merge canonical chip declarations from the source tree."""

    resolvedNodeSourceResult: Result[CircuitNodeSource] = (
        _resolvedNodeSourceResult_build(
            circuitNodeSource=circuitNodeSource,
            declarationRegistryMutable=declarationRegistryMutable,
        )
    )
    if not result_isOkCheck(resolvedNodeSourceResult):
        return False

    childCallSource: CircuitChildCallSource
    for childCallSource in circuitNodeSource.childNodeSources.childCallSources:
        if not _nodeDeclarations_collectCheck(
            circuitNodeSource=childCallSource.childNodeSource,
            declarationRegistryMutable=declarationRegistryMutable,
        ):
            return False
    return True


def _circuitChipSetResult_buildFromDeclarationRegistry(
    declarationRegistryMutable: dict[tuple[str, str], CircuitNodeSource],
) -> Result[CircuitChipSet]:
    """Build canonical chip set from the merged declaration registry."""

    chipsMutable: list = []
    _declarationKey: tuple[str, str]
    declarationSource: CircuitNodeSource
    for (
        _declarationKey,
        declarationSource,
    ) in declarationRegistryMutable.items():
        chipResult = _chipResult_buildFromNodeSource(
            declarationSource=declarationSource,
        )
        if not result_isOkCheck(chipResult):
            return resultErr_build()
        chipsMutable.append(chipResult.value)
    return circuitChipSetResult_build(chips=tuple(chipsMutable))


def _circuitCallSetResult_buildFromDeclarationRegistry(
    declarationRegistryMutable: dict[tuple[str, str], CircuitNodeSource],
) -> Result[CircuitCallSet]:
    """Build ordered canonical call edges from the declaration registry."""

    circuitCallsMutable: list[CircuitCall] = []
    declarationSource: CircuitNodeSource
    for declarationSource in declarationRegistryMutable.values():
        sourceChipRef: ChipRef = ChipRef(
            chipId=ChipId(
                moduleName=declarationSource.moduleName,
                functionName=declarationSource.functionName,
            )
        )
        childIndex: int
        childCallSource: CircuitChildCallSource
        for childIndex, childCallSource in enumerate(
            declarationSource.childNodeSources.childCallSources
        ):
            circuitCallsMutable.append(
                CircuitCall(
                    sourceChipRef=sourceChipRef,
                    destinationChipRef=ChipRef(
                        chipId=ChipId(
                            moduleName=childCallSource.childNodeSource.moduleName,
                            functionName=childCallSource.childNodeSource.functionName,
                        )
                    ),
                    callIndex=childIndex,
                    sourcePortDeclaration=None,
                )
            )
    return circuitCallSetResult_build(circuitCalls=tuple(circuitCallsMutable))


def _chipPortContracts_validateCheck(
    declarationRegistryMutable: dict[tuple[str, str], CircuitNodeSource],
    circuitCallSet: CircuitCallSet,
    rootNodeSource: CircuitNodeSource,
) -> bool:
    """Validate explicit port ownership against realized graph connectivity."""

    rootKey: tuple[str, str] = (
        rootNodeSource.moduleName,
        rootNodeSource.functionName,
    )
    incomingCountByChipMutable: dict[tuple[str, str], int] = {}
    outgoingCountByChipMutable: dict[tuple[str, str], int] = {}

    circuitCall: CircuitCall
    for circuitCall in circuitCallSet.circuitCalls:
        sourceKey: tuple[str, str] = (
            circuitCall.sourceChipRef.chipId.moduleName,
            circuitCall.sourceChipRef.chipId.functionName,
        )
        destinationKey: tuple[str, str] = (
            circuitCall.destinationChipRef.chipId.moduleName,
            circuitCall.destinationChipRef.chipId.functionName,
        )
        outgoingCountByChipMutable[sourceKey] = (
            outgoingCountByChipMutable.get(sourceKey, 0) + 1
        )
        incomingCountByChipMutable[destinationKey] = (
            incomingCountByChipMutable.get(destinationKey, 0) + 1
        )

    declarationKey: tuple[str, str]
    declarationSource: CircuitNodeSource
    for (
        declarationKey,
        declarationSource,
    ) in declarationRegistryMutable.items():
        incomingCount: int = incomingCountByChipMutable.get(declarationKey, 0)
        outgoingCount: int = outgoingCountByChipMutable.get(declarationKey, 0)

        if outgoingCount > 0 and not declarationSource.hasExplicitOutputPorts:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.missing_explicit_output_ports",
                message=(
                    "Chips with outgoing calls must declare "
                    "explicit output_ports or "
                    "output_signal/output_return"
                ),
                context=(
                    declarationSource.moduleName,
                    declarationSource.functionName,
                ),
            )
            return False

        if incomingCount > 0 and not declarationSource.hasExplicitInputPorts:
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.missing_explicit_input_ports",
                message=(
                    "Chips with incoming calls must declare "
                    "explicit input_ports or "
                    "input_signal/input_return"
                ),
                context=(
                    declarationSource.moduleName,
                    declarationSource.functionName,
                ),
            )
            return False

        if (
            declarationKey != rootKey
            and incomingCount == 0
            and not declarationSource.hasExplicitInputPorts
        ):
            diagnosticStack.error_push(
                phase=DiagnosticPhase.VALIDATION,
                code="engine.input.node.missing_explicit_input_ports",
                message=(
                    "Non-root chips must declare explicit input_ports or "
                    "input_signal/input_return"
                ),
                context=(
                    declarationSource.moduleName,
                    declarationSource.functionName,
                ),
            )
            return False

    return True


def _chipResult_buildFromNodeSource(
    declarationSource: CircuitNodeSource,
) -> Result:
    """Build one canonical chip from a merged node declaration."""

    inputPortDeclarationSetResult: Result[ChipPortDeclarationSet] = (
        _chipPortDeclarationSetResult_buildFromSourceSet(
            declarationSource.inputPortDeclarationSourceSet
        )
    )
    if not result_isOkCheck(inputPortDeclarationSetResult):
        return resultErr_build()
    outputPortDeclarationSetResult: Result[ChipPortDeclarationSet] = (
        _chipPortDeclarationSetResult_buildFromSourceSet(
            declarationSource.outputPortDeclarationSourceSet
        )
    )
    if not result_isOkCheck(outputPortDeclarationSetResult):
        return resultErr_build()
    outputDisplayPortDeclarationSetResult: Result[ChipPortDeclarationSet] = (
        _chipOutputDisplayPortDeclarationSetResult_build(
            declarationSource=declarationSource,
            outputPortDeclarationSet=outputPortDeclarationSetResult.value,
        )
    )
    if not result_isOkCheck(outputDisplayPortDeclarationSetResult):
        return resultErr_build()
    internalWiringDirectiveSetResult: Result[
        ChipInternalWiringDirectiveSet
    ] = _chipInternalWiringDirectiveSetResult_buildFromSourceSet(
        declarationSource.wiringDirectiveSourceSet
    )
    if not result_isOkCheck(internalWiringDirectiveSetResult):
        return resultErr_build()
    chipTerminalSetResult: Result[ChipTerminalSet] = (
        _chipTerminalSetResult_buildFromPortDeclarationSets(
            inputPortDeclarationSet=inputPortDeclarationSetResult.value,
            outputPortDeclarationSet=outputPortDeclarationSetResult.value,
        )
    )
    if not result_isOkCheck(chipTerminalSetResult):
        return resultErr_build()

    return chipResult_build(
        chipId=ChipId(
            moduleName=declarationSource.moduleName,
            functionName=declarationSource.functionName,
        ),
        chipTerminalSet=chipTerminalSetResult.value,
        inputPortDeclarationSet=inputPortDeclarationSetResult.value,
        outputPortDeclarationSet=outputPortDeclarationSetResult.value,
        outputDisplayPortDeclarationSet=(
            outputDisplayPortDeclarationSetResult.value
        ),
        internalWiringDirectiveSet=internalWiringDirectiveSetResult.value,
        chipIo=_chipIo_buildFromSource(declarationSource.chipIoSource),
    )


def _chipOutputDisplayPortDeclarationSetResult_buildFromBindSource(
    bindOutputSource: CircuitPortDeclarationSource,
) -> Result[ChipPortDeclaration]:
    """Build one display-only declaration from one `bind_output` source."""

    return chipPortDeclarationResult_build(
        signalName=bindOutputSource.signalName,
        returnName=bindOutputSource.returnName,
    )


def _chipOutputDisplayPortDeclarationSetResult_build(
    declarationSource: CircuitNodeSource,
    outputPortDeclarationSet: ChipPortDeclarationSet,
) -> Result[ChipPortDeclarationSet]:
    """Build display declarations from canonical output ports plus aliases.

    `bind_output` is display-only. It may change the wall text shown on the
    source chip for one outgoing call, but it must not replace the canonical
    terminal ids used for routing and attach lookup.
    """

    displayDeclarationsMutable: list[ChipPortDeclaration] = []
    canonicalDeclarations = outputPortDeclarationSet.portDeclarations
    childCalls = declarationSource.childNodeSources.childCallSources
    portIndex: int
    canonicalDeclaration: ChipPortDeclaration
    for portIndex, canonicalDeclaration in enumerate(canonicalDeclarations):
        if portIndex < len(childCalls):
            bindOutputSource = childCalls[
                portIndex
            ].bindOutputPortDeclarationSource
            if bindOutputSource is not None:
                declarationSetResultBuild = _chipOutputDisplayPortDeclarationSetResult_buildFromBindSource  # noqa: E501 - RPN helper name exceeds line limit
                displayDeclarationResult = declarationSetResultBuild(
                    bindOutputSource
                )
                if not result_isOkCheck(displayDeclarationResult):
                    return resultErr_build()
                displayDeclarationsMutable.append(
                    displayDeclarationResult.value
                )
                continue
        displayDeclarationsMutable.append(canonicalDeclaration)
    return chipPortDeclarationSetResult_build(
        portDeclarations=tuple(displayDeclarationsMutable)
    )


def _resolvedNodeSourceResult_build(
    circuitNodeSource: CircuitNodeSource,
    declarationRegistryMutable: dict[tuple[str, str], CircuitNodeSource],
) -> Result[CircuitNodeSource]:
    """Build effective source node by reusing prior fuller declarations."""

    declarationKey: tuple[str, str] = (
        circuitNodeSource.moduleName,
        circuitNodeSource.functionName,
    )
    previousNodeSource: CircuitNodeSource | None = (
        declarationRegistryMutable.get(declarationKey)
    )
    if previousNodeSource is None:
        declarationRegistryMutable[declarationKey] = circuitNodeSource
        return resultOk_build(circuitNodeSource)

    mergedNodeSourceResult: Result[CircuitNodeSource] = (
        _mergedNodeSourceResult_build(
            previousNodeSource=previousNodeSource,
            currentNodeSource=circuitNodeSource,
        )
    )
    if not result_isOkCheck(mergedNodeSourceResult):
        return resultErr_build()
    declarationRegistryMutable[declarationKey] = mergedNodeSourceResult.value
    return resultOk_build(mergedNodeSourceResult.value)


def _mergedNodeSourceResult_build(
    previousNodeSource: CircuitNodeSource,
    currentNodeSource: CircuitNodeSource,
) -> Result[CircuitNodeSource]:
    """Build merged node source from prior fuller and current occurrence."""

    inputPortDeclarationSourceSetResult: Result[
        CircuitPortDeclarationSourceSet
    ] = _mergedPortDeclarationSourceSetResult_build(
        previousPortDeclarationSourceSet=(
            previousNodeSource.inputPortDeclarationSourceSet
        ),
        currentPortDeclarationSourceSet=currentNodeSource.inputPortDeclarationSourceSet,
        conflictContext=(
            previousNodeSource.moduleName,
            previousNodeSource.functionName,
            "input_ports",
        ),
    )
    if not result_isOkCheck(inputPortDeclarationSourceSetResult):
        return resultErr_build()
    outputPortDeclarationSourceSetResult: Result[
        CircuitPortDeclarationSourceSet
    ] = _mergedPortDeclarationSourceSetResult_build(
        previousPortDeclarationSourceSet=(
            previousNodeSource.outputPortDeclarationSourceSet
        ),
        currentPortDeclarationSourceSet=currentNodeSource.outputPortDeclarationSourceSet,
        conflictContext=(
            previousNodeSource.moduleName,
            previousNodeSource.functionName,
            "output_ports",
        ),
    )
    if not result_isOkCheck(outputPortDeclarationSourceSetResult):
        return resultErr_build()
    wiringDirectiveSourceSetResult: Result[CircuitWiringDirectiveSourceSet] = (
        _mergedWiringDirectiveSourceSetResult_build(
            previousWiringDirectiveSourceSet=previousNodeSource.wiringDirectiveSourceSet,
            currentWiringDirectiveSourceSet=currentNodeSource.wiringDirectiveSourceSet,
            conflictContext=(
                previousNodeSource.moduleName,
                previousNodeSource.functionName,
                "internal_wiring",
            ),
        )
    )
    if not result_isOkCheck(wiringDirectiveSourceSetResult):
        return resultErr_build()
    chipIoSourceResult: Result[CircuitChipIoSource | None] = (
        _mergedChipIoSourceResult_build(
            previousChipIoSource=previousNodeSource.chipIoSource,
            currentChipIoSource=currentNodeSource.chipIoSource,
            conflictContext=(
                previousNodeSource.moduleName,
                previousNodeSource.functionName,
                "chip_io",
            ),
        )
    )
    if not result_isOkCheck(chipIoSourceResult):
        return resultErr_build()
    childNodeSourcesResult: Result[CircuitNodeSourceChildren] = (
        _mergedChildNodeSourcesResult_build(
            previousChildNodeSources=previousNodeSource.childNodeSources,
            currentChildNodeSources=currentNodeSource.childNodeSources,
            conflictContext=(
                previousNodeSource.moduleName,
                previousNodeSource.functionName,
                "calls",
            ),
        )
    )
    if not result_isOkCheck(childNodeSourcesResult):
        return resultErr_build()

    return resultOk_build(
        CircuitNodeSource(
            moduleName=currentNodeSource.moduleName,
            functionName=currentNodeSource.functionName,
            hasExplicitInputPorts=(
                previousNodeSource.hasExplicitInputPorts
                or currentNodeSource.hasExplicitInputPorts
            ),
            hasExplicitOutputPorts=(
                previousNodeSource.hasExplicitOutputPorts
                or currentNodeSource.hasExplicitOutputPorts
            ),
            inputPortDeclarationSourceSet=inputPortDeclarationSourceSetResult.value,
            outputPortDeclarationSourceSet=outputPortDeclarationSourceSetResult.value,
            wiringDirectiveSourceSet=wiringDirectiveSourceSetResult.value,
            chipIoSource=chipIoSourceResult.value,
            childNodeSources=childNodeSourcesResult.value,
        )
    )


def _chipPortDeclarationSetResult_buildFromSourceSet(
    portDeclarationSourceSet: CircuitPortDeclarationSourceSet,
) -> Result[ChipPortDeclarationSet]:
    """Build validated chip port declarations from one source port set."""

    portDeclarationsMutable: list[ChipPortDeclaration] = []
    portDeclarationSource: CircuitPortDeclarationSource
    for (
        portDeclarationSource
    ) in portDeclarationSourceSet.portDeclarationSources:
        portDeclarationResult: Result[ChipPortDeclaration] = (
            chipPortDeclarationResult_build(
                signalName=portDeclarationSource.signalName,
                returnName=portDeclarationSource.returnName,
            )
        )
        if not result_isOkCheck(portDeclarationResult):
            return resultErr_build()
        portDeclarationsMutable.append(portDeclarationResult.value)
    return chipPortDeclarationSetResult_build(
        portDeclarations=tuple(portDeclarationsMutable)
    )


def _mergedPortDeclarationSourceSetResult_build(
    previousPortDeclarationSourceSet: CircuitPortDeclarationSourceSet,
    currentPortDeclarationSourceSet: CircuitPortDeclarationSourceSet,
    conflictContext: tuple[str, ...],
) -> Result[CircuitPortDeclarationSourceSet]:
    """Build merged port declarations from prior and current values."""

    previousDeclarations: tuple[CircuitPortDeclarationSource, ...] = (
        previousPortDeclarationSourceSet.portDeclarationSources
    )
    currentDeclarations: tuple[CircuitPortDeclarationSource, ...] = (
        currentPortDeclarationSourceSet.portDeclarationSources
    )
    if not currentDeclarations:
        return resultOk_build(previousPortDeclarationSourceSet)
    if not previousDeclarations:
        return resultOk_build(currentPortDeclarationSourceSet)
    if currentDeclarations != previousDeclarations:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.conflicting_reuse_declaration",
            message=_CONFLICTING_REUSE_MESSAGE,
            context=conflictContext,
        )
        return resultErr_build()
    return resultOk_build(currentPortDeclarationSourceSet)


def _mergedWiringDirectiveSourceSetResult_build(
    previousWiringDirectiveSourceSet: CircuitWiringDirectiveSourceSet,
    currentWiringDirectiveSourceSet: CircuitWiringDirectiveSourceSet,
    conflictContext: tuple[str, ...],
) -> Result[CircuitWiringDirectiveSourceSet]:
    """Build merged internal wiring from prior and current values."""

    previousDirectives: tuple[CircuitWiringDirectiveSource, ...] = (
        previousWiringDirectiveSourceSet.wiringDirectiveSources
    )
    currentDirectives: tuple[CircuitWiringDirectiveSource, ...] = (
        currentWiringDirectiveSourceSet.wiringDirectiveSources
    )
    if not currentDirectives:
        return resultOk_build(previousWiringDirectiveSourceSet)
    if not previousDirectives:
        return resultOk_build(currentWiringDirectiveSourceSet)
    if currentDirectives != previousDirectives:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.conflicting_reuse_declaration",
            message=_CONFLICTING_REUSE_MESSAGE,
            context=conflictContext,
        )
        return resultErr_build()
    return resultOk_build(currentWiringDirectiveSourceSet)


def _mergedChipIoSourceResult_build(
    previousChipIoSource: CircuitChipIoSource | None,
    currentChipIoSource: CircuitChipIoSource | None,
    conflictContext: tuple[str, ...],
) -> Result[CircuitChipIoSource | None]:
    """Build merged chip-io source from prior and current values."""

    if currentChipIoSource is None:
        return resultOk_build(previousChipIoSource)
    if previousChipIoSource is None:
        return resultOk_build(currentChipIoSource)
    if currentChipIoSource != previousChipIoSource:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.conflicting_reuse_declaration",
            message=_CONFLICTING_REUSE_MESSAGE,
            context=conflictContext,
        )
        return resultErr_build()
    return resultOk_build(currentChipIoSource)


def _mergedChildNodeSourcesResult_build(
    previousChildNodeSources: CircuitNodeSourceChildren,
    currentChildNodeSources: CircuitNodeSourceChildren,
    conflictContext: tuple[str, ...],
) -> Result[CircuitNodeSourceChildren]:
    """Build merged child-node source set from prior/current values."""

    previousChildren: tuple[CircuitChildCallSource, ...] = (
        previousChildNodeSources.childCallSources
    )
    currentChildren: tuple[CircuitChildCallSource, ...] = (
        currentChildNodeSources.childCallSources
    )
    if not currentChildren:
        return resultOk_build(previousChildNodeSources)
    if not previousChildren:
        return resultOk_build(currentChildNodeSources)
    if currentChildren != previousChildren:
        diagnosticStack.error_push(
            phase=DiagnosticPhase.VALIDATION,
            code="engine.input.node.conflicting_reuse_declaration",
            message=_CONFLICTING_REUSE_MESSAGE,
            context=conflictContext,
        )
        return resultErr_build()
    return resultOk_build(currentChildNodeSources)


def _chipInternalWiringDirectiveSetResult_buildFromSourceSet(
    wiringDirectiveSourceSet: CircuitWiringDirectiveSourceSet,
) -> Result[ChipInternalWiringDirectiveSet]:
    """Build validated internal-wiring directives from one source set."""

    directivesMutable: list[ChipInternalWiringDirective] = []
    wiringDirectiveSource: CircuitWiringDirectiveSource
    for (
        wiringDirectiveSource
    ) in wiringDirectiveSourceSet.wiringDirectiveSources:
        directiveResult: Result[ChipInternalWiringDirective] = (
            chipInternalWiringDirectiveResult_build(
                wiringDeclaration=wiringDirectiveSource.wiringDeclaration
            )
        )
        if not result_isOkCheck(directiveResult):
            return resultErr_build()
        directivesMutable.append(directiveResult.value)
    return chipInternalWiringDirectiveSetResult_build(
        directives=tuple(directivesMutable)
    )


def _chipTerminalSetResult_buildFromPortDeclarationSets(
    inputPortDeclarationSet: ChipPortDeclarationSet,
    outputPortDeclarationSet: ChipPortDeclarationSet,
) -> Result[ChipTerminalSet]:
    """Build chip terminals from validated input and output port declarations.

    Current synthesis rule:
        - input_ports signal and return labels both become west terminals
        - output_ports signal and return labels both become east terminals

    The port declaration names the chip wall, not a transaction direction.
    `signal` and `return` within one port differ only in row ordering on that
    wall, not in which wall they belong to.  This matches the legacy
    chip_geometry model where leftNames = all input_ports labels and
    rightNames = all output_ports labels.
    """

    # Use an insertion-ordered dict keyed by (name, side) so that the same
    # label appearing in multiple port roles on the same wall (e.g. a pipeline
    # chain where one port's return name equals the next port's signal name) is
    # deduplicated to a single terminal.  This matches the legacy behaviour
    # where rightNames / leftNames were plain sets.
    terminalsByKey: dict[tuple[str, ChipTerminalSide], ChipTerminal] = {}
    portDeclaration: ChipPortDeclaration
    for portDeclaration in inputPortDeclarationSet.portDeclarations:
        for name in (portDeclaration.signalName, portDeclaration.returnName):
            if name is not None:
                key = (name, ChipTerminalSide.WEST)
                terminalsByKey.setdefault(
                    key,
                    ChipTerminal(
                        terminalName=name,
                        terminalSide=ChipTerminalSide.WEST,
                    ),
                )
    for portDeclaration in outputPortDeclarationSet.portDeclarations:
        for name in (portDeclaration.signalName, portDeclaration.returnName):
            if name is not None:
                key = (name, ChipTerminalSide.EAST)
                terminalsByKey.setdefault(
                    key,
                    ChipTerminal(
                        terminalName=name,
                        terminalSide=ChipTerminalSide.EAST,
                    ),
                )
    return chipTerminalSetResult_build(
        terminals=tuple(terminalsByKey.values())
    )


def _legacyPortKeys_normalize(
    nodeDict: dict[str, object],
) -> dict[str, object]:
    """Return a copy with legacy bare 'signal'/'return' keys renamed.

    When a node uses the legacy bare ``signal`` key and has no canonical
    ``input_signal`` or ``input_ports`` already present, ``signal`` is
    renamed to ``input_signal`` so the standard port parser picks it up.
    The same applies to bare ``return`` -> ``input_return``. If the
    canonical keys are already present the dict is returned unchanged.
    """

    needsSignalFix: bool = (
        "signal" in nodeDict
        and nodeDict["signal"] is not None
        and "input_signal" not in nodeDict
        and "input_ports" not in nodeDict
    )
    needsReturnFix: bool = (
        "return" in nodeDict
        and nodeDict["return"] is not None
        and "input_return" not in nodeDict
        and "input_ports" not in nodeDict
    )
    if not needsSignalFix and not needsReturnFix:
        return nodeDict
    portDict: dict[str, object] = dict(nodeDict)
    if needsSignalFix:
        portDict["input_signal"] = portDict.pop("signal")
    if needsReturnFix:
        portDict["input_return"] = portDict.pop("return")
    return portDict


def _legacyOutputPorts_buildFromChildren(
    childNodeSources: CircuitNodeSourceChildren,
) -> Result[CircuitPortDeclarationSourceSet]:
    """Derive output port declarations from children's input signals.

    When a parent chip has no explicit ``output_ports``/``output_signal``
    declaration (legacy YAML style), its output ports are the union of its
    children's input port signals.  Each unique (signalName, returnName) pair
    becomes one output port declaration, preserving child call order.

    This exists only as an input-normalization fallback. The validated graph
    still requires explicit output declarations on chips with outgoing calls.
    """

    seen: set[tuple[str | None, str | None]] = set()
    declarations: list[CircuitPortDeclarationSource] = []
    childCallSource: CircuitChildCallSource
    for childCallSource in childNodeSources.childCallSources:
        portSource: CircuitPortDeclarationSource
        inputDeclarationSourceSet = (
            childCallSource.childNodeSource.inputPortDeclarationSourceSet
        )
        for portSource in inputDeclarationSourceSet.portDeclarationSources:
            key: tuple[str | None, str | None] = (
                portSource.signalName,
                portSource.returnName,
            )
            if key not in seen and (
                portSource.signalName is not None
                or portSource.returnName is not None
            ):
                seen.add(key)
                declarations.append(
                    CircuitPortDeclarationSource(
                        signalName=portSource.signalName,
                        returnName=portSource.returnName,
                    )
                )
    return resultOk_build(
        CircuitPortDeclarationSourceSet(
            portDeclarationSources=tuple(declarations)
        )
    )


def _chipIo_buildFromSource(
    chipIoSource: CircuitChipIoSource | None,
) -> ChipIo:
    """Build validated chip-io block from source form."""

    if chipIoSource is None:
        return ChipIo()
    return ChipIo(
        chipIoInput=ChipIoInput(
            explicit=(
                None
                if chipIoSource.chipIoInputSource is None
                else chipIoSource.chipIoInputSource.explicit
            )
        ),
        chipIoInternalWiring=ChipIoInternalWiring(
            colorize=(
                None
                if chipIoSource.chipIoInternalWiringSource is None
                else chipIoSource.chipIoInternalWiringSource.colorize
            ),
            showInternalLabels=(
                None
                if chipIoSource.chipIoInternalWiringSource is None
                else chipIoSource.chipIoInternalWiringSource.showInternalLabels
            ),
            aliasInternalLabels=(
                None
                if chipIoSource.chipIoInternalWiringSource is None
                else (
                    chipIoSource.chipIoInternalWiringSource.aliasInternalLabels
                )
            ),
        ),
    )
