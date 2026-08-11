"""Tests for glyph tables, icon rendering, and icon style detection."""

import pytest
from rich.cells import cell_len

from librarian.icons import (
    DEFAULT_ICON_STYLE,
    EMOJI_GLYPHS,
    FALLBACK_GLYPH_STYLE,
    FALLBACK_GLYPHS,
    GLYPH_STYLES,
    ICON_CELL_WIDTH,
    ICON_STYLES,
    NERD_FONT_TERMINALS,
    NERD_GLYPHS,
    detect_glyph_style,
    folder_glyph,
    has_nerd_font_installed,
    has_nerd_font_terminal,
    pad_glyph,
    resolve_icon,
    resolve_style,
)


class TestGlyphTables:
    def test_both_styles_cover_the_same_icon_names(self):
        assert set(NERD_GLYPHS) == set(EMOJI_GLYPHS)

    def test_nerd_glyphs_are_in_the_material_design_range(self):
        # Nerd Fonts places Material Design Icons at U+F0001-U+F1AF0; a glyph
        # outside that range means a bad codepoint that would render as tofu.
        for name, glyph in NERD_GLYPHS.items():
            assert len(glyph) == 1, name
            assert 0xF0001 <= ord(glyph) <= 0xF1AF0, name

    def test_nerd_glyphs_are_single_cell(self):
        for name, glyph in NERD_GLYPHS.items():
            assert cell_len(glyph) == 1, name

    def test_every_style_has_a_fallback_glyph(self):
        for style in GLYPH_STYLES:
            assert FALLBACK_GLYPHS[style]


class TestResolveIcon:
    def test_lucide_name_maps_to_nerd_glyph(self):
        assert resolve_icon("library", "nerd").startswith("\U000f0331")  # md-library

    def test_lucide_name_maps_to_emoji_glyph(self):
        assert resolve_icon("library", "emoji").startswith("\U0001f4da")

    @pytest.mark.parametrize("style", GLYPH_STYLES)
    def test_emoji_icons_pass_through_in_every_style(self, style):
        # An emoji chosen deliberately renders as an emoji whichever style is
        # configured.
        assert resolve_icon("emoji:\U0001f916", style).startswith("\U0001f916")

    @pytest.mark.parametrize("style", GLYPH_STYLES)
    def test_unknown_name_falls_back_per_style(self, style):
        assert resolve_icon("no-such-icon", style).startswith(FALLBACK_GLYPHS[style])

    @pytest.mark.parametrize("style", GLYPH_STYLES)
    def test_empty_name_returns_empty(self, style):
        assert resolve_icon("", style) == ""

    def test_unusable_style_still_renders_something(self):
        # Defensive: a bad style must not raise mid-render.
        assert resolve_icon("library", "wingdings")  # type: ignore[arg-type]

    def test_all_icons_render_to_the_same_width(self):
        # A tree mixes one-cell Nerd Font glyphs with two-cell emoji, so every
        # icon must occupy the same number of cells or names will not line up.
        widths = {
            cell_len(resolve_icon(name, style))
            for style in GLYPH_STYLES
            for name in ("library", "triangle-right", "emoji:\U0001f916", "unknown")
        } | {
            cell_len(folder_glyph(expanded, style))
            for style in GLYPH_STYLES
            for expanded in (True, False)
        }
        assert widths == {ICON_CELL_WIDTH + 1}

    def test_icon_ends_with_a_separating_space(self):
        # Without this, a two-cell emoji would abut the folder name.
        assert resolve_icon("emoji:\U0001f916", "emoji").endswith(" ")

    def test_pad_glyph_ignores_empty(self):
        assert pad_glyph("") == ""


class TestFolderGlyph:
    @pytest.mark.parametrize("style", GLYPH_STYLES)
    def test_expanded_and_collapsed_differ(self, style):
        assert folder_glyph(True, style) != folder_glyph(False, style)

    def test_nerd_style_uses_nerd_folder_glyphs(self):
        assert folder_glyph(False, "nerd").startswith("\U000f024b")  # md-folder
        assert folder_glyph(True, "nerd").startswith("\U000f0770")  # md-folder_open

    def test_emoji_style_uses_emoji_folder_glyphs(self):
        assert folder_glyph(False, "emoji").startswith("\U0001f4c1")
        assert folder_glyph(True, "emoji").startswith("\U0001f4c2")


class TestDetection:
    @pytest.fixture(autouse=True)
    def isolate_environment(self, monkeypatch, tmp_path):
        """Detach detection from the real terminal and font directories."""
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        empty = tmp_path / "no-fonts"
        empty.mkdir()
        monkeypatch.setattr("librarian.icons.FONT_DIRECTORIES", (empty,))

    def test_nerd_font_terminal_detected(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        assert has_nerd_font_terminal()
        assert detect_glyph_style() == "nerd"

    def test_terminal_match_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "  WezTerm  ")
        assert has_nerd_font_terminal()

    def test_other_terminal_not_detected(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
        assert not has_nerd_font_terminal()

    def test_no_signals_falls_back_to_emoji(self):
        assert detect_glyph_style() == FALLBACK_GLYPH_STYLE == "emoji"

    def test_installed_nerd_font_detected(self, monkeypatch, tmp_path):
        fonts = tmp_path / "fonts"
        fonts.mkdir()
        (fonts / "JetBrainsMonoNerdFont-Regular.ttf").write_bytes(b"")
        monkeypatch.setattr("librarian.icons.FONT_DIRECTORIES", (fonts,))

        assert has_nerd_font_installed()
        assert detect_glyph_style() == "nerd"

    def test_non_nerd_fonts_ignored(self, monkeypatch, tmp_path):
        fonts = tmp_path / "fonts"
        fonts.mkdir()
        (fonts / "Helvetica.ttc").write_bytes(b"")
        (fonts / "SomeNerdReadme.txt").write_bytes(b"")  # right name, wrong suffix
        monkeypatch.setattr("librarian.icons.FONT_DIRECTORIES", (fonts,))

        assert not has_nerd_font_installed()

    def test_missing_font_directory_is_not_an_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "librarian.icons.FONT_DIRECTORIES", (tmp_path / "nonexistent",)
        )
        assert not has_nerd_font_installed()

    def test_terminal_allowlist_is_lowercase(self):
        # has_nerd_font_terminal() lowercases before matching, so entries that
        # are not lowercase could never match.
        assert all(name == name.lower() for name in NERD_FONT_TERMINALS)


class TestResolveStyle:
    @pytest.fixture(autouse=True)
    def no_nerd_font(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        empty = tmp_path / "no-fonts"
        empty.mkdir()
        monkeypatch.setattr("librarian.icons.FONT_DIRECTORIES", (empty,))

    @pytest.mark.parametrize("style", GLYPH_STYLES)
    def test_explicit_styles_are_honored(self, style):
        assert resolve_style(style) == style

    def test_explicit_nerd_wins_over_detection(self, monkeypatch):
        # Detection would say emoji here; the user's choice must still win.
        assert resolve_style("nerd") == "nerd"

    def test_auto_detects(self):
        assert resolve_style("auto") == "emoji"

    def test_auto_detects_nerd_when_available(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        assert resolve_style("auto") == "nerd"

    def test_none_detects(self):
        assert resolve_style(None) == "emoji"

    def test_unknown_style_detects_rather_than_guessing(self):
        assert resolve_style("nerdfont") == "emoji"

    def test_default_config_style_is_auto(self):
        assert DEFAULT_ICON_STYLE == "auto"
        assert set(ICON_STYLES) == {"auto", *GLYPH_STYLES}
