"""Tests for the [tools] tags switch: the tags panel as an optional panel."""

import time

import pytest

from librarian.config import (
    CalendarConfig,
    Config,
    CraftConfig,
    FoldersConfig,
    IconConfig,
    ObsidianConfig,
    TagConfig,
    ToolsConfig,
)
from librarian.craft import CraftDoc, CraftFolder
from librarian.database import add_file, batch_writes
from librarian.widgets import FileList, TagList


class FakeCraft:
    def __init__(self, api_url: str, api_key_ref: str) -> None:
        pass

    def list_folders(self) -> list[CraftFolder]:
        return [CraftFolder(id="F1", name="meetings", document_count=1)]

    def list_documents(self, folder_id: str) -> list[CraftDoc]:
        return [CraftDoc(id="D1", title="Weekly Sync")]

    def fetch_document_markdown(self, doc_id: str) -> str:
        return "body"

    def clear_cache(self) -> None:
        pass


async def wait_until(pilot, predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition not met before timeout")


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "note.md").write_text("# note #tagged\n")
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
        tools=ToolsConfig(tags=False),
        icons=IconConfig(style="nerd"),
        folders=FoldersConfig(),
        obsidian=ObsidianConfig(),
    )


@pytest.fixture
def app(config, tmp_index):
    from librarian.app import LibrarianApp

    with batch_writes():
        add_file(config.scan_directory / "note.md", 1.0, ["tagged"])

    return LibrarianApp(config)


class TestConfig:
    def test_tags_defaults_on(self):
        assert ToolsConfig().tags is True
        assert ToolsConfig().is_enabled("tags")

    def test_missing_key_backfills_true(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        path = config_dir / "config.toml"
        path.write_text(
            f'scan_directory = "{tmp_path}"\n'
            f'data_directory = "{tmp_path / "data"}"\n'
            "[tools]\n"
            "folders = true\n"
        )
        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("librarian.config.get_config_path", lambda: path)

        config = Config.load()

        assert config.tools.tags is True
        assert "tags = true" in path.read_text()

    def test_save_writes_the_switch(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "config"
        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr(
            "librarian.config.get_config_path",
            lambda: config_dir / "config.toml",
        )
        Config(
            scan_directory=tmp_path,
            data_directory=tmp_path / "data",
            tools=ToolsConfig(tags=False),
        ).save()
        assert "tags = false" in (config_dir / "config.toml").read_text()


class TestTagsOff:
    async def test_tags_panel_is_gone(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            assert tag_list.all_tags_list_view is None
            ids = [child.id for child in tag_list.children]
            assert ids == ["folders-panel"]

    async def test_folders_still_lead(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            assert tag_list.active_source == "folders"
            assert app.focused is tag_list.directory_tree

    async def test_tab_cycle_skips_the_missing_panel(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            tag_list.directory_tree.focus()
            await pilot.pause()
            app.action_focus_next()
            await pilot.pause()

            assert app.focused is file_list.list_view

    async def test_index_updates_do_not_crash(self, app):
        """update_tags must be a no-op, not a NoMatches crash."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app._refresh_tags()
            await pilot.pause()

    async def test_t_warns_instead_of_crashing(self, app):
        app.config.tools.taskpaper = True
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("t")
            await pilot.pause()
            # No crash; the Files panel keeps the folder view.
            assert app.query_one(TagList).active_source == "folders"

    async def test_search_exit_falls_back_to_the_folder_tree(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app.action_search()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert app.focused is app.query_one(TagList).directory_tree


class TestCraftOnly:
    async def test_craft_leads_when_it_is_the_only_panel(
        self, config, tmp_index, monkeypatch
    ):
        """folders=false, tags=false, craft=true: the Craft tree gets startup
        focus, which triggers its first load -- loading it is the point."""
        from librarian.app import LibrarianApp

        monkeypatch.setattr(
            "librarian.actions.craft_actions.CraftClient", FakeCraft
        )
        config.tools = ToolsConfig(folders=False, tags=False, craft=True)
        config.craft = CraftConfig(api_url="https://x/api/v1", api_key_ref="op://x/y/z")
        app = LibrarianApp(config)

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            assert tag_list.active_source == "craft"
            assert app.focused is tag_list.craft_tree
            await wait_until(
                pilot,
                lambda: any(
                    "meetings" in str(n.label)
                    for n in tag_list.craft_tree.root.children
                ),
            )

    async def test_everything_off_still_starts(self, config, tmp_index):
        from librarian.app import LibrarianApp

        config.tools = ToolsConfig(folders=False, tags=False)
        app = LibrarianApp(config)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            ids = [child.id for child in app.query_one(TagList).children]
            assert ids == []
