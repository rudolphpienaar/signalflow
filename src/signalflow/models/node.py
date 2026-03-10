"""Graph node model: functional units, ports, and geometry (RPN Naming)."""
from __future__ import annotations

# Standard library
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# Local
from signalflow.config import config

if TYPE_CHECKING:
    from signalflow.models.chip_geometry import ChipGeometry

# PortKey uniquely identifies one call occurrence in a parent→child edge.
# Format: (id(other_node), call_index) where call_index is the sequential
# count of how many times any parent has bound a port on the child up to
# and including this call.  This replaces the bare int (id(node)) key that
# caused silent collisions when the same child was called more than once.
PortKey = tuple[int, int]


@dataclass
class Port:
    """Represents a named entry/exit point on a functional unit."""
    signal: str | None = None
    ret:    str | None = None


@dataclass
class Node:
    """A unique functional unit (chip) within the call graph.

    Nodes are canonicalized by their (module, func) pair. They maintain
    input and output ports, parent/child relationships, and canvas
    coordinates.

    Attributes:
        module: Name of the source file/module.
        func: Name of the function.
        children: De-duplicated list of unique child Nodes (layout/traversal).
        call_sequence: Ordered call list including repeated children, each
            entry is (child, out_key, in_key) for wire rendering.
        input_ports: Map of PortKey -> Port (Call entry/return).
        output_ports: Map of PortKey -> Port (Call exit/return).
        unbound_inputs: Pool of defined but unused input ports.
        unbound_outputs: Pool of defined but unused output ports.
        internal_wiring: List of 'src:dst' signal mapping strings.
        x, y: Canvas coordinates of the top-left corner.
        ow: Outer width of the chip box.
        chipH: Total height of the chip in rows.
        col: Assigned column index in the diagram.
        entryRow: Global row for the primary entry signal (first port).
        returnRow: Global row for the primary return signal (first port).
        entryRows: Map of PortKey -> specific entry row.
        returnRows: Map of PortKey -> specific return row.
    """
    module: str
    func:   str
    children:        list[Node]                          = field(default_factory=list)
    call_sequence:   list[tuple[Node, PortKey, PortKey]] = field(default_factory=list)
    input_ports:     dict[PortKey, Port]                 = field(default_factory=dict)
    output_ports:    dict[PortKey, Port]                 = field(default_factory=dict)
    unbound_inputs:  list[Port]                          = field(default_factory=list)
    unbound_outputs: list[Port]                          = field(default_factory=list)
    internal_wiring: list[str]                           = field(default_factory=list)

    # Sovereign Interface Logic
    inputExplicit: bool | None = None  # None: defer to global config
    internalWireColorizeOverride: bool | None = None
    showInternalLabelsOverride: bool | None = None
    aliasInternalLabelsOverride: bool | None = None

    # Geometry (set by layout_compute)
    x:          int  = 0
    y:          int  = 0
    ow:         int  = 0
    chipH:      int  = 0
    col:        int  = 0
    entryRow:   int  = 0
    returnRow:  int  = 0
    entryRows:  dict[PortKey, int] = field(default_factory=dict)
    returnRows: dict[PortKey, int] = field(default_factory=dict)

    # Authoritative geometry record (set by layout_compute via build_structural)
    geometry: ChipGeometry | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Seed a default chip height for freshly created nodes."""
        if self.chipH == 0:
            self.chipH = config.baseLeafHeight

    @property
    def isRoot(self) -> bool:
        """True if this node has no parents (assigned by the factory)."""
        return not self.input_ports

    @property
    def isInputExplicit(self) -> bool:
        """Resolved inputExplicit: None defers to config.chipIoInputExplicit."""
        if self.inputExplicit is None:
            return config.chipIoInputExplicit
        return self.inputExplicit

    @property
    def internalWireColorizeResolved(self) -> bool:
        """Resolved internal-wire colorization flag for this chip."""
        if self.internalWireColorizeOverride is None:
            return config.internalWireColorize
        return self.internalWireColorizeOverride

    @property
    def showInternalLabelsResolved(self) -> bool:
        """Resolved internal-label visibility flag for this chip."""
        if self.showInternalLabelsOverride is None:
            return config.showInternalLabels
        return self.showInternalLabelsOverride

    @property
    def aliasInternalLabelsResolved(self) -> bool:
        """Resolved internal-label aliasing flag for this chip."""
        if self.aliasInternalLabelsOverride is None:
            return config.aliasInternalLabels
        return self.aliasInternalLabelsOverride

    @classmethod
    def _ports_get(cls, data: dict, keyPrefix: str) -> list[Port]:
        """Return normalized port definitions for one input/output prefix."""
        ports: list[Port] = []
        portList: list[dict] | None = data.get(f"{keyPrefix}_ports")
        if portList:
            return [Port(port.get("signal"), port.get("return")) for port in portList]
        if data.get(f"{keyPrefix}_signal") or data.get(f"{keyPrefix}_return"):
            ports.append(
                Port(
                    data.get(f"{keyPrefix}_signal"),
                    data.get(f"{keyPrefix}_return"),
                )
            )
        return ports

    @classmethod
    def _chipIoOverrides_parse(
        cls, data: dict
    ) -> tuple[bool | None, bool | None, bool | None, bool | None]:
        """Parse optional per-chip input and internal-wiring overrides."""
        inputExplicit: bool | None = None
        internalWireColorizeOverride: bool | None = None
        showInternalLabelsOverride: bool | None = None
        aliasInternalLabelsOverride: bool | None = None
        if "chip_io" not in data or not isinstance(data["chip_io"], dict):
            return (
                inputExplicit,
                internalWireColorizeOverride,
                showInternalLabelsOverride,
                aliasInternalLabelsOverride,
            )

        chipIo: dict = data["chip_io"]
        if "input" in chipIo and isinstance(chipIo["input"], dict):
            chipInput: dict = chipIo["input"]
            if "explicit" in chipInput:
                inputExplicit = bool(chipInput["explicit"])

        if "internal_wiring" not in chipIo or not isinstance(
            chipIo["internal_wiring"], dict
        ):
            return (
                inputExplicit,
                internalWireColorizeOverride,
                showInternalLabelsOverride,
                aliasInternalLabelsOverride,
            )

        chipWiring: dict = chipIo["internal_wiring"]
        if "colorize" in chipWiring:
            internalWireColorizeOverride = bool(chipWiring["colorize"])
        if "showInternalLabels" in chipWiring:
            showInternalLabelsOverride = bool(chipWiring["showInternalLabels"])
        if "show_internal_labels" in chipWiring:
            showInternalLabelsOverride = bool(chipWiring["show_internal_labels"])
        if "aliasInternalLabels" in chipWiring:
            aliasInternalLabelsOverride = bool(chipWiring["aliasInternalLabels"])
        if "alias_internal_labels" in chipWiring:
            aliasInternalLabelsOverride = bool(chipWiring["alias_internal_labels"])
        return (
            inputExplicit,
            internalWireColorizeOverride,
            showInternalLabelsOverride,
            aliasInternalLabelsOverride,
        )

    @classmethod
    def _registryNode_getOrCreate(
        cls,
        data: dict,
        registry: dict[str, Node],
    ) -> Node:
        """Return the canonical node for one `(module, func)` pair."""
        key: str = f"{data['module']}:{data['func']}"
        (
            inputExplicit,
            internalWireColorizeOverride,
            showInternalLabelsOverride,
            aliasInternalLabelsOverride,
        ) = cls._chipIoOverrides_parse(data)

        if key not in registry:
            node = cls(
                module=data["module"],
                func=data["func"],
                internal_wiring=data.get("internal_wiring", []),
                unbound_inputs=cls._ports_get(data, "input"),
                unbound_outputs=cls._ports_get(data, "output"),
                inputExplicit=inputExplicit,
                internalWireColorizeOverride=internalWireColorizeOverride,
                showInternalLabelsOverride=showInternalLabelsOverride,
                aliasInternalLabelsOverride=aliasInternalLabelsOverride,
            )
            registry[key] = node
            return node

        node = registry[key]
        newInputs: list[Port] = cls._ports_get(data, "input")
        newOutputs: list[Port] = cls._ports_get(data, "output")
        if len(newInputs) > len(node.unbound_inputs):
            node.unbound_inputs = newInputs
        if len(newOutputs) > len(node.unbound_outputs):
            node.unbound_outputs = newOutputs
        if not node.internal_wiring and "internal_wiring" in data:
            node.internal_wiring = data["internal_wiring"]
        if node.inputExplicit is None:
            node.inputExplicit = inputExplicit
        if node.internalWireColorizeOverride is None:
            node.internalWireColorizeOverride = internalWireColorizeOverride
        if node.showInternalLabelsOverride is None:
            node.showInternalLabelsOverride = showInternalLabelsOverride
        if node.aliasInternalLabelsOverride is None:
            node.aliasInternalLabelsOverride = aliasInternalLabelsOverride
        return node

    @classmethod
    def _childPorts_bind(
        cls,
        node: Node,
        child: Node,
        childDict: dict,
        childIdx: int,
        portCounters: dict[str, int],
    ) -> tuple[PortKey, PortKey]:
        """Bind one parent→child call occurrence and return its port keys."""
        childKey: str = f"{child.module}:{child.func}"
        currentInIdx: int = portCounters.get(childKey, 0)
        inKey: PortKey = (id(node), currentInIdx)
        outKey: PortKey = (id(child), currentInIdx)

        localInputs: list[Port] = cls._ports_get(childDict, "input")
        if localInputs:
            child.input_ports[inKey] = localInputs[0]
        elif currentInIdx < len(child.unbound_inputs):
            child.input_ports[inKey] = child.unbound_inputs[currentInIdx]
        else:
            child.input_ports[inKey] = Port()

        portCounters[childKey] = currentInIdx + 1

        if childIdx < len(node.unbound_outputs):
            node.output_ports[outKey] = node.unbound_outputs[childIdx]
        else:
            node.output_ports[outKey] = Port()

        return outKey, inKey

    @classmethod
    def node_fromDict(
        cls,
        d: dict,
        registry: dict[str, Node] | None = None,
        isRoot: bool = True,
        portCounters: dict[str, int] | None = None,
    ) -> Node:
        """Deserialise call-tree dict into a unique-chip Graph with smart port binding.
        """
        if registry is None:
            registry = {}
        if portCounters is None:
            portCounters = {}
        node: Node = cls._registryNode_getOrCreate(d, registry)

        # Process children
        childIdx: int
        cDict: dict
        for childIdx, cDict in enumerate(d.get("calls", [])):
            child: Node = cls.node_fromDict(
                cDict, registry, isRoot=False, portCounters=portCounters
            )

            if child not in node.children:
                node.children.append(child)

            out_key: PortKey
            in_key: PortKey
            out_key, in_key = cls._childPorts_bind(
                node, child, cDict, childIdx, portCounters
            )
            node.call_sequence.append((child, out_key, in_key))

        return node
