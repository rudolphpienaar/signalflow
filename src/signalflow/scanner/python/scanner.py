"""Python AST Scanner (RPN Naming Convention)."""

import ast
from signalflow.scanner.base import BaseScanner

class PythonScanner(BaseScanner):
    """Scans Python source code using the AST module."""

    def source_scan(self, source: str):
        """RPN: source_scan - Traverse the AST and extract call edges."""
        tree = ast.parse(source)
        self.AST_visit(tree)

    def AST_visit(self, node):
        """RPN: AST_visit - Recursive stateful visitor."""
        current_func = None
        
        for n in ast.walk(node):
            if isinstance(n, ast.FunctionDef):
                current_func = n.name
            
            # Pattern: r1 = p1("s1")
            if isinstance(n, ast.Assign) and current_func:
                if isinstance(n.value, ast.Call) and isinstance(n.targets[0], ast.Name):
                    self.call_extract(n.value, n.targets[0].id, current_func)

    def call_extract(self, call_node, return_var, caller_name):
        """RPN: call_extract - Map a call site to a netlist edge."""
        # Extract child name
        if isinstance(call_node.func, ast.Name):
            child_name = call_node.func.id
            
            # Extract first arg as signal
            arg_val = None
            if call_node.args and isinstance(call_node.args[0], ast.Constant):
                arg_val = str(call_node.args[0].value)
            
            edge = {
                "caller": f"{self.module}:{caller_name}",
                "child":  child_name,
                "arg":    arg_val,
                "ret":    return_var
            }
            self.netlist.append(edge)

    def netlist_get(self) -> list[dict]:
        """RPN: netlist_get - Return the extracted edges."""
        return self.netlist
