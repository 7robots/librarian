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

    def test_markdown_heading_is_not_a_tag(self):
        # A heading has a space after the `#`, so it never matches.
        assert extract_tags("# Heading\n\n#realtag") == ["realtag"]

    def test_heading_without_a_space_is_treated_as_a_tag(self):
        # `#Heading` is indistinguishable from a tag, and Obsidian agrees.
        assert extract_tags("#Heading") == ["Heading"]

    def test_empty_content(self):
        assert extract_tags("") == []

    def test_link_anchors_are_not_tags(self):
        """The regression: markdown link anchors were becoming tags."""
        content = "- [LMA](./LMA.md#lma)\n- [Obs](../platform/Observability.md#observability)\n"
        assert extract_tags(content) == []

    def test_url_fragments_are_not_tags(self):
        content = (
            "See https://docs.google.com/presentation/d/abc/edit#slide=id.p1 and\n"
            "https://example.com/page#heading=h.xyz\n"
        )
        assert extract_tags(content) == []

    def test_tag_must_follow_whitespace_or_start_a_line(self):
        assert extract_tags("word#nottag") == []
        assert extract_tags("(#nottag)") == []
        assert extract_tags("a/b#nottag") == []
        assert extract_tags("#tag") == ["tag"]
        assert extract_tags("text #tag") == ["tag"]
        assert extract_tags("text\n#tag") == ["tag"]
        assert extract_tags("text\t#tag") == ["tag"]

    def test_tag_at_start_of_content(self):
        assert extract_tags("#first and more") == ["first"]

    def test_real_tags_survive_alongside_anchors(self):
        content = "# Notes\n\n#arete\n\n- [LMA](./LMA.md#lma)\n\nmore #meetings\n"
        assert extract_tags(content) == ["arete", "meetings"]

    def test_fenced_code_is_ignored(self):
        content = "#real\n\n```c\n#include <stdio.h>\n#define X 1\n```\n"
        assert extract_tags(content) == ["real"]

    def test_tilde_fenced_code_is_ignored(self):
        content = "~~~\n#notatag\n~~~\n\n#real\n"
        assert extract_tags(content) == ["real"]

    def test_inline_code_is_ignored(self):
        assert extract_tags("use `#notatag` here, but #real counts") == ["real"]

    def test_unbalanced_fence_does_not_swallow_later_tags(self):
        """A stray fence must not cost the rest of the file its tags."""
        content = "```\nsome code\n\n#real\n"
        assert extract_tags(content) == ["real"]

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


class TestScannerVersionForcesRescan:
    """A tag-rules change must not wait for mtimes that will never change."""

    @pytest.fixture
    def config(self, tmp_path, sample_config):
        """sample_config with its index inside tmp_path."""
        sample_config.data_directory = tmp_path
        return sample_config

    def write_old_index(self, config, tags, scanner_version):
        """An index as an older scanner would have left it."""
        import json

        note = config.scan_directory / "note1.md"
        payload = {
            "files": {str(note): {"mtime": note.stat().st_mtime, "tags": tags}}
        }
        if scanner_version is not None:
            payload["scanner_version"] = scanner_version
        config.get_index_path().write_text(json.dumps(payload))

    def test_stale_version_triggers_a_rescan(self, config):
        # Holds a tag the current rules reject, on a file whose mtime is current.
        self.write_old_index(config, ["python", "nottag"], scanner_version=1)
        init_database(config.get_index_path())

        scan_directory(config)

        assert "nottag" not in {name for name, _ in get_all_tags()}

    def test_missing_version_triggers_a_rescan(self, config):
        """Indexes written before the field existed have no version at all."""
        self.write_old_index(config, ["python", "nottag"], scanner_version=None)
        init_database(config.get_index_path())

        scan_directory(config)

        assert "nottag" not in {name for name, _ in get_all_tags()}

    def test_current_version_is_recorded_on_write(self, config):
        import json

        from librarian.scanner import SCANNER_VERSION

        init_database(config.get_index_path())
        scan_directory(config)

        written = json.loads(config.get_index_path().read_text())
        assert written["scanner_version"] == SCANNER_VERSION

    def test_matching_version_still_honors_mtime(self, config):
        """With versions equal, an unchanged file is not re-read."""
        init_database(config.get_index_path())
        scan_directory(config)

        assert scan_directory(config) == (0, 0, 0)
