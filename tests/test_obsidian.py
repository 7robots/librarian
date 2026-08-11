"""Tests for Notebook Navigator appearance mirroring."""

import json

import pytest
from rich.cells import cell_len

from librarian.obsidian import (
    EMOJI_GLYPHS,
    FALLBACK_GLYPHS,
    ICON_CELL_WIDTH,
    ICON_STYLES,
    NERD_GLYPHS,
    PLUGIN_DATA_RELATIVE_PATH,
    NotebookNavigatorAppearance,
    find_vault_root,
    folder_glyph,
    normalize_style,
    resolve_icon,
)


def make_vault(root, data=None):
    """Create a vault skeleton, optionally with Notebook Navigator data."""
    (root / ".obsidian").mkdir(parents=True, exist_ok=True)
    if data is not None:
        data_path = root / PLUGIN_DATA_RELATIVE_PATH
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(json.dumps(data))
    return root


SAMPLE_DATA = {
    "showFolderIcons": True,
    "inheritFolderColors": True,
    "folderIcons": {
        "anthologia": "library",
        "kybernetes": "emoji:\U0001f916",
        "techne": "computer",
        "melete": "not-a-real-lucide-name",
    },
    "folderColors": {
        "anthologia": "#78716c",
        "kybernetes": "#06b6d4",
    },
    "tagColors": {"arete": "#84cc16"},
}


class TestResolveIcon:
    def test_nerd_style_is_the_default(self):
        assert resolve_icon("library") == resolve_icon("library", "nerd")

    def test_lucide_name_maps_to_nerd_glyph(self):
        assert resolve_icon("library", "nerd").startswith("\U000f0331")  # md-library

    def test_lucide_name_maps_to_emoji_glyph(self):
        assert resolve_icon("library", "emoji").startswith("\U0001f4da")

    @pytest.mark.parametrize("style", ICON_STYLES)
    def test_emoji_icons_pass_through_in_every_style(self, style):
        # An emoji chosen in Obsidian renders as an emoji there, so it should
        # here too, whichever style is configured.
        assert resolve_icon("emoji:\U0001f916", style).startswith("\U0001f916")

    @pytest.mark.parametrize("style", ICON_STYLES)
    def test_unknown_name_falls_back_per_style(self, style):
        assert resolve_icon("no-such-icon", style).startswith(FALLBACK_GLYPHS[style])

    @pytest.mark.parametrize("style", ICON_STYLES)
    def test_empty_name_returns_empty(self, style):
        assert resolve_icon("", style) == ""

    def test_unknown_style_falls_back_to_default(self):
        assert resolve_icon("library", "wingdings") == resolve_icon("library", "nerd")

    def test_all_icons_render_to_the_same_width(self):
        # A tree mixes one-cell Nerd Font glyphs with two-cell emoji, so every
        # icon must occupy the same number of cells or names will not line up.
        widths = {
            cell_len(resolve_icon(name, style))
            for style in ICON_STYLES
            for name in ("library", "triangle-right", "emoji:\U0001f916", "unknown")
        } | {
            cell_len(folder_glyph(expanded, style))
            for style in ICON_STYLES
            for expanded in (True, False)
        }
        assert widths == {ICON_CELL_WIDTH + 1}

    def test_icon_ends_with_a_separating_space(self):
        # Without this, a two-cell emoji would abut the folder name.
        assert resolve_icon("emoji:\U0001f916").endswith(" ")


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


class TestNormalizeStyle:
    @pytest.mark.parametrize("style", ICON_STYLES)
    def test_known_styles_pass_through(self, style):
        assert normalize_style(style) == style

    @pytest.mark.parametrize("style", ["", None, "nerdfont", "NERD"])
    def test_unknown_styles_become_the_default(self, style):
        assert normalize_style(style) == "nerd"


class TestFolderGlyph:
    def test_expanded_and_collapsed_differ(self):
        for style in ICON_STYLES:
            assert folder_glyph(True, style) != folder_glyph(False, style)

    def test_nerd_style_uses_nerd_folder_glyphs(self):
        assert folder_glyph(False, "nerd").startswith("\U000f024b")  # md-folder
        assert folder_glyph(True, "nerd").startswith("\U000f0770")  # md-folder_open

    def test_emoji_style_uses_emoji_folder_glyphs(self):
        assert folder_glyph(False, "emoji").startswith("\U0001f4c1")
        assert folder_glyph(True, "emoji").startswith("\U0001f4c2")


class TestFindVaultRoot:
    def test_finds_vault_at_path(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        assert find_vault_root(vault) == vault.resolve()

    def test_walks_up_from_subdirectory(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        nested = vault / "techne" / "deep"
        nested.mkdir(parents=True)
        assert find_vault_root(nested) == vault.resolve()

    def test_returns_none_outside_vault(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert find_vault_root(plain) is None


class TestLoad:
    def test_returns_none_when_not_a_vault(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert NotebookNavigatorAppearance.load(plain) is None

    def test_returns_none_when_plugin_missing(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        assert NotebookNavigatorAppearance.load(vault) is None

    def test_returns_none_on_invalid_json(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        data_path = vault / PLUGIN_DATA_RELATIVE_PATH
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text("{not valid json")
        assert NotebookNavigatorAppearance.load(vault) is None

    def test_loads_icons_and_colors(self, tmp_path):
        vault = make_vault(tmp_path / "vault", SAMPLE_DATA)
        appearance = NotebookNavigatorAppearance.load(vault)
        assert appearance is not None
        assert appearance.vault_root == vault.resolve()
        assert appearance.folder_icons["anthologia"] == "library"
        assert appearance.folder_colors["kybernetes"] == "#06b6d4"
        assert appearance.tag_colors == {"arete": "#84cc16"}

    def test_loads_from_subdirectory_scan_root(self, tmp_path):
        vault = make_vault(tmp_path / "vault", SAMPLE_DATA)
        nested = vault / "techne"
        nested.mkdir()
        appearance = NotebookNavigatorAppearance.load(nested)
        assert appearance is not None
        # Keys stay relative to the vault root, not the scan directory.
        assert appearance.icon_for(nested).startswith("\U000f0322")  # md-laptop

    def test_ignores_non_string_and_blank_values(self, tmp_path):
        vault = make_vault(
            tmp_path / "vault",
            {"folderColors": {"a": "#fff", "b": 42, "c": "", "d": None}},
        )
        appearance = NotebookNavigatorAppearance.load(vault)
        assert appearance is not None
        assert appearance.folder_colors == {"a": "#fff"}


class TestLookups:
    @pytest.fixture
    def appearance(self, tmp_path):
        vault = make_vault(tmp_path / "vault", SAMPLE_DATA)
        return NotebookNavigatorAppearance.load(vault)

    def test_icon_for_folder(self, appearance):
        path = appearance.vault_root / "anthologia"
        assert appearance.icon_for(path).startswith("\U000f0331")  # md-library

    def test_icon_style_selects_the_glyph_table(self, tmp_path):
        vault = make_vault(tmp_path / "styled", SAMPLE_DATA)
        emoji = NotebookNavigatorAppearance.load(vault, "emoji")
        assert emoji is not None
        assert emoji.icon_for(vault / "anthologia").startswith("\U0001f4da")

    def test_default_folder_icon_follows_style(self, appearance):
        assert appearance.icon_style == "nerd"
        assert appearance.default_folder_icon(False).startswith("\U000f024b")

    def test_icon_for_unstyled_folder_is_empty(self, appearance):
        assert appearance.icon_for(appearance.vault_root / "veritas") == ""

    def test_icon_for_vault_root_is_empty(self, appearance):
        assert appearance.icon_for(appearance.vault_root) == ""

    def test_icon_for_path_outside_vault_is_empty(self, appearance, tmp_path):
        assert appearance.icon_for(tmp_path / "elsewhere") == ""

    def test_icon_suppressed_when_show_folder_icons_off(self, appearance):
        appearance.show_folder_icons = False
        assert appearance.icon_for(appearance.vault_root / "anthologia") == ""

    def test_color_for_folder(self, appearance):
        assert appearance.color_for(appearance.vault_root / "anthologia") == "#78716c"

    def test_color_inherited_by_descendants(self, appearance):
        nested = appearance.vault_root / "anthologia" / "greek" / "epigrams"
        assert appearance.color_for(nested) == "#78716c"

    def test_nearest_ancestor_color_wins(self, appearance):
        appearance.folder_colors["anthologia/greek"] = "#123456"
        nested = appearance.vault_root / "anthologia" / "greek" / "epigrams"
        assert appearance.color_for(nested) == "#123456"

    def test_inheritance_disabled(self, appearance):
        appearance.inherit_folder_colors = False
        nested = appearance.vault_root / "anthologia" / "greek"
        assert appearance.color_for(nested) is None

    def test_color_for_unstyled_folder_is_none(self, appearance):
        assert appearance.color_for(appearance.vault_root / "veritas") is None

    def test_color_for_vault_root_is_none(self, appearance):
        assert appearance.color_for(appearance.vault_root) is None
