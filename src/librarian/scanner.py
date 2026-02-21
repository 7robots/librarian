"""File scanning and tag extraction for markdown files."""

import re
from pathlib import Path

from .config import Config
from .database import (
    add_file,
    batch_writes,
    get_all_files,
    get_file_mtime,
    init_database,
    remove_file,
    cleanup_orphaned_tags,
)

# Regex pattern for hashtags: # followed by letter, then letters/numbers/underscores/hyphens
TAG_PATTERN = re.compile(r"#([a-zA-Z][a-zA-Z0-9_-]*)")


def extract_tags(content: str) -> list[str]:
    """Extract unique hashtags from markdown content."""
    tags = TAG_PATTERN.findall(content)
    # Return unique tags, preserving case
    seen = set()
    unique_tags = []
    for tag in tags:
        lower_tag = tag.lower()
        if lower_tag not in seen:
            seen.add(lower_tag)
            unique_tags.append(tag)
    return unique_tags


def scan_file(path: Path, config: Config) -> list[str]:
    """Scan a single file and extract tags, applying whitelist if configured."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    tags = extract_tags(content)

    # Apply whitelist filtering if configured
    if config.tags.mode == "whitelist" and config.tags.whitelist:
        whitelist_lower = {t.lower() for t in config.tags.whitelist}
        tags = [t for t in tags if t.lower() in whitelist_lower]

    return tags


SUPPORTED_EXTENSIONS = {".md", ".taskpaper"}


def find_scannable_files(directory: Path) -> list[Path]:
    """Recursively find all supported files (.md, .taskpaper) in a directory."""
    if not directory.exists():
        return []

    files = []
    try:
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
    except PermissionError:
        pass

    return files


def scan_directory(config: Config, full_rescan: bool = False) -> tuple[int, int, int]:
    """
    Scan the configured directory for markdown files and update the index.

    Args:
        config: Application configuration
        full_rescan: If True, rescan all files regardless of mtime

    Returns:
        Tuple of (added, updated, removed) file counts
    """
    init_database(config.get_index_path())

    scan_dir = config.scan_directory
    scannable_files = find_scannable_files(scan_dir)

    # Track current file paths
    current_paths = {str(p) for p in scannable_files}

    # Get previously indexed files
    indexed_files = get_all_files()
    indexed_paths = {str(p) for p in indexed_files}

    added = 0
    updated = 0
    removed = 0

    # Batch all writes to save only once at the end
    with batch_writes():
        # Remove files that no longer exist
        for path in indexed_files:
            if str(path) not in current_paths:
                remove_file(path)
                removed += 1

        # Add or update files
        for path in scannable_files:
            mtime = path.stat().st_mtime

            if str(path) not in indexed_paths:
                # New file
                tags = scan_file(path, config)
                if tags:  # Only index files with tags
                    add_file(path, mtime, tags)
                    added += 1
            elif full_rescan or get_file_mtime(path) != mtime:
                # Modified file
                tags = scan_file(path, config)
                if tags:
                    add_file(path, mtime, tags)
                    updated += 1
                else:
                    # File no longer has tags, remove it
                    remove_file(path)
                    removed += 1

    # Clean up orphaned tags
    cleanup_orphaned_tags()

    return added, updated, removed


def rescan_file(path: Path, config: Config) -> bool:
    """
    Rescan a single file and update the index.

    Returns True if the file was indexed (has tags), False otherwise.
    """
    if not path.exists() or not path.is_file():
        remove_file(path)
        cleanup_orphaned_tags()
        return False

    mtime = path.stat().st_mtime
    tags = scan_file(path, config)

    if tags:
        add_file(path, mtime, tags)
        return True
    else:
        remove_file(path)
        cleanup_orphaned_tags()
        return False
