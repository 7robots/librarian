"""Tests for the banner: it must stay short and never grow with content."""

import pytest
from rich.cells import cell_len
from textual.app import App, ComposeResult

from librarian.widgets.banner import (
    ROBOT_ROWS,
    ROBOT_WIDTH,
    SUBTITLE,
    TITLE,
    URL,
    Banner,
    _build_banner,
)

BANNER_HEIGHT = 3


class BannerApp(App):
    def compose(self) -> ComposeResult:
        yield Banner()


class TestRobotArt:
    def test_three_rows(self):
        assert len(ROBOT_ROWS) == BANNER_HEIGHT

    def test_rows_are_the_same_width(self):
        """Ragged rows would shift the text column between lines."""
        assert {cell_len(row) for row in ROBOT_ROWS} == {ROBOT_WIDTH}

    def test_single_cell_glyphs_only(self):
        """A double-width glyph would misalign the columns beside it."""
        for row in ROBOT_ROWS:
            for char in row:
                assert cell_len(char) == 1, repr(char)

    def test_antenna_is_centered_over_the_eyes(self):
        antenna, face = ROBOT_ROWS[0], ROBOT_ROWS[1]
        eyes = [i for i, char in enumerate(face) if char == "●"]

        assert len(eyes) == 2
        assert antenna.index("●") == pytest.approx(sum(eyes) / 2, abs=0.5)


class TestBannerText:
    def test_lines_match_the_art_rows(self):
        assert len(_build_banner().plain.splitlines()) == len(ROBOT_ROWS)

    def test_contains_title_and_tagline(self):
        plain = _build_banner().plain
        # The title is letter-spaced, so match on its letters in order.
        assert " ".join(TITLE) in plain
        assert SUBTITLE in plain
        assert URL in plain

    def test_title_letters_are_individually_colored(self):
        text = _build_banner()
        styles = {
            span.style for span in text.spans if isinstance(span.style, str)
        }
        title_colors = {s for s in styles if s.startswith("bold bright_")}

        # One span per letter, in more than one color.
        assert len(title_colors) > 1

    def test_does_not_wrap(self):
        """Wrapping would make the banner taller than its fixed height."""
        assert _build_banner().no_wrap is True


class TestBannerWidget:
    async def test_height_is_fixed(self):
        app = BannerApp()
        async with app.run_test(size=(110, 24)) as pilot:
            await pilot.pause()
            assert app.query_one(Banner).size.height == BANNER_HEIGHT

    @pytest.mark.parametrize("width", [40, 60, 80, 200])
    async def test_height_holds_at_any_width(self, width):
        """A narrow terminal must clip the tagline, not grow the banner."""
        app = BannerApp()
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.pause()
            assert app.query_one(Banner).size.height == BANNER_HEIGHT
