"""REPL-facing debug entry points and prompt/display orchestration."""

from __future__ import annotations

import code
import os
import re
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from signalflow.models import Diagnostic, result_isOkCheck
from signalflow.models.diagnostics import diagnosticStack

from . import views
from .backend import boardBackend_get, boardBackend_set
from .build import context_buildFromDocument
from .chip_helpers import _chipHandle_build
from .context import SignalFlowContext, WorkflowView
from .kernel_runtime import solution_materialize, solution_realize
from .manual import REPL_AVAILABLE_NAMES_LINES, REPL_HELPER_LINES
from .terminal import (
    ANSI_BOLD,
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_RESET,
    ANSI_YELLOW,
    HISTORY_FILE,
    HISTORY_LENGTH,
    readline,
    rlcompleter,
)


class _SignalFlowInteractiveConsole(code.InteractiveConsole):
    """Interactive console with stable plain-text prompt handling."""

    def raw_input(self, prompt: object = "") -> str:
        """Read one line and pass the prompt directly to `input()`."""

        return input(str(prompt))


def _snippetFile_run(pathText: str, replLocals: dict[str, object]) -> None:
    """Execute one Python snippet file inside the live REPL namespace."""

    snippetPath = Path(pathText).expanduser()
    snippetSource = snippetPath.read_text(encoding="utf-8")
    exec(
        compile(snippetSource, str(snippetPath), "exec"),
        replLocals,
        replLocals,
    )


def repl_run(
    documentDict: dict[str, object],
    sourcePath: str | None = None,
    loadSnippetPath: str | None = None,
) -> int:
    """Run the operator-facing debug REPL for one source document."""

    debugContextResult = context_buildFromDocument(documentDict)
    if not result_isOkCheck(debugContextResult):
        _diagnostics_printToStdout()
        return 1

    debugContext: SignalFlowContext = debugContextResult.value
    sourceDescription: str = sourcePath or "<in-memory>"
    banner: str = _replBanner_build(sourceDescription)
    previousPs1: str | None = getattr(sys, "ps1", None)
    previousPs2: str | None = getattr(sys, "ps2", None)
    previousDisplayHook = sys.displayhook
    prompt = _replPrompts_configure(debugContext)
    replLocals: dict[str, object] = {}
    replLocals.update(
        _replLocals_build(debugContext, prompt=prompt, replLocals=replLocals)
    )
    if loadSnippetPath is not None:
        _snippetFile_run(loadSnippetPath, replLocals)
    _readline_setup(replLocals)
    views._displayHook_configure()
    interactiveConsole = _SignalFlowInteractiveConsole(locals=replLocals)
    try:
        interactiveConsole.interact(banner=banner, exitmsg="")
    finally:
        _readlineHistory_save()
        _replPrompts_restore(previousPs1, previousPs2)
        views._displayHook_restore(previousDisplayHook)
    return 0


def snippet_run(
    documentDict: dict[str, object],
    snippetPath: str,
    sourcePath: str | None = None,
) -> int:
    """Run one snippet against the new-engine inspect context and exit."""

    debugContextResult = context_buildFromDocument(documentDict)
    if not result_isOkCheck(debugContextResult):
        _diagnostics_printToStdout()
        return 1

    debugContext: SignalFlowContext = debugContextResult.value
    replLocals: dict[str, object] = {}
    replLocals.update(
        _replLocals_build(
            debugContext, replLocals=replLocals, sourcePath=sourcePath
        )
    )
    _snippetFile_run(snippetPath, replLocals)
    return 0


def _diagnostics_printToStdout() -> None:
    """Print accumulated diagnostics using the debugger's line formatter."""

    diagnostic: Diagnostic
    for (
        diagnostic
    ) in diagnosticStack.diagnosticSet_build().diagnostics_getAll():
        print(views._diagnosticLine_build(diagnostic))


def _summary_print(text: str) -> None:
    """Print one structured debug summary using summary-aware coloring."""

    print(views._summaryTextColorize_build(text))


def _colorEnabled_check() -> bool:
    """Return whether ANSI coloring should be emitted."""

    return os.environ.get("NO_COLOR") is None


def _ansiWrap_build(text: str, *ansiCodes: str) -> str:
    """Wrap one text fragment in ANSI styles when color is enabled."""

    if not _colorEnabled_check():
        return text
    return f"{''.join(ansiCodes)}{text}{ANSI_RESET}"


def _ansiPrompt_build(
    text: str,
    *ansiCodes: str,
    trailingAnsiCodes: tuple[str, ...] = (),
) -> str:
    """Build a readline-safe ANSI prompt string."""

    if not _colorEnabled_check():
        return text
    return (
        f"\001{''.join(ansiCodes)}\002{text}"
        f"\001{''.join(trailingAnsiCodes)}\002"
    )


def _promptDisplayText_build(prompt: str) -> str:
    """Strip readline prompt sentinels before prompt text reaches `input()`."""

    return prompt.replace("\001", "").replace("\002", "")


def _promptSegment_build(text: str, *ansiCodes: str) -> str:
    """Build one colored segment for a readline-safe prompt."""

    if not _colorEnabled_check() or not ansiCodes:
        return text
    return f"\001{''.join(ansiCodes)}\002{text}"


def _promptReset_build() -> str:
    """Readline-safe ANSI reset for the end of a multi-segment prompt."""

    if not _colorEnabled_check():
        return ""
    return f"\001{ANSI_RESET}\002"


@dataclass
class _ReplTitleController:
    """Mutable title-format controller for the live REPL prompt."""

    prompt: _ReplPs1

    def __dir__(self) -> list[str]:
        return ["full", "len_truncate"]

    def __repr__(self) -> str:
        return "<prompt.title>"

    def full(self) -> _ReplTitleController:
        self.prompt.titleTransform = None
        return self

    def len_truncate(self, maxLength: int) -> _ReplTitleController:
        if maxLength < 0:
            raise ValueError("maxLength must be >= 0")
        self.prompt.titleTransform = lambda title: title[:maxLength]
        return self


@dataclass
class _ReplPs1:
    """Dynamic `sys.ps1` whose `__str__` is called before each prompt."""

    debugContext: SignalFlowContext
    titleTransform: Callable[[str], str] | None = None
    title: _ReplTitleController = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.title = _ReplTitleController(prompt=self)

    def __dir__(self) -> list[str]:
        return ["print", "reset", "title", "toStr"]

    def __repr__(self) -> str:
        return "<prompt>"

    def _titleText_get(self) -> str:
        title = self.debugContext.circuitDocument.title or "untitled"
        if self.titleTransform is None:
            return title
        return self.titleTransform(title)

    def toStr(self) -> str:
        display = _promptDisplayText_build(str(self))
        return re.sub(r"\x1b\[[0-9;]*m", "", display)

    def print(self) -> None:
        print(self.toStr(), end="")

    def reset(self) -> _ReplPs1:
        self.title.full()
        return self

    def __str__(self) -> str:
        ctx = self.debugContext
        title = self._titleText_get()
        errorCount = len(ctx.diagnostics_getAll())
        health = (
            _promptSegment_build("\u2713", ANSI_GREEN, ANSI_BOLD)
            if errorCount == 0
            else _promptSegment_build(f"{errorCount}!", ANSI_RED, ANSI_BOLD)
        )
        chipOblCount = len(
            ctx.routeObligationSet.chipInternalRouteObligationSet.chipInternalRouteObligations
        )
        callOblCount = len(
            ctx.routeObligationSet.callRouteObligationSet.callRouteObligations
        )
        chipRouteCount = len(
            ctx.chipInternalSolvedRouteSet.chipInternalSolvedRoutes
        )
        zoneRouteCount = len(
            ctx.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        )
        seamRouteCount = len(
            ctx.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes
        )
        gridRouteCount = len(
            ctx.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
        )
        seamOblCount = callOblCount if ctx.routingZoneCount_get() > 1 else 0

        def _stage(letter: str, oblCount: int, routeCount: int) -> str:
            if routeCount > 0:
                return _promptSegment_build(letter, ANSI_GREEN)
            if oblCount > 0:
                return _promptSegment_build(letter, ANSI_YELLOW)
            return _promptSegment_build(letter, ANSI_DIM)

        stages = (
            _stage("c", chipOblCount, chipRouteCount)
            + _stage("z", callOblCount, zoneRouteCount)
            + _stage("x", seamOblCount, seamRouteCount)
            + _stage("g", 0, gridRouteCount)
        )
        return (
            _promptSegment_build(f"{title}[", ANSI_CYAN)
            + health
            + _promptSegment_build("|", ANSI_DIM)
            + stages
            + _promptSegment_build("]> ", ANSI_CYAN)
            + _promptReset_build()
        )


def _replBanner_build(sourceDescription: str) -> str:
    """Build the startup banner shown when the debugger REPL launches."""

    return "\n".join(
        [
            _ansiWrap_build(
                "SignalFlow new-engine debug REPL", ANSI_BOLD, ANSI_CYAN
            ),
            f"{_ansiWrap_build('source', ANSI_DIM)}: {sourceDescription}",
            "",
            _ansiWrap_build("available names", ANSI_BOLD, ANSI_GREEN),
            *REPL_AVAILABLE_NAMES_LINES,
            "",
            _ansiWrap_build("useful helpers", ANSI_BOLD, ANSI_GREEN),
            *REPL_HELPER_LINES,
            "",
            _ansiWrap_build(
                "tab completion is enabled when readline is available",
                ANSI_DIM,
            ),
        ]
    )


def _replLocals_build(
    debugContext: SignalFlowContext,
    prompt: _ReplPs1 | None = None,
    replLocals: dict[str, object] | None = None,
    sourcePath: str | None = None,
) -> dict[str, object]:
    """Build the curated local namespace exposed to the debug REPL."""

    if replLocals is None:
        replLocals = {}
    livePrompt = prompt or _ReplPs1(debugContext=debugContext)
    return {
        "ctx": debugContext,
        "source_yaml": sourcePath,
        "document": views.DocumentView(debugContext),
        "circuit": views.CircuitView(debugContext),
        "config": views.ConfigView(debugContext),
        "grid": views.TopologyGridView(debugContext),
        "assignment": views.AssignmentView(debugContext),
        "placed": debugContext.world,
        "obligations": views.ObligationView(debugContext),
        "chips": debugContext.chips,
        "zones": debugContext.zones,
        "world": debugContext.world,
        "calls": debugContext.calls,
        "routes": debugContext.routes,
        "interconnects": debugContext.interconnects,
        "diagnostics": views.DiagnosticView(debugContext),
        "root_chip": _chipHandle_build(
            debugContext=debugContext,
            chipId=debugContext.circuitDocument.rootChipRef.chipId,
        ),
        "root_placement": views.PlacementHandle(
            debugContext=debugContext,
            chipId=debugContext.circuitDocument.rootChipRef.chipId,
        ),
        "prompt": livePrompt,
        "raw_placed": debugContext.placedRoutingZoneGrid,
        "raw_chips": debugContext.chips_getAll(),
        "raw_calls": debugContext.calls_getAll(),
        "raw_zones": debugContext.zones_getAll(),
        "raw_interconnects": debugContext.interconnects_getAll(),
        "raw_zone_local_routes": (
            debugContext.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        ),
        "raw_interconnect_routes": (
            debugContext.routingZoneInterconnectSolvedRouteSet.routingZoneInterconnectSolvedRoutes
        ),
        "raw_grid_routes": (
            debugContext.routingZoneGridSolvedRouteSet.routingZoneGridSolvedRoutes
        ),
        "sfhelp": lambda: print(_replBanner_build("<current session>")),
        "man": views._manual_print,
        "load": lambda path: _snippetFile_run(path, replLocals),
        "board_backend_get": boardBackend_get,
        "board_backend_set": boardBackend_set,
        "solution_realize": solution_realize,
        "solution_materialize": solution_materialize,
        "workflows": WorkflowView(
            debugContext=debugContext, replLocals=replLocals
        ),
        "ls": views.ls,
        "tree": views.tree,
    }


def _replPrompts_configure(
    debugContext: SignalFlowContext | None = None,
) -> _ReplPs1 | None:
    """Configure a context-bearing colored prompt."""

    if debugContext is None:
        sys.ps1 = "> "
        sys.ps2 = "... "
        return None

    prompt = _ReplPs1(debugContext=debugContext)
    sys.ps1 = prompt
    sys.ps2 = _ansiPrompt_build(
        "... ",
        ANSI_DIM,
        trailingAnsiCodes=(ANSI_RESET,),
    )
    return prompt


def _replPrompts_restore(
    previousPs1: str | None,
    previousPs2: str | None,
) -> None:
    """Restore Python prompts after leaving the REPL."""

    if _colorEnabled_check():
        sys.stdout.write(ANSI_RESET)
        sys.stdout.flush()

    if previousPs1 is None:
        with suppress(AttributeError):
            del sys.ps1
    else:
        sys.ps1 = previousPs1
    if previousPs2 is None:
        with suppress(AttributeError):
            del sys.ps2
    else:
        sys.ps2 = previousPs2


def _completionWrapper_build(
    completer: object,
) -> Callable[[str, int], str | None]:
    """Build a safe tab-completion callable for readline."""

    def _complete(text: str, state: int) -> str | None:
        if not text:
            return None
        return completer.complete(text, state)  # type: ignore[union-attr]

    return _complete


def _readlineHistory_save() -> None:
    """Write readline history to disk immediately."""

    if readline is None:  # pragma: no cover - platform dependent
        return
    with suppress(OSError):
        readline.write_history_file(HISTORY_FILE)


def _readline_setup(replLocals: dict[str, object]) -> None:
    """Enable readline history and tab completion when available."""

    if readline is None or rlcompleter is None:  # pragma: no cover
        return
    with suppress(OSError):
        readline.read_history_file(HISTORY_FILE)
    readline.set_history_length(HISTORY_LENGTH)
    completer = rlcompleter.Completer(replLocals)
    readline.set_completer(_completionWrapper_build(completer))
    readline.set_completer_delims(" \t\n`~!@#$%^&*()-=+[{]}\\|;:'\",<>/?")
    if readline.__doc__ and "libedit" in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")


__all__: list[str] = [
    "_replLocals_build",
    "repl_run",
    "snippet_run",
]
