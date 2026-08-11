"""Tests for librarian.config module."""

from pathlib import Path

import pytest

from librarian.config import (
    CalendarConfig,
    Config,
    FoldersConfig,
    IconConfig,
    ObsidianConfig,
    TagConfig,
    get_config_dir,
    get_default_data_dir,
)


class TestConfigDefaults:
    def test_default_scan_directory(self):
        config = Config()
        assert config.scan_directory == Path.home() / "Documents"

    def test_default_editor(self):
        config = Config()
        assert config.editor == "vim"

    def test_default_data_directory(self):
        config = Config()
        assert config.data_directory == get_default_data_dir()

    def test_get_index_path(self):
        config = Config()
        assert config.get_index_path() == config.data_directory / "index.json"

    def test_default_tag_config(self):
        config = Config()
        assert config.tags.mode == "all"
        assert config.tags.whitelist == []

    def test_default_calendar_config(self):
        config = Config()
        assert config.calendar.calendar_name == ""
        assert config.calendar.icalpal_path == ""


class TestConfigSaveLoad:
    def test_save_creates_file(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".config" / "librarian"
        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("librarian.config.get_config_path", lambda: config_dir / "config.toml")

        config = Config(
            scan_directory=tmp_path / "docs",
            data_directory=tmp_path / "data",
        )
        config.save()
        assert (config_dir / "config.toml").exists()

    def test_round_trip(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".config" / "librarian"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("librarian.config.get_config_path", lambda: config_path)

        original = Config(
            scan_directory=tmp_path / "docs",
            editor="nano",
            taskpaper="/usr/local/bin/taskpapertui",
            tags=TagConfig(mode="whitelist", whitelist=["python", "rust"]),
            export_directory=tmp_path / "exports",
            data_directory=tmp_path / "data",
            calendar=CalendarConfig(calendar_name="Work"),
        )
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        original.save()

        loaded = Config.load()
        assert loaded.scan_directory == original.scan_directory
        assert loaded.editor == original.editor
        assert loaded.taskpaper == original.taskpaper
        assert loaded.tags.mode == original.tags.mode
        assert loaded.tags.whitelist == original.tags.whitelist
        assert loaded.export_directory == original.export_directory
        assert loaded.calendar.calendar_name == original.calendar.calendar_name

    def test_load_creates_defaults_when_missing(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".config" / "librarian"
        data_dir = tmp_path / ".local" / "share" / "librarian"
        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("librarian.config.get_config_path", lambda: config_dir / "config.toml")
        monkeypatch.setattr("librarian.config.get_default_data_dir", lambda: data_dir)

        config = Config.load()
        assert (config_dir / "config.toml").exists()
        assert config.editor == "vim"

    def test_load_partial_config(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".config" / "librarian"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        data_dir = tmp_path / ".local" / "share" / "librarian"
        data_dir.mkdir(parents=True)

        # Write a minimal config with only some fields
        config_path.write_text('scan_directory = "/tmp/docs"\neditor = "code"\n')

        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("librarian.config.get_config_path", lambda: config_path)
        monkeypatch.setattr("librarian.config.get_default_data_dir", lambda: data_dir)

        config = Config.load()
        assert config.scan_directory == Path("/tmp/docs")
        assert config.editor == "code"
        # Defaults for missing fields
        assert config.tags.mode == "all"
        assert config.tools.calendar is False


class TestTagConfig:
    def test_default(self):
        tc = TagConfig()
        assert tc.mode == "all"
        assert tc.whitelist == []

    def test_whitelist_mode(self):
        tc = TagConfig(mode="whitelist", whitelist=["python", "rust"])
        assert tc.mode == "whitelist"
        assert len(tc.whitelist) == 2


class TestCalendarConfig:
    def test_default(self):
        cc = CalendarConfig()
        assert cc.calendar_name == ""
        assert cc.icalpal_path == ""


class TestAppearanceConfig:
    def _write_config(self, tmp_path, monkeypatch, body):
        config_dir = tmp_path / ".config" / "librarian"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        data_dir = tmp_path / ".local" / "share" / "librarian"
        data_dir.mkdir(parents=True)
        config_path.write_text(body)

        monkeypatch.setattr("librarian.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("librarian.config.get_config_path", lambda: config_path)
        monkeypatch.setattr("librarian.config.get_default_data_dir", lambda: data_dir)
        return config_path

    def test_defaults(self):
        config = Config()
        assert config.icons.style == "auto"
        assert config.folders.icons == {}
        assert config.folders.colors == {}
        assert config.obsidian.enabled is True

    def test_loads_icon_style(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, monkeypatch, '[icons]\nstyle = "emoji"\n')
        assert Config.load().icons.style == "emoji"

    def test_loads_folder_icons_and_colors(self, tmp_path, monkeypatch):
        self._write_config(
            tmp_path,
            monkeypatch,
            """
[folders.icons]
"projects" = "briefcase"
"projects/2026" = "calendar"

[folders.colors]
"projects" = "#8b5cf6"
""",
        )
        config = Config.load()

        assert config.folders.icons == {
            "projects": "briefcase",
            "projects/2026": "calendar",
        }
        assert config.folders.colors == {"projects": "#8b5cf6"}

    def test_ignores_non_string_folder_values(self, tmp_path, monkeypatch):
        self._write_config(
            tmp_path,
            monkeypatch,
            '[folders.icons]\n"a" = "book"\n"b" = 3\n"c" = ""\n',
        )
        assert Config.load().folders.icons == {"a": "book"}

    def test_tools_are_all_off_by_default(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, monkeypatch, 'editor = "code"\n')
        tools = Config.load().tools

        assert (tools.taskpaper, tools.reminders, tools.calendar) == (
            False,
            False,
            False,
        )

    def test_tools_can_be_enabled(self, tmp_path, monkeypatch):
        self._write_config(
            tmp_path,
            monkeypatch,
            "[tools]\ntaskpaper = true\nreminders = true\ncalendar = true\n",
        )
        tools = Config.load().tools

        assert (tools.taskpaper, tools.reminders, tools.calendar) == (True, True, True)

    def test_legacy_calendar_enabled_still_turns_the_tool_on(
        self, tmp_path, monkeypatch
    ):
        """The switch used to live at [calendar] enabled."""
        self._write_config(
            tmp_path, monkeypatch, '[calendar]\nenabled = true\ncalendar_name = "Work"\n'
        )
        config = Config.load()

        assert config.tools.calendar is True
        assert config.calendar.calendar_name == "Work"

    def test_tools_section_wins_over_the_legacy_key(self, tmp_path, monkeypatch):
        self._write_config(
            tmp_path,
            monkeypatch,
            "[tools]\ncalendar = false\n\n[calendar]\nenabled = true\n",
        )
        assert Config.load().tools.calendar is False

    def test_legacy_calendar_disabled_is_honored(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, monkeypatch, "[calendar]\nenabled = false\n")
        assert Config.load().tools.calendar is False

    def test_obsidian_can_be_disabled(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, monkeypatch, "[obsidian]\nenabled = false\n")
        assert Config.load().obsidian.enabled is False

    def test_missing_sections_use_defaults(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, monkeypatch, 'editor = "code"\n')
        config = Config.load()

        assert config.icons.style == "auto"
        assert config.folders.icons == {}
        assert config.obsidian.enabled is True

    def test_round_trip(self, tmp_path, monkeypatch):
        config_path = self._write_config(tmp_path, monkeypatch, "")
        Config(
            icons=IconConfig(style="emoji"),
            folders=FoldersConfig(
                icons={"my notes/a.b": "book"}, colors={"my notes": "#fff"}
            ),
            obsidian=ObsidianConfig(enabled=False),
        ).save()

        written = config_path.read_text()
        assert 'style = "emoji"' in written
        assert "[folders.icons]" in written
        assert "enabled = false" in written

        reloaded = Config.load()
        assert reloaded.icons.style == "emoji"
        # Keys with spaces and dots must survive quoting.
        assert reloaded.folders.icons == {"my notes/a.b": "book"}
        assert reloaded.folders.colors == {"my notes": "#fff"}
        assert reloaded.obsidian.enabled is False

    def test_round_trip_with_no_folder_entries(self, tmp_path, monkeypatch):
        """Empty tables are commented out, so reload must not see stray keys."""
        config_path = self._write_config(tmp_path, monkeypatch, "")
        Config().save()

        assert "# [folders.icons]" in config_path.read_text()
        reloaded = Config.load()
        assert reloaded.folders.icons == {}
        assert reloaded.folders.colors == {}
