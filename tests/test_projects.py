"""Tests for the Projects tool, which embeds projection or hands off to it.

Nothing here needs projection installed: the embedded path is covered in
`test_projects_panel.py`, which skips without it. These tests cover the parts
Librarian owns either way -- resolving the executable, the opt-in gate, and the
fallback when the package is not importable.
"""

import pytest

from librarian.actions.projects_actions import (
    DEFAULT_PROJECTS_COMMAND,
    resolve_projects_command,
)
from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets import TagList
from librarian.widgets.tag_list import ALL_TOOLS
from librarian.widgets.tool_tabs import LAUNCHER_TAB_IDS, ToolTabs, launcher_tool_for


class TestResolveCommand:
    def test_defaults_to_projection_on_path(self, monkeypatch):
        monkeypatch.setattr(
            "librarian.actions.projects_actions.shutil.which",
            lambda name: "/usr/local/bin/projection" if name == "projection" else None,
        )
        assert resolve_projects_command("") == "/usr/local/bin/projection"

    def test_configured_name_looked_up_on_path(self, monkeypatch):
        seen = {}

        def fake_which(name):
            seen["name"] = name
            return "/opt/bin/mytui"

        monkeypatch.setattr(
            "librarian.actions.projects_actions.shutil.which", fake_which
        )
        assert resolve_projects_command("mytui") == "/opt/bin/mytui"
        assert seen["name"] == "mytui"

    def test_absolute_path_used_directly(self, tmp_path):
        binary = tmp_path / "projection"
        binary.write_text("#!/bin/sh\n")
        assert resolve_projects_command(str(binary)) == str(binary)

    def test_missing_absolute_path_is_none(self, tmp_path):
        assert resolve_projects_command(str(tmp_path / "nope")) is None

    def test_missing_from_path_is_none(self, monkeypatch):
        monkeypatch.setattr(
            "librarian.actions.projects_actions.shutil.which", lambda name: None
        )
        assert resolve_projects_command("") is None

    def test_whitespace_only_config_falls_back_to_default(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "librarian.actions.projects_actions.shutil.which",
            lambda name: seen.setdefault("name", name) and None,
        )
        resolve_projects_command("   ")
        assert seen["name"] == DEFAULT_PROJECTS_COMMAND


class TestToolsMenu:
    def test_projects_is_a_tool(self):
        assert "Projects" in ALL_TOOLS

    def test_projects_is_a_launcher_not_a_panel(self):
        assert "projects" in LAUNCHER_TAB_IDS

    def test_projects_comes_last_in_the_catalog(self):
        """Catalog order is the menu order; new tools append."""
        assert ALL_TOOLS == ("TaskPaper", "Reminders", "Calendar", "Projects")


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    return Config(
        scan_directory=root,
        editor="vim",
        taskpaper="",
        reminders="",
        projects="",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        tools=ToolsConfig(projects=True),
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


@pytest.fixture
def no_embedded_panel(monkeypatch):
    """Force the external-program path, as on a machine without projection.

    projection lives in a private repository and cannot be declared as an
    optional dependency here, so the executable fallback is the *common* case
    rather than a rare one.
    """
    monkeypatch.setattr("librarian.widgets.projects_modal.is_available", lambda: False)


class TestLaunching:
    async def test_selecting_the_tool_launches_projection(
        self, no_embedded_panel, app, monkeypatch, tmp_path
    ):
        """End to end: activating the Projects tab suspends and runs it."""
        binary = tmp_path / "projection"
        binary.write_text("#!/bin/sh\n")
        app.config.projects = str(binary)

        calls = []
        monkeypatch.setattr(
            "librarian.actions.projects_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            suspend = FakeSuspend()
            monkeypatch.setattr(app, "suspend", suspend)

            app.query_one(ToolTabs).active = "tab-projects"
            await pilot.pause()
            await pilot.pause()

            assert suspend.entered
            assert calls == [[str(binary)]]
            # The launcher tab snaps back; the workspace never changes hands.
            assert app.query_one(ToolTabs).active == "tab-local"

    async def test_missing_binary_notifies_instead_of_launching(
        self, no_embedded_panel, app, monkeypatch
    ):
        app.config.projects = "definitely-not-installed"
        monkeypatch.setattr(
            "librarian.actions.projects_actions.shutil.which", lambda name: None
        )

        calls = []
        monkeypatch.setattr(
            "librarian.actions.projects_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            suspend = FakeSuspend()
            monkeypatch.setattr(app, "suspend", suspend)

            app.action_launch_projects()
            await pilot.pause()

            assert calls == []
            assert not suspend.entered
            notifications = [n.message for n in app._notifications]
            assert any("definitely-not-installed" in m for m in notifications)
            assert any("github.com/7robots/projection" in m for m in notifications)

    async def test_subprocess_failure_is_reported(
        self, no_embedded_panel, app, monkeypatch, tmp_path
    ):
        binary = tmp_path / "projection"
        binary.write_text("#!/bin/sh\n")
        app.config.projects = str(binary)

        def boom(cmd, **kw):
            raise OSError("exec format error")

        monkeypatch.setattr("librarian.actions.projects_actions.subprocess.run", boom)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(app, "suspend", FakeSuspend())

            app.action_launch_projects()
            await pilot.pause()

            notifications = [n.message for n in app._notifications]
            assert any("exec format error" in m for m in notifications)

    async def test_launching_leaves_the_panels_alone(
        self, no_embedded_panel, app, monkeypatch, tmp_path
    ):
        """Projects is a launcher, so the Files panel must keep its content."""
        binary = tmp_path / "projection"
        binary.write_text("#!/bin/sh\n")
        app.config.projects = str(binary)
        monkeypatch.setattr(
            "librarian.actions.projects_actions.subprocess.run", lambda cmd, **kw: None
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(app, "suspend", FakeSuspend())

            tag_list = app.query_one(TagList)
            before = tag_list.active_source

            app.action_launch_projects()
            await pilot.pause()

            assert tag_list.active_source == before == "folders"
            assert tag_list.directory_tree.display


class TestEmbedPreferredOverHandoff:
    async def test_the_panel_is_tried_before_the_executable(
        self, app, monkeypatch, tmp_path
    ):
        """With projection importable, Librarian must not suspend."""
        binary = tmp_path / "projection"
        binary.write_text("#!/bin/sh\n")
        app.config.projects = str(binary)

        calls = []
        monkeypatch.setattr(
            "librarian.actions.projects_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )
        # Stand in for a successful embed without needing projection installed.
        monkeypatch.setattr(
            "librarian.actions.projects_actions.ProjectsActionsMixin."
            "_open_projects_panel",
            lambda self: True,
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            suspend = FakeSuspend()
            monkeypatch.setattr(app, "suspend", suspend)

            app.action_launch_projects()
            await pilot.pause()

            assert calls == []
            assert not suspend.entered

    async def test_a_broken_embed_falls_back_rather_than_failing(
        self, app, monkeypatch, tmp_path
    ):
        """An import that blows up must not take the tool -- or the app -- down."""
        binary = tmp_path / "projection"
        binary.write_text("#!/bin/sh\n")
        app.config.projects = str(binary)

        monkeypatch.setattr(
            "librarian.widgets.projects_modal.is_available", lambda: True
        )

        def boom(*args, **kwargs):
            raise RuntimeError("panel exploded on construction")

        monkeypatch.setattr("librarian.app.LibrarianApp.push_screen", boom)

        calls = []
        monkeypatch.setattr(
            "librarian.actions.projects_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(app, "suspend", FakeSuspend())

            app.action_launch_projects()
            await pilot.pause()

            assert app.is_running
            assert calls == [[str(binary)]]


class TestDisabledByDefault:
    @pytest.fixture
    def off_app(self, config, tmp_index):
        from librarian.app import LibrarianApp

        config.tools = ToolsConfig()
        return LibrarianApp(config)

    def test_projects_is_off_in_a_default_config(self):
        assert ToolsConfig().projects is False

    async def test_hidden_from_the_menu(self, off_app):
        async with off_app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            names = [
                str(tab.label)
                for tab in off_app.query_one(ToolTabs).query("Tab")
                if launcher_tool_for(tab.id) is not None
            ]
            assert "Projects" not in names

    async def test_the_action_is_inert_and_says_why(self, off_app, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "librarian.actions.projects_actions.subprocess.run",
            lambda cmd, **kw: calls.append(cmd),
        )

        async with off_app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            suspend = FakeSuspend()
            monkeypatch.setattr(off_app, "suspend", suspend)

            off_app.action_launch_projects()
            await pilot.pause()

            assert calls == []
            assert not suspend.entered
            notifications = [n.message for n in off_app._notifications]
            # The guard names the config key, so the switch stays discoverable.
            assert any("projects = true" in m for m in notifications)
