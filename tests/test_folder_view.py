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
from librarian.widgets.tag_list import ALL_TOOLS
from librarian.widgets.tool_tabs import ToolTabs, launcher_tool_for


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


def select_tag(tag_list, name):
    """Select a tag in the Tags panel, as clicking or pressing enter would."""
    from librarian.widgets.tag_list import TagItem

    tags = tag_list.all_tags_list_view
    for index, item in enumerate(tags.children):
        if isinstance(item, TagItem) and item.tag_name == name:
            tags.index = index
            tag_list.on_list_view_selected(
                type("Selected", (), {"item": item})()
            )
            return
    raise AssertionError(f"no tag named {name!r}")


def folder_of(tree, name):
    """Find a child node of the tree root by folder name."""
    return next(node for node in tree.root.children if node.data.path.name == name)


class TestThreePanels:
    async def test_folders_and_tags_are_both_visible(self, app):
        """The point of the three-panel sidebar: no switching between them."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            assert tag_list.directory_tree.is_mounted
            assert tag_list.all_tags_list_view.is_mounted
            assert tag_list.directory_tree.display
            assert tag_list.all_tags_list_view.display

    async def test_folders_drives_the_files_panel_at_startup(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert app.query_one(TagList).active_source == "folders"

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
    async def test_panels_run_folders_then_tags(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            ids = [child.id for child in app.query_one(TagList).children]

            assert ids == ["folders-panel", "tags-panel"]

    async def test_focus_order_goes_down_the_left_then_the_right(self, app):
        """Tab cycles the sidebar panels, then Files, then Preview."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)
            preview = app.query_one("#preview")

            tag_list.directory_tree.focus()
            await pilot.pause()

            seen = []
            for _ in range(5):
                app.action_focus_next()
                await pilot.pause()
                seen.append(app.focused)

            assert seen == [
                tag_list.all_tags_list_view,
                file_list.list_view,
                preview.scroll_view,
                app.query_one("#tool-tabs"),
                tag_list.directory_tree,
            ]

    async def test_enabled_launchers_do_not_add_focus_stops(self, config, tmp_index):
        """Launchers live in the tab strip, not the panel focus cycle."""
        from librarian.app import LibrarianApp
        from librarian.config import ToolsConfig

        config.tools = ToolsConfig(reminders=True)
        app = LibrarianApp(config)

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tag_list.all_tags_list_view.focus()
            await pilot.pause()
            app.action_focus_next()
            await pilot.pause()

            assert app.focused is file_list.list_view

    async def test_shift_tab_walks_back_up(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            tag_list.all_tags_list_view.focus()
            await pilot.pause()
            app.action_focus_previous()
            await pilot.pause()

            assert app.focused is tag_list.directory_tree


class TestAgentsRemoved:
    def test_not_in_tools_constant(self):
        assert "Agents" not in ALL_TOOLS

    async def test_not_in_the_tab_strip(self, app):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            names = [
                str(tab.label) for tab in app.query_one(ToolTabs).query("Tab")
            ]
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
        """The restore follows whichever panel drives Files, not just Folders."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            select_tag(tag_list, "tagged")
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
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            assert tag_list.active_source == "folders"
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


class TestFilesFollowsTheLastPanelTouched:
    """Both panels are visible, so the last one used drives the Files list."""

    async def test_selecting_a_tag_switches_the_source(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            select_tag(tag_list, "tagged")
            await pilot.pause()
            await pilot.pause()

            assert tag_list.active_source == "tags"
            assert file_list.get_header_text() == "FILES (#tagged)"

    async def test_moving_the_folder_cursor_switches_back(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tree = tag_list.directory_tree
            tree.root.expand()
            await pilot.pause()

            select_tag(tag_list, "tagged")
            await pilot.pause()
            await pilot.pause()
            assert file_list.get_header_text() == "FILES (#tagged)"

            tree.cursor_line = folder_of(tree, "techne").line
            await pilot.pause()
            await pilot.pause()

            assert tag_list.active_source == "folders"
            assert file_list.get_header_text() == "FILES (techne/)"

    async def test_index_updates_respect_the_tag_source(self, app):
        """A rescan must not drag the Files panel back to a folder."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            select_tag(tag_list, "tagged")
            await pilot.pause()
            await pilot.pause()

            app._refresh_file_panel()
            await pilot.pause()
            await pilot.pause()

            assert file_list.get_header_text() == "FILES (#tagged)"


class TestSidebarProportions:
    """The visible tree and the Tags panel split the sidebar 50/50."""

    async def test_folders_and_tags_are_equal_height(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            folders = tag_list.query_one("#folders-panel").region
            tags = tag_list.query_one("#tags-panel").region

            assert abs(folders.height - tags.height) <= 1, (
                f"folders={folders.height} tags={tags.height}"
            )

    async def test_panels_run_folders_then_tags(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            assert [c.id for c in tag_list.children] == [
                "folders-panel",
                "tags-panel",
            ]
            tops = [
                tag_list.query_one(f"#{pid}").region.y
                for pid in ("folders-panel", "tags-panel")
            ]
            assert tops == sorted(tops), f"panels are not stacked in order: {tops}"
