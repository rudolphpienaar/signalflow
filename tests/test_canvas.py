"""Tests for Canvas draw primitives."""

from signalflow.models import Canvas


def _canvas(rows: int = 10, cols: int = 20) -> Canvas:
    return Canvas(rows=rows, cols=cols)


class TestCanvasSet:
    def test_set_and_get(self):
        c = _canvas()
        c.set(3, 2, 'X')
        assert c.get(3, 2) == 'X'

    def test_out_of_bounds_silently_ignored(self):
        c = _canvas()
        c.set(100, 100, 'X')  # no exception
        assert c.get(100, 100) == ' '


class TestHline:
    def test_hline_fills_spaces(self):
        c = _canvas()
        c.hline(1, 2, 6)
        assert all(c.get(x, 1) == '─' for x in range(2, 6))

    def test_hline_skips_nonempty(self):
        c = _canvas()
        c.set(3, 1, '│')
        c.hline(1, 2, 6)
        assert c.get(3, 1) == '│'

    def test_hline_force_overwrites(self):
        c = _canvas()
        c.set(3, 1, '│')
        c.hline_force(1, 2, 6)
        assert c.get(3, 1) == '─'


class TestVline:
    def test_vline_fills_spaces(self):
        c = _canvas()
        c.vline(2, 1, 5)
        assert all(c.get(2, y) == '│' for y in range(1, 5))


class TestText:
    def test_text_writes_string(self):
        c = _canvas()
        c.text(1, 1, 'hello')
        assert ''.join(c.get(1 + i, 1) for i in range(5)) == 'hello'
