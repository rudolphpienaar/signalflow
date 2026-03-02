"""Base Scanner Interface (RPN Naming Convention)."""

from abc import ABC, abstractmethod

class BaseScanner(ABC):
    """Abstract base for language-specific AST scanners."""

    def __init__(self, module: str):
        self.module = module
        self.netlist = []

    @abstractmethod
    def source_scan(self, source: str):
        """RPN: source_scan - High-level entry point to scan raw source."""
        pass

    @abstractmethod
    def netlist_get(self) -> list[dict]:
        """RPN: netlist_get - Return the current formal IR (list of edges)."""
        pass
