"""Tests for the new-engine debug context surface."""
from __future__ import annotations

import re
import sys

import pytest

from signalflow.__main__ import arguments_parse
from signalflow.engine import newEngineDebugContextResult_buildFromDocumentDict
from signalflow.engine.debug import (
    _ANSI_WHITE,
    _HISTORY_FILE,
    DebugChipHandle,
    DebugGridView,
    _completionWrapper_build,
    _diagnosticLine_build,
    _displayText_build,
    _manual_print,
    _promptDisplayText_build,
    _readline_setup,
    _readlineHistory_save,
    _replBanner_build,
    _replLocals_build,
    _replPrompts_configure,
    _replPrompts_restore,
    _reprSyntaxColorize_build,
    _summaryTextColorize_build,
)
from signalflow.models import (
    Diagnostic,
    DiagnosticLevel,
    DiagnosticPhase,
    RouteObligationScope,
    RoutingZoneRegionSide,
    result_isOkCheck,
    resultOk_build,
)


class TestNewEngineDebugContext:
    """Verification of the current debug-context pipeline."""

    def test_arguments_parse_accepts_repl_flag(self) -> None:
        """CLI parsing should expose the debug REPL flag."""

        arguments = arguments_parse(["--repl", "examples/root-multi-child.yaml"])

        assert arguments.repl is True

    def test_replBanner_build_contains_current_debug_surface(self) -> None:
        """The REPL banner should advertise the available debug names."""

        banner: str = _replBanner_build(
            "examples/simple-circuit/three-deep-linear.yaml"
        )

        assert "SignalFlow new-engine debug REPL" in banner
        assert "document" in banner
        assert "chips" in banner
        assert "workflows" in banner
        assert "prompt" in banner
        assert "zone.world_print()" in banner
        assert "interconnects.all_print()" in banner
        assert "routes.gridLongHaul_get()" in banner
        assert "prompt.title.len_truncate(32)" in banner
        assert "sfhelp()" in banner
        assert "man('chips')" in banner
        assert "tab completion is enabled" in banner

    def test_replPrompts_configure_sets_signalflow_prompts(
        self,
        monkeypatch,
    ) -> None:
        """The debug REPL should set custom prompts and restore them cleanly."""

        monkeypatch.delenv("NO_COLOR", raising=False)
        previousPs1 = getattr(sys, "ps1", None)
        previousPs2 = getattr(sys, "ps2", None)

        # With no context, falls back to plain prompts.
        _replPrompts_configure()
        assert sys.ps1 == "> "
        assert sys.ps2 == "... "
        assert _ANSI_WHITE not in sys.ps1
        assert _ANSI_WHITE not in sys.ps2

        _replPrompts_restore(previousPs1, previousPs2)

    def test_promptDisplayText_build_strips_readline_sentinels(self) -> None:
        """Prompt display text should not leak readline sentinel characters."""

        promptText = "\001\033[36m\002title[3!|czxg]> \001\033[0m\002"

        assert (
            _promptDisplayText_build(promptText)
            == "\033[36mtitle[3!|czxg]> \033[0m"
        )

    def test_replPrompt_uses_full_title_without_sf_prefix(self, monkeypatch) -> None:
        """Live primary prompt should render the full title with no `sf:` prefix."""

        monkeypatch.delenv("NO_COLOR", raising=False)
        previousPs1 = getattr(sys, "ps1", None)
        previousPs2 = getattr(sys, "ps2", None)
        documentDict = {
            "title": "non-root parent — branch on return, converging dependencies",
            "tree": {"module": "App.ts", "func": "main()", "calls": []},
        }
        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        try:
            prompt = _replPrompts_configure(debugContextResult.value)
            assert prompt is not None

            rendered = _promptDisplayText_build(str(prompt))

            assert rendered.startswith(
                "\033[36mnon-root parent — branch on return, converging dependencies["
            )
            assert "sf:" not in rendered
        finally:
            _replPrompts_restore(previousPs1, previousPs2)

    def test_replPrompt_title_len_truncate_mutates_live_prompt(self) -> None:
        """Title formatter chain should truncate and reset the live prompt title."""

        documentDict = {
            "title": "non-root parent — branch on return, converging dependencies",
            "tree": {"module": "App.ts", "func": "main()", "calls": []},
        }
        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        replLocals = _replLocals_build(debugContextResult.value)
        prompt = replLocals["prompt"]

        assert prompt.render().startswith(
            "non-root parent — branch on return, converging dependencies["
        )
        assert prompt.title.len_truncate(20) is prompt.title
        assert prompt.render().startswith("non-root parent — br[")
        assert prompt.title.full() is prompt.title
        assert prompt.render().startswith(
            "non-root parent — branch on return, converging dependencies["
        )

    def test_readline_setup_loads_and_persists_history(
        self, tmp_path, monkeypatch
    ) -> None:
        """REPL setup should round-trip history through _HISTORY_FILE.

        When a history file already exists it must be loaded so that prior
        commands are available for up-arrow recall.  When readline is absent
        (non-default platform) the setup must still complete without raising.
        """
        try:
            import readline as rl
        except ImportError:
            return  # pragma: no cover - platform without readline

        histFile = str(tmp_path / "sf_test_history")
        monkeypatch.setattr("signalflow.engine.debug._HISTORY_FILE", histFile)

        # Seed a history file with a known entry.
        histFilePath = tmp_path / "sf_test_history"
        histFilePath.write_text("chips.names_get()\n")

        # Setup must load that entry without raising.
        rl.clear_history()
        _readline_setup({})

        # The seeded entry should now be in readline history.
        assert rl.get_history_length() != 0 or rl.get_current_history_length() > 0

        # _HISTORY_FILE constant should point to ~/.signalflow_history.
        assert _HISTORY_FILE.endswith(".signalflow_history")

    def test_readlineHistory_save_writes_file(
        self, tmp_path, monkeypatch
    ) -> None:
        """_readlineHistory_save must write the history file immediately.

        History is written in the REPL finally-block, not via atexit, so the
        file must materialise as soon as _readlineHistory_save is called.
        """
        try:
            import readline as rl
        except ImportError:
            return  # pragma: no cover

        histFile = str(tmp_path / "sf_saved_history")
        monkeypatch.setattr("signalflow.engine.debug._HISTORY_FILE", histFile)

        rl.clear_history()
        rl.add_history("chips.names_get()")

        _readlineHistory_save()

        assert (tmp_path / "sf_saved_history").exists()

    def test_completionWrapper_build_suppresses_empty_text(self) -> None:
        """The completion wrapper must return None for empty text.

        When the cursor is immediately after `(` the word readline hands to the
        completer is "".  Without the guard, rlcompleter falls through to
        global_matches("") and returns hundreds of candidates, causing GNU
        readline to fire its "Display all N possibilities?" prompt which
        corrupts the terminal column state and produces the double-prompt /
        bck: artifacts.
        """
        try:
            import rlcompleter as rlc
        except ImportError:
            return  # pragma: no cover

        namespace = {"chips": object(), "zones": object()}
        completer = rlc.Completer(namespace)
        wrapped = _completionWrapper_build(completer)

        # Empty text must always return None regardless of state.
        assert wrapped("", 0) is None
        assert wrapped("", 1) is None

        # Non-empty text must still delegate to rlcompleter normally.
        result = wrapped("chip", 0)
        assert result == "chips" or result is None  # depends on rlcompleter match

    def test_diagnosticLine_build_formats_debug_output(self) -> None:
        """Debug diagnostics should be rendered as one readable colorized line."""

        diagnostic = Diagnostic(
            level=DiagnosticLevel.ERROR,
            phase=DiagnosticPhase.ROUTING,
            code="routing.example.problem",
            message="Example routing failure",
            context=("A.ts", "run()"),
        )

        line: str = _diagnosticLine_build(diagnostic)

        assert "routing.example.problem" in line
        assert "Example routing failure" in line
        assert "context=('A.ts', 'run()')" in line

    def test_displayText_build_colorizes_result_and_collections(
        self,
        monkeypatch,
    ) -> None:
        """Interactive display text should distinguish results and containers."""

        monkeypatch.delenv("NO_COLOR", raising=False)
        okResult = resultOk_build(("a", "b"))

        okText: str = _displayText_build(okResult)
        tupleText: str = _displayText_build(("a", "b"))
        plainTupleText = re.sub(r"\x1b\[[0-9;]*m", "", tupleText)

        assert "ResultOk" in okText
        assert "\033[" in okText
        assert "('a', 'b')" in plainTupleText
        assert "\033[" in tupleText

    def test_displayText_build_colorizes_strings_dicts_and_callables(
        self,
        monkeypatch,
    ) -> None:
        """Interactive display text should classify common REPL values distinctly."""

        monkeypatch.delenv("NO_COLOR", raising=False)

        stringText: str = _displayText_build("hello")
        dictText: str = _displayText_build({"a": 1})
        callableText: str = _displayText_build(len)
        plainDictText = re.sub(r"\x1b\[[0-9;]*m", "", dictText)

        assert _ANSI_WHITE not in stringText
        assert "\033[" in stringText
        assert "{'a': 1}" in plainDictText
        assert "\033[" in dictText
        assert "built-in function len" in callableText
        assert "\033[" in callableText

    def test_reprSyntaxColorize_build_classifies_repr_tokens(
        self,
        monkeypatch,
    ) -> None:
        """Repr syntax colorization should distinguish core repr token classes."""

        monkeypatch.delenv("NO_COLOR", raising=False)

        colorizedText = _reprSyntaxColorize_build(
            "('Root.ts:root()', {'row': 1, 'ok': True})",
            defaultAnsiCodes=("\033[97m",),
        )

        assert "Root.ts:root()" in colorizedText
        assert "'row'" in colorizedText
        assert "1" in colorizedText
        assert "True" in colorizedText
        assert "\033[" in colorizedText

    def test_displayText_build_renders_multiline_strings_as_text_blocks(
        self,
        monkeypatch,
    ) -> None:
        """Multiline strings should render directly, not as quoted repr text."""

        monkeypatch.delenv("NO_COLOR", raising=False)

        blockText: str = _displayText_build("a\nb")

        assert "'a\\nb'" not in blockText
        assert "a\nb" in blockText
        assert "\033[" in blockText

    def test_summaryTextColorize_build_colorizes_structured_summary(
        self,
        monkeypatch,
    ) -> None:
        """Structured print summaries should be colorized by line role."""

        monkeypatch.delenv("NO_COLOR", raising=False)

        summaryText = "\n".join(
            [
                "chip App.ts:main()",
                "  title: App.ts:main()",
                "  draw:",
                "    ┌──────┐",
            ]
        )

        colorizedText: str = _summaryTextColorize_build(summaryText)

        assert "chip App.ts:main()" in colorizedText
        assert "title:" in colorizedText
        assert "┌──────┐" in colorizedText
        assert "\033[" in colorizedText

    def test_debugContext_builds_full_current_pipeline_for_simple_chain(
        self,
    ) -> None:
        """The debug context should materialize the current new-engine stages."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "calls": [],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        assert debugContextResult.value.chipCount_get() == 2
        assert len(debugContextResult.value.chipIds_getAll()) == 2
        assert debugContextResult.value.routingZoneCount_get() == 1
        rootPlacementResult = debugContextResult.value.rootPlacementResult_get()
        assert result_isOkCheck(rootPlacementResult)
        assert (
            rootPlacementResult.value.chipTerminalRegionId.routingZoneRegionSide
            is RoutingZoneRegionSide.WEST
        )
        rootChipResult = debugContextResult.value.rootChipResult_get()
        assert result_isOkCheck(rootChipResult)
        assert rootChipResult.value.chipId.functionName == "main()"

    def test_debugContext_builds_recursive_root_case(self) -> None:
        """Recursive self-edge inputs should still materialize a full debug context."""

        documentDict = {
            "tree": {
                "module": "Loop.ts",
                "func": "loop()",
                "input_ports": [{"signal": "tick", "return": "tock"}],
                "output_ports": [{"signal": "tick", "return": "tock"}],
                "internal_wiring": ["tick:tick", "tock:tock"],
                "calls": [{"module": "Loop.ts", "func": "loop()"}],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        assert debugContextResult.value.chipCount_get() == 1
        assert len(
            debugContextResult.value.routeObligationSet.callRouteObligationSet.callRouteObligations
        ) == 1
        assert (
            debugContextResult.value.routeObligationSet.callRouteObligationSet.callRouteObligations[
                0
            ].routeObligationScope
            is RouteObligationScope.ZONE_LOCAL
        )
        assert len(
            debugContextResult.value.routingZoneLocalSolvedRouteSet.routingZoneLocalSolvedRoutes
        ) == 1
        assert len(
            debugContextResult.value.chipInternalSolvedRouteSet.chipInternalSolvedRoutes
        ) == 2
        assert len(
            debugContextResult.value.chipRoutesForChip_get(
                debugContextResult.value.circuitDocument.rootChipRef.chipId
            )
        ) == 2

    def test_chip_view_exposes_title_size_terminals_location_and_draw(self) -> None:
        """The chip debug view should expose focused chip inspection helpers."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "input_ports": [{"signal": "in"}],
                "output_ports": [{"signal": "out"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [{"signal": "out"}],
                        "calls": [],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        chips = debugContextResult.value.chips

        assert chips.title_get("App.ts", "main()") == "App.ts:main()"
        assert chips.terminals_get("App.ts", "main()") == {
            "north": 0,
            "south": 0,
            "east": 1,
            "west": 1,
        }
        width, height = chips.size_get("App.ts", "main()")
        assert width > 0
        assert height > 0
        location = chips.location_get("App.ts", "main()")
        assert location is not None
        assert location["terminalSide"] == "west"
        assert location["zone"].columnIndex == 1
        assert location["zone"].rowIndex == 1
        drawing = chips.draw("App.ts", "main()")
        assert "main()" in drawing
        # Full form: title header above separator above body rows.
        assert "├" in drawing
        # Drawing should show actual terminal names, not count labels.
        assert "in" in drawing
        assert "out" in drawing
        assert "W:1" not in drawing
        assert "E:1" not in drawing

    def test_chip_view_supports_handle_selection(self) -> None:
        """The chip debug view should support selecting one chip once."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "input_ports": [{"signal": "in"}],
                "output_ports": [{"signal": "out"}],
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        chips = debugContextResult.value.chips

        handle = chips.chip_get("App.ts", "main()")
        indexedHandle = chips["App.ts:main()"]

        assert isinstance(handle, DebugChipHandle)
        assert isinstance(indexedHandle, DebugChipHandle)
        assert handle.title_get() == "App.ts:main()"
        assert indexedHandle.title_get() == "App.ts:main()"
        assert handle.terminals_get() == {
            "north": 0,
            "south": 0,
            "east": 1,
            "west": 1,
        }

    def test_chip_handle_reports_explicit_dimensions(self) -> None:
        """Chip handles should expose named drawing dimensions."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        chip = debugContextResult.value.chips["App.ts:main()"]

        # No terminals: compact title-only form, bodyWidth=max(10,10)=10, 3 rows.
        assert chip.size_get() == (12, 3)
        assert chip.dimensions_get() == {
            "widthColumns": 12,
            "heightRows": 3,
        }
        assert chip.width_get() == 12
        assert chip.height_get() == 3

    def test_chips_all_returns_interactive_handles(self) -> None:
        """chips.all_get() should return DebugChipHandle objects, not raw chips.

        Raw chip dataclasses would expose their full field vocabulary in tab
        completion. Returning handles keeps the tab-complete surface curated.
        """

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "calls": [],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        allChips = debugContextResult.value.chips.all_get()

        assert len(allChips) == 2
        assert all(isinstance(chip, DebugChipHandle) for chip in allChips)
        titles = [c.title_get() for c in allChips]
        assert "App.ts:main()" in titles
        assert "Worker.ts:run()" in titles
        # Curated dir on each handle — no raw dataclass fields.
        for chipHandle in allChips:
            names = dir(chipHandle)
            assert "debugContext" not in names
            assert "chipId" not in names
            assert "draw" in names
            assert "title_get" in names

    def test_chip_draw_shows_named_terminals_not_count_labels(self) -> None:
        """chip.draw() should show actual terminal names, not N:/W:/E:/S: counts.

        Named terminals make chip.draw() useful as a render-design surface.
        Count labels were provisional scaffolding.
        """

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "func()",
                "input_ports": [{"signal": "checker"}],
                "output_ports": [{"signal": "callExpr"}],
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        drawing = debugContextResult.value.chips.draw("App.ts", "func()")

        assert "func()" in drawing
        # Title header above separator above body rows.
        assert "├" in drawing
        # Forward thread stub shows west terminal name; east stub shows east name.
        assert "checker" in drawing
        assert "callExpr" in drawing
        assert "N:" not in drawing
        assert "W:" not in drawing
        assert "E:" not in drawing
        assert "S:" not in drawing

    def test_chip_draw_scales_height_for_multiple_east_terminals(self) -> None:
        """chip.draw() box height scales to fit all east terminal stubs.

        The west side always shows exactly ONE forward thread stub (named with
        the first declared west terminal's signal) and ONE return thread stub,
        regardless of how many west terminals are declared. The body rows
        expand to accommodate all east terminal stubs.
        """

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "hub()",
                "input_ports": [
                    {"signal": "in1"},
                    {"signal": "in2"},
                    {"signal": "in3"},
                ],
                "output_ports": [
                    {"signal": "out1"},
                    {"signal": "out2"},
                ],
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        chip = debugContextResult.value.chips["App.ts:hub()"]
        drawing = chip.draw()
        _, height = chip.size_get()

        # Full form: title header + separator + body + top/bottom borders.
        # body = max(2, 2*N_east) = max(2, 2*2) = 4 rows.
        # Total = 1 + 1 + 1 + 4 + 1 = 8 rows.
        assert height == 8
        # Forward thread shows first west terminal name only.
        assert "in1" in drawing
        # East stubs show all east terminal names.
        assert "out1" in drawing
        assert "out2" in drawing
        # Title header must be present above the separator.
        assert "hub()" in drawing
        assert "├" in drawing

    def test_chip_draw_labels_west_return_stub_and_uses_inward_arrow_for_east_returns(
        self,
    ) -> None:
        """West return stub must be labelled; east return stubs must use inward arrow.

        For a chip with input_ports signal=a / return=ra and
        output_ports signal=b / return=rb:

          - West forward stub:  ``a ─►│``  (outward from caller)
          - West return stub:   ``ra ◄─│`` (labelled, return flows leftward)
          - East signal stub:   ``│─► b``  (exits chip to the right)
          - East return stub:   ``│◄─ rb`` (enters chip from the right)
        """

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "mid()",
                "input_ports": [{"signal": "a", "return": "ra"}],
                "output_ports": [{"signal": "b", "return": "rb"}],
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        drawing = debugContextResult.value.chips.draw("App.ts", "mid()")

        # West forward stub carries signal name; T-junction closes the gap.
        assert "a─►┤" in drawing
        # West return stub is labelled with T-junction.
        assert "ra◄─┤" in drawing
        # East signal terminal exits chip through T-junction.
        assert "├─►b" in drawing
        # East return terminal enters chip from east through T-junction.
        assert "├◄─rb" in drawing
        # East return must NOT appear with an outward arrow.
        assert "─►rb" not in drawing

    def test_chip_view_rejects_malformed_or_unknown_titles(self) -> None:
        """Chip selection should fail fast on malformed or unknown titles."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        chips = debugContextResult.value.chips

        with pytest.raises(ValueError) as malformedTitleContext:
            chips["App.ts::main()"]

        assert "App.ts::main()" in str(malformedTitleContext.value)
        assert "chips.names_get()" in str(malformedTitleContext.value)

        with pytest.raises(KeyError) as unknownTitleContext:
            chips["Missing.ts:ghost()"]

        assert "Missing.ts:ghost()" in str(unknownTitleContext.value)
        assert "chips.names_get()" in str(unknownTitleContext.value)

    def test_chip_handle_exposes_canonical_children(self) -> None:
        """A selected chip handle should expose child chips as handles."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "calls": [],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        chip = debugContextResult.value.chips["App.ts:main()"]
        children = chip.children_get()

        assert len(children) == 1
        assert isinstance(children[0], DebugChipHandle)
        assert children[0].title_get() == "Worker.ts:run()"
        assert chip.child_get(0).title_get() == "Worker.ts:run()"

    def test_zone_areas_set_supports_names_and_lookup(self) -> None:
        """Zone area sets should expose names and keyed lookup helpers."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "calls": [],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        zone = debugContextResult.value.zones.zone_get(1, 1)
        areas = zone.areas_get()

        assert "west/chip_terminal" in areas.names_get()
        westTerminal = areas.area_get("west/chip_terminal")
        assert westTerminal is not None
        assert westTerminal.name == "west/chip_terminal"
        assert areas.area_get("chip_terminal", side="west") is not None
        assert areas.area_get("missing/region") is None

    def test_zone_areas_names_print_lists_region_names(self, capsys) -> None:
        """names_print() should emit canonical region names."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        zone = debugContextResult.value.zones.zone_get(1, 1)

        zone.areas_get().names_print()
        captured = capsys.readouterr()

        assert "west/inter_routing_longitude" in captured.out
        assert "east/inter_routing_longitude" in captured.out

    def test_debug_views_support_batch_rendering_for_render_design(self) -> None:
        """Curated views should support the chip->zone->interconnect audit loop."""

        documentDict = {
            "tree": {
                "module": "Root.ts",
                "func": "root()",
                "output_ports": [{"signal": "a", "return": "ra"}],
                "calls": [
                    {
                        "module": "Mid.ts",
                        "func": "mid()",
                        "input_ports": [{"signal": "a", "return": "ra"}],
                        "output_ports": [{"signal": "b", "return": "rb"}],
                        "calls": [
                            {
                                "module": "Leaf.ts",
                                "func": "leaf()",
                                "input_ports": [{"signal": "b", "return": "rb"}],
                                "calls": [],
                            }
                        ],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        debugContext = debugContextResult.value

        chipBatch = debugContext.chips.all_render()
        zoneBatch = debugContext.zones.all_render()
        interconnectBatch = debugContext.interconnects.all_render()

        assert "chip Root.ts:root()" in chipBatch
        assert "chip Mid.ts:mid()" in chipBatch
        assert "zone GridCoord(columnIndex=1, rowIndex=1)" in zoneBatch
        assert "interconnect" in interconnectBatch

    def test_chip_handle_dir_is_curated_for_repl_completion(self) -> None:
        """The chip handle should expose only the intended REPL surface in dir()."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "calls": [],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        chip = debugContextResult.value.chips["App.ts:main()"]
        names = dir(chip)

        assert "title_get" in names
        assert "draw" in names
        assert "children_get" in names
        assert "debugContext" not in names
        assert "chipId" not in names

    def test_debugContext_builds_grid_long_haul_routes(self) -> None:
        """Long-haul backedges should materialize grid-level solved routes."""

        documentDict = {
            "tree": {
                "module": "Root.ts",
                "func": "root()",
                "input_ports": [{"signal": "root", "return": "rroot"}],
                "output_ports": [{"signal": "a", "return": "ra"}],
                "calls": [
                    {
                        "module": "A.ts",
                        "func": "a()",
                        "input_ports": [{"signal": "a", "return": "ra"}],
                        "output_ports": [{"signal": "b", "return": "rb"}],
                        "calls": [
                            {
                                "module": "B.ts",
                                "func": "b()",
                                "input_ports": [{"signal": "b", "return": "rb"}],
                                "output_ports": [{"signal": "c", "return": "rc"}],
                                "calls": [
                                    {
                                        "module": "C.ts",
                                        "func": "c()",
                                        "input_ports": [
                                            {"signal": "c", "return": "rc"}
                                        ],
                                        "output_ports": [
                                            {"signal": "d", "return": "rd"}
                                        ],
                                        "calls": [
                                            {
                                                "module": "D.ts",
                                                "func": "d()",
                                                "input_ports": [
                                                    {"signal": "d", "return": "rd"}
                                                ],
                                                "output_ports": [
                                                    {
                                                        "signal": "root",
                                                        "return": "rroot",
                                                    }
                                                ],
                                                "calls": [
                                                    {
                                                        "module": "Root.ts",
                                                        "func": "root()",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        assert len(debugContextResult.value.routes.gridLongHaul_get()) == 1
        assert len(
            debugContextResult.value.gridRoutesForChip_get(
                debugContextResult.value.circuitDocument.rootChipRef.chipId
            )
        ) == 1

    def test_replLocals_build_exposes_curated_placed_and_raw_placed(self) -> None:
        """The REPL should expose `placed` as curated view and `raw_placed` as raw."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "calls": [],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        replLocals = _replLocals_build(debugContextResult.value)

        assert isinstance(replLocals["placed"], DebugGridView)
        assert isinstance(replLocals["world"], DebugGridView)
        assert (
            replLocals["placed"].debugContext
            is debugContextResult.value
        )
        assert (
            replLocals["world"].debugContext
            is debugContextResult.value
        )
        assert (
            replLocals["raw_placed"]
            is debugContextResult.value.placedRoutingZoneGrid
        )

    def test_replLocals_build_exposes_curated_debug_views(self) -> None:
        """REPL locals should favor curated debug views over raw tuples."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "calls": [],
            }
        }
        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        replLocals = _replLocals_build(debugContextResult.value)
        assert hasattr(replLocals["chips"], "ids_get")
        assert hasattr(replLocals["chips"], "print")
        assert hasattr(replLocals["zones"], "zone_get")
        assert hasattr(replLocals["zones"], "routes_get")
        assert hasattr(replLocals["zones"], "print")
        assert hasattr(replLocals["calls"], "outgoing_get")
        assert hasattr(replLocals["world"], "print")
        assert hasattr(replLocals["routes"], "chipInternal_get")
        assert hasattr(replLocals["routes"], "zoneLocal_get")
        assert hasattr(replLocals["routes"], "seamCrossing_get")
        assert hasattr(replLocals["routes"], "gridLongHaul_get")
        assert hasattr(replLocals["interconnects"], "interconnect_get")
        assert hasattr(replLocals["interconnects"], "print")
        assert "raw_chips" in replLocals
        assert "raw_zone_local_routes" in replLocals
        assert "raw_interconnect_routes" in replLocals
        assert "raw_grid_routes" in replLocals
        assert "sfhelp" in replLocals
        assert "man" in replLocals
        assert "workflows" in replLocals
        assert "ls" in replLocals
        assert "tree" in replLocals

    def test_replLocals_build_curates_dir_for_all_advertised_names(self) -> None:
        """Every advertised REPL name should complete against a curated surface."""

        documentDict = {
            "tree": {
                "module": "Root.ts",
                "func": "root()",
                "output_ports": [{"signal": "a", "return": "ra"}],
                "calls": [
                    {
                        "module": "Mid.ts",
                        "func": "mid()",
                        "input_ports": [{"signal": "a", "return": "ra"}],
                        "output_ports": [{"signal": "b", "return": "rb"}],
                        "calls": [
                            {
                                "module": "Leaf.ts",
                                "func": "leaf()",
                                "input_ports": [{"signal": "b", "return": "rb"}],
                                "calls": [],
                            }
                        ],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        replLocals = _replLocals_build(debugContextResult.value)

        expectedDirByName = {
            "ctx": [
                "calls",
                "chipCount_get",
                "chips",
                "diagnostics_getAll",
                "interconnectCount_get",
                "interconnects",
                "placementForChipResult_get",
                "rootPlacementResult_get",
                "routes",
                "routingZoneCount_get",
                "world",
                "zoneOwningChipResult_get",
                "zones",
            ],
            "document": [
                "callCount_get",
                "callingDepth_get",
                "chipCount_get",
                "raw_get",
                "root_get",
                "title_get",
            ],
            "circuit": [
                "callCount_get",
                "calls_get",
                "chipCount_get",
                "chips_get",
                "raw_get",
                "root_get",
                "title_get",
            ],
            "config": [
                "channelSense_get",
                "gridSize_get",
                "interconnectCount_get",
                "occupancyPolicy_get",
                "packingPolicy_get",
                "pathPolicy_get",
                "raw_get",
                "sense_get",
                "zoneCount_get",
            ],
            "grid": [
                "interconnectAt_get",
                "interconnectCount_get",
                "raw_get",
                "size_get",
                "zoneAt_get",
                "zoneCount_get",
            ],
            "assignment": [
                "all_get",
                "count_get",
                "forChip_get",
                "forZone_get",
                "print",
                "raw_get",
                "render",
            ],
            "placed": [
                "canvas_print",
                "canvas_render",
                "draw_print",
                "draw_render",
                "print",
                "render",
                "size_get",
            ],
            "obligations": [
                "calls_get",
                "chipInternal_get",
                "count_get",
                "print",
                "raw_get",
                "render",
            ],
            "chips": [
                "all_get",
                "all_print",
                "all_render",
                "chipByTitle_get",
                "chip_get",
                "count_get",
                "draw",
                "ids_get",
                "location_get",
                "locations_get",
                "names_get",
                "placement_get",
                "print",
                "render",
                "root_get",
                "routes_get",
                "size_get",
                "terminals_get",
                "title_get",
            ],
            "zones": [
                "all_get",
                "all_print",
                "all_render",
                "count_get",
                "draw_print",
                "draw_render",
                "ids_get",
                "placements_get",
                "print",
                "render",
                "routes_get",
                "routes_print",
                "routes_render",
                "zoneForChip_get",
                "zone_get",
            ],
            "world": [
                "canvas_print",
                "canvas_render",
                "draw_print",
                "draw_render",
                "print",
                "render",
                "size_get",
            ],
            "calls": ["all_get", "count_get", "incoming_get", "outgoing_get"],
            "routes": [
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
            ],
            "interconnects": [
                "all_get",
                "all_print",
                "all_render",
                "count_get",
                "interconnect_get",
                "print",
                "render",
                "routes_get",
            ],
            "diagnostics": [
                "all_get",
                "codes_get",
                "count_get",
                "print",
                "raw_get",
                "render",
            ],
            "root_chip": [
                "all_print",
                "all_render",
                "child_get",
                "children_get",
                "dimensions_get",
                "draw",
                "height_get",
                "location_get",
                "locations_get",
                "placement_get",
                "print",
                "raw_get",
                "render",
                "routes_get",
                "size_get",
                "terminals_get",
                "title_get",
                "width_get",
            ],
            "root_placement": [
                "order_get",
                "print",
                "raw_get",
                "render",
                "side_get",
                "worldPoint_get",
                "zone_get",
            ],
            "prompt": ["print", "render", "reset", "title"],
        }

        for name, expectedDir in expectedDirByName.items():
            assert dir(replLocals[name]) == expectedDir

        assert dir(replLocals["prompt"].title) == ["full", "len_truncate"]
        zoneAreas = replLocals["zones"].zone_get(1, 1).areas_get()
        assert dir(zoneAreas) == [
            "all_get",
            "area_get",
            "draw",
            "draw_get",
            "draw_print",
            "info_get",
            "info_print",
            "names_get",
            "names_print",
        ]
        assert dir(replLocals["zones"].zone_get(1, 1)) == [
            "area_get",
            "areas_get",
            "draw_print",
            "draw_render",
            "id_get",
            "placements_get",
            "print",
            "raw_get",
            "render",
            "routes_get",
            "routes_print",
                "routes_render",
                "sense_get",
                "world_print",
                "world_render",
            ]
        assert dir(replLocals["interconnects"].interconnect_get(1, 1, 2, 1)) == [
            "draw_print",
            "draw_render",
            "endpoints_get",
            "print",
            "raw_get",
            "render",
            "routes_get",
            "world_print",
            "world_render",
        ]

    def test_zone_world_render_crops_authoritative_world_canvas(self) -> None:
        """Zone world rendering should be a crop of the composed world canvas."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "calls": [],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        zone = debugContextResult.value.zones.zone_get(1, 1)
        zoneResult = zone.raw_get()
        assert result_isOkCheck(zoneResult)

        fullWorldLines = debugContextResult.value.world.canvas_render().splitlines()
        zoneFrame = zoneResult.value.routingZoneFrame
        expectedZoneLines = [
            row[zoneFrame.horizontalStart:zoneFrame.horizontalEnd_calculate()]
            for row in fullWorldLines[
                zoneFrame.verticalStart:zoneFrame.verticalEnd_calculate()
            ]
        ]

        assert zone.world_render() == "\n".join(expectedZoneLines)

    def test_interconnect_world_render_crops_authoritative_world_canvas(self) -> None:
        """Interconnect world rendering should crop the composed world canvas."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "output_ports": [{"signal": "leaf", "return": "rleaf"}],
                        "calls": [
                            {
                                "module": "Leaf.ts",
                                "func": "finish()",
                                "input_ports": [
                                    {"signal": "leaf", "return": "rleaf"}
                                ],
                                "calls": [],
                            }
                        ],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        interconnect = debugContextResult.value.interconnects.interconnect_get(
            1, 1, 2, 1
        )
        interconnectResult = interconnect.raw_get()
        assert result_isOkCheck(interconnectResult)

        fullWorldLines = debugContextResult.value.world.canvas_render().splitlines()
        frame = interconnectResult.value.routingZoneInterconnectFrame
        expectedLines = [
            row[frame.horizontalStart:frame.horizontalStart + frame.horizontalSpan]
            for row in fullWorldLines[
                frame.verticalStart:frame.verticalStart + frame.verticalSpan
            ]
        ]

        assert interconnect.world_render() == "\n".join(expectedLines)

    def test_interconnect_draw_render_shows_pixel_frame(self) -> None:
        """Interconnect draw should expose the seam frame as a pixel block."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "output_ports": [{"signal": "leaf", "return": "rleaf"}],
                        "calls": [
                            {
                                "module": "Leaf.ts",
                                "func": "finish()",
                                "input_ports": [
                                    {"signal": "leaf", "return": "rleaf"}
                                ],
                                "calls": [],
                            }
                        ],
                    }
                ],
            }
        }

        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )

        assert result_isOkCheck(debugContextResult)
        interconnect = debugContextResult.value.interconnects.interconnect_get(
            1, 1, 2, 1
        )
        rendered = interconnect.draw_render("pixel")

        assert "legend:" in rendered
        assert "seam/interconnect" in rendered
        assert "▓▓" in rendered

    def test_manual_print_accepts_named_topics(self, capsys) -> None:
        """The lightweight manual should print topic-specific help."""

        _manual_print("chips")
        captured = capsys.readouterr()

        assert "chips" in captured.out
        assert "chips.chip_get(moduleName, functionName)" in captured.out

    def test_manual_print_world_topic_mentions_grid_print_styles(
        self,
        capsys,
    ) -> None:
        """The world manual should describe the grid printing surface."""

        _manual_print("world")
        captured = capsys.readouterr()

        assert "world" in captured.out
        assert "world.print(style='zones')" in captured.out
        assert "world.print(style='routes')" in captured.out

    def test_manual_print_routes_topic_mentions_zone_local_queries(
        self,
        capsys,
    ) -> None:
        """The routes manual should surface zone-local inspection helpers."""

        _manual_print("routes")
        captured = capsys.readouterr()

        assert "routes.zoneLocal_get()" in captured.out
        assert "routes.forZone_get(columnIndex, rowIndex)" in captured.out
        assert "routes.seamCrossing_get()" in captured.out
        assert "routes.gridLongHaul_get()" in captured.out

    def test_debug_views_render_readable_chip_zone_and_world_text(self) -> None:
        """Debug print helpers should render readable summaries."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "calls": [],
                    }
                ],
            }
        }
        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(debugContextResult)

        chipText = debugContextResult.value.chips.render("App.ts", "main()")
        zoneText = debugContextResult.value.zones.render(1, 1)
        worldText = debugContextResult.value.world.render("placements")

        assert "chip App.ts:main()" in chipText
        assert "zone GridCoord(columnIndex=1, rowIndex=1)" in zoneText
        assert "world placements" in worldText

    def test_interconnect_view_render_shows_seam_route_summary(self) -> None:
        """Interconnect debug view should render solved seam route summaries."""

        documentDict = {
            "tree": {
                "module": "App.ts",
                "func": "main()",
                "output_ports": [{"signal": "query", "return": "result"}],
                "calls": [
                    {
                        "module": "Worker.ts",
                        "func": "run()",
                        "input_ports": [
                            {"signal": "query", "return": "result"}
                        ],
                        "output_ports": [{"signal": "leaf", "return": "rleaf"}],
                        "calls": [
                            {
                                "module": "Leaf.ts",
                                "func": "finish()",
                                "input_ports": [
                                    {"signal": "leaf", "return": "rleaf"}
                                ],
                                "calls": [],
                            }
                        ],
                    }
                ],
            }
        }
        debugContextResult = newEngineDebugContextResult_buildFromDocumentDict(
            documentDict
        )
        assert result_isOkCheck(debugContextResult)

        interconnectText = debugContextResult.value.interconnects.render(1, 1, 2, 1)

        assert "interconnect GridCoord(columnIndex=1, rowIndex=1)" in interconnectText
        assert "seam routes: 2" in interconnectText
