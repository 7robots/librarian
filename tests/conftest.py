"""Shared fixtures for librarian tests."""

import json
from pathlib import Path

import pytest

from librarian import database


@pytest.fixture
def tmp_index(tmp_path):
    """Initialize database with a fresh temp index and clean up after."""
    index_path = tmp_path / "index.json"
    database.init_database(index_path)
    yield index_path
    # Reset module-level state
    database._index = {}
    database._index_path = None
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
