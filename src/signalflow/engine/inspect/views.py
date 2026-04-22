"""Inspect view/display helpers and surface re-exports."""

from __future__ import annotations

import builtins
import os
import re
import sys
from dataclasses import dataclass, is_dataclass
from pprint import pformat
from typing import TYPE_CHECKING

from signalflow.board import BoardChip
from signalflow.models import (
    ChipId,
    Diagnostic,
    GridCoord,
    RoutingZoneId,
    callingStackResult_buildFromCircuitDocument,
    result_isOkCheck,
)

from .chip_helpers import _chipHandle_build, _chipTitleText_build
from .context import DebugWorkflowView, SignalFlowContext, WorkflowView
from .geometry import (
    _gridText_build,
    _interconnectDrawingText_build,
    _interconnectSummaryText_build,
    _interconnectWorldCanvasText_build,
    _worldCanvasText_build,
    _worldDrawText_build,
    _zoneDrawingLines_build,
    _zoneRoutesText_build,
    _zoneSummaryText_build,
)
from .kernel_runtime import _boardZoneRuntime_build
from .manual import MANUAL_BY_TOPIC
from .terminal import (
    ANSI_BLUE as _ANSI_BLUE,
)
from .terminal import (
    ANSI_BOLD as _ANSI_BOLD,
)
from .terminal import (
    ANSI_CYAN as _ANSI_CYAN,
)
from .terminal import (
    ANSI_DIM as _ANSI_DIM,
)
from .terminal import (
    ANSI_GREEN as _ANSI_GREEN,
)
from .terminal import (
    ANSI_MAGENTA as _ANSI_MAGENTA,
)
from .terminal import (
    ANSI_RED as _ANSI_RED,
)
from .terminal import (
    ANSI_RESET as _ANSI_RESET,
)
from .terminal import (
    ANSI_WHITE as _ANSI_WHITE,
)
from .terminal import (
    ANSI_YELLOW as _ANSI_YELLOW,
)

if TYPE_CHECKING:
    from .surfaces import ChipView


def _summary_print(text: str) -> None:
    from .repl import _summary_print as _impl

    _impl(text)


def _colorEnabled_check() -> bool:
    """Return whether ANSI coloring should be emitted."""

    return os.environ.get("NO_COLOR") is None


def _ansiWrap_build(text: str, *ansiCodes: str) -> str:
    """Wrap one text fragment in ANSI styles when color is enabled."""

    if not _colorEnabled_check():
        return text
    return f"{''.join(ansiCodes)}{text}{_ANSI_RESET}"


def ls(obj=None) -> None:
    """List the navigable surface of any debug object."""

    if obj is None:
        print(_ansiWrap_build("top-level REPL names", _ANSI_BOLD, _ANSI_CYAN))
        print(
            _ansiWrap_build(
                "  use ls(name) on any of these to explore further", _ANSI_DIM
            )
        )
        return

    try:
        names: list[str] = [n for n in obj.__dir__() if not n.startswith("_")]
    except Exception:
        names = [n for n in dir(obj) if not n.startswith("_")]

    if not names:
        print(
            _ansiWrap_build(
                f"  (no public surface on {type(obj).__name__})", _ANSI_DIM
            )
        )
        return

    typeName: str = type(obj).__name__
    print(
        _ansiWrap_build(repr(obj), _ANSI_BOLD, _ANSI_CYAN)
        + "  "
        + _ansiWrap_build(f"[{typeName}]", _ANSI_DIM)
    )

    maxLen: int = max(len(n) for n in names)
    for name in names:
        attr = getattr(obj, name, None)
        if attr is None:
            docLine: str = ""
        elif callable(attr):
            rawDoc: str = getattr(attr, "__doc__", "") or ""
            docLine = rawDoc.strip().split("\n")[0]
        else:
            docLine = repr(attr)

        paddedName: str = name.ljust(maxLen)
        print(
            "  "
            + _ansiWrap_build(paddedName, _ANSI_MAGENTA)
            + "  "
            + _ansiWrap_build(docLine[:72], _ANSI_DIM)
        )


def tree(
    obj=None, _depth: int = 2, _prefix: str = "", _label: str = ""
) -> None:
    """Recursively show the navigable subtree of any debug object."""

    if obj is None:
        print(
            _ansiWrap_build(
                "pass an object to tree(), e.g. tree(chips)", _ANSI_DIM
            )
        )
        return

    label: str = _label or repr(obj)
    print(_prefix + _ansiWrap_build(label, _ANSI_BOLD, _ANSI_CYAN))

    if _depth <= 0:
        print(_prefix + "  " + _ansiWrap_build("...", _ANSI_DIM))
        return

    try:
        names: list[str] = [n for n in obj.__dir__() if not n.startswith("_")]
    except Exception:
        names = [n for n in dir(obj) if not n.startswith("_")]

    for name in names:
        attr = getattr(obj, name, None)
        if attr is None:
            continue
        if callable(attr):
            rawDoc: str = getattr(attr, "__doc__", "") or ""
            docLine: str = rawDoc.strip().split("\n")[0][:60]
            print(
                _prefix
                + "  "
                + _ansiWrap_build(name + "()", _ANSI_MAGENTA)
                + "  "
                + _ansiWrap_build(docLine, _ANSI_DIM)
            )
        else:
            childLabel: str = f"{name} = {repr(attr)[:60]}"
            if hasattr(attr, "__dir__") and not isinstance(
                attr, (str, int, float, bool, type(None))
            ):
                tree(
                    attr,
                    _depth=_depth - 1,
                    _prefix=_prefix + "  ",
                    _label=childLabel,
                )
            else:
                print(
                    _prefix + "  " + _ansiWrap_build(childLabel, _ANSI_WHITE)
                )


def _manual_print(topic: str | None = None) -> None:
    """Print a topic-focused manual for the debug REPL surface."""

    resolvedTopic: str = "general" if topic is None else topic
    manualLines = MANUAL_BY_TOPIC.get(
        resolvedTopic, MANUAL_BY_TOPIC["general"]
    )

    colorizedLines: list[str] = []
    for line in manualLines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if not stripped:
            colorizedLines.append("")
        elif indent == "" and not stripped.startswith("#"):
            colorizedLines.append(
                _ansiWrap_build(line, _ANSI_BOLD, _ANSI_CYAN)
            )
        elif stripped.startswith("#"):
            colorizedLines.append(_ansiWrap_build(line, _ANSI_DIM))
        elif (
            stripped.startswith("workflows.")
            or stripped.startswith("chips.")
            or stripped.startswith("chip.")
            or stripped.startswith("zones.")
            or stripped.startswith("zone.")
            or stripped.startswith("world.")
            or stripped.startswith("calls.")
            or stripped.startswith("routes.")
            or stripped.startswith("interconnects.")
            or stripped.startswith("ic.")
            or stripped.startswith("document.")
            or stripped.startswith("circuit.")
            or stripped.startswith("config.")
            or stripped.startswith("ls(")
            or stripped.startswith("tree(")
        ):
            if "  #" in line:
                codePart, commentPart = line.split("  #", 1)
                colorizedLines.append(
                    _ansiWrap_build(codePart, _ANSI_MAGENTA)
                    + _ansiWrap_build("  #" + commentPart, _ANSI_DIM)
                )
            else:
                colorizedLines.append(_ansiWrap_build(line, _ANSI_MAGENTA))
        else:
            colorizedLines.append(line)

    print("\n".join(colorizedLines))


def _displayHook_configure() -> None:
    """Install the debugger display hook for interactive expression results."""

    sys.displayhook = _displayHook_render


def _displayHook_restore(previousDisplayHook) -> None:
    """Restore the previous Python display hook after leaving the REPL."""

    sys.displayhook = previousDisplayHook


def _displayHook_render(value) -> None:
    """Render one interactive expression result with debugger color policy."""

    if value is None:
        return
    builtins.__dict__["_"] = value
    print(_displayText_build(value))


def _displayText_build(value) -> str:
    """Build colorized interactive output for one Python value."""

    baseText: str = pformat(value, sort_dicts=False)
    if isinstance(value, str):
        if "\n" in value:
            return _ansiWrap_build(value, _ANSI_YELLOW)
        return _ansiWrap_build(baseText, _ANSI_YELLOW)
    if callable(value):
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_MAGENTA)
    if isinstance(value, type):
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_BLUE)
    if isinstance(value, bool):
        return _ansiWrap_build(
            baseText,
            _ANSI_BOLD,
            _ANSI_GREEN if value else _ANSI_RED,
        )
    if isinstance(value, (int, float)):
        return _ansiWrap_build(baseText, _ANSI_GREEN)
    if is_dataclass(value):
        return _ansiWrap_build(baseText, _ANSI_CYAN)
    if value.__class__.__name__ == "ResultOk":
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_GREEN)
    if value.__class__.__name__ == "ResultErr":
        return _ansiWrap_build(baseText, _ANSI_BOLD, _ANSI_RED)
    if isinstance(value, dict):
        return _reprSyntaxColorize_build(
            baseText, defaultAnsiCodes=(_ANSI_BLUE,)
        )
    if isinstance(value, (tuple, list, set, frozenset)):
        return _reprSyntaxColorize_build(
            baseText, defaultAnsiCodes=(_ANSI_WHITE,)
        )
    return _reprSyntaxColorize_build(baseText, defaultAnsiCodes=(_ANSI_CYAN,))


def _reprSyntaxColorize_build(
    text: str,
    *,
    defaultAnsiCodes: tuple[str, ...],
) -> str:
    """Colorize a repr-like text buffer by simple token class."""

    tokenPattern = re.compile(
        r"""
        (?P<string>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")
        |(?P<number>\b-?\d+(?:\.\d+)?\b)
        |(?P<boolnone>\bTrue\b|\bFalse\b|\bNone\b)
        |(?P<identifier>\b[A-Za-z_][A-Za-z0-9_]*\b)
        |(?P<operator>[=])
        |(?P<punct>[()\[\]{}:,])
        """,
        re.VERBOSE,
    )

    pieces: list[str] = []
    lastEnd: int = 0
    match: re.Match[str] | None
    for match in tokenPattern.finditer(text):
        if match.start() > lastEnd:
            pieces.append(
                _ansiWrap_build(
                    text[lastEnd : match.start()], *defaultAnsiCodes
                )
            )
        tokenText = match.group(0)
        if match.lastgroup == "string":
            pieces.append(_ansiWrap_build(tokenText, _ANSI_YELLOW))
        elif match.lastgroup == "number":
            pieces.append(_ansiWrap_build(tokenText, _ANSI_GREEN))
        elif match.lastgroup == "boolnone":
            if tokenText == "False":
                pieces.append(
                    _ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_RED)
                )
            elif tokenText == "True":
                pieces.append(
                    _ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_GREEN)
                )
            else:
                pieces.append(_ansiWrap_build(tokenText, _ANSI_DIM))
        elif match.lastgroup == "identifier":
            nextIndex = match.end()
            nextChar = text[nextIndex : nextIndex + 1]
            if nextChar == "(":
                pieces.append(
                    _ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_CYAN)
                )
            elif nextChar == "=":
                pieces.append(
                    _ansiWrap_build(tokenText, _ANSI_BOLD, _ANSI_GREEN)
                )
            else:
                pieces.append(_ansiWrap_build(tokenText, *defaultAnsiCodes))
        elif match.lastgroup == "operator":
            pieces.append(_ansiWrap_build(tokenText, _ANSI_DIM))
        else:
            pieces.append(_ansiWrap_build(tokenText, _ANSI_DIM))
        lastEnd = match.end()
    if lastEnd < len(text):
        pieces.append(_ansiWrap_build(text[lastEnd:], *defaultAnsiCodes))
    return "".join(pieces)


def _summaryTextColorize_build(text: str) -> str:
    """Colorize one structured summary block for REPL printing."""

    colorizedLines: list[str] = []
    inDrawBlock: bool = False
    line: str
    for line in text.splitlines():
        strippedLine: str = line.strip()
        if not strippedLine:
            colorizedLines.append(line)
            continue
        if not line.startswith(" "):
            colorizedLines.append(
                _ansiWrap_build(line, _ANSI_BOLD, _ANSI_CYAN)
            )
            inDrawBlock = False
            continue
        if inDrawBlock and line.startswith("    "):
            colorizedLines.append(_ansiWrap_build(line, _ANSI_YELLOW))
            continue

        indentation: str = line[: len(line) - len(line.lstrip(" "))]
        body: str = line[len(indentation) :]
        if body.endswith(":"):
            colorizedLines.append(
                f"{indentation}"
                f"{_ansiWrap_build(body, _ANSI_BOLD, _ANSI_GREEN)}"
            )
            inDrawBlock = body == "draw:"
            continue
        if ":" in body:
            label, valueText = body.split(":", 1)
            colorizedLines.append(
                f"{indentation}"
                f"{_ansiWrap_build(label + ':', _ANSI_BOLD, _ANSI_GREEN)}"
                f"{_ansiWrap_build(valueText, _ANSI_WHITE)}"
            )
            inDrawBlock = False
            continue
        if body.startswith("- "):
            colorizedLines.append(
                f"{indentation}{_ansiWrap_build(body, _ANSI_WHITE)}"
            )
            inDrawBlock = False
            continue
        colorizedLines.append(_ansiWrap_build(line, _ANSI_WHITE))
        inDrawBlock = False
    return "\n".join(colorizedLines)


def _diagnosticLine_build(diagnostic: Diagnostic) -> str:
    """Build one colorized diagnostic output line."""

    contextSuffix: str = ""
    if diagnostic.context:
        contextSuffix = _ansiWrap_build(
            f" context={diagnostic.context}",
            _ANSI_DIM,
        )
    if diagnostic.level.value == "error":
        levelText = _ansiWrap_build(
            diagnostic.level.value, _ANSI_BOLD, _ANSI_RED
        )
    else:
        levelText = _ansiWrap_build(
            diagnostic.level.value, _ANSI_BOLD, _ANSI_YELLOW
        )
    phaseText = _ansiWrap_build(diagnostic.phase.value, _ANSI_CYAN)
    codeText = _ansiWrap_build(diagnostic.code, _ANSI_GREEN)
    return (
        f"{levelText}:{phaseText}:{codeText}: "
        f"{diagnostic.message}{contextSuffix}"
    )


@dataclass(frozen=True)
class DocumentView:
    """Interactive inspection view over the loaded source document."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "callCount_get",
            "callingDepth_get",
            "chipCount_get",
            "raw_get",
            "root_get",
            "title_get",
        ]

    def __repr__(self) -> str:
        return "<document>"

    def raw_get(self):
        return self.debugContext.documentDict

    def title_get(self) -> str:
        return self.debugContext.circuitDocument.title

    def root_get(self) -> BoardChip:
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=self.debugContext.circuitDocument.rootChipRef.chipId,
        )

    def callingDepth_get(self) -> int:
        callingStackResult = callingStackResult_buildFromCircuitDocument(
            self.debugContext.circuitDocument
        )
        if not result_isOkCheck(callingStackResult):
            return 0
        return callingStackResult.value.bandCount_calculate()

    def chipCount_get(self) -> int:
        return self.debugContext.chipCount_get()

    def callCount_get(self) -> int:
        return len(self.debugContext.calls_getAll())


@dataclass(frozen=True)
class CircuitView:
    """Interactive inspection view over the validated circuit graph."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "callCount_get",
            "calls_get",
            "chipCount_get",
            "chips_get",
            "raw_get",
            "root_get",
            "title_get",
        ]

    def __repr__(self) -> str:
        return "<circuit>"

    def raw_get(self):
        return self.debugContext.circuitDocument

    def title_get(self) -> str:
        return self.debugContext.circuitDocument.title

    def root_get(self) -> BoardChip:
        return _chipHandle_build(
            debugContext=self.debugContext,
            chipId=self.debugContext.circuitDocument.rootChipRef.chipId,
        )

    def chips_get(self) -> ChipView:
        return self.debugContext.chips

    def calls_get(self) -> CallView:
        return self.debugContext.calls

    def chipCount_get(self) -> int:
        return self.debugContext.chipCount_get()

    def callCount_get(self) -> int:
        return len(self.debugContext.calls_getAll())


@dataclass(frozen=True)
class ConfigView:
    """Interactive inspection view over validated application config."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "channelSense_get",
            "gridSize_get",
            "interconnectCount_get",
            "moduleBoxPadding_get",
            "occupancyPolicy_get",
            "packingPolicy_get",
            "pathPolicy_get",
            "raw_get",
            "sense_get",
            "zoneCount_get",
        ]

    def __repr__(self) -> str:
        return "<config>"

    def raw_get(self):
        return self.debugContext.signalFlowConfig

    def sense_get(self) -> str:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .worldSense
            .value
        )

    def gridSize_get(self) -> GridCoord:
        dimensions = (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .routingZoneGridDimensions
        )
        return GridCoord(
            columnIndex=dimensions.columnCount,
            rowIndex=dimensions.rowCount,
        )

    def zoneCount_get(self) -> int:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .routingZoneCount_calculate()
        )

    def interconnectCount_get(self) -> int:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .routingZoneInterconnectCount_calculate()
        )

    def moduleBoxPadding_get(self) -> int:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .moduleBoxPadding
        )

    def pathPolicy_get(self) -> str:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .pathPolicy
            .value
        )

    def channelSense_get(self) -> str:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .channelSense
            .value
        )

    def occupancyPolicy_get(self) -> str:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .occupancyPolicy
            .value
        )

    def packingPolicy_get(self) -> str:
        return (
            self.debugContext
            .signalFlowConfig
            .routingZoneGridConfig
            .packingPolicy
            .value
        )


@dataclass(frozen=True)
class TopologyGridView:
    """Interactive inspection view over the unplaced topology grid."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "compatibilityInterconnectAt_get",
            "compatibilityInterconnectCount_get",
            "raw_get",
            "size_get",
            "zoneAt_get",
            "zoneCount_get",
        ]

    def __repr__(self) -> str:
        return "<grid>"

    def raw_get(self):
        return self.debugContext.routingZoneGrid

    def size_get(self) -> GridCoord:
        return self.debugContext.routingGridSize_get()

    def zoneCount_get(self) -> int:
        return self.debugContext.routingZoneCount_get()

    def compatibilityInterconnectCount_get(self) -> int:
        return self.debugContext.interconnectCount_get()

    def interconnectCount_get(self) -> int:
        return self.compatibilityInterconnectCount_get()

    def zoneAt_get(self, columnIndex: int, rowIndex: int):
        return self.debugContext.routingZoneAtCoordResult_get(
            GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
        )

    def compatibilityInterconnectAt_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        return self.debugContext.routingInterconnectAtCoordsResult_get(
            sourceGridCoord=GridCoord(
                columnIndex=sourceColumnIndex,
                rowIndex=sourceRowIndex,
            ),
            destinationGridCoord=GridCoord(
                columnIndex=destinationColumnIndex,
                rowIndex=destinationRowIndex,
            ),
        )

    def interconnectAt_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        return self.compatibilityInterconnectAt_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )


@dataclass(frozen=True)
class AssignmentView:
    """Interactive inspection view over circuit-to-zone assignments."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "all_get",
            "count_get",
            "forChip_get",
            "forZone_get",
            "raw_get",
            "summary_text",
        ]

    def __repr__(self) -> str:
        return "<assignment>"

    def raw_get(self):
        return self.debugContext.routingZoneAssignmentSet

    def all_get(self):
        return self.debugContext.routingZoneAssignments_getAll()

    def count_get(self) -> int:
        return len(self.all_get())

    def forChip_get(self, moduleName: str, functionName: str):
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        return self.debugContext.assignmentForChipResult_get(chipId)

    def forZone_get(self, columnIndex: int, rowIndex: int):
        routingZoneId = RoutingZoneId(
            id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
        )
        return self.debugContext.assignmentsForZone_get(routingZoneId)

    def summary_sprint(self) -> str:
        lines = ["assignment"]
        for assignment in self.all_get():
            lines.append(
                "  - "
                f"{_chipTitleText_build(assignment.chipRef.chipId)} -> "
                f"{assignment.routingZoneId.id} "
                f"{assignment.terminalSide.value}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class ObligationView:
    """Interactive inspection view over route obligations."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "calls_get",
            "chipInternal_get",
            "count_get",
            "raw_get",
            "summary_text",
        ]

    def __repr__(self) -> str:
        return "<obligations>"

    def raw_get(self):
        return self.debugContext.routeObligationSet

    def calls_get(self):
        return self.debugContext.callRouteObligations_getAll()

    def chipInternal_get(self):
        return self.debugContext.chipInternalRouteObligations_getAll()

    def count_get(self) -> int:
        return len(self.calls_get()) + len(self.chipInternal_get())

    def summary_sprint(self) -> str:
        return "\n".join(
            [
                "obligations",
                f"  call: {len(self.calls_get())}",
                f"  chip_internal: {len(self.chipInternal_get())}",
            ]
        )


@dataclass(frozen=True)
class DiagnosticView:
    """Interactive inspection view over accumulated diagnostics."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return ["all_get", "codes_get", "count_get", "raw_get", "summary_text"]

    def __repr__(self) -> str:
        return "<diagnostics>"

    def raw_get(self):
        return self.debugContext.diagnostics_getAll()

    def all_get(self):
        return self.debugContext.diagnostics_getAll()

    def count_get(self) -> int:
        return len(self.all_get())

    def codes_get(self) -> tuple[str, ...]:
        return tuple(diagnostic.code for diagnostic in self.all_get())

    def summary_sprint(self) -> str:
        if not self.all_get():
            return "diagnostics\n  <none>"
        return "\n".join(
            [
                "diagnostics",
                *(f"  - {diagnostic.code}" for diagnostic in self.all_get()),
            ]
        )


@dataclass(frozen=True)
class InterconnectHandle:
    """Interactive handle for one placed routing-zone interconnect."""

    debugContext: SignalFlowContext
    sourceGridCoord: GridCoord
    destinationGridCoord: GridCoord

    def __dir__(self) -> list[str]:
        return [
            "endpoints_get",
            "raw_get",
            "routes_get",
            "schematic_text",
            "summary_text",
            "world_text",
        ]

    def __repr__(self) -> str:
        return (
            f"<interconnect "
            f"{self.sourceGridCoord}->{self.destinationGridCoord}>"
        )

    def raw_get(self):
        return self._routingZoneInterconnect_get()

    def endpoints_get(self) -> tuple:
        return self._routingZoneInterconnectEndpoints_get()

    def routes_get(self):
        return self._routingZoneInterconnectRoutes_get()

    def schematic_sprint(self, mode: str = "pixel") -> str:
        return self._routingZoneInterconnectDraw_render(mode=mode)

    def world_sprint(self) -> str:
        return self._routingZoneInterconnectWorldCanvas_render()

    def _routingZoneInterconnect_get(self):
        return self.debugContext.stagedInterconnectAtCoordsResult_get(
            sourceColumnIndex=self.sourceGridCoord.columnIndex,
            sourceRowIndex=self.sourceGridCoord.rowIndex,
            destinationColumnIndex=self.destinationGridCoord.columnIndex,
            destinationRowIndex=self.destinationGridCoord.rowIndex,
        )

    def _routingZoneInterconnectEndpoints_get(
        self,
    ) -> tuple[GridCoord, GridCoord]:
        return (self.sourceGridCoord, self.destinationGridCoord)

    def _routingZoneInterconnectRoutes_get(self):
        interconnectResult = self._routingZoneInterconnect_get()
        if not result_isOkCheck(interconnectResult):
            return ()
        return (
            self.debugContext.compatibilityInterconnectRoutesForInterconnect_get(
                interconnectResult.value.routingZoneInterconnectId
            )
        )

    def _routingZoneBreakout_get(self):
        interconnectResult = self._routingZoneInterconnect_get()
        if not result_isOkCheck(interconnectResult):
            return None
        breakout = interconnectResult.value.breakoutZone
        if not breakout:
            return None
        boardZone = self.debugContext.boardZoneById_get(
            breakout.routingZoneId
        )
        if boardZone is None:
            return _boardZoneRuntime_build(
                debugContext=self.debugContext,
                routingZoneId=breakout.routingZoneId,
            )
        return boardZone

    def _routingZoneInterconnectDraw_render(self, mode: str = "pixel") -> str:
        return _interconnectDrawingText_build(
            debugContext=self.debugContext,
            sourceGridCoord=self.sourceGridCoord,
            destinationGridCoord=self.destinationGridCoord,
            mode=mode,
        )

    def _routingZoneInterconnectDraw_print(self, mode: str = "pixel") -> None:
        _summary_print(self._routingZoneInterconnectDraw_render(mode=mode))

    def _routingZoneInterconnect_draw(self, mode: str = "pixel") -> None:
        self._routingZoneInterconnectDraw_print(mode=mode)

    def _routingZoneInterconnect_print(self) -> None:
        self._routingZoneInterconnectDraw_print()

    def _routingZoneInterconnectWorldCanvas_render(self) -> str:
        return _interconnectWorldCanvasText_build(
            debugContext=self.debugContext,
            sourceGridCoord=self.sourceGridCoord,
            destinationGridCoord=self.destinationGridCoord,
        )

    def _routingZoneInterconnectWorldCanvas_print(self) -> None:
        _summary_print(self._routingZoneInterconnectWorldCanvas_render())

    def summary_sprint(self) -> str:
        interconnectResult = self.raw_get()
        if not result_isOkCheck(interconnectResult):
            return "interconnect\n  status: missing"
        return _interconnectSummaryText_build(
            debugContext=self.debugContext,
            routingZoneInterconnectId=interconnectResult.value.routingZoneInterconnectId,
        )


@dataclass(frozen=True)
class PlacementHandle:
    """Interactive handle for one placed chip record."""

    debugContext: SignalFlowContext
    chipId: ChipId

    def __dir__(self) -> list[str]:
        return [
            "zone_get",
            "side_get",
            "order_get",
            "worldPoint_get",
            "raw_get",
            "summary_text",
        ]

    def __repr__(self) -> str:
        return f"<placement {_chipTitleText_build(self.chipId)}>"

    def raw_get(self):
        return self.debugContext.placementForChipResult_get(self.chipId)

    def zone_get(self):
        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return location[0]["zone"] if location else None

    def side_get(self) -> str | None:
        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return str(location[0]["terminalSide"]) if location else None

    def order_get(self) -> int | None:
        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return int(location[0]["orderIndex"]) if location else None  # type: ignore[arg-type]

    def worldPoint_get(self):
        location = self.debugContext.locationRecordsForChip_build(self.chipId)
        return location[0]["worldPoint"] if location else None

    def summary_sprint(self) -> str:
        return "\n".join(
            [
                f"placement {_chipTitleText_build(self.chipId)}",
                f"  zone: {self.zone_get()}",
                f"  side: {self.side_get()}",
                f"  order: {self.order_get()}",
                f"  point: {self.worldPoint_get()}",
            ]
        )


@dataclass(frozen=True)
class ZoneView:
    """Interactive inspection view over placed routing zones."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "all_get",
            "all_text",
            "count_get",
            "ids_get",
            "placements_get",
            "routes_get",
            "routes_text",
            "schematic_text",
            "summary_text",
            "zoneForChip_get",
            "zone_get",
        ]

    def __repr__(self) -> str:
        return "<zones>"

    def all_get(self):
        return self._routingZonesAll_get()

    def count_get(self) -> int:
        return self._routingZonesCount_get()

    def ids_get(self):
        return self._routingZoneIds_get()

    def all_sprint(self) -> str:
        return self._routingZonesAll_render()

    def zone_get(self, columnIndex: int, rowIndex: int):
        return self._routingZone_get(columnIndex, rowIndex)

    def zoneForChip_get(self, moduleName: str, functionName: str):
        return self._routingZoneForChip_get(moduleName, functionName)

    def placements_get(self, columnIndex: int, rowIndex: int):
        return self._routingZonePlacements_get(columnIndex, rowIndex)

    def routes_get(self, columnIndex: int, rowIndex: int):
        return self._routingZoneLocalRoutes_get(columnIndex, rowIndex)

    def routes_sprint(self, columnIndex: int, rowIndex: int) -> str:
        return self._routingZoneRoutesDraw_render(columnIndex, rowIndex)

    def schematic_sprint(self, columnIndex: int, rowIndex: int) -> str:
        return self._routingZoneDraw_render(columnIndex, rowIndex)

    def summary_sprint(self, columnIndex: int, rowIndex: int) -> str:
        return self._routingZone_render(columnIndex, rowIndex)

    def _routingZonesAll_get(self):
        return self.debugContext.boardZones_getAll()

    def _routingZonesCount_get(self) -> int:
        return len(self._routingZonesAll_get())

    def _routingZoneIds_get(self):
        return tuple(
            handle.routingZoneId for handle in self._routingZonesAll_get()
        )

    def _routingZonesAll_render(self) -> str:
        return "\n\n".join(
            self._routingZone_render(
                routingZoneId.id.columnIndex, routingZoneId.id.rowIndex
            )
            for routingZoneId in self._routingZoneIds_get()
            if isinstance(routingZoneId.id, GridCoord)
        )

    def _routingZonesAll_print(self) -> None:
        _summary_print(self._routingZonesAll_render())

    def _routingZone_get(self, columnIndex: int, rowIndex: int):
        routingZoneId = RoutingZoneId(
            id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
        )
        boardZone = self.debugContext.boardZoneById_get(routingZoneId)
        if boardZone is None:
            return _boardZoneRuntime_build(
                debugContext=self.debugContext,
                routingZoneId=routingZoneId,
            )
        return boardZone

    def _routingZoneForChip_get(self, moduleName: str, functionName: str):
        chipId = ChipId(moduleName=moduleName, functionName=functionName)
        zoneResult = self.debugContext.zoneOwningChipResult_get(chipId)
        if not result_isOkCheck(zoneResult):
            raise KeyError(
                f"No placed zone for chip {_chipTitleText_build(chipId)!r}"
            )
        boardZone = self.debugContext.boardZoneById_get(
            zoneResult.value.routingZoneId
        )
        if boardZone is None:
            return _boardZoneRuntime_build(
                debugContext=self.debugContext,
                routingZoneId=zoneResult.value.routingZoneId,
            )
        return boardZone

    def _routingZonePlacements_get(self, columnIndex: int, rowIndex: int):
        return self.debugContext.placementsForZone_get(
            RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            )
        )

    def _routingZoneLocalRoutes_get(self, columnIndex: int, rowIndex: int):
        return self.debugContext.zoneLocalRoutesForZone_get(
            RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            )
        )

    def _routingKernel_get(
        self, columnIndex: int, rowIndex: int, side: str = "intra"
    ):
        return self._routingZone_get(columnIndex, rowIndex).kernel_get(side)

    def _routingZoneRoutesDraw_render(
        self, columnIndex: int, rowIndex: int
    ) -> str:
        return _zoneRoutesText_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def _routingZoneRoutesDraw_print(
        self, columnIndex: int, rowIndex: int
    ) -> None:
        _summary_print(
            self._routingZoneRoutesDraw_render(columnIndex, rowIndex)
        )

    def _routingZone_render(self, columnIndex: int, rowIndex: int) -> str:
        return _zoneSummaryText_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def _routingZoneDraw_render(self, columnIndex: int, rowIndex: int) -> str:
        return _zoneDrawingLines_build(
            debugContext=self.debugContext,
            routingZoneId=RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            ),
        )

    def _routingZoneDraw_print(self, columnIndex: int, rowIndex: int) -> None:
        _summary_print(self._routingZoneDraw_render(columnIndex, rowIndex))

    def _routingZone_draw(self, columnIndex: int, rowIndex: int) -> None:
        self._routingZoneDraw_print(columnIndex, rowIndex)

    def _routingZone_print(self, columnIndex: int, rowIndex: int) -> None:
        _summary_print(self._routingZone_render(columnIndex, rowIndex))


@dataclass(frozen=True)
class GridView:
    """Interactive inspection and printing view over the placed world grid."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "gridCanvas_text",
            "gridSchematic_text",
            "gridSize_get",
            "gridStyle_text",
        ]

    def __repr__(self) -> str:
        return "<world>"

    def gridSize_get(self) -> GridCoord:
        return self.debugContext.stagedGridSize_get()

    def gridCanvas_sprint(self) -> str:
        return _worldCanvasText_build(self.debugContext)

    def gridSchematic_sprint(self) -> str:
        return _worldDrawText_build(self.debugContext)

    def gridStyle_sprint(self, style: str = "zones") -> str:
        return _gridText_build(debugContext=self.debugContext, style=style)


@dataclass(frozen=True)
class InterconnectView:
    """Interactive inspection view over placed routing-zone interconnects."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "all_get",
            "all_text",
            "count_get",
            "interconnect_get",
            "routes_get",
            "summary_text",
        ]

    def __repr__(self) -> str:
        return "<interconnects>"

    def all_get(self):
        return self._routingZoneInterconnectsAll_get()

    def count_get(self) -> int:
        return self._routingZoneInterconnectsCount_get()

    def all_sprint(self) -> str:
        return self._routingZoneInterconnectsAll_render()

    def interconnect_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        return self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )

    def routes_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        return self._routingZoneInterconnectRoutes_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )

    def summary_sprint(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> str:
        return self._routingZoneInterconnect_render(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )

    def _routingZoneInterconnectsAll_get(self):
        return tuple(
            InterconnectHandle(
                debugContext=self.debugContext,
                sourceGridCoord=interconnect.sourceZoneId.id,
                destinationGridCoord=interconnect.destinationZoneId.id,
            )
            for interconnect in (
                self.debugContext.compatibilityInterconnects_getAll()
            )
            if isinstance(interconnect.sourceZoneId.id, GridCoord)
            and isinstance(interconnect.destinationZoneId.id, GridCoord)
        )

    def _routingZoneInterconnectsCount_get(self) -> int:
        return len(self._routingZoneInterconnectsAll_get())

    def _routingZoneInterconnectsAll_render(self) -> str:
        return "\n\n".join(
            interconnect.summary_sprint()
            for interconnect in self._routingZoneInterconnectsAll_get()
        )

    def _routingZoneInterconnectsAll_print(self) -> None:
        _summary_print(self._routingZoneInterconnectsAll_render())

    def _routingZoneInterconnect_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        return InterconnectHandle(
            debugContext=self.debugContext,
            sourceGridCoord=GridCoord(
                columnIndex=sourceColumnIndex, rowIndex=sourceRowIndex
            ),
            destinationGridCoord=GridCoord(
                columnIndex=destinationColumnIndex,
                rowIndex=destinationRowIndex,
            ),
        )

    def _routingZoneInterconnectRoutes_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        return self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        ).routes_get()

    def _routingZoneBreakout_get(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ):
        return self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        )._routingZoneBreakout_get()

    def _routingZoneInterconnect_render(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> str:
        return self._routingZoneInterconnect_get(
            sourceColumnIndex=sourceColumnIndex,
            sourceRowIndex=sourceRowIndex,
            destinationColumnIndex=destinationColumnIndex,
            destinationRowIndex=destinationRowIndex,
        ).summary_sprint()

    def _routingZoneInterconnect_print(
        self,
        sourceColumnIndex: int,
        sourceRowIndex: int,
        destinationColumnIndex: int,
        destinationRowIndex: int,
    ) -> None:
        _summary_print(
            self._routingZoneInterconnect_render(
                sourceColumnIndex=sourceColumnIndex,
                sourceRowIndex=sourceRowIndex,
                destinationColumnIndex=destinationColumnIndex,
                destinationRowIndex=destinationRowIndex,
            )
        )


@dataclass(frozen=True)
class CallView:
    """Interactive inspection view over canonical call edges."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return ["all_get", "count_get", "outgoing_get", "incoming_get"]

    def __repr__(self) -> str:
        return "<calls>"

    def all_get(self):
        return self.debugContext.calls_getAll()

    def count_get(self) -> int:
        return len(self.all_get())

    def outgoing_get(self, moduleName: str, functionName: str):
        return (
            self.debugContext
            .circuitDocument
            .circuitCallSet
            .outgoingCallsForChip_get(
                ChipId(moduleName=moduleName, functionName=functionName)
            )
        )

    def incoming_get(self, moduleName: str, functionName: str):
        return (
            self.debugContext
            .circuitDocument
            .circuitCallSet
            .incomingCallsForChip_get(
                ChipId(moduleName=moduleName, functionName=functionName)
            )
        )


@dataclass(frozen=True)
class RouteView:
    """Interactive inspection view over obligations and solved routes."""

    debugContext: SignalFlowContext

    def __dir__(self) -> list[str]:
        return [
            "callObligations_get",
            "chipInternalObligations_get",
            "chipInternal_get",
            "forChip_get",
            "forZone_get",
            "gridLongHaulForChip_get",
            "gridLongHaul_get",
            "seamCrossing_get",
            "seamForChip_get",
            "zoneLocalForChip_get",
            "zoneLocal_get",
        ]

    def __repr__(self) -> str:
        return "<routes>"

    def _routingCallObligations_get(self):
        return self.debugContext.callRouteObligations_getAll()

    def _chipInternalRoutes_get(self):
        return self.debugContext.chipInternalSolvedRoutes_getAll()

    def _routingZoneLocalRoutes_get(self):
        return self.debugContext.zoneLocalSolvedRoutes_getAll()

    def _routingZoneInterconnectRoutes_get(self):
        return self.debugContext.compatibilityInterconnectSolvedRoutes_getAll()

    def _routingZoneGridSolvedRoutes_get(self):
        return self.debugContext.gridSolvedRoutes_getAll()

    def _chipRoutes_get(self, moduleName: str, functionName: str):
        return self.debugContext.chipRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def _routingZoneLocalForChip_get(self, moduleName: str, functionName: str):
        return self.debugContext.zoneLocalRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def _routingZoneLocalForZone_get(self, columnIndex: int, rowIndex: int):
        return self.debugContext.zoneLocalRoutesForZone_get(
            RoutingZoneId(
                id=GridCoord(columnIndex=columnIndex, rowIndex=rowIndex)
            )
        )

    def _routingZoneInterconnectForChip_get(
        self, moduleName: str, functionName: str
    ):
        return self.debugContext.compatibilityInterconnectRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def _routingZoneGridForChip_get(self, moduleName: str, functionName: str):
        return self.debugContext.gridRoutesForChip_get(
            ChipId(moduleName=moduleName, functionName=functionName)
        )

    def callObligations_get(self):
        return self._routingCallObligations_get()

    def chipInternal_get(self):
        return self._chipInternalRoutes_get()

    def zoneLocal_get(self):
        return self._routingZoneLocalRoutes_get()

    def seamCrossing_get(self):
        return self._routingZoneInterconnectRoutes_get()

    def gridLongHaul_get(self):
        return self._routingZoneGridSolvedRoutes_get()

    def forChip_get(self, moduleName: str, functionName: str):
        return self._chipRoutes_get(moduleName, functionName)

    def forZone_get(self, columnIndex: int, rowIndex: int):
        return self._routingZoneLocalForZone_get(columnIndex, rowIndex)

    def zoneLocalForChip_get(self, moduleName: str, functionName: str):
        return self._routingZoneLocalForChip_get(moduleName, functionName)

    def seamForChip_get(self, moduleName: str, functionName: str):
        return self._routingZoneInterconnectForChip_get(
            moduleName, functionName
        )

    def gridLongHaulForChip_get(self, moduleName: str, functionName: str):
        return self._routingZoneGridForChip_get(moduleName, functionName)


def __getattr__(name: str):
    """Resolve remaining cross-module debug surface names lazily."""

    if name in {
        "CallView",
        "ChipInternalBoardHandle",
        "ChipView",
        "GridView",
        "InterconnectHandle",
        "InterconnectView",
        "KernelBoardHandle",
        "KernelChannelHandle",
        "KernelChannelsHandle",
        "KernelHandle",
        "KernelLaneHandle",
        "KernelLanesHandle",
        "KernelWire",
        "KernelWiringHandle",
        "PlacementHandle",
        "RouteView",
        "WorkflowView",
        "ZoneAreaView",
        "ZoneHandle",
        "ZoneRegionHandle",
        "ZoneRegionSetHandle",
        "ZoneView",
    }:
        from . import handles as handles_module
        from . import primitives as primitives_module
        from . import surfaces as surfaces_module

        if hasattr(handles_module, name):
            return getattr(handles_module, name)
        if hasattr(surfaces_module, name):
            return getattr(surfaces_module, name)
        return getattr(primitives_module, name)
    raise AttributeError(name)


DebugAssignmentView = AssignmentView
DebugCallView = CallView
DebugCircuitView = CircuitView
DebugConfigView = ConfigView
DebugDiagnosticView = DiagnosticView
DebugDocumentView = DocumentView
DebugGridView = GridView
DebugInterconnectHandle = InterconnectHandle
DebugInterconnectView = InterconnectView
DebugObligationView = ObligationView
DebugPlacementHandle = PlacementHandle
DebugRouteView = RouteView
DebugTopologyGridView = TopologyGridView
DebugZoneView = ZoneView


__all__: list[str] = [
    "AssignmentView",
    "CallView",
    "CircuitView",
    "ConfigView",
    "DebugAssignmentView",
    "DebugCallView",
    "DebugCircuitView",
    "DebugConfigView",
    "DebugDiagnosticView",
    "DebugDocumentView",
    "DebugGridView",
    "DebugInterconnectHandle",
    "DebugInterconnectView",
    "DebugObligationView",
    "DebugPlacementHandle",
    "DebugRouteView",
    "DebugTopologyGridView",
    "DebugWorkflowView",
    "DebugZoneView",
    "DiagnosticView",
    "DocumentView",
    "GridView",
    "InterconnectHandle",
    "InterconnectView",
    "ObligationView",
    "PlacementHandle",
    "RouteView",
    "TopologyGridView",
    "WorkflowView",
    "ZoneView",
    "ls",
    "tree",
]
