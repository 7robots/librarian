"""Tests for the Reminders tool, which hands the terminal to remtui."""

import pytest

from librarian.actions.reminders_actions import (
    DEFAULT_REMINDERS_COMMAND,
    resolve_reminders_command,
)
from librarian.config import CalendarConfig, Config, TagConfig
from librarian.widgets import TagList
from librarian.widgets.tag_list import LAUNCHER_TOOLS, TOOLS, ToolItem


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
        assert "Reminders" in TOOLS

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
        calendar=CalendarConfig(enabled=False),
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
