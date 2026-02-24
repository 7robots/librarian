"""Tests for librarian.config module."""

from pathlib import Path

import pytest

from librarian.config import Config, TagConfig, CalendarConfig, get_config_dir, get_default_data_dir


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
        assert config.calendar.enabled is True
        assert config.calendar.calendar_name == ""


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
            calendar=CalendarConfig(enabled=False, calendar_name="Work"),
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
        assert loaded.calendar.enabled == original.calendar.enabled
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
        assert config.calendar.enabled is True


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
        assert cc.enabled is True
        assert cc.calendar_name == ""
        assert cc.icalpal_path == ""
