"""Node dataclass representing one function call in the call tree."""

from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.config import BASE_LEAF


@dataclass
class Port:
    """A call/return signal pair for one entry or exit point."""
    signal: str | None = None
    ret:    str | None = None


@dataclass
class Node:
    """One function chip in the signal flow graph.

    Each unique module:func pair appears exactly once. A 'Hub' node is
    called by multiple parents.

    Attributes:
        module:        Module/file owning this function.
        func:          Function label shown in the chip.
        input_ports:   Map of parent_id -> Port (on LEFT wall).
        output_ports:  Map of child_id  -> Port (on RIGHT wall).
        children:      Ordered unique child nodes (outgoing).
        parents:       Unique parent nodes (incoming).
        col:           Call depth (max depth across all call paths).
        x, y:          Canvas top-left of chip.
        chip_h:        Chip height (scaled to fit all ports).
        is_root:       True for the entry-point node.
        entry_rows:    Map of parent_id -> canvas row index.
        return_rows:   Map of parent_id -> canvas row index.
    """
    module:        str
    func:          str
    input_ports:      dict[int, Port] = field(default_factory=dict)
    output_ports:     dict[int, Port] = field(default_factory=dict)
    unbound_inputs:   list[Port] = field(default_factory=list)
    unbound_outputs:  list[Port] = field(default_factory=list)
    children:         list[Node] = field(default_factory=list)
    parents:       list[Node] = field(default_factory=list)
    col:        int  = 0
    x:          int  = 0
    y:          int  = 0
    ow:         int  = 0
    chip_h:     int  = BASE_LEAF
    is_root:    bool = False
    entry_rows:  dict[int, int] = field(default_factory=dict)
    return_rows: dict[int, int] = field(default_factory=dict)
    internal_wiring: list[str] = field(default_factory=list)

    @classmethod
    def node_fromDict(cls, d: dict, registry: dict[str, Node] | None = None, 
                      is_root: bool = True, port_counters: dict[str, int] | None = None) -> Node:
        """Deserialise call-tree dict into a unique-chip Graph with smart port binding."""
        if registry is None: registry = {}
        if port_counters is None: port_counters = {}
        
        def _get_ports(data, key_prefix):
            ports = []
            p_list = data.get(f'{key_prefix}_ports', [])
            if p_list:
                ports = [Port(p.get('signal'), p.get('return')) for p in p_list]
            elif data.get(f'{key_prefix}_signal') or data.get(f'{key_prefix}_return'):
                ports = [Port(data.get(f'{key_prefix}_signal'), data.get(f'{key_prefix}_return'))]
            return ports

        key = f"{d['module']}:{d['func']}"
        if key in registry:
            node = registry[key]
            # Accumulate port definitions from this new context if provided
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

        # Handle Root entry ports (only for the actual entry point)
        if is_root:
            node.is_root = True
            if node.unbound_inputs:
                node.input_ports[0] = node.unbound_inputs[0]

        # Process children
        for c_dict in d.get('calls', []):
            child = cls.node_fromDict(c_dict, registry, is_root=False, port_counters=port_counters)
            
            if child not in node.children:
                node.children.append(child)
            if node not in child.parents:
                child.parents.append(node)

            # Bind Child's Input Port
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
            elif id(child) not in node.output_ports:
                node.output_ports[id(child)] = Port()

        return node
