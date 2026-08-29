"""Tests for the full-width tool tab strip (docs/plans/tool-tabs.md).

Two kinds of tab: workspace tabs (Local Folders, Craft Docs) switch what the
sidebar and Files panel show; launcher tabs (TaskPaper, Reminders, Calendar,
Projects) launch the tool -- modals stay modals -- and snap the strip back to
the last workspace tab. Only tools set true in [tools] expose a tab.
"""

import pytest
from textual.widgets import Static

from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets import FileList, TagList, ToolTabs
from librarian.widgets.calendar_modal import CalendarModal
from tests.test_calendar import _parse_event, raw_event
from tests.test_craft_panel import FakeCraft


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "note.md").write_text("# note #tagged\n")
    (root / "sub").mkdir()
    return root


def make_config(vault, tmp_path, **tools) -> Config:
    return Config(
        scan_directory=vault,
        editor="vim",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        tools=ToolsConfig(**tools),
    )


@pytest.fixture
def app_all_tools(vault, tmp_path, tmp_index, monkeypatch):
    """Every tool enabled, Craft faked, calendar fetch faked."""
    from librarian.app import LibrarianApp
    from librarian.calendar_store import init_store

    monkeypatch.setattr("librarian.actions.craft_actions.CraftClient", FakeCraft)
    event = _parse_event(raw_event(title="Standup"))
    monkeypatch.setattr(
        "librarian.actions.calendar_actions.fetch_todays_events",
        lambda *a, **kw: [event],
    )
    init_store(tmp_path / "store")
    config = make_config(
        vault,
        tmp_path,
        taskpaper=True,
        reminders=True,
        calendar=True,
        projects=True,
        craft=True,
    )
    return LibrarianApp(config)


def tab_ids(app) -> list[str]:
    return [tab.id for tab in app.query_one(ToolTabs).query("Tab")]


def tags_header(app) -> str:
    tag_list = app.query_one(TagList)
    return str(tag_list.query_one("#all-tags-header", Static).render())


class TestStrip:
    async def test_default_config_shows_only_local_folders(
        self, vault, tmp_path, tmp_index
    ):
        from librarian.app import LibrarianApp

        app = LibrarianApp(make_config(vault, tmp_path))
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            assert tab_ids(app) == ["tab-local"]
            assert app.query_one(ToolTabs).active == "tab-local"

    async def test_every_enabled_tool_gets_a_tab_in_catalog_order(
        self, app_all_tools
    ):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            assert tab_ids(app_all_tools) == [
                "tab-local",
                "tab-craft",
                "tab-taskpaper",
                "tab-reminders",
                "tab-calendar",
                "tab-projects",
            ]

    async def test_craft_only_config_starts_on_the_craft_tab(
        self, vault, tmp_path, tmp_index, monkeypatch
    ):
        from librarian.app import LibrarianApp

        monkeypatch.setattr(
            "librarian.actions.craft_actions.CraftClient", FakeCraft
        )
        config = make_config(vault, tmp_path, folders=False, tags=False, craft=True)
        app = LibrarianApp(config)
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            assert tab_ids(app) == ["tab-craft"]
            assert app.query_one(ToolTabs).active == "tab-craft"
            assert app.query_one(TagList).workspace == "craft"

    async def test_the_tools_panel_is_gone(self, app_all_tools):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tag_list = app_all_tools.query_one(TagList)
            assert not tag_list.query("#tools-panel")
            ids = [child.id for child in tag_list.children]
            assert ids == ["folders-panel", "craft-panel", "tags-panel"]


class TestWorkspaceTabs:
    async def test_startup_shows_the_local_workspace(self, app_all_tools):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tag_list = app_all_tools.query_one(TagList)
            assert tag_list.workspace == "folders"
            assert tag_list.query_one("#folders-panel").display
            assert not tag_list.query_one("#craft-panel").display
            assert tags_header(app_all_tools) == "ALL TAGS"

    async def test_activating_craft_docs_switches_the_workspace(
        self, app_all_tools
    ):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            app_all_tools.query_one(ToolTabs).active = "tab-craft"
            await pilot.pause()
            await pilot.pause()

            tag_list = app_all_tools.query_one(TagList)
            assert tag_list.workspace == "craft"
            assert not tag_list.query_one("#folders-panel").display
            assert tag_list.query_one("#craft-panel").display
            assert tag_list.active_source == "craft"
            assert tags_header(app_all_tools) == "CRAFT TAGS"
            # First activation focuses the tree, which triggers the lazy fetch.
            assert app_all_tools.focused is tag_list.craft_tree

    async def test_switching_back_restores_the_folder_listing(self, app_all_tools):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tabs = app_all_tools.query_one(ToolTabs)
            tabs.active = "tab-craft"
            await pilot.pause()
            tabs.active = "tab-local"
            await pilot.pause()
            await pilot.pause()

            tag_list = app_all_tools.query_one(TagList)
            assert tag_list.workspace == "folders"
            assert tag_list.active_source == "folders"
            assert tags_header(app_all_tools) == "ALL TAGS"
            file_list = app_all_tools.query_one(FileList)
            assert "note.md" in [p.name for p in file_list._files]


class TestFocusCycle:
    async def test_tab_cycle_includes_the_strip_and_skips_the_hidden_tree(
        self, app_all_tools
    ):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tag_list = app_all_tools.query_one(TagList)
            file_list = app_all_tools.query_one(FileList)
            preview = app_all_tools.query_one("#preview")
            tabs = app_all_tools.query_one(ToolTabs)

            tag_list.directory_tree.focus()
            await pilot.pause()

            seen = []
            for _ in range(5):
                app_all_tools.action_focus_next()
                await pilot.pause()
                seen.append(app_all_tools.focused)

            # The Craft tree is composed but hidden (its tab is not active),
            # so it is not a stop; the strip is.
            assert seen == [
                tag_list.all_tags_list_view,
                file_list.list_view,
                preview.scroll_view,
                tabs,
                tag_list.directory_tree,
            ]

    async def test_the_active_workspaces_tree_is_the_one_in_the_cycle(
        self, app_all_tools
    ):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tag_list = app_all_tools.query_one(TagList)
            tabs = app_all_tools.query_one(ToolTabs)
            tabs.active = "tab-craft"
            await pilot.pause()
            await pilot.pause()

            tabs.focus()
            await pilot.pause()
            app_all_tools.action_focus_next()
            await pilot.pause()

            assert app_all_tools.focused is tag_list.craft_tree


class TestLauncherTabs:
    async def test_calendar_tab_opens_the_modal_and_snaps_back(self, app_all_tools):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tabs = app_all_tools.query_one(ToolTabs)
            tabs.active = "tab-calendar"
            for _ in range(20):
                await pilot.pause()
                if isinstance(app_all_tools.screen, CalendarModal):
                    break

            assert isinstance(app_all_tools.screen, CalendarModal)
            assert tabs.active == "tab-local"

    async def test_closing_the_modal_leaves_the_workspace_untouched(
        self, app_all_tools
    ):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tabs = app_all_tools.query_one(ToolTabs)
            tabs.active = "tab-calendar"
            for _ in range(20):
                await pilot.pause()
                if isinstance(app_all_tools.screen, CalendarModal):
                    break
            await pilot.press("escape")
            await pilot.pause()

            tag_list = app_all_tools.query_one(TagList)
            assert not isinstance(app_all_tools.screen, CalendarModal)
            assert tag_list.workspace == "folders"
            assert tag_list.active_source == "folders"

    async def test_launcher_from_craft_workspace_snaps_back_to_craft(
        self, app_all_tools
    ):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tabs = app_all_tools.query_one(ToolTabs)
            tabs.active = "tab-craft"
            await pilot.pause()
            tabs.active = "tab-calendar"
            for _ in range(20):
                await pilot.pause()
                if isinstance(app_all_tools.screen, CalendarModal):
                    break

            assert isinstance(app_all_tools.screen, CalendarModal)
            assert tabs.active == "tab-craft"
            assert app_all_tools.query_one(TagList).workspace == "craft"

    async def test_taskpaper_tab_pulls_the_strip_to_the_local_workspace(
        self, app_all_tools
    ):
        async with app_all_tools.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tabs = app_all_tools.query_one(ToolTabs)
            tabs.active = "tab-craft"
            await pilot.pause()
            tabs.active = "tab-taskpaper"
            await pilot.pause()
            await pilot.pause()

            # #taskpaper is a local tag, so the strip lands on Local Folders --
            # not on the Craft workspace the launcher was pressed from.
            assert tabs.active == "tab-local"
            tag_list = app_all_tools.query_one(TagList)
            assert tag_list.workspace == "folders"
            assert tag_list.tags_scope == "local"


class TestAcceptance:
    """The tool-tabs acceptance gate (docs/plans/tool-tabs.md, phase 15).

    One flow across every moving part: startup on Local Folders, a workspace
    switch to Craft Docs with the tags scope following, a launcher tab opening
    its modal and snapping back, and the folder listing intact afterwards.
    """

    async def test_the_whole_flow(self, app_all_tools):
        app = app_all_tools
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            tabs = app.query_one(ToolTabs)
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            # Startup: Local Folders tab, folder tree leading, local tags.
            assert tabs.active == "tab-local"
            assert tag_list.workspace == "folders"
            assert tags_header(app) == "ALL TAGS"
            assert "note.md" in [p.name for p in file_list._files]

            # Switch to Craft Docs: tree flips, tags scope follows.
            tabs.active = "tab-craft"
            await pilot.pause()
            await pilot.pause()
            assert tag_list.workspace == "craft"
            assert tags_header(app) == "CRAFT TAGS"
            assert tag_list.active_source == "craft"

            # A launcher tab opens its modal and snaps back to Craft Docs.
            tabs.active = "tab-calendar"
            for _ in range(20):
                await pilot.pause()
                if isinstance(app.screen, CalendarModal):
                    break
            assert isinstance(app.screen, CalendarModal)
            assert tabs.active == "tab-craft"

            # Close it: the Craft workspace is exactly where it was.
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, CalendarModal)
            assert tag_list.workspace == "craft"
            assert tag_list.active_source == "craft"

            # And back to Local Folders: the folder listing returns.
            tabs.active = "tab-local"
            await pilot.pause()
            await pilot.pause()
            assert tags_header(app) == "ALL TAGS"
            assert "note.md" in [p.name for p in file_list._files]
