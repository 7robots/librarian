"""File scanning and tag extraction for markdown files."""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

from .config import Config
from .database import (
    add_file,
    get_index_scanner_version,
    batch_writes,
    get_all_files,
    get_file_mtime,
    init_database,
    remove_file,
    cleanup_orphaned_tags,
)

# Bumped whenever tag extraction changes meaning, so an index built by an older
# version is rescanned rather than trusted -- scanning skips files by mtime, and
# a rules change does not touch mtimes.
#   1: initial
#   2: `#` must start a line or follow whitespace; code blocks ignored
SCANNER_VERSION = 2

# A hashtag is `#` followed by a letter, then letters/numbers/underscores/
# hyphens -- and the `#` must start a line or follow whitespace. That last part
# matters more than it looks: without it, every URL fragment and link anchor in
# the vault becomes a tag. `[LMA](./LMA.md#lma)` and a Google Docs link ending
# `#slide=id.p` were producing #lma and #slide, which is why Librarian once
# listed 55 tags for a vault Obsidian showed 2 for. Obsidian applies the same
# rule.
TAG_PATTERN = re.compile(r"(?<![^\s])#([a-zA-Z][a-zA-Z0-9_-]*)")

# Fenced code blocks, requiring a closing fence so an unbalanced one does not
# swallow the rest of the file (and with it any real tags below).
FENCED_CODE_PATTERN = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)

# Inline code spans, which stay on one line.
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")


def strip_code(content: str) -> str:
    """Blank out code blocks and inline code before looking for tags.

    Obsidian does not read tags inside code, and neither should we: `#include`
    at the start of a line in a C snippet is not a tag.
    """
    without_blocks = FENCED_CODE_PATTERN.sub(" ", content)
    return INLINE_CODE_PATTERN.sub(" ", without_blocks)


def extract_tags(content: str) -> list[str]:
    """Extract unique hashtags from markdown content."""
    tags = TAG_PATTERN.findall(strip_code(content))
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


def list_folder_files(directory: Path) -> list[Path]:
    """List supported files directly inside a directory, sorted by name.

    Only immediate children -- descendants are not included, matching Notebook
    Navigator's own ``includeDescendantNotes = false`` default.

    This reads the filesystem rather than the index on purpose: the index holds
    only files carrying at least one hashtag, so a folder-organized vault would
    look almost empty if listed from there.
    """
    if not directory.is_dir():
        return []

    files = []
    try:
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
    except PermissionError:
        return []

    return sorted(files, key=lambda p: p.name.lower())


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

    if not full_rescan and get_index_scanner_version() != SCANNER_VERSION:
        # Tag rules have changed since this index was written; mtimes cannot
        # tell us that, so re-read everything once.
        logger.info(
            "Index built by scanner version %s, now %s: forcing a full rescan",
            get_index_scanner_version(),
            SCANNER_VERSION,
        )
        full_rescan = True

    scan_dir = config.scan_directory
    logger.info("Scanning directory: %s (full_rescan=%s)", scan_dir, full_rescan)
    scannable_files = find_scannable_files(scan_dir)
    logger.debug("Found %d scannable files", len(scannable_files))

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

    logger.info("Scan complete: %d added, %d updated, %d removed", added, updated, removed)
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
