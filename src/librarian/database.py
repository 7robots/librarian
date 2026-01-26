"""JSON-based index operations for indexing files and tags."""

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

from .config import get_index_path


class FileEntry(TypedDict):
    """Type for a file entry in the index."""

    mtime: float
    tags: list[str]


# In-memory index cache
_index: dict[str, FileEntry] = {}


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

    # Sort by path
    result.sort(key=lambda x: str(x[0]))
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
