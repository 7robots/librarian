"""Tests for the [tools] folders switch: the folder browser as an optional panel."""

import pytest

from librarian.config import (
    CalendarConfig,
    Config,
    FoldersConfig,
    IconConfig,
    ObsidianConfig,
    TagConfig,
    ToolsConfig,
)
from librarian.database import add_file, batch_writes
from librarian.widgets import FileList, TagList


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / "techne").mkdir(parents=True)
    (root / "root-note.md").write_text("# root\n")
    (root / "techne" / "Alpha.md").write_text("# alpha #tagged\n")
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
        tools=ToolsConfig(folders=False),
        icons=IconConfig(style="nerd"),
        folders=FoldersConfig(),
        obsidian=ObsidianConfig(),
    )


@pytest.fixture
def app(config, tmp_index):
    """A LibrarianApp with the folder browser off and one tagged file indexed."""
    from librarian.app import LibrarianApp

    with batch_writes():
        add_file(config.scan_directory / "techne" / "Alpha.md", 1.0, ["tagged"])

    return LibrarianApp(config)


class TestConfig:
    def test_folders_defaults_on(self):
        assert ToolsConfig().folders is True
        assert ToolsConfig().is_enabled("folders")

    def test_load_reads_the_switch(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            f'scan_directory = "{tmp_path}"\n'
            f'data_directory = "{tmp_path / "data"}"\n'
            "[tools]\n"
            "folders = false\n"
        )
        monkeypatch.setattr(
            "librarian.config.get_config_dir", lambda: config_dir
        )
        monkeypatch.setattr(
            "librarian.config.get_config_path",
            lambda: config_dir / "config.toml",
        )
        assert Config.load().tools.folders is False

    def test_missing_key_backfills_true(self, tmp_path, monkeypatch):
        """A config written before the switch existed gains it, defaulted on."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        path = config_dir / "config.toml"
        path.write_text(
            f'scan_directory = "{tmp_path}"\n'
            f'data_directory = "{tmp_path / "data"}"\n'
            "[tools]\n"
            "taskpaper = false\n"
        )
        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("librarian.config.get_config_path", lambda: path)

        config = Config.load()

        assert config.tools.folders is True
        assert "folders = true" in path.read_text()

    def test_save_writes_the_switch(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "config"
        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr(
            "librarian.config.get_config_path",
            lambda: config_dir / "config.toml",
        )
        config = Config(
            scan_directory=tmp_path,
            data_directory=tmp_path / "data",
            tools=ToolsConfig(folders=False),
        )
        config.save()
        assert "folders = false" in (config_dir / "config.toml").read_text()


class TestFoldersOff:
    async def test_folders_panel_is_gone(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            ids = [child.id for child in tag_list.children]
            assert ids == ["tags-panel"]
            assert tag_list.directory_tree is None

    async def test_tags_drive_the_files_panel(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert app.query_one(TagList).active_source == "tags"

    async def test_startup_focus_is_the_tags_list(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            assert app.focused is tag_list.all_tags_list_view

    async def test_startup_shows_the_highlighted_tags_files(self, app):
        """With no folder tree to lead, the first tag fills the Files panel."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            file_list = app.query_one(FileList)
            assert [p.name for p in file_list._files] == ["Alpha.md"]

    async def test_tab_cycle_skips_the_missing_tree(self, app):
        """The cycle is tags, files, preview, then the tab strip."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)
            preview = app.query_one("#preview")

            seen = []
            for _ in range(4):
                app.action_focus_next()
                await pilot.pause()
                seen.append(app.focused)

            assert seen == [
                file_list.list_view,
                preview.scroll_view,
                app.query_one("#tool-tabs"),
                tag_list.all_tags_list_view,
            ]

    async def test_index_update_keeps_the_tag_listing(self, app):
        """_refresh_file_panel must follow the tags source, not crash on folders."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app._refresh_file_panel()
            await pilot.pause()

            file_list = app.query_one(FileList)
            assert [p.name for p in file_list._files] == ["Alpha.md"]

    async def test_search_exit_returns_to_the_tags_list(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app.action_search()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            tag_list = app.query_one(TagList)
            assert app.focused is tag_list.all_tags_list_view

    async def test_vim_left_lands_on_the_tags_list(self, app):
        """The remembered left-column panel is the tree; it must fall back."""
        app.config.keys.vim = True
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            file_list = app.query_one(FileList)
            file_list.list_view.focus()
            await pilot.pause()

            await pilot.press("ctrl+w")
            await pilot.press("h")
            await pilot.pause()

            tag_list = app.query_one(TagList)
            assert app.focused is tag_list.all_tags_list_view


class TestFoldersOnByDefault:
    async def test_default_config_still_shows_the_tree(self, config, tmp_index):
        from librarian.app import LibrarianApp

        config.tools = ToolsConfig()
        app = LibrarianApp(config)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            assert tag_list.directory_tree is not None
            assert tag_list.active_source == "folders"
            assert app.focused is tag_list.directory_tree
