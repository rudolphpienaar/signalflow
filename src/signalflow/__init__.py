"""SignalFlow package root for the re-architecture transition.

The top-level `signalflow` namespace is now reserved for the new architecture.
The pre-existing implementation lives under `signalflow.legacy` as an explicit
compatibility and reference tree. New subsystems should be added at the package
top level rather than under `signalflow.legacy`.
"""

__version__ = "5.9.6"
