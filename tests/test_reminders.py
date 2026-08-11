"""Tests for the Reminders tool, which hands the terminal to remtui."""

import pytest

from librarian.actions.reminders_actions import (
    DEFAULT_REMINDERS_COMMAND,
    resolve_reminders_command,
)
from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets import TagList
from librarian.widgets.tag_list import ALL_TOOLS, LAUNCHER_TOOLS, ToolItem


class TestResolveCommand:
    def test_defaults_to_remtui_on_path(self, monkeypatch):
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.shutil.which",
            lambda name: "/usr/local/bin/remtui" if name == "remtui" else None,
        )
        assert resolve_reminders_command("") == "/usr/local/bin/remtui"

    def test_configured_name_looked_up_on_path(self, monkeypatch):
        seen = {}

        def fake_which(name):
            seen["name"] = name
            return "/opt/bin/mytui"

        monkeypatch.setattr(
            "librarian.actions.reminders_actions.shutil.which", fake_which
        )
        assert resolve_reminders_command("mytui") == "/opt/bin/mytui"
        assert seen["name"] == "mytui"

    def test_absolute_path_used_directly(self, tmp_path):
        binary = tmp_path / "remtui"
        binary.write_text("#!/bin/sh\n")
        assert resolve_reminders_command(str(binary)) == str(binary)

    def test_missing_absolute_path_is_none(self, tmp_path):
        assert resolve_reminders_command(str(tmp_path / "nope")) is None

    def test_missing_from_path_is_none(self, monkeypatch):
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.shutil.which", lambda name: None
        )
        assert resolve_reminders_command("") is None

    def test_whitespace_only_config_falls_back_to_default(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.shutil.which",
            lambda name: seen.setdefault("name", name) and None,
        )
        resolve_reminders_command("   ")
        assert seen["name"] == DEFAULT_REMINDERS_COMMAND


class TestToolsMenu:
    def test_reminders_is_a_tool(self):
        assert "Reminders" in ALL_TOOLS

    def test_reminders_is_a_launcher_not_a_panel(self):
        assert "reminders" in LAUNCHER_TOOLS


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    return Config(
        scan_directory=root,
        editor="vim",
        taskpaper="",
        reminders="",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        tools=ToolsConfig(reminders=True),
    )


@pytest.fixture
def app(config, tmp_index):
    from librarian.app import LibrarianApp

    return LibrarianApp(config)


class FakeSuspend:
    """Stands in for App.suspend(), recording that it was entered."""

    def __init__(self):
        self.entered = False

    def __call__(self):
        return self

    def __enter__(self):
        self.entered = True
        return None

    def __exit__(self, *exc):
        return False


class TestLaunching:
    async def test_selecting_the_tool_launches_remtui(self, app, monkeypatch, tmp_path):
        """End to end: picking Reminders from the menu suspends and runs remtui."""
        binary = tmp_path / "remtui"
        binary.write_text("#!/bin/sh\n")
        app.config.reminders = str(binary)

        calls = []
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            suspend = FakeSuspend()
            monkeypatch.setattr(app, "suspend", suspend)

            tag_list = app.query_one(TagList)
            tools = tag_list.tools_list_view
            tools.focus()  # startup focus is the folder tree; Tab reaches Tools
            await pilot.pause()

            item = next(
                i
                for i in tools.children
                if isinstance(i, ToolItem) and i.tool_name == "Reminders"
            )
            tools.index = list(tools.children).index(item)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            assert suspend.entered
            assert calls == [[str(binary)]]

    async def test_missing_binary_notifies_instead_of_launching(
        self, app, monkeypatch
    ):
        app.config.reminders = "definitely-not-installed"
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.shutil.which", lambda name: None
        )

        calls = []
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            suspend = FakeSuspend()
            monkeypatch.setattr(app, "suspend", suspend)

            app.action_launch_reminders()
            await pilot.pause()

            assert calls == []
            assert not suspend.entered
            notifications = [n.message for n in app._notifications]
            assert any("definitely-not-installed" in m for m in notifications)

    async def test_subprocess_failure_is_reported(self, app, monkeypatch, tmp_path):
        binary = tmp_path / "remtui"
        binary.write_text("#!/bin/sh\n")
        app.config.reminders = str(binary)

        def boom(cmd, **kw):
            raise OSError("exec format error")

        monkeypatch.setattr(
            "librarian.actions.reminders_actions.subprocess.run", boom
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(app, "suspend", FakeSuspend())

            app.action_launch_reminders()
            await pilot.pause()

            notifications = [n.message for n in app._notifications]
            assert any("exec format error" in m for m in notifications)

    async def test_launching_leaves_the_panels_alone(self, app, monkeypatch, tmp_path):
        """Reminders is not a panel, so the content panel must not change."""
        binary = tmp_path / "remtui"
        binary.write_text("#!/bin/sh\n")
        app.config.reminders = str(binary)
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.subprocess.run", lambda cmd, **kw: None
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(app, "suspend", FakeSuspend())

            tag_list = app.query_one(TagList)
            before = tag_list.active_tool

            app.action_launch_reminders()
            await pilot.pause()

            assert tag_list.active_tool == before == "folders"
            assert not tag_list.query_one("#folders-section").has_class("hidden")


class TestOptionalTools:
    """Task tools are opt-in; their code stays live either way."""

    async def menu_names(self, app, pilot):
        await pilot.pause()
        return [
            item.tool_name
            for item in app.query_one(TagList).tools_list_view.children
            if isinstance(item, ToolItem)
        ]

    def app_with(self, config, **flags):
        from librarian.app import LibrarianApp

        config.tools = ToolsConfig(**flags)
        return LibrarianApp(config)

    async def test_all_optional_tools_hidden_by_default(self, config, tmp_index):
        """Only the tools needing no third-party program are shown."""
        app = self.app_with(config)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await self.menu_names(app, pilot) == ["Tags", "Folders"]

    async def test_only_calendar(self, config, tmp_index):
        app = self.app_with(config, calendar=True)
        async with app.run_test(size=(100, 30)) as pilot:
            names = await self.menu_names(app, pilot)
            assert names == ["Tags", "Folders", "Calendar"]

    async def test_only_taskpaper(self, config, tmp_index):
        app = self.app_with(config, taskpaper=True)
        async with app.run_test(size=(100, 30)) as pilot:
            names = await self.menu_names(app, pilot)
            assert "TaskPaper" in names
            assert "Reminders" not in names

    async def test_only_reminders(self, config, tmp_index):
        app = self.app_with(config, reminders=True)
        async with app.run_test(size=(100, 30)) as pilot:
            names = await self.menu_names(app, pilot)
            assert "Reminders" in names
            assert "TaskPaper" not in names

    async def test_all_enabled(self, config, tmp_index):
        app = self.app_with(config, taskpaper=True, reminders=True, calendar=True)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await self.menu_names(app, pilot) == list(ALL_TOOLS)

    async def test_menu_order_is_stable(self, config, tmp_index):
        """Enabling a tool inserts it in catalog order, not at the end."""
        app = self.app_with(config, taskpaper=True, reminders=True, calendar=True)
        async with app.run_test(size=(100, 30)) as pilot:
            names = await self.menu_names(app, pilot)
            assert names.index("TaskPaper") < names.index("Reminders")
            assert names.index("Reminders") < names.index("Calendar")


class TestDisabledToolsAreUnreachable:
    """A hidden tool must not stay reachable by shortcut or action."""

    def app_with(self, config, **flags):
        from librarian.app import LibrarianApp

        config.tools = ToolsConfig(**flags)
        return LibrarianApp(config)

    async def test_taskpaper_action_is_inert(self, config, tmp_index):
        app = self.app_with(config)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_launch_taskpaper()
            await pilot.pause()

            assert app.query_one(TagList).active_tool == "folders"
            assert any("TaskPaper is off" in n.message for n in app._notifications)

    async def test_reminders_action_is_inert(self, config, tmp_index, monkeypatch):
        app = self.app_with(config)
        calls = []
        monkeypatch.setattr(
            "librarian.actions.reminders_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            suspend = FakeSuspend()
            monkeypatch.setattr(app, "suspend", suspend)

            app.action_launch_reminders()
            await pilot.pause()

            assert calls == []
            assert not suspend.entered
            assert any("Reminders is off" in n.message for n in app._notifications)

    async def test_taskpaper_action_works_when_enabled(self, config, tmp_index):
        app = self.app_with(config, taskpaper=True)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_launch_taskpaper()
            await pilot.pause()

            # No #taskpaper tag in this index, so it warns rather than switching,
            # but it must reach that code path rather than being gated out.
            assert not any("TaskPaper is off" in n.message for n in app._notifications)

    async def test_calendar_panel_explains_it_is_off(self, config, tmp_index):
        """The panel is unreachable from the menu, but the fetch guard still holds."""
        app = self.app_with(config)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            app._fetch_calendar_events()
            await pilot.pause()

            status = str(tag_list.calendar_list.status_label.render())
            assert "Calendar is off" in status

    async def test_help_omits_shortcuts_for_hidden_tools(self, config, tmp_index):
        app = self.app_with(config)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_help()
            await pilot.pause()

            help_text = next(
                n.message for n in app._notifications if "s=Search" in n.message
            )
            assert "t=TaskPaper" not in help_text
            assert "a=Associate" not in help_text

    async def test_taskpaper_files_still_supported(self, config, tmp_index):
        """Hiding the tools must not stop .taskpaper files being indexed."""
        from librarian.scanner import SUPPORTED_EXTENSIONS, list_folder_files

        assert ".taskpaper" in SUPPORTED_EXTENSIONS

        (config.scan_directory / "todo.taskpaper").write_text(
            "Inbox:\n\t- x #taskpaper\n"
        )
        assert [p.name for p in list_folder_files(config.scan_directory)] == [
            "todo.taskpaper"
        ]
