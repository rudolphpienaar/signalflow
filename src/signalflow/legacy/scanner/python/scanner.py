"""Python AST Scanner (RPN Naming Convention)."""

import ast

from signalflow.legacy.scanner.base import BaseScanner


class PythonScanner(BaseScanner):
    """Scans Python source code using the AST module."""

    def source_scan(self, source: str) -> None:
        """RPN: source_scan - Traverse the AST and extract call edges."""
        tree: ast.AST = ast.parse(source)
        self.AST_visit(tree)

    def AST_visit(self, node: ast.AST) -> None:
        """RPN: AST_visit - Recursive stateful visitor."""
        currentFunc: str | None = None

        n: ast.AST
        for n in ast.walk(node):
            if isinstance(n, ast.FunctionDef):
                currentFunc = n.name

            # Pattern: r1 = p1("s1")
            if (
                isinstance(n, ast.Assign)
                and currentFunc
                and isinstance(n.value, ast.Call)
                and isinstance(n.targets[0], ast.Name)
            ):
                self.call_extract(n.value, n.targets[0].id, currentFunc)

    def call_extract(
        self, callNode: ast.Call, returnVar: str, callerName: str
    ) -> None:
        """RPN: call_extract - Map a call site to a netlist edge."""
        # Extract child name
        if isinstance(callNode.func, ast.Name):
            childName: str = callNode.func.id

            # Extract first arg as signal
            argVal: str | None = None
            if callNode.args and isinstance(callNode.args[0], ast.Constant):
                argVal = str(callNode.args[0].value)

            edge: dict[str, str | None] = {
                "caller": f"{self.module}:{callerName}",
                "child": childName,
                "arg": argVal,
                "ret": returnVar,
            }
            self.netlist.append(edge)

    def netlist_get(self) -> list[dict]:
        """RPN: netlist_get - Return the extracted edges."""
        return self.netlist
