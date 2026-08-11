"""Tests for layered folder appearance and its precedence rules."""

import json

import pytest

from librarian.appearance import (
    ConfigAppearance,
    FolderAppearance,
    build_folder_appearance,
    lookup_with_inheritance,
    relative_key,
)
from librarian.config import (
    CalendarConfig,
    Config,
    FoldersConfig,
    IconConfig,
    ObsidianConfig,
    TagConfig,
)
from librarian.obsidian import PLUGIN_DATA_RELATIVE_PATH, NotebookNavigatorAppearance


@pytest.fixture(autouse=True)
def no_nerd_font_detection(monkeypatch, tmp_path):
    """Pin detection so tests do not depend on the terminal running them."""
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    empty = tmp_path / "no-fonts"
    empty.mkdir()
    monkeypatch.setattr("librarian.icons.FONT_DIRECTORIES", (empty,))


def make_config(root, tmp_path, **overrides):
    """A Config rooted at `root`, with appearance sections overridable."""
    kwargs = dict(
        scan_directory=root,
        editor="vim",
        taskpaper="",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        icons=IconConfig(style="nerd"),
        folders=FoldersConfig(),
        obsidian=ObsidianConfig(),
    )
    kwargs.update(overrides)
    return Config(**kwargs)


def write_plugin_data(root, data):
    """Make `root` an Obsidian vault with Notebook Navigator data."""
    path = root / PLUGIN_DATA_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return root


class TestRelativeKey:
    def test_child_path(self, tmp_path):
        assert relative_key(tmp_path / "a" / "b", tmp_path) == "a/b"

    def test_root_itself_has_no_key(self, tmp_path):
        assert relative_key(tmp_path, tmp_path) is None

    def test_path_outside_root(self, tmp_path):
        assert relative_key(tmp_path.parent / "elsewhere", tmp_path) is None


class TestLookupWithInheritance:
    def test_exact_match(self):
        assert lookup_with_inheritance({"a": "x"}, "a") == "x"

    def test_inherits_from_ancestor(self):
        assert lookup_with_inheritance({"a": "x"}, "a/b/c") == "x"

    def test_nearest_ancestor_wins(self):
        values = {"a": "x", "a/b": "y"}
        assert lookup_with_inheritance(values, "a/b/c") == "y"

    def test_inheritance_can_be_disabled(self):
        assert lookup_with_inheritance({"a": "x"}, "a/b", inherit=False) is None

    def test_missing_key(self):
        assert lookup_with_inheritance({}, "a/b") is None


class TestConfigAppearance:
    def test_icon_and_color(self, tmp_path):
        source = ConfigAppearance(
            root=tmp_path, icons={"projects": "briefcase"}, colors={"projects": "#fff"}
        )
        assert source.icon_name_for(tmp_path / "projects") == "briefcase"
        assert source.color_for(tmp_path / "projects") == "#fff"

    def test_nested_key(self, tmp_path):
        source = ConfigAppearance(root=tmp_path, icons={"a/b": "book"})
        assert source.icon_name_for(tmp_path / "a" / "b") == "book"

    def test_colors_inherit_but_icons_do_not(self, tmp_path):
        source = ConfigAppearance(
            root=tmp_path, icons={"a": "book"}, colors={"a": "#fff"}
        )
        nested = tmp_path / "a" / "b"
        assert source.color_for(nested) == "#fff"
        assert source.icon_name_for(nested) is None

    def test_unset_folder(self, tmp_path):
        source = ConfigAppearance(root=tmp_path)
        assert source.icon_name_for(tmp_path / "whatever") is None
        assert source.color_for(tmp_path / "whatever") is None

    def test_is_empty(self, tmp_path):
        assert ConfigAppearance(root=tmp_path).is_empty()
        assert not ConfigAppearance(root=tmp_path, icons={"a": "book"}).is_empty()


class TestFolderAppearanceDefaults:
    """With no sources at all, folders still render sensibly."""

    def test_falls_back_to_folder_glyph(self, tmp_path):
        appearance = FolderAppearance(glyph_style="nerd")

        assert appearance.icon_name_for(tmp_path / "a") is None
        assert appearance.color_for(tmp_path / "a") is None
        assert appearance.folder_icon(tmp_path / "a").startswith("\U000f024b")

    def test_fallback_tracks_expanded_state(self, tmp_path):
        appearance = FolderAppearance(glyph_style="emoji")

        assert appearance.folder_icon(tmp_path / "a", expanded=False).startswith("\U0001f4c1")
        assert appearance.folder_icon(tmp_path / "a", expanded=True).startswith("\U0001f4c2")

    def test_configured_icon_ignores_expanded_state(self, tmp_path):
        appearance = FolderAppearance(
            glyph_style="nerd",
            sources=(ConfigAppearance(root=tmp_path, icons={"a": "library"}),),
        )
        folder = tmp_path / "a"

        assert appearance.folder_icon(folder, expanded=False) == appearance.folder_icon(
            folder, expanded=True
        )


class TestPrecedence:
    @pytest.fixture
    def layered(self, tmp_path):
        """Config and plugin sources that overlap only partially."""
        root = tmp_path / "vault"
        root.mkdir()
        write_plugin_data(
            root,
            {
                "folderIcons": {"shared": "library", "plugin-only": "computer"},
                "folderColors": {"shared": "#111111", "plugin-only": "#222222"},
            },
        )
        plugin = NotebookNavigatorAppearance.load(root)
        config_source = ConfigAppearance(
            root=root,
            icons={"shared": "rocket", "config-only": "brain"},
            colors={"config-only": "#333333"},
        )
        return root, FolderAppearance(
            glyph_style="nerd", sources=(config_source, plugin)
        )

    def test_config_wins_over_plugin(self, layered):
        root, appearance = layered
        assert appearance.icon_name_for(root / "shared") == "rocket"

    def test_plugin_fills_gaps(self, layered):
        root, appearance = layered
        assert appearance.icon_name_for(root / "plugin-only") == "computer"

    def test_config_only_folder(self, layered):
        root, appearance = layered
        assert appearance.icon_name_for(root / "config-only") == "brain"

    def test_precedence_is_per_key_not_per_source(self, layered):
        """Config sets no color for `shared`, so the plugin's color applies."""
        root, appearance = layered
        assert appearance.icon_name_for(root / "shared") == "rocket"
        assert appearance.color_for(root / "shared") == "#111111"

    def test_unknown_folder_gets_nothing(self, layered):
        root, appearance = layered
        assert appearance.icon_name_for(root / "nope") is None
        assert appearance.color_for(root / "nope") is None


class TestBuildFolderAppearance:
    def test_plain_directory_has_no_sources(self, tmp_path):
        """The no-Obsidian case: defaults only, and it must not raise."""
        root = tmp_path / "notes"
        root.mkdir()
        appearance = build_folder_appearance(make_config(root, tmp_path))

        assert appearance.sources == ()
        assert appearance.folder_icon(root / "anything").startswith("\U000f024b")

    def test_config_only(self, tmp_path):
        root = tmp_path / "notes"
        root.mkdir()
        config = make_config(
            root, tmp_path, folders=FoldersConfig(icons={"a": "library"})
        )
        appearance = build_folder_appearance(config)

        assert len(appearance.sources) == 1
        assert appearance.icon_name_for(root / "a") == "library"

    def test_plugin_picked_up_when_present(self, tmp_path):
        root = write_plugin_data(tmp_path / "vault", {"folderIcons": {"a": "computer"}})
        appearance = build_folder_appearance(make_config(root, tmp_path))

        assert len(appearance.sources) == 1
        assert appearance.icon_name_for(root / "a") == "computer"

    def test_both_layers(self, tmp_path):
        root = write_plugin_data(tmp_path / "vault", {"folderIcons": {"a": "computer"}})
        config = make_config(root, tmp_path, folders=FoldersConfig(colors={"a": "#fff"}))
        appearance = build_folder_appearance(config)

        assert len(appearance.sources) == 2
        assert appearance.icon_name_for(root / "a") == "computer"
        assert appearance.color_for(root / "a") == "#fff"

    def test_obsidian_can_be_disabled(self, tmp_path):
        root = write_plugin_data(tmp_path / "vault", {"folderIcons": {"a": "computer"}})
        config = make_config(root, tmp_path, obsidian=ObsidianConfig(enabled=False))
        appearance = build_folder_appearance(config)

        assert appearance.sources == ()
        assert appearance.icon_name_for(root / "a") is None

    def test_unreadable_plugin_data_degrades(self, tmp_path):
        root = tmp_path / "vault"
        path = root / PLUGIN_DATA_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text("{ broken")
        appearance = build_folder_appearance(make_config(root, tmp_path))

        assert appearance.sources == ()
        assert appearance.folder_icon(root / "a")  # still renders

    def test_style_comes_from_config(self, tmp_path):
        root = tmp_path / "notes"
        root.mkdir()
        config = make_config(root, tmp_path, icons=IconConfig(style="emoji"))
        assert build_folder_appearance(config).glyph_style == "emoji"

    def test_auto_style_is_detected(self, tmp_path):
        root = tmp_path / "notes"
        root.mkdir()
        config = make_config(root, tmp_path, icons=IconConfig(style="auto"))
        # Detection is pinned to no-Nerd-Font by the autouse fixture.
        assert build_folder_appearance(config).glyph_style == "emoji"

    def test_color_icon_only_taken_from_plugin(self, tmp_path):
        root = write_plugin_data(tmp_path / "vault", {"colorIconOnly": True})
        assert build_folder_appearance(make_config(root, tmp_path)).color_icon_only

    def test_color_icon_only_defaults_false_without_plugin(self, tmp_path):
        root = tmp_path / "notes"
        root.mkdir()
        assert not build_folder_appearance(make_config(root, tmp_path)).color_icon_only

    def test_explicit_scan_directory_overrides_config(self, tmp_path):
        """set_scan_directory rebuilds appearance for a different root."""
        configured = tmp_path / "one"
        other = write_plugin_data(tmp_path / "two", {"folderIcons": {"a": "computer"}})
        configured.mkdir()

        appearance = build_folder_appearance(
            make_config(configured, tmp_path), scan_directory=other
        )
        assert appearance.icon_name_for(other / "a") == "computer"
