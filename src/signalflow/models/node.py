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
    """One function call in the recursive call tree.

    Attributes:
        module:        Module/file owning this function.
        func:          Function label shown in the chip.
        input_ports:   List of entry ports on the LEFT wall.
        output_ports:  List of exit ports on the RIGHT wall.
        children:      Ordered child calls (DFS left-to-right).
        col:           Call depth (set by col_assign).
        x, y:          Canvas top-left of chip (set by layout_compute).
        chip_h:        Chip height in canvas rows (set by layout_compute).
        is_root:       True for the tree root (no parent).
        entry_row:     Canvas row where the first forward wire enters.
        return_row:    Canvas row where the final return wire exits.
    """
    module:        str
    func:          str
    input_ports:   list[Port] = field(default_factory=list)
    output_ports:  list[Port] = field(default_factory=list)
    children:      list = field(default_factory=list)
    col:        int  = 0
    x:          int  = 0
    y:          int  = 0
    chip_h:     int  = BASE_LEAF
    is_root:    bool = False
    entry_row:  int  = 0
    return_row: int  = 0

    @classmethod
    def node_fromDict(cls, d: dict) -> Node:
        """Deserialise a recursive call-tree dict into a Node tree."""
        children = [cls.node_fromDict(c) for c in d.get('calls', [])]

        # Parse ports, falling back to legacy single fields for migration ease
        inputs = []
        if 'input_ports' in d:
            inputs = [Port(p.get('signal'), p.get('return')) for p in d['input_ports']]
        elif d.get('input_signal') or d.get('input_return'):
            inputs = [Port(d.get('input_signal'), d.get('input_return'))]

        outputs = []
        if 'output_ports' in d:
            outputs = [Port(p.get('signal'), p.get('return')) for p in d['output_ports']]
        elif d.get('output_signal') or d.get('output_return'):
            outputs = [Port(d.get('output_signal'), d.get('output_return'))]

        return cls(
            module=d['module'],
            func=d['func'],
            input_ports=inputs,
            output_ports=outputs,
            children=children,
        )
