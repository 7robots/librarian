"""Tests for backfilling options into an existing config file.

`Config.load()` used to write a config only when none existed, so a file created
before an option was added never gained it -- the switch was undiscoverable
without reading the source. A real config had drifted seven keys behind.

The hazard these tests mostly guard is TOML scoping: a bare `key = value`
appended to the end of a file belongs to whatever `[table]` precedes it, so a
naive append silently moves top-level options into the last table.
"""

from __future__ import annotations

import tomllib

import pytest

from librarian.config import Config, _add_missing_keys


def parse(text: str) -> dict:
    return tomllib.loads(text)


class TestKeyPlacement:
    def test_top_level_key_does_not_land_in_the_last_table(self):
        """The whole point: appending `projects` after [tools] would rename it."""
        text = '# Librarian Configuration\nscan_directory = "/notes"\n\n[tools]\nreminders = true\n'
        out = _add_missing_keys(text, parse(text))

        data = parse(out)
        assert "projects" in data, "top-level key missing"
        assert isinstance(data["projects"], str)
        # Not swallowed by [tools], which has its own separate `projects` bool.
        assert data["tools"]["projects"] is False

    def test_top_level_key_goes_above_a_comment_introducing_a_table(self):
        """A comment block above a header belongs to the header, not the preamble."""
        text = (
            'scan_directory = "/notes"\n'
            "\n"
            "# Optional tools shown in the Tools menu.\n"
            "[tools]\n"
            "reminders = true\n"
        )
        out = _add_missing_keys(text, parse(text))
        lines = out.splitlines()

        comment = lines.index("# Optional tools shown in the Tools menu.")
        projects = next(i for i, l in enumerate(lines) if l.startswith("projects ="))
        assert projects < comment, "key was inserted below the table's own comment"
        assert isinstance(parse(out)["projects"], str)

    def test_missing_table_is_created(self):
        text = 'scan_directory = "/notes"\n'
        out = _add_missing_keys(text, parse(text))
        data = parse(out)

        assert data["tools"]["projects"] is False
        assert data["icons"]["style"] == "auto"
        assert data["keys"]["vim"] is False
        assert data["obsidian"]["enabled"] is True
        assert data["calendar"]["calendar_name"] == ""

    def test_a_new_table_of_one_key_is_created(self):
        """[keys] is the newest table; an old config has no header to append to."""
        text = 'scan_directory = "/notes"\n\n[tools]\nreminders = true\n'
        out = _add_missing_keys(text, parse(text))

        assert parse(out)["keys"]["vim"] is False

    def test_key_is_added_to_an_existing_table(self):
        text = "[tools]\nreminders = true\n"
        out = _add_missing_keys(text, parse(text))
        data = parse(out)

        assert data["tools"]["reminders"] is True
        assert data["tools"]["projects"] is False
        assert data["tools"]["calendar"] is False

    def test_key_goes_above_a_comment_introducing_the_next_table(self):
        """A comment between two tables belongs to the one below it.

        TOML scopes the key correctly either way, but inserting below the
        comment reads as though the key belonged to the next section.
        """
        text = (
            "[tools]\n"
            "reminders = true\n"
            "\n"
            '# Tag filtering: "all" or "whitelist"\n'
            "[tags]\n"
            'mode = "all"\n'
        )
        out = _add_missing_keys(text, parse(text))
        lines = out.splitlines()

        comment = lines.index('# Tag filtering: "all" or "whitelist"')
        projects = next(i for i, l in enumerate(lines) if l.startswith("projects ="))
        assert projects < comment
        assert parse(out)["tools"]["projects"] is False

    def test_a_table_with_a_trailing_blank_line_keeps_its_keys_together(self):
        text = "[tools]\nreminders = true\n\n[icons]\nstyle = \"nerd\"\n"
        out = _add_missing_keys(text, parse(text))
        data = parse(out)

        assert data["tools"]["projects"] is False
        assert data["icons"]["style"] == "nerd"


class TestNonDestructive:
    def test_existing_values_survive(self):
        text = (
            'scan_directory = "/my/vault"\n'
            'editor = "nvim"\n'
            "\n"
            "[tools]\n"
            "reminders = true\n"
            "calendar = true\n"
        )
        out = _add_missing_keys(text, parse(text))
        data = parse(out)

        assert data["scan_directory"] == "/my/vault"
        assert data["editor"] == "nvim"
        assert data["tools"]["reminders"] is True
        assert data["tools"]["calendar"] is True

    def test_hand_written_comments_survive(self):
        text = "[tools]\nreminders = true   # I use this one daily\n"
        out = _add_missing_keys(text, parse(text))

        assert "# I use this one daily" in out

    def test_nothing_to_do_returns_none(self):
        """A current file must not be rewritten on every launch."""
        text = 'scan_directory = "/notes"\n'
        once = _add_missing_keys(text, parse(text))
        assert once is not None

        assert _add_missing_keys(once, parse(once)) is None

    def test_is_idempotent(self):
        text = 'scan_directory = "/notes"\n[tools]\nreminders = true\n'
        first = _add_missing_keys(text, parse(text))
        second = _add_missing_keys(first, parse(first))

        assert second is None
        assert parse(first)["tools"]["reminders"] is True

    def test_path_defaults_are_not_backfilled(self):
        """These depend on the environment; a literal would be wrong for others."""
        text = 'scan_directory = "/notes"\n'
        out = _add_missing_keys(text, parse(text))
        data = parse(out)

        assert "export_directory" not in data
        assert "data_directory" not in data


class TestThroughLoad:
    @pytest.fixture
    def config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        return tmp_path / "librarian"

    def test_load_backfills_an_old_config(self, config_dir):
        """The reported symptom: a real config with no `projects` key."""
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"
        path.write_text(
            'scan_directory = "~/vault"\n'
            "\n"
            "[tools]\n"
            "reminders = true   # Apple Reminders via remtui\n"
            "calendar = true    # today's meetings via icalPal\n"
        )

        config = Config.load()
        written = path.read_text()
        data = tomllib.loads(written)

        assert "projects" in data["tools"]
        assert "projects" in data
        assert "style" in data["icons"]
        # Still off -- backfilling makes the switch visible, it does not flip it.
        assert config.tools.projects is False
        # And what was already there is untouched.
        assert config.tools.reminders is True
        assert "# Apple Reminders via remtui" in written

    def test_load_leaves_a_current_config_byte_identical(self, config_dir):
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"

        Config().save()
        before = path.read_bytes()

        Config.load()
        assert path.read_bytes() == before

    def test_a_read_only_config_does_not_stop_startup(self, config_dir, monkeypatch):
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"
        path.write_text('scan_directory = "~/vault"\n')

        def boom(*args, **kwargs):
            raise OSError("read-only file system")

        monkeypatch.setattr("pathlib.Path.write_text", boom)

        config = Config.load()  # must not raise
        assert config.tools.projects is False


class TestCalendarCommandMigration:
    """`[calendar] command` replaced `icalpal_path`, a key named after one tool.

    The old key is still read. That matters more than it looks: migration adds
    `command = ""` to a file that may already carry a real `icalpal_path`, and
    `save()` only writes `command` -- so if the fallback did not adopt the old
    value, the next save would silently drop it.
    """

    @pytest.fixture
    def config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        return tmp_path / "librarian"

    def test_an_old_icalpal_path_is_adopted(self, config_dir):
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"
        path.write_text(
            'scan_directory = "~/vault"\n'
            "\n"
            "[calendar]\n"
            'icalpal_path = "/opt/homebrew/bin/icalPal"\n'
        )

        assert Config.load().calendar.command == "/opt/homebrew/bin/icalPal"

    def test_the_adopted_value_survives_a_save(self, config_dir):
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"
        path.write_text(
            'scan_directory = "~/vault"\n'
            "\n"
            "[calendar]\n"
            'icalpal_path = "/opt/homebrew/bin/icalPal"\n'
        )

        config = Config.load()
        config.save()
        reloaded = tomllib.loads(path.read_text())

        assert reloaded["calendar"]["command"] == "/opt/homebrew/bin/icalPal"

    def test_the_new_key_wins_when_both_are_present(self, config_dir):
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"
        path.write_text(
            'scan_directory = "~/vault"\n'
            "\n"
            "[calendar]\n"
            'icalpal_path = "/opt/homebrew/bin/icalPal"\n'
            'command = "calctl"\n'
        )

        assert Config.load().calendar.command == "calctl"

    def test_an_empty_new_key_does_not_shadow_the_old_one(self, config_dir):
        """Migration writes `command = ""`, which must not blank a real setting."""
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"
        path.write_text(
            'scan_directory = "~/vault"\n'
            "\n"
            "[calendar]\n"
            'icalpal_path = "/opt/homebrew/bin/icalPal"\n'
            'command = ""\n'
        )

        assert Config.load().calendar.command == "/opt/homebrew/bin/icalPal"

    def test_a_config_with_neither_key_gets_the_new_one(self, config_dir):
        config_dir.mkdir(parents=True)
        path = config_dir / "config.toml"
        path.write_text('scan_directory = "~/vault"\n')

        config = Config.load()
        assert "command" in tomllib.loads(path.read_text())["calendar"]
        # Empty means auto-detect, which prefers calctl.
        assert config.calendar.command == ""
