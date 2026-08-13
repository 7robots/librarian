"""Shared fixtures for librarian tests."""

import json
from pathlib import Path

import pytest

from librarian import database


@pytest.fixture(autouse=True)
def isolate_projection_paths(monkeypatch, tmp_path):
    """Keep the embed tests away from the real projection config and store.

    `ProjectsPanel` reads projection's own config when it is not handed one --
    which is exactly what happens here, since a host has no reason to know about
    it -- and from that config comes the path to projection's project store,
    which is its *source of record*, not a cache. A test that builds a panel
    therefore reads, migrates and rewrites real user data.

    Today nothing does, but only because `fake_backend` stubs the sync
    coordinator out; the protection is a side effect of that stubbing rather than
    anything deliberate. One new test that mounts a panel without asking for that
    fixture would be enough. projection's own suite has the same fixture for the
    same reason.

    A no-op when projection is not installed.
    """
    try:
        from projection import config as projection_config
        from projection import local_storage as projection_storage
    except ImportError:
        return

    monkeypatch.setattr(projection_config, "CONFIG_DIR", tmp_path / "pconfig")
    monkeypatch.setattr(
        projection_config,
        "DEFAULT_CONFIG_FILE",
        tmp_path / "pconfig" / "config.toml",
    )
    monkeypatch.setattr(projection_config, "DATA_DIR", tmp_path / "pdata")
    # `LocalStorage` carries its own default, independent of the config module's.
    monkeypatch.setattr(
        projection_storage, "DEFAULT_STORAGE_DIR", tmp_path / "pdata"
    )
    # Write the sandbox config, so the panel does not read this as projection's
    # *first* run -- which opens its setup wizard over Librarian's modal. That
    # behavior is projection's, and is tested there; here it would just cover the
    # panel every test is trying to look at. `test_projects_panel.py` opens the
    # wizard deliberately, by key, to check it works over Librarian.
    config_file = tmp_path / "pconfig" / "config.toml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text('backend = ""\n')


@pytest.fixture
def tmp_index(tmp_path):
    """Initialize database with a fresh temp index and clean up after."""
    index_path = tmp_path / "index.json"
    database.init_database(index_path)
    yield index_path
    # Reset module-level state
    database._index = {}
    database._index_path = None
    database._index_loaded = False
    database._batch_mode = False
    database._batch_dirty = False


@pytest.fixture
def sample_files(tmp_path):
    """Create sample markdown and taskpaper files in a temp directory."""
    docs = tmp_path / "docs"
    docs.mkdir()

    (docs / "note1.md").write_text("# Note 1\n\nSome content #python #coding\n")
    (docs / "note2.md").write_text("# Note 2\n\n#python #testing\n")
    (docs / "note3.md").write_text("# Note 3\n\nNo tags here\n")
    (docs / "tasks.taskpaper").write_text("Inbox:\n\t- Task 1\n\n#taskpaper\n")

    sub = docs / "subdir"
    sub.mkdir()
    (sub / "deep.md").write_text("# Deep\n\n#python #deep\n")

    return docs


@pytest.fixture
def sample_config(tmp_path, sample_files):
    """Create a Config pointing to sample_files directory."""
    from librarian.config import Config, TagConfig, CalendarConfig

    return Config(
        scan_directory=sample_files,
        editor="vim",
        taskpaper="",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
    )
