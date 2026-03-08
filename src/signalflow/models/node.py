"""Graph node model: functional units, ports, and geometry (RPN Naming)."""
from __future__ import annotations

# Standard library
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# Local
from signalflow.config import config

if TYPE_CHECKING:
    from signalflow.models.chip_geometry import ChipGeometry


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
        children: List of child nodes called by this function.
        input_ports: Map of parent_id -> Port (Call entry/return).
        output_ports: Map of child_id -> Port (Call exit/return).
        unbound_inputs: Pool of defined but unused input ports.
        unbound_outputs: Pool of defined but unused output ports.
        internal_wiring: List of 'src:dst' signal mapping strings.
        x, y: Canvas coordinates of the top-left corner.
        ow: Outer width of the chip box.
        chipH: Total height of the chip in rows.
        col: Assigned column index in the diagram.
        entryRow: Global row for the primary entry signal.
        returnRow: Global row for the primary return signal.
        entryRows: Map of parent_id -> specific entry row.
        returnRows: Map of parent_id -> specific return row.
    """
    module: str
    func:   str
    children:        list[Node] = field(default_factory=list)
    input_ports:     dict[int, Port] = field(default_factory=dict)
    output_ports:    dict[int, Port] = field(default_factory=dict)
    unbound_inputs:  list[Port] = field(default_factory=list)
    unbound_outputs: list[Port] = field(default_factory=list)
    internal_wiring: list[str] = field(default_factory=list)

    # Sovereign Interface Logic
    inputExplicit: bool | None = None  # None: defer to global config

    # Geometry (set by layout_compute)
    x:          int  = 0
    y:          int  = 0
    ow:         int  = 0
    chipH:      int  = 0
    col:        int  = 0
    entryRow:   int  = 0
    returnRow:  int  = 0
    entryRows:  dict[int, int] = field(default_factory=dict)
    returnRows: dict[int, int] = field(default_factory=dict)

    # Authoritative geometry record (set by layout_compute via build_structural)
    geometry: ChipGeometry | None = field(default=None, init=False)

    def __post_init__(self) -> None:
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

        def _get_ports(data: dict, keyPrefix: str) -> list[Port]:
            ports: list[Port] = []
            pList: list[dict] | None = data.get(f"{keyPrefix}_ports")
            if pList:
                ports = [Port(p.get("signal"), p.get("return")) for p in pList]
            elif data.get(f"{keyPrefix}_signal") or data.get(f"{keyPrefix}_return"):
                ports = [
                    Port(
                        data.get(f"{keyPrefix}_signal"), data.get(f"{keyPrefix}_return")
                    )
                ]
            return ports

        # Chip Canonicalization
        key: str = f"{d['module']}:{d['func']}"
        node: Node

        # Parse Sovereign flag if present
        inputExplicit: bool | None = None
        if "chip_io" in d and isinstance(d["chip_io"], dict):
            cio: dict = d["chip_io"]
            if "input" in cio and isinstance(cio["input"], dict):
                cin: dict = cio["input"]
                if "explicit" in cin:
                    inputExplicit = bool(cin["explicit"])

        if key in registry:
            node = registry[key]
            # Merge port definitions if new ones found
            newInputs: list[Port] = _get_ports(d, "input")
            newOutputs: list[Port] = _get_ports(d, "output")
            if len(newInputs) > len(node.unbound_inputs):
                node.unbound_inputs = newInputs
            if len(newOutputs) > len(node.unbound_outputs):
                node.unbound_outputs = newOutputs
            if not node.internal_wiring and "internal_wiring" in d:
                node.internal_wiring = d["internal_wiring"]
            if node.inputExplicit is None:
                node.inputExplicit = inputExplicit
        else:
            node = cls(
                module=d["module"],
                func=d["func"],
                internal_wiring=d.get("internal_wiring", []),
                unbound_inputs=_get_ports(d, "input"),
                unbound_outputs=_get_ports(d, "output"),
                inputExplicit=inputExplicit,
            )
            registry[key] = node

        # Process children
        childIdx: int
        cDict: dict
        for childIdx, cDict in enumerate(d.get("calls", [])):
            child: Node = cls.node_fromDict(
                cDict, registry, isRoot=False, portCounters=portCounters
            )

            if child not in node.children:
                node.children.append(child)

            # Bind Child's Input Port
            # Unique sequential counter per chip: distinct lanes for shared Hubs
            cKey: str = f"{child.module}:{child.func}"
            currentInIdx: int = portCounters.get(cKey, 0)

            localInputs: list[Port] = _get_ports(cDict, "input")
            if localInputs:
                child.input_ports[id(node)] = localInputs[0]
            elif currentInIdx < len(child.unbound_inputs):
                child.input_ports[id(node)] = child.unbound_inputs[currentInIdx]
            elif id(node) not in child.input_ports:
                child.input_ports[id(node)] = Port()

            portCounters[cKey] = currentInIdx + 1

            # Bind Parent's Output Port
            if childIdx < len(node.unbound_outputs):
                node.output_ports[id(child)] = node.unbound_outputs[childIdx]
            else:
                node.output_ports[id(child)] = Port()

        return node
