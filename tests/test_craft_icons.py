"""Tests for Craft folder icons: the appearance layers, config, and rendering.

The Craft REST API does not expose folder icons, so these come from config
(`[craft-folders.icons]` / `[craft-folders.colors]`), falling back to the local
folder appearance for the same relative path -- Craft spaces here mirror the
vault's top-level folders, so a Craft "projects" borrows the local one's look.
"""

import pytest
from rich.style import Style
from textual.app import App, ComposeResult

from librarian.appearance import (
    ConfigAppearance,
    CraftAppearance,
    FolderAppearance,
    build_craft_appearance,
)
from librarian.config import Config, CraftFoldersConfig
from librarian.craft import CraftFolder
from librarian.icons import folder_glyph, resolve_icon
from librarian.widgets.craft_tree import CraftTree


@pytest.fixture
def local(tmp_path) -> FolderAppearance:
    """A local appearance where 'projects' has an icon and a color."""
    source = ConfigAppearance(
        root=tmp_path,
        icons={"projects": "briefcase"},
        colors={"projects": "#8b5cf6"},
    )
    return FolderAppearance(glyph_style="nerd", sources=(source,))


class TestCraftAppearance:
    def test_explicit_craft_icon_wins_over_local(self, tmp_path, local):
        appearance = CraftAppearance(
            glyph_style="nerd",
            icons={"projects": "rocket"},
            local=local,
            local_root=tmp_path,
        )
        assert appearance.icon_name_for("projects") == "rocket"

    def test_same_path_falls_back_to_local_appearance(self, tmp_path, local):
        appearance = CraftAppearance(
            glyph_style="nerd", local=local, local_root=tmp_path
        )
        # The Craft folder need not exist on disk -- the *name* matches.
        assert appearance.icon_name_for("projects") == "briefcase"
        assert appearance.color_for("projects") == "#8b5cf6"

    def test_craft_colors_inherit_to_subfolders(self, tmp_path, local):
        appearance = CraftAppearance(
            glyph_style="nerd",
            colors={"clients": "#ff0000"},
            local=local,
            local_root=tmp_path,
        )
        assert appearance.color_for("clients/2026") == "#ff0000"

    def test_unmatched_folder_gets_default_glyph_and_no_color(self, tmp_path, local):
        appearance = CraftAppearance(
            glyph_style="nerd", local=local, local_root=tmp_path
        )
        assert appearance.icon_name_for("inbox-zero") is None
        assert appearance.color_for("inbox-zero") is None
        assert appearance.folder_icon("inbox-zero") == folder_glyph(False, "nerd")
        assert appearance.folder_icon("inbox-zero", expanded=True) == folder_glyph(
            True, "nerd"
        )

    def test_configured_icon_ignores_expanded_state(self, tmp_path, local):
        appearance = CraftAppearance(
            glyph_style="nerd", local=local, local_root=tmp_path
        )
        expected = resolve_icon("briefcase", "nerd")
        assert appearance.folder_icon("projects") == expected
        assert appearance.folder_icon("projects", expanded=True) == expected

    def test_works_with_no_local_appearance(self):
        appearance = CraftAppearance(glyph_style="emoji", icons={"a": "book"})
        assert appearance.icon_name_for("a") == "book"
        assert appearance.icon_name_for("b") is None
        assert appearance.color_for("a") is None
        assert appearance.color_icon_only is False

    def test_color_icon_only_follows_local(self, tmp_path, local):
        local.color_icon_only = True
        appearance = CraftAppearance(
            glyph_style="nerd", local=local, local_root=tmp_path
        )
        assert appearance.color_icon_only is True


class TestBuildCraftAppearance:
    def test_reuses_the_local_appearance_and_config_tables(self, tmp_path, local):
        config = Config(scan_directory=tmp_path)
        config.craft_folders = CraftFoldersConfig(
            icons={"meetings": "calendar"}, colors={"meetings": "#00ff00"}
        )
        appearance = build_craft_appearance(config, local)
        assert appearance.local is local
        assert appearance.glyph_style == local.glyph_style
        assert appearance.icon_name_for("meetings") == "calendar"
        assert appearance.icon_name_for("projects") == "briefcase"  # via local

    def test_builds_local_appearance_when_not_given(self, tmp_path):
        config = Config(scan_directory=tmp_path)
        appearance = build_craft_appearance(config)
        assert appearance.local is not None
        assert appearance.local_root == tmp_path


class TestConfigRoundTrip:
    def test_craft_folders_survive_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        config = Config(
            scan_directory=tmp_path,
            data_directory=tmp_path / "data",
            export_directory=tmp_path / "exports",
        )
        config.craft_folders = CraftFoldersConfig(
            icons={"projects/2026": "calendar"},
            colors={"projects": "#8b5cf6"},
        )
        config.save()

        loaded = Config.load()
        assert loaded.craft_folders.icons == {"projects/2026": "calendar"}
        assert loaded.craft_folders.colors == {"projects": "#8b5cf6"}

    def test_empty_tables_are_written_commented_out(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        config = Config(
            scan_directory=tmp_path,
            data_directory=tmp_path / "data",
            export_directory=tmp_path / "exports",
        )
        config.save()
        text = (tmp_path / "config" / "librarian" / "config.toml").read_text()
        assert "# [craft-folders.icons]" in text
        assert "\n[craft-folders.icons]" not in text


FOLDERS = [
    CraftFolder(
        id="F1",
        name="projects",
        document_count=2,
        folders=[CraftFolder(id="F2", name="2026", document_count=1)],
    ),
    CraftFolder(id="F3", name="inbox-zero", document_count=0),
]


class TreeHarness(App):
    def __init__(self, appearance: CraftAppearance | None) -> None:
        super().__init__()
        self._appearance = appearance

    def compose(self) -> ComposeResult:
        yield CraftTree(appearance=self._appearance, id="tree")


def make_appearance(root) -> CraftAppearance:
    return CraftAppearance(
        glyph_style="nerd",
        icons={"projects": "briefcase", "projects/2026": "calendar"},
        colors={"projects": "#8b5cf6"},
        local=None,
        local_root=root,
    )


class TestCraftTreeRendering:
    def test_folder_key_walks_ancestors(self, tmp_path):
        tree = CraftTree()
        tree.update_folders(FOLDERS)
        projects = tree.root.children[0]
        assert CraftTree.folder_key(projects) == "projects"
        assert CraftTree.folder_key(projects.children[0]) == "projects/2026"
        assert CraftTree.folder_key(tree.root) is None

    async def test_rendered_labels_carry_icon_and_color(self, tmp_path):
        app = TreeHarness(make_appearance(tmp_path))
        async with app.run_test(size=(60, 20)):
            tree = app.query_one(CraftTree)
            tree.update_folders(FOLDERS)

            projects = tree.root.children[0]
            label = tree.render_label(projects, Style(), Style())
            assert label.plain.startswith(resolve_icon("briefcase", "nerd"))
            assert "#8b5cf6" in str(label.spans)

            # Subfolder: its own icon, the parent's inherited color.
            nested = tree.render_label(projects.children[0], Style(), Style())
            assert nested.plain.startswith(resolve_icon("calendar", "nerd"))
            assert "#8b5cf6" in str(nested.spans)

            # Leaf with no entry anywhere: the plain folder glyph, uncolored.
            other = tree.render_label(tree.root.children[1], Style(), Style())
            assert other.plain.startswith(folder_glyph(False, "nerd"))
            assert "#8b5cf6" not in str(other.spans)

    async def test_placeholder_rows_are_left_alone(self, tmp_path):
        app = TreeHarness(make_appearance(tmp_path))
        async with app.run_test(size=(60, 20)):
            tree = app.query_one(CraftTree)
            tree.show_message("(select to load)")
            row = tree.root.children[0]
            label = tree.render_label(row, Style(), Style())
            assert label.plain == "(select to load)"

    async def test_no_appearance_leaves_stock_rendering(self, tmp_path):
        app = TreeHarness(None)
        async with app.run_test(size=(60, 20)):
            tree = app.query_one(CraftTree)
            tree.update_folders(FOLDERS)
            label = tree.render_label(tree.root.children[0], Style(), Style())
            assert label.plain.endswith("projects (2)")
            assert resolve_icon("briefcase", "nerd") not in label.plain
