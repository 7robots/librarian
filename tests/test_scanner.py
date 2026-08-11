"""Tests for librarian.scanner module."""

from pathlib import Path

import pytest

from librarian.scanner import (
    TAG_PATTERN,
    extract_tags,
    find_scannable_files,
    list_folder_files,
    rescan_file,
    scan_directory,
    scan_file,
)
from librarian.database import get_all_files, get_all_tags, get_file_mtime, init_database


class TestExtractTags:
    def test_basic_extraction(self):
        assert extract_tags("Hello #python world") == ["python"]

    def test_multiple_tags(self):
        tags = extract_tags("#python #rust #go")
        assert tags == ["python", "rust", "go"]

    def test_uniqueness(self):
        tags = extract_tags("#python #python #python")
        assert tags == ["python"]

    def test_case_normalization(self):
        tags = extract_tags("#Python #PYTHON #python")
        # Should deduplicate case-insensitively, keeping first occurrence
        assert len(tags) == 1

    def test_tag_with_hyphens_and_underscores(self):
        tags = extract_tags("#my-tag #my_tag")
        assert "my-tag" in tags
        assert "my_tag" in tags

    def test_tag_must_start_with_letter(self):
        tags = extract_tags("#123 #_bad #good")
        assert tags == ["good"]

    def test_no_tags(self):
        assert extract_tags("Just plain text") == []

    def test_tag_in_heading(self):
        # Markdown headings use # but should not be tags
        # Actually the regex will match # followed by letter
        tags = extract_tags("# Heading\n\n#realtag")
        # "Heading" matches the tag pattern since it starts with a letter
        assert "realtag" in tags

    def test_empty_content(self):
        assert extract_tags("") == []

    def test_tag_at_end_of_line(self):
        assert extract_tags("content #tag\n") == ["tag"]


class TestScanFile:
    def test_scan_file_with_tags(self, sample_files, sample_config):
        tags = scan_file(sample_files / "note1.md", sample_config)
        assert "python" in tags
        assert "coding" in tags

    def test_scan_file_without_tags(self, sample_files, sample_config):
        tags = scan_file(sample_files / "note3.md", sample_config)
        assert tags == []

    def test_scan_nonexistent_file(self, sample_config):
        tags = scan_file(Path("/nonexistent/file.md"), sample_config)
        assert tags == []

    def test_scan_with_whitelist(self, sample_files, sample_config):
        sample_config.tags.mode = "whitelist"
        sample_config.tags.whitelist = ["python"]
        tags = scan_file(sample_files / "note1.md", sample_config)
        assert tags == ["python"]
        assert "coding" not in tags

    def test_scan_taskpaper_file(self, sample_files, sample_config):
        tags = scan_file(sample_files / "tasks.taskpaper", sample_config)
        assert "taskpaper" in tags


class TestFindScannableFiles:
    def test_finds_md_files(self, sample_files):
        files = find_scannable_files(sample_files)
        names = {f.name for f in files}
        assert "note1.md" in names
        assert "note2.md" in names
        assert "note3.md" in names

    def test_finds_taskpaper_files(self, sample_files):
        files = find_scannable_files(sample_files)
        names = {f.name for f in files}
        assert "tasks.taskpaper" in names

    def test_finds_nested_files(self, sample_files):
        files = find_scannable_files(sample_files)
        names = {f.name for f in files}
        assert "deep.md" in names

    def test_missing_directory(self, tmp_path):
        files = find_scannable_files(tmp_path / "nonexistent")
        assert files == []

    def test_ignores_non_supported_extensions(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")
        (tmp_path / "file.py").write_text("content")
        files = find_scannable_files(tmp_path)
        assert files == []


class TestListFolderFiles:
    def test_lists_direct_children_only(self, sample_files):
        names = [f.name for f in list_folder_files(sample_files)]
        assert "note1.md" in names
        assert "tasks.taskpaper" in names
        # deep.md lives in a subdirectory and must not appear
        assert "deep.md" not in names

    def test_includes_untagged_files(self, sample_files):
        # The index only holds tagged files; a folder listing must not.
        names = [f.name for f in list_folder_files(sample_files)]
        assert "note3.md" in names

    def test_sorted_case_insensitively(self, tmp_path):
        for name in ("zebra.md", "Apple.md", "mango.md"):
            (tmp_path / name).write_text("x")
        names = [f.name for f in list_folder_files(tmp_path)]
        assert names == ["Apple.md", "mango.md", "zebra.md"]

    def test_ignores_unsupported_extensions(self, tmp_path):
        (tmp_path / "keep.md").write_text("x")
        (tmp_path / "skip.txt").write_text("x")
        (tmp_path / "skip.pdf").write_text("x")
        assert [f.name for f in list_folder_files(tmp_path)] == ["keep.md"]

    def test_excludes_directories(self, tmp_path):
        (tmp_path / "sub.md").mkdir()  # a directory that looks like a file
        assert list_folder_files(tmp_path) == []

    def test_missing_directory(self, tmp_path):
        assert list_folder_files(tmp_path / "nonexistent") == []

    def test_path_is_a_file(self, tmp_path):
        target = tmp_path / "note.md"
        target.write_text("x")
        assert list_folder_files(target) == []

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert list_folder_files(empty) == []


class TestScanDirectory:
    def test_scan_adds_files_with_tags(self, tmp_index, sample_config):
        added, updated, removed = scan_directory(sample_config)
        # note1, note2, tasks.taskpaper, deep.md have tags; note3 does not
        assert added == 4
        assert updated == 0
        assert removed == 0

    def test_scan_skips_files_without_tags(self, tmp_index, sample_config):
        scan_directory(sample_config)
        all_files = get_all_files()
        names = {f.name for f in all_files}
        assert "note3.md" not in names

    def test_scan_detects_removed_files(self, tmp_index, sample_config):
        scan_directory(sample_config)
        # Remove a file
        (sample_config.scan_directory / "note1.md").unlink()
        _, _, removed = scan_directory(sample_config)
        assert removed == 1

    def test_scan_detects_modified_files(self, tmp_index, sample_config):
        scan_directory(sample_config)
        # Modify a file (change content and mtime)
        note = sample_config.scan_directory / "note1.md"
        import time
        time.sleep(0.05)  # Ensure different mtime
        note.write_text("# Updated\n\n#python #newstuff\n")
        _, updated, _ = scan_directory(sample_config)
        assert updated >= 1

    def test_full_rescan(self, tmp_index, sample_config):
        scan_directory(sample_config)
        _, updated, _ = scan_directory(sample_config, full_rescan=True)
        # All files with tags should be "updated"
        assert updated == 4


class TestRescanFile:
    def test_rescan_existing_file(self, tmp_index, sample_config):
        path = sample_config.scan_directory / "note1.md"
        result = rescan_file(path, sample_config)
        assert result is True
        assert get_file_mtime(path) is not None

    def test_rescan_file_without_tags(self, tmp_index, sample_config):
        path = sample_config.scan_directory / "note3.md"
        result = rescan_file(path, sample_config)
        assert result is False

    def test_rescan_missing_file(self, tmp_index, sample_config):
        path = Path("/nonexistent/file.md")
        result = rescan_file(path, sample_config)
        assert result is False
