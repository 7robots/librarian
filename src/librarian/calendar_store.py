"""Calendar event-to-file association storage."""

import json
import os
import threading
from pathlib import Path
from typing import TypedDict


class Association(TypedDict):
    """Type for a calendar association entry."""

    file: str


# Module state
_store_path: Path | None = None
_associations: dict[str, Association] = {}
_write_lock = threading.Lock()


def init_store(data_directory: Path) -> None:
    """Initialize the association store.

    Args:
        data_directory: Directory where calendar_associations.json is stored.
    """
    global _store_path, _associations
    _store_path = data_directory / "calendar_associations.json"
    _associations = _load()


def _get_store_path() -> Path:
    if _store_path is None:
        raise RuntimeError("Calendar store not initialized. Call init_store() first.")
    return _store_path


def _load() -> dict[str, Association]:
    """Load associations from JSON file."""
    path = _get_store_path()
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text())
        return data.get("associations", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _save() -> None:
    """Save associations to JSON file with atomic write."""
    with _write_lock:
        path = _get_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps({"associations": _associations}, indent=2))
        os.replace(temp_path, path)


def get_association(event_uid: str) -> Path | None:
    """Get the associated file for an event.

    Args:
        event_uid: The calendar event UID.

    Returns:
        Path to the associated file, or None.
    """
    entry = _associations.get(event_uid)
    if entry is None:
        return None

    file_path = Path(entry["file"])
    if file_path.exists():
        return file_path

    # File no longer exists — clean up stale association
    del _associations[event_uid]
    _save()
    return None


def set_association(event_uid: str, file_path: Path) -> None:
    """Associate an event with a file.

    Args:
        event_uid: The calendar event UID.
        file_path: Path to the note file.
    """
    _associations[event_uid] = {"file": str(file_path)}
    _save()


def remove_association(event_uid: str) -> None:
    """Remove an event association.

    Args:
        event_uid: The calendar event UID.
    """
    if event_uid in _associations:
        del _associations[event_uid]
        _save()


def get_all_associations() -> dict[str, Path]:
    """Get all current associations as uid -> Path mapping."""
    result = {}
    for uid, entry in _associations.items():
        path = Path(entry["file"])
        if path.exists():
            result[uid] = path
    return result
