"""Tests for the SignalFlow scanner (transcompiler)."""

from signalflow.scanner.python.scanner import PythonScanner


def test_python_simple_call_extract():
    """TDD: Extract a simple call from a Python function snippet."""
    source = """
def main():
    r1 = p1("s1")
"""
    scanner = PythonScanner(module="test.py")
    scanner.source_scan(source)
    netlist = scanner.netlist_get()

    assert len(netlist) == 1
    edge = netlist[0]
    assert edge['caller'] == "test.py:main"
    assert edge['child']  == "p1"
    assert edge['arg']    == "s1"
    assert edge['ret']    == "r1"
