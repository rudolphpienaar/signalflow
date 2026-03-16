"""Tests for Canvas draw primitives."""

from signalflow.legacy.models import Canvas


def _canvas(rows: int = 10, cols: int = 20) -> Canvas:
    return Canvas(rows=rows, cols=cols)


class TestCanvasSet:
    """Tests for basic Canvas.set semantics."""

    def test_set_and_get(self):
        """Canvas.set should write a glyph retrievable through Canvas.get."""
        c = _canvas()
        c.set(3, 2, 'X')
        assert c.get(3, 2) == 'X'

    def test_out_of_bounds_raises_in_debug_mode(self):
        """Canvas.set should raise on out-of-bounds writes in debug mode."""
        import pytest
        c = _canvas()
        with pytest.raises(IndexError, match="Canvas OOB"):
            c.set(100, 100, 'X')


class TestHline:
    """Tests for horizontal line primitives."""

    def test_hline_fills_spaces(self):
        """hline_force should fill the requested horizontal span with wires."""
        c = _canvas()
        c.hline_force(1, 2, 6)
        assert all(c.get(x, 1) == '─' for x in range(2, 6))

    def test_hline_pierce_merges_with_modeMerge(self):
        """hline_pierce in merge mode combines │ and ─ into ┼."""
        c = _canvas()
        c.set(3, 1, '│')
        c.modeMerge = True
        c.hline_pierce(1, 2, 6)
        c.modeMerge = False
        assert c.get(3, 1) == '┼'

    def test_hline_force_overwrites(self):
        """hline_force should overwrite any existing glyphs in its span."""
        c = _canvas()
        c.set(3, 1, '│')
        c.hline_force(1, 2, 6)
        assert c.get(3, 1) == '─'


class TestVline:
    """Tests for vertical line primitives."""

    def test_vline_fills_spaces(self):
        """vline should fill the requested vertical span with wire glyphs."""
        c = _canvas()
        c.vline(2, 1, 5)
        assert all(c.get(2, y) == '│' for y in range(1, 5))


class TestText:
    """Tests for text overlay primitives."""

    def test_text_writes_string(self):
        """text should write a contiguous string starting at the given coordinate."""
        c = _canvas()
        c.text(1, 1, 'hello')
        assert ''.join(c.get(1 + i, 1) for i in range(5)) == 'hello'
