"""JSON-based index operations for indexing files and tags."""

import json
import os
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, TypedDict

from .config import get_index_path


class FileEntry(TypedDict):
    """Type for a file entry in the index."""

    mtime: float
    tags: list[str]


# In-memory index cache
_index: dict[str, FileEntry] = {}

# Batch mode: when True, defer saves until batch ends
_batch_mode: bool = False
_batch_dirty: bool = False


def _load_index() -> dict[str, FileEntry]:
    """Load index from JSON file."""
    index_path = get_index_path()
    if not index_path.exists():
        return {}

    try:
        data = json.loads(index_path.read_text())
        return data.get("files", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _save_index() -> None:
    """Save index to JSON file with atomic write."""
    global _batch_dirty

    # In batch mode, just mark dirty and defer the save
    if _batch_mode:
        _batch_dirty = True
        return

    index_path = get_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = index_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps({"files": _index}, indent=2))
    os.replace(temp_path, index_path)


@contextmanager
def batch_writes() -> Generator[None, None, None]:
    """Context manager for batching database writes.

    All add_file() and remove_file() calls within this context
    will be batched and written to disk only once at the end.
    """
    global _batch_mode, _batch_dirty
    _batch_mode = True
    _batch_dirty = False
    try:
        yield
    finally:
        _batch_mode = False
        if _batch_dirty:
            _batch_dirty = False
            # Force save now
            index_path = get_index_path()
            index_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = index_path.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps({"files": _index}, indent=2))
            os.replace(temp_path, index_path)


def init_database() -> None:
    """Initialize the index by loading from JSON file."""
    global _index
    _index = _load_index()


def add_file(path: Path, mtime: float, tags: list[str]) -> None:
    """Add or update a file with its tags."""
    _index[str(path)] = {"mtime": mtime, "tags": tags}
    _save_index()


def remove_file(path: Path) -> None:
    """Remove a file from the index."""
    path_str = str(path)
    if path_str in _index:
        del _index[path_str]
        _save_index()


def get_file_mtime(path: Path) -> float | None:
    """Get the stored mtime for a file, or None if not indexed."""
    entry = _index.get(str(path))
    return entry["mtime"] if entry else None


def get_all_tags() -> list[tuple[str, int]]:
    """Get all tags with their file counts, sorted by count descending."""
    tag_counts: dict[str, int] = defaultdict(int)

    for entry in _index.values():
        for tag in entry["tags"]:
            tag_counts[tag] += 1

    # Sort by count descending, then name ascending
    sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
    return sorted_tags


def get_files_by_tag(tag_name: str) -> list[tuple[Path, float]]:
    """Get all files with a specific tag."""
    result = []
    for path_str, entry in _index.items():
        if tag_name in entry["tags"]:
            result.append((Path(path_str), entry["mtime"]))

    # Sort by mtime descending (most recently modified first)
    result.sort(key=lambda x: x[1], reverse=True)
    return result


def get_all_files() -> list[Path]:
    """Get all indexed file paths."""
    return sorted(Path(p) for p in _index.keys())


def clear_index() -> None:
    """Clear all indexed data."""
    global _index
    _index = {}
    _save_index()


def cleanup_orphaned_tags() -> None:
    """No-op: tags are inline in JSON, no orphans possible."""
    pass


def resolve_wiki_link(target: str, current_file: Path | None = None) -> Path | None:
    """Resolve a wiki link target to a file path.

    Resolution order:
    1. Relative to current file's directory (if current_file provided)
    2. Search by filename in index
    3. Try appending .md extension if missing

    Args:
        target: The wiki link target (e.g., "note.md" or "folder/note")
        current_file: The file containing the wiki link (for relative resolution)

    Returns:
        Resolved Path or None if not found
    """
    # Normalize target - remove leading/trailing whitespace
    target = target.strip()

    # List of targets to try (original and with .md extension)
    targets_to_try = [target]
    if not target.lower().endswith(".md"):
        targets_to_try.append(f"{target}.md")

    for try_target in targets_to_try:
        # 1. Try relative to current file's directory
        if current_file is not None:
            relative_path = current_file.parent / try_target
            if relative_path.exists() and relative_path.is_file():
                return relative_path.resolve()

        # 2. Search by filename in index
        target_name = Path(try_target).name.lower()
        for path_str in _index.keys():
            indexed_path = Path(path_str)
            if indexed_path.name.lower() == target_name:
                if indexed_path.exists():
                    return indexed_path

        # 3. Search by path suffix (for targets like "folder/note.md")
        if "/" in try_target:
            target_suffix = try_target.lower()
            for path_str in _index.keys():
                if path_str.lower().endswith(target_suffix):
                    indexed_path = Path(path_str)
                    if indexed_path.exists():
                        return indexed_path

    return None
