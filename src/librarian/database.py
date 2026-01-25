"""SQLite database operations for indexing files and tags."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from .config import get_database_path


def get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_database() -> None:
    """Initialize the database schema."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                mtime REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS file_tags (
                file_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (file_id, tag_id),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
            CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
        """)


def get_or_create_tag(conn: sqlite3.Connection, tag_name: str) -> int:
    """Get or create a tag, returning its ID."""
    cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    row = cursor.fetchone()
    if row:
        return row["id"]

    cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
    return cursor.lastrowid


def add_file(path: Path, mtime: float, tags: list[str]) -> None:
    """Add or update a file with its tags."""
    path_str = str(path)

    with get_db() as conn:
        # Check if file exists
        cursor = conn.execute("SELECT id FROM files WHERE path = ?", (path_str,))
        row = cursor.fetchone()

        if row:
            file_id = row["id"]
            # Update mtime
            conn.execute("UPDATE files SET mtime = ? WHERE id = ?", (mtime, file_id))
            # Remove old tag associations
            conn.execute("DELETE FROM file_tags WHERE file_id = ?", (file_id,))
        else:
            # Insert new file
            cursor = conn.execute(
                "INSERT INTO files (path, mtime) VALUES (?, ?)",
                (path_str, mtime),
            )
            file_id = cursor.lastrowid

        # Add tag associations
        for tag in tags:
            tag_id = get_or_create_tag(conn, tag)
            conn.execute(
                "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
                (file_id, tag_id),
            )


def remove_file(path: Path) -> None:
    """Remove a file and its tag associations."""
    with get_db() as conn:
        conn.execute("DELETE FROM files WHERE path = ?", (str(path),))


def get_file_mtime(path: Path) -> float | None:
    """Get the stored mtime for a file, or None if not indexed."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT mtime FROM files WHERE path = ?", (str(path),)
        )
        row = cursor.fetchone()
        return row["mtime"] if row else None


def get_all_tags() -> list[tuple[str, int]]:
    """Get all tags with their file counts, sorted by count descending."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT t.name, COUNT(ft.file_id) as count
            FROM tags t
            JOIN file_tags ft ON t.id = ft.tag_id
            GROUP BY t.id
            ORDER BY count DESC, t.name ASC
        """)
        return [(row["name"], row["count"]) for row in cursor.fetchall()]


def get_files_by_tag(tag_name: str) -> list[tuple[Path, float]]:
    """Get all files with a specific tag."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT f.path, f.mtime
            FROM files f
            JOIN file_tags ft ON f.id = ft.file_id
            JOIN tags t ON ft.tag_id = t.id
            WHERE t.name = ?
            ORDER BY f.path
        """, (tag_name,))
        return [(Path(row["path"]), row["mtime"]) for row in cursor.fetchall()]


def get_all_files() -> list[Path]:
    """Get all indexed file paths."""
    with get_db() as conn:
        cursor = conn.execute("SELECT path FROM files ORDER BY path")
        return [Path(row["path"]) for row in cursor.fetchall()]


def clear_index() -> None:
    """Clear all indexed data."""
    with get_db() as conn:
        conn.executescript("""
            DELETE FROM file_tags;
            DELETE FROM files;
            DELETE FROM tags;
        """)


def cleanup_orphaned_tags() -> None:
    """Remove tags that have no associated files."""
    with get_db() as conn:
        conn.execute("""
            DELETE FROM tags
            WHERE id NOT IN (SELECT DISTINCT tag_id FROM file_tags)
        """)
