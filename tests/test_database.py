"""Tests for librarian.database module."""

import json
from pathlib import Path

import pytest

from librarian.database import (
    add_file,
    batch_writes,
    clear_index,
    get_all_files,
    get_all_tags,
    get_file_mtime,
    get_files_by_tag,
    init_database,
    remove_file,
    resolve_wiki_link,
    search_files,
)


class TestInitDatabase:
    def test_init_creates_empty_index(self, tmp_index):
        assert get_all_files() == []
        assert get_all_tags() == []

    def test_init_loads_existing_index(self, tmp_path):
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps({
            "files": {
                "/tmp/test.md": {"mtime": 100.0, "tags": ["python"]}
            }
        }))
        init_database(index_path)
        assert len(get_all_files()) == 1

    def test_init_handles_corrupt_json(self, tmp_path):
        index_path = tmp_path / "index.json"
        index_path.write_text("not json{{{")
        init_database(index_path)
        assert get_all_files() == []

    def test_init_handles_missing_files_key(self, tmp_path):
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps({"other": "data"}))
        init_database(index_path)
        assert get_all_files() == []


class TestAddRemoveFile:
    def test_add_file(self, tmp_index):
        path = Path("/tmp/test.md")
        add_file(path, 100.0, ["python", "coding"])
        assert get_file_mtime(path) == 100.0
        assert path in get_all_files()

    def test_add_file_persists(self, tmp_index):
        path = Path("/tmp/test.md")
        add_file(path, 100.0, ["python"])
        # Re-init from disk
        init_database(tmp_index)
        assert get_file_mtime(path) == 100.0

    def test_update_file(self, tmp_index):
        path = Path("/tmp/test.md")
        add_file(path, 100.0, ["python"])
        add_file(path, 200.0, ["python", "updated"])
        assert get_file_mtime(path) == 200.0
        tags = get_all_tags()
        tag_names = [t[0] for t in tags]
        assert "updated" in tag_names

    def test_remove_file(self, tmp_index):
        path = Path("/tmp/test.md")
        add_file(path, 100.0, ["python"])
        remove_file(path)
        assert get_file_mtime(path) is None
        assert path not in get_all_files()

    def test_remove_nonexistent_file(self, tmp_index):
        # Should not raise
        remove_file(Path("/tmp/nonexistent.md"))

    def test_get_file_mtime_missing(self, tmp_index):
        assert get_file_mtime(Path("/tmp/missing.md")) is None


class TestGetAllTags:
    def test_empty_index(self, tmp_index):
        assert get_all_tags() == []

    def test_tag_counts(self, tmp_index):
        add_file(Path("/tmp/a.md"), 100.0, ["python", "coding"])
        add_file(Path("/tmp/b.md"), 200.0, ["python", "testing"])
        tags = get_all_tags()
        tag_dict = dict(tags)
        assert tag_dict["python"] == 2
        assert tag_dict["coding"] == 1
        assert tag_dict["testing"] == 1

    def test_sorted_by_count_then_name(self, tmp_index):
        add_file(Path("/tmp/a.md"), 100.0, ["beta", "alpha"])
        add_file(Path("/tmp/b.md"), 200.0, ["beta"])
        tags = get_all_tags()
        # beta (2) before alpha (1)
        assert tags[0] == ("beta", 2)
        assert tags[1] == ("alpha", 1)

    def test_equal_counts_sorted_alphabetically(self, tmp_index):
        add_file(Path("/tmp/a.md"), 100.0, ["zebra", "apple"])
        tags = get_all_tags()
        assert tags[0][0] == "apple"
        assert tags[1][0] == "zebra"


class TestGetFilesByTag:
    def test_filter_by_tag(self, tmp_index):
        add_file(Path("/tmp/a.md"), 100.0, ["python"])
        add_file(Path("/tmp/b.md"), 200.0, ["rust"])
        add_file(Path("/tmp/c.md"), 300.0, ["python", "rust"])
        files = get_files_by_tag("python")
        paths = [f[0] for f in files]
        assert Path("/tmp/a.md") in paths
        assert Path("/tmp/c.md") in paths
        assert Path("/tmp/b.md") not in paths

    def test_sorted_by_mtime_descending(self, tmp_index):
        add_file(Path("/tmp/old.md"), 100.0, ["python"])
        add_file(Path("/tmp/new.md"), 300.0, ["python"])
        add_file(Path("/tmp/mid.md"), 200.0, ["python"])
        files = get_files_by_tag("python")
        mtimes = [f[1] for f in files]
        assert mtimes == [300.0, 200.0, 100.0]

    def test_nonexistent_tag(self, tmp_index):
        assert get_files_by_tag("nonexistent") == []


class TestSearchFiles:
    def test_search_by_filename(self, tmp_index):
        add_file(Path("/tmp/python-guide.md"), 100.0, ["tutorial"])
        add_file(Path("/tmp/rust-guide.md"), 200.0, ["tutorial"])
        results = search_files("python")
        assert len(results) == 1
        assert results[0][0] == Path("/tmp/python-guide.md")

    def test_search_by_tag(self, tmp_index):
        add_file(Path("/tmp/notes.md"), 100.0, ["python", "coding"])
        results = search_files("coding")
        assert len(results) == 1
        assert "coding" in results[0][2]

    def test_search_case_insensitive(self, tmp_index):
        add_file(Path("/tmp/Notes.md"), 100.0, ["Python"])
        results = search_files("python")
        assert len(results) == 1

    def test_search_empty_query(self, tmp_index):
        add_file(Path("/tmp/notes.md"), 100.0, ["python"])
        assert search_files("") == []
        assert search_files("   ") == []

    def test_search_partial_match(self, tmp_index):
        add_file(Path("/tmp/my-notes.md"), 100.0, ["programming"])
        results = search_files("note")
        assert len(results) == 1
        results = search_files("program")
        assert len(results) == 1


class TestResolveWikiLink:
    def test_resolve_by_filename(self, tmp_index, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("content")
        add_file(note, 100.0, ["test"])
        result = resolve_wiki_link("note.md")
        assert result == note

    def test_resolve_with_extension_appended(self, tmp_index, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("content")
        add_file(note, 100.0, ["test"])
        result = resolve_wiki_link("note")
        assert result == note

    def test_resolve_relative_to_current_file(self, tmp_index, tmp_path):
        current = tmp_path / "dir" / "current.md"
        current.parent.mkdir()
        current.write_text("content")
        target = tmp_path / "dir" / "sibling.md"
        target.write_text("content")
        result = resolve_wiki_link("sibling.md", current)
        assert result == target.resolve()

    def test_resolve_not_found(self, tmp_index):
        result = resolve_wiki_link("nonexistent.md")
        assert result is None

    def test_resolve_path_suffix(self, tmp_index, tmp_path):
        note = tmp_path / "folder" / "note.md"
        note.parent.mkdir()
        note.write_text("content")
        add_file(note, 100.0, ["test"])
        result = resolve_wiki_link("folder/note.md")
        assert result == note

    def test_resolve_case_insensitive(self, tmp_index, tmp_path):
        note = tmp_path / "MyNote.md"
        note.write_text("content")
        add_file(note, 100.0, ["test"])
        result = resolve_wiki_link("mynote.md")
        assert result == note


class TestBatchWrites:
    def test_batch_defers_writes(self, tmp_index):
        with batch_writes():
            add_file(Path("/tmp/a.md"), 100.0, ["python"])
            add_file(Path("/tmp/b.md"), 200.0, ["rust"])
            # Index file should not be updated mid-batch
            data = json.loads(tmp_index.read_text()) if tmp_index.exists() else {"files": {}}
            assert len(data["files"]) == 0

        # After batch exits, file should be written
        data = json.loads(tmp_index.read_text())
        assert len(data["files"]) == 2

    def test_batch_single_write(self, tmp_index):
        with batch_writes():
            for i in range(10):
                add_file(Path(f"/tmp/file{i}.md"), float(i), ["tag"])
        # All 10 files should be persisted
        init_database(tmp_index)
        assert len(get_all_files()) == 10


class TestClearIndex:
    def test_clear(self, tmp_index):
        add_file(Path("/tmp/a.md"), 100.0, ["python"])
        clear_index()
        assert get_all_files() == []
        assert get_all_tags() == []
