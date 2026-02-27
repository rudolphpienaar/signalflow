"""ModuleBox dataclass: single double-line container for same-module chips."""

from dataclasses import dataclass


@dataclass
class ModuleBox:
    """Single double-line outer container for same-module chips.

    Attributes:
        label:           Module name shown in the top border.
        ox0, oy0:        Box canvas top-left corner (inclusive).
        ox1, oy1:        Box canvas bottom-right corner (inclusive).
    """
    label: str
    ox0:   int = 0
    oy0:   int = 0
    ox1:   int = 0
    oy1:   int = 0
