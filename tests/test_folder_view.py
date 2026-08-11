"""Tests for folder-first navigation: default tool, panel order, Files panel."""

import pytest

from librarian.config import (
    CalendarConfig,
    Config,
    FoldersConfig,
    IconConfig,
    ObsidianConfig,
    TagConfig,
)
from librarian.database import add_file, batch_writes
from librarian.widgets import FileList, TagList
from librarian.widgets.tag_list import ALL_TOOLS, DEFAULT_TOOLS, ToolItem


@pytest.fixture
def vault(tmp_path):
    """A folder-organized directory: mostly untagged files, some nested."""
    root = tmp_path / "vault"
    (root / "techne").mkdir(parents=True)
    (root / "techne" / "nested").mkdir()
    (root / "veritas").mkdir()  # subfolders only, no direct files

    (root / "root-note.md").write_text("# root\n")
    (root / "techne" / "beta.md").write_text("# beta\n")
    (root / "techne" / "Alpha.md").write_text("# alpha #tagged\n")
    (root / "techne" / "notes.taskpaper").write_text("Inbox:\n")
    (root / "techne" / "nested" / "deep.md").write_text("# deep\n")
    (root / "veritas" / "sub").mkdir()
    return root


@pytest.fixture
def config(vault, tmp_path):
    return Config(
        scan_directory=vault,
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


@pytest.fixture
def app(config, tmp_index):
    """A LibrarianApp with one tagged file in the index."""
    from librarian.app import LibrarianApp

    with batch_writes():
        add_file(config.scan_directory / "techne" / "Alpha.md", 1.0, ["tagged"])

    app = LibrarianApp(config)
    yield app


def folder_of(tree, name):
    """Find a child node of the tree root by folder name."""
    return next(node for node in tree.root.children if node.data.path.name == name)


class TestDefaultTool:
    async def test_opens_on_folders(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            assert tag_list.active_tool == "folders"
            assert not tag_list.query_one("#folders-section").has_class("hidden")
            assert tag_list.query_one("#tags-section").has_class("hidden")

    async def test_tools_menu_highlights_the_active_tool(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            highlighted = tag_list.tools_list_view.highlighted_child

            assert isinstance(highlighted, ToolItem)
            assert highlighted.tool_name == "Folders"

    async def test_startup_focus_is_the_folder_tree(self, app):
        """Browsing starts in the folder tree, not the Tools mode switch."""
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            assert app.focused is tag_list.directory_tree

    async def test_startup_cursor_is_on_the_root_folder(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tree = app.query_one(TagList).directory_tree

            assert tree.cursor_line == 0
            assert tree.cursor_node is tree.root
            assert tree.cursor_node.data.path == app.config.scan_directory

    async def test_arrow_keys_move_the_tree_immediately(self, app):
        """Focus must be live, so navigation works with no extra keypress."""
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tree = app.query_one(TagList).directory_tree
            tree.root.expand()
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()

            assert tree.cursor_line == 1
            assert tree.cursor_node.data.path.name == "techne"


class TestPanelOrder:
    async def test_content_panel_comes_before_tools(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            ids = [child.id for child in tag_list.children]

            assert ids.index("content-panel") < ids.index("tools-panel")

    async def test_focus_order_is_clockwise_from_content(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)
            preview = app.query_one("#preview")

            tag_list.directory_tree.focus()
            await pilot.pause()

            seen = []
            for _ in range(4):
                app.action_focus_next()
                await pilot.pause()
                seen.append(app.focused)

            assert seen == [
                file_list.list_view,
                preview.scroll_view,
                tag_list.tools_list_view,
                tag_list.directory_tree,
            ]


class TestAgentsRemoved:
    def test_not_in_tools_constant(self):
        assert "Agents" not in ALL_TOOLS

    async def test_not_in_tools_menu(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            names = [
                item.tool_name
                for item in tag_list.tools_list_view.children
                if isinstance(item, ToolItem)
            ]

            assert names == list(DEFAULT_TOOLS)
            assert "Agents" not in names

    async def test_placeholder_section_is_gone(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            assert not app.query("#placeholder-section")


class TestFilesFollowFolder:
    async def test_startup_lists_the_scan_directory(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            file_list = app.query_one(FileList)

            assert [f.name for f in file_list._files] == ["root-note.md"]
            assert file_list.get_header_text() == "FILES (vault/)"

    async def test_cursor_move_updates_files(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tree = tag_list.directory_tree
            tree.root.expand()
            await pilot.pause()
            tree.cursor_line = folder_of(tree, "techne").line
            await pilot.pause()

            # Direct children only, sorted, tagged and untagged alike.
            assert [f.name for f in file_list._files] == [
                "Alpha.md",
                "beta.md",
                "notes.taskpaper",
            ]
            assert file_list.get_header_text() == "FILES (techne/)"

    async def test_nested_folder_header_shows_relative_path(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tree = tag_list.directory_tree
            tree.root.expand()
            await pilot.pause()
            techne = folder_of(tree, "techne")
            techne.expand()
            await pilot.pause()
            nested = next(
                n for n in techne.children if n.data.path.name == "nested"
            )
            tree.cursor_line = nested.line
            await pilot.pause()

            assert file_list.get_header_text() == "FILES (techne/nested/)"
            assert [f.name for f in file_list._files] == ["deep.md"]

    async def test_folder_with_no_files_empties_the_panel(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tree = tag_list.directory_tree
            tree.root.expand()
            await pilot.pause()
            tree.cursor_line = folder_of(tree, "veritas").line
            await pilot.pause()

            assert file_list._files == []
            assert file_list.get_header_text() == "FILES (veritas/)"

    async def test_index_update_does_not_clobber_folder_view(self, app):
        """A finished scan must not replace the folder listing with a tag's."""
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tree = tag_list.directory_tree
            tree.root.expand()
            await pilot.pause()
            tree.cursor_line = folder_of(tree, "techne").line
            await pilot.pause()

            app._refresh_file_panel()
            await pilot.pause()
            await pilot.pause()

            assert file_list.get_header_text() == "FILES (techne/)"
            assert "beta.md" in [f.name for f in file_list._files]


class TestSearchExit:
    async def test_focus_returns_to_the_folder_tree(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            await pilot.press("s")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert app.focused is tag_list.directory_tree

    async def test_folder_listing_is_restored(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tree = tag_list.directory_tree
            tree.root.expand()
            await pilot.pause()
            tree.cursor_line = folder_of(tree, "techne").line
            await pilot.pause()
            before = [f.name for f in file_list._files]

            await pilot.press("s")
            await pilot.pause()
            assert file_list._files == []  # search clears the panel

            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()

            assert [f.name for f in file_list._files] == before
            assert file_list.get_header_text() == "FILES (techne/)"

    async def test_tag_listing_is_restored(self, app):
        """The restore follows the active tool, not just the folder view."""
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tag_list._switch_panel("tags")
            await pilot.pause()
            await pilot.pause()

            await pilot.press("s")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()

            assert file_list.get_header_text() == "FILES (#tagged)"
            assert app.focused is tag_list.all_tags_list_view


class TestWithoutNotebookNavigator:
    """The scan directory here is a plain folder — no vault, no plugin."""

    async def test_app_starts_and_lists_folders(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            assert tag_list.active_tool == "folders"
            assert file_list.get_header_text() == "FILES (vault/)"

    async def test_appearance_has_no_sources(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            appearance = app.query_one(TagList).directory_tree.appearance

            assert appearance is not None
            assert appearance.sources == ()

    async def test_folders_render_with_default_glyphs(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tree = app.query_one(TagList).directory_tree
            tree.root.expand()
            await pilot.pause()

            label = tree.render_label(
                folder_of(tree, "techne"), tree.rich_style, tree.rich_style
            )
            assert label.plain.startswith("\U000f024b")  # md-folder
            assert label.plain.endswith("techne")

    async def test_config_icons_apply_without_a_vault(self, config, tmp_index):
        """Librarian's own config is a full replacement for the plugin."""
        from librarian.app import LibrarianApp

        config.folders.icons["techne"] = "computer"
        config.folders.colors["techne"] = "#6b7280"

        app = LibrarianApp(config)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tree = app.query_one(TagList).directory_tree
            tree.root.expand()
            await pilot.pause()

            label = tree.render_label(
                folder_of(tree, "techne"), tree.rich_style, tree.rich_style
            )
            assert label.plain.startswith("\U000f0322")  # md-laptop
            assert any(
                span.style.color and span.style.color.triplet.hex == "#6b7280"
                for span in label.spans
                if span.style.color is not None
            )


class TestToolSwitching:
    async def test_switching_to_tags_shows_tag_files(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tag_list._switch_panel("tags")
            await pilot.pause()
            await pilot.pause()

            assert tag_list.active_tool == "tags"
            assert file_list.get_header_text() == "FILES (#tagged)"

    async def test_switching_back_to_folders_restores_folder_files(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tag_list._switch_panel("tags")
            await pilot.pause()
            await pilot.pause()
            tag_list._switch_panel("folders")
            await pilot.pause()
            await pilot.pause()

            assert file_list.get_header_text() == "FILES (vault/)"
            assert [f.name for f in file_list._files] == ["root-note.md"]

    async def test_folder_cursor_ignored_while_tags_active(self, app):
        """Moving the tree cursor must not hijack the Files panel in tag view."""
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tree = tag_list.directory_tree
            tree.root.expand()
            await pilot.pause()

            tag_list._switch_panel("tags")
            await pilot.pause()
            await pilot.pause()

            tree.cursor_line = folder_of(tree, "techne").line
            await pilot.pause()
            await pilot.pause()

            assert file_list.get_header_text() == "FILES (#tagged)"
