"""SignalFlow symbolic notation package."""

from signalflow.models.result import (
    Result,
    result_isErrCheck,
    result_isOkCheck,
    resultErr_build,
    resultOk_build,
)
from signalflow.notation.path import (
    WTE_INTRA_FORWARD,
    WTE_INTRA_RETURN,
    WTE_OUTER_EASTBOUND_ARC,
    WTE_OUTER_EASTRETURN_UTURN,
    WTE_OUTER_EASTSIGNAL_UTURN,
    WTE_OUTER_WESTBOUND_ARC,
    WTE_OUTER_WESTRETURN_UTURN,
    WTE_OUTER_WESTSIGNAL_UTURN,
    AlgebraicPath,
    LaneSense,
    PathHop,
    PathSolutionBuilder,
    WiringSolution,
)
from signalflow.notation.sfn import sfN

__all__ = [
    "AlgebraicPath",
    "LaneSense",
    "PathHop",
    "PathSolutionBuilder",
    "Result",
    "WTE_INTRA_FORWARD",
    "WTE_INTRA_RETURN",
    "WTE_OUTER_EASTBOUND_ARC",
    "WTE_OUTER_EASTRETURN_UTURN",
    "WTE_OUTER_EASTSIGNAL_UTURN",
    "WTE_OUTER_WESTBOUND_ARC",
    "WTE_OUTER_WESTRETURN_UTURN",
    "WTE_OUTER_WESTSIGNAL_UTURN",
    "WiringSolution",
    "result_isErrCheck",
    "result_isOkCheck",
    "resultErr_build",
    "resultOk_build",
    "sfN",
]
