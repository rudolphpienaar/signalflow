"""Node dataclass representing one function call in the call tree."""

from __future__ import annotations

from dataclasses import dataclass, field

from signalflow.config import BASE_LEAF


@dataclass
class Node:
    """One function call in the recursive call tree.

    Attributes:
        module:        Module/file owning this function.
        func:          Function label shown in the chip.
        input_signal:  Label flush on LEFT of func on input from parent.
        input_return:  Label flush on LEFT of func on return to parent.
        output_signal: Label flush on RIGHT on output to first child.
        output_return: Label flush on RIGHT on receipt from last child.
        children:      Ordered child calls (DFS left-to-right).
        col:           Call depth (set by col_assign).
        x, y:          Canvas top-left of chip (set by layout_compute).
        chip_h:        Chip height in canvas rows (set by layout_compute).
        is_root:       True for the tree root (no parent).
        entry_row:     Canvas row where the forward wire enters the chip's left border.
        return_row:    Canvas row where the return wire exits the chip's left border.
    """
    module:        str
    func:          str
    input_signal:  str | None = None
    input_return:  str | None = None
    output_signal: str | None = None
    output_return: str | None = None
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
        return cls(
            module=d['module'],
            func=d['func'],
            input_signal=d.get('input_signal'),
            input_return=d.get('input_return'),
            output_signal=d.get('output_signal'),
            output_return=d.get('output_return'),
            children=children,
        )
