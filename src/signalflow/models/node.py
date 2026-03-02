"""Graph node model: functional units, ports, and geometry (RPN Naming)."""
from __future__ import annotations

# Standard library
from dataclasses import dataclass, field
from typing import Optional

# Local
from signalflow.config import config


@dataclass
class Port:
    """Represents a named entry/exit point on a functional unit."""
    signal: Optional[str] = None
    ret:    Optional[str] = None


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
        chip_h: Total height of the chip in rows.
        col: Assigned column index in the diagram.
        entry_row: Global row for the primary entry signal.
        return_row: Global row for the primary return signal.
        entry_rows: Map of parent_id -> specific entry row.
        return_rows: Map of parent_id -> specific return row.
    """
    module: str
    func:   str
    children:        list[Node] = field(default_factory=list)
    input_ports:     dict[int, Port] = field(default_factory=dict)
    output_ports:    dict[int, Port] = field(default_factory=dict)
    unbound_inputs:  list[Port] = field(default_factory=list)
    unbound_outputs: list[Port] = field(default_factory=list)
    internal_wiring: list[str] = field(default_factory=list)

    # Geometry (set by layout_compute)
    x:          int  = 0
    y:          int  = 0
    ow:         int  = 0
    chip_h:     int  = 0
    col:        int  = 0
    entry_row:  int  = 0
    return_row: int  = 0
    entry_rows:  dict[int, int] = field(default_factory=dict)
    return_rows: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.chip_h == 0:
            self.chip_h = config.baseLeafHeight

    @property
    def is_root(self) -> bool:
        """True if this node has no parents (assigned by the factory)."""
        return not self.input_ports

    @classmethod
    def node_fromDict(cls, d: dict, registry: dict[str, Node] | None = None, 
                      is_root: bool = True, port_counters: dict[str, int] | None = None) -> Node:
        """Deserialise call-tree dict into a unique-chip Graph with smart port binding."""
        if registry is None: registry = {}
        if port_counters is None: port_counters = {}
        
        def _get_ports(data, key_prefix):
            ports = []
            p_list = data.get(f'{key_prefix}_ports')
            if p_list:
                ports = [Port(p.get('signal'), p.get('return')) for p in p_list]
            elif data.get(f'{key_prefix}_signal') or data.get(f'{key_prefix}_return'):
                ports = [Port(data.get(f'{key_prefix}_signal'), data.get(f'{key_prefix}_return'))]
            return ports

        # Chip Canonicalization
        key = f"{d['module']}:{d['func']}"
        if key in registry:
            node = registry[key]
            # Merge port definitions if new ones found
            new_inputs  = _get_ports(d, 'input')
            new_outputs = _get_ports(d, 'output')
            if len(new_inputs)  > len(node.unbound_inputs):  node.unbound_inputs  = new_inputs
            if len(new_outputs) > len(node.unbound_outputs): node.unbound_outputs = new_outputs
            if not node.internal_wiring and 'internal_wiring' in d:
                node.internal_wiring = d['internal_wiring']
        else:
            node = cls(
                module=d['module'], 
                func=d['func'], 
                internal_wiring=d.get('internal_wiring', []),
                unbound_inputs=_get_ports(d, 'input'),
                unbound_outputs=_get_ports(d, 'output')
            )
            registry[key] = node

        # Process children
        for c_dict in d.get('calls', []):
            child = cls.node_fromDict(c_dict, registry, is_root=False, port_counters=port_counters)
            
            if child not in node.children:
                node.children.append(child)

            # Bind Child's Input Port
            # Use unique sequential counter per chip to ensure distinct lanes for shared Hubs
            c_key = f"{child.module}:{child.func}"
            current_in_idx = port_counters.get(c_key, 0)
            
            local_inputs = _get_ports(c_dict, 'input')
            if local_inputs:
                child.input_ports[id(node)] = local_inputs[0]
            elif current_in_idx < len(child.unbound_inputs):
                child.input_ports[id(node)] = child.unbound_inputs[current_in_idx]
            elif id(node) not in child.input_ports:
                child.input_ports[id(node)] = Port()
            
            port_counters[c_key] = current_in_idx + 1
            
            # Bind Parent's Output Port
            child_idx = d.get('calls', []).index(c_dict)
            if child_idx < len(node.unbound_outputs):
                node.output_ports[id(child)] = node.unbound_outputs[child_idx]
            else:
                node.output_ports[id(child)] = Port()

        return node
